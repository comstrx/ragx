config-release-key () {

    case "${1:-}" in
        PROJECT|RELEASE|MIGRATION_POLICY|API_IMAGE|WEB_IMAGES|API_HOST|WEB_HOSTS)            return 0 ;;
        API_READY_PATH|WEB_READY_PATH|TLS_ENABLED|HTTP_PORT|HTTPS_PORT|API_PORT|WEB_PORT)    return 0 ;;
        IMAGE_POSTGRES|IMAGE_RABBITMQ|IMAGE_REDIS|APP_MEMORY|DATA_MEMORY|CPUS)               return 0 ;;
        API_ENV_SHA256|API_ENV_MOUNT|API_STORAGE_MOUNT|API_RELEASE_VARIABLE|API_FORCED_ENV)  return 0 ;;
        API_*_COMMAND|API_SERVE_ENV|API_WORK_ENV|API_SCHEDULE_ENV)                           return 0 ;;
        WEB_ENV_SHA256|WEB_ENV_MOUNT|WEB_FORCED_ENV|DB_*|RABBIT_*|REDIS_*)                   return 0 ;;
    esac

    return 1

}
config-release-keys () {

    local key=""

    for key in "${CONFIG_SCHEMA[@]}" IMAGE_POSTGRES IMAGE_RABBITMQ IMAGE_REDIS API_ENV_SHA256 WEB_ENV_SHA256; do
        config-release-key "${key}" || continue
        out "${key}"
    done | LC_ALL=C sort -u

}
config-release-save () {

    local destination="${1}" key=""
    local -a keys=()

    while IFS= read -r key; do
        keys+=( "${key}" )
    done < <(config-release-keys)

    template-env "${destination}" "${keys[@]}"

}
config-release-load () {

    local source="${1}" key=""
    local -A values=() expected=()

    while IFS= read -r key; do
        expected["${key}"]=1
    done < <(config-release-keys)

    parse-pairs values "${source}" || return
    [[ "${values[PROJECT]:-}" == "${CONFIG[PROJECT]}" ]] || { err "Release snapshot belongs to another project: ${source}"; return; }

    for key in "${!values[@]}"; do
        [[ -n "${expected[${key}]:-}" ]] || { err "Unexpected key in release snapshot: ${key}"; return; }
    done

    for key in "${!expected[@]}"; do
        [[ -n "${values[${key}]+x}" ]] || { err "Release snapshot lacks ${key}: ${source}"; return; }
    done

    for key in "${!values[@]}"; do
        cfg-set "${key}" "${values[${key}]}" release
    done

    config-derive

}
