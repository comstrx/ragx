source-include module/docker.sh || return
source-include module/haproxy.sh || return

native-specs () {

    local -A images=()

    parse-map images "${CONFIG[WEB_IMAGES]}" || return
    (( ${#images[@]} > 0 )) || return 0

    printf '%s\n' "${!images[@]}" | LC_ALL=C sort

}
native-services () {

    local spec=""

    out api

    while IFS= read -r spec; do
        [[ -z "${spec}" ]] || out "web-${spec}"
    done < <(native-specs)

}
native-variable () {

    local name="${1^^}"

    out "WEB_${name//-/_}_REPLICAS"

}
native-replicas () {

    local service="${1}"
    local -A counts=()

    [[ "${service}" != api ]] || { out "${CONFIG[API_REPLICAS]}"; return; }
    parse-map counts "${CONFIG[WEB_REPLICAS]}" || return

    out "${counts[${service#web-}]:-2}"

}
native-service-image () {

    local service="${1}"
    local -A images=()

    [[ "${service}" != api ]] || { out "${CONFIG[API_IMAGE]}"; return; }
    parse-map images "${CONFIG[WEB_IMAGES]}" || return

    out "${images[${service#web-}]}"

}
native-host () {

    local service="${1}"
    local -A hosts=()

    [[ "${service}" != api ]] || { out "${CONFIG[API_HOST]}"; return; }
    parse-map hosts "${CONFIG[WEB_HOSTS]}" || return

    out "${hosts[${service#web-}]}"

}
native-routes () {

    local service="" host=""

    while IFS= read -r service; do

        host="$(native-host "${service}")" || return

        if [[ "${service}" == api ]]; then out "api|${host}|${CONFIG[API_PORT]}|${CONFIG[API_READY_PATH]}|${CONFIG[API_BALANCE]}|200"
        else out "${service}|${host}|${CONFIG[WEB_PORT]}|${CONFIG[WEB_READY_PATH]}|${CONFIG[WEB_BALANCE]}|200-399"
        fi

    done < <(native-services)

}
native-edge-routes () {

    native-routes || return
    [[ -z "${CONFIG[GRAFANA_HOST]}" ]] || out "grafana|${CONFIG[GRAFANA_HOST]}|3000|/api/health|roundrobin|200|static"

}
native-hosts () {

    local service=""

    while IFS= read -r service; do
        native-host "${service}" || return
    done < <(native-services)

    [[ -z "${CONFIG[GRAFANA_HOST]}" ]] || out "${CONFIG[GRAFANA_HOST]}"

}
native-slot () {

    local release="${1}" slot=""

    for slot in blue green; do
        [[ "$(state-read "${CONFIG[STATE_ROOT]}" "slot-${slot}" 2>/dev/null)" != "${release}" ]] || { out "${slot}"; return; }
    done

    out "${CONFIG[DEPLOY_SLOT]}"

}
native-interpolation () {

    local release="${1}" spec="" directory="" slot=""

    directory="$(native-directory "${release}")" || return
    slot="$(native-slot "${release}")" || return

    out "API_REPLICAS=${CONFIG[API_REPLICAS]}" "WORKER_REPLICAS=${CONFIG[WORKER_REPLICAS]}"
    out "DEPLOY_SLOT=${slot}" "RELEASE_ROOT=${directory}"

    while IFS= read -r spec; do
        [[ -z "${spec}" ]] || out "$(native-variable "${spec}")=$(native-replicas "web-${spec}")"
    done < <(native-specs)

}

native-compose-app () {

    local release="${1}" directory="" pair=""
    local -a variables=()

    shift
    directory="$(native-directory "${release}")" || return

    while IFS= read -r pair; do
        variables+=( "${pair}" )
    done < <(native-interpolation "${release}")

    (
        for pair in "${variables[@]}"; do
            export "${pair?}"
        done

        docker-compose "${CONFIG[COMPOSE_PROJECT]}-${release}" -f "${directory}/application.yaml" -f "${directory}/web.yaml" "$@"
    )

}
native-compose-data () {

    docker-compose "${CONFIG[COMPOSE_PROJECT]}-data" -f "${CONFIG[STATE_ROOT]}/data/data.yaml" "$@"

}
native-compose-edge () {

    docker-compose "${CONFIG[COMPOSE_PROJECT]}-edge" -f "${CONFIG[STATE_ROOT]}/edge/edge.yaml" "$@"

}
native-edge-container () {

    local container=""

    container="$(native-compose-edge ps -q edge)" || return
    [[ -n "${container}" ]] || { err "Edge container is not running"; return; }

    out "${container}"

}

native-healthy () {

    local release="${1}" service="${2}" expected="${3}" image="" container="" actual="" count=0

    image="$(native-service-image "${service}")" || return

    while IFS= read -r container; do
        [[ -n "${container}" ]] || continue
        docker-health "${container}" || return 1
        actual="$(docker-inspect "${container}" '{{.Config.Image}}')" || return 1
        [[ "${actual}" == "${image}" ]] || return 1
        count=$(( count + 1 ))
    done < <(native-compose-app "${release}" ps -q "${service}")

    (( count == expected ))

}
native-wait-app () {

    local release="${1}" service="" replicas=""

    while IFS= read -r service; do
        replicas="$(native-replicas "${service}")" || return
        run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 native-healthy "${release}" "${service}" "${replicas}" || { err "${service} did not reach ${replicas} healthy replicas"; return; }
    done < <(native-services)

}
native-data-healthy () {

    local service="" container=""

    for service in postgres rabbitmq redis; do
        container="$(native-compose-data ps -q "${service}")" || return 1
        [[ -n "${container}" ]] && docker-health "${container}" || return 1
    done

}
native-wait-data () {

    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 native-data-healthy || { err "Data services did not become healthy"; return; }

}
