declare -gA CLI_FLAGS=() CLI_VALUED=()
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
            --project|--target)
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
            -h|--help|--version)
                CLI_FLAGS["${1/#-h/--help}"]=true
                shift
            ;;
            --)
                shift
                CLI_ARGS+=( "$@" )
                break
            ;;
            --[a-z]*=*)
                [[ -n "${CLI_VALUED[${1%%=*}]+x}" ]] || { err "${1%%=*} takes no value"; return; }
                [[ -z "${CLI_FLAGS[${1%%=*}]+x}" ]] || { err "Repeated flag: ${1%%=*}"; return; }
                CLI_FLAGS["${1%%=*}"]="${1#*=}"
                shift
            ;;
            --[a-z]*)
                [[ "${1}" =~ ^--[a-z][a-z0-9-]*$ ]] || { err "Invalid flag: ${1}"; return; }
                if [[ -n "${CLI_VALUED[${1}]+x}" ]]; then
                    (( $# >= 2 )) || { err "Value required: ${1}"; return; }
                    [[ -z "${CLI_FLAGS[${1}]+x}" ]] || { err "Repeated flag: ${1}"; return; }
                    CLI_FLAGS["${1}"]="${2}"
                    shift 2
                else
                    CLI_FLAGS["${1}"]=true
                    shift
                fi
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

    [[ -z "${CLI_VALUED[${1}]+x}" && "${CLI_FLAGS[${1}]:-false}" == true ]]

}
cli-value () {

    [[ -n "${CLI_VALUED[${1}]+x}" && -n "${CLI_FLAGS[${1}]+x}" ]] || return 1

    out "${CLI_FLAGS[${1}]}"

}
cli-dispatch () {

    local prefix="${1}" action="${2}" allowed="${3}"

    shift 3
    cli-allowed "${prefix#*-}" "${action}" "${allowed}" || return
    declare -F "${prefix}-${action}" >/dev/null || { err "Unsupported operation: ${action}"; return; }

    "${prefix}-${action}" "$@"

}
cli-allowed () {

    local label="${1}" action="${2}" allowed="${3}" suggestion="" expected=""
    local -a names=()

    [[ " ${allowed} " != *" ${action} "* ]] || return 0
    read -r -a names <<< "${allowed}"

    suggestion="$(cli-suggest "${action}" "${names[@]}")"
    expected="${allowed// /, }"
    (( ${#names[@]} < 2 )) || expected="${expected%, *} or ${names[-1]}"

    err "Unknown ${label} action: ${action}${suggestion:+; did you mean ${suggestion}?} (expected ${expected})"

}
cli-actions () {

    local entry="" listed=""
    local -a entries=()

    IFS='|' read -r -a entries <<< "${1:-}"

    for entry in "${entries[@]}"; do
        entry="${entry%%=*}"
        listed+="${listed:+ }${entry%% *}"
    done

    [[ -n "${listed}" ]] || { err "No actions declared"; return; }

    out "${listed}"

}
cli-switches () {

    local flag=""

    for flag in "${!CLI_FLAGS[@]}"; do
        [[ "${flag}" == --project || "${flag}" == --target || "${flag}" == --help || "${flag}" == --version ]] || out "${flag}"
    done | LC_ALL=C sort

}
cli-suggest () {

    local name="${1:-}" candidate="" best="" score=0 lowest=3

    shift

    for candidate in "$@"; do
        [[ "${candidate}" != "${name}"* ]] || { out "${candidate}"; return 0; }
        score="$(cli-distance "${name}" "${candidate}")"
        (( score >= lowest )) || { lowest="${score}"; best="${candidate}"; }
    done

    [[ -z "${best}" ]] || out "${best}"

}
cli-distance () {

    local left="${1}" right="${2}" row="" column="" cost=0 deletion=0 insertion=0 substitution=0
    local -a above=() below=()

    for (( column = 0; column <= ${#right}; column++ )); do
        above[column]="${column}"
    done

    for (( row = 1; row <= ${#left}; row++ )); do
        below=( "${row}" )
        for (( column = 1; column <= ${#right}; column++ )); do
            cost=1
            [[ "${left:row-1:1}" != "${right:column-1:1}" ]] || cost=0
            deletion=$(( above[column] + 1 ))
            insertion=$(( below[column - 1] + 1 ))
            substitution=$(( above[column - 1] + cost ))
            below[column]="${deletion}"
            (( insertion >= below[column] )) || below[column]="${insertion}"
            (( substitution >= below[column] )) || below[column]="${substitution}"
        done
        above=( "${below[@]}" )
    done

    out "${above[${#right}]}"

}
