fs-dir () {

    local path="${1:-}" mode="${2:-700}"

    [[ -n "${path}" ]] || { err "Directory path required"; return; }
    [[ ! -L "${path}" ]] || { err "Refusing symlinked directory: ${path}"; return; }

    mkdir -p -- "${path}" && chmod "${mode}" "${path}"

}
fs-read () {

    local path="${1:-}"

    [[ -f "${path}" && ! -L "${path}" ]] || { err "Regular file required: ${path}"; return; }

    cat -- "${path}"

}
fs-write () {

    local path="${1:-}" mode="${2:-600}" parent="" temporary=""

    [[ -n "${path}" ]] || { err "Destination required"; return; }
    [[ ! -L "${path}" ]] || { err "Refusing symlink destination: ${path}"; return; }

    parent="${path%/*}"
    [[ "${parent}" != "${path}" ]] || parent=.

    ( umask 077; mkdir -p -- "${parent}" ) || { err "Cannot create directory: ${parent}"; return; }
    temporary="$(mktemp "${path}.tmp.XXXXXXXX")" || { err "Cannot stage: ${path}"; return; }

    if cat > "${temporary}" && chmod "${mode}" "${temporary}" && mv -f -- "${temporary}" "${path}"; then
        return 0
    fi

    rm -f -- "${temporary}"
    err "Atomic write failed: ${path}"

}
fs-produce () {

    local destination="${1}" mode="${2}" temporary="" status=0

    shift 2
    temporary="$(fs-temp-file)" || return

    if "$@" > "${temporary}"; then fs-write "${destination}" "${mode}" < "${temporary}" || status=$?
    else status=$?
    fi

    rm -f -- "${temporary}"
    return "${status}"

}
fs-copy () {

    fs-produce "${2}" "${3:-600}" fs-read "${1}"

}

fs-hash () {

    local result=""

    if has sha256sum; then result="$(sha256sum -- "${1}")" || return
    elif has shasum; then result="$(shasum -a 256 -- "${1}")" || return
    else err "sha256sum or shasum required"; return
    fi

    out "${result%% *}"

}
fs-hashes () {

    local path="" digest="" joined=""

    for path in "$@"; do
        digest="$(fs-hash "${path}")" || return
        joined+="${digest}"$'\n'
    done

    printf '%s' "${joined}" | fs-hash -

}
fs-mode () {

    stat -c '%a' -- "${1}" 2>/dev/null || stat -f '%Lp' -- "${1}"

}
fs-modified () {

    stat -c '%Y' -- "${1}" 2>/dev/null || stat -f '%m' -- "${1}"

}

fs-relative () {

    local path="${1:-}"

    [[ -n "${path}" && "${path}" != /* && "${path}" != -* ]] || return 1
    [[ "${path}" != *\\* && "${path}" != *$'\n'* ]] || return 1

    [[ "/${path}/" != */../* && "/${path}/" != */./* && "/${path}/" != *//* ]]

}
fs-within () {

    local root="${1}" relative="${2:-}" part="" walked="${1}"
    local -a parts=()

    fs-relative "${relative}" || { err "Expected a confined relative path: ${relative}"; return; }
    IFS=/ read -r -a parts <<< "${relative}"

    for part in "${parts[@]}"; do
        walked+="/${part}"
        [[ ! -L "${walked}" ]] || { err "Path traverses a symlink: ${relative}"; return; }
    done

    out "${root}/${relative}"

}
fs-files () {

    local root="${1}" suffix="${2:-}" file="" LC_ALL=C

    [[ -d "${root}" ]] || { err "Directory required: ${root}"; return; }

    (
        shopt -s nullglob globstar

        for file in "${root}"/**/*; do
            [[ -f "${file}" && ! -L "${file}" && "${file}" == *"${suffix}" ]] || continue
            printf '%s\0' "${file}"
        done
    )

}

fs-temp () {

    mktemp -d "${TOOL_TEMP:-${TMPDIR:-/tmp}}/infra.XXXXXXXX" || err "Cannot create a temporary directory"

}
fs-temp-file () {

    mktemp "${TOOL_TEMP:-${TMPDIR:-/tmp}}/infra.XXXXXXXX" || err "Cannot create a temporary file"

}
fs-remove-tree () {

    local root="${1:-}" path="${2:-}"

    [[ -n "${root}" && "${root}" != / && "${path}" == "${root}/"* && "/${path}/" != */../* ]] || { err "Refusing removal outside ${root}: ${path}"; return; }
    [[ ! -L "${root}" && ! -L "${path}" ]] || { err "Refusing symlinked removal: ${path}"; return; }

    rm -rf -- "${path}"

}
