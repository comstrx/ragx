#!/usr/bin/env bash

## the edge — the certificate and the running nginx

edge_certbot () {

    compose_cmd run --rm --no-deps certbot "$@"

}
## true when the certificate lineage already lives in the certs volume
edge_certified () {

    compose_cmd run --rm --no-deps --entrypoint test nginx -f "/etc/letsencrypt/live/${TLS_NAME}/fullchain.pem" >/dev/null 2>&1

}
## the certificate exists before the tls edge renders — dns-01 straight away, http-01 through a plain edge first
edge_prepare () {

    [[ "${TLS_ENABLED}" == "true" ]] || return 0

    ! edge_certified || return 0

    if [[ "${TLS_DNS01}" == "true" ]]; then

        ( TLS_ENABLED=false; compose_render ) >/dev/null
        edge_issue

        return 0

    fi

    ( TLS_ENABLED=false; compose_render ) >/dev/null
    compose_up nginx
    edge_issue

}
## obtain or expand the certificate — dns-01 through cloudflare when a token exists (wildcard), http-01 through the running edge otherwise
edge_issue () {

    local args=() name=""

    server_here || { server_forward edge issue; return; }

    [[ "${TLS_ENABLED}" == "true" ]] || die "TLS_ENABLED is false — nothing to issue"
    [[ -n "${SSL_EMAIL}" ]] || die "Missing SSL_EMAIL — the ACME account needs an owner"

    args=( certonly --non-interactive --agree-tos --no-eff-email --email "${SSL_EMAIL}" --cert-name "${TLS_NAME}" \
           --key-type ecdsa --elliptic-curve secp256r1 --server "${ACME_URL}" --keep-until-expiring --expand )

    for name in ${TLS_NAMES}; do args+=( -d "${name}" ); done

    if [[ "${TLS_DNS01}" == "true" ]]; then

        args+=( --dns-cloudflare --dns-cloudflare-credentials /run/secrets/cloudflare --dns-cloudflare-propagation-seconds "${DNS_PROPAGATION}" )

    else

        args+=( --webroot --webroot-path /var/www/acme )

    fi

    step "Issuing ${TLS_NAME} for: ${TLS_NAMES}"

    edge_certbot "${args[@]}" || die "Certificate issuance failed — the certbot output above carries the reason"

    succ "Certificate ready for ${TLS_NAME}."

}
## renew when due, then reload the edge so it serves the new chain
edge_renew () {

    server_here || { server_forward edge renew; return; }

    [[ "${TLS_ENABLED}" == "true" ]] || { info "TLS is off — nothing to renew"; return 0; }

    edge_certbot renew --non-interactive --quiet || die "Renewal failed — the certbot output above carries the reason"

    edge_reload

}
## test and reload the running edge — a broken configuration is refused, the running one stays
edge_reload () {

    server_here || { server_forward edge reload; return; }

    [[ -n "$(compose_running nginx)" ]] || { info "The edge is not running — nothing to reload"; return 0; }

    compose_cmd exec -T nginx nginx -t -c /etc/nginx/platform/nginx.conf >/dev/null 2>&1 \
        || { compose_cmd exec -T nginx nginx -t -c /etc/nginx/platform/nginx.conf; die "The edge refused its configuration — nothing was reloaded"; }

    compose_cmd exec -T nginx nginx -s reload

    succ "Edge reloaded."

}
## test the rendered edge configuration without touching the running one
edge_test () {

    server_here || { server_forward edge test; return; }

    compose_cmd run --rm --no-deps nginx nginx -t -c /etc/nginx/platform/nginx.conf

}
## the days left on the certificate the edge serves
edge_days () {

    local end=""

    ensure openssl

    end="$(printf '' | openssl s_client -servername "${API_HOST}" -connect "$(server_host):${HTTPS_PORT}" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"

    [[ -n "${end}" ]] || return 1

    printf '%s' $(( ( $(date -d "${end}" +%s) - $(date +%s) ) / 86400 ))

}
## the names the certificate covers
edge_names () {

    printf '%s\n' "${TLS_NAMES// /$'\n'}"

}
