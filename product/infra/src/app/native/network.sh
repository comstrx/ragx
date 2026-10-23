source-include module/tls.sh || return
source-include module/firewall.sh || return
source-include module/haproxy.sh || return

native-tls () {

    native-dispatch tls "$@"

}
native-tls-issue () {

    tls-volumes || return
    native-certificate-refresh

}
native-tls-renew () {

    local entry=""
    local -a issued=()

    while IFS= read -r entry; do
        [[ -z "${entry}" || "${entry#* }" == imported ]] || issued+=( "${entry%% *}" )
    done < <(state-read "${CONFIG[STATE_ROOT]}" certificates 2>/dev/null)

    tls-renew "${issued[@]}" || { native-announce tls.renewal-failed "certificate renewal failed; the current certificates keep serving"; return 1; }
    native-edge-reload

}
native-tls-present () {

    tls-present && { out present; return; }

    out absent
    return 1

}
native-tls-import () {

    local base=""

    base="$(tls-import "$@")" || return
    native-certificate-record "${base}" "${base} imported" || return
    [[ ! -f "${CONFIG[STATE_ROOT]}/edge/edge.yaml" ]] || native-edge-reload

}
native-firewall () {

    native-dispatch firewall "$@"

}
native-firewall-ports () {

    out "${CONFIG[HTTP_PORT]}/tcp"
    cfg-true TLS_ENABLED && out "${CONFIG[HTTPS_PORT]}/tcp"
    haproxy-quic && out "${CONFIG[HTTPS_PORT]}/udp"

    return 0

}
native-firewall-apply () {

    local -a ports=()

    cli-flag --force || { err "Review firewall ports, then repeat with --force; no rule is removed"; return; }
    mapfile -t ports < <(native-firewall-ports)

    firewall-apply "${ports[@]}" || return
    ui-result firewall-apply true safe

}
