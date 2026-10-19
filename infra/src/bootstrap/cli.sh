declare -ga BOOTSTRAP_COMMANDS=(
    'help|help|Show this help'
    'build|build|Build the development bundle, tests included'
    'build-release|build-release|Build the release bundle and its SHA256SUMS'
    'checksum|checksum|Print the SHA-256 of the release bundle'
    'prepare|prepare|Install the checksum-pinned ShellCheck into the build tools'
    'check|check|Run syntax, ShellCheck, layer and style laws'
    'test|test [FILTER] [--check] [--list]|Run every test in an isolated process'
    'run|run [ARGS...]|Run the configured entrypoint'
    'config|config KEY|Print one resolved setting with secrets redacted'
)
declare -ga STACK_COMMANDS=()

bootstrap-help () {

    out "${MANIFEST[name]} ${MANIFEST[version]} (stack ${MANIFEST[stack]})"
    ui-section Usage
    ui-row 'infra [OPTIONS] COMMAND [ARGS...]'
    ui-row '--project DIR' 'Project root holding the env files and the cache'
    ui-row '--config FILE' 'Ordered env files replacing the automatic selection'
    ui-row '--environment staging|production' 'Deployment environment'
    ui-row '--target HOST' 'SSH target for remote commands'
    ui-row '-e KEY=VALUE' 'Highest precedence override'
    ui-row '--force' 'Confirm an operation that interrupts or removes'
    ui-table Governance "${BOOTSTRAP_COMMANDS[@]}"
    ui-table "Stack ${MANIFEST[stack]}" "${STACK_COMMANDS[@]}"
    ui-section Contract
    out '  Precedence: .env.example defaults, env files, process env, -e overrides.'
    out '  Secrets are redacted from every output channel. Failures exit nonzero. No implicit sudo.'

}
bootstrap-app () {

    local stack="${MANIFEST[stack]}" file="" count=0

    while IFS= read -r file; do
        source-include "${file}" || return
        count=$(( count + 1 ))
    done < <(source-list "app/${stack}")

    (( count > 0 )) || { err "Stack ${stack} has no app/${stack} sources"; return; }
    (( ${#STACK_COMMANDS[@]} > 0 )) || { err "Stack ${stack} declares no commands"; return; }

}
bootstrap-config () {

    (( $# == 1 )) || { err "Usage: config KEY"; return; }

    cfg-show "${1}"

}
bootstrap-main () {

    local command="" stack=""

    (( BASH_VERSINFO[0] >= 5 )) || { printf '%s\n' '[-] Bash 5 or newer required' >&2; return 1; }

    set +x
    umask 077
    TOOL_TEMP="$(mktemp -d "${TMPDIR:-/tmp}/infra-session.XXXXXXXX")" || { err "Cannot create the session directory"; return; }
    trap 'rm -rf -- "${TOOL_TEMP}"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    cli-parse "$@" || return
    config-manifest || return
    bootstrap-app || return

    command="${CLI_ARGS[0]:-help}"
    stack="${MANIFEST[stack]}"
    set -- "${CLI_ARGS[@]:1}"

    case "${command}" in
        help|build|build-release|checksum|prepare|check|test)
            "bootstrap-${command}" "$@"
        ;;
        run|config)
            config-load || return
            "bootstrap-${command}" "$@"
        ;;
        __tests)
            config-load || return
            bootstrap-discover
        ;;
        __test)
            config-load || return
            bootstrap-isolate "$@"
        ;;
        *)
            cli-has "${command}" "${STACK_COMMANDS[@]}" || { err "Unknown command: ${command}; see help"; return; }
            config-load || return
            "${stack}-${command}" "$@"
        ;;
    esac

}
