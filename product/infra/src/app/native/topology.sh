source-include module/docker.sh || return
source-include module/haproxy.sh || return

native-parts () {

    local name=""
    local -a parts=()

    read -r -a parts <<< "${CONFIG[PARTS]:-}"

    for name in "${parts[@]}"; do
        out "${name}"
    done

}
native-server-part () {

    local name=""

    while IFS= read -r name; do
        [[ "${CONFIG[${name^^}_KIND]:-}" != server ]] || { out "${name}"; return; }
    done < <(native-parts)

    return 1

}
native-primary () {

    local name=""
    local -a names=()

    ! name="$(native-server-part)" || names+=( "${name}" )
    mapfile -t -O "${#names[@]}" names < <(native-parts)

    for name in "${names[@]}"; do
        [[ -z "$(config-first "${CONFIG[${name^^}_DOMAIN]:-}")" ]] || { out "${name}"; return; }
    done

    return 1

}
native-roles () {

    [[ -f "$(native-directory "${1}")/part-$(config-server).yaml" ]]

}
native-routed () {

    local name=""
    local -a parts=()

    read -r -a parts <<< "${CONFIG[ROUTED]:-}"

    for name in "${parts[@]}"; do
        out "${name}"
    done

}
native-replicas () {

    out "${CONFIG[${1^^}_REPLICAS]:-1}"

}
native-service-image () {

    out "${CONFIG[${1^^}_IMAGE]:-}"

}
native-domains-of () {

    local listed=""

    listed="$(config-list "${CONFIG[${1^^}_DOMAIN]:-}")" || return

    out "${listed//$'\n'/ }"

}
native-routes () {

    local name="" prefix="" listed=""
    local -a parts=()

    read -r -a parts <<< "${CONFIG[ROUTED]:-}"
    ! config-domains-on || parts=( "${CONFIG_PARTS[@]}" )

    for name in "${parts[@]}"; do
        prefix="${name^^}"
        listed="$(native-domains-of "${name}")" || return
        out "${name}|${listed}|${CONFIG[${prefix}_PORT]}|${CONFIG[${prefix}_PATH]}|${CONFIG[${prefix}_READY]}|${CONFIG[${prefix}_BALANCE]}|${CONFIG[${prefix}_EXPECT]}|${CONFIG[${prefix}_LIMIT]}|slot"
    done

}
native-edge-routes () {

    local listed=""

    native-routes || return
    listed="$(config-list "${CONFIG[GRAFANA_DOMAIN]}")" || return
    [[ -z "${listed}" ]] || out "grafana|${listed//$'\n'/ }|3000|/|/api/health|roundrobin|200||static"

}
native-domains () {

    local scope="${1:-all}" route="" domain=""
    local -a domains=()
    local -A seen=()

    while IFS='|' read -r _ route _; do
        read -r -a domains <<< "${route}"
        for domain in "${domains[@]}"; do
            [[ -z "${seen[${domain}]:-}" ]] || continue
            seen["${domain}"]=1
            out "${domain}"
        done
    done < <(native-edge-routes)

    [[ "${scope}" == all ]] && config-domains-on && [[ -f "${CONFIG[STATE_ROOT]}/edge/domains.wanted" ]] || return 0

    while read -r domain _; do
        [[ -z "${domain}" || -n "${seen[${domain}]:-}" ]] || out "${domain}"
    done < "${CONFIG[STATE_ROOT]}/edge/domains.wanted"

}
native-slot () {

    local release="${1}" slot=""

    for slot in blue green; do
        [[ "$(state-read "${CONFIG[STATE_ROOT]}" "slot-${slot}" 2>/dev/null)" != "${release}" ]] || { out "${slot}"; return; }
    done

    out "${CONFIG[DEPLOY_SLOT]}"

}
native-interpolation () {

    local release="${1}" file="" name="" directory="" slot=""

    directory="$(native-directory "${release}")" || return
    slot="$(native-slot "${release}")" || return

    out "WORKER_REPLICAS=${CONFIG[WORKER_REPLICAS]}" "DEPLOY_SLOT=${slot}" "RELEASE_ROOT=${directory}"

    for file in "${directory}"/part-*.yaml; do
        [[ -f "${file}" ]] || continue
        name="${file##*/part-}"
        name="${name%.yaml}"
        out "${name^^}_REPLICAS=$(native-replicas "${name}")"
    done

}
native-compose-files () {

    local directory="${1}" file="" found=0

    for file in "${directory}"/part-*.yaml; do
        [[ -f "${file}" ]] || continue
        out -f "${file}"
        found=1
    done

    (( found == 1 )) || { err "No part Compose files in ${directory}"; return; }

}
native-compose-app () {

    local release="${1}" directory="" pair=""
    local -a variables=() files=()

    shift
    directory="$(native-directory "${release}")" || return
    mapfile -t files < <(native-compose-files "${directory}")
    (( ${#files[@]} > 0 )) || { err "Release ${release} has no part Compose files"; return; }

    while IFS= read -r pair; do
        variables+=( "${pair}" )
    done < <(native-interpolation "${release}")

    (
        for pair in "${variables[@]}"; do
            export "${pair?}"
        done

        docker-compose "${CONFIG[COMPOSE_PROJECT]}-${release}" "${files[@]}" "$@"
    )

}
native-compose-data () {

    docker-compose "${CONFIG[COMPOSE_PROJECT]}-data" -f "${CONFIG[STATE_ROOT]}/data/data.yaml" "$@"

}
native-compose-models () {

    local file=""
    local -a files=()

    for file in "${CONFIG[STATE_ROOT]}"/models/model-*.yaml; do
        [[ ! -f "${file}" ]] || files+=( -f "${file}" )
    done

    docker-compose "${CONFIG[COMPOSE_PROJECT]}-models" "${files[@]}" "$@"

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
    done < <(native-parts)

}
native-data-healthy () {

    local service="" container=""

    while IFS= read -r service; do
        container="$(native-compose-data ps -q "${service}")" || return 1
        [[ -n "${container}" ]] && docker-health "${container}" || return 1
    done < <(config-data-services)

}
native-wait-data () {

    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 native-data-healthy || { err "Data services did not become healthy"; return; }

}
