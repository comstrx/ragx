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
    cfg-set DB_NAME shop
    cfg-set DB_USER shopper
    cfg-set DB_PASSWORD "dollar \$ quote ' backslash \\ line
end"
    cfg-set DB_ADMIN_PASSWORD admin-sentinel-0123456789
    cfg-set RABBIT_USER rabbit
    cfg-set RABBIT_PASSWORD 'rabbit@:/ sentinel-01'
    cfg-set REDIS_PASSWORD 'redis@:/"sentinel-02'
    cfg-set AUTH_SECRET 01234567890123456789012345678901
    cfg-set AUTH_KEYS '["MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="]'

    config-derive

}
fixture-web () {

    cfg-set WEB_IMAGES "client=example/client@$(fixture-digest 2),admin=example/admin@$(fixture-digest 3)"
    cfg-set WEB_HOSTS 'client=shop.test,admin=admin.shop.test'
    cfg-set WEB_REPLICAS 'client=3'

    config-derive

}
test-render-artifacts () {

    local directory="" text="" file=""
    local -A parsed=()

    fixture-release
    fixture-web
    directory="$(native-render)"

    for file in api.env postgres.env rabbitmq.env redis.env release.env application.yaml data.yaml web.yaml; do
        expect-equal "$(fs-mode "${directory}/${file}")" 600 "mode of ${file}"
        text="$(fs-read "${directory}/${file}")"
        expect-absent "${text}" '{{' "placeholders in ${file}"
    done

    parse-pairs parsed "${directory}/api.env"
    expect-equal "${parsed[DB_PASSWORD]}" "${CONFIG[DB_PASSWORD]}"
    expect-equal "${parsed[QUEUE_URL]}" 'amqp://rabbit:rabbit%40%3A%2F%20sentinel-01@rabbitmq:5672/'
    expect-equal "${parsed[CACHE_URL]}" 'redis://:redis%40%3A%2F%22sentinel-02@redis:6379/0'
    expect-equal "${parsed[APP_URL]}" http://api.shop.test
    expect-equal "${parsed[APP_ORIGINS]}" '["http://admin.shop.test","http://shop.test"]'
    expect-equal "${parsed[DB_MIGRATE]}" false
    expect-equal "${parsed[DOCS_ENABLED]}" false
    expect-equal "${parsed[APP_WORKERS]}" "${CONFIG[APP_WORKERS]}"
    expect-equal "${parsed[MAIL_SENDER]-unset}" unset 'empty providers keep the API default'

    text="$(fs-read "${directory}/application.yaml")"
    expect-contains "${text}" 'scale: ${API_REPLICAS:?API_REPLICAS required}'
    expect-contains "${text}" "aliases: ['api-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"
    expect-contains "${text}" "env_file: ['\${RELEASE_ROOT:?RELEASE_ROOT required}/api.env']"
    expect-contains "${text}" "image: \"example/api@$(fixture-digest 1)\""
    expect-contains "${text}" 'no-new-privileges:true'
    expect-equal "$(grep -c 'healthcheck: {disable: true}' <<< "${text}")" 2 'worker and scheduler serve no port'
    expect-contains "${text}" "name: 'shop-staging-data'"
    expect-absent "${text}" 'container_name'
    expect-absent "${text}" 'ports:'
    expect-absent "${text}" 'sentinel'

    text="$(fs-read "${directory}/web.yaml")"
    expect-contains "${text}" '  web-admin:'
    expect-contains "${text}" '  web-client:'
    expect-contains "${text}" 'scale: ${WEB_CLIENT_REPLICAS:?WEB_CLIENT_REPLICAS required}'
    expect-contains "${text}" "aliases: ['web-client-\${DEPLOY_SLOT:?DEPLOY_SLOT required}']"

    text="$(fs-read "${directory}/data.yaml")"
    expect-contains "${text}" "name: 'shop-staging-postgres'"
    expect-absent "${text}" 'sentinel'

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

    config-release-load "${directory}/release.env"
    expect-equal "${CONFIG[API_HOST]}" api.shop.test
    expect-equal "${CONFIG[API_REPLICAS]}" 5

    cfg-set PROJECT other
    expect-error 'belongs to another project' config-release-load "${directory}/release.env"

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
