config-valid () {

    local kind="${1}" value="${2-}"

    case "${kind}" in
        identifier) parse-identifier "${value}" ;;
        port)       parse-port "${value}" ;;
        positive)   parse-positive "${value}" ;;
        replicas)   parse-positive "${value}" && (( value <= 32 )) ;;
        workers)    parse-count "${value}" && (( value <= 32 )) ;;
        boolean)    parse-boolean "${value}" ;;
        path)       parse-path "${value}" ;;
        host)       parse-host "${value}" ;;
        address)    parse-address "${value}" ;;
        pinned)     parse-pinned "${value}" ;;
        memory)     [[ "${value}" =~ ^[1-9][0-9]{0,5}[mg]$ ]] ;;
        megabytes)  [[ "${value}" =~ ^[1-9][0-9]{0,5}(MB|GB)$ ]] ;;
        cpus)       [[ "${value}" =~ ^(0\.[0-9]*[1-9][0-9]*|[1-9][0-9]?(\.[0-9]+)?)$ ]] ;;
        https)      [[ "${value}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9/_.~%-]*)?$ ]] ;;
        webhook)    [[ "${value}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[^[:space:]\"\\@]*)?$ ]] ;;
        retries)    parse-count "${value}" && (( value <= 5 )) ;;
        rate)       [[ "${value}" =~ ^[1-9][0-9]{0,8}/[1-9][0-9]{0,4}[smh]$ ]] ;;
        bucket)     [[ "${value}" =~ ^(s3|gs)://[a-z0-9][a-z0-9._-]{1,62}(/[A-Za-z0-9/_.-]*)?$ ]] ;;
        bot)        [[ "${value}" =~ ^[0-9]{1,20}:[A-Za-z0-9_-]{20,64}$ ]] ;;
        chat)       [[ "${value}" =~ ^-?[1-9][0-9]{0,19}$ ]] ;;
        duration)   [[ "${value}" =~ ^[1-9][0-9]{0,3}[hdwy]$ ]] ;;
        variable)   [[ "${value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ;;
        extensions) [[ "${value}" =~ ^([a-z][a-z0-9_]{0,62}(,[a-z][a-z0-9_]{0,62})*)?$ ]] ;;
        header)     [[ "${value}" =~ ^[A-Za-z][A-Za-z0-9-]{0,63}$ ]] ;;
        email)      [[ "${value}" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63}$ ]] ;;
        branch)     git-ref "${value}" ;;
        region)     [[ "${value}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] ;;
        namespace)  [[ "${value}" =~ ^[a-z0-9]+([._-][a-z0-9]+)*$ ]] ;;
        target)     [[ "${value}" =~ ^[A-Za-z0-9][A-Za-z0-9.:-]*$ ]] ;;
        user)       [[ "${value}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]] ;;
        proxies)    config-proxies "${value}" ;;
        relative)   fs-relative "${value}" ;;
        command)    [[ "${value}" =~ [^[:space:]] && "${value}" != *$'\n'* ]] ;;
        pairs)      config-pairs "${value}" ;;
        *)          [[ " ${kind//,/ } " == *" ${value} "* ]] ;;
    esac

}
config-check () {

    local kind="${1}" key="" failed=0

    shift

    for key in "$@"; do
        config-valid "${kind}" "${CONFIG[${key}]-}" || { err "Invalid ${key}: expected ${kind//,/|}"; failed=1; }
    done

    (( failed == 0 ))

}
config-check-set () {

    local kind="${1}" key="" failed=0

    shift

    for key in "$@"; do
        [[ -z "${CONFIG[${key}]-}" ]] || config-check "${kind}" "${key}" || failed=1
    done

    (( failed == 0 ))

}
config-validate () {

    local failed=0

    config-check port HTTP_PORT HTTPS_PORT SSH_PORT API_PORT WEB_PORT METRICS_PORT PORTAINER_PORT || failed=1
    config-check positive HEALTH_TIMEOUT WARMUP_SECONDS DRAIN_TIMEOUT RETENTION_SECONDS || failed=1
    config-check positive EDGE_MAXCONN BACKEND_MAXCONN GITOPS_INTERVAL BACKUP_MAX_AGE BACKUP_DAYS PORTAINER_ENDPOINT || failed=1
    config-check positive VERIFY_SECONDS VERIFY_FAILURES VERIFY_INTERVAL MONITOR_INTERVAL BACKUP_INTERVAL RENEW_INTERVAL || failed=1
    config-check positive BACKUP_ARCHIVE_INTERVAL || failed=1
    config-check replicas API_REPLICAS || failed=1
    config-check workers WORKER_REPLICAS || failed=1
    config-check boolean TLS_ENABLED HTTP3_ENABLED METRICS_ENABLED DNS_PROXIED BACKUP_WAL || failed=1
    config-check path API_READY_PATH WEB_READY_PATH API_ENV_MOUNT WEB_ENV_MOUNT API_STORAGE_MOUNT || failed=1
    config-check relative GITOPS_DESIRED GITOPS_COMPOSE || failed=1
    config-check extensions DB_EXTENSIONS || failed=1
    config-check command API_SERVE_COMMAND API_WORK_COMMAND API_SCHEDULE_COMMAND || failed=1
    config-check pairs API_FORCED_ENV API_SERVE_ENV API_WORK_ENV API_SCHEDULE_ENV WEB_FORCED_ENV || failed=1
    config-check address BIND_ADDRESS || failed=1
    config-check memory APP_MEMORY DATA_MEMORY EDGE_MEMORY || failed=1
    config-check megabytes DB_MEMORY || failed=1
    config-check cpus CPUS || failed=1
    config-check pinned IMAGE_POSTGRES IMAGE_RABBITMQ IMAGE_REDIS IMAGE_HAPROXY IMAGE_PORTAINER IMAGE_CURL IMAGE_CERTBOT IMAGE_AWS || failed=1
    config-check pinned IMAGE_PROMETHEUS IMAGE_ALERTMANAGER IMAGE_GRAFANA IMAGE_NODE_EXPORTER IMAGE_POSTGRES_EXPORTER || failed=1
    config-check duration METRICS_RETENTION || failed=1
    config-check https PORTAINER_URL || failed=1
    config-check none,expand MIGRATION_POLICY || failed=1
    config-check blue-green,manual DEPLOY_STRATEGY || failed=1
    config-check portainer,compose DEPLOY_DRIVER || failed=1
    config-check http,dns TLS_CHALLENGE || failed=1
    config-check ghcr,dockerhub REGISTRY_DRIVER || failed=1
    config-check auto,agent,key,certificate,password SSH_METHOD || failed=1
    config-check roundrobin,leastconn API_BALANCE WEB_BALANCE || failed=1
    config-check blue,green DEPLOY_SLOT || failed=1

    config-check-set identifier PROJECT VERSION RELEASE DB_NAME DB_USER RABBIT_USER || failed=1
    config-check-set host API_HOST || failed=1
    config-check-set pinned API_IMAGE || failed=1
    config-check-set https EXTERNAL_HEALTH_URL GITOPS_URL || failed=1
    config-check-set rate RATE_LIMIT_GLOBAL RATE_LIMIT_HOST RATE_LIMIT_IP || failed=1
    config-check-set host GRAFANA_HOST || failed=1
    config-check-set bucket BACKUP_URI || failed=1
    config-check-set path EDGE_SOCKETS || failed=1
    config-check-set https BACKUP_ENDPOINT || failed=1
    config-check-set path BACKUP_DIR || failed=1
    config-check-set address DNS_ADDRESS || failed=1
    config-check-set cloudflare DNS_PROVIDER || failed=1
    config-check-set proxies TRUSTED_PROXIES || failed=1
    config-check-set header TRUSTED_HEADER || failed=1
    config-check-set bot TELEGRAM_BOT_TOKEN || failed=1
    config-check-set chat TELEGRAM_CHAT_ID || failed=1
    config-check-set webhook SLACK_WEBHOOK_URL WEBHOOK_URL || failed=1
    config-check retries NOTIFY_RETRIES || failed=1
    config-check-set variable API_RELEASE_VARIABLE WEB_SPEC_VARIABLE WEB_API_VARIABLE || failed=1
    config-check-set command API_MIGRATE_COMMAND || failed=1
    config-check branch GITOPS_BRANCH || failed=1
    config-check-set email TLS_EMAIL || failed=1
    config-check-set path HEALTH_CA PORTAINER_CA || failed=1
    config-check-set region BACKUP_REGION || failed=1
    config-check-set namespace REGISTRY_NAMESPACE || failed=1
    config-check-set target SSH_HOST || failed=1
    config-check-set user SSH_USER || failed=1
    config-check-set relative REMOTE_DIR || failed=1

    [[ "${CONFIG[DB_USER]}" != postgres ]] || { err "DB_USER must not be the PostgreSQL superuser"; failed=1; }
    [[ "${CONFIG[GITOPS_DESIRED]}" != "${CONFIG[GITOPS_COMPOSE]}" ]] || { err "GITOPS_DESIRED and GITOPS_COMPOSE must differ"; failed=1; }
    [[ "${CONFIG[MIGRATION_POLICY]}" != expand || -n "${CONFIG[API_MIGRATE_COMMAND]}" ]] || { err "MIGRATION_POLICY=expand requires API_MIGRATE_COMMAND"; failed=1; }
    ! cfg-true HTTP3_ENABLED || cfg-true TLS_ENABLED || { err "HTTP3_ENABLED=true requires TLS_ENABLED=true"; failed=1; }
    [[ "${CONFIG[ENV_MODE]}" != production ]] || cfg-true TLS_ENABLED || { err "Production requires TLS_ENABLED=true"; failed=1; }

    config-web || failed=1
    config-hosts || failed=1
    config-limits || failed=1
    config-group BACKUP_URI BACKUP_KEY BACKUP_SECRET || failed=1
    config-group DNS_PROVIDER DNS_TOKEN DNS_ZONE DNS_ADDRESS || failed=1
    config-group TRUSTED_PROXIES TRUSTED_HEADER || failed=1
    config-group TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID || failed=1
    config-group GRAFANA_HOST GRAFANA_PASSWORD || failed=1
    config-group REGISTRY_USER REGISTRY_TOKEN || failed=1
    config-group GITOPS_URL GITOPS_USER GITOPS_TOKEN || failed=1

    [[ -z "${CONFIG[GRAFANA_PASSWORD]}" ]] || (( ${#CONFIG[GRAFANA_PASSWORD]} >= 12 )) || { err "GRAFANA_PASSWORD needs at least 12 characters"; failed=1; }
    [[ "${CONFIG[TLS_CHALLENGE]}" != dns || -n "${CONFIG[DNS_PROVIDER]}" ]] || { err "TLS_CHALLENGE=dns requires DNS_PROVIDER"; failed=1; }
    ! cfg-true DNS_PROXIED || [[ -n "${CONFIG[DNS_PROVIDER]}" ]] || { err "DNS_PROXIED applies to the records DNS_PROVIDER manages"; failed=1; }
    [[ -z "${CONFIG[WEBHOOK_SECRET]}" || -n "${CONFIG[WEBHOOK_URL]}" ]] || { err "WEBHOOK_SECRET signs WEBHOOK_URL deliveries; set WEBHOOK_URL"; failed=1; }
    [[ -z "${CONFIG[GITOPS_URL]}" || -n "${CONFIG[REGISTRY_TOKEN]}" ]] || warn "GitOps pulls private images only with a permanent REGISTRY_TOKEN on the server"

    ! cfg-true DNS_PROXIED || ! cfg-true HTTP3_ENABLED || [[ -n "${CONFIG[EDGE_SOCKETS]}" ]] || warn "DNS_PROXIED=true: the DNS provider terminates public QUIC and origin HTTP/3 stays unused"
    ! cfg-true DNS_PROXIED || [[ -n "${CONFIG[TRUSTED_HEADER]}" ]] || warn "DNS_PROXIED=true without TRUSTED_HEADER: the edge sees the provider's addresses instead of the clients'"

    (( failed == 0 ))

}
config-group () {

    local key="" set=0 missing=""

    for key in "$@"; do
        if [[ -n "${CONFIG[${key}]}" ]]; then set=$(( set + 1 ))
        else missing+="${missing:+, }${key}"
        fi
    done

    (( set == 0 || set == $# )) || { err "${1%%_*} settings are partial; missing ${missing}"; return; }

}
config-proxies () {

    local item=""
    local -a items=()

    [[ "${1-}" != *$'\n'* ]] || return 1
    read -r -a items <<< "${1-}"

    for item in "${items[@]}"; do
        parse-cidr "${item}" || config-valid https "${item}" || return 1
    done

}
config-pairs () {

    local pair=""
    local -a pairs=()

    [[ "${1-}" != *$'\n'* ]] || return 1
    read -r -a pairs <<< "${1-}"

    for pair in "${pairs[@]}"; do
        [[ "${pair}" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*$ ]] || return 1
    done

}
config-hosts () {

    local host="" failed=0
    local -A hosts=() seen=()

    parse-map hosts "${CONFIG[WEB_HOSTS]}" || return

    for host in "${CONFIG[API_HOST]}" "${hosts[@]}" "${CONFIG[GRAFANA_HOST]}"; do
        [[ -n "${host}" ]] || continue
        [[ -z "${seen[${host}]:-}" ]] || { err "Host ${host} is routed twice"; failed=1; }
        seen["${host}"]=1
    done

    (( failed == 0 ))

}
config-limits () {

    local rule="" prefix="" other="" failed=0
    local -a prefixes=() entries=()

    [[ -n "${CONFIG[RATE_LIMIT_PATHS]}" ]] || return 0
    IFS=, read -r -a entries <<< "${CONFIG[RATE_LIMIT_PATHS]}"

    for rule in "${entries[@]}"; do
        prefix="${rule%%=*}"

        if ! parse-path "${prefix}" || ! config-valid rate "${rule#*=}"; then
            err "Invalid RATE_LIMIT_PATHS entry: ${rule}"
            failed=1
            continue
        fi

        prefixes+=( "${prefix}" )
    done

    for prefix in "${prefixes[@]}"; do
        for other in "${prefixes[@]}"; do
            [[ "${prefix}" == "${other}" || "${other}" != "${prefix}"* ]] || { err "RATE_LIMIT_PATHS prefixes must not nest: ${prefix} and ${other}"; failed=1; }
        done
    done

    (( failed == 0 ))

}
config-web () {

    local spec="" name="" failed=0
    local -A images=() hosts=() replicas=() names=()

    parse-map images "${CONFIG[WEB_IMAGES]}" || return
    parse-map hosts "${CONFIG[WEB_HOSTS]}" || return
    parse-map replicas "${CONFIG[WEB_REPLICAS]}" || return

    for spec in "${!images[@]}"; do

        name="${spec^^}"
        name="${name//-/_}"

        [[ -z "${names[${name}]:-}" ]] || { err "Web specs collide as ${name}: ${spec}"; failed=1; }
        names["${name}"]="${spec}"

        parse-pinned "${images[${spec}]}" || { err "WEB_IMAGES ${spec} must be pinned by digest"; failed=1; }
        parse-host "${hosts[${spec}]:-}" || { err "WEB_HOSTS requires a host for ${spec}"; failed=1; }

    done

    for spec in "${!hosts[@]}"; do
        [[ -n "${images[${spec}]:-}" ]] || { err "WEB_HOSTS names an unknown spec: ${spec}"; failed=1; }
    done

    for spec in "${!replicas[@]}"; do
        [[ -n "${images[${spec}]:-}" ]] || { err "WEB_REPLICAS names an unknown spec: ${spec}"; failed=1; }
        config-valid replicas "${replicas[${spec}]}" || { err "WEB_REPLICAS ${spec} must be 1..32"; failed=1; }
    done

    (( failed == 0 ))

}
config-required () {

    local key="" failed=0

    cfg-require PROJECT RELEASE API_IMAGE API_HOST DB_NAME DB_USER DB_PASSWORD DB_ADMIN_PASSWORD RABBIT_USER RABBIT_PASSWORD REDIS_PASSWORD || failed=1

    for key in DB_PASSWORD DB_ADMIN_PASSWORD RABBIT_PASSWORD REDIS_PASSWORD; do
        [[ -z "${CONFIG[${key}]}" ]] || (( ${#CONFIG[${key}]} >= 16 )) || { err "${key} needs at least 16 characters"; failed=1; }
    done

    (( failed == 0 ))

}
