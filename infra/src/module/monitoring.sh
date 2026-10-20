monitoring-render () {

    local directory="${1}" templates="${MANIFEST[paths.templates]}/native/monitor" alerting="" alertmanager="" receivers=""

    if [[ -n "${CONFIG[TELEGRAM_BOT_TOKEN]}" ]]; then
        receivers+=$'    telegram_configs:\n      - bot_token_file: /run/secrets/telegram-token\n'
        receivers+="        chat_id: ${CONFIG[TELEGRAM_CHAT_ID]}"$'\n        send_resolved: true\n'
    fi

    [[ -z "${CONFIG[SLACK_WEBHOOK_URL]}" ]] || receivers+=$'    slack_configs:\n      - api_url_file: /run/secrets/slack-url\n        send_resolved: true\n'
    cfg-set MONITOR_RECEIVERS "${receivers%$'\n'}"

    if [[ -n "${receivers}" ]]; then
        alerting=$'alerting:\n  alertmanagers:\n    - static_configs: [{targets: [\'alertmanager:9093\']}]\n'
        alertmanager="$(template-text "${templates}/alertmanager.yaml.tpl")" || return
    fi

    cfg-set MONITOR_ALERTING "${alerting}"
    cfg-set MONITOR_ALERTMANAGER "${alertmanager}"

    fs-dir "${directory}" || return
    template-render "${templates}/monitor.yaml.tpl" "${directory}/monitor.yaml" || return
    template-render "${templates}/prometheus.yml.tpl" "${directory}/prometheus/prometheus.yml" || return
    template-render "${templates}/rules.yml.tpl" "${directory}/prometheus/rules.yml" || return
    template-render "${templates}/datasource.yaml" "${directory}/grafana/datasources/prometheus.yaml" || return
    template-render "${templates}/dashboards.yaml" "${directory}/grafana/dashboards/platform.yaml" || return
    template-render "${templates}/platform.json" "${directory}/grafana/dashboards/platform.json" || return

    printf '%s' "${CONFIG[GRAFANA_PASSWORD]}" | fs-write "${directory}/secrets/grafana-password" || return
    printf '%s' "${CONFIG[DB_PASSWORD]}" | fs-write "${directory}/secrets/db-password" || return

    [[ -n "${alertmanager}" ]] || return 0

    template-render "${templates}/alertmanager.yml.tpl" "${directory}/alertmanager/alertmanager.yml" || return
    printf '%s' "${CONFIG[TELEGRAM_BOT_TOKEN]}" | fs-write "${directory}/secrets/telegram-token" || return
    printf '%s' "${CONFIG[SLACK_WEBHOOK_URL]}" | fs-write "${directory}/secrets/slack-url"

}
monitoring-fingerprint () {

    local directory="${1}" file="" digest=""

    [[ -d "${directory}" ]] || return 1

    while IFS= read -r -d '' file; do
        digest="$(fs-hash "${file}")" || return
        printf '%s %s\n' "${file#"${directory}/"}" "${digest}"
    done < <(fs-files "${directory}") | fs-hash -

}
monitoring-compose () {

    local directory="${1}"

    shift

    docker-compose "${CONFIG[COMPOSE_PROJECT]}-monitor" -f "${directory}/monitor.yaml" "$@"

}
monitoring-healthy () {

    local directory="${1}" ids="" container="" count=0

    ids="$(monitoring-compose "${directory}" ps -aq)" || return 1

    while IFS= read -r container; do
        [[ -n "${container}" ]] || continue
        docker-health "${container}" || return 1
        count=$(( count + 1 ))
    done <<< "${ids}"

    (( count > 0 ))

}
monitoring-password () {

    local directory="${1}"

    monitoring-compose "${directory}" exec -T grafana grafana cli admin reset-admin-password --password-from-stdin \
        < "${directory}/secrets/grafana-password" >/dev/null || { err "Grafana admin password was not applied"; return; }

}
