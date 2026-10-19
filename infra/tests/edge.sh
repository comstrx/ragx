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

    expect-contains "${text}" '- "0.0.0.0:80:8080/tcp"'
    expect-contains "${text}" '- "0.0.0.0:443:8443/tcp"'
    expect-contains "${text}" '- "0.0.0.0:443:8443/udp"'
    expect-contains "${text}" 'nofile: {soft: 65536, hard: 65536}'
    expect-contains "${text}" "tls:/etc/haproxy-tls:ro"
    expect-absent "${text}" '9090/tcp'
    expect-absent "${text}" '{{'

    cfg-set HTTP3_ENABLED false
    cfg-set METRICS_ENABLED true
    native-edge-render "${TMPDIR}/edge"
    text="$(fs-read "${TMPDIR}/edge/edge.yaml")"
    expect-absent "${text}" '/udp'
    expect-contains "${text}" '- "127.0.0.1:9090:9090/tcp"'

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
