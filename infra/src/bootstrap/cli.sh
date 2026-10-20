declare -ga BOOTSTRAP_COMMANDS=(
    'help|Tool|help [COMMAND]|Show every command, or one command with its flags, notes and examples'
    'version|Tool|version|Print the tool, stack and build'
    'config|Tool|config [KEY] [--changed]|Print one resolved setting, or every setting with its source, secrets redacted'
    'check|Tool|check|Run syntax, ShellCheck, layer and style laws over every source'
    'test|Tool|test [FILTER] [--check] [--list]|Run every test in an isolated process'
    'build|Tool|build|Build the development bundle, tests included'
    'build-release|Tool|build-release|Build the release bundle and its SHA256SUMS'
    'checksum|Tool|checksum|Print the SHA-256 of the release bundle'
    'prepare|Tool|prepare|Install the checksum-pinned ShellCheck into the build tools'
)
declare -ga STACK_COMMANDS=() COMMAND_GROUPS=()
declare -gA COMMAND_FLAGS=() COMMAND_ABOUT=() COMMAND_NOTES=() COMMAND_EXAMPLES=() COMMAND_WHERE=()

COMMAND_FLAGS[config]='--changed=List only the settings whose value differs from the default'
COMMAND_FLAGS[test]='--check=Run the check gate before the tests|--list=List the test names without running them'
COMMAND_ABOUT[config]='Resolves the settings exactly as every command does, so the value printed is the value used. Secrets print as [redacted].'
COMMAND_NOTES[config]='Sources: defaults, file, process, cli, release, gitops, derived, manifest|Precedence: .env.example defaults, the env file, the process environment, -e'
COMMAND_EXAMPLES[config]='infra config RELEASE|infra config --changed|infra --config prod.env config API_HOST'
COMMAND_ABOUT[test]='Builds the development bundle and runs each test in a fresh process with its own HOME and TMPDIR, so no test can leak into another.'
COMMAND_EXAMPLES[test]='infra test --check|infra test restore|infra test --list'

bootstrap-commands () {

    printf '%s\n' "${BOOTSTRAP_COMMANDS[@]}" "${STACK_COMMANDS[@]}"

}
bootstrap-unknown () {

    local suggestion=""
    local -a names=()

    mapfile -t names < <(bootstrap-commands | cut -d'|' -f1)
    suggestion="$(cli-suggest "${1}" "${names[@]}")"

    err "Unknown command: ${1}${suggestion:+; did you mean ${suggestion}?} See infra help"

}
bootstrap-row () {

    local name="${1:-}" row=""
    local -a rows=()

    mapfile -t rows < <(bootstrap-commands)

    for row in "${rows[@]}"; do
        [[ "${row%%|*}" != "${name}" ]] || { out "${row}"; return 0; }
    done

    return 1

}
bootstrap-flags () {

    local command="${1}" flag="" allowed=""

    bootstrap-row "${command}" >/dev/null || { bootstrap-unknown "${command}"; return; }

    allowed="|${COMMAND_FLAGS[${command}]:-}"
    [[ "${COMMAND_WHERE[${command}]:-}" != server ]] || allowed+="|--local="

    while IFS= read -r flag; do
        [[ -n "${flag}" ]] || continue
        [[ "${allowed}" == *"|${flag}="* || "${allowed}" == *"|${flag} "* ]] || { err "${command} does not take ${flag}; see infra help ${command}"; return; }
    done < <(cli-switches)

}
bootstrap-valued () {

    local table="" entry=""
    local -a entries=()

    for table in "${COMMAND_FLAGS[@]}"; do
        IFS='|' read -r -a entries <<< "${table}"
        for entry in "${entries[@]}"; do
            [[ ! "${entry}" =~ ^(--[a-z][a-z0-9-]*)\ [A-Z]+= ]] || CLI_VALUED["${BASH_REMATCH[1]}"]=true
        done
    done

}
bootstrap-help () {

    local command="${1:-}"

    if [[ -z "${command}" ]]; then bootstrap-overview
    else bootstrap-manual "${command}"
    fi

}
bootstrap-overview () {

    local group="" row="" name="" section="" usage="" summary="" UI_WIDTH=0

    while IFS='|' read -r name section usage summary; do
        (( ${#usage} <= UI_WIDTH )) || UI_WIDTH="${#usage}"
    done < <(bootstrap-commands)

    out "${MANIFEST[name]} ${MANIFEST[version]} · stack ${MANIFEST[stack]} · ${TOOL_BUILD} build"
    out 'Ships, guards and operates one server: blue/green releases, data, edge, backups and notifications.'
    ui-section Usage
    ui-row 'infra [GLOBAL FLAGS] COMMAND [ARGUMENTS] [FLAGS]'
    ui-row 'infra help COMMAND' 'Flags, notes and examples for one command'

    for group in "${COMMAND_GROUPS[@]}" Tool; do
        ui-section "${group}"
        while IFS='|' read -r name section usage summary; do
            [[ "${section}" != "${group}" ]] || ui-row "${usage}" "${summary}"
        done < <(bootstrap-commands)
    done

    bootstrap-globals
    ui-section Settings
    out '  Resolution: .env.example defaults, then the env file, the process environment and -e overrides.'
    out '  ENV_FILE (plain or one base64 line) replaces the file. A release bundle reads .env.production, .env.prod'
    out '  or .env; a checkout reads .env.local, otherwise .env. Server commands run on SSH_HOST when it is set.'
    out '  Commands that interrupt or remove need --force. Secrets are redacted everywhere. Failures exit non-zero.'

}
bootstrap-globals () {

    local UI_WIDTH=14

    ui-section 'Global flags'
    ui-row '--config FILE' 'Load this env file instead of the automatic choice; repeatable, later files win'
    ui-row '--project DIR' 'Project root holding the env files and the state; defaults to the tool directory'
    ui-row '--target HOST' 'SSH target for server commands; overrides SSH_HOST'
    ui-row '--local' 'Run a server command on this host even when SSH_HOST is set'
    ui-row '-e KEY=VALUE' 'Override one setting with the highest precedence; repeatable'
    ui-row '-h, --help' 'Show help; after a command, that command'"'"'s help'
    ui-row '--version' 'Print the version'

}
bootstrap-manual () {

    local command="${1}" row="" name="" usage="" summary="" entry="" flag="" text="" UI_WIDTH=12
    local -a entries=()

    row="$(bootstrap-row "${command}")" || { bootstrap-unknown "${command}"; return; }

    IFS='|' read -r name _ usage summary <<< "${row}"

    out "infra ${usage}"
    out "${summary}."
    [[ -z "${COMMAND_ABOUT[${name}]:-}" ]] || { printf '\n'; fold -s -w 100 <<< "${COMMAND_ABOUT[${name}]}" | sed 's/ *$//'; }

    if [[ -n "${COMMAND_FLAGS[${name}]:-}" ]]; then
        ui-section Flags
        IFS='|' read -r -a entries <<< "${COMMAND_FLAGS[${name}]}"
        for entry in "${entries[@]}"; do
            flag="${entry%%=*}"
            text="${entry#*=}"
            ui-row "${flag}" "${text}"
        done
    fi

    if [[ "${COMMAND_WHERE[${name}]:-}" == server ]]; then
        ui-section Where
        ui-row "Runs on SSH_HOST over SSH when it is set, or here with --local; the server reads its staged settings"
    fi

    if [[ -n "${COMMAND_NOTES[${name}]:-}" ]]; then
        ui-section Notes
        IFS='|' read -r -a entries <<< "${COMMAND_NOTES[${name}]}"
        for entry in "${entries[@]}"; do
            ui-row "• ${entry}"
        done
    fi

    if [[ -n "${COMMAND_EXAMPLES[${name}]:-}" ]]; then
        ui-section Examples
        IFS='|' read -r -a entries <<< "${COMMAND_EXAMPLES[${name}]}"
        for entry in "${entries[@]}"; do
            ui-row "${entry}"
        done
    fi

    ui-section 'Global flags'
    ui-row '--config FILE, --project DIR, --target HOST, -e KEY=VALUE; see infra help'

}
bootstrap-version () {

    out "${MANIFEST[name]} ${MANIFEST[version]} (stack ${MANIFEST[stack]}, ${TOOL_BUILD} build, bash ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]})"

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

    local key="" UI_WIDTH=0

    (( $# <= 1 )) || { err "Usage: config [KEY] [--changed]"; return; }
    [[ -z "${1:-}" ]] || { cfg-show "${1}"; return; }

    for key in "${CONFIG_SCHEMA[@]}"; do
        (( ${#key} <= UI_WIDTH )) || UI_WIDTH="${#key}"
    done

    for key in "${CONFIG_SCHEMA[@]}"; do
        ! cli-flag --changed || [[ "${CONFIG[${key}]}" != "${CONFIG_DEFAULTS[${key}]}" ]] || continue
        ui-row "${key}" "$(cfg-show "${key}")  (${CONFIG_SOURCE[${key}]})"
    done

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

    config-manifest || return
    bootstrap-app || return
    bootstrap-valued
    cli-parse "$@" || return

    ! cli-flag --version || { bootstrap-version; return; }

    command="${CLI_ARGS[0]:-help}"
    stack="${MANIFEST[stack]}"
    set -- "${CLI_ARGS[@]:1}"

    if cli-flag --help; then
        if [[ "${command}" == help ]]; then bootstrap-help "${1:-}"
        else bootstrap-help "${command}"
        fi
        return
    fi

    case "${command}" in
        __tests)
            config-load || return
            bootstrap-discover
            return
        ;;
        __test)
            config-load || return
            bootstrap-isolate "$@"
            return
        ;;
    esac

    bootstrap-flags "${command}" || return

    case "${command}" in
        help|version|build|build-release|checksum|prepare|check|test)
            "bootstrap-${command}" "$@"
        ;;
        config)
            config-load || return
            bootstrap-config "$@"
        ;;
        *)
            config-load || return
            [[ "${COMMAND_WHERE[${command}]:-}" != server ]] || cli-flag --local || { "${stack}-route" "${command}" "$@"; return; }
            "${stack}-${command}" "$@"
        ;;
    esac

}
