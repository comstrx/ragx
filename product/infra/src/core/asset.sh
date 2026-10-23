asset-text () {

    local path="${1:-}" file=""

    if declare -F embedded-asset >/dev/null; then
        embedded-asset "${path}"
        return
    fi

    file="$(fs-within "${TOOL_ROOT}" "${path}")" || return

    fs-read "${file}"

}
asset-materialize () {

    local path="${1:-}" temporary=""

    temporary="$(fs-temp-file)" || return
    asset-text "${path}" > "${temporary}" || { rm -f -- "${temporary}"; return 1; }

    out "${temporary}"

}
