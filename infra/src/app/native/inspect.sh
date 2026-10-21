source-include module/docker.sh || return
source-include module/systemd.sh || return
source-include module/launchd.sh || return
source-include module/haproxy.sh || return

native-plan () {

    ui-row stack "${CONFIG[STACK]}"
    ui-row mode "${CONFIG[ENV_MODE]}"
    ui-row driver "${CONFIG[DEPLOY_DRIVER]}"
    ui-row strategy "${CONFIG[DEPLOY_STRATEGY]}"
    ui-row target "${CONFIG[SSH_HOST]:-local}"
    ui-row registry "${CONFIG[REGISTRY_DRIVER]}"
    ui-row protocols "$(native-protocols)"
    ui-row integrations "$(native-integrations)"
    ui-row state "${CONFIG[STATE_ROOT]}"

}
native-integrations () {

    local -a enabled=()

    [[ -z "${CONFIG[GRAFANA_HOST]}" ]] || enabled+=( monitoring )
    [[ -z "${CONFIG[TELEGRAM_BOT_TOKEN]}" ]] || enabled+=( telegram )
    [[ -z "${CONFIG[SLACK_WEBHOOK_URL]}" ]] || enabled+=( slack )
    [[ -z "${CONFIG[WEBHOOK_URL]}" ]] || enabled+=( webhook )
    [[ -z "${CONFIG[DNS_PROVIDER]}" ]] || enabled+=( "dns(${CONFIG[DNS_PROVIDER]})" )
    [[ -z "${CONFIG[TRUSTED_PROXIES]}" ]] || enabled+=( trusted-proxies )
    [[ -z "${CONFIG[BACKUP_URI]}" ]] || enabled+=( "offsite-backups(${CONFIG[BACKUP_URI]%%:*})" )
    [[ -z "${CONFIG[RATE_LIMIT_GLOBAL]}${CONFIG[RATE_LIMIT_HOST]}${CONFIG[RATE_LIMIT_IP]}${CONFIG[RATE_LIMIT_PATHS]}" ]] || enabled+=( rate-limits )

    out "${enabled[*]:-none}"

}
native-protocols () {

    local protocols="http/1.1"

    cfg-true TLS_ENABLED && protocols+=" h2"
    haproxy-quic && protocols+=" h3"

    out "${protocols}"

}
native-status () {

    local name="" value="" UI_WIDTH=12

    for name in current previous pending phase active-slot slot-blue slot-green desired; do
        value="$(state-read "${CONFIG[STATE_ROOT]}" "${name}" 2>/dev/null)" || value=""
        ui-row "${name}" "${value:-unset}"
    done

    ui-row backup "$(native-backup-age 2>/dev/null || out none)"
    ui-row channels "$(native-channels | paste -sd ' ' - | grep . || out none)"
    docker compose ls --all --filter "name=${CONFIG[COMPOSE_PROJECT]}"

}
native-backup-age () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" latest="" modified=""

    latest="$(state-read "${root}" latest)" || return
    modified="$(fs-modified "${root}/${latest}")" || return

    out "${latest}, $(( ($(date +%s) - modified) / 3600 ))h old"

}
native-doctor () {

    local check="" verdict="" detail="" failed=0 warned=0 mark=""

    for check in runtime docker settings env disk edge certificate data release backup wal timers channels; do

        IFS=' ' read -r verdict detail < <("native-doctor-${check}" 2>/dev/null || out "fail the check itself failed")

        case "${verdict}" in
            ok)   mark='✓' ;;
            warn) mark='!'; warned=$(( warned + 1 )) ;;
            *)    mark='✗'; failed=$(( failed + 1 )) ;;
        esac

        printf '  %s %-12s %s\n' "${mark}" "${check}" "${detail}"

    done

    (( failed == 0 )) || { err "${failed} check(s) failed, ${warned} warning(s)"; return; }
    succ "Every check passed, ${warned} warning(s)"

}
native-doctor-runtime () {

    local tool="" missing=""
    local -a tools=()

    read -r -a tools <<< "${MANIFEST[requires.runtime]}"

    for tool in "${tools[@]}"; do
        has "${tool}" || missing+=" ${tool}"
    done

    [[ -z "${missing}" ]] || { out "fail missing:${missing}"; return 0; }
    out "ok bash ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}, ${MANIFEST[requires.runtime]}"

}
native-doctor-docker () {

    local engine="" compose="" mode=rootful

    docker-ready || { out "fail the Docker daemon is unreachable; install it with infra docker install"; return 0; }
    engine="$(docker version --format '{{.Server.Version}}')" || engine=unknown
    compose="$(docker compose version --short)" || compose=unknown
    ! docker-rootless || mode=rootless

    if [[ "${engine}" == "${MANIFEST[tools.docker]}" && "${compose#v}" == "${MANIFEST[tools.compose]}" ]]; then out "ok engine ${engine}, compose ${compose#v}, ${mode}"
    elif [[ "${CONFIG[ENV_MODE]}" == production ]]; then out "fail engine ${engine} and compose ${compose#v} differ from ${MANIFEST[tools.docker]} and ${MANIFEST[tools.compose]}"
    else out "warn engine ${engine} and compose ${compose#v} differ from the pinned ${MANIFEST[tools.docker]} and ${MANIFEST[tools.compose]}"
    fi

}
native-doctor-settings () {

    local problem=""

    problem="$( { config-validate && native-release-id && config-required; } 2>&1 >/dev/null | grep '^\[-\]' | head -1)"
    [[ -z "${problem}" ]] || { out "fail ${problem#\[-\] }"; return 0; }
    out "ok valid and complete for a deploy"

}
native-doctor-env () {

    local app="" found="" file=""

    for app in API WEB; do
        file="$(native-env-file "${app}")"
        if native-env-present "${app}"; then found+="${found:+, }${app,,}"
        elif [[ "${app}" == API ]]; then out "fail API env content missing: export API_ENV_FILE or stage ${file##*/}"; return 0
        fi
    done

    out "ok ${found}"

}
native-doctor-disk () {

    local free=0 path="${CONFIG[PROJECT_ROOT]}"

    free="$(df -Pk "${path}" | awk 'NR == 2 { print $4 }')" || { out "fail free space unreadable under ${path}"; return 0; }

    if (( free >= 2097152 )); then out "ok $(( free / 1048576 )) GiB free under ${path}"
    elif (( free >= 524288 )); then out "warn $(( free / 1024 )) MiB free under ${path}; deploys need 512 MiB"
    else out "fail $(( free / 1024 )) MiB free under ${path}; deploys stop below 512 MiB"
    fi

}
native-doctor-edge () {

    [[ -f "${CONFIG[STATE_ROOT]}/edge/edge.yaml" ]] || { out "warn not applied yet; run infra edge apply"; return 0; }
    native-edge-alive || { out "fail the edge is not running; run infra start"; return 0; }
    if [[ -z "${CONFIG[EDGE_SOCKETS]}" ]]; then
        docker-rootless || { out "ok listening on ${CONFIG[BIND_ADDRESS]}:${CONFIG[HTTPS_PORT]} ($(native-protocols))"; return 0; }
        out "warn listening on ${CONFIG[BIND_ADDRESS]}:${CONFIG[HTTPS_PORT]} through rootless Docker, whose port forwarding shows every client as the network gateway to logs, RATE_LIMIT_IP and TRUSTED_PROXIES; relay through EDGE_SOCKETS to keep client addresses"
        return 0
    fi

    native-edge-sockets 2>/dev/null || { out "fail uid 1000 cannot write ${CONFIG[EDGE_SOCKETS]}; run: $(native-edge-grant)"; return 0; }
    out "ok relayed through ${CONFIG[EDGE_SOCKETS]}/http.sock and https.sock with the PROXY protocol ($(native-protocols))"

}
native-doctor-certificate () {

    local expiry="" days=0

    cfg-true TLS_ENABLED || { out "warn TLS is off"; return 0; }
    native-edge-alive 2>/dev/null || { out "warn unchecked while the edge is down"; return 0; }
    expiry="$(native-certificate-expiry)" || { out "fail no certificate answers; run infra tls issue or tls import"; return 0; }
    days=$(( (expiry - $(date +%s)) / 86400 ))

    if (( days >= 14 )); then out "ok ${days} days left"
    elif (( days >= 0 )); then out "warn ${days} days left; the renew timer or infra tls renew must run"
    else out "fail expired; run infra tls renew"
    fi

}
native-doctor-data () {

    [[ -f "${CONFIG[STATE_ROOT]}/data/data.yaml" ]] || { out "warn not deployed yet"; return 0; }
    native-data-healthy || { out "fail PostgreSQL, RabbitMQ or Redis is unhealthy; run infra start"; return 0; }
    out "ok PostgreSQL, RabbitMQ and Redis healthy"

}
native-doctor-release () {

    local root="${CONFIG[STATE_ROOT]}" current="" pending="" phase=""

    current="$(state-read "${root}" current 2>/dev/null)" || current=""
    pending="$(state-read "${root}" pending 2>/dev/null)" || pending=""
    phase="$(state-read "${root}" phase 2>/dev/null)" || phase=""

    [[ "${phase}" != recovery-required ]] || { out "fail recovery required; read status, then rollback or recover --force"; return 0; }
    [[ -z "${pending}" ]] || { out "warn ${pending} is pending in phase ${phase}"; return 0; }
    [[ -n "${current}" ]] || { out "warn no release deployed yet"; return 0; }
    out "ok ${current} (${phase:-complete})"

}
native-doctor-wal () {

    local bases="" oldest=""

    cfg-true BACKUP_WAL || { out "ok off; restores use the dumps"; return 0; }
    native-data-healthy || { out "warn unchecked while the data services are down"; return 0; }
    native-compose-data exec -T postgres test -f /wal/enabled || { out "warn archiving is not switched on yet; run infra deploy or infra backup"; return 0; }
    native-archive-healthy || { out "fail archiving fails; read the PostgreSQL log and the space under the WAL archive"; return 0; }

    bases="$(postgresql-bases native-compose-data exec -T postgres | sort)" || bases=""
    [[ -n "${bases}" ]] || { out "warn archiving, but no base backup yet; run infra backup"; return 0; }
    read -r _ _ oldest <<< "${bases%%$'\n'*}"

    out "ok archiving every 60s at most; point in time back to ${oldest}"

}
native-archive-healthy () {

    local archived="" failed=""

    read -r archived failed < <(postgresql-archiver native-compose-data exec -T postgres) || return 0
    [[ "${failed}" =~ ^-?[0-9]+$ && "${archived}" =~ ^-?[0-9]+$ ]] || return 0
    (( failed < 0 || (archived >= 0 && archived <= failed) ))

}
native-doctor-backup () {

    local age=""

    age="$(native-backup-age 2>/dev/null)" || { out "warn no backup recorded yet; run infra backup"; return 0; }
    (( $(date +%s) - $(fs-modified "${CONFIG[BACKUP_SQL_ROOT]}/${age%%,*}") <= CONFIG[BACKUP_MAX_AGE] )) || { out "fail ${age}; older than BACKUP_MAX_AGE"; return 0; }
    out "ok ${age}"

}
native-doctor-timers () {

    local name="" missing="" linger=""
    local -a timers=( monitor backup )

    [[ "${TOOL_BUNDLED:-false}" == true && "${TOOL_BUILD}" == release ]] || { out "warn checked only from the staged release bundle"; return 0; }
    ! cfg-true TLS_ENABLED || timers+=( renew )
    [[ -z "${CONFIG[GITOPS_URL]}" ]] || timers+=( reconcile )

    for name in "${timers[@]}"; do
        if is-linux; then systemd-present "${CONFIG[COMPOSE_PROJECT]}-${name}" || missing+=" ${name}"
        else launchd-present "${CONFIG[COMPOSE_PROJECT]}-${name}" || missing+=" ${name}"
        fi
    done

    [[ -z "${missing}" ]] || { out "warn not installed:${missing}; deploy installs them"; return 0; }
    linger="$(loginctl show-user "$(id -un)" --property=Linger 2>/dev/null)" || linger=""
    [[ "${linger}" == Linger=yes ]] || ! is-linux || { out "warn installed, but they stop at logout; run loginctl enable-linger"; return 0; }
    out "ok ${timers[*]}"

}
native-doctor-channels () {

    local channels=""

    channels="$(native-channels | paste -sd ' ' -)"
    [[ -n "${channels}" ]] || { out "warn none configured; failures will be silent"; return 0; }
    out "ok ${channels}"

}
