declare -gA SOURCE_STATE=()

source-include () {

    local path="${1:-}" status=0

    [[ "${path}" =~ ^[a-z0-9_-]+(/[a-z0-9_-]+)*\.sh$ ]] || { err "Invalid source path: ${path}"; return; }

    case "${SOURCE_STATE[${path}]:-}" in
        loaded)  return 0 ;;
        loading) err "Source cycle: ${path}"; return ;;
    esac

    SOURCE_STATE["${path}"]=loading

    if declare -F embedded-source >/dev/null; then
        embedded-source "${path}" || status=$?
    elif [[ -f "${TOOL_SOURCE}/${path}" && ! -L "${TOOL_SOURCE}/${path}" ]]; then
        source "${TOOL_SOURCE}/${path}" || status=$?
    else
        err "Missing source: ${path}" || status=$?
    fi

    if (( status == 0 )); then SOURCE_STATE["${path}"]=loaded
    else unset 'SOURCE_STATE[$path]'
    fi

    return "${status}"

}
source-list () {

    local directory="${1:-}" file="" LC_ALL=C

    [[ "${directory}" =~ ^[a-z0-9_-]+(/[a-z0-9_-]+)*$ ]] || { err "Invalid source directory: ${directory}"; return; }

    if declare -F embedded-sources >/dev/null; then

        while IFS= read -r file; do
            [[ "${file}" == "${directory}/"* && "${file#"${directory}/"}" != */* ]] && out "${file}"
        done < <(embedded-sources)

        return 0

    fi

    for file in "${TOOL_SOURCE}/${directory}"/*.sh; do
        [[ -f "${file}" && ! -L "${file}" ]] && out "${file#"${TOOL_SOURCE}/"}"
    done

    return 0

}
