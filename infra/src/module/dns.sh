#!/usr/bin/env bash

## managed names — point every domain at the stack edge

dns_call () {

    local method="${1:?Missing method}" path="${2:?Missing path}" body="${3:-}" token=""

    token="$(secret_require CLOUDFLARE_API_TOKEN)"

    curl -sS -X "${method}" "${CLOUDFLARE_API}${path}" \
        -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" \
        ${body:+--data "${body}"}

}
## the zone this stack answers in — CLOUDFLARE_DOMAIN_ID when the manifest names it, looked up by BASE_DOMAIN otherwise
dns_zone () {

    if [[ -z "${CLOUDFLARE_DOMAIN_ID}" ]]; then

        ensure curl jq

        CLOUDFLARE_DOMAIN_ID="$(dns_call GET "/zones?name=${BASE_DOMAIN}" | jq -r '.result[0].id // empty')"

        [[ -n "${CLOUDFLARE_DOMAIN_ID}" ]] || die "No Cloudflare zone answers for ${BASE_DOMAIN} — the token cannot see it, or the zone is not there"

        export CLOUDFLARE_DOMAIN_ID

    fi

    printf '%s' "${CLOUDFLARE_DOMAIN_ID}"

}
dns_api () {

    local method="${1:?Missing method}" path="${2:?Missing path}" body="${3:-}"

    dns_call "${method}" "/zones/$(dns_zone)${path}" "${body}"

}
## true when this stack owns names — the manifest check already demanded the token
dns_managed () {

    [[ -n "${DNS_MANAGED}" ]]

}
## resolve the current edge address
dns_edge () {

    local address=""

    if [[ -n "${EDGE_TYPE}" ]]; then

        ensure kubectl

        address="$(k8s_gateway_address hostname)"

        [[ -n "${address}" ]] || { warn "The gateway has no load balancer address yet — run 'infra dns sync' once it does"; return 1; }

        printf 'CNAME %s' "${address}"

        return 0

    fi

    printf 'A %s' "$(server_host)"

}
## upsert one dns record
dns_record () {

    local name="${1:?Missing name}" type="${2:?Missing type}" content="${3:?Missing content}" id="" body=""

    ensure curl jq

    id="$(dns_api GET "/dns_records?name=${name}" | jq -r '.result[0].id // empty')"

    body="$(jq -nc --arg type "${type}" --arg name "${name}" --arg content "${content}" \
        '{type: $type, name: $name, content: $content, proxied: false, ttl: 60}')"

    if [[ -n "${id}" ]]; then

        dns_api PUT "/dns_records/${id}" "${body}" | jq -e '.success' >/dev/null || die "Cannot update record: ${name}"

        info "${name} → ${type} ${content}"

        return 0

    fi

    dns_api POST "/dns_records" "${body}" | jq -e '.success' >/dev/null || die "Cannot create record: ${name}"

    info "${name} → ${type} ${content} (new)"

}
## list the names this stack manages
dns_names () {

    printf '%s' "${DNS_MANAGED}"

}
## point every managed name at the current edge
dns_sync () {

    local edge="" type="" content="" name=""

    dns_managed || die "Missing DNS_MANAGED — name the records this stack owns, or no stack owns any"

    edge="$(dns_edge)"
    type="${edge%% *}"
    content="${edge#* }"

    for name in $(dns_names); do

        dns_record "${name}" "${type}" "${content}"

    done

    succ "DNS points at this stack — every managed name resolves to its edge."

}
## converge the edge names when this stack manages any — silent otherwise
dns_ensure () {

    dns_managed || { info "No managed names for this stack — dns converge skipped."; return 0; }
    dns_edge >/dev/null 2>&1 || { warn "The edge has no address yet — names stay as they are until it does."; return 0; }

    dns_sync

}
## show the live records
dns_show () {

    ensure curl jq

    dns_api GET "/dns_records?per_page=100" \
        | jq -r '.result[] | "\(.type)\t\(.name)\t\(.content)\tproxied=\(.proxied)"'

}
