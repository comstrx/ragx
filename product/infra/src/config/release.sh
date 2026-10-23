config-release-names () {

    local server="${2:-}" key="" name="" service="" prefix=""
    local -a parts=() prefixes=()

    read -r -a parts <<< "${1-}"

    while IFS= read -r service; do
        out "IMAGE_${service^^}"
        prefix="$(config-data "${service}" prefix)" || return
        prefixes+=( "${prefix}_" )
    done < <(config-data-services)

    for key in "${CONFIG_SCHEMA[@]}"; do
        case "${key}" in
            PROJECT|RELEASE|MIGRATION_POLICY|TLS_ENABLED|HTTP_PORT|HTTPS_PORT|APP_MEMORY|DATA_MEMORY|CPUS) out "${key}"; continue ;;
        esac
        for prefix in "${prefixes[@]}"; do
            [[ "${key}" != "${prefix}"* ]] || { out "${key}"; break; }
        done
    done

    out PARTS

    for name in "${parts[@]}"; do
        for key in "${CONFIG_PART_PINNED[@]}"; do
            out "${name^^}_${key}"
        done
    done

    if [[ -n "${server}" ]]; then
        for key in "${CONFIG_SERVER_KEYS[@]}"; do
            out "${server^^}_${key}"
        done
    fi

}
config-release-keys () {

    local name="" server=""
    local -a parts=()

    read -r -a parts <<< "${CONFIG[PARTS]}"

    for name in "${parts[@]}"; do
        [[ "${CONFIG[${name^^}_KIND]:-}" != server ]] || server="${name}"
    done

    config-release-names "${CONFIG[PARTS]}" "${server}" | LC_ALL=C sort -u

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

    local source="${1}" key="" name="" server=""
    local -A values=() expected=()
    local -a parts=()

    parse-pairs values "${source}" || return
    [[ "${values[PROJECT]:-}" == "${CONFIG[PROJECT]}" ]] || { err "Release snapshot belongs to another project: ${source}"; return; }
    [[ -n "${values[PARTS]+x}" ]] || { err "Release snapshot lacks PARTS: ${source}"; return; }
    read -r -a parts <<< "${values[PARTS]}"

    for name in "${parts[@]}"; do
        [[ "${name}" =~ ^[a-z][a-z0-9]*$ ]] || { err "Release snapshot names an invalid part: ${name}"; return; }
        [[ "${values[${name^^}_KIND]:-}" != server ]] || server="${name}"
    done

    while IFS= read -r key; do
        expected["${key}"]=1
    done < <(config-release-names "${values[PARTS]}" "${server}")

    for key in "${!values[@]}"; do
        [[ -n "${expected[${key}]:-}" ]] || { err "Unexpected key in release snapshot: ${key}"; return; }
    done

    for key in "${!expected[@]}"; do
        [[ -n "${values[${key}]+x}" ]] || { err "Release snapshot lacks ${key}: ${source}"; return; }
    done

    for name in "${CONFIG_PARTS[@]}"; do
        [[ " ${parts[*]} " == *" ${name} "* ]] || cfg-set "${name^^}_IMAGE" "" release
    done

    for key in "${!values[@]}"; do
        cfg-set "${key}" "${values[${key}]}" release
    done

    config-derive

}
