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

    local root="${1}" mode="${2}"

    if [[ "${mode}" == production ]]; then

        [[ ! -f "${root}/.env.production" || ! -f "${root}/.env.pod" ]] || { err "Both .env.production and .env.pod exist; keep one or pass --config"; return; }
        [[ ! -f "${root}/.env.production" ]] || { out "${root}/.env.production"; return; }
        [[ ! -f "${root}/.env.pod" ]] || { out "${root}/.env.pod"; return; }

    elif [[ -f "${root}/.env.local" ]]; then

        out "${root}/.env.local"
        return

    fi

    [[ ! -f "${root}/.env" ]] || out "${root}/.env"

}
config-load () {

    local root="${CLI_FLAGS[--project]:-${TOOL_ROOT}}" mode=local schema="" file="" pair="" key="" status=0

    root="$(cd -- "${root}" 2>/dev/null && pwd -P)" || { err "Project directory required: ${CLI_FLAGS[--project]:-${TOOL_ROOT}}"; return; }
    [[ "${TOOL_BUILD:-dev}" != release ]] || mode=production

    CONFIG=()
    CONFIG_SOURCE=()
    CONFIG_KEYS=()

    schema="$(asset-materialize .env.example)" || return
    cfg-load "${schema}" any defaults || status=$?
    rm -f -- "${schema}"
    (( status == 0 )) || return "${status}"

    CONFIG_SCHEMA=( "${CONFIG_KEYS[@]}" )

    if (( ${#CLI_CONFIGS[@]} > 0 )); then

        for file in "${CLI_CONFIGS[@]}"; do
            cfg-load "${file}" known file || return
        done

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

    [[ -z "${CLI_FLAGS[--environment]:-}" ]] || cfg-set DEPLOY_ENV "${CLI_FLAGS[--environment]}" cli
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

    local stack="${MANIFEST[stack]}" key="" name="" scheme=http port="${CONFIG[HTTP_PORT]}" default=80 origins="" host=""
    local -A hosts=()

    [[ "${CONFIG[DEPLOY_ENV]}" == staging || "${CONFIG[DEPLOY_ENV]}" == production ]] || { err "DEPLOY_ENV must be staging or production"; return; }
    [[ -z "${CONFIG[PROJECT]}" ]] || parse-identifier "${CONFIG[PROJECT]}" || { err "PROJECT must be an identifier"; return; }

    cfg-set STACK "${stack}" manifest

    for key in "${!MANIFEST[@]}"; do

        case "${key}" in
            images.*)     name="IMAGE_${key#images.}" ;;
            "${stack}".*) name="${key#"${stack}".}" ;;
            *)            continue ;;
        esac

        name="${name^^}"
        name="${name//-/_}"
        ! config-schema-key "${name}" || { err "Bash.toml ${key} collides with the env schema"; return; }
        [[ "${CONFIG_SOURCE[${name}]:-}" != release ]] || continue
        cfg-set "${name}" "${MANIFEST[${key}]}" manifest

    done

    cfg-has DEPLOY_SLOT || cfg-set DEPLOY_SLOT blue state

    cfg-set COMPOSE_PROJECT "${CONFIG[PROJECT]:-unconfigured}-${CONFIG[DEPLOY_ENV]}"
    cfg-set STATE_ROOT "${CONFIG[PROJECT_ROOT]}/${MANIFEST[paths.cache]}/${CONFIG[COMPOSE_PROJECT]}"
    cfg-set WEB_ENABLED false
    [[ -z "${CONFIG[WEB_IMAGES]}" ]] || cfg-set WEB_ENABLED true

    if cfg-true TLS_ENABLED; then
        scheme=https
        port="${CONFIG[HTTPS_PORT]}"
        default=443
    fi

    [[ "${port}" != "${default}" ]] || port=""
    cfg-set API_URL "${scheme}://${CONFIG[API_HOST]:-localhost}${port:+:${port}}"

    parse-map hosts "${CONFIG[WEB_HOSTS]}" || return

    while IFS= read -r key; do
        [[ -n "${key}" ]] || continue
        host="${hosts[${key}]}"
        origins+="${origins:+,}$(parse-json-string "${scheme}://${host}${port:+:${port}}")"
    done < <(printf '%s\n' "${!hosts[@]}" | LC_ALL=C sort)

    cfg-set APP_ORIGINS "[${origins}]"

}
