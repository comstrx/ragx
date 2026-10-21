tls-volumes () {

    local owner="${CONFIG[COMPOSE_PROJECT]}"

    docker-volume "${owner}-acme" "${owner}" || return
    docker-volume "${owner}-tls" "${owner}" 1000 "${CONFIG[IMAGE_HAPROXY]}"

}
tls-authority () {

    local directory="${1}" name="${2}" host="" alternatives=""
    local -A seen=()

    shift 2
    [[ ! -f "${directory}/ca.pem" || ! -f "${directory}/server.pem" || ! -f "${directory}/server.key" ]] || return 0
    (( $# > 0 )) || { err "Certificate names required"; return; }
    need openssl || return

    for host in "$@"; do
        [[ -z "${seen[${host}]:-}" ]] || continue
        seen["${host}"]=1
        if parse-address "${host}"; then alternatives+="${alternatives:+,}IP:${host}"
        else alternatives+="${alternatives:+,}DNS:${host}"
        fi
    done

    fs-dir "${directory}" || return

    (
        umask 077
        cd -- "${directory}" || exit
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 -subj "/CN=${name} authority" \
            -addext 'basicConstraints=critical,CA:true' -addext 'keyUsage=critical,keyCertSign,cRLSign' -keyout ca.key -out ca.pem &&
        openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=${1}" -keyout server.key -out server.csr &&
        printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:false\n' "${alternatives}" > server.ext &&
        openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days 825 -extfile server.ext -out server.pem
        status=$?
        rm -f ca.key ca.srl server.csr server.ext
        exit "${status}"
    ) >/dev/null 2>&1 || { err "Certificate authority creation failed: ${directory}"; return; }

    chmod 644 "${directory}/ca.pem" "${directory}/server.pem"

}
tls-certbot () {

    local credentials="" status=0
    local -a flags=(
        --memory 256m --tmpfs /tmp --tmpfs /var/log/letsencrypt --tmpfs /var/lib/letsencrypt --cap-add DAC_OVERRIDE
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-acme,target=/etc/letsencrypt"
    )

    case "${CONFIG[TLS_CHALLENGE]}" in
        http)
            flags+=( --network "${CONFIG[COMPOSE_PROJECT]}-apps" --network-alias acme )
        ;;
        dns)
            cfg-require DNS_PROVIDER DNS_TOKEN || return
            [[ "${CONFIG[DNS_TOKEN]}" =~ ^[A-Za-z0-9_-]+$ ]] || { err "DNS_TOKEN has an unexpected format"; return; }
            credentials="${CONFIG[STATE_ROOT]}/cloudflare.ini"
            printf 'dns_cloudflare_api_token = %s\n' "${CONFIG[DNS_TOKEN]}" | fs-write "${credentials}" || return
            flags+=( --network bridge --mount "type=bind,source=${credentials},target=/run/cloudflare.ini,readonly" )
        ;;
    esac

    docker-oneshot "${flags[@]}" -- "${CONFIG[IMAGE_CERTBOT]}" "$@" || status=$?
    [[ -z "${credentials}" ]] || rm -f -- "${credentials}"

    (( status == 0 )) || { err "Certbot failed: ${1:-}"; return; }

}
tls-issue () {

    local host=""
    local -a arguments=( certonly --non-interactive --agree-tos --keep-until-expiring --cert-name site --email "${CONFIG[TLS_EMAIL]}" )

    cfg-require TLS_EMAIL || return
    (( $# > 0 )) || { err "At least one certificate host required"; return; }

    for host in "$@"; do
        parse-host "${host}" || { err "Invalid certificate host: ${host}"; return; }
        arguments+=( -d "${host}" )
    done

    case "${CONFIG[TLS_CHALLENGE]}" in
        http) arguments+=( --standalone --http-01-port 8080 ) ;;
        dns)  arguments+=( --dns-cloudflare --dns-cloudflare-credentials /run/cloudflare.ini ) ;;
    esac

    tls-certbot "${arguments[@]}" || return
    tls-promote

}
tls-renew () {

    tls-certbot renew --non-interactive || return
    tls-promote

}
tls-promote () {

    docker-oneshot --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-acme,target=/acme,readonly" \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c \
        'set -eu; umask 077; cat /acme/live/site/fullchain.pem /acme/live/site/privkey.pem > /tls/site.pem.new; chown 1000:1000 /tls/site.pem.new; mv /tls/site.pem.new /tls/site.pem' ||
        { err "Certificate promotion failed"; return; }

}
tls-present () {

    docker-oneshot --user 1000:1000 --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls,readonly" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c 'test -s /tls/site.pem' >/dev/null 2>&1

}
tls-import () {

    local certificate="${1:-}" key="${2:-}" public="" private=""

    [[ -f "${certificate}" && -f "${key}" ]] || { err "Usage: infra tls import CERT KEY"; return; }
    need openssl || return

    public="$(openssl x509 -in "${certificate}" -pubkey -noout)" || { err "Unreadable certificate: ${certificate}"; return; }
    private="$(openssl pkey -in "${key}" -pubout)" || { err "Unreadable private key"; return; }
    [[ "${public}" == "${private}" ]] || { err "Certificate and key do not match"; return; }

    tls-volumes || return

    cat -- "${certificate}" "${key}" | docker-oneshot -i --user 1000:1000 --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c 'set -eu; umask 077; cat > /tls/site.pem.new; mv /tls/site.pem.new /tls/site.pem' ||
        { err "Certificate import failed"; return; }

}
tls-expiry () {

    local host="${1}" address="${2}" port="${3}"

    need openssl || return

    openssl s_client -connect "${address}:${port}" -servername "${host}" < /dev/null 2>/dev/null | tls-enddate || { err "No certificate answered on ${address}:${port}"; return; }

}
tls-enddate () {

    local line="" end=""

    need openssl || return

    end="$(while IFS= read -r line; do printf '%s\n' "${line#Cert:}"; done | openssl x509 -noout -enddate 2>/dev/null)" || return 1

    date -u -d "${end#notAfter=}" +%s 2>/dev/null || { err "Certificate expiry unreadable: ${end}"; return; }

}
