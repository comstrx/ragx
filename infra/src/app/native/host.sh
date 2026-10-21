source-include module/docker.sh || return
source-include module/systemd.sh || return
source-include module/launchd.sh || return

native-docker () {

    native-dispatch docker "$@"

}
native-docker-status () {

    docker-ready || return
    docker version --format 'engine {{.Server.Version}}'
    docker compose version
    if docker-rootless; then out 'mode rootless'
    else out 'mode rootful'
    fi

}
native-docker-install () {

    docker-install || return
    ui-result docker-install true safe

}
native-timer () {

    native-dispatch timer "$@"

}
native-timer-install () {

    local command="${1:-}" seconds="${2:-}" root="${CONFIG[PROJECT_ROOT]}" binary="${TOOL_BIN}" name="" directory="${CONFIG[STATE_ROOT]}/units"
    local -a arguments=()

    case "${command}" in
        reconcile|backup|monitor) arguments=( "${command}" ) ;;
        renew)                    arguments=( tls renew ) ;;
        archive)                  arguments=( backup archive ) ;;
        *)                        err "Usage: infra timer install monitor|backup|archive|renew|reconcile SECONDS"; return ;;
    esac

    parse-positive "${seconds}" || { err "Timer interval must be a positive number of seconds"; return; }
    [[ "${TOOL_BUNDLED:-false}" == true && "${TOOL_BUILD}" == release ]] || { err "Install timers from the staged release bundle"; return; }
    [[ "${binary}" == /* ]] || binary="${root}/${binary#./}"
    [[ "${root}${binary}" != *[\"%$'\n']* ]] || { err "Timer paths must not contain quotes, percent signs or newlines"; return; }

    name="${CONFIG[COMPOSE_PROJECT]}-${command}"
    fs-dir "${directory}" || return

    if is-linux; then systemd-timer "${name}" "${directory}" "${root}" "\"${binary}\" --project \"${root}\" ${arguments[*]}" "${seconds}" || return
    elif is-macos; then launchd-timer "${name}" "${directory}" "${root}" "${seconds}" "${binary}" --project "${root}" "${arguments[@]}" || return
    else err "Timers need systemd or launchd"; return
    fi

    ui-result timer-install true safe

}
native-timer-remove () {

    local name="${CONFIG[COMPOSE_PROJECT]}-${1:-}"

    [[ "${1:-}" =~ ^(reconcile|backup|archive|monitor|renew)$ ]] || { err "Usage: infra timer remove monitor|backup|archive|renew|reconcile"; return; }

    if is-linux; then ! systemd-present "${name}" || systemd-remove "${name}"
    elif is-macos; then launchd-remove "${name}"
    else err "Timers need systemd or launchd"
    fi

}
native-timer-list () {

    if is-linux; then systemd-list "${CONFIG[COMPOSE_PROJECT]}"
    elif is-macos; then launchd-list "${CONFIG[COMPOSE_PROJECT]}"
    else err "Timers need systemd or launchd"
    fi

}
