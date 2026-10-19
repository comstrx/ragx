test-operations-topology () {

    fixture-release
    expect-equal "$(native-services)" api
    expect-equal "$(native-routes)" "api|api.shop.test|${CONFIG[API_PORT]}|/health|leastconn|200"

    fixture-web
    expect-equal "$(native-services | tr '\n' ' ')" 'api web-admin web-client '
    expect-equal "$(native-replicas web-client)" 3
    expect-equal "$(native-replicas web-admin)" 2
    expect-equal "$(native-replicas api)" 2
    expect-equal "$(native-variable client-one)" WEB_CLIENT_ONE_REPLICAS
    expect-equal "$(native-service-image web-admin)" "example/admin@$(fixture-digest 3)"
    expect-equal "$(native-hosts | tr '\n' ' ')" 'api.shop.test admin.shop.test shop.test '
    expect-contains "$(native-routes)" "web-client|shop.test|${CONFIG[WEB_PORT]}|/|roundrobin|200-399"

    mkdir -p "${CONFIG[STATE_ROOT]}"
    state-write "${CONFIG[STATE_ROOT]}" slot-green r1
    expect-contains "$(native-interpolation r1)" DEPLOY_SLOT=green
    expect-contains "$(native-interpolation r1)" "RELEASE_ROOT=${CONFIG[STATE_ROOT]}/releases/r1"
    expect-contains "$(native-interpolation r1)" WEB_CLIENT_REPLICAS=3
    expect-contains "$(native-interpolation r9)" DEPLOY_SLOT=blue

}
test-operations-backup-retention () {

    local root="${CONFIG[STATE_ROOT]}/backups" name=""

    mkdir -p "${root}"
    cfg-set BACKUP_DAYS 1

    for name in old latest recent; do
        printf '%s\n' "${name}" > "${root}/${name}.dump"
        printf 'sum\n' > "${root}/${name}.dump.sha256"
    done

    printf 'keep\n' > "${root}/unrelated"
    touch -t 200001010000 "${root}/old.dump" "${root}/latest.dump"
    state-write "${root}" latest latest.dump

    native-backup-prune

    expect-fail test -e "${root}/old.dump"
    expect-fail test -e "${root}/old.dump.sha256"
    expect-equal "$(fs-read "${root}/latest.dump")" latest
    expect-equal "$(fs-read "${root}/recent.dump")" recent
    expect-equal "$(fs-read "${root}/unrelated")" keep

}
test-operations-guards () {

    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp 443/udp '
    cfg-set HTTP3_ENABLED false
    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp '
    expect-equal "$(native-protocols)" 'http/1.1 h2'

    expect-error 'repeat with --force' native-firewall-apply
    expect-error 'Repeat with --force' native-uninstall
    expect-error 'recover --force removes a dead lock' native-recover
    expect-error 'Install timers from the staged release bundle' native-timer-install backup 3600
    expect-error 'Usage: timer install' native-timer-install shell 60
    expect-error 'Usage: restore BACKUP_FILE NEW_DATABASE' native-restore one
    expect-error 'Unknown command: drop' native-tls drop
    expect-error 'Usage: image build api|web TAG [SPEC]' native-image-build other example/x:1
    expect-error 'Image builds need the monorepo checkout' native-image-build api example/api:1

    cfg-set PROJECT shop
    cfg-set REGISTRY_NAMESPACE org
    expect-equal "$(native-registry-reference api 1.0.0)" ghcr.io/org/shop-api:1.0.0
    cfg-set REGISTRY_DRIVER dockerhub
    expect-equal "$(native-registry-host)" docker.io
    expect-error 'Image outside docker.io/org' native-registry-push ghcr.io/org/shop-api:1

}
test-operations-cloudflare () {

    local log="${TMPDIR}/cloudflare.log" output=""

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'method=GET url="" out="" body=""' 'cat > "${TMPDIR}/cloudflare.config"' \
        'while (( $# > 0 )); do case "$1" in --request) method="$2" ;; --url) url="$2" ;; --output) out="$2" ;; --data-binary) body="${2#@}" ;; esac; shift; done' \
        'printf "%s %s %s\n" "${method}" "${url}" "$( [[ -n "${body}" ]] && cat "${body}" )" >> "${TMPDIR}/cloudflare.log"' \
        'if [[ "${method}" == GET && -f "${TMPDIR}/cloudflare.existing" ]]; then printf "{\"success\":true,\"result\":[{\"id\":\"%s\"}]}" "$(cat "${TMPDIR}/cloudflare.existing")" > "${out}"' \
        'else printf "{\"success\":true,\"result\":[]}" > "${out}"; fi' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set CLOUDFLARE_TOKEN 'cf-sentinel-token'
    cfg-set CLOUDFLARE_ZONE "$(printf 'a%.0s' {1..32})"

    cloudflare-upsert api.shop.test 203.0.113.7 false
    output="$(fs-read "${log}")"
    expect-contains "${output}" 'GET https://api.cloudflare.com/client/v4/zones/'
    expect-contains "${output}" '/dns_records?name=api.shop.test&type=A'
    expect-contains "${output}" 'POST https://api.cloudflare.com/client/v4/zones/'
    expect-contains "${output}" '{"type":"A","name":"api.shop.test","content":"203.0.113.7","ttl":300,"proxied":false}'
    expect-equal "$(fs-read "${TMPDIR}/cloudflare.config")" 'header = "Authorization: Bearer cf-sentinel-token"'
    expect-absent "${output}" cf-sentinel-token

    : > "${log}"
    printf '%s' "$(printf 'b%.0s' {1..32})" > "${TMPDIR}/cloudflare.existing"
    cloudflare-upsert api.shop.test 2001:db8::7 true
    output="$(fs-read "${log}")"
    expect-contains "${output}" "PUT https://api.cloudflare.com/client/v4/zones/$(printf 'a%.0s' {1..32})/dns_records/$(printf 'b%.0s' {1..32})"
    expect-contains "${output}" '"type":"AAAA"'
    expect-contains "${output}" '"proxied":true'

    printf 'not-an-id' > "${TMPDIR}/cloudflare.existing"
    expect-error 'Unexpected Cloudflare record identifier' cloudflare-upsert api.shop.test 203.0.113.7 false
    expect-error 'Invalid DNS address' cloudflare-upsert api.shop.test 'bad;address' false
    cfg-set CLOUDFLARE_ZONE short
    expect-error 'CLOUDFLARE_ZONE must be a zone identifier' cloudflare-upsert api.shop.test 203.0.113.7 false

}
test-operations-certbot () {

    local log="${TMPDIR}/certbot.log" text=""

    docker-oneshot () {

        printf '%s\n' "$@" >> "${TMPDIR}/certbot.log"
        [[ ! -f "${CONFIG[STATE_ROOT]}/cloudflare.ini" ]] || cp "${CONFIG[STATE_ROOT]}/cloudflare.ini" "${TMPDIR}/certbot.ini"

    }

    fixture-release
    mkdir -p "${CONFIG[STATE_ROOT]}"
    cfg-set TLS_EMAIL ops@shop.test

    tls-issue api.shop.test shop.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'certonly\n--non-interactive\n--agree-tos'
    expect-contains "${text}" $'-d\napi.shop.test\n-d\nshop.test'
    expect-contains "${text}" $'--standalone\n--http-01-port\n8080'
    expect-contains "${text}" $'--network\nshop-staging-apps\n--network-alias\nacme'
    expect-contains "${text}" '/acme/live/site/fullchain.pem /acme/live/site/privkey.pem > /tls/site.pem.new'

    : > "${log}"
    cfg-set TLS_CHALLENGE dns
    cfg-set CLOUDFLARE_TOKEN cf_dns_token-01
    tls-issue api.shop.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'--dns-cloudflare\n--dns-cloudflare-credentials\n/run/cloudflare.ini'
    expect-equal "$(fs-read "${TMPDIR}/certbot.ini")" 'dns_cloudflare_api_token = cf_dns_token-01'
    expect-fail test -e "${CONFIG[STATE_ROOT]}/cloudflare.ini"
    expect-absent "${text}" cf_dns_token-01

    cfg-set CLOUDFLARE_TOKEN 'bad token'
    expect-error 'CLOUDFLARE_TOKEN has an unexpected format' tls-issue api.shop.test
    expect-error 'Invalid certificate host' tls-issue 'bad host'

}
test-operations-retire-without-edge () {

    local root=""

    native-compose-app () { printf '%s\n' "$*" >> "${TMPDIR}/compose.log"; }
    native-edge-alive () { [[ -f "${TMPDIR}/edge.alive" ]]; }

    fixture-release
    cfg-set DRAIN_TIMEOUT 1
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}/releases/r1"
    state-write "${root}" slot-blue r1

    native-retire blue
    expect-contains "$(fs-read "${TMPDIR}/compose.log")" 'r1 --profile worker --profile scheduler down'
    expect-equal "$(state-read "${root}" slot-blue)" ''

    : > "${TMPDIR}/edge.alive"
    state-write "${root}" slot-blue r1
    expect-error 'Slot blue still serves sessions' native-retire blue
    expect-equal "$(state-read "${root}" slot-blue)" r1

}
