test-operations-topology () {

    fixture-release
    expect-equal "$(native-parts)" core
    expect-equal "$(native-server-part)" core
    expect-equal "$(native-routes)" 'core|api.shop.test|8000|/|/health|leastconn|200||slot'

    fixture-sites
    expect-equal "$(native-parts | paste -sd ' ' -)" 'core shop desk'
    expect-equal "$(native-replicas shop)" 3
    expect-equal "$(native-replicas desk)" 1
    expect-equal "$(native-replicas core)" 2
    expect-equal "$(native-service-image desk)" "example/desk@$(fixture-digest 3)"
    expect-equal "$(native-domains | paste -sd ' ' -)" 'api.shop.test shop.test www.shop.test'
    expect-contains "$(native-routes)" 'shop|shop.test www.shop.test|3000|/|/|roundrobin|200-399||slot'
    expect-contains "$(native-routes)" 'desk|shop.test|3000|/desk|/desk/health|roundrobin|200|600/1m|slot'
    expect-absent "$(native-edge-routes)" grafana

    cfg-set GRAFANA_DOMAIN 'grafana.shop.test,metrics.shop.test'
    expect-equal "$(native-domains | paste -sd ' ' -)" 'api.shop.test shop.test www.shop.test grafana.shop.test metrics.shop.test'
    expect-contains "$(native-edge-routes)" 'grafana|grafana.shop.test metrics.shop.test|3000|/|/api/health|roundrobin|200||static'
    expect-absent "$(native-routes)" grafana 'candidate probes never wait for Grafana'
    expect-equal "$(native-certificate-groups)" 'shop.test api.shop.test grafana.shop.test metrics.shop.test shop.test www.shop.test' 'one certificate per registrable domain'

    mkdir -p "${CONFIG[STATE_ROOT]}/releases/r1"
    touch "${CONFIG[STATE_ROOT]}/releases/r1/part-shop.yaml"
    state-write "${CONFIG[STATE_ROOT]}" slot-green r1
    expect-contains "$(native-interpolation r1)" DEPLOY_SLOT=green
    expect-contains "$(native-interpolation r1)" "RELEASE_ROOT=${CONFIG[STATE_ROOT]}/releases/r1"
    expect-contains "$(native-interpolation r1)" SHOP_REPLICAS=3
    expect-absent "$(native-interpolation r1)" CORE_REPLICAS 'only the parts a release holds are interpolated'
    expect-contains "$(native-interpolation r9)" DEPLOY_SLOT=blue

}
test-operations-suffixes () {

    expect-equal "$(tls-groups www.example.com.eg api.example.com.eg example.com.eg api.example.com.eg)" 'example.com.eg api.example.com.eg example.com.eg www.example.com.eg'
    expect-equal "$(tls-groups a.b.example.co.uk shop.test)" $'example.co.uk a.b.example.co.uk\nshop.test shop.test'
    expect-equal "$(tls-groups x.www.ck)" 'www.ck x.www.ck' 'an exception rule ends the public suffix'
    expect-equal "$(tls-groups shop.other.ck)" 'shop.other.ck shop.other.ck' 'a wildcard rule spans one more label'
    expect-equal "$(tls-groups api.ragx.comstrx.com ragx.comstrx.com)" 'comstrx.com api.ragx.comstrx.com ragx.comstrx.com'
    expect-error 'com.eg is a public suffix; route a name under it' tls-groups com.eg
    expect-error 'Invalid certificate host: bad_host' tls-groups bad_host

}
test-operations-backup-retention () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" name=""

    expect-equal "${root}" "${CONFIG[STATE_ROOT]}/backups/sql"
    expect-equal "${CONFIG[BACKUP_WAL_ROOT]}" "${CONFIG[STATE_ROOT]}/backups/wal"
    cfg-set BACKUP_DIR /srv/backups
    config-derive
    expect-equal "${CONFIG[BACKUP_ROOT]}" /srv/backups
    expect-equal "${CONFIG[BACKUP_SQL_ROOT]}" /srv/backups/sql
    expect-equal "${CONFIG[BACKUP_WAL_ROOT]}" /srv/backups/wal
    cfg-set BACKUP_DIR ''
    config-derive

    mkdir -p "${root}"
    cfg-set BACKUP_RETENTION 86400

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
    expect-error 'Usage: infra timer install' native-timer-install shell 60
    expect-error 'Usage: infra restore [BACKUP] --force' native-restore one two
    expect-error 'Restore replaces the live database; rerun with --force' native-restore
    expect-error 'stop takes the edge and the current release offline' native-stop
    expect-error 'Usage: infra timer remove monitor|backup|archive|renew|reconcile' native-timer-remove shell
    expect-error 'Unknown tls action: drop (expected present, issue, renew or import)' native-tls drop

    cfg-set PROJECT shop
    cfg-set REGISTRY_NAMESPACE org
    expect-equal "$(native-registry-reference core 1.0.0)" ghcr.io/org/shop-core:1.0.0
    cfg-set REGISTRY_DRIVER dockerhub
    expect-equal "$(native-registry-host)" docker.io
    expect-error 'Image outside docker.io/org' native-registry-push ghcr.io/org/shop-core:1

}
test-operations-images () {

    local digest=""

    fixture-release
    fixture-sites
    cfg-set REGISTRY_NAMESPACE org

    expect-error 'Unknown part: other (expected core shop desk)' native-image-build other example/x:1
    expect-error 'Image builds need the monorepo checkout' native-image-build core example/core:1
    expect-equal "$(native-image-env core)" ''
    expect-equal "$(native-image-env desk)" 'SPEC=desk ORIGIN=http://api.shop.test SELF=http://shop.test/desk'
    expect-equal "$(native-image-reference core v1.0.0)" ghcr.io/org/shop-core:v1.0.0 'a part without build variables keeps the release tag'

    digest="$(printf '%s' 'SPEC=shop ORIGIN=http://api.shop.test' | fs-hash - | cut -c1-8)"
    expect-equal "$(native-image-reference shop v1.0.0)" "ghcr.io/org/shop-shop:v1.0.0-${digest}" 'baked addresses name their own image'
    cfg-set CORE_DOMAIN api.other.test
    config-derive
    [[ "$(native-image-reference shop v1.0.0)" != *"-${digest}" ]] || err "A changed address kept the image reference"

    expect-equal "$(native-image-inputs desk | paste -sd ' ' -)" 'PROJECT=shop TLS_ENABLED=false HTTP_PORT=80 HTTPS_PORT=443 CORE_DOMAIN=api.other.test DESK_DOMAIN=shop.test'
    expect-equal "$(native-image-inputs core | paste -sd ' ' -)" 'PROJECT=shop TLS_ENABLED=false HTTP_PORT=80 HTTPS_PORT=443'
    expect-error 'Usage: infra image resolve TAG' native-image-resolve

}
test-operations-certbot () {

    local log="${TMPDIR}/certbot.log" text=""

    docker-oneshot () {

        printf '%s\n' "$@" >> "${TMPDIR}/certbot.log"

    }

    fixture-release
    mkdir -p "${CONFIG[STATE_ROOT]}"
    cfg-set TLS_EMAIL ops@shop.test

    tls-issue shop.test api.shop.test shop.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'certonly\n--non-interactive\n--agree-tos\n--keep-until-expiring\n--cert-name\nshop.test'
    expect-contains "${text}" $'-d\napi.shop.test\n-d\nshop.test'
    expect-contains "${text}" $'--standalone\n--http-01-port\n8080'
    expect-contains "${text}" $'--network\nshop-apps\n--network-alias\nacme'
    expect-contains "${text}" 'cat "/acme/live/${name}/fullchain.pem" "/acme/live/${name}/privkey.pem" > "/tls/.staging/${name}.pem"'
    expect-contains "${text}" $'done\nsh\nshop.test' 'the lineage named after its registrable domain is promoted'

    : > "${log}"
    tls-renew shop.test other.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'renew\n--non-interactive'
    expect-contains "${text}" $'\nsh\nshop.test\nother.test'

    : > "${log}"
    cfg-set TLS_STAGING true
    tls-issue --force shop.test api.shop.test
    text="$(fs-read "${log}")"
    expect-contains "${text}" $'--staging\n--force-renewal' 'staging and a forced reissue reach certbot'
    cfg-set TLS_STAGING false

    expect-error 'Invalid certificate host' tls-issue shop.test 'bad host'
    expect-error 'Invalid certificate name' tls-issue '../etc' api.shop.test

}
test-operations-certificates () {

    local root="" text=""

    fixture-release
    fixture-sites
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}"
    cfg-set TLS_ENABLED true

    tls-issue () {

        printf '%s\n' "$*" >> "${TMPDIR}/issued"
        [[ ! -f "${TMPDIR}/fail" || "$(< "${TMPDIR}/fail")" != "${1}" ]]

    }
    tls-prune () {

        printf '%s\n' "$*" > "${TMPDIR}/kept"

    }

    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/issued")" 'shop.test api.shop.test shop.test www.shop.test'
    expect-equal "$(state-read "${root}" certificates)" 'shop.test api.shop.test shop.test www.shop.test'
    expect-equal "${CONFIG[CERTIFICATES_CHANGED]}" true

    rm -f "${TMPDIR}/issued"
    native-certificate-converge
    expect-fail test -e "${TMPDIR}/issued"
    expect-equal "${CONFIG[CERTIFICATES_CHANGED]}" false

    cfg-set TLS_STAGING true
    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/issued")" '--force shop.test api.shop.test shop.test www.shop.test' 'switching to staging reissues the lineage'
    expect-equal "$(state-read "${root}" certificates)" 'shop.test api.shop.test shop.test www.shop.test @staging'
    rm -f "${TMPDIR}/issued"
    cfg-set TLS_STAGING false
    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/issued")" '--force shop.test api.shop.test shop.test www.shop.test' 'leaving staging reissues a trusted certificate'
    expect-equal "$(state-read "${root}" certificates)" 'shop.test api.shop.test shop.test www.shop.test'
    rm -f "${TMPDIR}/issued"

    cfg-set CERTIFICATE_BATCH 1
    cfg-set GRAFANA_DOMAIN 'metrics.example.com.eg grafana.other.example'
    text="$(native-certificate-converge 2>&1)"
    expect-equal "$(fs-read "${TMPDIR}/issued")" 'example.com.eg metrics.example.com.eg' 'one run issues at most CERTIFICATE_BATCH certificates'
    expect-contains "${text}" '1 more certificates wait for the next run (CERTIFICATE_BATCH=1)'
    rm -f "${TMPDIR}/issued"
    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/issued")" 'other.example grafana.other.example' 'the next run takes the rest'

    cfg-set GRAFANA_DOMAIN 'metrics.example.com.eg grafana.other.example api.third.example'
    printf 'third.example' > "${TMPDIR}/fail"
    rm -f "${TMPDIR}/issued"
    expect-contains "$(native-certificate-converge 2>&1)" 'The certificate of third.example failed; retrying after 3600s'
    expect-equal "$(state-read "${root}" certificates | grep -c third.example)" 0
    rm -f "${TMPDIR}/issued" "${TMPDIR}/fail"
    native-certificate-converge
    expect-fail test -e "${TMPDIR}/issued" 'a failed domain waits CERTIFICATE_RETRY'
    state-write "${root}/certificate-failures" third-example 1
    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/issued")" 'third.example api.third.example' 'after CERTIFICATE_RETRY it is issued again'

    native-certificate-record example.com.eg 'example.com.eg imported'
    cfg-set GRAFANA_DOMAIN 'metrics.example.com.eg grafana.example.com.eg'
    rm -f "${TMPDIR}/issued"
    native-certificate-converge
    expect-fail test -e "${TMPDIR}/issued" 'an imported certificate is never replaced by an issued one'
    expect-fail test -e "${TMPDIR}/kept" 'an unused certificate outlives its domains for CERTIFICATE_RETENTION'
    test -f "${root}/certificate-unused/other-example" || err "An unused certificate must be marked"

    cfg-set GRAFANA_DOMAIN 'grafana.other.example'
    native-certificate-converge
    expect-fail test -e "${root}/certificate-unused/other-example" 'a returning domain keeps its certificate'

    cfg-set GRAFANA_DOMAIN ''
    cfg-set CERTIFICATE_RETENTION 0
    native-certificate-converge
    expect-equal "$(fs-read "${TMPDIR}/kept")" shop.test 'certificates unused past CERTIFICATE_RETENTION are pruned'
    expect-equal "$(state-read "${root}" certificates)" 'shop.test api.shop.test shop.test www.shop.test'
    expect-equal "${CONFIG[CERTIFICATES_CHANGED]}" true

    mkdir -p "${root}/certificates.lock"
    printf '%s\n' "$$" > "${root}/certificates.lock/owner"
    cfg-set GRAFANA_DOMAIN 'grafana.fourth.example'
    rm -f "${TMPDIR}/issued"
    expect-contains "$(native-certificate-run 2>&1)" 'Another run is issuing certificates'
    expect-fail test -e "${TMPDIR}/issued" 'a busy certificate lock is never waited on'
    printf '999999\n' > "${root}/certificates.lock/owner"
    native-certificate-run
    expect-equal "$(fs-read "${TMPDIR}/issued")" 'fourth.example grafana.fourth.example' 'a lock left by a dead run is recovered'
    expect-fail test -e "${root}/certificates.lock"

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
    cfg-set BACKUP_WAL false
    root="${CONFIG[STATE_ROOT]}"
    mkdir -p "${root}/backups/sql"
    printf 'dump' > "${root}/backups/sql/latest.dump"
    state-write "${root}/backups/sql" latest latest.dump
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
    expect-contains "${output}" 'The server core env files differ from the desired state of r2; waiting for server stage'
    expect-fail test -e "${TMPDIR}/deployed"

    cfg-set CORE_ENV_SHA256 "$(native-env-digest core)"
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
    mkdir -p "${root}/releases/r1" "${root}/releases/r2"
    : > "${root}/releases/r1/part-core.yaml"
    : > "${root}/releases/r2/part-core.yaml"
    state-write "${root}" slot-blue r1
    state-write "${root}" slot-green r2

    native-uninstall-locked > /dev/null
    calls="$(fs-read "${TMPDIR}/docker.calls")"

    expect-contains "${calls}" '--project-name shop-edge -f' 'the edge goes down'
    expect-contains "${calls}" '--project-name shop-r1 -f' 'the blue release goes down'
    expect-contains "${calls}" '--project-name shop-r2 -f' 'the green release kept for rollback goes down too'
    expect-contains "${calls}" '--project-name shop-monitor -f' 'the monitoring goes down'
    expect-contains "${calls}" '--project-name shop-data -f' 'the data services go down'
    expect-contains "${calls}" '--project-name shop-models down --remove-orphans' 'the models go down by project name, files or not'
    expect-equal "$(grep -c ' down' <<< "${calls}")" 6

}
test-operations-remote-job () {

    local output="" status=0

    mkdir -p "${TMPDIR}/bin" "${HOME}/app"
    cat > "${HOME}/app/infra" <<'INFRA'
#!/usr/bin/env bash
printf 'step %s\n' "$*"
printf 'env WORKER_REPLICAS=%s SSH_HOST=%s\n' "${WORKER_REPLICAS:-unset}" "${SSH_HOST:-unset}"
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
[[ "${mode}" != flaky || "${calls}" != 1 ]] || exit 255
if [[ "${mode}" == cut && "${remote}" =~ \'start\'\ \'app\'\ \'\.infra/jobs\'\ \'([^\']+)\' ]]; then
    mkdir -p "${HOME}/app/.infra/jobs"
    : > "${HOME}/app/.infra/jobs/${BASH_REMATCH[1]}.claim"
    exit 255
fi
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

    cli-parse -e WORKER_REPLICAS=4 -e SSH_HOST=198.51.100.9 scale
    output="$(native-route scale 2>&1)" || true
    expect-contains "${output}" 'env WORKER_REPLICAS=4 SSH_HOST=unset' '-e overrides travel with the command, never the SSH target'
    cli-parse

    rm -f -- "${TMPDIR}/calls"
    expect-error 'Unknown backup action: lst; did you mean list?' native-route backup lst
    expect-fail test -e "${TMPDIR}/calls"

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

    printf flaky > "${TMPDIR}/mode"
    rm -f -- "${TMPDIR}/calls"
    status=0
    output="$(native-server-run flaky 2>&1)" || status=$?
    expect-equal "${status}" 3 "a start lost before the job existed runs it once again: ${output}"
    expect-contains "${output}" 'Connection lost before remote job'
    expect-equal "$(grep -c 'step flaky' <<< "${output}")" 1 'the job runs exactly once'

    printf cut > "${TMPDIR}/mode"
    rm -f -- "${TMPDIR}/calls"
    output="$(native-server-run cut 2>&1)" && err "A start cut off after its claim was accepted"
    expect-contains "${output}" 'was claimed but its start was cut off, so it may be running'
    expect-absent "${output}" 'starting it again' 'a claimed job is never started twice'
    expect-equal "$(fs-read "${TMPDIR}/calls")" 2 'one start and one status query'

    printf skip > "${TMPDIR}/mode"
    rm -f -- "${TMPDIR}/calls"
    expect-error 'did not start' native-server-run third
    expect-equal "$(fs-read "${TMPDIR}/calls")" 6 'three starts and three status queries, then it gives up'

    printf down > "${TMPDIR}/mode"
    expect-error 'is unreachable; if it started it keeps running' native-server-run fourth

}
test-operations-backup-restore () {

    local root="" name="" output=""
    local -a dumps=()

    fixture-release
    cfg-set BACKUP_WAL false
    config-derive
    fixture-telegram
    root="${CONFIG[BACKUP_SQL_ROOT]}"

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
    expect-contains "${output}" "core=${CONFIG[CORE_IMAGE]}"
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

    expect-equal "$(native-doctor-env)" 'ok core'
    unset CORE_ENV_FILE
    expect-equal "$(native-doctor-env)" 'fail core env content missing: export CORE_ENV_FILE or stage .env.core'

    expect-contains "$(native-doctor-backup)" 'warn no backup recorded yet'
    mkdir -p "${root}/backups/sql"
    printf dump > "${root}/backups/sql/a.dump"
    state-write "${root}/backups/sql" latest a.dump
    expect-contains "$(native-doctor-backup)" 'ok a.dump, 0h old'
    touch -t 200001010000 "${root}/backups/sql/a.dump"
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

    mkdir -p "${root}/edge"
    printf 'services: {}\n' > "${root}/edge/edge.yaml"
    native-edge-alive () { :; }
    native-edge-sockets () { :; }
    docker-rootless () { :; }
    expect-contains "$(native-doctor-edge)" 'warn listening on 127.0.0.1:443 through rootless Docker' 'rootless port forwarding hides client addresses'
    docker-rootless () { return 1; }
    expect-contains "$(native-doctor-edge)" 'ok listening on 127.0.0.1:443'
    cfg-set EDGE_SOCKETS /srv/edge
    expect-contains "$(native-doctor-edge)" 'ok relayed through /srv/edge/http.sock' 'a relay keeps client addresses even on rootless Docker'

    expect-equal "$(native-doctor-models)" 'ok none served'
    docker-ready () { :; }
    docker () { [[ "${1}" != ps ]] || printf '%s\n' shop-data shop-r1 shop-models shop-r0 '' other-r9 shop-monitor; }
    state-write "${root}" slot-blue r1
    expect-equal "$(native-doctor-orphans)" 'warn containers outside the known projects: shop-r0; remove each with docker compose -p NAME down'
    state-write "${root}" slot-green r0
    expect-contains "$(native-doctor-orphans)" 'ok every container belongs to a slot'

}
test-operations-backup-wal () {

    local calls="${TMPDIR}/data.calls" archive="${TMPDIR}/wal"

    fixture-release
    cfg-set BACKUP_RETENTION 259200
    cfg-set BACKUP_URI s3://bucket/prefix
    cfg-set BACKUP_KEY key-id
    cfg-set BACKUP_SECRET wal-sentinel-secret
    mkdir -p "${TMPDIR}/bin" "${archive}"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" > "${TMPDIR}/docker.args"' > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"
    PATH="${TMPDIR}/bin:${PATH}"

    native-compose-data () {

        printf '%s\n' "$*" >> "${TMPDIR}/data.calls"

        case "$*" in
            *backup_manifest*) printf '1 1 A2000028\n' ;;
            *wal_segment_size*) printf '16MB\n' ;;
            *'ps -q postgres'*) printf 'pg-container\n' ;;
        esac

    }
    docker-inspect () {

        printf '%s\n' "${TMPDIR}/wal"

    }

    cfg-set BACKUP_WAL false
    native-backup-base
    expect-contains "$(fs-read "${calls}")" 'rm -f /wal/enabled' 'switching WAL off removes the flag'
    expect-absent "$(fs-read "${calls}")" pg_basebackup 'no base backup while WAL is off'

    : > "${calls}"
    cfg-set BACKUP_WAL true
    native-backup-base

    expect-contains "$(fs-read "${calls}")" ': > /wal/enabled'
    expect-contains "$(fs-read "${calls}")" 'pg_basebackup -U "$POSTGRES_USER" -D "/wal/base/$1.part" --format=tar --gzip --wal-method=none --checkpoint=fast'
    expect-contains "$(fs-read "${calls}")" ' 0000000100000001000000A2 ' 'the start segment comes from the manifest LSN and the segment size'
    expect-contains "$(fs-read "${calls}")" 'pg_archivecleanup /wal/archive "$segment"'
    expect-contains "$(fs-read "${calls}")" ' prune 4320' 'base backups older than BACKUP_RETENTION go, in minutes'
    expect-contains "$(fs-read "${calls}")" '-mmin +"$1"'
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" $'--user\n999:999'
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" "type=bind,source=${archive},target=/sync,readonly"
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" $'sync\n--only-show-errors\n--exclude\nenabled'
    expect-contains "$(fs-read "${TMPDIR}/docker.args")" $'/sync\ns3://bucket/prefix/wal'
    expect-absent "$(fs-read "${TMPDIR}/docker.args")" --delete 'an offsite copy is never pruned by a sync'
    expect-absent "$(fs-read "${TMPDIR}/docker.args")" wal-sentinel-secret

    expect-equal "$(postgresql-bytes 16MB)" 16777216
    expect-equal "$(postgresql-bytes 1GB)" 1073741824
    expect-error 'Unexpected wal_segment_size' postgresql-bytes 16kB
    expect-error 'Invalid base backup name' postgresql-base 'x;y' native-compose-data exec -T postgres

}
test-operations-restore-point () {

    local output=""

    fixture-release
    fixture-telegram
    state-write "${CONFIG[STATE_ROOT]}" current r1

    postgresql-bases () {

        printf '%s\n' '20261021T000000Z 000000010000000000000009 20261021T000150Z' '20261020T000000Z 000000010000000000000003 20261020T000210Z'

    }
    native-wait-data () { :; }
    native-current () { cfg-set RELEASE r1; }
    native-archive-source () { out /srv/wal; }
    native-backup-dump () { out /srv/backups/sql/saved.dump; }
    native-background-stop () { printf 'background stop %s\n' "$1" >> "${TMPDIR}/flow"; }
    native-background-start () { printf 'background start %s\n' "$1" >> "${TMPDIR}/flow"; }
    native-compose-data () { printf 'data %s\n' "$*" >> "${TMPDIR}/flow"; }
    postgresql-unpack () { printf 'unpack %s %s %s %s\n' "$2" "$4" "$5" "$3" >> "${TMPDIR}/flow"; }
    postgresql-repack () { printf 'repack %s\n' "$2" >> "${TMPDIR}/flow"; }
    postgresql-settle () { printf 'settle\n' >> "${TMPDIR}/flow"; }
    native-replay () { [[ ! -f "${TMPDIR}/stuck" ]]; }
    native-probe-public () { :; }
    native-backup-base () { printf 'base\n' >> "${TMPDIR}/flow"; }
    native-probe-public || err "The public probe stub must answer"

    output="$(native-restore-point 20261021T120000Z 2>&1)"
    expect-contains "$(fs-read "${TMPDIR}/flow")" 'unpack shop-postgres 20261021T000000Z 2026-10-21 12:00:00+00 /srv/wal' 'the newest base finished before the moment is used'
    expect-contains "$(fs-read "${TMPDIR}/flow")" $'background stop r1\ndata stop postgres'
    expect-contains "$(fs-read "${TMPDIR}/flow")" $'data start postgres\nsettle\ndata restart postgres' 'a restart drops the recovery target from memory'
    expect-contains "$(fs-read "${TMPDIR}/flow")" $'background start r1\nbase' 'a new base anchors the new timeline'
    expect-contains "${output}" 'restore: changed=true'
    expect-contains "$(fs-read "${TMPDIR}/telegram")" 'the database was restored to 2026-10-21 12:00:00+00 from base 20261021T000000Z'

    : > "${TMPDIR}/flow"
    native-restore-point 20261021T000100Z > /dev/null 2>&1
    expect-contains "$(fs-read "${TMPDIR}/flow")" 'unpack shop-postgres 20261020T000000Z' 'a base still running at the moment is skipped'

    expect-error 'No base backup finished before 2026-10-19 12:00:00+00' native-restore-point 20261019T120000Z

    : > "${TMPDIR}/flow"
    : > "${TMPDIR}/stuck"
    expect-error 'the previous data is back' native-restore-point 20261021T120000Z
    expect-contains "$(fs-read "${TMPDIR}/flow")" 'repack shop-postgres'
    expect-absent "$(fs-read "${TMPDIR}/flow")" settle
    expect-contains "$(fs-read "${TMPDIR}/flow")" 'background start r1' 'the worker and scheduler come back after a failed restore'

    cfg-set BACKUP_WAL false
    expect-error 'needs BACKUP_WAL=true' native-restore-point 20261021T120000Z

    expect-equal "$(native-moment 2026-10-20T22:59:30Z)" 20261020T225930Z
    expect-equal "$(native-moment '2026-10-20 22:59:30')" 20261020T225930Z
    expect-error 'Name the moment in UTC' native-moment 21/10/2026
    expect-error 'is in the future' native-moment 2999-01-01T00:00:00Z

    cli-parse restore one.dump --at 2026-10-21T22:59:30Z --force
    expect-error 'a BACKUP or --at TIME, not both' native-restore one.dump
    cli-parse restore --at 2026-10-21T22:59:30Z
    expect-error 'rerun with --force' native-restore
    cli-parse

}
test-operations-data-change () {

    local first="" second="" root="" text=""

    fixture-release
    root="${CONFIG[STATE_ROOT]}/data"
    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" >> "${TMPDIR}/docker.args"' \
        '[[ "$*" != *psql* && "$*" != *import_definitions* ]] || cat >> "${TMPDIR}/docker.stdin"' \
        'printf "%s\n" "${NEW_DB_PASSWORD:-}" >> "${TMPDIR}/docker.env"' > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"
    PATH="${TMPDIR}/bin:${PATH}"

    native-compose-data () {

        printf '%s\n' "$*" >> "${TMPDIR}/compose.calls"

        case "$*" in
            'ps -q postgres') printf 'pg-container\n' ;;
            'ps -q rabbitmq') printf 'mq-container\n' ;;
            *PG_VERSION*)     printf '18\n' ;;
        esac

    }
    native-wait-data () { :; }
    native-backup-dump () { touch "${TMPDIR}/dumped"; }
    native-announce () { printf '%s %s\n' "${1}" "${2}" >> "${TMPDIR}/announced"; }
    postgresql-major () { cat "${TMPDIR}/major"; }
    rabbitmq-applied () { :; }
    native-wait-data
    native-backup-dump
    native-announce notice check
    rabbitmq-applied courier hash
    rm -f -- "${TMPDIR}/dumped" "${TMPDIR}/announced"
    printf '18\n' > "${TMPDIR}/major"

    first="$(native-render)"
    native-data "${first}"
    test -f "${root}/fingerprint" || err "The first deploy must adopt the data settings"
    expect-contains "$(fs-read "${root}/identity")" 'DB_USER=shopper'
    expect-absent "$(fs-read "${root}/identity")" sentinel 'only password hashes are recorded'
    expect-fail test -e "${TMPDIR}/dumped" 'adopting cuts nothing'

    native-data "${first}"
    expect-fail test -e "${TMPDIR}/dumped" 'unchanged settings cut nothing'

    cfg-set RELEASE r2
    cfg-set DB_PASSWORD 'rotated-sentinel-password-0123'
    cfg-set RABBIT_USER courier
    config-derive
    second="$(native-render)"
    native-data "${second}"

    test -e "${TMPDIR}/dumped" || err "A data change must save a dump first"
    text="$(fs-read "${TMPDIR}/docker.args")"
    expect-contains "${text}" 'exec -i -e NEW_DB_USER -e NEW_DB_NAME -e NEW_DB_PASSWORD -e NEW_DB_ADMIN_PASSWORD pg-container psql'
    expect-contains "${text}" '-v old_user=shopper -v old_database=shop'
    expect-contains "${text}" 'mq-container rabbitmqctl -q delete_user rabbit' 'a renamed user replaces the previous one'
    expect-absent "${text}" rotated-sentinel 'no password reaches argv'
    expect-contains "$(fs-read "${TMPDIR}/docker.env")" 'rotated-sentinel-password-0123' 'the password reaches psql through its environment'
    text="$(fs-read "${TMPDIR}/docker.stdin")"
    expect-contains "${text}" "SELECT format('ALTER ROLE %I NOLOGIN', :'old_user') \\gexec"
    expect-contains "${text}" 'pg_terminate_backend'
    expect-contains "${text}" "SET log_min_error_statement = 'panic';"
    expect-contains "${text}" '"name":"courier"'
    expect-absent "${text}" rotated-sentinel
    expect-absent "${text}" 'rabbit@:/ sentinel-01' 'RabbitMQ receives a hash, never the password'
    expect-contains "$(fs-read "${TMPDIR}/compose.calls")" $'\nup -d postgres rabbitmq redis\n' 'changed services are recreated'
    expect-contains "$(fs-read "${root}/identity")" 'RABBIT_USER=courier'
    expect-contains "$(fs-read "${TMPDIR}/announced")" 'data.changed data service settings changed (identity of postgres rabbitmq)'

    rm -f -- "${TMPDIR}/dumped"
    printf '19\n' > "${TMPDIR}/major"
    cfg-set RELEASE r3
    cfg-set DB_MEMORY 256MB
    config-derive
    expect-error 'PostgreSQL 18 holds the data and the new image is 19' native-data "$(native-render)"
    expect-fail test -e "${TMPDIR}/dumped" 'a refused major upgrade touches nothing'

}
test-operations-models () {

    local root="" directory="" compose="" text="" small="" pool=""

    fixture-release
    root="${CONFIG[STATE_ROOT]}/models"
    small="$(printf '{}' | fs-hash -)"
    pool="$(printf '{"cls":1}' | fs-hash -)"
    CONFIG_MODEL_FILES="
model     file                   size  sha256
embedder  config.json            2     ${small}
embedder  1_Pooling/config.json  9     ${pool}
ranker    config.json            2     ${small}
"
    config-models-load
    cfg-set MODELS embedder
    config-derive
    directory="${root}/embedder/${CONFIG_MODEL[embedder.revision]}"
    compose="${CONFIG[STATE_ROOT]}/models/model-embedder.yaml"

    net-fetch () {

        printf '%s %s\n' "${1}" "${5:-}" >> "${TMPDIR}/fetched"
        [[ ! -f "${TMPDIR}/offline" ]] || return 1
        if [[ "${2}" == */1_Pooling/* ]]; then printf '{"cls":1}' > "${2}"
        else printf '{}' > "${2}"
        fi
        chmod 644 "${2}"

    }
    docker-ready () { :; }
    docker-memory () { cat "${TMPDIR}/memory"; }
    docker-network () { printf '%s\n' "$*" >> "${TMPDIR}/networks"; }
    native-compose-models () { printf '%s\n' "$*" >> "${TMPDIR}/compose"; }
    native-models-healthy () { :; }
    native-announce () { printf '%s %s\n' "${1}" "${2}" >> "${TMPDIR}/announced"; }
    native-announce notice check
    native-models-healthy
    net-fetch https://models.test/warm "${TMPDIR}/warm"
    rm -f -- "${TMPDIR}/announced" "${TMPDIR}/fetched" "${TMPDIR}/warm"
    printf '%s\n' 99999999999 > "${TMPDIR}/memory"
    cfg-set MODELS_TOKEN hf-sentinel-token

    native-models-sync
    text="$(fs-read "${TMPDIR}/fetched")"
    expect-contains "${text}" "https://huggingface.co/BAAI/bge-m3/resolve/${CONFIG_MODEL[embedder.revision]}/1_Pooling/config.json hf-sentinel-token"
    expect-contains "${text}" "https://huggingface.co/BAAI/bge-m3/resolve/${CONFIG_MODEL[embedder.revision]}/config.json"
    expect-absent "${text}" bge-reranker 'only the models MODELS names are fetched'
    expect-equal "$(fs-mode "${directory}")" 755 'the model directory is readable by the unprivileged runner'
    expect-equal "$(fs-mode "${directory}/1_Pooling")" 755
    expect-equal "$(fs-mode "${directory}/config.json")" 644
    test -f "${directory}.verified" || err "A verified model must be stamped"
    expect-equal "$(fs-read "${TMPDIR}/networks")" 'shop-models shop internal'
    expect-equal "$(fs-read "${TMPDIR}/compose")" 'up -d --remove-orphans'

    text="$(fs-read "${compose}")"
    expect-contains "${text}" "image: \"${MANIFEST[images.tei]}\""
    expect-contains "${text}" "user: '65534:65534'"
    expect-contains "${text}" 'read_only: true'
    expect-contains "${text}" 'cap_drop: [ALL]'
    expect-contains "${text}" "HF_HUB_OFFLINE: '1'"
    expect-contains "${text}" 'mem_limit: "4g"'
    expect-contains "${text}" "source: \"${directory}\""
    expect-contains "${text}" $'target: /model\n        read_only: true'
    expect-contains "${text}" "aliases: ['embedder']"
    expect-contains "${text}" "name: 'shop-models'"
    expect-contains "${text}" '"--max-batch-tokens", "2048", "--auto-truncate"'
    expect-absent "${text}" hf-sentinel-token 'the token never reaches a Compose file'

    rm -f -- "${TMPDIR}/fetched"
    native-models-sync
    expect-fail test -e "${TMPDIR}/fetched" 'a verified model is never fetched again'

    printf '[]' > "${directory}/config.json"
    printf 'pickle' > "${directory}/pytorch_model.bin"
    mkdir -p "${root}/embedder/old-revision"
    printf 'old' > "${root}/embedder/old-revision/config.json"
    touch "${root}/embedder/old-revision.verified"
    text="$(native-models-verify 2>&1)"
    expect-equal "$(fs-read "${TMPDIR}/fetched")" "https://huggingface.co/BAAI/bge-m3/resolve/${CONFIG_MODEL[embedder.revision]}/config.json hf-sentinel-token" 'verify fetches only the file that differs'
    expect-contains "${text}" 'Removing embedder/pytorch_model.bin: the models table does not list it'
    expect-fail test -e "${directory}/pytorch_model.bin"
    expect-fail test -e "${root}/embedder/old-revision" 'a superseded revision is pruned once the new one verifies'
    expect-fail test -e "${root}/embedder/old-revision.verified"
    expect-equal "$(fs-read "${directory}/config.json")" '{}'

    printf '%s\n' 1048576 > "${TMPDIR}/memory"
    expect-error 'The models need 4096MiB of unreserved Docker memory' native-models-sync
    printf '%s\n' 99999999999 > "${TMPDIR}/memory"

    cfg-set MODELS 'embedder ranker'
    touch "${TMPDIR}/offline"
    rm -f -- "${TMPDIR}/fetched"
    native-models-converge 2>/dev/null
    expect-contains "$(fs-read "${TMPDIR}/announced")" 'models.failed the models embedder ranker did not converge; the release is unaffected'
    rm -f -- "${TMPDIR}/offline"

    rm -f -- "${TMPDIR}/fetched"
    CONFIG_MODEL_FILES="${CONFIG_MODEL_FILES/ranker    config.json            2/ranker    config.json            999999999999999}"
    config-models-load
    config-derive
    expect-error 'ranker needs 953674316MiB plus 1024MiB of headroom' native-models-pull
    expect-fail test -e "${TMPDIR}/fetched" 'no byte is fetched without the space for it'

    cfg-set MODELS ''
    : > "${TMPDIR}/compose"
    native-models-sync
    expect-fail test -e "${compose}" 'a model dropped from MODELS loses its Compose file'
    expect-equal "$(fs-read "${TMPDIR}/compose")" 'down --remove-orphans'
    test -f "${directory}/config.json" || err "Cached files outlive MODELS"

}
test-operations-logs () {

    local output=""

    fixture-release
    docker-ready () { :; }
    native-logs-compose () {

        case "${1} ${2}" in
            'data config') printf 'postgres\nredis\n' ;;
            'edge config') printf 'edge\n' ;;
            'data logs')   printf '%s\n' "${*:2}" >> "${TMPDIR}/logs"; printf 'connect DB_PASSWORD=%s ok\n' "${CONFIG[DB_ADMIN_PASSWORD]}" ;;
            *)             return 1 ;;
        esac

    }

    CLI_FLAGS[--since]=30m
    CLI_FLAGS[--tail]=50
    output="$(native-logs postgres)"
    expect-equal "${output}" 'connect DB_PASSWORD=[redacted] ok' 'logs redact every secret of the settings'
    expect-equal "$(fs-read "${TMPDIR}/logs")" 'logs --no-color --timestamps --tail 50 --since 30m postgres'

    expect-error 'Unknown service: ghost (running here: postgres redis edge)' native-logs ghost
    CLI_FLAGS[--since]='30 minutes'
    expect-error '--since takes a duration such as 30m' native-logs postgres
    CLI_FLAGS[--since]=2026-10-23T10:00:00Z
    CLI_FLAGS[--tail]=0
    expect-error '--tail takes 1 to 10000 lines' native-logs postgres
    expect-error 'Usage: infra logs SERVICE' native-logs

}
