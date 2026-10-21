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
    expect-equal "${CONFIG_SOURCE[HEALTH_TIMEOUT]}" defaults
    expect-equal "${CONFIG_SOURCE[IMAGE_POSTGRES]}" manifest
    expect-equal "${CONFIG[STATE_ROOT]}" "${CONFIG[PROJECT_ROOT]}/.infra/unconfigured"
    config-schema-key HEALTH_TIMEOUT
    expect-fail config-schema-key IMAGE_POSTGRES
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
    expect-equal "${CONFIG[COMPOSE_PROJECT]}" cli

    unset RELEASE API_HOST
    CLI_OVERRIDES=( UNKNOWN=value )
    expect-error 'Unknown setting: UNKNOWN' config-load

}
test-config-files () {

    local root="${TMPDIR}/project"

    mkdir -p "${root}"
    expect-equal "$(config-file "${root}" production)" '' 'no file leaves the defaults'

    printf 'PROJECT=base\n' > "${root}/.env"
    expect-equal "$(config-file "${root}" local)" "${root}/.env"
    expect-equal "$(config-file "${root}" production)" "${root}/.env"

    printf 'PROJECT=local\n' > "${root}/.env.local"
    expect-equal "$(config-file "${root}" local)" "${root}/.env.local"
    expect-equal "$(config-file "${root}" production)" "${root}/.env" 'production never reads the local file'

    printf 'PROJECT=prod\n' > "${root}/.env.prod"
    expect-equal "$(config-file "${root}" production)" "${root}/.env.prod"

    printf 'PROJECT=production\n' > "${root}/.env.production"
    expect-equal "$(config-file "${root}" production)" "${root}/.env.production"

    CLI_FLAGS[--project]="${root}"
    ENV_FILE="$(printf 'PROJECT=encoded\nAPI_HOST=api.encoded.test\n' | openssl base64 -A)"
    config-load
    expect-equal "${CONFIG[PROJECT]}" encoded 'a base64 ENV_FILE replaces the env files'
    expect-equal "${CONFIG_SOURCE[PROJECT]}" file

    ENV_FILE=$'PROJECT=plain\nAPI_HOST=api.plain.test'
    config-load
    expect-equal "${CONFIG[API_HOST]}" api.plain.test 'a plain ENV_FILE is read as written'

    ENV_FILE='CDN_MODE=direct'
    expect-error 'Unknown setting in' config-load
    unset ENV_FILE

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

    expect-error 'Unknown setting: DEPLOY_ENV' bash "${TOOL_BIN}" --project "${root}" config DEPLOY_ENV

    TOOL_BUILD=release
    config-load
    expect-equal "${CONFIG[ENV_MODE]}" production

}
test-config-derived () {

    cfg-set PROJECT shop
    cfg-set API_HOST api.shop.test
    cfg-set WEB_HOSTS 'client=shop.test,admin=admin.shop.test'
    config-derive

    expect-equal "${CONFIG[API_URL]}" https://api.shop.test
    expect-equal "${CONFIG[IMAGE_POSTGRES]}" "${MANIFEST[images.postgres]}"

    cfg-set HTTPS_PORT 8443
    config-derive
    expect-equal "${CONFIG[API_URL]}" https://api.shop.test:8443

    cfg-set TLS_ENABLED false
    config-derive
    expect-equal "${CONFIG[API_URL]}" http://api.shop.test

    MANIFEST[native.health_timeout]=999
    config-derive
    expect-equal "${CONFIG[HEALTH_TIMEOUT]}" 120 'deployment settings live in the env schema only'

    cfg-set REGISTRY_DRIVER ghcr
    cfg-set REGISTRY_USER ''
    cfg-set REGISTRY_TOKEN ''
    cfg-set GITOPS_URL https://github.com/org/deploy
    cfg-set GITOPS_USER ''
    cfg-set GITOPS_TOKEN ''
    cfg-set GITHUB_TOKEN github-sentinel process
    config-derive
    expect-equal "${CONFIG[REGISTRY_TOKEN]}" github-sentinel 'GITHUB_TOKEN pulls from GHCR'
    expect-equal "${CONFIG[REGISTRY_USER]}" x-access-token
    expect-equal "${CONFIG_SOURCE[REGISTRY_TOKEN]}" process 'an exported GITHUB_TOKEN stays transient'
    expect-equal "${CONFIG[GITOPS_TOKEN]}" github-sentinel 'GITHUB_TOKEN reads a GitHub desired-state repository'

    cfg-set REGISTRY_TOKEN robot-token file
    cfg-set REGISTRY_USER robot file
    config-derive
    expect-equal "${CONFIG[REGISTRY_TOKEN]}" robot-token 'an explicit registry token wins'

    CONFIG_SCHEMA+=( IMAGE_EXTRA )
    MANIFEST[images.extra]=example/extra@sha256:0
    expect-error 'collides with the env schema' config-derive

}
test-config-validation () {

    local output=""

    config-validate

    cfg-set TLS_ENABLED false
    expect-error 'HTTP3_ENABLED=true requires TLS_ENABLED=true' config-validate

    cfg-set HTTP3_ENABLED false
    config-validate

    cfg-set ENV_MODE production
    expect-error 'Production requires TLS_ENABLED=true' config-validate

    cfg-set ENV_MODE local
    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set EDGE_SOCKETS ''
    cfg-set DNS_PROXIED true
    expect-error 'DNS_PROXIED applies to the records DNS_PROVIDER manages' config-validate
    cfg-set DNS_PROVIDER route53
    expect-error 'Invalid DNS_PROVIDER: expected cloudflare' config-validate
    cfg-set DNS_PROVIDER cloudflare
    cfg-set DNS_TOKEN token-for-tests
    expect-error 'DNS settings are partial; missing DNS_ZONE, DNS_ADDRESS' config-validate

    cfg-set DNS_ZONE "$(printf 'a%.0s' {1..32})"
    cfg-set DNS_ADDRESS 203.0.113.7
    cfg-set RATE_LIMIT_IP 20/1s
    output="$(config-validate 2>&1)"
    expect-contains "${output}" 'DNS_PROXIED=true: the DNS provider terminates public QUIC'
    expect-contains "${output}" 'DNS_PROXIED=true without TRUSTED_HEADER'
    cfg-set EDGE_SOCKETS /srv/edge
    expect-absent "$(config-validate 2>&1)" 'QUIC' 'a relayed edge serves no QUIC to warn about'
    cfg-set EDGE_SOCKETS ''

    cfg-set TRUSTED_PROXIES 'https://proxy.example/ips 198.51.100.0/24 2001:db8::/32'
    expect-error 'TRUSTED settings are partial; missing TRUSTED_HEADER' config-validate
    cfg-set TRUSTED_HEADER 'Bad Header'
    expect-error 'Invalid TRUSTED_HEADER: expected header' config-validate
    cfg-set TRUSTED_HEADER True-Client-IP
    expect-absent "$(config-validate 2>&1)" 'without TRUSTED_HEADER' 'a trusted header restores the clients behind proxied records'
    cfg-set TRUSTED_PROXIES 'http://proxy.example/ips'
    expect-error 'Invalid TRUSTED_PROXIES: expected proxies' config-validate
    cfg-set TRUSTED_PROXIES '198.51.100.0/33'
    expect-error 'Invalid TRUSTED_PROXIES: expected proxies' config-validate

    cfg-set TRUSTED_PROXIES ''
    cfg-set TRUSTED_HEADER ''
    cfg-set DNS_PROXIED false
    cfg-set DNS_PROVIDER ''
    cfg-set DNS_TOKEN ''
    cfg-set DNS_ZONE ''
    cfg-set DNS_ADDRESS ''
    cfg-set RATE_LIMIT_GLOBAL 5000/10s
    cfg-set RATE_LIMIT_PATHS '/v1/auth=10/1m,/v1/upload=5/1h'
    config-validate

    cfg-set RATE_LIMIT_HOST 10/1d
    cfg-set RATE_LIMIT_PATHS '/v1=10/1m,/v1/auth=5/1m,auth=1/1s'
    output="$(config-validate 2>&1)" && err "Invalid rate limits were accepted"
    expect-contains "${output}" 'Invalid RATE_LIMIT_HOST: expected rate'
    expect-contains "${output}" 'Invalid RATE_LIMIT_PATHS entry: auth=1/1s'
    expect-contains "${output}" 'RATE_LIMIT_PATHS prefixes must not nest: /v1 and /v1/auth'

    cfg-set RATE_LIMIT_HOST ''
    cfg-set RATE_LIMIT_PATHS ''
    cfg-set API_HOST api.shop.test
    cfg-set GRAFANA_HOST api.shop.test
    cfg-set GRAFANA_PASSWORD short
    cfg-set TELEGRAM_BOT_TOKEN 123456:not-a-token
    cfg-set REGISTRY_TOKEN pull-token
    output="$(config-validate 2>&1)" && err "Partial integrations were accepted"
    expect-contains "${output}" 'Host api.shop.test is routed twice'
    expect-contains "${output}" 'GRAFANA_PASSWORD needs at least 12 characters'
    expect-contains "${output}" 'Invalid TELEGRAM_BOT_TOKEN: expected bot'
    expect-contains "${output}" 'TELEGRAM settings are partial; missing TELEGRAM_CHAT_ID'
    expect-contains "${output}" 'REGISTRY settings are partial; missing REGISTRY_USER'

    cfg-set GRAFANA_HOST grafana.shop.test
    cfg-set GRAFANA_PASSWORD grafana-password-01
    cfg-set TELEGRAM_BOT_TOKEN "123456:$(printf 'A%.0s' {1..35})"
    cfg-set TELEGRAM_CHAT_ID -1001234567890
    cfg-set REGISTRY_TOKEN ''
    config-validate

    cfg-set API_FORCED_ENV 'APP_PORT=8000 not-a-pair'
    cfg-set API_WORK_COMMAND ' '
    cfg-set GITOPS_DESIRED ../desired.env
    cfg-set DB_EXTENSIONS 'vector;drop'
    cfg-set MIGRATION_POLICY expand
    cfg-set API_MIGRATE_COMMAND ''
    output="$(config-validate 2>&1)" && err "Invalid runtime contracts were accepted"
    expect-contains "${output}" 'Invalid API_FORCED_ENV: expected pairs'
    expect-contains "${output}" 'Invalid API_WORK_COMMAND: expected command'
    expect-contains "${output}" 'Invalid GITOPS_DESIRED: expected relative'
    expect-contains "${output}" 'Invalid DB_EXTENSIONS: expected extensions'
    expect-contains "${output}" 'MIGRATION_POLICY=expand requires API_MIGRATE_COMMAND'

    cfg-set API_FORCED_ENV ''
    cfg-set API_WORK_COMMAND 'python -m bootstrap work'
    cfg-set GITOPS_DESIRED deploy/desired.env
    cfg-set DB_EXTENSIONS vector,pg_trgm
    cfg-set MIGRATION_POLICY none
    config-validate

    cfg-set BACKUP_WAL yes
    cfg-set BACKUP_ARCHIVE_INTERVAL 0
    output="$(config-validate 2>&1)" && err "Invalid WAL settings were accepted"
    expect-contains "${output}" 'Invalid BACKUP_WAL: expected boolean'
    expect-contains "${output}" 'Invalid BACKUP_ARCHIVE_INTERVAL: expected positive'
    cfg-set BACKUP_WAL true
    cfg-set BACKUP_ARCHIVE_INTERVAL 300

    cfg-set GITOPS_BRANCH '--upload-pack=touch'
    cfg-set TLS_EMAIL 'ops at example'
    cfg-set HEALTH_CA '/ca.pem,target=/etc'
    cfg-set BACKUP_REGION 'us east'
    cfg-set REGISTRY_NAMESPACE 'Org/Team'
    cfg-set SSH_HOST 'deploy@203.0.113.7'
    cfg-set SSH_USER '-oProxyCommand=x'
    cfg-set REMOTE_DIR /srv/ragx
    output="$(config-validate 2>&1)" && err "Unsafe operator inputs were accepted"
    expect-contains "${output}" 'Invalid GITOPS_BRANCH: expected branch'
    expect-contains "${output}" 'Invalid TLS_EMAIL: expected email'
    expect-contains "${output}" 'Invalid HEALTH_CA: expected path'
    expect-contains "${output}" 'Invalid BACKUP_REGION: expected region'
    expect-contains "${output}" 'Invalid REGISTRY_NAMESPACE: expected namespace'
    expect-contains "${output}" 'Invalid SSH_HOST: expected target'
    expect-contains "${output}" 'Invalid SSH_USER: expected user'
    expect-contains "${output}" 'Invalid REMOTE_DIR: expected relative'

    cfg-set GITOPS_BRANCH desired/main
    cfg-set TLS_EMAIL ops+tls@example.co.uk
    cfg-set HEALTH_CA /etc/ssl/health-ca.pem
    cfg-set BACKUP_REGION me-central-1
    cfg-set REGISTRY_NAMESPACE org-team
    cfg-set SSH_HOST 203.0.113.7
    cfg-set SSH_USER deploy
    cfg-set REMOTE_DIR apps/ragx
    config-validate

    cfg-set GITOPS_URL https://git.example.test/org/deploy
    output="$(config-validate 2>&1)" && err "Invalid delivery settings were accepted"
    expect-contains "${output}" 'GITOPS settings are partial; missing GITOPS_USER, GITOPS_TOKEN'

    cfg-set GITOPS_USER reader
    cfg-set GITOPS_TOKEN reader-token
    output="$(config-validate 2>&1)"
    expect-contains "${output}" 'GitOps pulls private images only with a permanent REGISTRY_TOKEN'

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
    cfg-set REDIS_PASSWORD ''
    expect-error 'DB_PASSWORD needs at least 16 characters' config-required
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
    expect-equal "$(cfg-show API_ENV_MOUNT)" /app/.env 'a mount path is not a secret'
    expect-equal "$(log-redact 'a sentinel-sensitive-value-1234567890 b')" 'a [redacted] b'

    output="$(err 'leaked registry-sentinel and ["private-key-material"]' 2>&1)" || true
    expect-equal "${output}" '[-] leaked [redacted] and [redacted]'
    output="$(info 'token registry-sentinel' 2>&1)"
    expect-absent "${output}" registry-sentinel

}
