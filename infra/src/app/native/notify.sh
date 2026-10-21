source-include module/telegram.sh || return
source-include module/slack.sh || return
source-include module/webhook.sh || return

native-notify () {

    local channels="" channel=""

    (( $# > 0 )) || { err "Usage: infra notify MESSAGE [--channel NAME]"; return; }
    native-notify-flags || return
    channel="$(cli-value --channel)" || channel=""
    channels="$(native-channels)"
    [[ -z "${channel}" || "${channels}" == "${channel}" ]] || { err "${channel} is not configured; pass its flags or set its settings"; return; }
    [[ -n "${channels}" ]] || { info "No notification channel is configured; nothing sent"; return 0; }

    native-deliver notice "$*" || return
    ui-row sent "${channels//$'\n'/ }"

}
native-announce () {

    native-deliver "$@" || warn "The ${1} notification did not reach every channel"
    return 0

}
native-notify-flags () {

    local flag="" key="" value=""

    for flag in --token=TELEGRAM_BOT_TOKEN --chat=TELEGRAM_CHAT_ID --hook=SLACK_WEBHOOK_URL --url=WEBHOOK_URL --secret=WEBHOOK_SECRET; do
        key="${flag#*=}"
        value="$(cli-value "${flag%%=*}")" || continue
        cfg-set "${key}" "${value}" cli
    done

    config-check-set bot TELEGRAM_BOT_TOKEN || return
    config-check-set chat TELEGRAM_CHAT_ID || return
    config-check-set webhook SLACK_WEBHOOK_URL WEBHOOK_URL || return
    config-group TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID || return

    case "$(cli-value --channel)" in
        '')       ;;
        telegram) cfg-set SLACK_WEBHOOK_URL '' cli; cfg-set WEBHOOK_URL '' cli ;;
        slack)    cfg-set TELEGRAM_BOT_TOKEN '' cli; cfg-set WEBHOOK_URL '' cli ;;
        webhook)  cfg-set TELEGRAM_BOT_TOKEN '' cli; cfg-set SLACK_WEBHOOK_URL '' cli ;;
        *)        err "Unknown channel: $(cli-value --channel) (expected telegram, slack or webhook)"; return ;;
    esac

}
native-deliver () {

    local event="${1:-}" text="${2:-}" emoji="" level="" line="" payload="" channel="" failed=""

    read -r emoji level < <(native-event "${event}") || { err "Unknown notification event: ${event}"; return; }
    [[ -n "${text}" ]] || { err "Notification text required"; return; }

    line="${emoji} ${CONFIG[COMPOSE_PROJECT]}: ${text}"
    payload="$(printf '{"event":%s,"level":%s,"project":%s,"release":%s,"host":%s,"time":%s,"text":%s}' \
        "$(parse-json-string "${event}")" "$(parse-json-string "${level}")" "$(parse-json-string "${CONFIG[COMPOSE_PROJECT]}")" \
        "$(parse-json-string "${CONFIG[RELEASE]:-}")" "$(parse-json-string "$(uname -n)")" "$(parse-json-string "$(date -u +%Y-%m-%dT%H:%M:%SZ)")" \
        "$(parse-json-string "${text}")")"

    while IFS= read -r channel; do
        [[ -n "${channel}" ]] || continue
        run-retry "$(( CONFIG[NOTIFY_RETRIES] + 1 ))" 2 native-send "${channel}" "${line}" "${payload}" || failed+="${failed:+ }${channel}"
    done < <(native-channels)

    [[ -z "${failed}" ]] || { err "Notification failed on ${failed}"; return; }

}
native-send () {

    case "${1}" in
        telegram) telegram-send "${2}" ;;
        slack)    slack-send "${2}" ;;
        webhook)  webhook-send "${3}" ;;
        *)        err "Unknown notification channel: ${1}" ;;
    esac

}
native-channels () {

    [[ -z "${CONFIG[TELEGRAM_BOT_TOKEN]}" ]] || out telegram
    [[ -z "${CONFIG[SLACK_WEBHOOK_URL]}" ]] || out slack
    [[ -z "${CONFIG[WEBHOOK_URL]}" ]] || out webhook

    return 0

}
native-event () {

    case "${1:-}" in
        deploy.succeeded)    out '🚀 info' ;;
        deploy.switched)     out '↩️ warning' ;;
        deploy.rejected)     out '🔴 error' ;;
        deploy.unrecovered)  out '🆘 critical' ;;
        verify.rolled-back)  out '↩️ error' ;;
        verify.degraded)     out '🔴 critical' ;;
        verify.unrecovered)  out '🆘 critical' ;;
        rollback.succeeded)  out '↩️ warning' ;;
        rollback.failed)     out '🆘 critical' ;;
        backup.succeeded)    out '💾 info' ;;
        backup.failed)       out '🔴 error' ;;
        restore.succeeded)   out '♻️ warning' ;;
        restore.failed)      out '🔴 error' ;;
        monitor.degraded)    out '⚠️ warning' ;;
        monitor.recovered)   out '✅ info' ;;
        edge.rolled-back)    out '🔴 error' ;;
        tls.renewal-failed)  out '🔴 error' ;;
        service.started)     out '▶️ info' ;;
        service.stopped)     out '⏸️ warning' ;;
        service.uninstalled) out '🗑️ warning' ;;
        scale.applied)       out '↕️ info' ;;
        notice)              out '📣 info' ;;
        *)                   return 1 ;;
    esac

}
