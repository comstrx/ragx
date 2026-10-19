state-write () {

    local root="${1}" name="${2:-}" value="${3-}"

    parse-identifier "${name}" || { err "Invalid state name: ${name}"; return; }

    printf '%s\n' "${value}" | fs-write "${root}/${name}"

}
state-read () {

    local root="${1}" name="${2:-}"

    parse-identifier "${name}" || { err "Invalid state name: ${name}"; return; }
    [[ -f "${root}/${name}" ]] || return 1

    fs-read "${root}/${name}"

}
state-audit () {

    local root="${1}" release="${2:-}" phase="${3:-}"

    parse-identifier "${release}" || { err "Invalid release: ${release}"; return; }
    parse-identifier "${phase}" || { err "Invalid phase: ${phase}"; return; }

    ( umask 077; printf '%s release=%s phase=%s pid=%s\n' "$(date -u +%FT%TZ)" "${release}" "${phase}" "${BASHPID}" >> "${root}/audit.log" )

}

state-lock () {

    local path="${1}"

    if ( umask 077; mkdir -- "${path}" ) 2>/dev/null; then
        printf '%s\n' "${BASHPID}" > "${path}/owner"
        return 0
    fi

    err "Locked by another operation; inspect status before recover --force: ${path}"

}
state-unlock () {

    local path="${1}" owner=""

    [[ -f "${path}/owner" && ! -L "${path}" ]] || { err "Lock missing: ${path}"; return; }
    IFS= read -r owner < "${path}/owner" || { err "Lock owner unreadable: ${path}"; return; }
    [[ "${owner}" == "${BASHPID}" ]] || { err "Lock owned by ${owner}: ${path}"; return; }

    rm -- "${path}/owner" && rmdir -- "${path}"

}
state-locked () {

    local path="${1}"

    shift

    (
        state-lock "${path}" || exit
        trap 'state-unlock "${path}"' EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        "$@"
    )

}
state-recover () {

    local path="${1}" owner=""

    [[ -d "${path}" && ! -L "${path}" && -f "${path}/owner" && ! -L "${path}/owner" ]] || { err "No recoverable lock: ${path}"; return; }

    owner="$(fs-read "${path}/owner")" || return
    [[ "${owner}" =~ ^[1-9][0-9]*$ ]] || { err "Invalid lock owner: ${path}"; return; }
    ! kill -0 "${owner}" 2>/dev/null || { err "Lock owner ${owner} is still alive"; return; }

    rm -- "${path}/owner" && rmdir -- "${path}"

}
