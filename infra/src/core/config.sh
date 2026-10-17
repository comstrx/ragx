#!/usr/bin/env bash

## configuration — one resolution, every source in its rank

infra_code () {

    sed '/^#__INFRA_PAYLOAD__$/,$d' "${INFRA_BIN}"

}
infra_keys () {

    { infra_defaults; infra_manifest; } | sed -nE 's/^([A-Z][A-Z0-9_]*)=.*/\1/p' | sort -u

}
infra_local_keys () {

    infra_defaults | sed -n 's/^LOCAL_KEYS=//p'

}
env_pairs () {

    local line="" key=""

    while IFS= read -r line || [[ -n "${line}" ]]; do

        [[ -n "${line}" && "${line}" != \#* && "${line}" == *=* ]] || continue

        key="${line%%=*}"
        [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue

        printf '%s\n' "${line}"

    done

}
env_apply () {

    local keep="${1:-}" line="" key="" value=""

    while IFS= read -r line; do

        key="${line%%=*}"
        value="${line#*=}"

        [[ -n "${value}" || -n "${keep}" ]] || continue
        [[ -z "${!key:-}" && " ${INFRA_FLAGS:-} " != *" ${key} "* ]] || continue

        export "${key}=${value}"

    done

}
env_load () {

    local file="${1:-}"

    [[ -f "${file}" ]] || die "Config file not found: ${file}"

    env_apply < <(env_pairs < "${file}")

}
env_files_load () {

    local files=() i=0

    [[ -n "${INFRA_CONFIG:-}" ]] || return 0

    mapfile -t files <<< "${INFRA_CONFIG}"

    for (( i = ${#files[@]} - 1; i >= 0; i-- )); do

        [[ -n "${files[i]}" ]] && env_load "${files[i]}"

    done

}
env_json_load () {

    [[ -n "${JSON_ENV:-}" ]] || return 0

    ensure jq

    local pair="" key="" value="" manifest="" local_keys=""

    manifest=" $(infra_keys | paste -sd ' ' -) "
    local_keys=" $(infra_local_keys) "

    while IFS= read -r pair; do

        key="${pair%%=*}"

        [[ "${manifest}" == *" ${key} "* && "${local_keys}" != *" ${key} "* && -z "${!key:-}" ]] || continue

        value="$(base64 -d <<< "${pair#*=}")"
        [[ -n "${value}" ]] || continue

        export "${key}=${value}" INFRA_MANIFEST="${INFRA_MANIFEST:-} ${key}"

    done < <(jq -r 'to_entries[] | "\(.key)=\(.value|@base64)"' <<< "${JSON_ENV}")

    unset JSON_ENV

}
config_preset () {

    case "${STACK}" in

        production ) printf '%s\n' "acme=${ACME_LIVE_URL}" ;;
        *          ) printf '%s\n' "acme=${ACME_STAGING_URL}" ;;

    esac

}
config_encode () {

    local raw="${1-}" out="" hex="" c="" i=0

    for (( i = 0; i < ${#raw}; i++ )); do

        c="${raw:i:1}"

        case "${c}" in
            [A-Za-z0-9._~-] ) out+="${c}" ;;
            * ) printf -v hex '%%%02X' "'${c}"; out+="${hex}" ;;
        esac

    done

    printf '%s' "${out}"

}
config_origin () {

    local host="${1-}"

    if [[ "${SCHEME}:${PUBLIC_PORT}" == "https:443" || "${SCHEME}:${PUBLIC_PORT}" == "http:80" ]]; then

        printf '%s://%s' "${SCHEME}" "${host}"
        return 0

    fi

    printf '%s://%s:%s' "${SCHEME}" "${host}" "${PUBLIC_PORT}"

}
config_memory () {

    local memory="${PG_MEMORY_MB}" work=0 maintenance=0 wal=0

    work=$(( memory * 1024 / 4 / PG_MAX_CONNECTIONS ))
    maintenance=$(( memory / 16 ))
    wal=$(( memory / 2 ))

    (( work >= 4096 )) || work=4096
    (( maintenance >= 64 )) || maintenance=64
    (( maintenance <= 1024 )) || maintenance=1024
    (( wal >= 1024 )) || wal=1024

    export PG_SHARED_BUFFERS="${PG_SHARED_BUFFERS:-$(( memory / 4 ))MB}"
    export PG_EFFECTIVE_CACHE_SIZE="${PG_EFFECTIVE_CACHE_SIZE:-$(( memory * 3 / 4 ))MB}"
    export PG_WORK_MEM="${PG_WORK_MEM:-${work}kB}"
    export PG_MAINTENANCE_WORK_MEM="${PG_MAINTENANCE_WORK_MEM:-${maintenance}MB}"
    export PG_MAX_WAL_SIZE="${PG_MAX_WAL_SIZE:-${wal}MB}"
    export PG_SHM_SIZE="${PG_SHM_SIZE:-$(( memory / 4 ))m}"
    export PG_MEMORY_LIMIT="${PG_MEMORY_LIMIT:-$(( memory * 5 / 4 ))m}"

}
config_derive () {

    local acme="" line="" owner="" hosts="" names="" origins="" profiles="" trusted="" header="X-Forwarded-For" \
          dns01=false wildcard=false workers="${QUEUE_WORKERS}" schedule=true scheme=http port="${HTTP_PORT}"

    while IFS= read -r line; do

        declare "${line}"

    done < <(config_preset)

    export GIT_REPO="${GIT_REPO:-$(printf '%s' "${GIT_REPO_URL%.git}" | sed -E 's#^.*[:/]([^/]+/[^/]+)$#\1#')}"

    owner="${GIT_REPO%%/*}"

    export REGISTRY_USER="${REGISTRY_USER:-${owner}}"
    export IMAGE_NAME="${IMAGE_NAME:-${GIT_REPO,,}}"
    export IMAGE_API="${IMAGE_API:-${REGISTRY}/${IMAGE_NAME}/api}"
    export IMAGE_WEB="${IMAGE_WEB:-${REGISTRY}/${IMAGE_NAME}/web}"
    export ACME_URL="${ACME_URL:-${acme}}"

    [[ -z "$(secret_get CLOUDFLARE_API_TOKEN)" ]] || dns01=true
    [[ "${TLS_ENABLED}" != "true" ]] || { scheme=https; port="${HTTPS_PORT}"; }

    export TLS_DNS01="${TLS_DNS01:-${dns01}}"

    [[ "${TLS_ENABLED}" != "true" || "${TLS_DNS01}" != "true" ]] || wildcard=true

    export TLS_WILDCARD="${TLS_WILDCARD:-${wildcard}}"
    export DNS_MANAGED="${DNS_MANAGED:-${dns01}}"
    export SCHEME="${scheme}"
    export PUBLIC_PORT="${port}"
    export API_HOST="${API_HOST:-${API_SUBDOMAIN}.${BASE_DOMAIN}}"
    export SUPER_HOST="${SUPER_HOST:-${SUPER_SUBDOMAIN}.${BASE_DOMAIN}}"
    export ADMIN_HOST="${ADMIN_HOST:-${ADMIN_SUBDOMAIN}.${BASE_DOMAIN}}"
    export CLIENT_HOST="${CLIENT_HOST:-${BASE_DOMAIN}}"

    hosts="${CLIENT_HOST} www.${CLIENT_HOST}"
    names="${API_HOST}"

    if [[ "${WEB_ENABLED}" == "true" ]]; then

        names+=" ${SUPER_HOST} ${ADMIN_HOST} ${CLIENT_HOST} www.${CLIENT_HOST}"
        origins="\"$(config_origin "${SUPER_HOST}")\",\"$(config_origin "${ADMIN_HOST}")\",\"$(config_origin "${CLIENT_HOST}")\",\"$(config_origin "www.${CLIENT_HOST}")\""
        profiles+="web,"

    fi

    [[ "${TLS_WILDCARD}" != "true" ]] || { hosts+=" *.${BASE_DOMAIN}"; names+=" *.${BASE_DOMAIN}"; }
    (( WORKER_REPLICAS == 0 )) || { profiles+="worker,"; workers=0; }
    [[ "${SCHEDULER_ENABLED}" != "true" ]] || { profiles+="scheduler,"; schedule=false; }
    [[ "${DNS_PROXIED}" != "true" ]] || { trusted="${CLOUDFLARE_CIDRS}"; header="CF-Connecting-IP"; }

    export CLIENT_HOSTS="${CLIENT_HOSTS:-${hosts}}"
    export TLS_NAMES="${TLS_NAMES:-${names}}"
    export TLS_NAME="${TLS_NAME:-${BASE_DOMAIN}}"
    export DNS_NAMES="${DNS_NAMES:-${names}}"
    export API_URL="${API_URL:-$(config_origin "${API_HOST}")}"
    export API_ORIGINS="${API_ORIGINS:-[${origins}]}"
    export COMPOSE_PROFILES="${COMPOSE_PROFILES:-${profiles%,}}"
    export API_QUEUE_WORKERS="${API_QUEUE_WORKERS:-${workers}}"
    export API_SCHEDULE="${API_SCHEDULE:-${schedule}}"
    export COMPOSE_PROJECT="${COMPOSE_PROJECT:-${PROJECT}-${STACK}}"
    export COMPOSE_DIR="${COMPOSE_DIR:-${BUILD_DIR}/compose/${STACK}}"
    export HTTP_BIND="${HTTP_BIND:-${BIND_ADDRESS}:${HTTP_PORT}}"
    export HTTPS_BIND="${HTTPS_BIND:-${BIND_ADDRESS}:${HTTPS_PORT}}"
    export EDGE_TRUSTED_CIDRS="${EDGE_TRUSTED_CIDRS:-${trusted}}"
    export REAL_IP_HEADER="${REAL_IP_HEADER:-${header}}"
    export AMQP_URL="${AMQP_URL:-amqp://$(config_encode "${RABBITMQ_USER}"):$(config_encode "$(secret_get RABBITMQ_PASSWORD)")@rabbitmq:5672/$(config_encode "${RABBITMQ_VHOST}")}"
    export REDIS_URL="${REDIS_URL:-redis://$(config_encode "${REDIS_USER}"):$(config_encode "$(secret_get REDIS_PASSWORD)")@redis:6379/0}"
    export UPLOAD_MAX_BYTES="${UPLOAD_MAX_BYTES:-$(( UPLOAD_MAX_MB * 1024 * 1024 ))}"
    export SERVER_PATH="${SERVER_PATH:-${SERVER_ROOT}/${PROJECT}/infra}"

    config_memory

    export INFRA_DERIVED="GIT_REPO REGISTRY_USER IMAGE_NAME IMAGE_API IMAGE_WEB ACME_URL TLS_DNS01 TLS_WILDCARD DNS_MANAGED SCHEME PUBLIC_PORT API_HOST SUPER_HOST ADMIN_HOST CLIENT_HOST CLIENT_HOSTS TLS_NAMES TLS_NAME DNS_NAMES API_URL API_ORIGINS COMPOSE_PROFILES API_QUEUE_WORKERS API_SCHEDULE COMPOSE_PROJECT COMPOSE_DIR HTTP_BIND HTTPS_BIND EDGE_TRUSTED_CIDRS REAL_IP_HEADER AMQP_URL REDIS_URL UPLOAD_MAX_BYTES SERVER_PATH PG_SHARED_BUFFERS PG_EFFECTIVE_CACHE_SIZE PG_WORK_MEM PG_MAINTENANCE_WORK_MEM PG_MAX_WAL_SIZE PG_SHM_SIZE PG_MEMORY_LIMIT"

}
config_managed_keys () {

    sed -nE 's/^([A-Z][A-Z0-9_]*)=.*/\1/p' "${TEMPLATE_DIR}/compose/api.env"

}
config_render () {

    local dst="${1:?config_render needs a destination}" key="" value="" skip=""

    skip=" ${LOCAL_KEYS} ${SERVER_SKIP_KEYS} "

    ( umask 077 && : > "${dst}" ) || die "Cannot write: ${dst}"
    chmod 600 "${dst}"

    while IFS= read -r key; do

        [[ "${skip}" != *" ${key} "* ]] || continue

        value="${!key:-}"

        [[ -n "${value}" ]] || continue

        printf '%s=%s\n' "${key}" "${value}" >> "${dst}"

    done < <(infra_keys)

}
config_reset () {

    local key=""

    for key in ${INFRA_DERIVED:-}; do

        [[ " ${INFRA_FLAGS:-} ${INFRA_MANIFEST:-} " == *" ${key} "* ]] || unset "${key}"

    done

}
config_ssh_key () {

    local raw="${SSH_PRIVATE_KEY:-}"

    [[ -n "${raw}" ]] || return 0
    [[ -z "${SSH_KEY:-}" || ! -f "${SSH_KEY}" ]] || return 0

    SSH_KEY="$(mktemp)"

    if [[ "${raw}" == -----BEGIN* ]]; then printf '%s\n' "${raw}" > "${SSH_KEY}"; else base64 -d <<< "${raw}" > "${SSH_KEY}" || die "SSH_PRIVATE_KEY is neither a key nor base64"; fi

    export SSH_KEY

}
config_roots () {

    REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
    BUILD_DIR="${BUILD_DIR:-${REPO_ROOT}/.infra}"
    TEMPLATE_DIR="${TEMPLATE_DIR:-$(template_dir)}"

    export REPO_ROOT BUILD_DIR TEMPLATE_DIR

}
config_load () {

    config_roots
    config_reset

    env_json_load
    env_files_load
    env_apply keep < <(infra_defaults | env_pairs)
    env_apply keep < <(infra_manifest | env_pairs)

    config_ssh_key

    export STACK="${STACK:?Missing STACK — the environment this run acts on}"
    export STACKS="${STACKS:?Missing STACKS — the stack names this platform recognizes}"

    [[ " ${STACKS} " == *" ${STACK} "* ]] || die "Unknown stack '${STACK}' — STACKS declares: ${STACKS}"

    config_derive
    template_ensure

}
config_light () {

    config_roots

    env_json_load
    env_files_load
    env_apply keep < <(infra_defaults | env_pairs)

}
