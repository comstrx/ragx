source-include module/haproxy.sh || return
source-include module/tls.sh || return

native-edge-sync () {

    config-domains-on || { info "Dynamic domains are off (they need DOMAINS_ENDPOINT, DOMAINS_TOKEN and a DOMAINS_INTERVAL above 0); the edge routes the fixed domains only"; return 0; }
    config-validate || return
    docker-ready || return
    [[ -f "${CONFIG[STATE_ROOT]}/edge/haproxy.cfg" ]] || { err "No edge yet; run infra edge apply first"; return; }

    native-edge-sync-run

}
native-edge-sync-run () {

    local live="${CONFIG[STATE_ROOT]}/edge" current="" wanted=""

    wanted="$(config-domains-fetch "${live}/domains.wanted" "${CONFIG[STATE_ROOT]}/domains.etag")" || return
    current="$(fs-read "${live}/domains.wanted" 2>/dev/null)" || current=""

    if [[ "${wanted}" != "${current}" ]]; then
        cli-flag --force || config-domains-guard "${current}" "${wanted}" || return
        native-edge-domains "${live}/domains.wanted" "${wanted}" || return
    fi

    native-certificate-run || warn "Certificates did not converge; the domains without one wait for the next run"

    state-locked "${CONFIG[STATE_ROOT]}/lock" native-edge-sync-publish

}
native-edge-sync-publish () {

    local live="${CONFIG[STATE_ROOT]}/edge" current="" routable=""

    routable="$(native-domains-routable)" || return
    current="$(fs-read "${live}/domains.map" 2>/dev/null)" || current=""

    if [[ "${routable}" == "${current}" ]] && ! cfg-true CERTIFICATES_CHANGED; then
        ui-result edge-sync false safe
        return
    fi

    native-edge-domains "${live}/domains.map" "${routable}" || return

    if ! native-edge-reload; then
        native-edge-domains "${live}/domains.map" "${current}" || return
        native-edge-reload || return
        err "The edge refused the new domains; the previous ones keep serving"
        return
    fi

    ui-result edge-sync true safe

}
native-domains-routable () {

    local live="${CONFIG[STATE_ROOT]}/edge" wanted="" recorded="" groups="" group="" entry="" domain="" part="" base=""
    local -a hosts=() names=()
    local -A entries=() ready=()

    wanted="$(fs-read "${live}/domains.wanted" 2>/dev/null)" || return 0
    [[ -n "${wanted}" ]] || return 0
    cfg-true TLS_ENABLED || { out "${wanted}"; return; }

    recorded="$(state-read "${CONFIG[STATE_ROOT]}" certificates 2>/dev/null)" || recorded=""

    while IFS= read -r entry; do
        [[ -z "${entry}" ]] || entries["${entry%% *}"]="${entry}"
    done <<< "${recorded}"

    while read -r domain _; do
        names+=( "${domain}" )
    done <<< "${wanted}"

    groups="$(tls-groups "${names[@]}")" || return

    while IFS= read -r group; do
        base="${group%% *}"
        entry="${entries[${base}]:-}"
        read -r -a hosts <<< "${group#* }"
        for domain in "${hosts[@]}"; do
            [[ "${entry}" != "${base} imported" && " ${entry} " != *" ${domain} "* ]] || ready["${domain}"]=1
        done
    done <<< "${groups}"

    while read -r domain part; do
        [[ -z "${ready[${domain}]:-}" ]] || out "${domain} ${part}"
    done <<< "${wanted}"

}
native-edge-domains () {

    local file="${1}" lines="${2}"

    if [[ -n "${lines}" ]]; then printf '%s\n' "${lines}" | fs-write "${file}" 644
    else printf '' | fs-write "${file}" 644
    fi

}
