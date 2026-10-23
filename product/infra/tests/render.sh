fixture-digest () {

    printf 'sha256:%064d' "${1:-1}"

}
fixture-release () {

    fixture-parts
    cfg-set PROJECT shop
    cfg-set RELEASE r1
    cfg-set DEPLOY_DRIVER compose
    cfg-set CORE_IMAGE "example/core@$(fixture-digest 1)"
    cfg-set CORE_DOMAIN api.shop.test
    cfg-set SHOP_IMAGE ''
    cfg-set SHOP_DOMAIN ''
    cfg-set DESK_IMAGE ''
    cfg-set DESK_DOMAIN ''
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
    export CORE_ENV_FILE=$'APP_ENV=production\nDB_PASSWORD="dollar $ hash # quote \' end"\nAPP_ORIGINS=["https://shop.test"]\n\n'

    config-derive

}
fixture-sites () {

    cfg-set SHOP_IMAGE "example/shop@$(fixture-digest 2)"
    cfg-set SHOP_DOMAIN 'shop.test, www.shop.test'
    cfg-set SHOP_REPLICAS 3
    cfg-set DESK_IMAGE "example/desk@$(fixture-digest 3)"
    cfg-set DESK_DOMAIN shop.test

    config-derive

}
test-render-artifacts () {

    local directory="" text="" file="" digest=""

    fixture-release
    fixture-sites
    directory="$(native-render)"

    for file in postgres.env rabbitmq.env redis.env release.env data.yaml part-core.yaml part-shop.yaml part-desk.yaml; do
        expect-equal "$(fs-mode "${directory}/${file}")" 600 "mode of ${file}"
        text="$(fs-read "${directory}/${file}")"
        expect-absent "${text}" '{{' "placeholders in ${file}"
    done

    expect-equal "$(fs-mode "${directory}/core.env")" 644 'the non-root container reads the env file inside the private release directory'
    expect-equal "$(fs-mode "${directory}")" 700
    expect-equal "$(fs-read "${directory}/core.env")" "$(printf '%s' "${CORE_ENV_FILE}")" 'the application env file passes through untouched'
    expect-fail test -e "${directory}/shop.env"
    digest="$(printf '%s\n' "$(printf '%s' "${CORE_ENV_FILE}")" | fs-hash -)"
    text="$(fs-read "${directory}/release.env")"
    expect-contains "${text}" "CORE_ENV_SHA256='${digest}'"
    expect-contains "${text}" "SHOP_ENV_SHA256=''"
    expect-contains "${text}" "PARTS='core shop desk'"
    expect-contains "${text}" "DESK_PATH='/desk'"
    expect-contains "${text}" "SHOP_DOMAIN='shop.test, www.shop.test'"
    expect-absent "${text}" SHOP_REPLICAS 'replicas are operational'

    text="$(fs-read "${directory}/part-core.yaml")"
    expect-contains "${text}" '  core:'
    expect-contains "${text}" 'scale: ${CORE_REPLICAS:?CORE_REPLICAS required}'
    expect-contains "${text}" "aliases: ['core-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"
    expect-contains "${text}" '{"type": "volume", "source": "storage", "target": "/app/storage"}'
    expect-contains "${text}" '{"type": "bind", "source": "${RELEASE_ROOT:?RELEASE_ROOT required}/core.env", "target": "/app/.env", "read_only": true}'
    expect-contains "${text}" 'command: ["python", "-m", "bootstrap", "serve"]'
    expect-contains "${text}" 'environment: {"APP_HOST": "0.0.0.0", "APP_PORT": "8000", "DB_MIGRATE": "false", "STORAGE_ROOT": "/app/storage", "QUEUE_WORKERS": "0", "SCHEDULE_ENABLED": "false", "APP_RELEASE": "r1"}'
    expect-contains "${text}" '"SCHEDULE_ENABLED": "true", "APP_RELEASE": "r1"}'
    expect-contains "${text}" 'socket.create_connection(("127.0.0.1", 8000), 2)'
    expect-absent "${text}" env_file
    expect-contains "${text}" "image: \"example/core@$(fixture-digest 1)\""
    expect-contains "${text}" 'no-new-privileges:true'
    expect-equal "$(grep -c 'healthcheck: {disable: true}' <<< "${text}")" 2 'worker and scheduler serve no port'
    expect-contains "${text}" "name: 'shop-data'"
    expect-absent "${text}" 'container_name'
    expect-absent "${text}" 'ports:'
    expect-absent "${text}" 'sentinel'

    text="$(fs-read "${directory}/part-shop.yaml")"
    expect-contains "${text}" '  shop:'
    expect-contains "${text}" 'scale: ${SHOP_REPLICAS:?SHOP_REPLICAS required}'
    expect-contains "${text}" "aliases: ['shop-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"
    expect-contains "${text}" 'volumes: []'
    expect-contains "${text}" 'environment: {"PORT": "3000", "HOSTNAME": "0.0.0.0"}'
    expect-contains "${text}" "name: 'shop-apps'"
    expect-absent "${text}" 'name: '"'"'shop-data'"'"

    expect-contains "$(fs-read "${directory}/part-desk.yaml")" '  desk:'
    expect-equal "$(native-interpolation r1 | sort | paste -sd ' ' -)" "CORE_REPLICAS=2 DEPLOY_SLOT=blue DESK_REPLICAS=1 RELEASE_ROOT=${directory} SHOP_REPLICAS=3 WORKER_REPLICAS=1"

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

    cfg-set CORE_REPLICAS 5
    cfg-set DEPLOY_STRATEGY manual
    cfg-set HTTP3_ENABLED false
    expect-equal "$(native-render)" "${directory}" 'operational settings keep the release'

    cfg-set CORE_IMAGE "example/core@$(fixture-digest 9)"
    expect-error 'Release r1 settings changed' native-render

    cfg-set CORE_IMAGE "example/core@$(fixture-digest 1)"
    cfg-set CORE_DOMAIN other.shop.test
    config-derive
    expect-error 'Release r1 settings changed' native-render

    cfg-set CORE_DOMAIN api.shop.test
    config-derive
    export CORE_ENV_FILE='APP_ENV=production'
    expect-error 'Release r1 settings changed' native-render
    fixture-release
    cfg-set CORE_REPLICAS 5

    fixture-sites
    config-release-load "${directory}/release.env"
    expect-equal "${CONFIG[CORE_DOMAIN]}" api.shop.test
    expect-equal "${CONFIG[CORE_REPLICAS]}" 5
    expect-equal "${CONFIG[PARTS]}" core 'a snapshot routes only its own parts'
    expect-equal "${CONFIG[SHOP_IMAGE]}" '' 'a part the snapshot lacks is switched off'
    expect-equal "${CONFIG_SOURCE[CORE_PORT]}" release

    cfg-set PROJECT other
    expect-error 'belongs to another project' config-release-load "${directory}/release.env"

    cfg-set PROJECT shop
    printf "CORE_SPARE='x'\n" >> "${directory}/release.env"
    expect-error 'Unexpected key in release snapshot: CORE_SPARE' config-release-load "${directory}/release.env"

}
test-render-env-files () {

    local directory="" text=""

    fixture-release
    cfg-set CORE_FORCED_ENV 'PRICE=$5 APP_HOST=0.0.0.0'
    cfg-set CORE_SERVE_ENV 'APP_HOST=127.0.0.1'
    cfg-set CORE_SERVE_COMMAND 'serve --price $5'
    fixture-sites
    printf 'NEXT_SECRET=web-sentinel\n' > "$(native-env-file shop)"
    printf 'NEXT_SECRET=desk-sentinel\n' > "$(native-env-file desk)"
    directory="$(native-render)"

    text="$(fs-read "${directory}/part-core.yaml")"
    expect-contains "${text}" 'environment: {"PRICE": "$$5", "APP_HOST": "127.0.0.1", "APP_RELEASE": "r1"}'
    expect-contains "${text}" 'command: ["serve", "--price", "$$5"]'
    expect-equal "$(fs-read "${directory}/shop.env")" NEXT_SECRET=web-sentinel 'without SHOP_ENV_FILE the staged file is used'
    expect-contains "$(fs-read "${directory}/part-shop.yaml")" '"source": "${RELEASE_ROOT:?RELEASE_ROOT required}/shop.env", "target": "/srv/.env"'
    expect-absent "$(fs-read "${directory}/part-shop.yaml")" web-sentinel
    expect-fail test -e "${directory}/desk.env"
    expect-contains "$(fs-read "${directory}/part-desk.yaml")" 'volumes: []' 'a part without env_mount never mounts a file'

    printf -v SHOP_ENV_FILE '%s' unexported-value
    expect-equal "${SHOP_ENV_FILE}" unexported-value
    expect-equal "$(native-env-content shop)" NEXT_SECRET=web-sentinel 'an unexported variable is ignored'
    unset SHOP_ENV_FILE

    CORE_ENV_FILE="$(printf 'APP_ENV=production\nAUTH_SECRET=base64-sentinel\n' | openssl base64 -A)"
    expect-equal "$(native-env-content core)" $'APP_ENV=production\nAUTH_SECRET=base64-sentinel' 'a single base64 line decodes'
    CORE_ENV_FILE='APP_ENV=production'
    expect-equal "$(native-env-content core)" APP_ENV=production 'plain text stays as written'

    cfg-set RELEASE r2
    rm -f -- "$(native-env-file shop)"
    directory="$(native-render)"
    expect-fail test -e "${directory}/shop.env"
    expect-absent "$(fs-read "${directory}/part-shop.yaml")" '/srv/.env'
    expect-contains "$(fs-read "${directory}/release.env")" "SHOP_ENV_SHA256=''"
    expect-equal "$(fs-read "${directory}/core.env")" APP_ENV=production

    unset CORE_ENV_FILE
    expect-error 'core env content missing: export CORE_ENV_FILE or stage .env.core' native-env-content core
    export CORE_ENV_FILE=$'A=1\r\nB=2'
    expect-error 'CORE_ENV_FILE has carriage returns' native-env-content core
    CORE_ENV_FILE="$(printf 'K=%049152d' 0)"
    export CORE_ENV_FILE
    expect-error 'CORE_ENV_FILE exceeds 48 KiB' native-env-content core

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
    cfg-set CORE_REPLICAS 7
    native-release-id
    expect-equal "${CONFIG[RELEASE]}" "${first}" 'operational settings keep the name'

    cfg-set RELEASE ''
    export CORE_ENV_FILE='APP_ENV=production'
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

    cfg-set PART_IMAGE '{{RELEASE}}'
    expect-error 'Nested placeholder in PART_IMAGE' template-text "${MANIFEST[paths.templates]}/native/server.yaml.tpl"

}
test-render-compose-without-secrets () {

    local directory="${TMPDIR}/compose" text=""

    fixture-parts
    cfg-set PROJECT shop
    cfg-set RELEASE r1
    cfg-set CORE_IMAGE "example/core@$(fixture-digest 1)"
    cfg-set CORE_DOMAIN api.shop.test
    fixture-sites

    native-render-compose "${directory}"
    expect-fail test -e "${directory}/core.env"
    text="$(fs-read "${directory}/part-core.yaml")$(fs-read "${directory}/part-shop.yaml")"
    expect-contains "${text}" '  shop:'
    expect-absent "${text}" '{{'
    expect-equal "$(native-compose-files "${directory}" | paste -sd ' ' -)" "-f ${directory}/part-core.yaml -f ${directory}/part-desk.yaml -f ${directory}/part-shop.yaml"
    expect-fail config-required

}
test-render-monitoring () {

    local directory="${TMPDIR}/monitor" text="" file="" first=""

    fixture-release
    cfg-set GRAFANA_DOMAIN grafana.shop.test
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
    expect-contains "${text}" "--storage.tsdb.retention.time=${CONFIG[METRICS_RETENTION]}s"
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
