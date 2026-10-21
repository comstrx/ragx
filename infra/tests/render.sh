fixture-digest () {

    printf 'sha256:%064d' "${1:-1}"

}
fixture-release () {

    cfg-set PROJECT shop
    cfg-set RELEASE r1
    cfg-set DEPLOY_DRIVER compose
    cfg-set API_IMAGE "example/api@$(fixture-digest 1)"
    cfg-set API_HOST api.shop.test
    cfg-set TLS_ENABLED false
    cfg-set HTTP3_ENABLED false
    cfg-set EDGE_SOCKETS ''
    cfg-set DB_NAME shop
    cfg-set DB_USER shopper
    cfg-set DB_PASSWORD "dollar \$ quote ' backslash \\ line
end"
    cfg-set DB_ADMIN_PASSWORD admin-sentinel-0123456789
    cfg-set RABBIT_USER rabbit
    cfg-set RABBIT_PASSWORD 'rabbit@:/ sentinel-01'
    cfg-set REDIS_PASSWORD 'redis@:/"sentinel-02'
    export API_ENV_FILE=$'APP_ENV=production\nDB_PASSWORD="dollar $ hash # quote \' end"\nAPP_ORIGINS=["https://shop.test"]\n\n'

    config-derive

}
fixture-web () {

    cfg-set WEB_IMAGES "client=example/client@$(fixture-digest 2),admin=example/admin@$(fixture-digest 3)"
    cfg-set WEB_HOSTS 'client=shop.test,admin=admin.shop.test'
    cfg-set WEB_REPLICAS 'client=3'

    config-derive

}
test-render-artifacts () {

    local directory="" text="" file="" digest=""

    fixture-release
    fixture-web
    directory="$(native-render)"

    for file in postgres.env rabbitmq.env redis.env release.env application.yaml data.yaml web.yaml; do
        expect-equal "$(fs-mode "${directory}/${file}")" 600 "mode of ${file}"
        text="$(fs-read "${directory}/${file}")"
        expect-absent "${text}" '{{' "placeholders in ${file}"
    done

    expect-equal "$(fs-mode "${directory}/api.env")" 644 'the non-root container reads the env file inside the private release directory'
    expect-equal "$(fs-mode "${directory}")" 700
    expect-equal "$(fs-read "${directory}/api.env")" "$(printf '%s' "${API_ENV_FILE}")" 'the application env file passes through untouched'
    expect-fail test -e "${directory}/web.env"
    digest="$(printf '%s\n' "$(printf '%s' "${API_ENV_FILE}")" | fs-hash -)"
    expect-contains "$(fs-read "${directory}/release.env")" "API_ENV_SHA256='${digest}'"
    expect-contains "$(fs-read "${directory}/release.env")" "WEB_ENV_SHA256=''"

    text="$(fs-read "${directory}/application.yaml")"
    expect-contains "${text}" 'scale: ${API_REPLICAS:?API_REPLICAS required}'
    expect-contains "${text}" "aliases: ['api-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"
    expect-contains "${text}" '{"type": "volume", "source": "storage", "target": "/app/storage"}'
    expect-contains "${text}" '{"type": "bind", "source": "${RELEASE_ROOT:?RELEASE_ROOT required}/api.env", "target": "/app/.env", "read_only": true}'
    expect-contains "${text}" 'command: ["python", "-m", "bootstrap", "serve"]'
    expect-contains "${text}" 'environment: {"APP_HOST": "0.0.0.0", "APP_PORT": "8000", "DB_MIGRATE": "false", "STORAGE_ROOT": "/app/storage", "QUEUE_WORKERS": "0", "SCHEDULE_ENABLED": "false", "APP_RELEASE": "r1"}'
    expect-contains "${text}" '"SCHEDULE_ENABLED": "true", "APP_RELEASE": "r1"}'
    expect-absent "${text}" env_file
    expect-contains "${text}" "image: \"example/api@$(fixture-digest 1)\""
    expect-contains "${text}" 'no-new-privileges:true'
    expect-equal "$(grep -c 'healthcheck: {disable: true}' <<< "${text}")" 2 'worker and scheduler serve no port'
    expect-contains "${text}" "name: 'shop-data'"
    expect-absent "${text}" 'container_name'
    expect-absent "${text}" 'ports:'
    expect-absent "${text}" 'sentinel'

    text="$(fs-read "${directory}/web.yaml")"
    expect-contains "${text}" '  web-admin:'
    expect-contains "${text}" '  web-client:'
    expect-contains "${text}" 'scale: ${WEB_CLIENT_REPLICAS:?WEB_CLIENT_REPLICAS required}'
    expect-contains "${text}" "aliases: ['web-client-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"
    expect-contains "${text}" 'volumes: []'
    expect-contains "${text}" 'environment: {"PORT": "3000", "HOSTNAME": "0.0.0.0"}'

    text="$(fs-read "${directory}/data.yaml")"
    expect-contains "${text}" "name: 'shop-postgres'"
    expect-absent "${text}" 'sentinel'
    expect-contains "${text}" "source: \"${CONFIG[STATE_ROOT]}/backups/wal\""
    expect-contains "${text}" 'target: /wal'
    expect-contains "${text}" '- archive_mode=on'
    expect-contains "${text}" '- archive_timeout=60'
    expect-contains "${text}" "'archive_command=test ! -f /wal/enabled || test -f /wal/archive/%f || { cp %p /wal/archive/%f.part && mv /wal/archive/%f.part /wal/archive/%f; }'"
    expect-contains "$(fs-read "${directory}/pg_hba.conf")" $'local all postgres peer\nlocal replication postgres peer\nlocal all all reject'

}
test-render-immutable () {

    local directory=""

    fixture-release
    directory="$(native-render)"
    expect-equal "$(native-render)" "${directory}"

    cfg-set API_REPLICAS 5
    cfg-set DEPLOY_STRATEGY manual
    cfg-set HTTP3_ENABLED false
    expect-equal "$(native-render)" "${directory}" 'operational settings keep the release'

    cfg-set API_IMAGE "example/api@$(fixture-digest 9)"
    expect-error 'Release r1 settings changed' native-render

    cfg-set API_IMAGE "example/api@$(fixture-digest 1)"
    cfg-set API_HOST other.shop.test
    config-derive
    expect-error 'Release r1 settings changed' native-render

    cfg-set API_HOST api.shop.test
    config-derive
    export API_ENV_FILE='APP_ENV=production'
    expect-error 'Release r1 settings changed' native-render
    fixture-release

    config-release-load "${directory}/release.env"
    expect-equal "${CONFIG[API_HOST]}" api.shop.test
    expect-equal "${CONFIG[API_REPLICAS]}" 5

    cfg-set PROJECT other
    expect-error 'belongs to another project' config-release-load "${directory}/release.env"

}
test-render-env-files () {

    local directory="" text=""

    fixture-release
    cfg-set API_FORCED_ENV 'PRICE=$5 APP_HOST=0.0.0.0'
    cfg-set API_SERVE_ENV 'APP_HOST=127.0.0.1'
    cfg-set API_SERVE_COMMAND 'serve --price $5'
    cfg-set WEB_ENV_MOUNT /srv/.env
    fixture-web
    printf 'NEXT_SECRET=web-sentinel\n' > "$(native-env-file WEB)"
    directory="$(native-render)"

    text="$(fs-read "${directory}/application.yaml")"
    expect-contains "${text}" 'environment: {"PRICE": "$$5", "APP_HOST": "127.0.0.1", "APP_RELEASE": "r1"}'
    expect-contains "${text}" 'command: ["serve", "--price", "$$5"]'
    expect-equal "$(fs-read "${directory}/web.env")" NEXT_SECRET=web-sentinel 'without WEB_ENV_FILE the staged file is used'
    expect-contains "$(fs-read "${directory}/web.yaml")" '"source": "${RELEASE_ROOT:?RELEASE_ROOT required}/web.env", "target": "/srv/.env"'
    expect-absent "$(fs-read "${directory}/web.yaml")" web-sentinel

    printf -v WEB_ENV_FILE '%s' unexported-value
    expect-equal "${WEB_ENV_FILE}" unexported-value
    expect-equal "$(native-env-content WEB)" NEXT_SECRET=web-sentinel 'an unexported variable is ignored'
    unset WEB_ENV_FILE

    API_ENV_FILE="$(printf 'APP_ENV=production\nAUTH_SECRET=base64-sentinel\n' | openssl base64 -A)"
    expect-equal "$(native-env-content API)" $'APP_ENV=production\nAUTH_SECRET=base64-sentinel' 'a single base64 line decodes'
    API_ENV_FILE='APP_ENV=production'
    expect-equal "$(native-env-content API)" APP_ENV=production 'plain text stays as written'

    cfg-set RELEASE r2
    rm -f -- "$(native-env-file WEB)"
    directory="$(native-render)"
    expect-fail test -e "${directory}/web.env"
    expect-absent "$(fs-read "${directory}/web.yaml")" '/srv/.env'
    expect-contains "$(fs-read "${directory}/release.env")" "WEB_ENV_SHA256=''"
    expect-equal "$(fs-read "${directory}/api.env")" APP_ENV=production

    unset API_ENV_FILE
    expect-error 'API env content missing: export API_ENV_FILE or stage .env.api' native-env-content API
    export API_ENV_FILE=$'A=1\r\nB=2'
    expect-error 'API_ENV_FILE has carriage returns' native-env-content API
    API_ENV_FILE="$(printf 'K=%049152d' 0)"
    export API_ENV_FILE
    expect-error 'API_ENV_FILE exceeds 48 KiB' native-env-content API

}
test-render-release-id () {

    local first=""

    fixture-release
    cfg-set RELEASE ''
    cfg-set VERSION v1-4-0
    native-release-id
    first="${CONFIG[RELEASE]}"
    [[ "${first}" =~ ^v1-4-0-[a-f0-9]{8}$ ]] || err "Unexpected release name: ${first}"

    cfg-set RELEASE ''
    cfg-set API_REPLICAS 7
    native-release-id
    expect-equal "${CONFIG[RELEASE]}" "${first}" 'operational settings keep the name'

    cfg-set RELEASE ''
    export API_ENV_FILE='APP_ENV=production'
    native-release-id
    [[ "${CONFIG[RELEASE]}" != "${first}" ]] || err "A changed application env kept the release name"

    fixture-release
    cfg-set RELEASE ''
    cfg-set APP_MEMORY 1g
    native-release-id
    [[ "${CONFIG[RELEASE]}" != "${first}" && "${CONFIG[RELEASE]}" == v1-4-0-* ]] || err "A changed pinned setting kept the release name"

    cfg-set RELEASE pinned
    native-release-id
    expect-equal "${CONFIG[RELEASE]}" pinned 'an explicit RELEASE wins'

    cfg-set RELEASE ''
    cfg-set VERSION ''
    expect-error 'Missing setting: VERSION or RELEASE' native-release-id
    cfg-set VERSION "v$(printf '%060d' 1)"
    expect-error 'VERSION is too long for a release name' native-release-id

}
test-render-template-failure () {

    local destination="${TMPDIR}/out"

    printf 'preserved\n' > "${destination}"
    expect-error 'Missing asset' template-render missing.tpl "${destination}"
    expect-equal "$(fs-read "${destination}")" preserved

    expect-error 'Unknown setting: UNKNOWN' template-env "${destination}" PROJECT UNKNOWN
    expect-equal "$(fs-read "${destination}")" preserved

    cfg-set API_IMAGE '{{RELEASE}}'
    expect-error 'Nested placeholder in API_IMAGE' template-text "${MANIFEST[paths.templates]}/native/application.yaml.tpl"

}
test-render-compose-without-secrets () {

    local directory="${TMPDIR}/compose" text=""

    cfg-set PROJECT shop
    cfg-set RELEASE r1
    cfg-set API_IMAGE "example/api@$(fixture-digest 1)"
    cfg-set API_HOST api.shop.test
    fixture-web

    native-render-compose "${directory}"
    expect-fail test -e "${directory}/api.env"
    text="$(fs-read "${directory}/application.yaml")$(fs-read "${directory}/web.yaml")"
    expect-contains "${text}" '  web-client:'
    expect-absent "${text}" '{{'
    expect-fail config-required

}
test-render-monitoring () {

    local directory="${TMPDIR}/monitor" text="" file="" first=""

    fixture-release
    cfg-set GRAFANA_HOST grafana.shop.test
    cfg-set GRAFANA_PASSWORD grafana-sentinel-password
    cfg-set MONITOR_USER 1000:1000
    config-derive
    monitoring-render "${directory}"

    for file in monitor.yaml prometheus/prometheus.yml prometheus/rules.yml grafana/datasources/prometheus.yaml \
        grafana/dashboards/platform.yaml grafana/dashboards/platform.json secrets/grafana-password secrets/db-password; do
        expect-equal "$(fs-mode "${directory}/${file}")" 600 "mode of ${file}"
        expect-absent "$(fs-read "${directory}/${file}")" '{{' "placeholders in ${file}"
    done

    text="$(fs-read "${directory}/monitor.yaml")"
    expect-contains "${text}" 'user: "1000:1000"'
    expect-contains "${text}" 'GF_SERVER_ROOT_URL: "http://grafana.shop.test"'
    expect-contains "${text}" 'GF_SECURITY_ADMIN_PASSWORD__FILE: /run/secrets/grafana-password'
    expect-contains "${text}" 'DATA_SOURCE_USER: "shopper"'
    expect-contains "${text}" "name: 'shop-apps'"
    expect-contains "${text}" "--storage.tsdb.retention.time=${CONFIG[METRICS_RETENTION]}"
    expect-absent "${text}" sentinel
    expect-absent "${text}" alertmanager
    expect-absent "$(fs-read "${directory}/prometheus/prometheus.yml")" alerting
    expect-contains "$(fs-read "${directory}/prometheus/rules.yml")" "platform_backup_timestamp_seconds > ${CONFIG[BACKUP_MAX_AGE]}"
    expect-equal "$(fs-read "${directory}/secrets/grafana-password")" grafana-sentinel-password
    expect-equal "$(fs-read "${directory}/secrets/db-password")" "${CONFIG[DB_PASSWORD]}"
    jq -e '.uid == "platform" and (.panels | length) > 10' "${directory}/grafana/dashboards/platform.json" >/dev/null || err "Dashboard is not valid"

    first="$(monitoring-fingerprint "${directory}")"
    expect-equal "$(monitoring-fingerprint "${directory}")" "${first}" 'fingerprints are stable'

    cfg-set TELEGRAM_BOT_TOKEN '123456:alert-sentinel-token-0123456789'
    cfg-set TELEGRAM_CHAT_ID -100123
    rm -rf -- "${directory}"
    monitoring-render "${directory}"

    text="$(fs-read "${directory}/monitor.yaml")"
    expect-contains "${text}" '  alertmanager:'
    expect-contains "${text}" './secrets/telegram-token:/run/secrets/telegram-token:ro'
    expect-absent "${text}" alert-sentinel
    expect-contains "$(fs-read "${directory}/prometheus/prometheus.yml")" "targets: ['alertmanager:9093']"
    text="$(fs-read "${directory}/alertmanager/alertmanager.yml")"
    expect-contains "${text}" 'chat_id: -100123'
    expect-contains "${text}" 'bot_token_file: /run/secrets/telegram-token'
    expect-absent "${text}" alert-sentinel
    expect-equal "$(fs-read "${directory}/secrets/telegram-token")" '123456:alert-sentinel-token-0123456789'
    expect-equal "$(fs-mode "${directory}/secrets/telegram-token")" 600
    expect-absent "${text}" slack_configs
    [[ "$(monitoring-fingerprint "${directory}")" != "${first}" ]] || err "Alert settings did not change the fingerprint"

}
