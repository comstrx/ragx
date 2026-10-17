#!/usr/bin/env bash

## live production checks — read-only, loud verdicts

AUDIT_FAILED=0

audit_check () {

    local label="${1:?Missing label}" ok="${2:-}" detail="${3:-}"

    if [[ "${ok}" == "true" ]]; then

        succ "${label}${detail:+ — ${detail}}"

        return 0

    fi

    err "${label}${detail:+ — ${detail}}"
    AUDIT_FAILED=1

}
audit_code () {

    local host="${1:?Missing host}" path="${2:-/}"

    curl -sk -o /dev/null -m 15 -w '%{http_code}' --resolve "${host}:${PUBLIC_PORT}:$(server_host)" "$(config_origin "${host}")${path}" 2>/dev/null || echo 000

}
## every public name answers through the edge on the box
audit_edge () {

    local host="" code=""

    ensure curl

    code="$(audit_code "${API_HOST}" "${RELEASE_PATH}")"

    audit_check "The api answers on ${API_HOST}" "$( [[ "${code}" == "200" ]] && echo true )" "HTTP ${code}"

    compose_enabled web || return 0

    for host in "${SUPER_HOST}" "${ADMIN_HOST}" "${CLIENT_HOST}"; do

        code="$(audit_code "${host}" /)"

        audit_check "The web answers on ${host}" "$( [[ "${code}" =~ ^[23] ]] && echo true )" "HTTP ${code}"

    done

}
## the certificate is not dying
audit_tls () {

    local days=""

    [[ "${TLS_ENABLED}" == "true" ]] || { info "TLS is off — no certificate to audit"; return 0; }

    days="$(edge_days || true)"

    audit_check "The certificate has time left" "$( [[ -n "${days}" ]] && (( days > WATCH_CERT_DAYS )) && echo true )" "${days:-no} day(s)"

}
## every container the stack runs is up and healthy
audit_services () {

    local report="" bad=""

    if server_here; then

        report="$(compose_cmd ps --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null)"

    else

        report="$(server_run "cd '${SERVER_PATH}/stack' && docker compose ps --format '{{.Service}} {{.State}} {{.Health}}'" 2>/dev/null)"

    fi

    bad="$(awk '$2 != "running" || ($3 != "" && $3 != "healthy") { print $1 }' <<< "${report}" | paste -sd ' ' -)"

    audit_check "Every container is running and healthy" "$( [[ -n "${report}" && -z "${bad}" ]] && echo true )" "${bad:-$(wc -l <<< "${report}") container(s)}"

}
## a recent backup exists
audit_backup () {

    local newest="" age=""

    newest="$(backup_list 2>/dev/null | grep -oE '[0-9]{8}-[0-9]{6}' | sort | tail -1)"

    [[ -z "${newest}" ]] || age=$(( ( $(date +%s) - $(date -u -d "${newest:0:4}-${newest:4:2}-${newest:6:2} ${newest:9:2}:${newest:11:2}:${newest:13:2}" +%s) ) / 3600 ))

    audit_check "A recent backup exists" "$( [[ -n "${age}" ]] && (( age < BACKUP_MAX_AGE_HOURS )) && echo true )" "${age:-no} hour(s) old"

}
## run every audit in one sweep
audit_all () {

    step "Auditing the '${STACK}' stack on $(server_host)"

    audit_edge
    audit_tls
    audit_services
    audit_backup

    (( AUDIT_FAILED == 0 )) || die "The stack is not in the shape it claims — the lines above say where"

    succ "Stack '${STACK}' audited — answering, certified, healthy, backed up."

}
## probe every watched target from outside: the health path answers 200 and the certificate is not dying
audit_watch () {

    local target="" code="" expiry="" left="" report="" targets="${WATCH_TARGETS:-${API_HOST}}"

    ensure curl openssl

    for target in ${targets}; do

        code="$(curl -sS -o /dev/null -m 15 -w '%{http_code}' "${SCHEME}://${target}${RELEASE_PATH}" || echo 000)"

        if [[ "${code}" != "200" ]]; then

            report+="🔴 ${target} answered ${code}"$'\n'
            continue

        fi

        [[ "${SCHEME}" == "https" ]] || continue

        expiry="$(printf '' | openssl s_client -connect "${target}:${HTTPS_PORT}" -servername "${target}" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"

        [[ -n "${expiry}" ]] || continue

        left=$(( ( $(date -d "${expiry}" +%s) - $(date +%s) ) / 86400 ))

        (( left > WATCH_CERT_DAYS )) || report+="🟠 ${target} certificate expires in ${left} days"$'\n'

    done

    if [[ -z "${report}" ]]; then

        succ "Every watched target answers."
        return 0

    fi

    log "${report}"
    audit_alarm "${report}"

    return 1

}
## tell the alert channel — silent when no bot token or chat id is configured
audit_alarm () {

    local token=""

    token="$(secret_get ALERT_BOT_TOKEN)"

    [[ -n "${token}" && -n "${ALERT_CHAT_ID}" ]] || return 0

    curl -sS -o /dev/null -X POST "${TELEGRAM_API}/bot${token}/sendMessage" \
        --data-urlencode "chat_id=${ALERT_CHAT_ID}" \
        --data-urlencode "text=${1:?audit_alarm needs a message}"

}
