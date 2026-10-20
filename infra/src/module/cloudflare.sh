cloudflare-request () {

    local method="${1}" path="${2}" result="${3}" body="${4:-}"

    cfg-require DNS_TOKEN DNS_ZONE || return
    [[ "${CONFIG[DNS_ZONE]}" =~ ^[a-f0-9]{32}$ ]] || { err "DNS_ZONE must be a Cloudflare zone identifier"; return; }
    need jq || return

    net-request "${method}" "${MANIFEST[endpoints.cloudflare]}/zones/${CONFIG[DNS_ZONE]}/dns_records${path}" \
        "${result}" Authorization "Bearer ${CONFIG[DNS_TOKEN]}" "${body}" || return

    jq -e '.success == true' "${result}" >/dev/null || { err "Cloudflare rejected ${method} ${path%%\?*}"; return; }

}
cloudflare-check () {

    local domain="${1:-}" result="" status=0

    parse-host "${domain}" || { err "Invalid domain: ${domain}"; return; }
    result="$(fs-temp-file)" || return

    cloudflare-request GET "?name=$(parse-url-component "${domain}")" "${result}" || status=$?
    (( status != 0 )) || jq '[.result[] | {id, type, name, content, proxied}]' "${result}" || status=$?

    rm -f -- "${result}"
    return "${status}"

}
cloudflare-upsert () {

    local domain="${1:-}" address="${2:-}" proxied="${3:-false}" kind=A ttl=300 result="" payload="" record="" status=0

    parse-host "${domain}" || { err "Invalid domain: ${domain}"; return; }
    [[ "${address}" =~ ^[0-9A-Fa-f:.]+$ ]] || { err "Invalid DNS address: ${address}"; return; }
    parse-boolean "${proxied}" || { err "Proxied flag must be true or false"; return; }
    [[ "${address}" != *:* ]] || kind=AAAA
    [[ "${proxied}" != true ]] || ttl=1

    result="$(fs-temp-file)" || return
    payload="$(fs-temp-file)" || return

    printf '{"type":"%s","name":%s,"content":%s,"ttl":%s,"proxied":%s}\n' \
        "${kind}" "$(parse-json-string "${domain}")" "$(parse-json-string "${address}")" "${ttl}" "${proxied}" | fs-write "${payload}" || status=$?

    if (( status == 0 )) && cloudflare-request GET "?name=$(parse-url-component "${domain}")&type=${kind}" "${result}"; then

        record="$(jq -r --arg content "${address}" --argjson proxied "${proxied}" \
            '.result[0] // empty | if .content == $content and .proxied == $proxied then "current" elif (.id | test("^[a-f0-9]{32}$")) then .id else error("unexpected record identifier") end' "${result}")" || err "Unexpected Cloudflare record for ${domain}" || status=$?

        case "${status}:${record}" in
            0:current) ;;
            0:)        cloudflare-request POST '' "${result}" "${payload}" || status=$? ;;
            0:*)       cloudflare-request PUT "/${record}" "${result}" "${payload}" || status=$? ;;
        esac

    else
        status=1
    fi

    rm -f -- "${result}" "${payload}"
    return "${status}"

}
