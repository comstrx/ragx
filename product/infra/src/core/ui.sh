ui-section () {

    if ui-color; then printf '\n\033[1m%s\033[0m\n' "${1-}"
    else printf '\n%s\n' "${1-}"
    fi

}
ui-row () {

    local width="${UI_WIDTH:-42}" pad=0

    if [[ -z "${2-}" ]]; then
        printf '  %s\n' "${1-}"
    elif ui-color; then
        (( pad = width - ${#1}, pad > 0 )) || pad=0
        printf '  \033[36m%s\033[0m%*s  %s\n' "${1}" "${pad}" '' "${2}"
    else
        printf '  %-*s  %s\n' "${width}" "${1-}" "${2}"
    fi

}
ui-color () {

    [[ -z "${NO_COLOR:-}" ]] || return 1
    [[ -z "${FORCE_COLOR:-}" ]] || return 0

    [[ -t 1 && "${TERM:-dumb}" != dumb ]]

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
