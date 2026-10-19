redis-render () {

    local value="${CONFIG[REDIS_PASSWORD]}"

    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"

    cfg-set REDISCLI_AUTH "${CONFIG[REDIS_PASSWORD]}"
    cfg-set REDIS_CONFIG "$(printf 'appendonly yes\nsave 900 1\nprotected-mode yes\nrequirepass "%s"\n' "${value}")"

    template-compose-env "${1}/redis.env" REDISCLI_AUTH REDIS_CONFIG

}
