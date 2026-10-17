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

        full  ) printf '%s\n' 'cluster=managed' 'provisioner=full'  'database=managed' 'identity=true'  'files=s3'  'edge=nlb' 'registry=' 'rollout=surge' ;;
        light ) printf '%s\n' 'cluster=ssh'     'provisioner=light' 'database=cluster' 'identity=true'  'files=s3'  'edge='    'registry=' 'rollout=swap' ;;
        *     ) printf '%s\n' 'cluster=ssh'     'provisioner='      'database=cluster' 'identity=false' 'files=pvc' 'edge='    "registry=${GHCR_REGISTRY}" 'rollout=surge' ;;

    esac

}
config_derive () {

    local cluster="" provisioner="" database="" identity="" files="" edge="" registry="" rollout="" surge=1 unavailable=0 \
          class="${LOCAL_STORAGE_CLASS}" managed=false local_pg=true section=http backup=s3 pull=false ceiling="${APP_MAX_REPLICAS_SSH}" \
          keys="${BACKUP_SECRET_KEYS}" owner="" repo="${GIT_REPO:-}" hosts="" line=""

    while IFS= read -r line; do

        declare "${line}"

    done < <(config_preset)

    export CLUSTER_SOURCE="${CLUSTER_SOURCE:-${cluster}}"
    export PROVISIONER="${PROVISIONER:-${provisioner}}"
    export DATABASE="${DATABASE:-${database}}"
    export CLOUD_IDENTITY="${CLOUD_IDENTITY:-${identity}}"
    export APP_STORAGE="${APP_STORAGE:-${files}}"
    export EDGE_TYPE="${EDGE_TYPE:-${edge}}"

    [[ "${CLUSTER_SOURCE}" != "managed" ]] || { managed=true; class="${MANAGED_STORAGE_CLASS}"; ceiling="${APP_MAX_REPLICAS_MANAGED}"; }
    [[ "${DATABASE}" != "managed" ]] || local_pg=false
    [[ "${APP_STORAGE}" != "pvc" ]] || backup=pvc
    [[ "${GATEWAY_TLS}" != "true" ]] || section=https
    [[ "${CLOUD_IDENTITY}" == "true" ]] || keys+=" BACKUP_AWS_ACCESS_KEY_ID BACKUP_AWS_SECRET_ACCESS_KEY"
    [[ "${rollout}" != "swap" ]] || { surge=0; unavailable=1; }

    owner="${repo%%/*}"

    export REGISTRY="${REGISTRY:-${registry}}"
    export REGISTRY_USER="${REGISTRY_USER:-${REGISTRY:+${owner}}}"

    [[ -z "${REGISTRY_USER}" ]] || pull=true
    [[ -n "${REGISTRY}" || "${CLOUD_IDENTITY}" != "true" || "${managed}" == "true" ]] || pull=true

    export CLUSTER_NAME="${CLUSTER_NAME:-${PROJECT}}"
    export K8S_NAMESPACE="${K8S_NAMESPACE:-${PROJECT}}"
    export IMAGE_NAME="${IMAGE_NAME:-${PROJECT}/${SERVICE_NAME}}"
    export DB_USER="${DB_USER:-${PROJECT}}"
    export TF_STATE_BUCKET="${TF_STATE_BUCKET:-${PROJECT}-tf-state}"
    export S3_BUCKET="${S3_BUCKET:-${PROJECT}-storage}"
    export S3_BACKUP_BUCKET="${S3_BACKUP_BUCKET:-${PROJECT}-backups}"
    export GATEWAY_DOMAIN="${GATEWAY_DOMAIN:-${BASE_DOMAIN}}"
    export GIT_REPO="${GIT_REPO:-$(printf '%s' "${GIT_REPO_URL%.git}" | sed -E 's#^.*[:/]([^/]+/[^/]+)$#\1#')}"

    hosts="\"${BASE_DOMAIN}\",\"*.${BASE_DOMAIN}\",\"*.${TENANT_SUBDOMAIN}.${BASE_DOMAIN}\""

    case "${GATEWAY_DOMAIN}" in

        "${BASE_DOMAIN}" | *".${BASE_DOMAIN}" ) ;;
        * ) hosts="\"${GATEWAY_DOMAIN}\",${hosts}" ;;

    esac

    export APP_HOSTNAMES="${APP_HOSTNAMES:-[${hosts}]}"
    export GATEWAY_SECTION="${GATEWAY_SECTION:-${section}}"
    export GRAFANA_HOSTNAME="${GRAFANA_HOSTNAME:-${GRAFANA_SUBDOMAIN}.${BASE_DOMAIN}}"
    export QUEUE_KEYS="${QUEUE_KEYS:-${PROJECT}${QUEUE_KEYS_SUFFIX}}"
    export VOLUME_CLASS="${VOLUME_CLASS:-${class}}"
    export PLATFORM_STORAGE_CLASS="${PLATFORM_STORAGE_CLASS:-${VOLUME_CLASS}}"
    export PLATFORM_PG_ENABLED="${PLATFORM_PG_ENABLED:-${local_pg}}"
    export APP_MAX_REPLICAS="${APP_MAX_REPLICAS:-${ceiling}}"
    export ROLLOUT_SURGE="${ROLLOUT_SURGE:-${surge}}"
    export ROLLOUT_UNAVAILABLE="${ROLLOUT_UNAVAILABLE:-${unavailable}}"
    export AUTOSCALER_ENABLED="${AUTOSCALER_ENABLED:-${managed}}"
    export METRICS_SERVER_ENABLED="${METRICS_SERVER_ENABLED:-${managed}}"
    export CLOUD_METRICS="${CLOUD_METRICS:-${CLOUD_IDENTITY}}"
    export BACKUP_SECRET_KEYS="${keys}"
    export BACKUP_TARGET="${BACKUP_TARGET:-${backup}}"
    export REGISTRY_PULL="${REGISTRY_PULL:-${pull}}"
    export KUBECONFIG="${KUBECONFIG:-$(path_expand "${KUBE_DIR}")/${PROJECT}.yaml}"
    export SERVER_PATH="${SERVER_PATH:-${SERVER_ROOT}/${PROJECT}/infra}"
    export INFRA_REPO_URL="${INFRA_REPO_URL:-https://github.com/${INFRA_REPO}.git}"
    export INFRA_TAG="${INFRA_TAG:-v${INFRA_VERSION}}"
    export INFRA_DERIVED="CLUSTER_SOURCE PROVISIONER DATABASE CLOUD_IDENTITY APP_STORAGE EDGE_TYPE REGISTRY REGISTRY_USER REGISTRY_PULL GATEWAY_DOMAIN GIT_REPO APP_HOSTNAMES GATEWAY_SECTION GRAFANA_HOSTNAME QUEUE_KEYS VOLUME_CLASS PLATFORM_STORAGE_CLASS PLATFORM_PG_ENABLED APP_MAX_REPLICAS ROLLOUT_SURGE ROLLOUT_UNAVAILABLE AUTOSCALER_ENABLED METRICS_SERVER_ENABLED CLOUD_METRICS BACKUP_SECRET_KEYS BACKUP_TARGET KUBECONFIG SERVER_PATH INFRA_REPO_URL INFRA_TAG"

}
config_managed_keys () {

    grep -oE '^  [A-Z][A-Z0-9_]+:' "${TEMPLATE_DIR}/helm/values/${SERVICE_NAME}.tpl" | tr -d ' :' | paste -sd ' ' -

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
cloud () {

    local fn="${CLOUD:?Missing CLOUD — the provider this platform provisions on}_${1:?cloud needs a verb}"

    shift

    declare -F "${fn}" >/dev/null || die "Cloud '${CLOUD}' does not implement '${fn}' — teach module/${CLOUD}.sh"

    "${fn}" "$@"

}
config_load () {

    config_roots
    config_reset

    env_json_load
    env_files_load
    env_apply keep < <(infra_defaults | env_pairs)

    config_ssh_key

    export STACK="${STACK:?Missing STACK — the environment this run acts on}"
    export STACKS="${STACKS:?Missing STACKS — the stack names this platform recognizes}"

    [[ " ${STACKS} " == *" ${STACK} "* ]] || die "Unknown stack '${STACK}' — STACKS declares: ${STACKS}"

    [[ -n "${AWS_PROFILE:-}" ]] || unset AWS_PROFILE
    [[ -z "${AWS_ACCESS_KEY_ID:-}" ]] || unset AWS_PROFILE

    config_derive
    template_ensure

}
config_light () {

    config_roots

    env_json_load
    env_files_load
    env_apply keep < <(infra_defaults | env_pairs)

}
