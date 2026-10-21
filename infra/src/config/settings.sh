declare -ga CONFIG_SCHEMA=()

config-manifest () {

    local file="" name="" value="" status=0

    file="$(asset-materialize Bash.toml)" || return
    manifest-load "${file}" || status=$?
    rm -f -- "${file}"
    (( status == 0 )) || return "${status}"

    for name in entrypoint source build tests templates; do
        value="${MANIFEST[paths.${name}]:-}"
        fs-relative "${value}" || { err "Bash.toml paths.${name} must be a relative path"; return; }
    done

    [[ "${MANIFEST[paths.cache]:-}" =~ ^\.?[a-z0-9][a-z0-9_.-]{0,62}$ ]] || { err "Bash.toml paths.cache must be one directory name"; return; }
    parse-identifier "${MANIFEST[stack]:-}" || { err "Bash.toml stack must be an identifier"; return; }

    [[ "${TOOL_BUNDLED:-false}" == true ]] || TOOL_BIN="${TOOL_ROOT}/${MANIFEST[paths.entrypoint]}"

}
config-file () {

    local root="${1}" mode="${2}" name=""
    local -a chain=( .env.local .env )

    [[ "${mode}" != production ]] || chain=( .env.production .env.prod .env )

    for name in "${chain[@]}"; do
        [[ ! -f "${root}/${name}" ]] || { out "${root}/${name}"; return 0; }
    done

}
config-load () {

    local root="${CLI_FLAGS[--project]:-${TOOL_ROOT}}" mode=local schema="" file="" pair="" key="" status=0

    root="$(cd -- "${root}" 2>/dev/null && pwd -P)" || { err "Project directory required: ${CLI_FLAGS[--project]:-${TOOL_ROOT}}"; return; }
    [[ "${TOOL_BUILD:-dev}" != release ]] || mode=production

    CONFIG=()
    CONFIG_SOURCE=()
    CONFIG_DEFAULTS=()
    CONFIG_KEYS=()

    schema="$(asset-materialize .env.example)" || return
    cfg-load "${schema}" any defaults || status=$?
    rm -f -- "${schema}"
    (( status == 0 )) || return "${status}"

    CONFIG_SCHEMA=( "${CONFIG_KEYS[@]}" )

    for key in "${CONFIG_SCHEMA[@]}"; do
        CONFIG_DEFAULTS["${key}"]="${CONFIG[${key}]}"
    done

    if (( ${#CLI_CONFIGS[@]} > 0 )); then

        for file in "${CLI_CONFIGS[@]}"; do
            cfg-load "${file}" known file || return
        done

    elif [[ -n "${ENV_FILE:-}" ]]; then

        file="$(fs-temp-file)" || return
        parse-content "${ENV_FILE}" | fs-write "${file}" || return
        cfg-load "${file}" known file || status=$?
        rm -f -- "${file}"
        (( status == 0 )) || return "${status}"

    else

        file="$(config-file "${root}" "${mode}")" || return
        [[ -z "${file}" ]] || cfg-load "${file}" known file || return

    fi

    cfg-environment "${CONFIG_SCHEMA[@]}"

    for pair in "${CLI_OVERRIDES[@]}"; do
        key="${pair%%=*}"
        config-schema-key "${key}" || { err "Unknown setting: ${key}"; return; }
        cfg-set "${key}" "${pair#*=}" cli
    done

    [[ -z "${CLI_FLAGS[--target]:-}" ]] || cfg-set SSH_HOST "${CLI_FLAGS[--target]}" cli

    cfg-set ENV_MODE "${mode}" build
    cfg-set PROJECT_ROOT "${root}" derived

    config-derive

}
config-schema-key () {

    local key=""

    for key in "${CONFIG_SCHEMA[@]}"; do
        [[ "${key}" != "${1:-}" ]] || return 0
    done

    return 1

}
config-derive () {

    local key="" name="" scheme=http port="${CONFIG[HTTP_PORT]}" default=80

    [[ -z "${CONFIG[PROJECT]}" ]] || parse-identifier "${CONFIG[PROJECT]}" || { err "PROJECT must be an identifier"; return; }

    cfg-set STACK "${MANIFEST[stack]}" manifest

    for key in "${!MANIFEST[@]}"; do

        [[ "${key}" == images.* ]] || continue

        name="IMAGE_${key#images.}"
        name="${name^^}"
        name="${name//-/_}"
        ! config-schema-key "${name}" || { err "Bash.toml ${key} collides with the env schema"; return; }
        [[ "${CONFIG_SOURCE[${name}]:-}" != release ]] || continue
        cfg-set "${name}" "${MANIFEST[${key}]}" manifest

    done

    cfg-has DEPLOY_SLOT || cfg-set DEPLOY_SLOT blue state

    cfg-set COMPOSE_PROJECT "${CONFIG[PROJECT]:-unconfigured}"
    cfg-set STATE_ROOT "${CONFIG[PROJECT_ROOT]}/${MANIFEST[paths.cache]}/${CONFIG[COMPOSE_PROJECT]}"
    cfg-set BACKUP_ROOT "${CONFIG[BACKUP_DIR]:-${CONFIG[STATE_ROOT]}/backups}"
    cfg-set BACKUP_SQL_ROOT "${CONFIG[BACKUP_ROOT]}/sql"
    cfg-set BACKUP_WAL_ROOT "${CONFIG[BACKUP_ROOT]}/wal"
    cfg-set WEB_ENABLED false
    [[ -z "${CONFIG[WEB_IMAGES]}" ]] || cfg-set WEB_ENABLED true
    config-github

    if cfg-true TLS_ENABLED; then
        scheme=https
        port="${CONFIG[HTTPS_PORT]}"
        default=443
    fi

    [[ "${port}" != "${default}" ]] || port=""
    cfg-set API_URL "${scheme}://${CONFIG[API_HOST]:-localhost}${port:+:${port}}"
    cfg-set GRAFANA_URL "${scheme}://${CONFIG[GRAFANA_HOST]:-localhost}${port:+:${port}}"

}
config-github () {

    local source="${CONFIG_SOURCE[GITHUB_TOKEN]:-}"

    [[ -n "${CONFIG[GITHUB_TOKEN]:-}" ]] || return 0

    if [[ -z "${CONFIG[REGISTRY_TOKEN]}" && "${CONFIG[REGISTRY_DRIVER]}" == ghcr ]]; then
        cfg-set REGISTRY_TOKEN "${CONFIG[GITHUB_TOKEN]}" "${source}"
        [[ -n "${CONFIG[REGISTRY_USER]}" ]] || cfg-set REGISTRY_USER x-access-token "${source}"
    fi

    if [[ -z "${CONFIG[GITOPS_TOKEN]}" && "${CONFIG[GITOPS_URL]}" == https://github.com/* ]]; then
        cfg-set GITOPS_TOKEN "${CONFIG[GITHUB_TOKEN]}" "${source}"
        [[ -n "${CONFIG[GITOPS_USER]}" ]] || cfg-set GITOPS_USER x-access-token "${source}"
    fi

    return 0

}
