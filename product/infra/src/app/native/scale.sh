source-include module/docker.sh || return
source-include module/haproxy.sh || return

native-scale () {

    config-validate || return
    docker-ready || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-scale-locked

}
native-scale-locked () {

    local root="${CONFIG[STATE_ROOT]}" key="" service="" expected="" entry="" summary="" status=0
    local -a drained=() keys=( WORKER_REPLICAS )
    local -A counts=()

    [[ -z "$(state-read "${root}" pending 2>/dev/null || true)" ]] || { err "Finish or reject the pending release before scaling"; return; }

    for service in "${CONFIG_PARTS[@]}"; do
        keys+=( "${service^^}_REPLICAS" )
    done

    for key in "${keys[@]}"; do
        counts["${key}"]="${CONFIG[${key}]}"
    done

    native-current || return

    for key in "${keys[@]}"; do
        cfg-set "${key}" "${counts[${key}]}"
    done

    config-check workers WORKER_REPLICAS || return
    config-check replicas "${keys[@]:1}" || return

    while IFS= read -r service; do
        expected="$(native-replicas "${service}")" || return
        summary+="${service}=${expected} "
        native-drain-excess "${service}" "${expected}" drained || { status=1; break; }
    done < <(native-parts)

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
    native-announce scale.applied "${CONFIG[RELEASE]} now runs ${summary}workers=${CONFIG[WORKER_REPLICAS]}"
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
