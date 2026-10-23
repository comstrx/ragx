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
        percent)    parse-count "${value}" && (( value <= 100 )) ;;
        count)      parse-count "${value}" ;;
        rate)       [[ "${value}" =~ ^[1-9][0-9]{0,8}/[1-9][0-9]{0,4}[smh]$ ]] ;;
        bucket)     [[ "${value}" =~ ^(s3|gs)://[a-z0-9][a-z0-9._-]{1,62}(/[A-Za-z0-9/_.-]*)?$ ]] ;;
        bot)        [[ "${value}" =~ ^[0-9]{1,20}:[A-Za-z0-9_-]{20,64}$ ]] ;;
        chat)       [[ "${value}" =~ ^-?[1-9][0-9]{0,19}$ ]] ;;
        variable)   [[ "${value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ;;
        extensions) [[ "${value}" =~ ^([a-z][a-z0-9_]{0,62}(,[a-z][a-z0-9_]{0,62})*)?$ ]] ;;
        header)     [[ "${value}" =~ ^[A-Za-z][A-Za-z0-9-]{0,63}$ ]] ;;
        email)      [[ "${value}" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63}$ ]] ;;
        branch)     git-ref "${value}" ;;
        region)     [[ "${value}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] ;;
        namespace)  [[ "${value}" =~ ^[a-z0-9]+([._-][a-z0-9]+)*$ ]] ;;
        target)     [[ "${value}" =~ ^[A-Za-z0-9][A-Za-z0-9.:-]*$ ]] ;;
        user)       [[ "${value}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]] ;;
        domains)    config-domains "${value}" ;;
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
        if [[ "${CONFIG[${key}]-}" =~ ^[[:space:]]|[[:space:]]$ ]]; then err "Invalid ${key}: spaces or a line break around the value; check how it was pasted"; failed=1
        elif ! config-valid "${kind}" "${CONFIG[${key}]-}"; then err "Invalid ${key}: expected ${kind//,/|}"; failed=1
        fi
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

    local server="" name="" failed=0
    local -a domains=() images=() replicas=() parts=()

    server="$(config-server)"
    server="${server^^}"

    for name in "${CONFIG_PARTS[@]}"; do
        domains+=( "${name^^}_DOMAIN" )
        parts+=( "${name^^}_IMAGE" )
        replicas+=( "${name^^}_REPLICAS" )
    done

    for name in "${!MANIFEST[@]}"; do
        [[ "${name}" != images.* ]] || images+=( "IMAGE_${name#images.}" )
    done

    images=( "${images[@]^^}" )
    images=( "${images[@]//-/_}" )

    config-check port HTTP_PORT HTTPS_PORT SSH_PORT METRICS_PORT PORTAINER_PORT || failed=1
    config-check positive HEALTH_TIMEOUT WARMUP_SECONDS DRAIN_TIMEOUT RETENTION_SECONDS || failed=1
    config-check positive EDGE_MAXCONN BACKEND_MAXCONN GITOPS_INTERVAL BACKUP_MAX_AGE BACKUP_RETENTION PORTAINER_ENDPOINT || failed=1
    config-check positive VERIFY_SECONDS VERIFY_FAILURES VERIFY_INTERVAL MONITOR_INTERVAL BACKUP_INTERVAL RENEW_INTERVAL || failed=1
    config-check positive BACKUP_ARCHIVE_INTERVAL METRICS_RETENTION CERTIFICATE_BATCH CERTIFICATE_RETRY || failed=1
    config-check count CERTIFICATE_RETENTION || failed=1
    config-check count DOMAINS_INTERVAL || failed=1
    config-check percent DOMAINS_MAX_DROP || failed=1
    config-check replicas "${replicas[@]}" || failed=1
    config-check workers WORKER_REPLICAS || failed=1
    config-check boolean TLS_ENABLED TLS_STAGING HTTP3_ENABLED METRICS_ENABLED BACKUP_WAL || failed=1
    config-check path "${server}_STORAGE_MOUNT" || failed=1
    config-check relative GITOPS_DESIRED GITOPS_COMPOSE || failed=1
    config-check extensions DB_EXTENSIONS || failed=1
    config-check command "${server}_SERVE_COMMAND" "${server}_WORK_COMMAND" "${server}_SCHEDULE_COMMAND" || failed=1
    config-check pairs "${server}_FORCED_ENV" "${server}_SERVE_ENV" "${server}_WORK_ENV" "${server}_SCHEDULE_ENV" || failed=1
    config-check address BIND_ADDRESS || failed=1
    config-check memory APP_MEMORY DATA_MEMORY EDGE_MEMORY || failed=1
    config-check megabytes DB_MEMORY || failed=1
    config-check cpus CPUS || failed=1
    config-check pinned "${images[@]}" || failed=1
    config-check https PORTAINER_URL || failed=1
    config-check none,expand MIGRATION_POLICY || failed=1
    config-check blue-green,manual DEPLOY_STRATEGY || failed=1
    config-check portainer,compose DEPLOY_DRIVER || failed=1
    config-check ghcr,dockerhub REGISTRY_DRIVER || failed=1
    config-check auto,agent,key,certificate,password SSH_METHOD || failed=1
    config-check blue,green DEPLOY_SLOT || failed=1

    config-check-set identifier PROJECT VERSION RELEASE DB_NAME DB_USER RABBIT_USER || failed=1
    config-check-set domains "${domains[@]}" GRAFANA_DOMAIN || failed=1
    config-check-set pinned "${parts[@]}" || failed=1
    config-models-valid || failed=1
    config-check-set path MODELS_DIR || failed=1
    config-check-set https EXTERNAL_HEALTH_URL GITOPS_URL DOMAINS_ENDPOINT || failed=1
    config-check-set rate RATE_LIMIT_GLOBAL RATE_LIMIT_IP || failed=1
    config-check-set bucket BACKUP_URI || failed=1
    config-check-set path EDGE_SOCKETS || failed=1
    config-check-set https BACKUP_ENDPOINT || failed=1
    config-check-set path BACKUP_DIR || failed=1
    config-check-set proxies TRUSTED_PROXIES || failed=1
    config-check-set header TRUSTED_HEADER || failed=1
    config-check-set bot TELEGRAM_BOT_TOKEN || failed=1
    config-check-set chat TELEGRAM_CHAT_ID || failed=1
    config-check-set webhook SLACK_WEBHOOK_URL WEBHOOK_URL || failed=1
    config-check retries NOTIFY_RETRIES || failed=1
    config-check-set variable "${server}_RELEASE_VARIABLE" || failed=1
    config-check-set command "${server}_MIGRATE_COMMAND" || failed=1
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
    [[ "${CONFIG[MIGRATION_POLICY]}" != expand || -n "${CONFIG[${server}_MIGRATE_COMMAND]}" ]] || { err "MIGRATION_POLICY=expand requires ${server}_MIGRATE_COMMAND"; failed=1; }
    ! cfg-true HTTP3_ENABLED || cfg-true TLS_ENABLED || { err "HTTP3_ENABLED=true requires TLS_ENABLED=true"; failed=1; }
    [[ "${CONFIG[ENV_MODE]}" != production ]] || cfg-true TLS_ENABLED || { err "Production requires TLS_ENABLED=true"; failed=1; }
    [[ "${CONFIG[ENV_MODE]}" != production ]] || ! cfg-true TLS_STAGING || warn "TLS_STAGING=true issues untrusted staging certificates; turn it off once the first deploy is proven"

    config-routes || failed=1
    config-limits || failed=1
    config-group BACKUP_URI BACKUP_KEY BACKUP_SECRET || failed=1
    config-group TRUSTED_PROXIES TRUSTED_HEADER || failed=1
    config-group TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID || failed=1
    config-group GRAFANA_DOMAIN GRAFANA_PASSWORD || failed=1
    config-group REGISTRY_USER REGISTRY_TOKEN || failed=1
    config-group GITOPS_URL GITOPS_USER GITOPS_TOKEN || failed=1

    [[ -z "${CONFIG[GRAFANA_PASSWORD]}" ]] || (( ${#CONFIG[GRAFANA_PASSWORD]} >= 12 )) || { err "GRAFANA_PASSWORD needs at least 12 characters"; failed=1; }
    config-domains-on || [[ -z "${CONFIG[DOMAINS_ENDPOINT]}${CONFIG[DOMAINS_TOKEN]}" || "${CONFIG[DOMAINS_INTERVAL]}" == 0 ]] || warn "Dynamic domains stay off: they need DOMAINS_ENDPOINT, DOMAINS_TOKEN and a DOMAINS_INTERVAL above 0"
    [[ -z "${CONFIG[WEBHOOK_SECRET]}" || -n "${CONFIG[WEBHOOK_URL]}" ]] || { err "WEBHOOK_SECRET signs WEBHOOK_URL deliveries; set WEBHOOK_URL"; failed=1; }
    [[ -z "${CONFIG[GITOPS_URL]}" || -n "${CONFIG[REGISTRY_TOKEN]}" ]] || warn "GitOps pulls private images only with a permanent REGISTRY_TOKEN on the server"

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
config-domains () {

    local item=""
    local -a items=()

    [[ "${1-}" != *$'\n'* ]] || return 1
    IFS=$' \t,' read -r -a items <<< "${1-}"

    for item in "${items[@]}"; do
        [[ -z "${item}" ]] || parse-host "${item}" || return 1
    done

}
config-routes () {

    local name="" domain="" route="" failed=0
    local -A seen=()

    for name in "${CONFIG_PARTS[@]}" grafana; do

        if [[ "${name}" == grafana ]]; then
            route=/
            domain="${CONFIG[GRAFANA_DOMAIN]}"
        else
            route="${CONFIG[${name^^}_PATH]}"
            domain="${CONFIG[${name^^}_DOMAIN]}"
        fi

        while IFS= read -r domain; do
            [[ -n "${domain}" ]] || continue
            [[ -z "${seen[${domain}${route}]:-}" ]] || { err "${domain}${route%/} is routed to ${seen[${domain}${route}]} and ${name}"; failed=1; }
            seen["${domain}${route}"]="${name}"
        done < <(config-list "${domain}")

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
config-required () {

    local key="" failed=0

    cfg-require PROJECT RELEASE DB_NAME DB_USER DB_PASSWORD DB_ADMIN_PASSWORD RABBIT_USER RABBIT_PASSWORD REDIS_PASSWORD || failed=1
    config-deployable || failed=1

    for key in DB_PASSWORD DB_ADMIN_PASSWORD RABBIT_PASSWORD REDIS_PASSWORD; do
        [[ -z "${CONFIG[${key}]}" ]] || (( ${#CONFIG[${key}]} >= 16 )) || { err "${key} needs at least 16 characters"; failed=1; }
    done

    (( failed == 0 ))

}
config-deployable () {

    [[ -n "${CONFIG[PARTS]}" ]] || { err "No part has both a domain and an image; set a <PART>_DOMAIN and its <PART>_IMAGE"; return; }

}
