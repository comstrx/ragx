source-include module/postgresql.sh || return
source-include module/rabbitmq.sh || return
source-include module/redis.sh || return

native-directory () {

    parse-identifier "${1:-}" || { err "Invalid release: ${1:-}"; return; }

    fs-within "${CONFIG[STATE_ROOT]}" "releases/${1}"

}
native-render () {

    local directory=""

    config-validate || return
    config-required || return
    directory="$(native-directory "${CONFIG[RELEASE]}")" || return

    if [[ -f "${directory}/release.env" ]]; then
        native-release-match "${directory}" || return
    else
        native-render-files "${directory}" || return
        config-release-save "${directory}/release.env" || return
        state-write "${directory}" migration "${CONFIG[MIGRATION_POLICY]}" || return
    fi

    out "${directory}"

}
native-render-files () {

    local directory="${1}" templates="${MANIFEST[paths.templates]}/native" spec="" image="" body=""

    fs-dir "${directory}" || return
    postgresql-render "${directory}" || return
    rabbitmq-render "${directory}" || return
    redis-render "${directory}" || return
    native-api-env "${directory}" || return

    template-render "${templates}/data.yaml.tpl" "${directory}/data.yaml" || return
    template-render "${templates}/application.yaml.tpl" "${directory}/application.yaml" || return

    body='services: {}'

    while IFS= read -r spec; do

        [[ -n "${spec}" ]] || continue
        [[ "${body}" != 'services: {}' ]] || body='services:'

        image="$(native-service-image "web-${spec}")" || return
        cfg-set WEB_SERVICE "web-${spec}"
        cfg-set WEB_IMAGE "${image}"
        cfg-set WEB_VARIABLE "$(native-variable "${spec}")"
        body+=$'\n'"$(template-text "${templates}/web.yaml.tpl")" || return

    done < <(native-specs)

    printf '%s\n' "${body}" | fs-write "${directory}/web.yaml"

}
native-api-env () {

    local directory="${1}" broker="" password="" key=""
    local -a keys=(
        APP_NAME APP_ENV APP_DEBUG APP_HOST APP_PORT APP_WORKERS APP_PREFIX APP_URL APP_RELEASE APP_ORIGINS LOG_RENDERER
        DB_DRIVER DB_HOST DB_PORT DB_DATABASE DB_USERNAME DB_PASSWORD DB_SSLMODE DB_POOL_MAX DB_MIGRATE DB_SEED
        AUTH_SECRET AUTH_KEYS QUEUE_DRIVER QUEUE_URL QUEUE_EXCHANGE QUEUE_WORKERS EVENT_DRIVER EVENT_URL EVENT_EXCHANGE
        CACHE_DRIVER CACHE_URL CACHE_PREFIX BROADCAST_ENABLED BROADCAST_DRIVER BROADCAST_URL SOCKET_ENABLED SCHEDULE_ENABLED
        STORAGE_DISK STORAGE_ROOT STORAGE_MAX_SIZE DOCS_ENABLED MAIL_DRIVER
    )

    broker="$(parse-url-component "${CONFIG[RABBIT_USER]}"):$(parse-url-component "${CONFIG[RABBIT_PASSWORD]}")"
    password="$(parse-url-component "${CONFIG[REDIS_PASSWORD]}")"

    cfg-set APP_NAME "${CONFIG[PROJECT]}"
    cfg-set APP_ENV production
    cfg-set APP_DEBUG false
    cfg-set APP_HOST 0.0.0.0
    cfg-set APP_PORT "${CONFIG[API_PORT]}"
    cfg-set APP_PREFIX "${CONFIG[API_PREFIX]}"
    cfg-set APP_URL "${CONFIG[API_URL]}"
    cfg-set APP_RELEASE "${CONFIG[RELEASE]}"
    cfg-set LOG_RENDERER json
    cfg-set DB_DRIVER postgresql
    cfg-set DB_HOST postgres
    cfg-set DB_PORT 5432
    cfg-set DB_DATABASE "${CONFIG[DB_NAME]}"
    cfg-set DB_USERNAME "${CONFIG[DB_USER]}"
    cfg-set DB_SSLMODE disable
    cfg-set DB_MIGRATE false
    cfg-set DB_SEED false
    cfg-set QUEUE_DRIVER rabbitmq
    cfg-set QUEUE_URL "amqp://${broker}@rabbitmq:5672/"
    cfg-set QUEUE_EXCHANGE "${CONFIG[COMPOSE_PROJECT]}.jobs"
    cfg-set EVENT_DRIVER rabbitmq
    cfg-set EVENT_URL "${CONFIG[QUEUE_URL]}"
    cfg-set EVENT_EXCHANGE "${CONFIG[COMPOSE_PROJECT]}.events"
    cfg-set CACHE_DRIVER redis
    cfg-set CACHE_URL "redis://:${password}@redis:6379/0"
    cfg-set CACHE_PREFIX "${CONFIG[COMPOSE_PROJECT]}:"
    cfg-set BROADCAST_ENABLED true
    cfg-set BROADCAST_DRIVER redis
    cfg-set BROADCAST_URL "redis://:${password}@redis:6379/1"
    cfg-set SOCKET_ENABLED true
    cfg-set SCHEDULE_ENABLED false
    cfg-set STORAGE_DISK public
    cfg-set STORAGE_ROOT /app/storage
    cfg-set STORAGE_MAX_SIZE "${CONFIG[UPLOAD_BYTES]}"
    cfg-set DOCS_ENABLED false

    [[ "${CONFIG[STORAGE_DRIVER]}" != s3 ]] || cfg-set STORAGE_DISK s3

    for key in STORAGE_S3_BUCKET STORAGE_S3_REGION STORAGE_S3_ENDPOINT STORAGE_S3_KEY STORAGE_S3_SECRET MAIL_HOST MAIL_PORT \
        MAIL_USERNAME MAIL_PASSWORD MAIL_SENDER LLM_OPENAI_KEY LLM_ANTHROPIC_KEY LLM_GEMINI_KEY LLM_DEEPSEEK_KEY LLM_LOCAL_URL LLM_LOCAL_KEY; do
        [[ -z "${CONFIG[${key}]}" ]] || keys+=( "${key}" )
    done

    template-compose-env "${directory}/api.env" "${keys[@]}"

}
native-release-match () {

    local directory="${1}" scratch="" expected="" actual="" status=0

    [[ -f "${directory}/release.env" ]] || { err "Release snapshot missing: ${directory}"; return; }
    scratch="$(fs-temp)" || return

    if ( config-release-load "${directory}/release.env" && config-release-save "${scratch}/expected" ) && config-release-save "${scratch}/actual"; then
        expected="$(fs-hash "${scratch}/expected")" || status=$?
        actual="$(fs-hash "${scratch}/actual")" || status=$?
        [[ "${expected}" == "${actual}" ]] || err "Release ${CONFIG[RELEASE]} settings changed; publish under a new RELEASE" || status=$?
    else
        status=1
    fi

    rm -rf -- "${scratch}"
    return "${status}"

}
