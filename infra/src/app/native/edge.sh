source-include module/docker.sh || return
source-include module/haproxy.sh || return
source-include module/tls.sh || return

native-edge-render () {

    local directory="${1}" route="" ports=""
    local -a routes=()

    while IFS= read -r route; do
        routes+=( "${route}" )
    done < <(native-routes)

    haproxy-render "${directory}" "${routes[@]}" || return

    ports="      - $(parse-json-string "${CONFIG[BIND_ADDRESS]}:${CONFIG[HTTP_PORT]}:8080/tcp")"

    if cfg-true TLS_ENABLED; then
        ports+=$'\n'"      - $(parse-json-string "${CONFIG[BIND_ADDRESS]}:${CONFIG[HTTPS_PORT]}:8443/tcp")"
        ! cfg-true HTTP3_ENABLED || ports+=$'\n'"      - $(parse-json-string "${CONFIG[BIND_ADDRESS]}:${CONFIG[HTTPS_PORT]}:8443/udp")"
    fi

    ! cfg-true METRICS_ENABLED || ports+=$'\n'"      - $(parse-json-string "127.0.0.1:${CONFIG[METRICS_PORT]}:9090/tcp")"

    cfg-set EDGE_ROOT "${CONFIG[STATE_ROOT]}/edge"
    cfg-set EDGE_PORTS "${ports}"

    template-render "${MANIFEST[paths.templates]}/native/edge.yaml.tpl" "${directory}/edge.yaml"

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

    if [[ ! -f "${live}/active.map" ]]; then
        current="$(state-read "${root}" current 2>/dev/null)" || current=none
        slot="$(state-read "${root}" active-slot 2>/dev/null)" || slot=unavailable
        [[ -n "${current}" && "${slot}" != none ]] || { current=none; slot=unavailable; }
        printf 'active %s:%s\n' "${slot}" "${current}" | fs-write "${live}/active.map" 644 || return
    fi

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

    tls-issue "${hosts[@]}"

}
native-edge-apply () {

    config-validate || return
    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-edge-apply-locked

}
native-edge-apply-locked () {

    local root="${CONFIG[STATE_ROOT]}" live="${CONFIG[STATE_ROOT]}/edge" backup="${CONFIG[STATE_ROOT]}/edge-previous" recreate=false

    [[ -f "${live}/haproxy.cfg" ]] || { native-edge-prepare; return; }

    native-edge-candidate || return
    native-edge-same && { ui-result edge-apply false safe; return; }

    fs-dir "${backup}" 755 || return
    fs-copy "${live}/haproxy.cfg" "${backup}/haproxy.cfg" 644 || return
    fs-copy "${live}/edge.yaml" "${backup}/edge.yaml" || return

    [[ "$(fs-hash "${live}/edge.yaml")" == "$(fs-hash "${root}/edge-next/edge.yaml")" ]] || recreate=true

    fs-copy "${root}/edge-next/haproxy.cfg" "${live}/haproxy.cfg" 644 || return
    fs-copy "${root}/edge-next/edge.yaml" "${live}/edge.yaml" || return

    if [[ "${recreate}" == true ]]; then
        warn "Edge ports or container settings changed; recreating the edge interrupts open connections"
        native-compose-edge up -d edge && run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive && { ui-result edge-apply true safe; return; }
    else
        native-edge-reload && run-until "${CONFIG[HEALTH_TIMEOUT]}" 1 native-edge-alive && { ui-result edge-apply true safe; return; }
    fi

    warn "Edge update failed; restoring the previous edge"
    fs-copy "${backup}/haproxy.cfg" "${live}/haproxy.cfg" 644 || return
    fs-copy "${backup}/edge.yaml" "${live}/edge.yaml" || return

    if [[ "${recreate}" == true ]]; then native-compose-edge up -d edge || return
    else native-edge-reload || return
    fi

    err "Edge update rolled back"

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

    [[ -z "${CONFIG[HEALTH_CA]}" ]] || arguments+=( --cacert "${CONFIG[HEALTH_CA]}" )

    if [[ -z "${url}" && "${CONFIG[DEPLOY_ENV]}" == production ]]; then
        url="${CONFIG[API_URL]}${CONFIG[API_READY_PATH]}"
    elif [[ -z "${url}" ]]; then
        [[ "${address}" != 0.0.0.0 ]] || address=127.0.0.1
        cfg-true TLS_ENABLED && { scheme=https; port="${CONFIG[HTTPS_PORT]}"; }
        url="${scheme}://${CONFIG[API_HOST]}:${port}${CONFIG[API_READY_PATH]}"
        arguments+=( --resolve "${CONFIG[API_HOST]}:${port}:${address}" )
    fi

    net-header "${url}" X-Release "${CONFIG[RELEASE]}" "${arguments[@]}"

}
