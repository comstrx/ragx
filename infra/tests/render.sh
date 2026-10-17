#!/usr/bin/env bash

stack_probe_config () {

    local file="${1:?stack_probe_config needs a file}"

    printf '%s\n' "$@" 'STACK=production' 'PROJECT=probe' 'BASE_DOMAIN=probe.test' 'GIT_REPO_URL=https://github.com/comstrx/ragx.git' \
        'SSH_HOST=203.0.113.10' 'SSL_EMAIL=ops@probe.test' 'IMAGE_TAG_OVERRIDE=probe' \
        'DB_PASSWORD=db-pw' 'PG_PASSWORD=pg-pw' 'RABBITMQ_PASSWORD=p@ss' 'REDIS_PASSWORD=r/pw' 'AUTH_SECRET=auth-pw' 'GIT_TOKEN=probe-token' > "${file}"

}
stack_render () {

    local file="${1:?stack_render needs a config}" dir="${2:?stack_render needs a dir}"

    shift 2

    "${INFRA_BIN}" --config "${file}" -y -e COMPOSE_DIR="${dir}" "$@" compose render >/dev/null

}
test_render_fills_placeholders_and_refuses_missing_ones () {

    local src="" dst=""

    src="$(mktemp)"
    dst="$(mktemp)"

    printf 'name: ${PROBE_NAME}\n' > "${src}"

    PROBE_NAME=probe render "${src}" "${dst}"

    assert_eq "$(cat "${dst}")" "name: probe" "a placeholder renders from the environment"
    assert_fails "an undefined placeholder refuses to render" env -u PROBE_NAME bash -c "source '${INFRA_BIN}'; render '${src}' '${dst}'"

    rm -f "${src}" "${dst}"

}
test_the_stack_renders_with_every_service_wired_to_the_api () {

    local file="" build="" dir="" env=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dir="${build}/stack"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    stack_render "${file}" "${dir}"

    env="$(cat "${dir}/api.env")"

    assert_eq "$(stat -c %a "${dir}/api.env")" "600" "the app env is private"
    assert_eq "$(grep -c '\${' "${dir}/compose.yaml")" "0" "no placeholder survives into the compose file"
    assert_contains "$(cat "${dir}/compose.yaml")" "image: ghcr.io/comstrx/ragx/api:probe" "the api image is the release tag under the repository's registry path"
    assert_contains "$(cat "${dir}/compose.yaml")" "image: ghcr.io/comstrx/ragx/web:client-probe" "each web spec is its own image on the same tag"
    assert_contains "$(cat "${dir}/compose.yaml")" "name: probe-production" "the project is the stack"
    assert_contains "${env}" "APP_RELEASE='probe'" "the api learns its release tag"
    assert_contains "${env}" "APP_URL='https://api.probe.test'" "the api knows its public origin"
    assert_contains "${env}" "QUEUE_URL='amqp://ragx:p%40ss@rabbitmq:5672/%2F'" "the broker url carries the credentials url-encoded"
    assert_contains "${env}" "EVENT_URL='amqp://ragx:p%40ss@rabbitmq:5672/%2F'" "events ride the same broker"
    assert_contains "${env}" "CACHE_URL='redis://ragx:r%2Fpw@redis:6379/0'" "the cache url carries the credentials url-encoded"
    assert_contains "${env}" "EVENT_QUEUE='probe.events'" "the event inbox is named after the project"
    assert_contains "${env}" "QUEUE_WORKERS='0'" "the http process runs no workers when a worker service exists"
    assert_contains "${env}" "SCHEDULE_ENABLED='false'" "the http process runs no schedule when a scheduler service exists"
    assert_contains "${env}" "APP_ORIGINS='[\"https://super.probe.test\",\"https://admin.probe.test\",\"https://probe.test\",\"https://www.probe.test\"]'" "cors admits exactly the web surfaces"
    assert_contains "$(cat "${dir}/postgres.env")" "APP_DB_PASSWORD='db-pw'" "the role init learns the app password"
    assert_contains "$(cat "${dir}/rabbitmq.env")" "RABBITMQ_DEFAULT_PASS='p@ss'" "the broker learns its password literally"
    assert_contains "$(cat "${dir}/compose.yaml")" "--user default off resetpass -@all --user" "the cache users are declared on the command line from the container's own env — no acl file on disk"
    assert_contains "$(cat "${dir}/redis.env")" "REDISCLI_AUTH='r/pw'" "the cache password reaches redis literally"
    assert_contains "$(cat "${dir}/postgres/pg_hba.conf")" "host    all   ragx      samenet         scram-sha-256" "the app role reaches postgres from the stack network only"
    assert_ok "the role init is executable" test -x "${dir}/postgres/init.sh"
    assert_ok "the stack unit is rendered" test -f "${dir}/systemd/probe-production.service"
    assert_ok "the backup timer is rendered" test -f "${dir}/systemd/probe-production-backup.timer"
    assert_ok "the renewal timer is rendered when tls is on" test -f "${dir}/systemd/probe-production-renew.timer"

    assert_eq "$("${INFRA_BIN}" --config "${file}" -e WORKER_REPLICAS=0 -e SCHEDULER_ENABLED=false ci setting COMPOSE_PROFILES)" "web" "no worker and no scheduler — the api runs them in process"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e WORKER_REPLICAS=0 ci setting API_QUEUE_WORKERS)" "2" "without a worker service the http process keeps its workers"

    rm -rf "${file}" "${build}"

}
test_the_edge_follows_the_certificate_state () {

    local file="" build="" dir=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dir="${build}/stack"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    stack_render "${file}" "${dir}"

    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "listen 8443 ssl;" "the api site listens on tls"
    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "listen 8443 quic;" "the api site speaks http/3"
    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "include /etc/nginx/platform/tls.inc;" "the api site includes the tls policy"
    assert_contains "$(cat "${dir}/nginx/conf.d/00-http.conf")" 'return 301 https://$host$request_uri;' "plain http redirects"
    assert_contains "$(cat "${dir}/nginx/conf.d/10-tls.conf")" "ssl_reject_handshake on;" "an unknown name gets no handshake"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" "ssl_protocols TLSv1.2 TLSv1.3;" "only modern tls"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1:secp384r1;" "post-quantum hybrid key exchange first"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" "max-age=63072000; includeSubDomains; preload" "hsts with preload"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" 'h3=":443"' "the alt-svc names the public port"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" "/etc/letsencrypt/live/probe.test/fullchain.pem" "the certificate lineage is the base domain"

    stack_render "${file}" "${dir}" -e TLS_ENABLED=false

    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "listen 8080;" "without tls the api site listens on plain http"
    assert_contains "$(cat "${dir}/nginx/conf.d/00-http.conf")" "return 444;" "without tls an unknown name is dropped"
    assert_fails "no tls policy renders without tls" test -f "${dir}/nginx/tls.inc"
    assert_fails "no tls default server renders without tls" test -f "${dir}/nginx/conf.d/10-tls.conf"
    assert_fails "no renewal timer renders without tls" test -f "${dir}/systemd/probe-production-renew.timer"
    assert_contains "$(cat "${dir}/api.env")" "APP_URL='http://api.probe.test'" "the api origin follows the scheme"
    assert_contains "$(cat "${dir}/nginx/proxy.inc")" "X-Forwarded-Port 80;" "the forwarded port is the public one"

    rm -rf "${file}" "${build}"

}
test_the_edge_carries_the_limits_the_socket_and_an_honest_client_address () {

    local file="" build="" dir=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dir="${build}/stack"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    stack_render "${file}" "${dir}" -e HTTPS_PORT=8443 -e API_PER_MINUTE=600

    assert_contains "$(cat "${dir}/nginx/nginx.conf")" "server_tokens off;" "the edge names no version"
    assert_contains "$(cat "${dir}/nginx/nginx.conf")" "rate=600r/m;" "the api rate is the knob"
    assert_contains "$(cat "${dir}/nginx/nginx.conf")" "server api:8000 resolve;" "the api upstream resolves lazily so the edge survives a rolling api"
    assert_contains "$(cat "${dir}/nginx/nginx.conf")" "limit_req_status 429;" "a limited client learns why"
    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "limit_req zone=auth burst=20 nodelay;" "auth has its own tighter bucket"
    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" 'proxy_set_header Connection $connection_upgrade;' "the socket upgrades"
    assert_contains "$(cat "${dir}/nginx/conf.d/20-api.conf")" "proxy_cache assets;" "assets and public files are cached at the edge"
    assert_contains "$(cat "${dir}/nginx/site.inc")" "limit_conn perip 200;" "connections per address are capped"
    assert_contains "$(cat "${dir}/nginx/proxy.inc")" 'proxy_set_header X-Forwarded-For $remote_addr;' "the forwarded address is set, never appended — the api trusts its first hop"
    assert_contains "$(cat "${dir}/nginx/proxy.inc")" "X-Forwarded-Port 8443;" "a custom public port is forwarded"
    assert_contains "$(cat "${dir}/nginx/tls.inc")" 'h3=":8443"' "the alt-svc follows the public port"
    assert_contains "$(cat "${dir}/api.env")" "APP_URL='https://api.probe.test:8443'" "a non-default port reaches the api origin"
    assert_fails "no shield, no real-ip rewrite" test -f "${dir}/nginx/conf.d/05-realip.conf"

    stack_render "${file}" "${dir}" -e DNS_PROXIED=true

    assert_contains "$(cat "${dir}/nginx/conf.d/05-realip.conf")" "real_ip_header CF-Connecting-IP;" "behind cloudflare the client address comes from its header"
    assert_contains "$(cat "${dir}/nginx/conf.d/05-realip.conf")" "set_real_ip_from 173.245.48.0/20;" "only cloudflare's networks may say so"

    rm -rf "${file}" "${build}"

}
test_the_web_and_the_wildcard_follow_the_knobs () {

    local file="" build="" dir=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dir="${build}/stack"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    stack_render "${file}" "${dir}" -e WEB_ENABLED=false

    assert_fails "no web sites render without the web" test -f "${dir}/nginx/conf.d/30-web.conf"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e WEB_ENABLED=false ci setting COMPOSE_PROFILES)" "worker,scheduler" "the web profile stays off"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e WEB_ENABLED=false ci setting TLS_NAMES)" "api.probe.test" "the certificate covers the api only"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e WEB_ENABLED=false ci setting API_ORIGINS)" "[]" "cors admits nobody without a web"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting TLS_DNS01)" "false" "no token, no dns-01"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting DNS_MANAGED)" "false" "no token, no managed names"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting CLIENT_HOSTS)" "probe.test www.probe.test" "http-01 covers the named hosts only"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting TLS_NAMES)" "api.probe.test super.probe.test admin.probe.test probe.test www.probe.test" "every surface is a certified name"

    stack_render "${file}" "${dir}" -e CLOUDFLARE_API_TOKEN=cf-token

    assert_eq "$("${INFRA_BIN}" --config "${file}" -e CLOUDFLARE_API_TOKEN=cf-token ci setting TLS_DNS01)" "true" "a token turns dns-01 on"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e CLOUDFLARE_API_TOKEN=cf-token ci setting TLS_WILDCARD)" "true" "dns-01 brings the wildcard"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e CLOUDFLARE_API_TOKEN=cf-token ci setting DNS_MANAGED)" "true" "a token turns the managed names on"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e CLOUDFLARE_API_TOKEN=cf-token -e DNS_MANAGED=false ci setting DNS_MANAGED)" "false" "the names can stay yours even with a token"
    assert_contains "$("${INFRA_BIN}" --config "${file}" -e CLOUDFLARE_API_TOKEN=cf-token ci setting CLIENT_HOSTS)" "*.probe.test" "tenant sites ride the wildcard"
    assert_contains "$(cat "${dir}/nginx/conf.d/30-web.conf")" "server_name probe.test www.probe.test *.probe.test;" "the client site answers every tenant name"
    assert_eq "$(env INFRA_CONFIG="${file}" CLOUDFLARE_API_TOKEN=cf-token bash -c "source '${INFRA_BIN}'; config_load; compose_ini")" "dns_cloudflare_api_token = cf-token" "certbot reads the token through a compose secret, never a file on disk"

    rm -rf "${file}" "${build}"

}
test_docker_compose_and_nginx_accept_what_the_stack_renders () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    assert_ok "docker compose accepts every stack" "${INFRA_BIN}" --config "${file}" -y ci compose
    assert_ok "nginx accepts the rendered edge" "${INFRA_BIN}" --config "${file}" -y ci nginx

    rm -rf "${file}" "${build}"

}
