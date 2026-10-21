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
    expect-absent "$(native-edge-routes)" grafana

    cfg-set GRAFANA_HOST grafana.shop.test
    expect-equal "$(native-hosts | tr '\n' ' ')" 'api.shop.test admin.shop.test shop.test grafana.shop.test '
    expect-contains "$(native-edge-routes)" 'grafana|grafana.shop.test|3000|/api/health|roundrobin|200|static'
    expect-absent "$(native-routes)" grafana 'candidate probes never wait for Grafana'
    expect-equal "$(native-certificate-names)" 'admin.shop.test api.shop.test grafana.shop.test shop.test'

    mkdir -p "${CONFIG[STATE_ROOT]}"
    state-write "${CONFIG[STATE_ROOT]}" slot-green r1
    expect-contains "$(native-interpolation r1)" DEPLOY_SLOT=green
    expect-contains "$(native-interpolation r1)" "RELEASE_ROOT=${CONFIG[STATE_ROOT]}/releases/r1"
    expect-contains "$(native-interpolation r1)" WEB_CLIENT_REPLICAS=3
    expect-contains "$(native-interpolation r9)" DEPLOY_SLOT=blue

}
test-operations-backup-retention () {

    local root="${CONFIG[BACKUP_ROOT]}" name=""

    expect-equal "${root}" "${CONFIG[STATE_ROOT]}/backups"
    cfg-set BACKUP_DIR /srv/backups
    config-derive
    expect-equal "${CONFIG[BACKUP_ROOT]}" /srv/backups
    cfg-set BACKUP_DIR ''
    config-derive

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

    cfg-set EDGE_SOCKETS ''
    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp 443/udp '
    cfg-set HTTP3_ENABLED false
    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp '
    expect-equal "$(native-protocols)" 'http/1.1 h2'

    expect-error 'repeat with --force' native-firewall-apply
    expect-error 'Repeat with --force' native-uninstall
    expect-error 'recover --force removes a dead lock' native-recover
    expect-error 'Install timers from the staged release bundle' native-timer-install backup 3600
    expect-error 'Usage: timer install' native-timer-install shell 60
    expect-error 'Usage: restore [BACKUP] --force' native-restore one two
    expect-error 'Restore replaces the live database; rerun with --force' native-restore
    expect-error 'stop takes the edge and the current release offline' native-stop
    expect-error 'Usage: timer remove reconcile|backup|monitor|renew' native-timer-remove shell
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

    local log="${TMPDIR}/cloudflare.log" output="" zone="" record=""

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'method=GET out="" body=""' 'cat > "${TMPDIR}/cloudflare.config"' \
        'url="$(sed -n "s/^url = \"\(.*\)\"$/\1/p" "${TMPDIR}/cloudflare.config")"' \
        'while (( $# > 0 )); do case "$1" in --request) method="$2" ;; --output) out="$2" ;; --data-binary) body="${2#@}" ;; esac; shift; done' \
        'printf "%s %s %s\n" "${method}" "${url}" "$( [[ -n "${body}" ]] && cat "${body}" )" >> "${TMPDIR}/cloudflare.log"' \
        'if [[ "${method}" == GET && -f "${TMPDIR}/cloudflare.existing" ]]; then printf "{\"success\":true,\"result\":[%s]}" "$(cat "${TMPDIR}/cloudflare.existing")" > "${out}"' \
        'else printf "{\"success\":true,\"result\":[]}" > "${out}"; fi' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    zone="$(printf 'a%.0s' {1..32})"
    record="$(printf 'b%.0s' {1..32})"
    cfg-set DNS_TOKEN 'cf-sentinel-token'
    cfg-set DNS_ZONE "${zone}"

    cloudflare-upsert api.shop.test 203.0.113.7 false
    output="$(fs-read "${log}")"
    expect-contains "${output}" "GET https://api.cloudflare.com/client/v4/zones/${zone}/dns_records?name=api.shop.test&type=A"
    expect-contains "${output}" "POST https://api.cloudflare.com/client/v4/zones/${zone}/dns_records"
    expect-contains "${output}" '{"type":"A","name":"api.shop.test","content":"203.0.113.7","ttl":300,"proxied":false}'
    expect-contains "$(fs-read "${TMPDIR}/cloudflare.config")" 'header = "Authorization: Bearer cf-sentinel-token"'
    expect-absent "${output}" cf-sentinel-token

    : > "${log}"
    printf '{"id":"%s","content":"2001:db8::1","proxied":true}' "${record}" > "${TMPDIR}/cloudflare.existing"
    cloudflare-upsert api.shop.test 2001:db8::7 true
    output="$(fs-read "${log}")"
    expect-contains "${output}" "PUT https://api.cloudflare.com/client/v4/zones/${zone}/dns_records/${record}"
    expect-contains "${output}" '"type":"AAAA"'
    expect-contains "${output}" '"ttl":1,"proxied":true'

    : > "${log}"
    printf '{"id":"%s","content":"203.0.113.7","proxied":false}' "${record}" > "${TMPDIR}/cloudflare.existing"
    cloudflare-upsert api.shop.test 203.0.113.7 false
    expect-equal "$(grep -c '^GET ' "${log}")" 1 'a current record is read once'
    expect-equal "$(grep -c '^PUT \|^POST ' "${log}")" 0 'a current record is not rewritten'

    printf '{"id":"not-an-id","content":"198.51.100.1","proxied":false}' > "${TMPDIR}/cloudflare.existing"
    expect-error 'Unexpected Cloudflare record for api.shop.test' cloudflare-upsert api.shop.test 203.0.113.7 false
    expect-error 'Invalid DNS address' cloudflare-upsert api.shop.test 'bad;address' false
    cfg-set DNS_ZONE short
    expect-error 'DNS_ZONE must be a Cloudflare zone identifier' cloudflare-upsert api.shop.test 203.0.113.7 false

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
    expect-contains "${text}" $'--network\nshop-apps\n--network-alias\nacme'
    expect-contains "${text}" '/acme/live/site/fullchain.pem /acme/live/site/privkey.pem > /tls/site.pem.new'

    : > "${log}"
    cfg-set TLS_CHALLENGE dns
    cfg-set DNS_PROVIDER cloudflare
    cfg-set DNS_TOKEN cf_dns_token-01
    tls-issue api.shop.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'--dns-cloudflare\n--dns-cloudflare-credentials\n/run/cloudflare.ini'
    expect-equal "$(fs-read "${TMPDIR}/certbot.ini")" 'dns_cloudflare_api_token = cf_dns_token-01'
    expect-fail test -e "${CONFIG[STATE_ROOT]}/cloudflare.ini"
    expect-absent "${text}" cf_dns_token-01

    cfg-set DNS_TOKEN 'bad token'
    expect-error 'DNS_TOKEN has an unexpected format' tls-issue api.shop.test
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
fixture-telegram () {

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'out="" body=""' 'cat > /dev/null' \
        'while (( $# > 0 )); do case "$1" in --output) out="$2" ;; --data-binary) body="${2#@}" ;; esac; shift; done' \
        'jq -r .text "${body}" >> "${TMPDIR}/telegram"' 'printf "{\"ok\":true}" > "${out}"' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set TELEGRAM_BOT_TOKEN '123456:fixture-sentinel-token-0123456789'
    cfg-set TELEGRAM_CHAT_ID 42

}
test-operations-verify () {

    local output=""

    fixture-release
    mkdir -p "${CONFIG[STATE_ROOT]}"
    cfg-set VERIFY_SECONDS 30
    cfg-set VERIFY_FAILURES 2
    cfg-set VERIFY_INTERVAL 1
    printf '%s\n' fail pass fail fail pass > "${TMPDIR}/checks"

    native-serving () {

        local outcome=""

        outcome="$(sed -n 1p "${TMPDIR}/checks")"
        sed -i.old 1d "${TMPDIR}/checks"
        [[ "${outcome}" == pass ]]

    }

    output="$(native-verify r1 2>&1)" && err "A release failing two consecutive checks passed verification"
    expect-contains "${output}" 'r1 failed 2 consecutive checks after the switch'
    expect-equal "$(fs-read "${TMPDIR}/checks")" pass 'verification stops at the threshold'

    cfg-set VERIFY_SECONDS 2
    printf '%s\n' pass pass pass pass > "${TMPDIR}/checks"
    native-verify r1 2>/dev/null

}
test-operations-revert () {

    local root="" output=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}"
    fixture-telegram

    native-rollback-locked () {

        [[ "$(cat "${TMPDIR}/rollback")" == ok ]]

    }

    output="$(native-revert r1 'failed verification' 2>&1)" && err "A revert without a previous release succeeded"
    expect-equal "$(state-read "${root}" phase)" degraded
    expect-equal "$(fs-read "${TMPDIR}/telegram")" '🔴 shop: r1 failed verification; no retained release to roll back to'

    : > "${TMPDIR}/telegram"
    state-write "${root}" previous r0
    printf 'ok' > "${TMPDIR}/rollback"
    native-revert r1 'failed verification' 2>/dev/null && err "A reverted release reported success"
    expect-equal "$(fs-read "${TMPDIR}/telegram")" '↩️ shop: r1 failed verification; rolled back to r0'

    : > "${TMPDIR}/telegram"
    printf 'broken' > "${TMPDIR}/rollback"
    native-revert r1 'failed verification' 2>/dev/null && err "A failed rollback reported success"
    expect-contains "$(fs-read "${TMPDIR}/telegram")" 'the rollback to r0 failed; inspect status'

}
test-operations-monitor () {

    local root="" output=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}/backups"
    printf 'dump' > "${root}/backups/latest.dump"
    state-write "${root}/backups" latest latest.dump
    fixture-telegram
    printf 'yes' > "${TMPDIR}/serving"

    native-current () {

        cfg-set RELEASE r1

    }
    native-serving () {

        [[ "$(cat "${TMPDIR}/serving")" == yes ]]

    }
    native-data-healthy () {

        return 0

    }

    native-monitor >/dev/null
    expect-fail test -e "${TMPDIR}/telegram"
    output="$(fs-read "${root}/metrics/platform.prom")"
    expect-contains "${output}" 'platform_healthy 1'
    expect-contains "${output}" 'platform_release_info{release="r1"} 1'
    expect-contains "${output}" 'platform_backup_timestamp_seconds '
    expect-absent "${output}" platform_certificate

    printf 'no' > "${TMPDIR}/serving"
    native-monitor >/dev/null 2>&1 && err "A degraded release passed the monitor"
    native-monitor >/dev/null 2>&1 && err "A degraded release passed the monitor"
    expect-equal "$(fs-read "${TMPDIR}/telegram")" '⚠️ shop: r1 is degraded: r1 is not serving on every replica and the public endpoint'
    expect-contains "$(fs-read "${root}/metrics/platform.prom")" 'platform_healthy 0'

    printf 'yes' > "${TMPDIR}/serving"
    native-monitor >/dev/null
    expect-equal "$(sed -n 2p "${TMPDIR}/telegram")" '✅ shop: r1 recovered'

    mkdir "${root}/lock"
    printf '%s\n' "$$" > "${root}/lock/owner"
    expect-contains "$(native-monitor 2>&1)" 'monitor skipped'

}
fixture-exec () {

    printf '%s\n' "$*" >> "${TMPDIR}/exec.log"

}
test-operations-extensions () {

    postgresql-extensions shop 'vector,pg_trgm' fixture-exec
    expect-contains "$(fs-read "${TMPDIR}/exec.log")" 'extension shop vector'
    expect-contains "$(fs-read "${TMPDIR}/exec.log")" 'extension shop pg_trgm'
    expect-contains "$(fs-read "${TMPDIR}/exec.log")" 'CREATE EXTENSION IF NOT EXISTS \"$2\"'

    : > "${TMPDIR}/exec.log"
    postgresql-extensions shop '' fixture-exec
    expect-equal "$(fs-read "${TMPDIR}/exec.log")" ''
    expect-error 'Invalid PostgreSQL extension: bad;drop' postgresql-extensions shop 'vector,bad;drop' fixture-exec

}
test-operations-rejected () {

    local root="" output=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}"
    state-write "${root}" current r1
    cfg-set RELEASE r2
    native-reject r2 'failed verification after the switch'

    expect-equal "$(native-rejected r2)" 'failed verification after the switch'
    expect-fail native-rejected r9
    expect-error 'Release r2 was rejected (failed verification after the switch); publish a new release or deploy --force' native-converge

    gitops-fetch () {

        cfg-set RELEASE r2

    }
    native-deploy () {

        printf deployed > "${TMPDIR}/deployed"

    }

    output="$(native-reconcile 2>&1)"
    expect-contains "${output}" 'Desired release r2 was rejected (failed verification after the switch); waiting for a new release'
    expect-fail test -e "${TMPDIR}/deployed"

    rm -f -- "${root}/rejected/r2"
    output="$(native-reconcile 2>&1)"
    expect-contains "${output}" 'The server API env files differ from the desired state of r2; waiting for server stage'
    expect-fail test -e "${TMPDIR}/deployed"

    cfg-set API_ENV_SHA256 "$(native-env-digest API)"
    cfg-set VERSION v1
    output="$(native-reconcile 2>&1)"
    expect-contains "${output}" 'The server settings differ from the desired state of r2; waiting for server stage'
    expect-fail test -e "${TMPDIR}/deployed"

    cfg-set VERSION ''
    cfg-set GITOPS_COMMIT "$(printf '%040d' 1)"
    native-reconcile
    expect-equal "$(fs-read "${TMPDIR}/deployed")" deployed
    rm -f -- "${TMPDIR}/deployed"

    native-release-match () {

        return 0

    }
    native-rollback-locked () {

        printf '%s' "${1}" > "${TMPDIR}/rollback"

    }
    native-observe () {

        return 0

    }

    state-write "${root}" previous r0
    cfg-set RELEASE r0
    native-converge >/dev/null 2>&1
    expect-equal "$(fs-read "${TMPDIR}/rollback")" 'superseded by r0'

}
test-operations-uninstall () {

    local root="" calls=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"

    mkdir -p "${TMPDIR}/bin" "${root}/monitor"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" >> "${TMPDIR}/docker.calls"' > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"
    PATH="${TMPDIR}/bin:${PATH}"

    : > "${root}/monitor/monitor.yaml"
    state-write "${root}" slot-blue r1
    state-write "${root}" slot-green r2

    native-uninstall-locked > /dev/null
    calls="$(fs-read "${TMPDIR}/docker.calls")"

    expect-contains "${calls}" '--project-name shop-edge -f' 'the edge goes down'
    expect-contains "${calls}" '--project-name shop-r1 -f' 'the blue release goes down'
    expect-contains "${calls}" '--project-name shop-r2 -f' 'the green release kept for rollback goes down too'
    expect-contains "${calls}" '--project-name shop-monitor -f' 'the monitoring goes down'
    expect-contains "${calls}" '--project-name shop-data -f' 'the data services go down'
    expect-equal "$(grep -c ' down' <<< "${calls}")" 5

}
test-operations-remote-job () {

    local output="" status=0

    mkdir -p "${TMPDIR}/bin" "${HOME}/app"
    cat > "${HOME}/app/infra" <<'INFRA'
#!/usr/bin/env bash
printf 'step %s\n' "$*"
/bin/sleep 2
printf 'warned\n' >&2
printf 'done\n'
exit 3
INFRA
    cat > "${TMPDIR}/bin/ssh" <<'SSH'
#!/usr/bin/env bash
mode="$(cat "${TMPDIR}/mode" 2>/dev/null)"
calls=$(( $(cat "${TMPDIR}/calls" 2>/dev/null || printf 0) + 1 ))
printf '%s' "${calls}" > "${TMPDIR}/calls"
remote="${!#}"
[[ "${mode}" != down ]] || exit 255
[[ "${mode}" != skip || "${remote}" != *" 'start' "* ]] || exit 255
if [[ "${mode}" == drop && "${calls}" == 1 ]]; then
    bash -c "${remote}" > /dev/null 2>&1 &
    /bin/sleep 1
    kill "$!"
    exit 255
fi
bash -c "${remote}"
SSH
    printf '%s\n' '#!/usr/bin/env bash' 'exec /bin/sleep 0.1' > "${TMPDIR}/bin/sleep"
    chmod 700 "${HOME}/app/infra" "${TMPDIR}/bin/ssh" "${TMPDIR}/bin/sleep"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set SSH_HOST 203.0.113.10
    cfg-set SSH_USER deploy
    cfg-set REMOTE_DIR app

    output="$(native-server-run first 2>&1)" || status=$?
    expect-equal "${status}" 3 "the remote command status is returned: ${output}"
    expect-contains "${output}" 'step first'
    expect-contains "${output}" warned
    expect-contains "${output}" 'done'
    expect-equal "$(fs-read "${TMPDIR}/calls")" 2 'a finished job costs one follow and one status query'
    expect-equal "$(fs-mode "${HOME}/app/.infra/jobs")" 700

    cli-parse restore one.dump --force
    status=0
    output="$(native-route restore one.dump 2>&1)" || status=$?
    expect-equal "${status}" 3 "a routed command returns the remote status: ${output}"
    expect-contains "${output}" 'Running restore on deploy@203.0.113.10'
    expect-contains "${output}" 'step restore one.dump --force' 'positional arguments and flags reach the server'
    cli-parse

    cfg-set SSH_HOST ''
    expect-contains "$(native-route plan)" 'stack' 'without SSH_HOST the command runs here'
    cfg-set SSH_HOST 203.0.113.10

    printf drop > "${TMPDIR}/mode"
    rm -f -- "${TMPDIR}/calls"
    status=0
    output="$(native-server-run second 2>&1)" || status=$?
    expect-equal "${status}" 3 "a dropped connection reattaches and keeps the job status: ${output}"
    expect-contains "${output}" 'Connection lost; following remote job'
    expect-contains "${output}" 'step second'
    expect-contains "${output}" 'done'

    printf skip > "${TMPDIR}/mode"
    expect-error 'did not start' native-server-run third

    printf down > "${TMPDIR}/mode"
    expect-error 'is unreachable; if it started it keeps running' native-server-run fourth

}
test-operations-backup-restore () {

    local root="" name="" output=""
    local -a dumps=()

    fixture-release
    config-derive
    fixture-telegram
    root="${CONFIG[BACKUP_ROOT]}"

    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" >> "${TMPDIR}/docker.args"' "printf dump-bytes" > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"

    name="$(native-backup-create)"
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" 'exec pg_dump -U "$POSTGRES_USER" -d "$DB_NAME" --format=custom'
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" shop-data
    name="${name##*/}"
    expect-equal "$(fs-read "${root}/${name}")" dump-bytes
    expect-equal "$(state-read "${root}" latest)" "${name}"
    expect-equal "$(fs-read "${TMPDIR}/telegram")" "💾 shop: database backup ${name} saved (1 KiB)"
    expect-contains "$(native-backup-list)" "${name}"
    expect-contains "$(native-backup-list)" '1 KiB latest'

    native-wait-data () {

        return 0

    }
    postgresql-create () {

        printf 'create %s\n' "${1}" >> "${TMPDIR}/sql"

    }
    postgresql-extensions () {

        printf 'extensions %s %s\n' "${1}" "${2}" >> "${TMPDIR}/sql"

    }
    postgresql-restore () {

        printf 'restore %s %s\n' "${1##*/}" "${2}" >> "${TMPDIR}/sql"
        [[ ! -f "${TMPDIR}/broken" ]]

    }
    postgresql-swap () {

        printf 'swap %s %s %s %s\n' "${1}" "${2%_*}" "${3%_*}" "${4}" >> "${TMPDIR}/sql"

    }
    postgresql-drop () {

        printf 'drop %s\n' "${1%_*}" >> "${TMPDIR}/sql"

    }

    : > "${TMPDIR}/telegram"
    output="$(native-restore-locked 2>&1)"
    expect-contains "$(fs-read "${TMPDIR}/sql")" "restore ${name} shop_restore_"
    expect-contains "$(fs-read "${TMPDIR}/sql")" 'extensions shop_restore_'
    expect-contains "$(fs-read "${TMPDIR}/sql")" 'swap shop shop_restore shop_before shopper'
    expect-contains "${output}" 'restore: changed=true'
    expect-contains "$(fs-read "${TMPDIR}/telegram")" "♻️ shop: the database was restored from ${name}; the previous data is kept as shop_before_"
    dumps=( "${root}"/*.dump )
    expect-equal "${#dumps[@]}" 2 'the live database is saved before the restore'

    : > "${TMPDIR}/sql"
    : > "${TMPDIR}/broken"
    expect-error 'the live database is unchanged' native-restore-locked "${name}"
    expect-contains "$(fs-read "${TMPDIR}/sql")" 'drop shop_restore'
    expect-absent "$(fs-read "${TMPDIR}/sql")" swap

    postgresql-tables () {

        printf '7\n'

    }

    rm -f -- "${TMPDIR}/broken"
    : > "${TMPDIR}/sql"
    output="$(native-backup-verify-locked "${name}")"
    expect-contains "${output}" "verified"
    expect-contains "${output}" 'tables'
    expect-contains "$(fs-read "${TMPDIR}/sql")" 'drop shop_verify'
    expect-absent "$(fs-read "${TMPDIR}/sql")" swap

    printf 'tampered' > "${root}/${name}"
    expect-error "Backup checksum mismatch: ${name}" native-restore-locked "${name}"
    expect-error 'Backup not found' native-restore-locked missing.dump
    expect-error 'Name a .dump file' native-restore-locked ../etc/passwd

}
test-operations-database-swap () {

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" >> "${TMPDIR}/swap.args"' 'cat >> "${TMPDIR}/swap.sql"' > "${TMPDIR}/bin/capture"
    chmod 700 "${TMPDIR}/bin/capture"
    PATH="${TMPDIR}/bin:${PATH}"

    postgresql-swap shop shop_restore_1 shop_before_1 shopper capture
    expect-contains "$(fs-read "${TMPDIR}/swap.sql")" 'ALTER DATABASE :"live" WITH ALLOW_CONNECTIONS false;'
    expect-contains "$(fs-read "${TMPDIR}/swap.sql")" "WHERE datname = :'live' AND pid <> pg_backend_pid();"
    expect-contains "$(fs-read "${TMPDIR}/swap.sql")" 'ALTER DATABASE :"source" RENAME TO :"target";'
    expect-contains "$(fs-read "${TMPDIR}/swap.sql")" 'ALTER DATABASE :"restored" RENAME TO :"live";'
    expect-contains "$(fs-read "${TMPDIR}/swap.sql")" 'REVOKE CONNECT ON DATABASE :"live" FROM PUBLIC;'
    expect-contains "$(fs-read "${TMPDIR}/swap.args")" $'-v\nsource=shop\n-v\ntarget=shop_before_1'
    expect-contains "$(fs-read "${TMPDIR}/swap.args")" $'-v\nowner=shopper'
    expect-error 'Invalid database name: shop;drop' postgresql-swap 'shop;drop' shop_restore_1 shop_before_1 shopper capture

    printf '%s\n' '#!/usr/bin/env bash' 'cat > /dev/null' \
        'if [[ "$*" == *--list* ]]; then printf "%s\n" "2; 3079 16386 EXTENSION - vector " "3634; 0 0 COMMENT - EXTENSION vector " "220; 1259 16714 TABLE public notes shopper"; exit 0; fi' \
        'printf "%s\n" "$@" > "${TMPDIR}/restore.args"' > "${TMPDIR}/bin/catalog"
    chmod 700 "${TMPDIR}/bin/catalog"
    printf 'dump' > "${TMPDIR}/backup.dump"
    postgresql-restore "${TMPDIR}/backup.dump" shop_restore_1 catalog
    expect-contains "$(fs-read "${TMPDIR}/restore.args")" '220; 1259 16714 TABLE public notes shopper'
    expect-absent "$(fs-read "${TMPDIR}/restore.args")" 'EXTENSION' 'the infrastructure creates extensions as the superuser'

}
test-operations-deploy-plan () {

    local root="" output=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}"
    state-write "${root}" current r0
    state-write "${root}" active-slot blue

    output="$(native-deploy-plan 2>&1)"
    expect-contains "${output}" 'deploy into the green slot through the readiness gates'
    expect-contains "${output}" "api=${CONFIG[API_IMAGE]}"
    expect-contains "${output}" 'deploy-plan: changed=false'

    state-write "${root}" previous r1
    expect-contains "$(native-deploy-plan 2>&1)" 'switch back to the retained r1 in seconds'

    state-write "${root}" previous ''
    state-write "${root}" current r1
    expect-contains "$(native-deploy-plan 2>&1)" 'no change: r1 is live'

    state-write "${root}" current r0
    native-reject r1 'failed at phase healthy'
    expect-error 'This deploy would be refused' native-deploy-plan
    expect-contains "$(native-deploy-plan 2>&1)" 'rejected (failed at phase healthy); --force ships it again'
    CLI_FLAGS[--force]=true
    expect-contains "$(native-deploy-plan 2>&1)" 'deploy-plan: changed=false'
    CLI_FLAGS[--force]=false

    state-write "${root}" pending r9
    expect-contains "$(native-deploy-plan 2>&1)" 'refused: r9 is pending'
    expect-fail test -e "${root}/releases/r1" 'a dry run renders nothing'

}
test-operations-doctor () {

    local root=""

    fixture-release
    config-derive
    root="${CONFIG[STATE_ROOT]}"

    MANIFEST[requires.runtime]='bash awk'
    expect-contains "$(native-doctor-runtime)" 'ok bash'
    MANIFEST[requires.runtime]='bash definitely-missing-tool'
    expect-equal "$(native-doctor-runtime)" 'fail missing: definitely-missing-tool'

    expect-equal "$(native-doctor-settings)" 'ok valid and complete for a deploy'
    cfg-set DB_PASSWORD short
    expect-contains "$(native-doctor-settings)" 'fail DB_PASSWORD needs at least 16 characters'

    expect-equal "$(native-doctor-env)" 'ok api'
    unset API_ENV_FILE
    expect-equal "$(native-doctor-env)" 'fail API env content missing: export API_ENV_FILE or stage .env.api'

    expect-contains "$(native-doctor-backup)" 'warn no backup recorded yet'
    mkdir -p "${root}/backups"
    printf dump > "${root}/backups/a.dump"
    state-write "${root}/backups" latest a.dump
    expect-contains "$(native-doctor-backup)" 'ok a.dump, 0h old'
    touch -t 200001010000 "${root}/backups/a.dump"
    expect-contains "$(native-doctor-backup)" 'older than BACKUP_MAX_AGE'

    expect-equal "$(native-doctor-release)" 'warn no release deployed yet'
    mkdir -p "${root}"
    state-write "${root}" current r1
    state-write "${root}" phase complete
    expect-equal "$(native-doctor-release)" 'ok r1 (complete)'
    state-write "${root}" phase recovery-required
    expect-contains "$(native-doctor-release)" 'fail recovery required'

    expect-contains "$(native-doctor-channels)" 'warn none configured'
    cfg-set SLACK_WEBHOOK_URL 'https://hooks.slack.com/services/T0/B0/x'
    expect-equal "$(native-doctor-channels)" 'ok slack'
    expect-contains "$(native-doctor-timers)" 'warn checked only from the staged release bundle'
    expect-contains "$(native-doctor-edge)" 'warn not applied yet'

}
