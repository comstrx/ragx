fixture-stats () {

    local header='# pxname,svname,qcur,qmax,scur'
    local tail=',0,0,0,0,0,0,0,0,0,0,,,,0,0,0,,,,,-1,"Layer7 wrong status, code 503",,0,0,0,0,,,,Layer4 connection problem,,2,3,0,,,,'

    out "${header}"
    out "api_blue,replica1,0,0,${1:-0},0,,0,0,0,,0,,0,0,0,0,UP,1,1,0,0,1,2,2,,1,3,1,,0,,2,0,,0,L7OK${tail}172.18.0.5:8000,,http"
    out "api_blue,replica2,0,0,0,0,,0,0,0,,0,,0,0,0,0,UP,1,1,0,0,1,2,2,,1,3,2,,0,,2,0,,0,L7OK${tail}172.18.0.6:8000,,http"
    out "api_blue,replica3,0,0,0,0,,0,0,0,,0,,0,0,0,0,MAINT (resolution),1,1,0,0,1,2,2,,1,3,3,,0,,2,0,,0,,${tail},,http"
    out "api_blue,BACKEND,0,0,${1:-0},0,,0,0,0,,0,,0,0,0,0,UP,2,2,0,,0,2,0,,1,3,0,,0,,1,0,,0,,${tail},,http"
    out "api_green,replica1,0,0,0,0,,0,0,0,,0,,0,0,0,0,DOWN,1,1,0,0,1,2,2,,1,4,1,,0,,2,0,,0,L4CON${tail}172.18.0.9:8000,,http"

}
test-edge-protocols () {

    local directory="${TMPDIR}/edge" text=""

    fixture-release
    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set HTTPS_PORT 443
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200' 'web-client|shop.test|3000|/|roundrobin|200-399'
    text="$(fs-read "${directory}/haproxy.cfg")"

    expect-contains "${text}" 'bind :8443 ssl crt /etc/haproxy-tls/site.pem strict-sni alpn h2,http/1.1'
    expect-contains "${text}" 'bind quic4@:8443 ssl crt /etc/haproxy-tls/site.pem strict-sni ssl-min-ver TLSv1.3 alpn h3'
    expect-contains "${text}" "set-header Alt-Svc 'h3=\":443\"; ma=86400' if { ssl_fc }"
    expect-contains "${text}" 'Strict-Transport-Security "max-age=63072000"'
    expect-contains "${text}" 'redirect prefix https://%[req.hdr(host),lower,field(1,:)] code 308'
    expect-contains "${text}" 'm str api.shop.test shop.test }'
    expect-contains "${text}" 'use_backend web-client_%[var(txn.slot)] if { req.hdr(host),lower,field(1,:) -m str shop.test }'
    expect-contains "${text}" 'server-template replica 1-32 api-blue:8000 check resolvers docker'
    expect-contains "${text}" 'server-template replica 1-32 web-client-green:3000 check resolvers docker'
    expect-contains "${text}" 'observe layer7 error-limit 10 on-error mark-down init-state fully-down'
    expect-contains "${text}" 'retry-on conn-failure empty-response'
    expect-contains "${text}" 'ssl-default-bind-curves X25519MLKEM768:X25519:P-256:P-384'
    expect-contains "${text}" '"path":"%HP"'
    expect-absent "${text}" '%HU'
    expect-absent "${text}" 'allow-0rtt'
    expect-absent "${text}" '{{'
    expect-equal "$(grep -c 'http-check expect status 200$' <<< "${text}")" 2
    expect-equal "$(grep -c 'http-check expect status 200-399$' <<< "${text}")" 2
    expect-equal "$(grep -c 'balance leastconn' <<< "${text}")" 2
    expect-equal "$(grep -c 'balance roundrobin' <<< "${text}")" 2

    cfg-set HTTPS_PORT 18443
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" "Alt-Svc 'h3=\":18443\"; ma=86400'"
    expect-contains "${text}" 'field(1,:)]:18443 code 308'

    cfg-set HTTP3_ENABLED false
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" 'quic4'
    expect-absent "${text}" 'Alt-Svc'
    expect-contains "${text}" 'alpn h2,http/1.1'

    cfg-set TLS_ENABLED false
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" ':8443'
    expect-absent "${text}" 'Strict-Transport-Security'
    expect-contains "${text}" 'bind :8081'

    cfg-set TLS_ENABLED true
    cfg-set HTTP3_ENABLED true
    cfg-set HTTPS_PORT 443
    cfg-set EDGE_SOCKETS /srv/edge
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" 'bind unix@/sockets/http.sock mode 666 accept-proxy'$'\n'
    expect-contains "${text}" 'bind unix@/sockets/https.sock mode 666 accept-proxy ssl crt /etc/haproxy-tls/site.pem strict-sni alpn h2,http/1.1'
    expect-contains "${text}" 'bind :8444 ssl crt'
    expect-absent "${text}" 'bind :8080'
    expect-absent "${text}" 'bind :8443'
    expect-absent "${text}" 'quic4'
    expect-absent "${text}" 'Alt-Svc'
    expect-contains "${text}" 'field(1,:)] code 308'

    cfg-set EDGE_SOCKETS ''
    cfg-set TRUSTED_HEADER X-Forwarded-For
    cfg-set TRUSTED_RANGES '173.245.48.0/20 103.21.244.0/22 2400:cb00::/32'
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-contains "${text}" 'acl trusted src 173.245.48.0/20 103.21.244.0/22 2400:cb00::/32'
    expect-contains "${text}" 'http-request set-src req.hdr_ip(X-Forwarded-For,-1) if trusted { req.hdr(X-Forwarded-For) -m found }'
    expect-equal "$(grep -n 'set-src' <<< "${text}" | cut -d: -f1)" "$(( $(grep -n 'm str api.shop.test }' <<< "${text}" | head -1 | cut -d: -f1) - 1 ))" 'the client is restored before any rule reads it'

    cfg-set TRUSTED_RANGES "$(printf '10.%s.0.0/16 ' {1..40})"
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-equal "$(grep -c 'acl trusted src' <<< "${text}")" 4 'long range lists split across acl lines'
    cfg-set TRUSTED_RANGES '1.2.3.4/32 bad;range'
    expect-error 'Invalid trusted range: bad;range' haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    cfg-set TRUSTED_RANGES ''
    cfg-set TRUSTED_HEADER ''

    expect-error 'Invalid readiness path for api' haproxy-render "${directory}" 'api|api.shop.test|8000|/x;y|leastconn|200'
    expect-error 'Invalid balance for api' haproxy-render "${directory}" 'api|api.shop.test|8000|/|random|200'
    expect-error 'Invalid readiness status for api: 2xx' haproxy-render "${directory}" 'api|api.shop.test|8000|/|leastconn|2xx'
    expect-error 'Invalid route host for api' haproxy-render "${directory}" 'api|bad host|8000|/|leastconn|200'

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

    cfg-set TRUSTED_HEADER CF-Connecting-IP
    cfg-set TRUSTED_PROXIES '198.51.100.0/24'
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 198.51.100.0/24' 'literal ranges need no fetch'

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'out=""' 'cat > /dev/null' \
        'while (( $# > 0 )); do [[ "$1" != --output ]] || out="$2"; shift; done' \
        'if [[ -f "${TMPDIR}/ranges.down" ]]; then false' \
        'else printf "%s" "{\"result\":{\"ipv4_cidrs\":[\"173.245.48.0/20\",\"103.21.244.0/22\"],\"ipv6_cidrs\":[\"2400:cb00::/32\"]},\"etag\":\"38f79d05\"}" > "${out}"; fi' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set TRUSTED_PROXIES 'https://proxy.example/ips 198.51.100.0/24'
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 103.21.244.0/22 173.245.48.0/20 2400:cb00::/32 198.51.100.0/24' 'published lists are fetched, sorted and recorded'
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'req.hdr_ip(CF-Connecting-IP,-1)'
    touch "${TMPDIR}/ranges.down"
    native-edge-render "${TMPDIR}/edge"
    expect-contains "$(fs-read "${TMPDIR}/edge/haproxy.cfg")" 'acl trusted src 103.21.244.0/22' 'an unreachable list keeps the recorded ranges'
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

    expect-equal "$(haproxy-up "${stats}" api_blue)" 2
    expect-equal "$(haproxy-up "${stats}" api_green)" 0
    expect-equal "$(haproxy-field "${stats}" api_blue BACKEND 4)" 4
    expect-equal "$(haproxy-field "${stats}" api_blue replica1 17)" UP
    expect-equal "$(haproxy-server "${stats}" api_blue 172.18.0.6)" replica2
    expect-fail haproxy-server "${stats}" api_blue 172.18.0.9
    expect-fail haproxy-server "${stats}" api_blue 172.18.0.50
    expect-fail haproxy-field "${stats}" api_blue replica9 4

}
test-edge-limits () {

    local directory="${TMPDIR}/edge" text=""

    fixture-release
    cfg-set RATE_LIMIT_GLOBAL 5000/10s
    cfg-set RATE_LIMIT_HOST 1000/1m
    cfg-set RATE_LIMIT_IP 20/1s
    cfg-set RATE_LIMIT_PATHS '/v1/auth=10/1m,/v1/upload=5/1h'
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200' 'grafana|grafana.shop.test|3000|/api/health|roundrobin|200|static'
    text="$(fs-read "${directory}/haproxy.cfg")"

    expect-contains "${text}" 'http-request track-sc0 int(1) table limit_global unless { path_beg /.well-known/acme-challenge/ }'
    expect-contains "${text}" 'http-request deny deny_status 429 hdr Retry-After 10 if { sc_http_req_rate(0) gt 5000 }'
    expect-contains "${text}" 'http-request track-sc1 req.hdr(host),lower,field(1,:) table limit_host'
    expect-contains "${text}" 'hdr Retry-After 60 if { sc_http_req_rate(1) gt 1000 }'
    expect-contains "${text}" 'http-request track-sc2 src table limit_ip'
    expect-contains "${text}" 'http-request track-sc3 src table limit_path_1 if { path_beg /v1/auth }'
    expect-contains "${text}" 'hdr Retry-After 3600 if { path_beg /v1/upload } { sc_http_req_rate(3) gt 5 }'
    expect-contains "${text}" 'stick-table type integer size 1 expire 20s store http_req_rate(10s)'
    expect-contains "${text}" 'stick-table type ipv6 size 1m expire 7200s store http_req_rate(3600s)'
    expect-contains "${text}" 'tune.stick-counters 4'
    expect-contains "${text}" 'use_backend grafana if { req.hdr(host),lower,field(1,:) -m str grafana.shop.test }'
    expect-contains "${text}" 'server-template replica 1-1 grafana:3000 check resolvers docker'
    expect-contains "${text}" 'm str api.shop.test grafana.shop.test }'
    expect-absent "${text}" 'backend grafana_blue'
    expect-absent "${text}" '{{'

    cfg-set RATE_LIMIT_GLOBAL ''
    cfg-set RATE_LIMIT_HOST ''
    cfg-set RATE_LIMIT_IP ''
    cfg-set RATE_LIMIT_PATHS ''
    haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200'
    text="$(fs-read "${directory}/haproxy.cfg")"
    expect-absent "${text}" 'track-sc'
    expect-absent "${text}" 'stick-table'

    expect-error 'Invalid route kind for api: other' haproxy-render "${directory}" 'api|api.shop.test|8000|/health|leastconn|200|other'
    expect-error 'Invalid rate: 10/1d' haproxy-rate 10/1d

}
