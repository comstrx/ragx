source-include module/docker.sh || return
source-include module/monitoring.sh || return

native-rollback () {

    local root="${CONFIG[STATE_ROOT]}" pending="" current="" previous=""

    docker-ready || return
    fs-dir "${root}" || return
    pending="$(state-read "${root}" pending 2>/dev/null)" || pending=""

    if ! state-locked "${root}/lock" native-rollback-locked; then
        native-announce rollback.failed "the rollback failed; inspect status"
        return 1
    fi

    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    previous="$(state-read "${root}" previous 2>/dev/null)" || previous=""

    if [[ -n "${pending}" ]]; then native-announce rollback.succeeded "${pending} was rejected by an operator; ${current:-no release} keeps serving"
    else native-announce rollback.succeeded "${current} is live again by an operator; ${previous} was set aside"
    fi

}
native-rollback-locked () {

    local reason="${1:-rolled back by an operator}" root="${CONFIG[STATE_ROOT]}" pending="" origin="" previous="" current="" directory="" policy=""

    pending="$(state-read "${root}" pending 2>/dev/null)" || pending=""

    if [[ -n "${pending}" ]]; then
        origin="$(state-read "${root}" origin)" || return
        directory="$(native-directory "${pending}")" || return
        config-release-load "${directory}/release.env" || return
        cfg-set DEPLOY_SLOT "$(state-read "${root}" pending-slot)" state || return
        native-reject "${pending}" "${reason}" || warn "Rejection of ${pending} was not recorded"
        native-abort "${directory}" "${pending}" "${origin}"
        return
    fi

    previous="$(state-read "${root}" previous 2>/dev/null)" || previous=""
    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    [[ -n "${previous}" && -n "${current}" ]] || { err "No retained previous release to roll back to"; return; }

    policy="$(state-read "$(native-directory "${current}")" migration 2>/dev/null)" || policy=""
    [[ "${policy}" == none || "${policy}" == expand ]] || { err "Release ${current} has an unknown migration policy; rollback refused"; return; }

    directory="$(native-directory "${previous}")" || return
    config-release-load "${directory}/release.env" || return
    cfg-set DEPLOY_SLOT "$(native-slot "${previous}")" state || return
    [[ "$(state-read "${root}" "slot-${CONFIG[DEPLOY_SLOT]}" 2>/dev/null)" == "${previous}" ]] || { err "Slot of ${previous} was reused; redeploy it under a new RELEASE"; return; }

    NATIVE_ROLLBACK=true
    config-validate || return

    state-write "${root}" origin "${current}" || return
    state-write "${root}" origin-slot "$(state-read "${root}" active-slot)" || return
    state-write "${root}" origin-previous "${previous}" || return

    native-resume "${previous}" || return
    native-wait-app "${previous}" || return
    native-probe-candidate || { err "Retained release ${previous} is not ready"; return; }

    if native-promote "${directory}" "${previous}" "${current}"; then
        native-reject "${current}" "${reason}" || warn "Rejection of ${current} was not recorded"
        ui-result rollback true safe
        return
    fi

    native-abort "${directory}" "${previous}" "${current}"
    err "Rollback to ${previous} failed; ${current} restored"

}
native-resume () {

    local release="${1}" service="" ids="" id="" count=0
    local -a services=()

    while IFS= read -r service; do

        services+=( "${service}" )
        ids="$(native-compose-app "${release}" ps -aq "${service}")" || return
        count=0

        while IFS= read -r id; do
            [[ -z "${id}" ]] || count=$(( count + 1 ))
        done <<< "${ids}"

        (( count > 0 )) || { err "Retained containers of ${service} are missing"; return; }
        cfg-set "${service^^}_REPLICAS" "${count}"

    done < <(native-parts)

    native-compose-app "${release}" start "${services[@]}"

}
native-current () {

    local current="" directory=""

    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""
    [[ -n "${current}" ]] || { err "No current release"; return; }

    directory="$(native-directory "${current}")" || return
    config-release-load "${directory}/release.env" || return
    cfg-set DEPLOY_SLOT "$(native-slot "${current}")" state

}
native-stop () {

    cli-flag --force || { err "stop takes the edge and the current release offline; data services keep running. Repeat with --force"; return; }
    native-current || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-stop-locked

}
native-stop-locked () {

    native-compose-edge stop edge || return
    native-compose-app "${CONFIG[RELEASE]}" --profile worker --profile scheduler stop -t "${CONFIG[DRAIN_TIMEOUT]}" || return

    native-announce service.stopped "the edge and ${CONFIG[RELEASE]} were stopped by an operator; data services keep running"
    ui-result stop true safe

}
native-start () {

    native-current || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-start-locked

}
native-start-locked () {

    native-data-up || return
    native-models-converge
    native-front-start "${CONFIG[RELEASE]}" || return
    native-wait-app "${CONFIG[RELEASE]}" || return
    native-edge-prepare || return
    native-select "${CONFIG[DEPLOY_SLOT]}" "${CONFIG[RELEASE]}" || return
    native-background-start "${CONFIG[RELEASE]}" || return

    native-announce service.started "${CONFIG[RELEASE]} and the edge were started by an operator"
    ui-result start true safe

}
native-uninstall () {

    cli-flag --force || { err "uninstall removes the edge and application containers; data volumes stay. Repeat with --force"; return; }
    native-current || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-uninstall-locked

}
native-uninstall-locked () {

    local root="${CONFIG[STATE_ROOT]}" slot="" release="" removed=""

    native-compose-edge down || return

    for slot in blue green; do
        release="$(state-read "${root}" "slot-${slot}" 2>/dev/null)" || release=""
        [[ -n "${release}" ]] || continue
        native-compose-app "${release}" --profile worker --profile scheduler down || return
        removed+="${removed:+, }${release}"
    done

    [[ ! -f "${root}/monitor/monitor.yaml" ]] || monitoring-compose "${root}/monitor" down --remove-orphans || return
    native-compose-models down --remove-orphans || return
    native-compose-data down || return

    native-announce service.uninstalled "the edge, the releases ${removed:-none}, the monitoring, the models and the data containers were removed by an operator; data volumes and cached models stay"
    ui-result uninstall true safe

}
native-recover () {

    cli-flag --force || { err "Inspect status first, then recover --force removes a dead lock and resumes"; return; }

    state-recover "${CONFIG[STATE_ROOT]}/lock" || return
    native-deploy

}
