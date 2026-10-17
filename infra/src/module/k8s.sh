#!/usr/bin/env bash

## cluster plumbing — secrets, pull access, the gitops handover

k8s_upsert () {

    "$@" --dry-run=client -o yaml | kubectl apply -f -

}

## print or fetch the kubeconfig for this stack
k8s_kubeconfig () {

    if [[ "${CLUSTER_SOURCE}" == "managed" ]]; then

        ensure aws kubectl

        run aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${AWS_REGION}"

        return 0

    fi

    server_kubeconfig

}
k8s_namespace () {

    ensure kubectl

    k8s_upsert kubectl create namespace "${1:-${K8S_NAMESPACE}}"

}
## apply the app / platform / backup secrets into the namespace
k8s_secrets () {

    local file="" owner="" scoped="" backup="" scratch="" token="" before="" checksum="" deploy=""

    ensure kubectl

    secret_require DB_PASSWORD >/dev/null
    secret_require REDIS_PASSWORD >/dev/null
    ! secret_split || secret_require DB_APP_PASSWORD >/dev/null

    k8s_namespace "${K8S_NAMESPACE}"
    k8s_platform_passwords

    file="$(tmp_file)"
    owner="$(tmp_file)"
    scoped="$(tmp_file)"
    backup="$(tmp_file)"
    scratch="$(tmp_file)"

    chmod 600 "${scoped}" "${backup}" "${scratch}"

    secret_env_file "${file}"
    secret_env_file "${owner}" owner
    printf 'DB_PASSWORD=%s\nREDIS_PASSWORD=%s\n' "$(secret_require DB_PASSWORD)" "$(secret_require REDIS_PASSWORD)" | grep -E "^(${PLATFORM_SECRET_KEYS// /|})=" > "${scoped}" || true
    grep -E "^(${BACKUP_SECRET_KEYS// /|})=" "${owner}" > "${backup}" || true
    [[ -z "$(secret_get BACKUP_AWS_ACCESS_KEY_ID)" ]] || printf 'BACKUP_AWS_ACCESS_KEY_ID=%s\nBACKUP_AWS_SECRET_ACCESS_KEY=%s\n' "$(secret_get BACKUP_AWS_ACCESS_KEY_ID)" "$(secret_require BACKUP_AWS_SECRET_ACCESS_KEY)" >> "${backup}"

    before="$(kubectl -n "${K8S_NAMESPACE}" get secret "${SERVICE_NAME}-secrets" -o jsonpath='{.metadata.annotations.infra/checksum}' 2>/dev/null || true)"
    checksum="$(sha256sum "${file}" | cut -d' ' -f1)"

    k8s_upsert kubectl create secret generic "${SERVICE_NAME}-secrets" \
        --from-env-file="${file}" \
        -n "${K8S_NAMESPACE}"
    run kubectl -n "${K8S_NAMESPACE}" annotate secret "${SERVICE_NAME}-secrets" "infra/checksum=${checksum}" --overwrite >/dev/null

    if [[ -n "${before}" && "${before}" != "${checksum}" ]]; then

        for deploy in $(kubectl -n "${K8S_NAMESPACE}" get deploy -o name 2>/dev/null | grep "^deployment.apps/${SERVICE_NAME}-" || true); do

            run kubectl -n "${K8S_NAMESPACE}" rollout restart "${deploy}"

        done

    fi

    k8s_upsert kubectl create secret generic "${SERVICE_NAME}-owner-secrets" \
        --from-env-file="${owner}" \
        -n "${K8S_NAMESPACE}"

    k8s_upsert kubectl create secret generic "platform-secrets" \
        --from-env-file="${scoped}" \
        -n "${K8S_NAMESPACE}"

    k8s_upsert kubectl create secret generic "${SERVICE_NAME}-backup-secrets" \
        --from-env-file="${backup}" \
        -n "${K8S_NAMESPACE}"

    token="$(secret_get CLOUDFLARE_API_TOKEN)"

    if [[ -n "${token}" ]]; then

        k8s_namespace "${CERT_MANAGER_NAMESPACE}"

        printf '%s' "${token}" > "${scratch}"

        k8s_upsert kubectl create secret generic cloudflare-token \
            --from-file=token="${scratch}" \
            -n "${CERT_MANAGER_NAMESPACE}"

    fi

    k8s_watcher_secrets "${scratch}"

    rm -f "${file}" "${owner}" "${scoped}" "${backup}" "${scratch}"

    succ "Secrets applied into '${K8S_NAMESPACE}' (app / owner / platform / backup split)."

}
## apply the guard watcher secrets
k8s_watcher_secrets () {

    local scratch="${1:?Missing scratch file}" password="" token=""

    [[ "${OBSERVABILITY_ENABLED}" == "true" ]] || return 0

    password="$(secret_get GRAFANA_PASSWORD)"
    token="$(secret_get ALERT_BOT_TOKEN)"

    [[ -n "${password}" || -n "${ALERT_CHAT_ID}" ]] || return 0

    k8s_namespace "${OBSERVABILITY_NAMESPACE}"

    if [[ -n "${password}" ]]; then

        k8s_upsert kubectl create secret generic grafana-admin \
            --from-literal=username=admin \
            --from-literal=password="${password}" \
            -n "${OBSERVABILITY_NAMESPACE}"

    fi

    if [[ -n "${ALERT_CHAT_ID}" ]]; then

        [[ -n "${token}" ]] || warn "ALERT_BOT_TOKEN is empty — alertmanager will start, but nothing will reach the chat"

        printf '%s' "${token}" > "${scratch}"

        k8s_upsert kubectl create secret generic alert-sink \
            --from-file=token="${scratch}" \
            -n "${OBSERVABILITY_NAMESPACE}"

    fi

}
## one ALTER ROLE statement, the password quoted for SQL
k8s_role_password () {

    local role="${1:?k8s_role_password needs a role}" password="${2:?k8s_role_password needs a password}"

    printf "ALTER ROLE \"%s\" WITH PASSWORD '%s';\n" "${role}" "${password//\'/\'\'}"

}
## move the database roles onto the manifest passwords before any secret carries them — sessions keep running, new logins take the new secret, postgres never restarts for it
k8s_platform_passwords () {

    local sql=""

    [[ "${PLATFORM_PG_ENABLED}" == "true" ]] || return 0
    kubectl -n "${K8S_NAMESPACE}" get statefulset postgresql >/dev/null 2>&1 || return 0

    sql="$(k8s_role_password "${DB_USER}" "$(secret_require DB_PASSWORD)")"

    if secret_split; then

        sql+="$(printf "DO \$\$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN %s END IF; END \$\$;\n" \
            "${DB_APP_USER}" "$(k8s_role_password "${DB_APP_USER}" "$(secret_require DB_APP_PASSWORD)")")"

    fi

    printf '%s\n' "${sql}" | kubectl -n "${K8S_NAMESPACE}" exec -i statefulset/postgresql -- psql -U "${DB_USER}" -d "${DB_NAME}" -q -v ON_ERROR_STOP=1 \
        || die "Cannot move the database roles onto the new passwords — the app would restart onto one the server never took"

}
## restart the platform units that only read their secret at start
k8s_platform_rotate () {

    [[ "${PLATFORM_REDIS_ENABLED}" == "true" ]] || return 0

    run kubectl -n "${K8S_NAMESPACE}" rollout restart statefulset redis
    run kubectl -n "${K8S_NAMESPACE}" rollout status statefulset/redis --timeout="${ROLLOUT_TIMEOUT}"

}
## rotate secrets: the roles take the passwords inside the secrets step, then every workload restarts onto them
k8s_rotate () {

    ensure kubectl

    k8s_secrets
    k8s_platform_rotate

    run kubectl -n "${K8S_NAMESPACE}" rollout restart deployment -l "app.kubernetes.io/name=${SERVICE_NAME}"

    succ "Secrets rotated — the roles took the passwords first, then every workload restarted onto them."

}
## apply the registry pull secret
k8s_pull_secret () {

    local password=""

    ensure kubectl

    ci_image >/dev/null

    k8s_namespace "${K8S_NAMESPACE}"

    if [[ -n "${REGISTRY_USER}" ]]; then

        password="$(secret_require GIT_TOKEN)"

    else

        password="$(cloud registry_token)" || die "Cannot fetch a registry token"

    fi

    [[ -n "${password}" && "${password}" != *[[:space:]]* ]] || die "The registry token is not a token — something wrote on stdout while minting it"

    k8s_upsert kubectl create secret docker-registry pull-secret \
        --docker-server="$(ci_registry)" \
        --docker-username="${REGISTRY_USER:-$(cloud registry_user)}" \
        --docker-password="${password}" \
        -n "${K8S_NAMESPACE}"

    succ "Pull secret applied — set 'imagePullSecrets: [pull-secret]' in the service values."

}
## ONE verb, all stacks: secrets → pull access → argocd owns the cluster from git
k8s_bootstrap () {

    k8s_secrets

    if [[ "${REGISTRY_PULL}" == "true" ]]; then

        k8s_pull_secret

        [[ -n "${REGISTRY_USER}" ]] || k8s_registry_refresher

    fi

    argocd_install
    argocd_repo
    argocd_bootstrap

    [[ -z "$(secret_get ARGOCD_PASSWORD)" ]] || argocd_rotate

    if dns_managed; then

        dns_sync || warn "DNS was not pointed at this stack — run 'infra dns sync' when its edge has an address"

    fi

    succ "Cluster → GitOps platform — ArgoCD owns it from git."

}
## schedule the provider token refresher (cloud-dispatched)
k8s_registry_refresher () {

    cloud registry_refresher

}
## pods, services and routes at a glance
k8s_status () {

    ensure kubectl

    run kubectl get pods,svc,httproute -n "${K8S_NAMESPACE}"

}
## every pod that is not ready, the reason it is not, and the last words it said
k8s_unhealthy () {

    local pod="" died=""

    ensure kubectl jq

    while IFS= read -r pod; do

        warn "${pod} is not ready"

        kubectl -n "${K8S_NAMESPACE}" get "${pod}" -o jsonpath='{range .status.containerStatuses[*]}  {.name}: restarts={.restartCount} now={.state.waiting.reason}{.state.terminated.reason}{.state.running.startedAt} last={.lastState.terminated.reason}/{.lastState.terminated.exitCode}{"\n"}{end}' >&2 2>/dev/null || true

        died="$(kubectl -n "${K8S_NAMESPACE}" get "${pod}" -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}' 2>/dev/null)"

        [[ -n "${died}" ]] || continue

        kubectl -n "${K8S_NAMESPACE}" logs "${pod}" --all-containers --tail="${POD_LOG_LINES}" --previous >&2 2>/dev/null || true

    done < <(kubectl -n "${K8S_NAMESPACE}" get pods -o json 2>/dev/null \
        | jq -r '.items[] | select(.status.phase != "Succeeded") | select(.status.phase == "Pending" or ([.status.containerStatuses[]? | .ready] | all | not)) | "pod/" + .metadata.name')

    return 0

}
## tail logs of one component
k8s_logs () {

    ensure kubectl

    run kubectl logs -n "${K8S_NAMESPACE}" -l "app.kubernetes.io/component=${1:-web}" --tail="${2:-100}" -f

}
k8s_gateway_selector () {

    printf 'gateway.envoyproxy.io/owning-gateway-name=gateway'

}
k8s_gateway_service () {

    kubectl -n "${ENVOY_NAMESPACE}" get svc -l "$(k8s_gateway_selector)" -o name 2>/dev/null | head -1 || true

}
k8s_gateway_address () {

    local field=""

    case "${1:?Missing field: hostname|ip|clusterIP}" in
        hostname  ) field='{.items[0].status.loadBalancer.ingress[0].hostname}' ;;
        ip        ) field='{.items[0].status.loadBalancer.ingress[0].ip}' ;;
        clusterIP ) field='{.items[0].spec.clusterIP}' ;;
        *         ) die "Unknown gateway address field: ${1}" ;;
    esac

    kubectl -n "${ENVOY_NAMESPACE}" get svc -l "$(k8s_gateway_selector)" -o jsonpath="${field}" 2>/dev/null

}
