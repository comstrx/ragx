#!/usr/bin/env bash

## secret resolution diagnostics — never prints values

## the keys this stack cannot release without — grown by what the stack provisions, reaches and manages
secrets_required () {

    local keys="PROJECT BASE_DOMAIN GIT_REPO_URL GIT_TOKEN DB_PASSWORD REDIS_PASSWORD AUTH_SECRET ENV_FILE"

    if [[ -n "${PROVISIONER}" ]]; then keys+=" AWS_REGION AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY ECR_REGISTRY"; else keys+=" SSH_HOST"; fi

    ! secret_split || keys+=" DB_APP_PASSWORD"

    [[ "${CLUSTER_SOURCE}" != "ssh" ]] || keys+=" SSH_PRIVATE_KEY"
    [[ "${CLUSTER_SOURCE}" != "ssh" || -z "${PROVISIONER}" ]] || keys+=" SSH_PUBLIC_KEY"
    [[ "${CLOUD_IDENTITY}" == "true" || "${BACKUP_TARGET}" != "s3" ]] || keys+=" BACKUP_AWS_ACCESS_KEY_ID BACKUP_AWS_SECRET_ACCESS_KEY"
    [[ "${GATEWAY_TLS}" != "true" || "${GATEWAY_DNS01}" != "true" ]] || keys+=" CLOUDFLARE_API_TOKEN"
    [[ -z "${DNS_MANAGED}" ]] || keys+=" CLOUDFLARE_API_TOKEN"

    printf ' %s ' "${keys}"

}
## which expected secrets resolve and which are missing — a missing required one refuses the release
secrets_check () {

    local key="" value="" missing=0 broken=0 required=""

    required="$(secrets_required)"

    info "Manifest for '${STACK}' — provisioner: ${PROVISIONER:-none} · cluster: ${CLUSTER_SOURCE}"

    while IFS= read -r key; do

        [[ -n "${key}" ]] || continue

        value="$(secret_get "${key}")"

        if [[ -n "${value}" ]]; then

            succ "${key}"

        elif [[ "${required}" == *" ${key} "* ]]; then

            err "${key} — REQUIRED, missing"
            broken=1

        else

            warn "${key} — missing"
            missing=1

        fi

    done < <({ tr ' ' '\n' <<< "${required}"; secret_keys; } | sort -u)

    (( broken == 0 )) || die "Required secrets are missing — the cluster cannot deploy without them."

    if (( missing == 0 )); then succ "All secrets resolve."; else warn "Optional secrets are missing — their features stay dark until filled."; fi

    secrets_drift

}
## the app env must carry the app's own secrets, and must not contradict the manifest where both speak
secrets_drift () {

    local line="" key="" value="" mine="" drift=0 appkey=0 loose=0

    while IFS= read -r line; do

        key="${line%%=*}"
        value="${line#*=}"
        [[ "${key}" != "APP_KEY" ]] || appkey=1
        mine="$(secret_get "${key}")"
        [[ -z "${mine}" || "${mine}" == "${value}" ]] || { warn "${key}: ENV_FILE disagrees with the manifest — the manifest wins on the cluster"; drift=$(( drift + 1 )); }

        [[ ! "${value}" =~ \$\{([A-Za-z_][A-Za-z0-9_]*)\} ]] \
            || { err "${key}: ENV_FILE names \${${BASH_REMATCH[1]}} — this becomes a kubernetes secret, and kubernetes expands nothing"; loose=$(( loose + 1 )); }

    done < <(secret_env_pairs)

    (( loose == 0 )) || die "ENV_FILE ships ${loose} placeholder(s) the pods would receive as literal text"
    (( appkey == 1 )) || die "ENV_FILE carries no APP_KEY — the service cannot boot"
    if (( drift == 0 )); then succ "ENV_FILE and the manifest agree on every shared key."; else warn "${drift} shared key(s) drift between ENV_FILE and the manifest."; fi

}
## the app env this manifest carries — key names only, never values
secrets_env () {

    local n=0 key=""

    while IFS= read -r key; do printf '  %s\n' "${key%%=*}"; n=$(( n + 1 )); done < <(secret_env_pairs)

    (( n > 0 )) || die "ENV_FILE is empty — the service has no environment to run on"
    succ "${n} app keys ride in ENV_FILE."

}
## law: the two examples are disjoint, and every key they name is read by the platform
secrets_example () {

    local key="" code="" shared="" unread=""

    code="$(infra_code)"
    shared="$(comm -12 <(infra_defaults | sed -nE 's/^([A-Z][A-Z0-9_]*)=.*/\1/p' | sort) <(secret_keys | sort) | paste -sd ' ' -)"

    [[ -z "${shared}" ]] || die "A key lives in both examples — pick one home: ${shared}"

    while IFS= read -r key; do

        grep -qE "\b${key}\b" <<< "${code}" || grep -rqE "\b${key}\b" "${TEMPLATE_DIR}" || unread+=" ${key}"

    done < <(infra_keys)

    [[ -z "${unread}" ]] || die "The examples name keys nobody reads:${unread}"

    succ "Examples are disjoint and every key they name is read by the platform."

}
## the full list of keys this platform expects from outside
secrets_keys () {

    secret_keys

}
