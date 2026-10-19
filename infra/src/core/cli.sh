declare -gA CLI_FLAGS=()
declare -ga CLI_ARGS=() CLI_OVERRIDES=() CLI_CONFIGS=()

cli-parse () {

    CLI_FLAGS=()
    CLI_ARGS=()
    CLI_OVERRIDES=()
    CLI_CONFIGS=()

    while (( $# > 0 )); do

        case "${1}" in
            --config)
                [[ -n "${2:-}" ]] || { err "Value required: ${1}"; return; }
                CLI_CONFIGS+=( "${2}" )
                shift 2
            ;;
            --project|--environment|--target)
                [[ -n "${2:-}" ]] || { err "Value required: ${1}"; return; }
                [[ -z "${CLI_FLAGS[${1}]+x}" ]] || { err "Repeated flag: ${1}"; return; }
                CLI_FLAGS["${1}"]="${2}"
                shift 2
            ;;
            -e)
                [[ "${2:-}" =~ ^[A-Z][A-Z0-9_]*= ]] || { err "Expected KEY=VALUE after -e"; return; }
                CLI_OVERRIDES+=( "${2}" )
                shift 2
            ;;
            --force|--check|--list)
                CLI_FLAGS["${1}"]=true
                shift
            ;;
            -h|--help)
                CLI_ARGS=( help )
                shift
            ;;
            --)
                shift
                CLI_ARGS+=( "$@" )
                break
            ;;
            -*)
                err "Unknown flag: ${1}"
                return
            ;;
            *)
                CLI_ARGS+=( "${1}" )
                shift
            ;;
        esac

    done

}
cli-flag () {

    [[ "${CLI_FLAGS[${1}]:-false}" == true ]]

}
cli-dispatch () {

    local prefix="${1}" action="${2}" allowed="${3}"

    shift 3

    [[ " ${allowed} " == *" ${action} "* ]] || { err "Unknown command: ${action} (expected: ${allowed})"; return; }
    declare -F "${prefix}-${action}" >/dev/null || { err "Unsupported operation: ${action}"; return; }

    "${prefix}-${action}" "$@"

}
cli-has () {

    local name="${1:-}" row=""

    shift

    for row in "$@"; do
        [[ "${row%%|*}" != "${name}" ]] || return 0
    done

    return 1

}
cli-names () {

    local row=""

    for row in "$@"; do
        out "${row%%|*}"
    done

}
