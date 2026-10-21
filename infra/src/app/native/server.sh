native-server () {

    native-dispatch server "$@"

}
native-server-inspect () {

    ssh-ready || return
    ssh-run docker version --format '{{.Server.Version}}'

}
native-server-stage () {

    local bundle="" settings="" key="" status=0
    local -a keys=() transient=()

    cfg-require SSH_HOST SSH_USER REMOTE_DIR || return
    fs-relative "${CONFIG[REMOTE_DIR]}" || { err "REMOTE_DIR must be relative to the SSH home"; return; }

    if [[ "${TOOL_BUNDLED:-false}" == true ]]; then
        [[ "${TOOL_BUILD}" == release ]] || { err "Stage from a release bundle or the source checkout"; return; }
        bundle="${TOOL_BIN}"
    else
        bundle="$(bash "${TOOL_BIN}" build-release)" || return
    fi

    mapfile -t transient < <(native-server-transient)

    for key in "${CONFIG_SCHEMA[@]}"; do
        [[ "${key}" == SSH_* || "${key}" == REMOTE_* || " ${transient[*]} " == *" ${key} "* ]] || keys+=( "${key}" )
    done

    settings="$(fs-temp-file)" || return
    template-env "${settings}" "${keys[@]}" || status=$?
    (( status != 0 )) || run-retry 3 3 ssh-upload "${bundle}" "${CONFIG[REMOTE_DIR]}/infra" 700 || status=$?
    (( status != 0 )) || run-retry 3 3 ssh-upload "${settings}" "${CONFIG[REMOTE_DIR]}/.env.production" 600 || status=$?
    (( status != 0 )) || native-stage-env API "${settings}" || status=$?
    (( status != 0 )) || native-stage-env WEB "${settings}" || status=$?
    rm -f -- "${settings}"

    (( status == 0 )) || return "${status}"
    ui-result server-stage true safe

}
native-stage-env () {

    local app="${1}" file="${2}" content=""

    if ! native-env-present "${app}"; then
        [[ "${app}" != API ]] || warn "${app} env not staged: export ${app}_ENV_FILE; the server keeps its current copy"
        return 0
    fi

    content="$(native-env-content "${app}")" || return
    printf '%s\n' "${content}" | fs-write "${file}" 600 || return
    run-retry 3 3 ssh-upload "${file}" "${CONFIG[REMOTE_DIR]}/.env.${app,,}" 600

}
native-server-run () {

    local directory="${CONFIG[REMOTE_DIR]:-}" jobs="${MANIFEST[paths.cache]}/jobs" id="" key="" result="" status=0 probe=0 attempt=0 starts=1 lost=false
    local -a transient=()

    cfg-require REMOTE_DIR || return
    fs-relative "${directory}" || { err "REMOTE_DIR must be relative to the SSH home"; return; }
    mapfile -t transient < <(native-server-transient)

    for key in "${transient[@]}"; do
        net-safe "${CONFIG[${key}]}" || { err "${key} must be a single line"; return; }
    done

    id="$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}${RANDOM}"

    native-server-launch "${directory}" "${jobs}" "${id}" "$@" || status=$?
    (( status != 255 )) || lost=true

    while (( status != 0 )); do

        probe=0
        result="$(ssh-job status "${directory}" "${jobs}" "${id}" < /dev/null 2>/dev/null)" || probe=$?

        case "${probe}" in
            0)
                [[ "${result}" =~ ^[0-9]{1,3}$ ]] || { err "Remote job ${id} reported an invalid status"; return; }
                (( status != 255 )) || { warn "Connection lost; replaying remote job ${id}"; ssh-job follow "${directory}" "${jobs}" "${id}" < /dev/null || true; }
                return "${result}"
            ;;
            66)
                [[ "${lost}" == true && "${starts}" -lt 3 ]] || { err "Remote job ${id} did not start"; return; }
                starts=$(( starts + 1 ))
                warn "Connection lost before remote job ${id} started; starting it again (${starts}/3)"
                sleep "$(( starts * 3 ))"
                status=0
                lost=false
                native-server-launch "${directory}" "${jobs}" "${id}" "$@" || status=$?
                (( status != 255 )) || lost=true
                continue
            ;;
            68) err "Remote job ${id} was claimed but its start was cut off, so it may be running; read ${directory}/${jobs}/${id}.out before running it again"; return ;;
            69) err "Remote job ${id} ended without a status; read ${directory}/${jobs}/${id}.err"; return ;;
        esac

        (( attempt < 10 )) || { err "Remote job ${id} is unreachable; if it started it keeps running and logs to ${directory}/${jobs}/${id}.out"; return; }
        attempt=$(( attempt + 1 ))
        warn "Connection lost; following remote job ${id} again (${attempt}/10)"
        sleep 6

        status=0
        ssh-job follow "${directory}" "${jobs}" "${id}" < /dev/null || status=$?

    done

}
native-server-launch () {

    local directory="${1}" jobs="${2}" id="${3}" key="" pair=""
    local -a transient=()

    shift 3
    mapfile -t transient < <(native-server-transient)

    {
        for key in "${transient[@]}"; do
            printf '%s=%s\0' "${key}" "${CONFIG[${key}]}"
        done

        for pair in "${CLI_OVERRIDES[@]}"; do
            [[ "${pair}" == SSH_* || "${pair}" == REMOTE_* ]] || printf '%s\0' "${pair}"
        done
    } | ssh-job start "${directory}" "${jobs}" "${id}" "$@"

}
native-route () {

    local command="${1}"
    local -a forwarded=()

    shift
    [[ -n "${CONFIG[SSH_HOST]}" ]] || { "native-${command}" "$@"; return; }
    native-allowed "${command}" "${1:-}" || return

    mapfile -t forwarded < <(native-route-flags)
    info "Running ${command} on ${CONFIG[SSH_USER]}@${CONFIG[SSH_HOST]}"

    if [[ "${command}" == deploy ]] && ! cli-flag --dry-run; then
        native-server-stage || return
        native-server-run edge apply || return
    fi

    native-server-run "${command}" "$@" "${forwarded[@]}"

}
native-route-flags () {

    local flag="" value=""

    while IFS= read -r flag; do
        [[ "${flag}" != --local ]] || continue
        out "${flag}"
        if value="$(cli-value "${flag}")"; then out "${value}"; fi
    done < <(cli-switches)

}
native-server-transient () {

    local key=""

    for key in GITHUB_TOKEN REGISTRY_USER REGISTRY_TOKEN GITOPS_USER GITOPS_TOKEN; do
        [[ -n "${CONFIG[${key}]}" && "${CONFIG_SOURCE[${key}]}" =~ ^(process|cli)$ ]] && out "${key}"
    done

    return 0

}
native-server-install () {

    native-server-run docker install

}
