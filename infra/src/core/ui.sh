ui-section () {

    if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then printf '\n\033[1m%s\033[0m\n' "${1-}"
    else printf '\n%s\n' "${1-}"
    fi

}
ui-row () {

    if [[ -n "${2-}" ]]; then printf '  %-*s  %s\n' "${UI_WIDTH:-42}" "${1-}" "${2}"
    else printf '  %s\n' "${1-}"
    fi

}
ui-table () {

    local title="${1}" row="" name="" usage="" summary=""

    shift
    ui-section "${title}"

    for row in "$@"; do
        IFS='|' read -r name usage summary <<< "${row}"
        ui-row "${usage:-${name}}" "${summary}"
    done

}
ui-result () {

    local action="${1}" changed="${2}" retry="${3}"

    succ "${action}: changed=${changed} retry=${retry}"

}
