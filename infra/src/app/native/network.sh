source-include module/tls.sh || return
source-include module/cloudflare.sh || return
source-include module/firewall.sh || return
source-include module/haproxy.sh || return

native-dns () {

    cli-dispatch native-dns "${1:-check}" 'check set' "${@:2}"

}
native-dns-check () {

    local driver=""

    driver="$(native-dns-driver)" || return
    "${driver}-check" "${1:-${CONFIG[API_HOST]}}"

}
native-dns-set () {

    local driver=""

    driver="$(native-dns-driver)" || return
    cfg-require DNS_ADDRESS || return

    "${driver}-upsert" "${1:-${CONFIG[API_HOST]}}" "${CONFIG[DNS_ADDRESS]}" "${CONFIG[DNS_PROXIED]}" || return
    ui-result dns-set true safe

}
native-dns-sync () {

    local driver="" host=""

    [[ -n "${CONFIG[DNS_PROVIDER]}" ]] || return 0
    driver="$(native-dns-driver)" || return

    while IFS= read -r host; do
        "${driver}-upsert" "${host}" "${CONFIG[DNS_ADDRESS]}" "${CONFIG[DNS_PROXIED]}" || warn "${driver} kept the previous record for ${host}"
    done < <(native-hosts)

}
native-dns-driver () {

    cfg-require DNS_PROVIDER || return
    config-check cloudflare DNS_PROVIDER || return

    out "${CONFIG[DNS_PROVIDER]}"

}
native-tls () {

    cli-dispatch native-tls "${1:-present}" 'issue renew present import' "${@:2}"

}
native-tls-issue () {

    tls-volumes || return
    native-certificate || return
    native-edge-reload

}
native-tls-renew () {

    tls-renew || { native-announce tls.renewal-failed "certificate renewal failed; the current certificate keeps serving"; return 1; }
    native-edge-reload

}
native-tls-present () {

    tls-present && { out present; return; }

    out absent
    return 1

}
native-tls-import () {

    tls-import "$@" || return
    rm -f -- "${CONFIG[STATE_ROOT]}/certificate"
    [[ ! -f "${CONFIG[STATE_ROOT]}/edge/edge.yaml" ]] || native-edge-reload

}
native-firewall () {

    cli-dispatch native-firewall "${1:-ports}" 'ports apply' "${@:2}"

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
