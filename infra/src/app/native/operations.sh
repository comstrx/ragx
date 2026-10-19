source-include module/docker.sh || return
source-include module/registry.sh || return
source-include module/tls.sh || return
source-include module/cloudflare.sh || return
source-include module/firewall.sh || return
source-include module/systemd.sh || return
source-include module/launchd.sh || return

native-plan () {

    ui-row stack "${CONFIG[STACK]}"
    ui-row mode "${CONFIG[ENV_MODE]}"
    ui-row environment "${CONFIG[DEPLOY_ENV]}"
    ui-row driver "${CONFIG[DEPLOY_DRIVER]}"
    ui-row strategy "${CONFIG[DEPLOY_STRATEGY]}"
    ui-row target "${CONFIG[SSH_HOST]:-local}"
    ui-row registry "${CONFIG[REGISTRY_DRIVER]}"
    ui-row protocols "$(native-protocols)"
    ui-row state "${CONFIG[STATE_ROOT]}"

}
native-protocols () {

    local protocols="http/1.1"

    cfg-true TLS_ENABLED && protocols+=" h2"
    cfg-true TLS_ENABLED && cfg-true HTTP3_ENABLED && protocols+=" h3"

    out "${protocols}"

}
native-status () {

    local name="" value=""

    for name in current previous pending phase active-slot slot-blue slot-green desired; do
        value="$(state-read "${CONFIG[STATE_ROOT]}" "${name}" 2>/dev/null)" || value=""
        ui-row "${name}" "${value:-unset}"
    done

    docker compose ls --all --filter "name=${CONFIG[COMPOSE_PROJECT]}"

}
native-edge () {

    cli-dispatch native-edge "${1:-apply}" apply "${@:2}"

}

native-server () {

    cli-dispatch native-server "${1:-inspect}" 'inspect stage run install' "${@:2}"

}
native-server-inspect () {

    ssh-ready || return
    ssh-run docker version --format '{{.Server.Version}}'

}
native-server-stage () {

    local bundle="" settings="" key="" status=0
    local -a keys=()

    cfg-require SSH_HOST SSH_USER REMOTE_DIR || return
    fs-relative "${CONFIG[REMOTE_DIR]}" || { err "REMOTE_DIR must be relative to the SSH home"; return; }

    if [[ "${TOOL_BUNDLED:-false}" == true ]]; then
        [[ "${TOOL_BUILD}" == release ]] || { err "Stage from a release bundle or the source checkout"; return; }
        bundle="${TOOL_BIN}"
    else
        bundle="$(bash "${TOOL_BIN}" build-release)" || return
    fi

    for key in "${CONFIG_SCHEMA[@]}"; do
        [[ "${key}" == SSH_* || "${key}" == REMOTE_* ]] || keys+=( "${key}" )
    done

    settings="$(fs-temp-file)" || return
    template-env "${settings}" "${keys[@]}" || status=$?
    (( status != 0 )) || ssh-upload "${bundle}" "${CONFIG[REMOTE_DIR]}/infra" 700 || status=$?
    (( status != 0 )) || ssh-upload "${settings}" "${CONFIG[REMOTE_DIR]}/.env.production" 600 || status=$?
    rm -f -- "${settings}"

    (( status == 0 )) || return "${status}"
    ui-result server-stage true safe

}
native-server-run () {

    cfg-require REMOTE_DIR || return
    fs-relative "${CONFIG[REMOTE_DIR]}" || { err "REMOTE_DIR must be relative to the SSH home"; return; }

    ssh-run bash -c 'cd -- "$1" && shift && exec ./infra "$@"' infra-run "${CONFIG[REMOTE_DIR]}" "$@"

}
native-server-install () {

    native-server-run docker install

}

native-docker () {

    cli-dispatch native-docker "${1:-status}" 'status install' "${@:2}"

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

native-registry () {

    cli-dispatch native-registry "${1:-host}" 'host reference login push logout' "${@:2}"

}
native-registry-host () {

    registry-host

}
native-registry-reference () {

    registry-reference "$@"

}
native-registry-login () {

    local host=""

    cfg-require REGISTRY_USER REGISTRY_TOKEN || return
    host="$(registry-host)" || return

    docker-login "${host}" "${CONFIG[REGISTRY_USER]}" "${CONFIG[REGISTRY_TOKEN]}" || return
    ui-result registry-login true safe

}
native-registry-push () {

    registry-owns "${1:-}" || return

    docker-push "${1}"

}
native-registry-logout () {

    local host=""

    host="$(registry-host)" || return

    docker-logout "${host}"

}

native-image () {

    cli-dispatch native-image "${1:-digest}" 'build digest' "${@:2}"

}
native-image-build () {

    local component="${1:-}" tag="${2:-}" spec="${3:-}" root="${TOOL_ROOT%/*}" dockerfile=""
    local -a arguments=()

    [[ "${component}" == api || "${component}" == web ]] || { err "Usage: image build api|web TAG [SPEC]"; return; }
    [[ "${TOOL_BUNDLED:-false}" != true ]] || { err "Image builds need the monorepo checkout"; return; }
    parse-image "${tag}" || { err "Invalid image tag: ${tag}"; return; }

    case "${component}" in
        api)
            arguments=( --build-arg "PYTHON_IMAGE=${CONFIG[IMAGE_PYTHON]}" --build-arg "UV_IMAGE=${CONFIG[IMAGE_UV]}" )
        ;;
        web)
            [[ "${spec}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { err "Usage: image build web TAG SPEC"; return; }
            cfg-require API_HOST || return
            arguments=( --build-arg "BUN_IMAGE=${CONFIG[IMAGE_BUN]}" --build-arg "NODE_IMAGE=${CONFIG[IMAGE_NODE]}" --build-arg "SPEC=${spec}" --build-arg "API_URL=${CONFIG[API_URL]}" )
        ;;
    esac

    dockerfile="${TOOL_ROOT}/${MANIFEST[paths.templates]}/image/${component}.Dockerfile"

    docker-client build --tag "${tag}" --file "${dockerfile}" "${arguments[@]}" "${root}" || { err "Image build failed: ${component}"; return; }

}
native-image-digest () {

    docker-digests "${1:-}"

}

native-timer () {

    cli-dispatch native-timer "${1:-}" 'install stop' "${@:2}"

}
native-timer-install () {

    local command="${1:-}" seconds="${2:-}" root="${CONFIG[PROJECT_ROOT]}" binary="${TOOL_BIN}" name="" directory="${CONFIG[STATE_ROOT]}/units"
    local -a arguments=()

    case "${command}" in
        reconcile|backup|monitor) arguments=( "${command}" ) ;;
        renew)                    arguments=( tls renew ) ;;
        *)                        err "Usage: timer install reconcile|backup|monitor|renew SECONDS"; return ;;
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
native-timer-stop () {

    local name="${CONFIG[COMPOSE_PROJECT]}-${1:-}"

    [[ "${1:-}" =~ ^(reconcile|backup|monitor|renew)$ ]] || { err "Usage: timer stop reconcile|backup|monitor|renew"; return; }

    if is-linux; then systemd-stop "${name}"
    elif is-macos; then launchd-stop "${name}"
    else err "Timers need systemd or launchd"
    fi

}

native-dns () {

    cli-dispatch native-dns "${1:-check}" 'check set' "${@:2}"

}
native-dns-check () {

    cloudflare-check "${1:-${CONFIG[API_HOST]}}"

}
native-dns-set () {

    cfg-require DNS_ADDRESS || return
    ! cfg-true CLOUDFLARE_PROXIED || ! cfg-true HTTP3_ENABLED || warn "Proxied record: Cloudflare terminates public QUIC; origin HTTP/3 stays unused"

    cloudflare-upsert "${1:-${CONFIG[API_HOST]}}" "${CONFIG[DNS_ADDRESS]}" "${CONFIG[CLOUDFLARE_PROXIED]}" || return
    ui-result dns-set true safe

}

native-tls () {

    cli-dispatch native-tls "${1:-present}" 'issue renew present import' "${@:2}"

}
native-tls-issue () {

    tls-volumes || return
    native-certificate || return
    native-edge-reload

}
native-tls-renew () {

    tls-renew || return
    native-edge-reload

}
native-tls-present () {

    tls-present && { out present; return; }

    out absent
    return 1

}
native-tls-import () {

    tls-import "$@" || return
    [[ ! -f "${CONFIG[STATE_ROOT]}/edge/edge.yaml" ]] || native-edge-reload

}

native-firewall () {

    cli-dispatch native-firewall "${1:-ports}" 'ports apply' "${@:2}"

}
native-firewall-ports () {

    out "${CONFIG[HTTP_PORT]}/tcp"
    cfg-true TLS_ENABLED && out "${CONFIG[HTTPS_PORT]}/tcp"
    cfg-true TLS_ENABLED && cfg-true HTTP3_ENABLED && out "${CONFIG[HTTPS_PORT]}/udp"

    return 0

}
native-firewall-apply () {

    local -a ports=()

    cli-flag --force || { err "Review firewall ports, then repeat with --force; no rule is removed"; return; }
    mapfile -t ports < <(native-firewall-ports)

    firewall-apply "${ports[@]}" || return
    ui-result firewall-apply true safe

}
