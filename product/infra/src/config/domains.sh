CONFIG_DOMAINS_SHAPE='.domains[] | "\(.domain) \(.part)"'

config-domains-on () {

    [[ -n "${CONFIG[DOMAINS_ENDPOINT]}" && -n "${CONFIG[DOMAINS_TOKEN]}" && "${CONFIG[DOMAINS_INTERVAL]}" =~ ^[1-9][0-9]*$ ]]

}
config-domains-fetch () {

    local cache="${1}" tag="${2}" body="" code="" lines="" domain="" part="" rest="" fixed=""
    local -A seen=()

    need jq || return
    [[ -f "${cache}" ]] || rm -f -- "${tag}"
    body="$(fs-temp-file)" || return

    if ! code="$(net-request GET "${CONFIG[DOMAINS_ENDPOINT]}" "${body}" Authorization "Bearer ${CONFIG[DOMAINS_TOKEN]}" "" "" "${tag}")"; then
        rm -f -- "${body}"
        err "DOMAINS_ENDPOINT is unreachable; the edge keeps its current domains"
        return
    fi

    if [[ "${code}" == 304 ]]; then
        rm -f -- "${body}"
        fs-read "${cache}"
        return
    fi

    if ! lines="$(jq -r "${CONFIG_DOMAINS_SHAPE}" "${body}" 2>/dev/null)"; then
        rm -f -- "${body}" "${tag}"
        err "DOMAINS_ENDPOINT answered outside the shape of src/config/domains.sh; the edge keeps its current domains"
        return
    fi

    rm -f -- "${body}"
    fixed=" $(config-domains-fixed) "

    while read -r domain part rest; do

        [[ -n "${domain}" ]] || continue
        domain="${domain,,}"

        if [[ -n "${rest}" ]] || ! parse-host "${domain}" || [[ " ${CONFIG_PARTS[*]} " != *" ${part} "* ]]; then
            warn "Skipping the domain entry '${domain} ${part}': a host and a part of the table are expected"
        elif [[ "${fixed}" == *" ${domain} "* || -n "${seen[${domain}]:-}" ]]; then
            warn "Skipping ${domain}: it is already routed"
        else
            seen["${domain}"]="${part}"
            out "${domain} ${part}"
        fi

    done <<< "${lines}" | LC_ALL=C sort

}
config-domains-fixed () {

    local name="" fixed=""

    for name in "${CONFIG_PARTS[@]}"; do
        fixed+=" $(config-list "${CONFIG[${name^^}_DOMAIN]:-}")"
    done

    fixed+=" $(config-list "${CONFIG[GRAFANA_DOMAIN]}")"

    out "${fixed//$'\n'/ }"

}
config-domains-guard () {

    local current="${1}" wanted="${2}" domain="" count=0 removed=0 allowed=0
    local -A next=()

    while read -r domain _; do
        [[ -z "${domain}" ]] || next["${domain}"]=1
    done <<< "${wanted}"

    while read -r domain _; do
        [[ -n "${domain}" ]] || continue
        count=$(( count + 1 ))
        [[ -n "${next[${domain}]:-}" ]] || removed=$(( removed + 1 ))
    done <<< "${current}"

    allowed=$(( count * CONFIG[DOMAINS_MAX_DROP] / 100 ))
    (( allowed >= 1 )) || allowed=1

    (( removed <= allowed )) || { err "DOMAINS_ENDPOINT drops ${removed} of ${count} domains, above DOMAINS_MAX_DROP=${CONFIG[DOMAINS_MAX_DROP]}%; check the endpoint, or accept with infra edge sync --force"; return; }

}
