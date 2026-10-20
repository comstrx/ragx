source-include module/docker.sh || return
source-include module/haproxy.sh || return

native-scale () {

    config-validate || return
    docker-ready || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-scale-locked

}
native-scale-locked () {

    local root="${CONFIG[STATE_ROOT]}" api="${CONFIG[API_REPLICAS]}" web="${CONFIG[WEB_REPLICAS]}" workers="${CONFIG[WORKER_REPLICAS]}"
    local service="" expected="" entry="" status=0
    local -a drained=()

    [[ -z "$(state-read "${root}" pending 2>/dev/null || true)" ]] || { err "Finish or reject the pending release before scaling"; return; }
    native-current || return

    cfg-set API_REPLICAS "${api}"
    cfg-set WEB_REPLICAS "${web}"
    cfg-set WORKER_REPLICAS "${workers}"
    config-web || return

    while IFS= read -r service; do
        expected="$(native-replicas "${service}")" || return
        native-drain-excess "${service}" "${expected}" drained || { status=1; break; }
    done < <(native-services)

    (( status != 0 )) || native-front-start "${CONFIG[RELEASE]}" || status=$?

    for entry in "${drained[@]}"; do
        haproxy-state "$(native-edge-container)" "${entry%/*}" "${entry#*/}" ready 2>/dev/null || true
    done

    (( status == 0 )) || return "${status}"

    native-wait-app "${CONFIG[RELEASE]}" || return
    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 native-probe-candidate || { err "Scaled replicas did not join the edge"; return; }
    native-background-start "${CONFIG[RELEASE]}" || return
    native-probe-public || return

    state-audit "${root}" "${CONFIG[RELEASE]}" scaled || return
    native-announce scale.applied "${CONFIG[RELEASE]} now runs api=${CONFIG[API_REPLICAS]} workers=${CONFIG[WORKER_REPLICAS]}${CONFIG[WEB_REPLICAS]:+ web=${CONFIG[WEB_REPLICAS]}}"
    ui-result scale true safe

}
native-drain-excess () {

    local service="${1}" expected="${2}" container="" index="" address="" stats="" server="" backend="${1}_${CONFIG[DEPLOY_SLOT]}" edge=""
    local -n _drained="${3}"
    local -a containers=() targets=()

    while IFS= read -r container; do
        [[ -z "${container}" ]] || containers+=( "${container}" )
    done < <(native-compose-app "${CONFIG[RELEASE]}" ps -q "${service}")

    (( ${#containers[@]} > expected )) || return 0

    edge="$(native-edge-container)" || return
    stats="$(haproxy-stats "${edge}")" || return

    for container in "${containers[@]}"; do

        index="$(docker-inspect "${container}" '{{index .Config.Labels "com.docker.compose.container-number"}}')" || return
        (( index > expected )) || continue

        address="$(docker-inspect "${container}" "{{(index .NetworkSettings.Networks \"${CONFIG[COMPOSE_PROJECT]}-apps\").IPAddress}}")" || return
        server="$(haproxy-server "${stats}" "${backend}" "${address}")" || { err "HAProxy has not discovered ${service} replica ${index} yet"; return; }

        haproxy-state "${edge}" "${backend}" "${server}" drain || return
        _drained+=( "${backend}/${server}" )
        targets+=( "${server}" )

    done

    for server in "${targets[@]}"; do
        run-until "${CONFIG[DRAIN_TIMEOUT]}" 1 haproxy-idle "${edge}" "${backend}" "${server}" || { err "Sessions on ${backend}/${server} outlived the drain window; nothing was removed"; return; }
    done

}
