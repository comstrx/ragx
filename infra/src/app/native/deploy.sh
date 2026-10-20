source-include module/docker.sh || return
source-include module/haproxy.sh || return
source-include module/portainer.sh || return
source-include module/postgresql.sh || return
source-include module/registry.sh || return
source-include module/tls.sh || return

native-deploy () {

    if [[ "${CONFIG[DEPLOY_DRIVER]}" == portainer && -z "${CONFIG[GITOPS_COMMIT]:-}" ]]; then
        native-reconcile
        return
    fi

    config-validate || return
    native-release-id || return
    config-required || return
    ! cli-flag --dry-run || { native-deploy-plan; return; }
    native-runtime || return
    docker-ready || return
    [[ "${CONFIG[ENV_MODE]}" != production ]] || docker-versions || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-converge

}
native-intent () {

    local root="${CONFIG[STATE_ROOT]}" release="${CONFIG[RELEASE]}" pending="" current="" previous="" reason=""

    pending="$(state-read "${root}" pending 2>/dev/null)" || pending=""
    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    previous="$(state-read "${root}" previous 2>/dev/null)" || previous=""

    if [[ -n "${pending}" && "${pending}" != "${release}" ]]; then out "blocked ${pending}"
    elif [[ -z "${pending}" && "${current}" != "${release}" ]] && reason="$(native-rejected "${release}")"; then out "rejected ${reason}"
    elif [[ -n "${pending}" ]]; then out resume
    elif [[ -n "${previous}" && "${release}" == "${previous}" ]]; then out switch
    elif [[ "${current}" == "${release}" ]]; then out current
    else out new
    fi

}
native-deploy-plan () {

    local intent="" detail="" current="" active="" slot=blue UI_WIDTH=10

    read -r intent detail < <(native-intent)
    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""
    active="$(state-read "${CONFIG[STATE_ROOT]}" active-slot 2>/dev/null)" || active=""
    [[ "${active}" != blue ]] || slot=green

    ui-row release "${CONFIG[RELEASE]}"
    ui-row live "${current:-none}${active:+ in ${active}}"
    ui-row images "api=${CONFIG[API_IMAGE]}${CONFIG[WEB_IMAGES]:+ ${CONFIG[WEB_IMAGES]}}"
    ui-row migration "${CONFIG[MIGRATION_POLICY]}"

    case "${intent}" in
        blocked)  ui-row intent "refused: ${detail} is pending; finish it with deploy or reject it with rollback" ;;
        rejected) ui-row intent "rejected (${detail}); --force ships it again" ;;
        resume)   ui-row intent "resume the pending release in its slot" ;;
        switch)   ui-row intent "switch back to the retained ${CONFIG[RELEASE]} in seconds, without pulling or migrating" ;;
        current)  ui-row intent "no change: ${CONFIG[RELEASE]} is live; probe the public endpoint" ;;
        new)      ui-row intent "deploy into the ${slot} slot through the readiness gates, then verify for ${CONFIG[VERIFY_SECONDS]}s" ;;
    esac

    if [[ "${intent}" == new ]] && docker-ready 2>/dev/null; then
        native-edge-preflight || return
        ui-row edge "the live edge matches the rendered one"
    elif [[ "${intent}" == new ]]; then
        ui-row edge "unchecked: Docker is unreachable"
    fi

    [[ "${intent}" != blocked ]] || { err "This deploy would be refused"; return; }
    [[ "${intent}" != rejected ]] || cli-flag --force || { err "This deploy would be refused"; return; }

    ui-result deploy-plan false safe

}
native-converge () {

    local root="${CONFIG[STATE_ROOT]}" release="${CONFIG[RELEASE]}" current="" active="" slot="" origin="" directory=""
    local intent="" detail="" phase="" status=0

    read -r intent detail < <(native-intent)
    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    active="$(state-read "${root}" active-slot 2>/dev/null)" || active=""

    case "${intent}" in
        blocked)
            err "Release ${detail} is pending; finish it with deploy or reject it with rollback"
            return
        ;;
        rejected)
            cli-flag --force || { err "Release ${release} was rejected (${detail}); publish a new release or deploy --force"; return; }
            rm -f -- "${root}/rejected/${release}"
            read -r intent detail < <(native-intent)
        ;;
    esac

    if [[ "${intent}" == switch ]]; then
        native-release-match "$(native-directory "${release}")" || return
        native-rollback-locked "superseded by ${release}" || return
        native-observe
        native-announce deploy.switched "${release} is live again; ${current} was superseded"
        return
    fi

    if [[ "${intent}" == current ]]; then
        cfg-set DEPLOY_SLOT "${active}" state
        native-release-match "$(native-directory "${release}")" || return
        native-probe-public || return
        native-observe
        ui-result deploy false safe
        return
    fi

    if [[ "${intent}" == new ]]; then

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

    if (( status != 0 )); then
        phase="$(state-read "${root}" phase 2>/dev/null)" || phase=""
        [[ ! "${phase}" =~ ^(data|migrated|healthy|switching|switched)$ ]] || native-reject "${release}" "failed at phase ${phase}" || warn "Rejection of ${release} was not recorded"
        if native-abort "${directory}" "${release}" "${origin}"; then native-announce deploy.rejected "${release} was rejected; ${origin:-no release} keeps serving"
        else native-announce deploy.unrecovered "${release} failed and automatic recovery failed; inspect status"
        fi
        return "${status}"
    fi

    native-verify "${release}" || { native-revert "${release}" "failed verification after the switch"; return; }
    native-observe
    native-announce deploy.succeeded "${release} is live on ${CONFIG[API_URL]}"

    ui-result deploy true safe

}
native-prepare () {

    local directory="${1}" release="${2}"

    native-phase prepared || return
    native-images || return
    native-capacity || return
    native-networks || return
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
native-reject () {

    state-write "${CONFIG[STATE_ROOT]}/rejected" "${1}" "${2}"

}
native-rejected () {

    state-read "${CONFIG[STATE_ROOT]}/rejected" "${1}" 2>/dev/null

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

    local service="" image="" host="" status=0
    local -a pulls=( "${CONFIG[IMAGE_POSTGRES]}" "${CONFIG[IMAGE_RABBITMQ]}" "${CONFIG[IMAGE_REDIS]}" "${CONFIG[IMAGE_HAPROXY]}" "${CONFIG[IMAGE_CURL]}" )

    while IFS= read -r service; do
        image="$(native-service-image "${service}")" || return
        parse-pinned "${image}" || { err "${service} image must be pinned by digest"; return; }
        pulls+=( "${image}" )
    done < <(native-services)

    if [[ -n "${CONFIG[REGISTRY_TOKEN]}" ]]; then
        host="$(registry-host)" || return
        docker-login "${host}" "${CONFIG[REGISTRY_USER]}" "${CONFIG[REGISTRY_TOKEN]}" || return
    fi

    for image in "${pulls[@]}"; do
        docker-present "${image}" || docker-pull "${image}" || { status=1; break; }
    done

    [[ -z "${host}" ]] || docker-logout "${host}" || warn "Registry logout failed: ${host}"

    return "${status}"

}
native-networks () {

    docker-network "${CONFIG[COMPOSE_PROJECT]}-data" "${CONFIG[COMPOSE_PROJECT]}" internal || return
    docker-network "${CONFIG[COMPOSE_PROJECT]}-apps" "${CONFIG[COMPOSE_PROJECT]}"

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
    native-wait-data || return

    postgresql-extensions "${CONFIG[DB_NAME]}" "${CONFIG[DB_EXTENSIONS]}" native-compose-data exec -T postgres

}
native-migrate () {

    local directory="${1}" release="${2}"
    local -a migrate=()

    [[ "${CONFIG[MIGRATION_POLICY]}" == expand && "${NATIVE_ROLLBACK:-false}" != true ]] || return 0
    [[ ! -f "${directory}/migrated" ]] || return 0
    [[ ! -f "${directory}/migration-started" ]] || { err "An interrupted migration needs schema inspection before retry"; return; }

    read -r -a migrate <<< "${CONFIG[API_MIGRATE_COMMAND]}"
    (( ${#migrate[@]} > 0 )) || { err "MIGRATION_POLICY=expand requires API_MIGRATE_COMMAND"; return; }

    state-write "${directory}" migration-started true || return
    native-compose-app "${release}" run --rm --no-deps -T api "${migrate[@]}" || { err "Migration failed for ${release}"; return; }
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
