fixture-stats () {

    local header='# pxname,svname,qcur,qmax,scur'
    local tail=',0,0,0,0,0,0,0,0,0,0,,,,0,0,0,,,,,-1,"Layer7 wrong status, code 503",,0,0,0,0,,,,Layer4 connection problem,,2,3,0,,,,'

    out "${header}"
    out "core_blue,replica1,0,0,${1:-0},0,,0,0,0,,0,,0,0,0,0,UP,1,1,0,0,1,2,2,,1,3,1,,0,,2,0,,0,L7OK${tail}172.18.0.5:8000,,http"
    out "core_blue,replica2,0,0,0,0,,0,0,0,,0,,0,0,0,0,UP,1,1,0,0,1,2,2,,1,3,2,,0,,2,0,,0,L7OK${tail}172.18.0.6:8000,,http"
    out "core_blue,replica3,0,0,0,0,,0,0,0,,0,,0,0,0,0,MAINT (resolution),1,1,0,0,1,2,2,,1,3,3,,0,,2,0,,0,,${tail},,http"
    out "core_blue,BACKEND,0,0,${1:-0},0,,0,0,0,,0,,0,0,0,0,UP,2,2,0,,0,2,0,,1,3,0,,0,,1,0,,0,,${tail},,http"
    out "core_green,replica1,0,0,0,0,,0,0,0,,0,,0,0,0,0,DOWN,1,1,0,0,1,2,2,,1,4,1,,0,,2,0,,0,L4CON${tail}172.18.0.9:8000,,http"

}
test-edge-protocols () {

    local directory="${TMPDIR}/edge" text="" core='core|api.shop.test core.shop.test|8000|/|/health|leastconn|200||slot'

    fixture-release
    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set HTTPS_PORT 443
    haproxy-render "${directory}" "${core}" 'shop|shop.test|3000|/|/|roundrobin|200-399||slot' 'desk|shop.test|3000|/desk|/desk/health|roundrobin|200||slot'
    text="$(fs-read "${directory}/haproxy.cfg")"

    expect-contains "${text}" 'bind :8443 ssl crt /etc/haproxy-tls/certs/ strict-sni alpn h2,http/1.1'
    expect-contains "${text}" 'bind quic4@:8443 ssl crt /etc/haproxy-tls/certs/ strict-sni ssl-min-ver TLSv1.3 alpn h3'
    expect-contains "${text}" "set-header Alt-Svc 'h3=\":443\"; ma=86400' if { ssl_fc }"
    expect-contains "${text}" 'Strict-Transport-Security "max-age=63072000"'
    expect-contains "${text}" 'redirect prefix https://%[req.hdr(host),lower,field(1,:)] code 308'
    expect-absent "${text}" 'deny deny_status 404 unless { req.hdr(host)' 'the part selection replaces a host allowlist'
    expect-contains "${text}" $'    acl part_desk_host req.hdr(host),lower,field(1,:) -m str shop.test\n    acl part_desk_path path /desk\n    acl part_desk_path path_beg /desk/\n    http-request set-var(txn.part) str(desk) if !{ var(txn.part) -m found } part_desk_host part_desk_path\n    acl part_core_host' 'the longest path claims the request first'
    expect-contains "${text}" 'http-request set-var(txn.part) str(shop) if !{ var(txn.part) -m found } part_shop_host'$'\n'
    expect-contains "${text}" 'http-request deny deny_status 404 unless { var(txn.part) -m found } || { path_beg /.well-known/acme-challenge/ }'
    expect-contains "${text}" 'use_backend shop_%[var(txn.slot)] if { var(txn.part) -m str shop }'
    expect-equal "$(grep -c 'http-request set-var(txn.part) str(desk)' <<< "${text}")" 2 'the candidate frontend selects parts the same way'
    expect-contains "${text}" 'http-check send meth GET uri /health ver HTTP/1.1 hdr Host api.shop.test'
    expect-contains "${text}" 'http-check send meth GET uri /desk/health ver HTTP/1.1 hdr Host shop.test'
    expect-contains "${text}" 'server-template replica 1-32 core-blue:8000 check resolvers docker'
    expect-contains "${text}" 'server-template replica 1-32 shop-green:3000 check resolvers docker'
    expect-contains "${text}" 'observe layer7 error-limit 10 on-error mark-down init-state fully-down'
    expect-contains "${text}" 'retry-on conn-failure empty-response'
    expect-contains "${text}" 'ssl-default-bind-curves X25519MLKEM768:X25519:P-256:P-384'
    expect-contains "${text}" '"path":"%HP"'
    expect-absent "${text}" '%HU'
    expect-absent "${text}" 'allow-0rtt'
    expect-absent "${text}" '{{'
    expect-equal "$(grep -c 'http-check expect status 200$' <<< "${text}")" 4
    expect-equal "$(grep -c 'http-check expect status 200-399$' <<< "${text}")" 2
    expect-equal "$(grep -c 'balance leastconn' <<< "${text}")" 2
    expect-equal "$(grep -c 'balance roundrobin' <<< "${text}")" 4

    cfg-set HTTPS_PORT 18443
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" "Alt-Svc 'h3=\":18443\"; ma=86400'"
    expect-contains "${text}" 'field(1,:)]:18443 code 308'

    cfg-set HTTP3_ENABLED false
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" 'quic4'
    expect-absent "${text}" 'Alt-Svc'
    expect-contains "${text}" 'alpn h2,http/1.1'

    cfg-set TLS_ENABLED false
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" ':8443'
    expect-absent "${text}" 'Strict-Transport-Security'
    expect-contains "${text}" 'bind :8081'

    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set HTTPS_PORT 443
    cfg-set EDGE_SOCKETS /srv/edge
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" 'bind unix@/sockets/http.sock mode 666 accept-proxy'$'\n'
    expect-contains "${text}" 'bind unix@/sockets/https.sock mode 666 accept-proxy ssl crt /etc/haproxy-tls/certs/ strict-sni alpn h2,http/1.1'
    expect-contains "${text}" 'bind :8444 ssl crt'
    expect-absent "${text}" 'bind :8080'
    expect-absent "${text}" 'bind :8443'
    expect-absent "${text}" 'quic4'
    expect-absent "${text}" 'Alt-Svc'
    expect-contains "${text}" 'field(1,:)] code 308'

    cfg-set EDGE_SOCKETS ''
    cfg-set TRUSTED_HEADER X-Forwarded-For
    cfg-set TRUSTED_RANGES '198.51.100.0/24 203.0.113.0/24 2001:db8::/32'
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" 'acl trusted src 198.51.100.0/24 203.0.113.0/24 2001:db8::/32'
    expect-contains "${text}" 'http-request set-src req.hdr_ip(X-Forwarded-For,-1) if trusted { req.hdr(X-Forwarded-For) -m found }'
    expect-equal "$(grep -n 'set-src' <<< "${text}" | cut -d: -f1)" "$(( $(grep -n 'acl part_core_host' <<< "${text}" | head -1 | cut -d: -f1) - 1 ))" 'the client is restored before any rule reads it'

    cfg-set TRUSTED_RANGES "$(printf '10.%s.0.0/16 ' {1..40})"
    haproxy-render "${directory}" "${core}"
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-equal "$(grep -c 'acl trusted src' <<< "${text}")" 4 'long range lists split across acl lines'
    cfg-set TRUSTED_RANGES '1.2.3.4/32 bad;range'
    expect-error 'Invalid trusted range: bad;range' haproxy-render "${directory}" "${core}"
    cfg-set TRUSTED_RANGES ''
    cfg-set TRUSTED_HEADER ''

    expect-error 'Invalid readiness path for core' haproxy-render "${directory}" 'core|api.shop.test|8000|/|/x;y|leastconn|200||slot'
    expect-error 'Invalid route path for core' haproxy-render "${directory}" 'core|api.shop.test|8000|/v1/|/v1/health|leastconn|200||slot'
    expect-error 'Invalid balance for core' haproxy-render "${directory}" 'core|api.shop.test|8000|/|/|random|200||slot'
    expect-error 'Invalid readiness status for core: 2xx' haproxy-render "${directory}" 'core|api.shop.test|8000|/|/|leastconn|2xx||slot'
    expect-error 'Invalid route domain for core' haproxy-render "${directory}" 'core|api.shop.test bad_host|8000|/|/|leastconn|200||slot'
    expect-error 'Route core needs a domain' haproxy-render "${directory}" 'core||8000|/|/|leastconn|200||slot'

}
test-edge-compose () {

    local text=""

    fixture-release
    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set BIND_ADDRESS 0.0.0.0
    native-edge-render "${TMPDIR}/edge"
    text="$(fs-read "${TMPDIR}/edge/edge.yaml")"

    expect-contains "${text}" 'ports: ["0.0.0.0:80:8080/tcp", "0.0.0.0:443:8443/tcp", "0.0.0.0:443:8443/udp"]'
    expect-contains "${text}" 'nofile: {soft: 65536, hard: 65536}'
    expect-contains "${text}" "tls:/etc/haproxy-tls:ro"$'\n'
    expect-absent "${text}" '9090/tcp'
    expect-absent "${text}" '/sockets'
    expect-absent "${text}" '{{'

    cfg-set HTTP3_ENABLED false
    cfg-set METRICS_ENABLED true
    native-edge-render "${TMPDIR}/edge"
    text="$(fs-read "${TMPDIR}/edge/edge.yaml")"
    expect-absent "${text}" '/udp'
    expect-contains "${text}" '"127.0.0.1:9090:9090/tcp"]'

    cfg-set HTTP3_ENABLED true
    cfg-set EDGE_SOCKETS /srv/edge
    native-edge-render "${TMPDIR}/edge"
    text="$(fs-read "${TMPDIR}/edge/edge.yaml")"
    expect-contains "${text}" 'ports: ["127.0.0.1:9090:9090/tcp"]' 'a relay owns the public ports'
    expect-contains "${text}" $'tls:/etc/haproxy-tls:ro\n      - type: bind\n        source: "/srv/edge"\n        target: /sockets\n'
    expect-equal "$(native-firewall-ports | paste -sd ' ' -)" '80/tcp 443/tcp' 'the relay still needs the public TCP ports, never UDP'
    expect-equal "$(native-protocols)" 'http/1.1 h2'

    cfg-set METRICS_ENABLED false
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/edge.yaml")" 'ports: []'

    cfg-set EDGE_SOCKETS ''
    expect-equal "$(native-firewall-ports | paste -sd ' ' -)" '80/tcp 443/tcp 443/udp'
    expect-equal "$(native-protocols)" 'http/1.1 h2 h3'

    cfg-set TRUSTED_HEADER True-Client-IP
    cfg-set TRUSTED_PROXIES '198.51.100.0/24'
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 198.51.100.0/24' 'literal ranges need no fetch'

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'out=""' 'cat > /dev/null' \
        'while (( $# > 0 )); do [[ "$1" != --output ]] || out="$2"; shift; done' \
        'if [[ -f "${TMPDIR}/ranges.down" ]]; then false' \
        'else printf "%s" "{\"ranges\":[\"203.0.113.0/24\",\"192.0.2.0/24\",\"2001:db8::/32\"]}" > "${out}"; fi' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set TRUSTED_PROXIES 'https://proxy.example/ips 198.51.100.0/24'
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 192.0.2.0/24 2001:db8::/32 203.0.113.0/24 198.51.100.0/24' 'published lists are fetched, sorted and recorded'
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'req.hdr_ip(True-Client-IP,-1)'
    touch "${TMPDIR}/ranges.down"
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 192.0.2.0/24' 'an unreachable list keeps the recorded ranges'
    expect-contains "$(native-edge-refresh 2>&1)" 'Keeping the recorded trusted proxy ranges'
    cfg-set TRUSTED_PROXIES 'https://other.example/ips'
    expect-error 'Trusted proxy ranges unreachable or empty: https://other.example/ips' native-edge-render "${TMPDIR}/edge"
    rm -f "${TMPDIR}/ranges.down"

    cfg-set TRUSTED_PROXIES ''
    cfg-set TRUSTED_HEADER ''
    native-edge-render "${TMPDIR}/edge"
    expect-absent "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'set-src' 'direct clients trust no header'

}
test-edge-stats () {

    local stats=""

    stats="$(fixture-stats 4)"

    expect-equal "$(haproxy-up "${stats}" core_blue)" 2
    expect-equal "$(haproxy-up "${stats}" core_green)" 0
    expect-equal "$(haproxy-field "${stats}" core_blue BACKEND 4)" 4
    expect-equal "$(haproxy-field "${stats}" core_blue replica1 17)" UP
    expect-equal "$(haproxy-server "${stats}" core_blue 172.18.0.6)" replica2
    expect-fail haproxy-server "${stats}" core_blue 172.18.0.9
    expect-fail haproxy-server "${stats}" core_blue 172.18.0.50
    expect-fail haproxy-field "${stats}" core_blue replica9 4

}
test-edge-runtime () {

    local stats=""

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'cat > /dev/null' 'cat "${TMPDIR}/runtime.reply"' > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"
    PATH="${TMPDIR}/bin:${PATH}"

    {
        printf '# pxname,svname,qcur,qmax,scur\n'
        printf 'core_green,replica1,0,0,0,0,128,,,,,,,,,,,DOWN,,,,,,,,,,,,,,,,,,,L7STS,404,,,,,,,,,,,,,,,,,,-1,File not found,,,,,,,,Layer7 wrong status\n'
        printf 'core_green,BACKEND,0,0,0,0,128,,,,,,,,,,,DOWN\n'
    } > "${TMPDIR}/runtime.reply"

    stats="$(haproxy-stats edge-container)"
    expect-contains "${stats}" 'File not found' 'a health check reason inside the stats is data, not a refusal'
    haproxy-idle edge-container core_green

    printf 'No such server.\n' > "${TMPDIR}/runtime.reply"
    expect-error 'HAProxy refused: set' haproxy-state edge-container core_green replica1 drain

    printf "Unknown command: 'show stats'\n" > "${TMPDIR}/runtime.reply"
    expect-error 'HAProxy refused: show' haproxy-stats edge-container

}
test-edge-limits () {

    local directory="${TMPDIR}/edge" text=""

    fixture-release
    cfg-set RATE_LIMIT_GLOBAL 5000/10s
    cfg-set RATE_LIMIT_IP 20/1s
    cfg-set RATE_LIMIT_PATHS '/v1/auth=10/1m,/v1/upload=5/1h'
    haproxy-render "${directory}" 'core|api.shop.test|8000|/|/health|leastconn|200|1000/1m|slot' 'grafana|grafana.shop.test|3000|/|/api/health|roundrobin|200||static'
    text="$(fs-read "${directory}/haproxy.cfg")"

    expect-contains "${text}" 'http-request track-sc0 int(1) table limit_global unless { path_beg /.well-known/acme-challenge/ }'
    expect-contains "${text}" 'http-request deny deny_status 429 hdr Retry-After 10 if { sc_http_req_rate(0) gt 5000 }'
    expect-contains "${text}" 'http-request track-sc1 src table limit_part_core if { var(txn.part) -m str core } !{ path_beg /.well-known/acme-challenge/ }'
    expect-contains "${text}" 'hdr Retry-After 60 if { var(txn.part) -m str core } { sc_http_req_rate(1) gt 1000 }'
    expect-contains "${text}" 'http-request track-sc2 src table limit_ip'
    expect-contains "${text}" 'http-request track-sc3 src table limit_path_1 if { path_beg /v1/auth }'
    expect-contains "${text}" 'hdr Retry-After 3600 if { path_beg /v1/upload } { sc_http_req_rate(3) gt 5 }'
    expect-contains "${text}" 'stick-table type integer size 1 expire 20s store http_req_rate(10s)'
    expect-contains "${text}" 'stick-table type ipv6 size 1m expire 7200s store http_req_rate(3600s)'
    expect-contains "${text}" 'tune.stick-counters 4'
    expect-contains "${text}" 'use_backend grafana if { var(txn.part) -m str grafana }'
    expect-contains "${text}" 'server-template replica 1-1 grafana:3000 check resolvers docker'
    expect-absent "${text}" 'backend grafana_blue'
    expect-absent "${text}" 'limit_part_grafana'
    expect-absent "${text}" '{{'
    (( $(grep -n 'set-var(txn.part) str(core)' <<< "${text}" | head -1 | cut -d: -f1) < $(grep -n 'track-sc0' <<< "${text}" | cut -d: -f1) )) || err "Parts must be selected before any limit reads them"

    cfg-set RATE_LIMIT_GLOBAL ''
    cfg-set RATE_LIMIT_IP ''
    cfg-set RATE_LIMIT_PATHS ''
    haproxy-render "${directory}" 'core|api.shop.test|8000|/|/health|leastconn|200||slot'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" 'track-sc'
    expect-absent "${text}" 'stick-table'

    expect-error 'Invalid route kind for core: other' haproxy-render "${directory}" 'core|api.shop.test|8000|/|/health|leastconn|200||other'
    expect-error 'Invalid rate: 10/1d' haproxy-render "${directory}" 'core|api.shop.test|8000|/|/health|leastconn|200|10/1d|slot'
    expect-error 'Invalid rate: 10/1d' haproxy-rate 10/1d

}
test-edge-readiness () {

    local directory=""

    fixture-release
    fixture-sites
    state-write "${CONFIG[STATE_ROOT]}" current r1
    directory="$(native-directory r1)"
    mkdir -p "${directory}"
    printf '%s\n' "PARTS='core desk'" 'CORE_PATH=/' 'CORE_READY=/health' 'CORE_PORT=8000' 'DESK_PATH=/desk' 'DESK_READY=/desk/health' 'DESK_PORT=3000' > "${directory}/release.env"

    native-edge-readiness

    cfg-set CORE_READY /ready
    cfg-set DESK_PORT 3001
    cfg-set SHOP_PORT 3005
    expect-error 'CORE_READY from /health to /ready, DESK_PORT from 3000 to 3001 while r1 is live' native-edge-readiness
    expect-error 'accept the gap with infra edge apply --force' native-edge-readiness

    cli-parse edge apply --force
    expect-contains "$(native-edge-readiness 2>&1)" 'r1 fails its health checks until a release serving the new values switches in'
    cli-parse

    state-write "${CONFIG[STATE_ROOT]}" current ''
    native-edge-readiness

}
test-edge-domains () {

    local directory="${TMPDIR}/edge" text="" live=""

    fixture-release
    fixture-sites
    cfg-set HAPROXY_DOMAINS true
    haproxy-render "${directory}" 'core|api.shop.test|8000|/|/health|leastconn|200||slot' 'shop||3000|/|/|roundrobin|200-399|100/1m|slot'
    text="$(fs-read "${directory}/haproxy.cfg")"

    expect-contains "${text}" 'http-request set-var(txn.part) req.hdr(host),lower,field(1,:),map_str(/etc/haproxy/domains.map) if !{ var(txn.part) -m found }'
    expect-contains "${text}" 'http-check send meth GET uri / ver HTTP/1.1 hdr Host localhost'
    expect-contains "${text}" 'use_backend shop_%[var(txn.slot)] if { var(txn.part) -m str shop }'
    expect-contains "${text}" 'track-sc1 src table limit_part_shop if { var(txn.part) -m str shop }' 'a dynamic domain gets the policies of its part'
    expect-absent "${text}" 'acl part_shop_host'
    (( $(grep -n 'map_str' <<< "${text}" | head -1 | cut -d: -f1) < $(grep -n 'unless { var(txn.part) -m found }' <<< "${text}" | cut -d: -f1) )) || err "The map must be read before unknown hosts are refused"

    cfg-set HAPROXY_DOMAINS false
    expect-error 'Route shop needs a domain' haproxy-render "${directory}" 'shop||3000|/|/|roundrobin|200-399||slot'

    cfg-set SHOP_DOMAIN ''
    cfg-set DESK_DOMAIN ''
    config-derive
    expect-equal "$(native-edge-routes | cut -d'|' -f1 | paste -sd ' ' -)" core
    expect-equal "${CONFIG[PARTS]}" core
    cfg-set DOMAINS_ENDPOINT https://api.shop.test/internal/domains
    cfg-set DOMAINS_TOKEN domains-sentinel-token
    config-derive
    expect-equal "$(native-edge-routes | cut -d'|' -f1 | paste -sd ' ' -)" 'core shop desk' 'with dynamic domains every part has backends'
    expect-equal "${CONFIG[PARTS]}" 'core shop desk' 'a part with an image ships when dynamic domains are on'

    live="${CONFIG[STATE_ROOT]}/edge"
    mkdir -p "${live}"
    printf '%s\n' 'a.acme.example shop' 'b.other.example desk' 'c.third.example shop' > "${live}/domains.wanted"
    cfg-set TLS_ENABLED false
    expect-equal "$(native-domains-routable)" "$(fs-read "${live}/domains.wanted")" 'without TLS every wanted domain routes'
    cfg-set TLS_ENABLED true
    state-write "${CONFIG[STATE_ROOT]}" certificates $'acme.example a.acme.example\nother.example imported'
    expect-equal "$(native-domains-routable)" $'a.acme.example shop\nb.other.example desk' 'a domain routes once its certificate exists'
    expect-contains "$(native-domains | paste -sd ' ' -)" 'c.third.example' 'a pending domain is certified'
    expect-absent "$(native-domains fixed | paste -sd ' ' -)" 'acme.example' 'expiry checks cover the fixed domains'

    fixture-curl
    native-certificate-run () { cfg-set CERTIFICATES_CHANGED false; }
    native-edge-reload () { touch "${TMPDIR}/reloaded"; }
    native-edge-reload
    rm -f -- "${TMPDIR}/reloaded"
    cfg-set TLS_ENABLED false
    rm -f -- "${live}/domains.wanted"
    printf '%s' '{"domains":[{"domain":"a.example","part":"shop"},{"domain":"b.example","part":"desk"}]}' > "${TMPDIR}/payload.json"

    native-edge-sync-run
    expect-equal "$(fs-read "${live}/domains.map")" $'a.example shop\nb.example desk'
    test -e "${TMPDIR}/reloaded" || err "New domains must reload the edge"

    rm -f -- "${TMPDIR}/reloaded"
    native-edge-sync-run
    expect-fail test -e "${TMPDIR}/reloaded" 'an unchanged list leaves the edge alone'

    printf '%s' '{"domains":[]}' > "${TMPDIR}/payload.json"
    expect-error 'DOMAINS_ENDPOINT drops 2 of 2 domains' native-edge-sync-run
    expect-equal "$(fs-read "${live}/domains.map")" $'a.example shop\nb.example desk' 'a refused list changes nothing'
    cli-parse edge sync --force
    native-edge-sync-run
    expect-equal "$(fs-read "${live}/domains.map")" '' 'force accepts the drop'
    cli-parse

}
test-edge-bootstrap () {

    fixture-release
    mkdir -p "${CONFIG[STATE_ROOT]}/edge"
    cfg-set TLS_ENABLED true

    native-edge-render () { printf 'render tls=%s\n' "${CONFIG[TLS_ENABLED]}" >> "${TMPDIR}/edge.calls"; }
    haproxy-check () { :; }
    native-compose-edge () { printf '%s\n' "$*" >> "${TMPDIR}/edge.calls"; }
    native-edge-alive () { :; }
    native-certificate () { printf 'issue\n' >> "${TMPDIR}/edge.calls"; }
    native-edge-reload () { printf 'reload\n' >> "${TMPDIR}/edge.calls"; }
    haproxy-check
    native-edge-alive

    native-edge-bootstrap
    expect-equal "$(fs-read "${TMPDIR}/edge.calls")" $'render tls=false\nup -d edge\nissue\nrender tls=true\nup -d edge\nreload' 'the TLS edge reloads after the plain bootstrap, so a socket relay serves the new configuration'
    expect-equal "${CONFIG[TLS_ENABLED]}" true

    state-write "${CONFIG[STATE_ROOT]}" current r1
    expect-error 'The live edge lost its certificates' native-edge-bootstrap

}
