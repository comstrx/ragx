out () {

    printf '%s\n' "$@"

}
lower () {

    local value="${1-}"

    printf '%s\n' "${value,,}"

}
upper () {

    local value="${1-}"

    printf '%s\n' "${value^^}"

}

log-secret () {

    case "${1-}" in
        *PASSWORD*|*SECRET*|*TOKEN*|*CREDENTIAL*|*WEBHOOK_URL|*_KEY|*_KEYS) return 0 ;;
    esac

    return 1

}
log-redact () {

    local text="${1-}" key="" value=""

    declare -p CONFIG >/dev/null 2>&1 || { printf '%s' "${text}"; return 0; }

    for key in "${!CONFIG[@]}"; do

        log-secret "${key}" || continue

        value="${CONFIG[${key}]}"
        [[ -z "${value}" ]] || text="${text//"${value}"/[redacted]}"

    done

    printf '%s' "${text}"

}
log-color () {

    [[ -z "${NO_COLOR:-}" ]] || return 1
    [[ -z "${FORCE_COLOR:-}" ]] || return 0

    [[ -t 2 && "${TERM:-dumb}" != dumb ]]

}
log-line () {

    local color="${1}" tag="${2}" text=""

    shift 2
    text="$(log-redact "$*")"

    if log-color; then printf '\033[%sm%s\033[0m %s\n' "${color}" "${tag}" "${text}" >&2
    else printf '%s %s\n' "${tag}" "${text}" >&2
    fi

    return 0

}

info () {

    log-line 96 '[*]' "$*"

}
succ () {

    log-line 32 '[+]' "$*"

}
warn () {

    log-line 33 '[!]' "$*"

}
err () {

    log-line 31 '[-]' "$*"
    return 1

}
