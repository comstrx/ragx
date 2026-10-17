#!/usr/bin/env bash

## secret resolution diagnostics — never prints values

## the keys this stack cannot release without — grown by what the stack reaches and manages
secrets_required () {

    local keys="PROJECT BASE_DOMAIN GIT_REPO_URL GIT_TOKEN SSH_HOST DB_PASSWORD PG_PASSWORD RABBITMQ_PASSWORD REDIS_PASSWORD AUTH_SECRET"

    [[ "${TLS_ENABLED}" != "true" ]] || keys+=" SSL_EMAIL"
    [[ "${TLS_ENABLED}" != "true" || "${TLS_DNS01}" != "true" ]] || keys+=" CLOUDFLARE_API_TOKEN"
    [[ "${DNS_MANAGED}" != "true" ]] || keys+=" CLOUDFLARE_API_TOKEN"
    [[ "${BACKUP_TARGET}" != "s3" ]] || keys+=" S3_BACKUP_BUCKET BACKUP_AWS_ACCESS_KEY_ID BACKUP_AWS_SECRET_ACCESS_KEY"
    [[ "${APP_STORAGE}" != "s3" ]] || keys+=" S3_BUCKET S3_REGION STORAGE_S3_KEY STORAGE_S3_SECRET"

    printf ' %s ' "${keys}"

}
## one way onto the server — a private key in the manifest, a key file, or a password
secrets_reach () {

    [[ -n "$(secret_get SSH_PRIVATE_KEY)" || -n "$(secret_get SSH_PASSWORD)" || -f "${SSH_KEY:-/nonexistent}" ]]

}
## which expected secrets resolve and which are missing — a missing required one refuses the release
secrets_check () {

    local key="" value="" missing=0 broken=0 required=""

    required="$(secrets_required)"

    info "Manifest for '${STACK}' — tls: ${TLS_ENABLED} · dns-01: ${TLS_DNS01} · names: ${DNS_MANAGED} · backups: ${BACKUP_TARGET} · files: ${APP_STORAGE}"

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

    secrets_reach || { err "SSH_PRIVATE_KEY, SSH_KEY or SSH_PASSWORD — one way onto the server is required"; broken=1; }

    (( broken == 0 )) || die "Required secrets are missing — the stack cannot deploy without them."

    secret_clean

    if (( missing == 0 )); then succ "All secrets resolve."; else warn "Optional secrets are missing — their features stay dark until filled."; fi

    secrets_drift

}
## the app env must not contradict the manifest where both speak, and must carry nothing the containers would read as literal text
secrets_drift () {

    local line="" key="" value="" mine="" drift=0 loose=0

    while IFS= read -r line; do

        key="${line%%=*}"
        value="${line#*=}"
        mine="$(secret_get "${key}")"

        [[ -z "${mine}" || "${mine}" == "${value}" ]] || { warn "${key}: ENV_FILE disagrees with the manifest — the manifest wins on the server"; drift=$(( drift + 1 )); }

        [[ ! "${value}" =~ \$\{([A-Za-z_][A-Za-z0-9_]*)\} ]] \
            || { err "${key}: ENV_FILE names \${${BASH_REMATCH[1]}} — the containers expand nothing"; loose=$(( loose + 1 )); }

    done < <(secret_env_pairs)

    (( loose == 0 )) || die "ENV_FILE ships ${loose} placeholder(s) the containers would receive as literal text"

    if (( drift == 0 )); then succ "ENV_FILE and the manifest agree on every shared key."; else warn "${drift} shared key(s) drift between ENV_FILE and the manifest."; fi

}
## the extra app env this manifest carries — key names only, never values
secrets_env () {

    local n=0 key=""

    while IFS= read -r key; do printf '  %s\n' "${key%%=*}"; n=$(( n + 1 )); done < <(secret_env_pairs)

    succ "${n} extra app key(s) ride in ENV_FILE — the platform renders the rest."

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
