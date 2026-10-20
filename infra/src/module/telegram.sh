telegram-send () {

    local text="${1:-}" body="" result="" status=0

    cfg-require TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID || return
    [[ -n "${text}" ]] || { err "Telegram message required"; return; }

    body="$(fs-temp-file)" || return
    result="$(fs-temp-file)" || return

    printf '{"chat_id":%s,"text":%s}\n' "$(parse-json-string "${CONFIG[TELEGRAM_CHAT_ID]}")" "$(parse-json-string "${text}")" | fs-write "${body}" || status=$?
    (( status != 0 )) || net-request POST "${MANIFEST[endpoints.telegram]}/bot${CONFIG[TELEGRAM_BOT_TOKEN]}/sendMessage" "${result}" '' '' "${body}" || status=$?

    rm -f -- "${body}" "${result}"
    return "${status}"

}
