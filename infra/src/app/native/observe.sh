source-include module/docker.sh || return
source-include module/monitoring.sh || return
source-include module/tls.sh || return

native-monitor () {

    local root="${CONFIG[STATE_ROOT]}" release="" latest="" backup=0 expiry=0 now="" previous="" healthy=true reason="" summary=""
    local -a reasons=()

    ! state-busy "${root}/lock" || { info "A deployment holds the lock; monitor skipped"; return 0; }
    native-current || return
    release="${CONFIG[RELEASE]}"
    now="$(date +%s)"

    native-serving "${release}" || reasons+=( "${release} is not serving on every replica and the public endpoint" )
    native-data-healthy || reasons+=( "data services are unhealthy" )

    if latest="$(state-read "${CONFIG[BACKUP_ROOT]}" latest 2>/dev/null)"; then
        backup="$(fs-modified "${CONFIG[BACKUP_ROOT]}/${latest}")" || return
        (( now - backup <= CONFIG[BACKUP_MAX_AGE] )) || reasons+=( "the latest backup is $(( (now - backup) / 3600 ))h old" )
    else
        reasons+=( "no backup is recorded" )
    fi

    if cfg-true TLS_ENABLED; then
        expiry="$(native-certificate-expiry)" || expiry=0
        (( expiry - now >= 1209600 )) || reasons+=( "the certificate expires in less than 14 days" )
    fi

    (( ${#reasons[@]} == 0 )) || healthy=false
    native-metrics "${release}" "${healthy}" "${backup}" "${expiry}" || warn "Platform metrics were not written"

    previous="$(state-read "${root}" monitor 2>/dev/null)" || previous=true
    state-write "${root}" monitor "${healthy}" || return

    ui-row release "${release}"
    ui-row healthy "${healthy}"

    if [[ "${healthy}" == true ]]; then
        [[ "${previous}" != false ]] || native-announce monitor.recovered "${release} recovered"
        return 0
    fi

    for reason in "${reasons[@]}"; do
        warn "${reason^}"
        summary+="${summary:+; }${reason}"
    done

    [[ "${previous}" == false ]] || native-announce monitor.degraded "${release} is degraded: ${summary}"
    return 1

}
native-serving () {

    local release="${1}" service="" replicas=""

    while IFS= read -r service; do
        replicas="$(native-replicas "${service}")" || return
        native-healthy "${release}" "${service}" "${replicas}" || return 1
    done < <(native-services)

    native-probe-public

}
native-certificate-expiry () {

    local address="${CONFIG[BIND_ADDRESS]}"

    if [[ -n "${CONFIG[EDGE_SOCKETS]}" ]]; then
        native-edge-curl https.sock --insecure --output /dev/null --write-out '%{certs}' "https://${CONFIG[API_HOST]}/" 2>/dev/null | tls-enddate
        return
    fi

    [[ "${address}" != 0.0.0.0 ]] || address=127.0.0.1

    tls-expiry "${CONFIG[API_HOST]}" "${address}" "${CONFIG[HTTPS_PORT]}"

}
native-metrics () {

    local release="${1}" healthy="${2}" backup="${3}" expiry="${4}" value=0

    [[ "${healthy}" != true ]] || value=1
    fs-dir "${CONFIG[STATE_ROOT]}/metrics" || return

    {
        printf 'platform_healthy %s\n' "${value}"
        printf 'platform_release_info{release="%s"} 1\n' "${release}"
        (( backup == 0 )) || printf 'platform_backup_timestamp_seconds %s\n' "${backup}"
        (( expiry == 0 )) || printf 'platform_certificate_expiry_timestamp_seconds %s\n' "${expiry}"
    } | fs-write "${CONFIG[STATE_ROOT]}/metrics/platform.prom"

}
native-verify () {

    local release="${1}" deadline=0 failures=0

    deadline=$(( $(date +%s) + CONFIG[VERIFY_SECONDS] ))
    info "Verifying ${release} for ${CONFIG[VERIFY_SECONDS]}s"

    while (( $(date +%s) < deadline )); do

        if native-serving "${release}"; then failures=0
        else failures=$(( failures + 1 ))
        fi

        (( failures < CONFIG[VERIFY_FAILURES] )) || { err "${release} failed ${failures} consecutive checks after the switch"; return; }
        sleep "${CONFIG[VERIFY_INTERVAL]}"

    done

}
native-revert () {

    local release="${1}" reason="${2}" previous=""

    previous="$(state-read "${CONFIG[STATE_ROOT]}" previous 2>/dev/null)" || previous=""

    if [[ -z "${previous}" ]]; then
        native-phase degraded
        native-announce verify.degraded "${release} ${reason}; no retained release to roll back to"
        return 1
    fi

    warn "Rolling ${release} back to ${previous}: ${reason}"

    if native-rollback-locked "${reason}"; then native-announce verify.rolled-back "${release} ${reason}; rolled back to ${previous}"
    else native-announce verify.unrecovered "${release} ${reason} and the rollback to ${previous} failed; inspect status"
    fi

    return 1

}
native-observe () {

    native-monitoring || warn "Monitoring did not converge; the release keeps serving"
    native-timers

}
native-monitoring () {

    local root="${CONFIG[STATE_ROOT]}" live="${CONFIG[STATE_ROOT]}/monitor" next="${CONFIG[STATE_ROOT]}/monitor-next" owner="${CONFIG[COMPOSE_PROJECT]}"
    local uid="" image="" fingerprint="" recorded=""
    local -a pulls=( "${CONFIG[IMAGE_PROMETHEUS]}" "${CONFIG[IMAGE_GRAFANA]}" "${CONFIG[IMAGE_NODE_EXPORTER]}" "${CONFIG[IMAGE_POSTGRES_EXPORTER]}" )

    if [[ -z "${CONFIG[GRAFANA_HOST]}" ]]; then
        [[ -d "${live}" ]] || return 0
        monitoring-compose "${live}" down --remove-orphans || return
        rm -rf -- "${live}"
        return
    fi

    [[ -z "${CONFIG[TELEGRAM_BOT_TOKEN]}${CONFIG[SLACK_WEBHOOK_URL]}" ]] || pulls+=( "${CONFIG[IMAGE_ALERTMANAGER]}" )

    for image in "${pulls[@]}"; do
        docker-present "${image}" || docker-pull "${image}" || return
    done

    uid="$(docker-uid)" || return
    cfg-set MONITOR_USER "${uid}:${uid}"

    docker-volume "${owner}-prometheus" "${owner}" "${uid}" "${CONFIG[IMAGE_POSTGRES]}" || return
    docker-volume "${owner}-grafana" "${owner}" "${uid}" "${CONFIG[IMAGE_POSTGRES]}" || return
    fs-dir "${root}/metrics" || return

    rm -rf -- "${next}"
    if ! monitoring-render "${next}" || ! fingerprint="$(monitoring-fingerprint "${next}")"; then
        rm -rf -- "${next}"
        err "Monitoring render failed"
        return
    fi

    recorded="$(monitoring-fingerprint "${live}" 2>/dev/null)" || recorded=""

    if [[ "${fingerprint}" == "${recorded}" ]]; then
        rm -rf -- "${next}"
        monitoring-compose "${live}" up -d --remove-orphans || return
        run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 monitoring-healthy "${live}" || { err "Monitoring services are not healthy"; return; }
        return
    fi

    rm -rf -- "${live}" && mv -- "${next}" "${live}" || return
    monitoring-compose "${live}" up -d --force-recreate --remove-orphans || return
    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 monitoring-healthy "${live}" || { err "Monitoring services did not become healthy"; return; }
    monitoring-password "${live}"

}
native-timers () {

    [[ "${TOOL_BUNDLED:-false}" == true && "${TOOL_BUILD}" == release ]] || return 0

    native-timer-install monitor "${CONFIG[MONITOR_INTERVAL]}" >/dev/null || warn "The monitor timer is not installed"
    native-timer-install backup "${CONFIG[BACKUP_INTERVAL]}" >/dev/null || warn "The backup timer is not installed"
    ! cfg-true TLS_ENABLED || native-timer-install renew "${CONFIG[RENEW_INTERVAL]}" >/dev/null || warn "The renewal timer is not installed"

    if [[ -n "${CONFIG[GITOPS_URL]}" ]]; then
        native-timer-install reconcile "${CONFIG[GITOPS_INTERVAL]}" >/dev/null || warn "The reconcile timer is not installed"
    else
        native-timer-remove reconcile || warn "The reconcile timer is still installed"
    fi

}
