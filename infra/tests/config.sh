test-config-schema () {

    local key="" schema=""

    schema="$(asset-text .env.example)"

    for key in "${CONFIG_SCHEMA[@]}"; do
        expect-contains "${schema}" $'\n'"${key}=" "schema key ${key}"
    done

    expect-equal "${CONFIG[HTTP3_ENABLED]}" true
    expect-equal "${CONFIG[TLS_ENABLED]}" true
    expect-equal "${CONFIG[DEPLOY_STRATEGY]}" blue-green
    expect-equal "${CONFIG_SOURCE[HTTP3_ENABLED]}" defaults
    expect-equal "${CONFIG[API_BALANCE]}" leastconn
    expect-equal "${CONFIG[WEB_BALANCE]}" roundrobin
    expect-equal "${CONFIG_SOURCE[HEALTH_TIMEOUT]}" manifest
    expect-equal "${CONFIG[STATE_ROOT]}" "${CONFIG[PROJECT_ROOT]}/.infra/unconfigured-staging"
    expect-fail config-schema-key HEALTH_TIMEOUT
    expect-fail config-schema-key CDN_MODE
    config-schema-key HTTP3_ENABLED

}
test-config-precedence () {

    local root="${TMPDIR}/project"

    mkdir -p "${root}"
    printf '%s\n' 'PROJECT=file' 'RELEASE=file' 'API_HOST=file.example.com' > "${root}/.env"
    CLI_FLAGS[--project]="${root}"
    CLI_OVERRIDES=( PROJECT=cli )
    RELEASE=process
    API_HOST=process.example.com

    config-load

    expect-equal "${CONFIG[PROJECT]}" cli
    expect-equal "${CONFIG_SOURCE[PROJECT]}" cli
    expect-equal "${CONFIG[RELEASE]}" process
    expect-equal "${CONFIG_SOURCE[RELEASE]}" process
    expect-equal "${CONFIG[API_HOST]}" process.example.com
    expect-equal "${CONFIG[COMPOSE_PROJECT]}" cli-staging

    unset RELEASE API_HOST
    CLI_OVERRIDES=( UNKNOWN=value )
    expect-error 'Unknown setting: UNKNOWN' config-load

}
test-config-files () {

    local root="${TMPDIR}/project"

    mkdir -p "${root}"
    printf 'PROJECT=base\n' > "${root}/.env"
    printf 'PROJECT=local\n' > "${root}/.env.local"

    expect-equal "$(config-file "${root}" local)" "${root}/.env.local"
    expect-equal "$(config-file "${root}" production)" "${root}/.env"

    printf 'PROJECT=pod\n' > "${root}/.env.pod"
    expect-equal "$(config-file "${root}" production)" "${root}/.env.pod"

    printf 'PROJECT=production\n' > "${root}/.env.production"
    expect-error 'Both .env.production and .env.pod exist' config-file "${root}" production

    printf 'PROJECT=first\n' > "${root}/one"
    printf 'PROJECT=second\n' > "${root}/two"
    cli-parse --project "${root}" --config "${root}/one" --config "${root}/two" config PROJECT
    config-load
    expect-equal "${CONFIG[PROJECT]}" second

    printf 'PROJECT=ok\nCDN_MODE=direct\n' > "${root}/three"
    cli-parse --project "${root}" --config "${root}/three"
    expect-error 'Unknown setting in' config-load
    expect-equal "${CONFIG[PROJECT]}" second 'unknown keys leave the previous configuration intact'

}
test-config-modes () {

    local root="${TMPDIR}/project" output=""

    mkdir -p "${root}"
    printf 'ENV_MODE=production\n' > "${root}/.env"
    expect-error 'Unknown setting in' bash "${TOOL_BIN}" --project "${root}" config PROJECT

    rm -f "${root}/.env"
    output="$(env ENV_MODE=production bash "${TOOL_BIN}" --project "${root}" config ENV_MODE)"
    expect-equal "${output}" local

    output="$(bash "${TOOL_BIN}" --project "${root}" --environment production config DEPLOY_ENV)"
    expect-equal "${output}" production
    expect-error 'DEPLOY_ENV must be staging or production' bash "${TOOL_BIN}" --project "${root}" --environment qa config DEPLOY_ENV

    TOOL_BUILD=release
    config-load
    expect-equal "${CONFIG[ENV_MODE]}" production
    expect-equal "${CONFIG[DEPLOY_ENV]}" staging

}
test-config-derived () {

    cfg-set PROJECT shop
    cfg-set API_HOST api.shop.test
    cfg-set WEB_HOSTS 'client=shop.test,admin=admin.shop.test'
    config-derive

    expect-equal "${CONFIG[API_URL]}" https://api.shop.test
    expect-equal "${CONFIG[APP_ORIGINS]}" '["https://admin.shop.test","https://shop.test"]'

    cfg-set HTTPS_PORT 8443
    config-derive
    expect-equal "${CONFIG[API_URL]}" https://api.shop.test:8443
    expect-equal "${CONFIG[APP_ORIGINS]}" '["https://admin.shop.test:8443","https://shop.test:8443"]'

    cfg-set TLS_ENABLED false
    config-derive
    expect-equal "${CONFIG[API_URL]}" http://api.shop.test

    MANIFEST[native.http3_enabled]=true
    expect-error 'collides with the env schema' config-derive

}
test-config-validation () {

    local output=""

    config-validate

    cfg-set TLS_ENABLED false
    expect-error 'HTTP3_ENABLED=true requires TLS_ENABLED=true' config-validate

    cfg-set HTTP3_ENABLED false
    config-validate

    cfg-set DEPLOY_ENV production
    expect-error 'Production requires TLS_ENABLED=true' config-validate

    cfg-set DEPLOY_ENV staging
    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set CLOUDFLARE_PROXIED true
    cfg-set CLOUDFLARE_TOKEN token-for-tests
    output="$(config-validate 2>&1)"
    expect-contains "${output}" 'Cloudflare proxies this record'

    cfg-set API_REPLICAS 33
    cfg-set HTTP_PORT '80; reboot'
    cfg-set API_READY_PATH '/health;false'
    cfg-set DEPLOY_STRATEGY rolling
    cfg-set API_IMAGE example/api:latest
    output="$(config-validate 2>&1)" && err "Invalid settings were accepted"
    expect-contains "${output}" 'Invalid API_REPLICAS'
    expect-contains "${output}" 'Invalid HTTP_PORT'
    expect-contains "${output}" 'Invalid API_READY_PATH'
    expect-contains "${output}" 'Invalid DEPLOY_STRATEGY: expected blue-green|manual'
    expect-contains "${output}" 'Invalid API_IMAGE: expected pinned'

}
test-config-web () {

    local digest=""

    digest="sha256:$(printf '%064d' 3)"

    cfg-set WEB_IMAGES "client=example/client@${digest},admin=example/admin@${digest}"
    cfg-set WEB_HOSTS 'client=shop.test,admin=admin.shop.test'
    cfg-set WEB_REPLICAS 'client=3'
    config-web

    cfg-set WEB_REPLICAS 'client=33'
    expect-error 'WEB_REPLICAS client must be 1..32' config-web

    cfg-set WEB_REPLICAS 'ghost=2'
    expect-error 'WEB_REPLICAS names an unknown spec: ghost' config-web

    cfg-set WEB_REPLICAS ''
    cfg-set WEB_HOSTS 'client=shop.test'
    expect-error 'WEB_HOSTS requires a host for admin' config-web

    cfg-set WEB_IMAGES "client-one=example/a@${digest},client_one=example/b@${digest}"
    cfg-set WEB_HOSTS 'client-one=one.test,client_one=two.test'
    expect-error 'Web specs collide as CLIENT_ONE' config-web

    cfg-set WEB_IMAGES 'client=example/client:latest'
    cfg-set WEB_HOSTS 'client=shop.test'
    expect-error 'WEB_IMAGES client must be pinned by digest' config-web

}
test-config-required () {

    fixture-release
    config-required

    cfg-set DB_PASSWORD short
    cfg-set AUTH_SECRET short
    cfg-set REDIS_PASSWORD ''
    expect-error 'DB_PASSWORD needs at least 16 characters' config-required
    expect-error 'AUTH_SECRET needs at least 32 characters' config-required
    expect-error 'Missing setting: REDIS_PASSWORD' config-required

}
test-config-secrets () {

    local output=""

    cfg-set AUTH_SECRET 'sentinel-sensitive-value-1234567890'
    cfg-set AUTH_KEYS '["private-key-material"]'
    cfg-set REGISTRY_TOKEN 'registry-sentinel'

    expect-equal "$(cfg-show AUTH_SECRET)" '[redacted]'
    expect-equal "$(cfg-show AUTH_KEYS)" '[redacted]'
    expect-equal "$(cfg-show REGISTRY_TOKEN)" '[redacted]'
    expect-equal "$(cfg-show TLS_ENABLED)" true
    expect-equal "$(log-redact 'a sentinel-sensitive-value-1234567890 b')" 'a [redacted] b'

    output="$(err 'leaked registry-sentinel and ["private-key-material"]' 2>&1)" || true
    expect-equal "${output}" '[-] leaked [redacted] and [redacted]'
    output="$(info 'token registry-sentinel' 2>&1)"
    expect-absent "${output}" registry-sentinel

}
