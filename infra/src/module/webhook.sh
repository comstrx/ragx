webhook-send () {

    local payload="${1:-}" body="" result="" signature="" status=0

    cfg-require WEBHOOK_URL || return
    [[ -n "${payload}" ]] || { err "Webhook payload required"; return; }

    body="$(fs-temp-file)" || return
    result="$(fs-temp-file)" || return

    printf '%s\n' "${payload}" | fs-write "${body}" || status=$?
    (( status != 0 )) || [[ -z "${CONFIG[WEBHOOK_SECRET]}" ]] || signature="sha256=$(net-hmac "${CONFIG[WEBHOOK_SECRET]}" "${body}")" || status=$?
    (( status != 0 )) || net-request POST "${CONFIG[WEBHOOK_URL]}" "${result}" "${signature:+X-Infra-Signature}" "${signature}" "${body}" || status=$?

    rm -f -- "${body}" "${result}"
    return "${status}"

}
