fixture-parts () {

    local key=""

    CONFIG_PARTS_TABLE='
name  kind    port  path   ready         expect   balance     replicas  limit   env_mount  source              dockerfile  build
core  server  8000  /      /health       200      leastconn   2         -       /app/.env  product/api         api         -
shop  site    3000  /      /             200-399  roundrobin  2         -       /srv/.env  product/web/shop    web         SPEC=shop ORIGIN={core}
desk  site    3000  /desk  /desk/health  200      roundrobin  1         600/1m  -          product/web/desk    web         SPEC=desk ORIGIN={core} SELF={desk}
'

    for key in "${CONFIG_SERVER_KEYS[@]/#/CORE_}" CORE_DOMAIN SHOP_DOMAIN DESK_DOMAIN; do
        config-schema-key "${key}" || CONFIG_SCHEMA+=( "${key}" )
    done

    cfg-set CORE_DOMAIN '' defaults
    cfg-set SHOP_DOMAIN '' defaults
    cfg-set DESK_DOMAIN '' defaults
    cfg-set CORE_STORAGE_MOUNT /app/storage defaults
    cfg-set CORE_RELEASE_VARIABLE APP_RELEASE defaults
    cfg-set CORE_FORCED_ENV 'APP_HOST=0.0.0.0 APP_PORT=8000 DB_MIGRATE=false STORAGE_ROOT=/app/storage' defaults
    cfg-set CORE_SERVE_COMMAND 'python -m bootstrap serve' defaults
    cfg-set CORE_SERVE_ENV 'QUEUE_WORKERS=0 SCHEDULE_ENABLED=false' defaults
    cfg-set CORE_WORK_COMMAND 'python -m bootstrap work' defaults
    cfg-set CORE_WORK_ENV SCHEDULE_ENABLED=false defaults
    cfg-set CORE_SCHEDULE_COMMAND 'python -m bootstrap schedule' defaults
    cfg-set CORE_SCHEDULE_ENV 'QUEUE_WORKERS=0 SCHEDULE_ENABLED=true' defaults
    cfg-set CORE_MIGRATE_COMMAND 'python -m bootstrap migrate' defaults

    config-parts-load || return
    config-derive

}
test-config-schema () {

    local key="" schema=""

    schema="$(asset-text .env.example)"

    for key in "${CONFIG_SCHEMA[@]}"; do
        if [[ -n "${CONFIG_INPUTS[${key}]:-}" ]]; then expect-absent "${schema}" $'\n'"${key}=" "the ${CONFIG_INPUTS[${key}]} table owns ${key}"
        else expect-contains "${schema}" $'\n'"${key}=" "schema key ${key}"
        fi
    done

    for key in "${CONFIG_PARTS[@]}"; do
        expect-contains "${schema}" $'\n'"${key^^}_DOMAIN=" "the domain of part ${key}"
        expect-equal "${CONFIG_SOURCE[${key^^}_KIND]}" parts
        expect-equal "${CONFIG[${key^^}_IMAGE]}" '' "no image is pinned by default for ${key}"
    done

    expect-equal "$(config-part-names | paste -sd ' ' -)" "${CONFIG_PARTS[*]}"
    expect-equal "${CONFIG[PARTS]}" '' 'a part without a domain is not routed'
    [[ -n "$(config-server)" ]] || err "The parts table has no server part"
    expect-equal "${CONFIG[HTTP3_ENABLED]}" true
    expect-equal "${CONFIG[TLS_ENABLED]}" true
    expect-equal "${CONFIG[DEPLOY_STRATEGY]}" blue-green
    expect-equal "${CONFIG_SOURCE[HTTP3_ENABLED]}" defaults
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
    printf '%s\n' 'PROJECT=file' 'RELEASE=file' 'GRAFANA_DOMAIN=file.example.com' > "${root}/.env"
    CLI_FLAGS[--project]="${root}"
    CLI_OVERRIDES=( PROJECT=cli )
    RELEASE=process
    GRAFANA_DOMAIN=process.example.com

    config-load

    expect-equal "${CONFIG[PROJECT]}" cli
    expect-equal "${CONFIG_SOURCE[PROJECT]}" cli
    expect-equal "${CONFIG[RELEASE]}" process
    expect-equal "${CONFIG_SOURCE[RELEASE]}" process
    expect-equal "${CONFIG[GRAFANA_DOMAIN]}" process.example.com
    expect-equal "${CONFIG[COMPOSE_PROJECT]}" cli

    unset RELEASE GRAFANA_DOMAIN
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
    ENV_FILE="$(printf 'PROJECT=encoded\nGRAFANA_DOMAIN=grafana.encoded.test\n' | openssl base64 -A)"
    config-load
    expect-equal "${CONFIG[PROJECT]}" encoded 'a base64 ENV_FILE replaces the env files'
    expect-equal "${CONFIG_SOURCE[PROJECT]}" file

    ENV_FILE=$'PROJECT=plain\nGRAFANA_DOMAIN=grafana.plain.test'
    config-load
    expect-equal "${CONFIG[GRAFANA_DOMAIN]}" grafana.plain.test 'a plain ENV_FILE is read as written'

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

    fixture-parts
    cfg-set PROJECT shop
    cfg-set CORE_DOMAIN 'API.shop.test, core.shop.test,,backend.shop.test'
    cfg-set DESK_DOMAIN shop.test
    config-derive

    expect-equal "${CONFIG[ROUTED]}" 'core desk' 'only parts with a domain are routed, in table order'
    expect-equal "${CONFIG[PARTS]}" '' 'only parts with an image ship'
    expect-equal "$(config-list "${CONFIG[CORE_DOMAIN]}" | paste -sd ' ' -)" 'api.shop.test core.shop.test backend.shop.test' 'spaces and commas both separate'
    expect-equal "${CONFIG[CORE_URL]}" https://api.shop.test
    expect-equal "${CONFIG[DESK_URL]}" https://shop.test/desk
    expect-equal "${CONFIG[SHOP_URL]}" https://localhost
    expect-equal "${CONFIG[DESK_LIMIT]}" 600/1m
    expect-equal "${CONFIG[DESK_ENV_MOUNT]}" ''
    expect-equal "${CONFIG[DESK_REPLICAS]}" 1 'the table gives the default replica count'
    expect-equal "${CONFIG[IMAGE_POSTGRES]}" "${MANIFEST[images.postgres]}"

    cfg-set HTTPS_PORT 8443
    config-derive
    expect-equal "${CONFIG[CORE_URL]}" https://api.shop.test:8443

    cfg-set TLS_ENABLED false
    config-derive
    expect-equal "${CONFIG[CORE_URL]}" http://api.shop.test

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

    fixture-parts
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
    cfg-set RATE_LIMIT_IP 20/1s
    cfg-set DOMAINS_ENDPOINT http://api.shop.test/domains
    cfg-set DOMAINS_MAX_DROP 101
    cfg-set DOMAINS_INTERVAL -1
    output="$(config-validate 2>&1)" && err "Invalid dynamic domain settings were accepted"
    expect-contains "${output}" 'Invalid DOMAINS_ENDPOINT: expected https'
    expect-contains "${output}" 'Invalid DOMAINS_MAX_DROP: expected percent'
    expect-contains "${output}" 'Invalid DOMAINS_INTERVAL: expected count'
    cfg-set DOMAINS_ENDPOINT https://api.shop.test/domains
    cfg-set DOMAINS_MAX_DROP 25
    cfg-set DOMAINS_INTERVAL 3600
    expect-contains "$(config-validate 2>&1)" 'Dynamic domains stay off' 'an endpoint without a token warns and never blocks'
    cfg-set DOMAINS_INTERVAL 0
    expect-absent "$(config-validate 2>&1)" 'Dynamic domains stay off' 'an interval of 0 is a deliberate off'
    cfg-set DOMAINS_ENDPOINT ''
    cfg-set DOMAINS_INTERVAL 3600

    cfg-set TRUSTED_PROXIES 'https://proxy.example/ips 198.51.100.0/24 2001:db8::/32'
    expect-error 'TRUSTED settings are partial; missing TRUSTED_HEADER' config-validate
    cfg-set TRUSTED_HEADER 'Bad Header'
    expect-error 'Invalid TRUSTED_HEADER: expected header' config-validate
    cfg-set TRUSTED_HEADER True-Client-IP
    cfg-set TRUSTED_PROXIES 'http://proxy.example/ips'
    expect-error 'Invalid TRUSTED_PROXIES: expected proxies' config-validate
    cfg-set TRUSTED_PROXIES '198.51.100.0/33'
    expect-error 'Invalid TRUSTED_PROXIES: expected proxies' config-validate

    cfg-set TRUSTED_PROXIES ''
    cfg-set TRUSTED_HEADER ''
    cfg-set RATE_LIMIT_GLOBAL 5000/10s
    cfg-set RATE_LIMIT_PATHS '/v1/auth=10/1m,/v1/upload=5/1h'
    config-validate

    cfg-set RATE_LIMIT_IP 10/1d
    cfg-set RATE_LIMIT_PATHS '/v1=10/1m,/v1/auth=5/1m,auth=1/1s'
    output="$(config-validate 2>&1)" && err "Invalid rate limits were accepted"
    expect-contains "${output}" 'Invalid RATE_LIMIT_IP: expected rate'
    expect-contains "${output}" 'Invalid RATE_LIMIT_PATHS entry: auth=1/1s'
    expect-contains "${output}" 'RATE_LIMIT_PATHS prefixes must not nest: /v1 and /v1/auth'

    cfg-set RATE_LIMIT_IP ''
    cfg-set RATE_LIMIT_PATHS ''
    cfg-set CORE_DOMAIN api.shop.test
    cfg-set GRAFANA_DOMAIN 'grafana.shop.test api.shop.test'
    cfg-set GRAFANA_PASSWORD short
    cfg-set TELEGRAM_BOT_TOKEN 123456:not-a-token
    cfg-set REGISTRY_TOKEN pull-token
    output="$(config-validate 2>&1)" && err "Partial integrations were accepted"
    expect-contains "${output}" 'api.shop.test is routed to core and grafana'
    expect-contains "${output}" 'GRAFANA_PASSWORD needs at least 12 characters'
    expect-contains "${output}" 'Invalid TELEGRAM_BOT_TOKEN: expected bot'
    expect-contains "${output}" 'TELEGRAM settings are partial; missing TELEGRAM_CHAT_ID'
    expect-contains "${output}" 'REGISTRY settings are partial; missing REGISTRY_USER'

    cfg-set GRAFANA_DOMAIN grafana.shop.test
    cfg-set GRAFANA_PASSWORD grafana-password-01
    cfg-set TELEGRAM_BOT_TOKEN "123456:$(printf 'A%.0s' {1..35})"
    cfg-set TELEGRAM_CHAT_ID -1001234567890
    cfg-set REGISTRY_TOKEN ''
    config-validate

    cfg-set CORE_FORCED_ENV 'APP_PORT=8000 not-a-pair'
    cfg-set CORE_WORK_COMMAND $'python -m\nbootstrap work'
    cfg-set RABBIT_USER $'rabbit\n'
    cfg-set TLS_STAGING sometimes
    cfg-set GITOPS_DESIRED ../desired.env
    cfg-set DB_EXTENSIONS 'vector;drop'
    cfg-set MIGRATION_POLICY expand
    cfg-set CORE_MIGRATE_COMMAND ''
    output="$(config-validate 2>&1)" && err "Invalid runtime contracts were accepted"
    expect-contains "${output}" 'Invalid CORE_FORCED_ENV: expected pairs'
    expect-contains "${output}" 'Invalid CORE_WORK_COMMAND: expected command'
    expect-contains "${output}" 'Invalid RABBIT_USER: spaces or a line break around the value; check how it was pasted'
    expect-contains "${output}" 'Invalid TLS_STAGING: expected boolean'
    expect-contains "${output}" 'Invalid GITOPS_DESIRED: expected relative'
    expect-contains "${output}" 'Invalid DB_EXTENSIONS: expected extensions'
    expect-contains "${output}" 'MIGRATION_POLICY=expand requires CORE_MIGRATE_COMMAND'

    cfg-set CORE_FORCED_ENV ''
    cfg-set CORE_WORK_COMMAND 'python -m bootstrap work'
    cfg-set RABBIT_USER rabbit
    cfg-set TLS_STAGING false
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

    cfg-set CORE_REPLICAS 33
    cfg-set HTTP_PORT '80; reboot'
    cfg-set SHOP_DOMAIN 'shop.test bad_host'
    cfg-set DEPLOY_STRATEGY rolling
    cfg-set CORE_IMAGE example/api:latest
    output="$(config-validate 2>&1)" && err "Invalid settings were accepted"
    expect-contains "${output}" 'Invalid CORE_REPLICAS'
    expect-contains "${output}" 'Invalid HTTP_PORT'
    expect-contains "${output}" 'Invalid SHOP_DOMAIN: expected domains'
    expect-contains "${output}" 'Invalid DEPLOY_STRATEGY: expected blue-green|manual'
    expect-contains "${output}" 'Invalid CORE_IMAGE: expected pinned'

}
test-config-parts () {

    local digest="" table=""

    digest="sha256:$(printf '%064d' 3)"
    fixture-parts
    table="${CONFIG_PARTS_TABLE}"

    cfg-set CORE_DOMAIN api.shop.test
    cfg-set SHOP_DOMAIN 'shop.test, www.shop.test'
    cfg-set DESK_DOMAIN shop.test
    cfg-set SHOP_IMAGE "example/shop@${digest}"
    config-derive
    config-routes

    cfg-set DESK_DOMAIN www.shop.test
    cfg-set GRAFANA_DOMAIN shop.test
    config-derive
    expect-error 'shop.test is routed to shop and grafana' config-routes
    cfg-set GRAFANA_DOMAIN ''

    cfg-set SHOP_DOMAIN ''
    config-derive
    config-routes
    expect-absent " ${CONFIG[PARTS]} " ' shop ' 'an image without a domain is ignored'
    expect-fail config-domains $'shop.test\nother.test'

    CONFIG_PARTS_TABLE="${table//desk  site/desk  server}"
    expect-error 'needs exactly one server part, found 2' config-parts-load

    CONFIG_PARTS_TABLE="${table//desk  site/acme  site}"
    expect-error 'Part name acme is reserved' config-parts-load

    CONFIG_PARTS_TABLE="${table//"/desk/health"/"/health"}"
    expect-error 'Part desk: ready must be a path under /desk' config-parts-load

    CONFIG_PARTS_TABLE="${table//"{desk}"/"{ghost}"}"
    expect-error 'Part desk: build references an unknown part {ghost}' config-parts-load

    CONFIG_PARTS_TABLE="${table//desk  site/hub   site}"
    expect-error 'Part hub: declare HUB_DOMAIN in .env.example' config-parts-load

    CONFIG_PARTS_TABLE="${table//name  kind/label kind}"
    expect-error 'Parts table columns must be' config-parts-load

    CONFIG_PARTS_TABLE="${table}"
    CONFIG_INPUTS=()
    CONFIG_SCHEMA+=( SHOP_REPLICAS )
    expect-error 'SHOP_REPLICAS belongs to the parts table; remove it from .env.example' config-parts-load

}
test-config-required () {

    fixture-release
    config-required

    cfg-set CORE_IMAGE ''
    config-derive
    expect-error 'No part has both a domain and an image' config-required
    fixture-release

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
    fixture-parts
    expect-equal "$(cfg-show CORE_ENV_MOUNT)" /app/.env 'a mount path is not a secret'
    expect-equal "$(log-redact 'a sentinel-sensitive-value-1234567890 b')" 'a [redacted] b'

    output="$(err 'leaked registry-sentinel and ["private-key-material"]' 2>&1)" || true
    expect-equal "${output}" '[-] leaked [redacted] and [redacted]'
    output="$(info 'token registry-sentinel' 2>&1)"
    expect-absent "${output}" registry-sentinel

}
fixture-curl () {

    mkdir -p "${TMPDIR}/bin"
    cat > "${TMPDIR}/bin/curl" <<'CURL'
#!/usr/bin/env bash
out="" save="" compare="" write=""
cat > "${TMPDIR}/curl.config"
printf '%s\n' "$@" > "${TMPDIR}/curl.args"
while (( $# > 0 )); do
    case "$1" in
        --output) out="$2"; shift ;;
        --etag-save) save="$2"; shift ;;
        --etag-compare) compare="$2"; shift ;;
        --write-out) write="$2"; shift ;;
    esac
    shift
done
if [[ -n "${compare}" && -f "${TMPDIR}/payload.unchanged" ]]; then
    : > "${out}"
    [[ -z "${write}" ]] || printf 304
    exit 0
fi
cp "${TMPDIR}/payload.json" "${out}"
[[ -z "${save}" ]] || printf '"v1"\n' > "${save}"
[[ -z "${write}" ]] || printf 200
CURL
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

}
test-config-domains () {

    local cache="${TMPDIR}/wanted" tag="${TMPDIR}/etag" lines="" warnings=""

    fixture-release
    expect-fail config-domains-on
    cfg-set DOMAINS_ENDPOINT https://api.shop.test/internal/domains
    expect-fail config-domains-on
    cfg-set DOMAINS_TOKEN domains-sentinel-token
    config-domains-on
    cfg-set DOMAINS_INTERVAL 0
    expect-fail config-domains-on
    cfg-set DOMAINS_INTERVAL 3600

    fixture-curl
    printf '%s' '{"domains":[{"domain":"Shop.Acme.Example","part":"shop"},{"domain":"api.shop.test","part":"core"},{"domain":"bad_host","part":"shop"},{"domain":"desk.acme.example","part":"ghost"},{"domain":"b.example","part":"desk"}]}' > "${TMPDIR}/payload.json"

    lines="$(config-domains-fetch "${cache}" "${tag}" 2> "${TMPDIR}/warnings")"
    warnings="$(fs-read "${TMPDIR}/warnings")"
    expect-equal "${lines}" $'b.example desk\nshop.acme.example shop'
    expect-contains "${warnings}" 'Skipping api.shop.test: it is already routed'
    expect-contains "${warnings}" "Skipping the domain entry 'bad_host shop'"
    expect-contains "${warnings}" "Skipping the domain entry 'desk.acme.example ghost'"
    expect-contains "$(fs-read "${TMPDIR}/curl.config")" 'header = "Authorization: Bearer domains-sentinel-token"'
    expect-absent "$(fs-read "${TMPDIR}/curl.args")" domains-sentinel-token 'the token never reaches argv'
    expect-contains "$(fs-read "${TMPDIR}/curl.args")" --compressed
    expect-absent "$(fs-read "${TMPDIR}/curl.args")" --etag-compare 'without a recorded list nothing is revalidated'
    expect-equal "$(fs-read "${tag}")" '"v1"'

    printf '%s\n' "${lines}" > "${cache}"
    touch "${TMPDIR}/payload.unchanged"
    printf '%s' '{"domains":[]}' > "${TMPDIR}/payload.json"
    expect-equal "$(config-domains-fetch "${cache}" "${tag}")" "${lines}" 'a 304 reuses the recorded list'
    expect-contains "$(fs-read "${TMPDIR}/curl.args")" --etag-compare

    rm -f -- "${cache}"
    expect-equal "$(config-domains-fetch "${cache}" "${tag}")" '' 'a lost recorded list is fetched in full'

    printf 'not json' > "${TMPDIR}/payload.json"
    expect-error 'answered outside the shape of src/config/domains.sh' config-domains-fetch "${cache}" "${tag}"

    CONFIG_DOMAINS_SHAPE='.items[] | "\(.host) \(.surface)"'
    printf '%s' '{"items":[{"host":"c.example","surface":"shop"}]}' > "${TMPDIR}/payload.json"
    expect-equal "$(config-domains-fetch "${cache}" "${tag}")" 'c.example shop' 'the payload shape is one line of config'

    lines=$'a.example shop\nb.example shop\nc.example shop\nd.example shop'
    config-domains-guard "${lines}" $'a.example shop\nb.example shop\nc.example shop'
    config-domains-guard "${lines}" $'a.example desk\nb.example shop\nc.example shop\nd.example shop'
    expect-error 'DOMAINS_ENDPOINT drops 4 of 4 domains, above DOMAINS_MAX_DROP=25%' config-domains-guard "${lines}" ''
    config-domains-guard 'a.example shop' ''
    cfg-set DOMAINS_MAX_DROP 100
    config-domains-guard "${lines}" ''

}
test-config-models () {

    local table="" listing="" output="" zero=""

    fixture-parts
    table="${CONFIG_MODELS_TABLE}"
    listing="${CONFIG_MODEL_FILES}"
    zero="$(printf '%064d' 0)"

    expect-equal "${CONFIG_SOURCE[EMBEDDER_MEMORY]}" defaults 'the models table registers its inputs'
    expect-equal "${CONFIG_INPUTS[RANKER_BATCH]}" models
    expect-equal "${CONFIG[EMBEDDER_URL]}" http://embedder:8080
    expect-equal "${CONFIG[MODELS_ROOT]}" "${CONFIG[STATE_ROOT]}/models"
    expect-equal "$(config-model-args embedder)" '--model-id /model --hostname 0.0.0.0 --port 8080 --max-batch-tokens 2048 --auto-truncate'

    cfg-set MODELS 'embedder, ranker'
    cfg-set EMBEDDER_BATCH 1024
    config-models-valid
    expect-equal "$(config-models | paste -sd ' ' -)" 'embedder ranker'
    expect-contains "$(config-model-args embedder)" '--max-batch-tokens 1024' 'the batch setting reaches the runner'

    cfg-set MODELS 'embedder ghost embedder'
    output="$(config-models-valid 2>&1)" && err "Unknown models were accepted"
    expect-contains "${output}" 'MODELS names an unknown model: ghost'
    expect-contains "${output}" 'MODELS names embedder twice'

    cfg-set MODELS embedder
    cfg-set EMBEDDER_MEMORY 4gb
    expect-error 'Invalid EMBEDDER_MEMORY: expected memory' config-models-valid
    cfg-set EMBEDDER_MEMORY 4g

    CONFIG_MODEL_FILES="${listing}embedder  pytorch_model.bin  10  ${zero}"$'\n'
    expect-error 'pytorch_model.bin is a pickle format that can run code on load' config-models-load
    CONFIG_MODEL_FILES="${listing}embedder  ../escape.json  10  ${zero}"$'\n'
    expect-error 'Model embedder: unsafe file path ../escape.json' config-models-load
    CONFIG_MODEL_FILES="${listing}embedder  config.json  687  ${zero}"$'\n'
    expect-error 'Model embedder: config.json is listed twice or reserved' config-models-load
    CONFIG_MODEL_FILES="${listing}embedder  tokenizer.json  1  short"$'\n'
    expect-error 'is listed twice or reserved' config-models-load

    CONFIG_MODEL_FILES="${listing}"
    CONFIG_MODELS_TABLE="${table//ranker    tei/shop      tei}"
    expect-error 'Model name shop is taken by a part, a service or another model' config-models-load
    CONFIG_MODELS_TABLE="${table//ranker    tei/ranker    ghost}"
    expect-error 'Model ranker: unknown runner ghost' config-models-load
    CONFIG_MODELS_TABLE="${table//name  /label  }"
    expect-error 'Models table columns must be' config-models-load

    CONFIG_MODELS_TABLE="${table}"
    config-models-load
    CONFIG_INPUTS=()
    expect-error 'EMBEDDER_MEMORY belongs to the models table; remove it from .env.example' config-models-load

}
