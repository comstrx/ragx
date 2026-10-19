cloudflare-request () {

    local method="${1}" path="${2}" result="${3}" body="${4:-}"

    cfg-require CLOUDFLARE_TOKEN CLOUDFLARE_ZONE || return
    [[ "${CONFIG[CLOUDFLARE_ZONE]}" =~ ^[a-f0-9]{32}$ ]] || { err "CLOUDFLARE_ZONE must be a zone identifier"; return; }
    need jq || return

    net-request "${method}" "${MANIFEST[endpoints.cloudflare]}/zones/${CONFIG[CLOUDFLARE_ZONE]}/dns_records${path}" \
        "${result}" Authorization "Bearer ${CONFIG[CLOUDFLARE_TOKEN]}" "${body}" || return

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

    local domain="${1:-}" address="${2:-}" proxied="${3:-false}" kind=A result="" payload="" record="" status=0

    parse-host "${domain}" || { err "Invalid domain: ${domain}"; return; }
    [[ "${address}" =~ ^[0-9A-Fa-f:.]+$ ]] || { err "Invalid DNS address: ${address}"; return; }
    parse-boolean "${proxied}" || { err "Proxied flag must be true or false"; return; }
    [[ "${address}" != *:* ]] || kind=AAAA

    result="$(fs-temp-file)" || return
    payload="$(fs-temp-file)" || return

    printf '{"type":"%s","name":%s,"content":%s,"ttl":300,"proxied":%s}\n' \
        "${kind}" "$(parse-json-string "${domain}")" "$(parse-json-string "${address}")" "${proxied}" | fs-write "${payload}" || status=$?

    if (( status == 0 )) && cloudflare-request GET "?name=$(parse-url-component "${domain}")&type=${kind}" "${result}"; then

        record="$(jq -r '.result[0].id // ""' "${result}")" || status=$?

        if [[ -z "${record}" ]]; then cloudflare-request POST '' "${result}" "${payload}" || status=$?
        elif [[ "${record}" =~ ^[a-f0-9]{32}$ ]]; then cloudflare-request PUT "/${record}" "${result}" "${payload}" || status=$?
        else err "Unexpected Cloudflare record identifier" || status=$?
        fi

    else
        status=1
    fi

    rm -f -- "${result}" "${payload}"
    return "${status}"

}
