source-include module/docker.sh || return
source-include module/haproxy.sh || return
source-include module/portainer.sh || return
source-include module/tls.sh || return

native-deploy () {

    if [[ "${CONFIG[DEPLOY_DRIVER]}" == portainer && -z "${CONFIG[GITOPS_COMMIT]:-}" ]]; then
        native-reconcile
        return
    fi

    config-validate || return
    config-required || return
    native-runtime || return
    docker-ready || return
    [[ "${CONFIG[DEPLOY_ENV]}" != production ]] || docker-versions || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-converge

}
native-converge () {

    local root="${CONFIG[STATE_ROOT]}" release="${CONFIG[RELEASE]}" pending="" current="" active="" slot="" origin="" directory="" status=0

    pending="$(state-read "${root}" pending 2>/dev/null)" || pending=""
    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    active="$(state-read "${root}" active-slot 2>/dev/null)" || active=""

    [[ -z "${pending}" || "${pending}" == "${release}" ]] || { err "Release ${pending} is pending; finish it with deploy or reject it with rollback"; return; }

    if [[ "${current}" == "${release}" && -z "${pending}" ]]; then
        cfg-set DEPLOY_SLOT "${active}" state
        native-release-match "$(native-directory "${release}")" || return
        native-probe-public || return
        ui-result deploy false safe
        return
    fi

    if [[ -z "${pending}" ]]; then

        native-edge-preflight || return

        slot=blue
        [[ "${active}" != blue ]] || slot=green

        native-retire "${slot}" || return
        state-write "${root}" origin "${current}" || return
        state-write "${root}" origin-slot "${active:-none}" || return
        state-write "${root}" origin-previous "$(state-read "${root}" previous 2>/dev/null || true)" || return
        state-write "${root}" pending-slot "${slot}" || return
        state-write "${root}" pending "${release}" || return

    fi

    origin="$(state-read "${root}" origin)" || return
    slot="$(state-read "${root}" pending-slot)" || return
    cfg-set DEPLOY_SLOT "${slot}" state

    directory="$(native-render)" || return
    state-write "${root}" "slot-${slot}" "${release}" || return

    if native-prepare "${directory}" "${release}"; then

        if [[ "${CONFIG[DEPLOY_STRATEGY]}" == manual ]] && ! cli-flag --force; then
            native-phase staged || return
            ui-result stage true safe
            return
        fi

        native-promote "${directory}" "${release}" "${origin}" || status=$?

    else
        status=$?
    fi

    (( status == 0 )) || { native-abort "${directory}" "${release}" "${origin}"; return "${status}"; }

    ui-result deploy true safe

}
native-prepare () {

    local directory="${1}" release="${2}"

    native-phase prepared || return
    native-images || return
    native-capacity || return
    docker-network "${CONFIG[COMPOSE_PROJECT]}-data" "${CONFIG[COMPOSE_PROJECT]}" internal || return
    docker-network "${CONFIG[COMPOSE_PROJECT]}-apps" "${CONFIG[COMPOSE_PROJECT]}" || return
    native-volumes || return
    native-data "${directory}" || return
    native-phase data || return
    native-migrate "${directory}" "${release}" || return
    native-phase migrated || return
    native-edge-prepare || return

    if [[ "${CONFIG[DEPLOY_DRIVER]}" == portainer ]]; then native-portainer-deploy "${release}" || return
    else native-front-start "${release}" || return
    fi

    native-wait-app "${release}" || return
    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 native-probe-candidate || { err "Candidate ${release} failed readiness through the edge"; return; }
    sleep "${CONFIG[WARMUP_SECONDS]}"
    native-probe-candidate || { err "Candidate ${release} regressed during warmup"; return; }

    state-write "${directory}" sealed "${CONFIG[API_IMAGE]}" || return
    native-phase healthy

}
native-promote () {

    local directory="${1}" release="${2}" origin="${3}" root="${CONFIG[STATE_ROOT]}"

    native-phase switching || return
    native-select "${CONFIG[DEPLOY_SLOT]}" "${release}" || return
    native-phase switched || return

    [[ -z "${origin}" ]] || native-background-stop "${origin}" || return
    native-background-start "${release}" || return
    run-until 15 1 native-probe-public || { err "Public endpoint does not serve ${release}"; return; }

    state-write "${root}" previous "${origin}" || return
    state-write "${root}" current "${release}" || return
    state-write "${root}" active-slot "${CONFIG[DEPLOY_SLOT]}" || return
    state-write "${directory}" activated "$(date +%s)" || return
    native-phase complete || return
    state-write "${root}" pending ""

}
native-abort () {

    local directory="${1}" release="${2}" origin="${3}" root="${CONFIG[STATE_ROOT]}" slot="" failed=0

    warn "Rejecting ${release}; restoring ${origin:-no release}"
    slot="$(state-read "${root}" origin-slot 2>/dev/null)" || slot=none

    if [[ -n "${origin}" ]]; then
        native-select "${slot}" "${origin}" || failed=1
        native-background-stop "${release}" || failed=1
        native-background-start "${origin}" || failed=1
    elif [[ -f "${root}/edge/edge.yaml" ]]; then
        native-select unavailable none || failed=1
    fi

    if (( failed == 0 )) && [[ -f "${root}/edge/edge.yaml" ]]; then
        run-until "${CONFIG[DRAIN_TIMEOUT]}" 1 haproxy-idle "$(native-edge-container)" "api_${CONFIG[DEPLOY_SLOT]}" || warn "Candidate still had sessions after ${CONFIG[DRAIN_TIMEOUT]}s"
    fi

    native-compose-app "${release}" --profile worker --profile scheduler stop -t "${CONFIG[DRAIN_TIMEOUT]}" || failed=1

    if (( failed != 0 )); then
        native-phase recovery-required
        err "Automatic recovery failed; pending state kept for rollback or recover --force"
        return
    fi

    state-write "${root}" current "${origin}" || return
    state-write "${root}" active-slot "${slot}" || return
    state-write "${root}" previous "$(state-read "${root}" origin-previous 2>/dev/null || true)" || return
    native-phase rejected || return
    state-write "${root}" pending ""

}
native-retire () {

    local slot="${1}" root="${CONFIG[STATE_ROOT]}" release="" current="" demoted=0 now=0

    release="$(state-read "${root}" "slot-${slot}" 2>/dev/null)" || release=""
    [[ -n "${release}" ]] || return 0

    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    [[ -z "${current}" ]] || demoted="$(state-read "$(native-directory "${current}")" activated 2>/dev/null || out 0)"
    now="$(date +%s)"

    (( now - demoted >= CONFIG[RETENTION_SECONDS] )) || { err "Slot ${slot} keeps ${release} for rollback for $(( CONFIG[RETENTION_SECONDS] - now + demoted ))s more"; return; }
    if native-edge-alive; then
        run-until "${CONFIG[DRAIN_TIMEOUT]}" 2 haproxy-idle "$(native-edge-container)" "api_${slot}" || { err "Slot ${slot} still serves sessions; retry after they drain"; return; }
    fi

    [[ ! -f "$(native-directory "${release}")/portainer-id" ]] || native-portainer-retire "${release}" || return
    native-compose-app "${release}" --profile worker --profile scheduler down -t "${CONFIG[DRAIN_TIMEOUT]}" || return

    [[ "$(state-read "${root}" previous 2>/dev/null || true)" != "${release}" ]] || state-write "${root}" previous "" || return
    state-write "${root}" "slot-${slot}" ""

}
native-phase () {

    state-write "${CONFIG[STATE_ROOT]}" phase "${1}" || return
    state-audit "${CONFIG[STATE_ROOT]}" "${CONFIG[RELEASE]}" "${1}" || return

    info "phase ${1}"

}
native-images () {

    local service="" image=""

    for image in "${CONFIG[IMAGE_POSTGRES]}" "${CONFIG[IMAGE_RABBITMQ]}" "${CONFIG[IMAGE_REDIS]}" "${CONFIG[IMAGE_HAPROXY]}" "${CONFIG[IMAGE_CURL]}"; do
        docker-present "${image}" || docker-pull "${image}" || return
    done

    while IFS= read -r service; do
        image="$(native-service-image "${service}")" || return
        parse-pinned "${image}" || { err "${service} image must be pinned by digest"; return; }
        docker-present "${image}" || docker-pull "${image}" || return
    done < <(native-services)

}
native-capacity () {

    local free="" service="" count=0 bytes="${CONFIG[APP_MEMORY]%[mg]}" available=""

    while IFS= read -r service; do
        count=$(( count + $(native-replicas "${service}") ))
    done < <(native-services)

    if [[ "${CONFIG[APP_MEMORY]}" == *g ]]; then bytes=$(( bytes * 1073741824 ))
    else bytes=$(( bytes * 1048576 ))
    fi

    free="$(docker-memory "${CONFIG[COMPOSE_PROJECT]}-${CONFIG[RELEASE]}")" || return
    (( free >= bytes * count )) || { err "Candidate needs $(( bytes * count / 1048576 ))MiB of unreserved Docker memory"; return; }

    available="$(df -Pk "${CONFIG[STATE_ROOT]}" | awk 'NR == 2 { print $4 }')" || return
    (( available >= 524288 )) || { err "Keep at least 512 MiB free under ${CONFIG[STATE_ROOT]}"; return; }

}
native-volumes () {

    local owner="${CONFIG[COMPOSE_PROJECT]}" name=""

    for name in postgres rabbitmq redis; do
        docker-volume "${owner}-${name}" "${owner}" 999 "${CONFIG[IMAGE_POSTGRES]}" || return
    done

    docker-volume "${owner}-storage" "${owner}" 10001 "${CONFIG[IMAGE_POSTGRES]}" || return
    tls-volumes

}
native-data () {

    local directory="${1}" root="${CONFIG[STATE_ROOT]}/data" file="" fingerprint="" recorded=""

    fs-dir "${root}" || return
    fingerprint="$(fs-hashes "${directory}/data.yaml" "${directory}/postgres.env" "${directory}/rabbitmq.env" "${directory}/redis.env" "${directory}/postgres.sql" "${directory}/pg_hba.conf")" || return

    if [[ -f "${root}/fingerprint" ]]; then
        recorded="$(state-read "${root}" fingerprint)" || return
        [[ "${recorded}" == "${fingerprint}" ]] || { err "Data service settings changed; plan that migration separately"; return; }
    else
        for file in data.yaml postgres.env rabbitmq.env redis.env postgres.sql pg_hba.conf; do
            fs-copy "${directory}/${file}" "${root}/${file}" "$(fs-mode "${directory}/${file}")" || return
        done
        state-write "${root}" fingerprint "${fingerprint}" || return
    fi

    native-compose-data up -d --no-recreate postgres rabbitmq redis || return
    native-wait-data

}
native-migrate () {

    local directory="${1}" release="${2}"

    [[ "${CONFIG[MIGRATION_POLICY]}" == expand && "${NATIVE_ROLLBACK:-false}" != true ]] || return 0
    [[ ! -f "${directory}/migrated" ]] || return 0
    [[ ! -f "${directory}/migration-started" ]] || { err "An interrupted migration needs schema inspection before retry"; return; }

    state-write "${directory}" migration-started true || return
    native-compose-app "${release}" run --rm --no-deps -T api python -m bootstrap migrate || { err "Migration failed for ${release}"; return; }
    state-write "${directory}" migrated true

}
native-front-start () {

    local release="${1}" service="" replicas=""
    local -a services=() scales=()

    while IFS= read -r service; do
        replicas="$(native-replicas "${service}")" || return
        services+=( "${service}" )
        scales+=( --scale "${service}=${replicas}" )
    done < <(native-services)

    native-compose-app "${release}" up -d --no-deps --no-recreate "${scales[@]}" "${services[@]}"

}
native-background-start () {

    local release="${1}"
    local -a services=( scheduler ) profiles=( --profile scheduler ) scales=()

    if (( CONFIG[WORKER_REPLICAS] > 0 )); then
        services+=( worker )
        profiles+=( --profile worker )
        scales=( --scale "worker=${CONFIG[WORKER_REPLICAS]}" )
    fi

    native-compose-app "${release}" "${profiles[@]}" up -d --no-deps --no-recreate "${scales[@]}" "${services[@]}"

}
native-background-stop () {

    native-compose-app "${1}" --profile worker --profile scheduler stop -t "${CONFIG[DRAIN_TIMEOUT]}" worker scheduler

}
native-runtime () {

    local detected=""

    detected="$(runtime)" || { err "Unsupported runtime"; return; }

    case "${detected}" in
        linux) return 0 ;;
        wsl)   [[ "${TOOL_BUILD}" == dev && "${CONFIG[BIND_ADDRESS]}" == 127.0.0.1 ]] && return 0 ;;
    esac

    err "Deployments need Linux; WSL is limited to a loopback development lab"

}
