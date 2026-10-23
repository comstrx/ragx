slack-send () {

    local text="${1:-}" body="" result="" status=0

    cfg-require SLACK_WEBHOOK_URL || return
    [[ -n "${text}" ]] || { err "Slack message required"; return; }

    body="$(fs-temp-file)" || return
    result="$(fs-temp-file)" || return

    printf '{"text":%s}\n' "$(parse-json-string "${text}")" | fs-write "${body}" || status=$?
    (( status != 0 )) || net-request POST "${CONFIG[SLACK_WEBHOOK_URL]}" "${result}" '' '' "${body}" || status=$?

    rm -f -- "${body}" "${result}"
    return "${status}"

}
