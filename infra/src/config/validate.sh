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

    config-check port HTTP_PORT HTTPS_PORT SSH_PORT MAIL_PORT API_PORT WEB_PORT METRICS_PORT PORTAINER_PORT || failed=1
    config-check positive HEALTH_TIMEOUT WARMUP_SECONDS DRAIN_TIMEOUT RETENTION_SECONDS APP_WORKERS QUEUE_WORKERS || failed=1
    config-check positive DB_POOL_MAX UPLOAD_BYTES EDGE_MAXCONN BACKEND_MAXCONN GITOPS_INTERVAL BACKUP_MAX_AGE BACKUP_DAYS PORTAINER_ENDPOINT || failed=1
    config-check replicas API_REPLICAS || failed=1
    config-check workers WORKER_REPLICAS || failed=1
    config-check boolean TLS_ENABLED HTTP3_ENABLED METRICS_ENABLED CLOUDFLARE_PROXIED || failed=1
    config-check path API_READY_PATH WEB_READY_PATH API_PREFIX || failed=1
    config-check address BIND_ADDRESS || failed=1
    config-check memory APP_MEMORY DATA_MEMORY EDGE_MEMORY || failed=1
    config-check megabytes DB_MEMORY || failed=1
    config-check cpus CPUS || failed=1
    config-check pinned IMAGE_POSTGRES IMAGE_RABBITMQ IMAGE_REDIS IMAGE_HAPROXY IMAGE_PORTAINER IMAGE_CURL IMAGE_CERTBOT || failed=1
    config-check https PORTAINER_URL || failed=1
    config-check none,expand MIGRATION_POLICY || failed=1
    config-check blue-green,manual DEPLOY_STRATEGY || failed=1
    config-check portainer,compose DEPLOY_DRIVER || failed=1
    config-check http,dns TLS_CHALLENGE || failed=1
    config-check ghcr,dockerhub REGISTRY_DRIVER || failed=1
    config-check local,s3 STORAGE_DRIVER BACKUP_DRIVER || failed=1
    config-check agent,key,certificate,password SSH_METHOD || failed=1
    config-check roundrobin,leastconn API_BALANCE WEB_BALANCE || failed=1
    config-check blue,green DEPLOY_SLOT || failed=1

    config-check-set identifier PROJECT RELEASE DB_NAME DB_USER RABBIT_USER || failed=1
    config-check-set host API_HOST || failed=1
    config-check-set pinned API_IMAGE || failed=1
    config-check-set https EXTERNAL_HEALTH_URL GITOPS_URL NOTIFY_URL || failed=1

    [[ "${CONFIG[DB_USER]}" != postgres ]] || { err "DB_USER must not be the PostgreSQL superuser"; failed=1; }
    ! cfg-true HTTP3_ENABLED || cfg-true TLS_ENABLED || { err "HTTP3_ENABLED=true requires TLS_ENABLED=true"; failed=1; }
    [[ "${CONFIG[DEPLOY_ENV]}" != production ]] || cfg-true TLS_ENABLED || { err "Production requires TLS_ENABLED=true"; failed=1; }

    config-web || failed=1

    if cfg-true HTTP3_ENABLED && cfg-true CLOUDFLARE_PROXIED && [[ -n "${CONFIG[CLOUDFLARE_TOKEN]}" ]]; then
        warn "Cloudflare proxies this record: public QUIC terminates at Cloudflare and origin HTTP/3 stays unused"
    fi

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

    cfg-require PROJECT RELEASE API_IMAGE API_HOST DB_NAME DB_USER DB_PASSWORD DB_ADMIN_PASSWORD \
        RABBIT_USER RABBIT_PASSWORD REDIS_PASSWORD AUTH_SECRET AUTH_KEYS || failed=1

    for key in DB_PASSWORD DB_ADMIN_PASSWORD RABBIT_PASSWORD REDIS_PASSWORD; do
        [[ -z "${CONFIG[${key}]}" ]] || (( ${#CONFIG[${key}]} >= 16 )) || { err "${key} needs at least 16 characters"; failed=1; }
    done

    [[ -z "${CONFIG[AUTH_SECRET]}" ]] || (( ${#CONFIG[AUTH_SECRET]} >= 32 )) || { err "AUTH_SECRET needs at least 32 characters"; failed=1; }
    [[ "${CONFIG[TLS_CHALLENGE]}" != dns ]] || cfg-require CLOUDFLARE_TOKEN CLOUDFLARE_ZONE || failed=1
    [[ "${CONFIG[STORAGE_DRIVER]}" != s3 ]] || cfg-require STORAGE_S3_BUCKET STORAGE_S3_REGION STORAGE_S3_KEY STORAGE_S3_SECRET || failed=1
    [[ "${CONFIG[BACKUP_DRIVER]}" != s3 ]] || cfg-require BACKUP_S3_URI BACKUP_S3_REGION BACKUP_S3_KEY BACKUP_S3_SECRET || failed=1

    (( failed == 0 ))

}
