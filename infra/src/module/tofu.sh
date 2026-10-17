#!/usr/bin/env bash

## cloud provisioning through opentofu — stacks live in template/tofu/<cloud>/stacks

tofu_dir () {

    printf '%s' "${TEMPLATE_DIR}/tofu/${CLOUD}/stacks/${PROVISIONER}"

}
tofu_stack () {

    [[ -n "${PROVISIONER}" ]] || die "Stack '${STACK}' provisions nothing — tofu runs where PROVISIONER names a stack"

}
tofu_vars () {

    local file="${BUILD_DIR}/tofu/${CLOUD}-${PROVISIONER}.tfvars"

    tofu_stack
    ensure_dir "$(dirname "${file}")"

    cloud tofu_vars > "${file}"

    printf '%s' "${file}"

}
tofu_secrets () {

    if [[ "${DATABASE}" == "managed" ]]; then

        TF_VAR_db_password="$(secret_require DB_PASSWORD)"
        export TF_VAR_db_password

    fi

}
tofu_cache () {

    export TF_PLUGIN_CACHE_DIR="${BUILD_DIR}/tofu/plugins"

    ensure_dir "${TF_PLUGIN_CACHE_DIR}"

}
## prepare the provider (state and backup buckets, stale lock) and initialize the stack backend
tofu_init () {

    local flags=()

    ensure tofu

    tofu_stack
    cloud tofu_prereqs

    tofu_cache

    mapfile -t flags < <(cloud backend_flags)

    run tofu -chdir="$(tofu_dir)" init -input=false "${flags[@]}"

}
## converge the cloud: nothing to provision on a bring-your-own stack, otherwise init → plan → guard → apply (idempotent)
tofu_ensure () {

    local plan=""

    [[ -n "${PROVISIONER}" ]] || { info "Stack '${STACK}' provisions nothing — cloud converge skipped."; return 0; }

    tofu_init

    plan="${BUILD_DIR}/tofu/${CLOUD}-${PROVISIONER}.plan"

    tofu_plan -out="${plan}"
    tofu_guard "${plan}"

    lock "tofu-${STACK}"

    run tofu -chdir="$(tofu_dir)" apply -input=false -lock-timeout="${TOFU_LOCK_TIMEOUT}" "${plan}"

    succ "Stack '${STACK}' converged."

}
## refuse a converge that destroys what holds state — replacing a box or a database is a decision, never a side effect
tofu_guard () {

    local plan="${1:?tofu_guard needs a plan file}" doomed=""

    ensure jq

    doomed="$(tofu -chdir="$(tofu_dir)" show -json "${plan}" \
        | jq -r --arg types " ${TOFU_GUARDED} " '.resource_changes[]? | select(.change.actions | index("delete")) | .type as $type | select($types | contains(" " + $type + " ")) | .address')"

    [[ -n "${doomed}" ]] || { succ "Converge guard clear — nothing that holds state is touched."; return 0; }

    [[ "${TOFU_ALLOW_DESTROY}" != "true" ]] || { warn "Converge destroys what holds state — allowed by TOFU_ALLOW_DESTROY:"$'\n'"${doomed}"; return 0; }

    die "Converge refused — it would destroy what holds state:"$'\n'"${doomed}"$'\n'"Mean it: infra -e TOFU_ALLOW_DESTROY=true tofu ensure"

}
## free the state lock a dead run left behind
tofu_unlock () {

    tofu_stack
    cloud unlock

}
## show what an apply would change
tofu_plan () {

    ensure tofu

    tofu_stack

    tofu_secrets

    run tofu -chdir="$(tofu_dir)" plan -input=false -lock-timeout="${TOFU_LOCK_TIMEOUT}" -var-file="$(tofu_vars)" "$@"

}
## build or update the cloud stack (confirmed)
tofu_apply () {

    ensure tofu

    tofu_stack

    confirm "Apply '${STACK}' stack on ${CLOUD^^}?"

    tofu_secrets
    lock "tofu-${STACK}"

    run tofu -chdir="$(tofu_dir)" apply -input=false -auto-approve -lock-timeout="${TOFU_LOCK_TIMEOUT}" -var-file="$(tofu_vars)" "$@"

    succ "Stack '${STACK}' applied."

}
tofu_unguard () {

    [[ "${DATABASE}" == "managed" ]] || return 0

    cloud db_unguard

}
tofu_owns_cluster () {

    local server="" expected=""

    server="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)" || return 1

    if [[ "${CLUSTER_SOURCE}" == "managed" ]]; then

        expected="$(tofu_output cluster_endpoint)" || return 1

    else

        expected="https://$(tofu_output server_ip):${K3S_API_PORT}" || return 1

    fi

    [[ "${server%/}" == "${expected%/}" ]]

}
tofu_release () {

    local name=""

    [[ -n "${EDGE_TYPE}" ]] || return 0

    has kubectl || return 0

    name="$(k8s_gateway_service)"

    [[ -n "${name}" ]] || return 0

    tofu_owns_cluster || { warn "The current kubeconfig is not the '${STACK}' cluster — leaving its resources alone"; return 0; }

    step "Releasing what kubernetes owns in the cloud before the cloud under it goes"

    run kubectl -n "${ENVOY_NAMESPACE}" delete "${name}" --wait=true --timeout="${PVC_TIMEOUT}" || true

    for name in "${K8S_NAMESPACE}" "${OBSERVABILITY_NAMESPACE}"; do

        run kubectl -n "${name}" delete pvc --all --wait=true --timeout="${PVC_TIMEOUT}" || true

    done

}
## tear the stack down — confirmed twice, releases k8s-owned cloud resources first
tofu_destroy () {

    ensure tofu

    tofu_stack

    confirm "DESTROY the '${STACK}' stack? This is irreversible"
    [[ "$(input 'Type the stack name to confirm' "${INFRA_CONFIRM:-}")" == "${STACK}" ]] \
        || die "Confirmation mismatch — name the stack you mean, on a terminal or with -e INFRA_CONFIRM=${STACK}"

    tofu_secrets
    tofu_release
    tofu_unguard
    lock "tofu-${STACK}"

    run tofu -chdir="$(tofu_dir)" destroy -input=false -auto-approve -var-file="$(tofu_vars)" "$@"

}
## read one stack output, e.g. server_ip or registry — initializes the backend first when this checkout never did
tofu_output () {

    local value=""

    ensure tofu

    [[ -d "$(tofu_dir)/.terraform" ]] || tofu_init >&2 || return 1

    value="$(tofu -chdir="$(tofu_dir)" output -no-color -raw "${1:?Missing output name}" 2>/dev/null)" || return 1

    [[ -n "${value}" && "${value}" != *[![:print:]]* ]] || return 1

    printf '%s' "${value}"

}
## print the scoped storage keys the stack minted, as the manifest lines that carry them (APP_AWS_* for the pods, BACKUP_AWS_* for the backup)
tofu_keys () {

    local app_id="" app_secret="" backup_id="" backup_secret=""

    app_id="$(tofu_output app_access_key_id)"               || die "The stack mints no app key yet — apply it first"
    app_secret="$(tofu_output app_secret_access_key)"       || die "The stack mints no app key yet — apply it first"
    backup_id="$(tofu_output backup_access_key_id)"         || die "The stack mints no backup key yet — apply it first"
    backup_secret="$(tofu_output backup_secret_access_key)" || die "The stack mints no backup key yet — apply it first"

    printf 'APP_AWS_ACCESS_KEY_ID=%s\nAPP_AWS_SECRET_ACCESS_KEY=%s\nBACKUP_AWS_ACCESS_KEY_ID=%s\nBACKUP_AWS_SECRET_ACCESS_KEY=%s\n' "${app_id}" "${app_secret}" "${backup_id}" "${backup_secret}"

}
## format every tofu file in the tree
tofu_fmt () {

    ensure tofu

    run tofu fmt "$@" -recursive "${TEMPLATE_DIR}/tofu"

}
## init -backend=false + validate every stack of every cloud
tofu_validate () {

    local dir="" data=""

    ensure tofu

    tofu_cache

    for dir in "${TEMPLATE_DIR}"/tofu/*/stacks/*/; do

        data="${BUILD_DIR}/tofu/validate/$(basename "${dir}")"

        TF_DATA_DIR="${data}" run tofu -chdir="${dir}" init -backend=false -input=false >/dev/null
        TF_DATA_DIR="${data}" run tofu -chdir="${dir}" validate

    done

    succ "Tofu templates valid."

}
