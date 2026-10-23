template-text () {

    local source="${1}" text="" token="" key="" filter="" value=""

    text="$(asset-text "${source}")" || return

    while [[ "${text}" =~ \{\{([A-Z][A-Z0-9_]*)(\|json)?\}\} ]]; do

        token="${BASH_REMATCH[0]}"
        key="${BASH_REMATCH[1]}"
        filter="${BASH_REMATCH[2]}"

        cfg-has "${key}" || { err "Template ${source} requires ${key}"; return; }

        value="${CONFIG[${key}]}"
        [[ "${value}" != *'{{'* ]] || { err "Nested placeholder in ${key}"; return; }
        [[ -z "${filter}" ]] || value="$(parse-json-string "${value}")"

        text="${text//"${token}"/"${value}"}"

    done

    [[ "${text}" != *'{{'* ]] || { err "Invalid placeholder in ${source}"; return; }

    printf '%s\n' "${text}"

}
template-render () {

    fs-produce "${2}" "${3:-600}" template-text "${1}"

}
template-env-text () {

    local compose="${1}" key="" value=""

    shift

    for key in "$@"; do
        cfg-value value "${key}" || return
        printf '%s=' "${key}"
        parse-env-string "${value}" "${compose}" || return
        printf '\n'
    done

}
template-env () {

    local destination="${1}"

    shift
    fs-produce "${destination}" 600 template-env-text false "$@"

}
template-compose-env () {

    local destination="${1}"

    shift
    fs-produce "${destination}" 600 template-env-text true "$@"

}
