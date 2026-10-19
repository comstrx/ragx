ui-section () {

    printf '\n%s\n' "${1-}"

}
ui-row () {

    if [[ -n "${2-}" ]]; then printf '  %-42s %s\n' "${1-}" "${2}"
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
