source-include module/docker.sh || return
source-include module/haproxy.sh || return
source-include module/tls.sh || return

native-edge-render () {

    local directory="${1}" sockets="${CONFIG[EDGE_SOCKETS]}" address="${CONFIG[BIND_ADDRESS]}" route="" port="" ports="" mounts=""
    local -a routes=() published=()

    while IFS= read -r route; do
        routes+=( "${route}" )
    done < <(native-edge-routes)

    native-edge-trust || return
    haproxy-render "${directory}" "${routes[@]}" || return

    if [[ -n "${sockets}" ]]; then
        mounts=$'\n'"      - type: bind"$'\n'"        source: $(parse-json-string "${sockets}")"$'\n'"        target: /sockets"
    else
        published+=( "${address}:${CONFIG[HTTP_PORT]}:8080/tcp" )
        ! cfg-true TLS_ENABLED || published+=( "${address}:${CONFIG[HTTPS_PORT]}:8443/tcp" )
        ! haproxy-quic || published+=( "${address}:${CONFIG[HTTPS_PORT]}:8443/udp" )
    fi

    ! cfg-true METRICS_ENABLED || published+=( "127.0.0.1:${CONFIG[METRICS_PORT]}:9090/tcp" )

    for port in "${published[@]}"; do
        ports+="${ports:+, }$(parse-json-string "${port}")"
    done

    cfg-set EDGE_ROOT "${CONFIG[STATE_ROOT]}/edge"
    cfg-set EDGE_PORTS "[${ports}]"
    cfg-set EDGE_MOUNTS "${mounts}"

    template-render "${MANIFEST[paths.templates]}/native/edge.yaml.tpl" "${directory}/edge.yaml"

}
native-edge-trust () {

    local ranges="${CONFIG[TRUSTED_PROXIES]}"

    if native-edge-listed; then
        ranges="$(native-edge-recorded)" || ranges="$(native-edge-ranges)" || return
    fi

    cfg-set TRUSTED_RANGES "${ranges}"

}
native-edge-listed () {

    [[ " ${CONFIG[TRUSTED_PROXIES]} " == *" https://"* ]]

}
native-edge-recorded () {

    local root="${CONFIG[STATE_ROOT]}" source="" ranges=""

    source="$(state-read "${root}" trusted-proxies 2>/dev/null)" && [[ "${source}" == "${CONFIG[TRUSTED_PROXIES]}" ]] || return 1
    ranges="$(state-read "${root}" trusted-ranges 2>/dev/null)" && [[ -n "${ranges}" ]] || return 1

    out "${ranges}"

}
native-edge-ranges () {

    local item="" found="" ranges=""
    local -a items=()

    read -r -a items <<< "${CONFIG[TRUSTED_PROXIES]}"

    for item in "${items[@]}"; do
        if [[ "${item}" == https://* ]]; then
            found="$(native-edge-fetch "${item}")" || return
            ranges+="${ranges:+ }${found}"
        else
            ranges+="${ranges:+ }${item}"
        fi
    done

    state-write "${CONFIG[STATE_ROOT]}" trusted-ranges "${ranges}" || return
    state-write "${CONFIG[STATE_ROOT]}" trusted-proxies "${CONFIG[TRUSTED_PROXIES]}" || return

    out "${ranges}"

}
native-edge-fetch () {

    local url="${1}" body="" range="" status=0
    local -a ranges=()

    body="$(fs-temp-file)" || return
    net-request GET "${url}" "${body}" 2>/dev/null || status=1
    (( status != 0 )) || mapfile -t ranges < <(grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}|[0-9A-Fa-f]{0,4}(:[0-9A-Fa-f]{0,4}){2,7}/[0-9]{1,3}' "${body}" | sort -u)
    rm -f -- "${body}"

    (( status == 0 && ${#ranges[@]} > 0 )) || { err "Trusted proxy ranges unreachable or empty: ${url}"; return; }

    for range in "${ranges[@]}"; do
        parse-cidr "${range}" || { err "Unexpected range from ${url}: ${range}"; return; }
    done

    out "${ranges[*]}"

}
native-edge-refresh () {

    native-edge-listed || return 0
    native-edge-ranges >/dev/null || warn "Keeping the recorded trusted proxy ranges"

}
native-edge-sockets () {

    local sockets="${CONFIG[EDGE_SOCKETS]}"

    [[ -n "${sockets}" ]] || return 0
    [[ -d "${sockets}" ]] || { err "EDGE_SOCKETS ${sockets} is missing; run: $(native-edge-grant)"; return; }

    docker-oneshot --user 1000:1000 --entrypoint sh --mount "type=bind,source=${sockets},target=/sockets" -- "${CONFIG[IMAGE_HAPROXY]}" \
        -c 'touch /sockets/.infra-probe && rm -f /sockets/.infra-probe' >/dev/null 2>&1 ||
        { err "The edge runs as uid 1000 and cannot write ${sockets}; run: $(native-edge-grant)"; return; }

}
native-edge-grant () {

    local sockets="${CONFIG[EDGE_SOCKETS]}" owner=1000 start=""

    if docker-rootless 2>/dev/null; then
        start="$(awk -F: -v name="$(id -un)" -v id="$(id -u)" '$1 == name || $1 == id { print $2; exit }' /etc/subuid 2>/dev/null)" || start=""
        [[ ! "${start}" =~ ^[0-9]+$ ]] || owner=$(( start + 999 ))
    fi

    out "sudo mkdir -p ${sockets} && sudo setfacl -m u:${owner}:rwx ${sockets}"

}
native-edge-curl () {

    local socket="${1}"
    local -a flags=() arguments=()

    shift

    if [[ -n "${CONFIG[HEALTH_CA]}" ]]; then
        flags+=( --mount "type=bind,source=${CONFIG[HEALTH_CA]},target=/run/health-ca.pem,readonly" )
        arguments+=( --cacert /run/health-ca.pem )
    fi

    docker-oneshot --user 1000:1000 --memory 64m "${flags[@]}" --mount "type=bind,source=${CONFIG[EDGE_SOCKETS]},target=/sockets,readonly" -- "${CONFIG[IMAGE_CURL]}" \
        --disable --silent --show-error --max-time 5 --unix-socket "/sockets/${socket}" --haproxy-protocol "${arguments[@]}" "$@"

}
native-edge-candidate () {

    local root="${CONFIG[STATE_ROOT]}" next="${CONFIG[STATE_ROOT]}/edge-next"

    native-edge-render "${next}" || return
    fs-copy "${root}/edge/active.map" "${next}/active.map" 644 || return
    haproxy-check "${next}" "${CONFIG[COMPOSE_PROJECT]}-tls"

}
native-edge-same () {

    local live="${CONFIG[STATE_ROOT]}/edge" next="${CONFIG[STATE_ROOT]}/edge-next" file=""

    for file in haproxy.cfg edge.yaml; do
        [[ -f "${live}/${file}" && "$(fs-hash "${live}/${file}")" == "$(fs-hash "${next}/${file}")" ]] || return 1
    done

}
native-edge-preflight () {

    [[ -f "${CONFIG[STATE_ROOT]}/edge/haproxy.cfg" ]] || return 0

    native-edge-candidate || return
    native-edge-same || { err "Edge settings changed; run edge apply before deploying"; return; }

}
native-edge-prepare () {

    local root="${CONFIG[STATE_ROOT]}" live="${CONFIG[STATE_ROOT]}/edge" current="" slot="" running=""

    fs-dir "${live}" 755 || return
    haproxy-features || return
    native-edge-sockets || return
    native-edge-refresh

    if [[ ! -f "${live}/active.map" ]]; then
        current="$(state-read "${root}" current 2>/dev/null)" || current=none
        slot="$(state-read "${root}" active-slot 2>/dev/null)" || slot=unavailable
        [[ -n "${current}" && "${slot}" != none ]] || { current=none; slot=unavailable; }
        printf 'active %s:%s\n' "${slot}" "${current}" | fs-write "${live}/active.map" 644 || return
    fi

    native-dns-sync

    if cfg-true TLS_ENABLED && ! tls-present; then
        if [[ "${CONFIG[TLS_CHALLENGE]}" == dns ]]; then native-certificate || return
        else native-edge-bootstrap || return
        fi
    fi

    native-edge-candidate || return

    if [[ -f "${live}/haproxy.cfg" ]]; then
        native-edge-same || { err "Edge settings changed; run edge apply before deploying"; return; }
    else
        fs-copy "${root}/edge-next/haproxy.cfg" "${live}/haproxy.cfg" 644 || return
        fs-copy "${root}/edge-next/edge.yaml" "${live}/edge.yaml" || return
    fi

    running="$(native-compose-edge ps -q edge)" || return
    [[ -n "${running}" ]] || native-compose-edge up -d edge || return

    run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive || { err "Edge did not become healthy"; return; }
    native-certificate-converge

}
native-edge-alive () {

    local container=""

    container="$(native-edge-container 2>/dev/null)" || return 1

    docker-health "${container}"

}
native-edge-bootstrap () {

    local live="${CONFIG[STATE_ROOT]}/edge" current="" quic="${CONFIG[HTTP3_ENABLED]}" status=0

    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""
    [[ -z "${current}" ]] || { err "The live edge lost its certificate; restore it or run tls import"; return; }

    cfg-set TLS_ENABLED false
    cfg-set HTTP3_ENABLED false

    if native-edge-render "${live}" && haproxy-check "${live}" "${CONFIG[COMPOSE_PROJECT]}-tls" && native-compose-edge up -d edge &&
        run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive; then
        native-certificate || status=$?
    else
        status=1
    fi

    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED "${quic}"
    (( status == 0 )) || { err "Initial certificate issuance failed"; return; }

    native-edge-render "${live}" || return
    haproxy-check "${live}" "${CONFIG[COMPOSE_PROJECT]}-tls" || return
    native-compose-edge up -d edge

}
native-certificate () {

    local -a hosts=()

    mapfile -t hosts < <(native-hosts)

    tls-issue "${hosts[@]}" || return
    state-write "${CONFIG[STATE_ROOT]}" certificate "$(native-certificate-names)"

}
native-certificate-names () {

    native-hosts | LC_ALL=C sort | paste -sd ' ' -

}
native-certificate-converge () {

    local recorded="" wanted=""

    cfg-true TLS_ENABLED || return 0
    recorded="$(state-read "${CONFIG[STATE_ROOT]}" certificate 2>/dev/null)" || return 0
    wanted="$(native-certificate-names)" || return
    [[ "${recorded}" != "${wanted}" ]] || return 0

    info "Certificate names changed; issuing for ${wanted}"
    native-certificate || return
    native-edge-reload

}
native-edge-apply () {

    config-validate || return
    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-edge-apply-locked

}
native-edge-apply-locked () {

    local root="${CONFIG[STATE_ROOT]}" live="${CONFIG[STATE_ROOT]}/edge" backup="${CONFIG[STATE_ROOT]}/edge-previous" recreate=false

    if [[ ! -f "${live}/haproxy.cfg" ]]; then
        native-networks && tls-volumes && native-edge-prepare || return
        ui-result edge-apply true safe
        return
    fi

    native-dns-sync
    native-edge-sockets || return
    native-edge-refresh
    native-edge-candidate || return
    native-edge-same && { native-certificate-converge || return; ui-result edge-apply false safe; return; }
    native-edge-readiness || return

    fs-dir "${backup}" 755 || return
    fs-copy "${live}/haproxy.cfg" "${backup}/haproxy.cfg" 644 || return
    fs-copy "${live}/edge.yaml" "${backup}/edge.yaml" || return

    [[ "$(fs-hash "${live}/edge.yaml")" == "$(fs-hash "${root}/edge-next/edge.yaml")" ]] || recreate=true

    fs-copy "${root}/edge-next/haproxy.cfg" "${live}/haproxy.cfg" 644 || return
    fs-copy "${root}/edge-next/edge.yaml" "${live}/edge.yaml" || return

    if [[ "${recreate}" == true ]]; then
        warn "Edge ports or container settings changed; recreating the edge interrupts open connections"
        native-compose-edge up -d edge && run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive && { native-edge-applied; return; }
    else
        native-edge-reload && run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive && { native-edge-applied; return; }
    fi

    warn "Edge update failed; restoring the previous edge"
    fs-copy "${backup}/haproxy.cfg" "${live}/haproxy.cfg" 644 || return
    fs-copy "${backup}/edge.yaml" "${live}/edge.yaml" || return

    if [[ "${recreate}" == true ]]; then native-compose-edge up -d edge || return
    else native-edge-reload || return
    fi

    native-announce edge.rolled-back "an edge change failed its health check and the previous edge was restored"
    err "Edge update rolled back"

}
native-edge-readiness () {

    local current="" directory="" key="" changed=""
    local -A pinned=()

    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || return 0
    [[ -n "${current}" ]] || return 0
    directory="$(native-directory "${current}")" || return
    [[ -f "${directory}/release.env" ]] || return 0
    parse-pairs pinned "${directory}/release.env" || return

    for key in API_READY_PATH API_PORT WEB_READY_PATH WEB_PORT; do
        [[ -z "${pinned[${key}]+x}" || "${pinned[${key}]}" == "${CONFIG[${key}]}" ]] || changed+="${changed:+, }${key} from ${pinned[${key}]} to ${CONFIG[${key}]}"
    done

    [[ -n "${changed}" ]] || return 0
    ! cli-flag --force || { warn "${changed}: ${current} fails its health checks until a release serving the new values switches in"; return 0; }

    err "${changed} while ${current} is live, which fails its health checks from this edge apply until a release serving the new values switches in; ship a release that serves both first, or accept the gap with infra edge apply --force"

}
native-edge-applied () {

    native-certificate-converge || return
    ui-result edge-apply true safe

}
native-edge-reload () {

    local container=""

    container="$(native-edge-container)" || return
    haproxy-check "${CONFIG[STATE_ROOT]}/edge" "${CONFIG[COMPOSE_PROJECT]}-tls" || return

    docker kill --signal USR2 "${container}" >/dev/null || { err "Edge reload signal failed"; return; }

}
native-select () {

    local slot="${1}" release="${2}" container=""

    container="$(native-edge-container)" || return

    haproxy-select "${container}" "${slot}" "${release}" "${CONFIG[STATE_ROOT]}/edge/active.map"

}

native-probe-candidate () {

    local container="" stats="" service="" replicas="" up="" route="" name="" host="" port="" path="" scheme=http front=8081
    local -a flags=() arguments=( --fail --silent --show-error --max-time 5 --noproxy '*' --header "X-Slot: ${CONFIG[DEPLOY_SLOT]}" )

    container="$(native-edge-container)" || return
    stats="$(haproxy-stats "${container}")" || return

    while IFS= read -r service; do
        replicas="$(native-replicas "${service}")" || return
        up="$(haproxy-up "${stats}" "${service}_${CONFIG[DEPLOY_SLOT]}")" || return
        [[ "${up}" == "${replicas}" ]] || return 1
    done < <(native-services)

    if cfg-true TLS_ENABLED; then
        scheme=https
        front=8444
    fi

    if [[ -n "${CONFIG[HEALTH_CA]}" ]]; then
        flags+=( --mount "type=bind,source=${CONFIG[HEALTH_CA]},target=/run/health-ca.pem,readonly" )
        arguments+=( --cacert /run/health-ca.pem )
    fi

    while IFS='|' read -r name host port path _ _; do
        docker-oneshot --network "${CONFIG[COMPOSE_PROJECT]}-apps" --memory 64m "${flags[@]}" -- "${CONFIG[IMAGE_CURL]}" \
            "${arguments[@]}" --connect-to "${host}:${front}:edge:${front}" --output /dev/null "${scheme}://${host}:${front}${path}" || return 1
    done < <(native-routes)

}
native-probe-public () {

    local url="${CONFIG[EXTERNAL_HEALTH_URL]}" address="${CONFIG[BIND_ADDRESS]}" port="${CONFIG[HTTP_PORT]}" scheme=http
    local -a arguments=()

    [[ -n "${url}" || -z "${CONFIG[EDGE_SOCKETS]}" ]] || { native-probe-socket; return; }
    [[ -z "${CONFIG[HEALTH_CA]}" ]] || arguments+=( --cacert "${CONFIG[HEALTH_CA]}" )

    if [[ -z "${url}" ]]; then
        [[ "${address}" != 0.0.0.0 ]] || address=127.0.0.1
        if cfg-true TLS_ENABLED; then
            scheme=https
            port="${CONFIG[HTTPS_PORT]}"
        fi
        url="${scheme}://${CONFIG[API_HOST]}:${port}${CONFIG[API_READY_PATH]}"
        arguments+=( --resolve "${CONFIG[API_HOST]}:${port}:${address}" )
    fi

    net-header "${url}" X-Release "${CONFIG[RELEASE]}" "${arguments[@]}"

}
native-probe-socket () {

    local socket=http.sock scheme=http headers=""

    if cfg-true TLS_ENABLED; then
        socket=https.sock
        scheme=https
    fi

    headers="$(native-edge-curl "${socket}" --fail --dump-header - --output /dev/null "${scheme}://${CONFIG[API_HOST]}${CONFIG[API_READY_PATH]}" 2>/dev/null)" || return 1

    net-header-has "${headers}" X-Release "${CONFIG[RELEASE]}"

}
native-edge () {

    native-dispatch edge "$@"

}
