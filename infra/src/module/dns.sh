#!/usr/bin/env bash

## managed names — point every name at the box, through cloudflare, only when a token says so

dns_call () {

    local method="${1:?Missing method}" path="${2:?Missing path}" body="${3:-}" token=""

    token="$(secret_require CLOUDFLARE_API_TOKEN)"

    curl -sS -X "${method}" "${CLOUDFLARE_API}${path}" \
        -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" \
        ${body:+--data "${body}"}

}
## the zone this stack answers in — CLOUDFLARE_ZONE_ID when the config names it, looked up by BASE_DOMAIN otherwise
dns_zone () {

    if [[ -z "${CLOUDFLARE_ZONE_ID}" ]]; then

        ensure curl jq

        CLOUDFLARE_ZONE_ID="$(dns_call GET "/zones?name=${BASE_DOMAIN}" | jq -r '.result[0].id // empty')"

        [[ -n "${CLOUDFLARE_ZONE_ID}" ]] || die "No Cloudflare zone answers for ${BASE_DOMAIN} — the token cannot see it, or the zone is not there"

        export CLOUDFLARE_ZONE_ID

    fi

    printf '%s' "${CLOUDFLARE_ZONE_ID}"

}
dns_api () {

    local method="${1:?Missing method}" path="${2:?Missing path}" body="${3:-}"

    dns_call "${method}" "/zones/$(dns_zone)${path}" "${body}"

}
## true when this stack owns its names — a token exists and nobody turned it off
dns_managed () {

    [[ "${DNS_MANAGED}" == "true" ]]

}
## the address every managed name points at
dns_edge () {

    printf 'A %s' "$(server_host)"

}
## upsert one dns record
dns_record () {

    local name="${1:?Missing name}" type="${2:?Missing type}" content="${3:?Missing content}" id="" body="" proxied=false ttl="${DNS_TTL}"

    ensure curl jq

    [[ "${DNS_PROXIED}" != "true" ]] || { proxied=true; ttl=1; }

    id="$(dns_api GET "/dns_records?name=${name}&type=${type}" | jq -r '.result[0].id // empty')"

    body="$(jq -nc --arg type "${type}" --arg name "${name}" --arg content "${content}" --argjson proxied "${proxied}" --argjson ttl "${ttl}" \
        '{type: $type, name: $name, content: $content, proxied: $proxied, ttl: $ttl}')"

    if [[ -n "${id}" ]]; then

        dns_api PUT "/dns_records/${id}" "${body}" | jq -e '.success' >/dev/null || die "Cannot update record: ${name}"

        info "${name} → ${type} ${content}"

        return 0

    fi

    dns_api POST "/dns_records" "${body}" | jq -e '.success' >/dev/null || die "Cannot create record: ${name}"

    info "${name} → ${type} ${content} (new)"

}
## the names this stack manages
dns_names () {

    printf '%s\n' "${DNS_NAMES// /$'\n'}"

}
## point every managed name at the box
dns_sync () {

    local edge="" type="" content="" name=""

    dns_managed || die "This stack manages no names — a CLOUDFLARE_API_TOKEN turns it on, DNS_MANAGED=false keeps it off"

    edge="$(dns_edge)"
    type="${edge%% *}"
    content="${edge#* }"

    for name in ${DNS_NAMES}; do

        dns_record "${name}" "${type}" "${content}"

    done

    succ "DNS points at this stack — every managed name resolves to $(server_host)."

}
## converge the names when this stack manages any — silent otherwise
dns_ensure () {

    dns_managed || { info "No managed names for this stack — dns converge skipped."; return 0; }

    dns_sync

}
## show the live records
dns_show () {

    ensure curl jq

    dns_api GET "/dns_records?per_page=100" \
        | jq -r '.result[] | "\(.type)\t\(.name)\t\(.content)\tproxied=\(.proxied)"'

}
