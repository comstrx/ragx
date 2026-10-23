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

    docker-oneshot --memory 256m --tmpfs /tmp --tmpfs /var/log/letsencrypt --tmpfs /var/lib/letsencrypt --cap-add DAC_OVERRIDE \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-acme,target=/etc/letsencrypt" \
        --network "${CONFIG[COMPOSE_PROJECT]}-apps" --network-alias acme \
        -- "${CONFIG[IMAGE_CERTBOT]}" "$@" || { err "Certbot failed: ${1:-}"; return; }

}
tls-groups () {

    local host="" line="" groups=""
    local -a hosts=()
    local program='
        $0 !~ /^\/\// && NF { rule[$1] = 1 }
        END {
            total = split(hosts, list, " ")
            for (h = 1; h <= total; h++) {
                count = split(list[h], label, ".")
                size = 0
                for (i = 1; i <= count && size == 0; i++) {
                    suffix = label[i]
                    for (j = i + 1; j <= count; j++) suffix = suffix "." label[j]
                    if (("!" suffix) in rule) size = count - i
                }
                for (i = 1; i <= count && size == 0; i++) {
                    suffix = label[i]
                    wild = "*"
                    for (j = i + 1; j <= count; j++) { suffix = suffix "." label[j]; wild = wild "." label[j] }
                    if ((suffix in rule) || (i < count && (wild in rule))) size = count - i + 1
                }
                if (size == 0) size = 1
                if (size >= count) { print "! " list[h]; continue }
                base = label[count - size]
                for (j = count - size + 1; j <= count; j++) base = base "." label[j]
                if (!(base in group)) { order[++bases] = base; group[base] = base }
                group[base] = group[base] " " list[h]
            }
            for (b = 1; b <= bases; b++) print group[order[b]]
        }'

    (( $# > 0 )) || { err "Certificate names required"; return; }

    for host in "$@"; do
        parse-host "${host}" || { err "Invalid certificate host: ${host}"; return; }
    done

    mapfile -t hosts < <(printf '%s\n' "${@,,}" | LC_ALL=C sort -u)
    groups="$(asset-text "${MANIFEST[paths.templates]}/generated/suffixes.dat" | awk -v hosts="${hosts[*]}" "${program}")" || { err "Public suffix lookup failed"; return; }

    while IFS= read -r line; do
        [[ "${line}" != '! '* ]] || { err "${line#! } is a public suffix; route a name under it"; return; }
    done <<< "${groups}"

    LC_ALL=C sort <<< "${groups}"

}
tls-issue () {

    local force="${1:-}" base="" host=""
    local -a arguments=()

    if [[ "${force}" == --force ]]; then shift
    else force=""
    fi

    base="${1:-}"
    arguments=( certonly --non-interactive --agree-tos --keep-until-expiring --cert-name "${base}" --email "${CONFIG[TLS_EMAIL]}" )
    ! cfg-true TLS_STAGING || arguments+=( --staging )
    [[ -z "${force}" ]] || arguments+=( --force-renewal )

    cfg-require TLS_EMAIL || return
    parse-host "${base}" || { err "Invalid certificate name: ${base}"; return; }
    shift
    (( $# > 0 )) || { err "At least one certificate host required"; return; }

    for host in "$@"; do
        parse-host "${host}" || { err "Invalid certificate host: ${host}"; return; }
        arguments+=( -d "${host}" )
    done

    tls-certbot "${arguments[@]}" --standalone --http-01-port 8080 || return
    tls-promote "${base}"

}
tls-renew () {

    tls-certbot renew --non-interactive || return
    (( $# == 0 )) || tls-promote "$@"

}
tls-promote () {

    local name=""

    (( $# > 0 )) || { err "Certificate names required"; return; }

    for name in "$@"; do
        parse-host "${name}" || { err "Invalid certificate name: ${name}"; return; }
    done

    docker-oneshot --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-acme,target=/acme,readonly" \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c \
        'set -eu; umask 077; mkdir -p /tls/certs /tls/.staging; chown 1000:1000 /tls/certs /tls/.staging
        for name in "$@"; do
            cat "/acme/live/${name}/fullchain.pem" "/acme/live/${name}/privkey.pem" > "/tls/.staging/${name}.pem"
            chown 1000:1000 "/tls/.staging/${name}.pem"
            mv "/tls/.staging/${name}.pem" "/tls/certs/${name}.pem"
        done' sh "$@" || { err "Certificate promotion failed: $*"; return; }

}
tls-present () {

    docker-oneshot --user 1000:1000 --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls,readonly" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c 'for file in /tls/certs/*.pem; do test -s "${file}" && exit 0; done; exit 1' >/dev/null 2>&1

}
tls-prune () {

    docker-oneshot --user 1000:1000 --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c \
        'for file in /tls/certs/*.pem; do
            test -e "${file}" || continue
            name="${file##*/}"
            keep=""
            for wanted in "$@"; do test "${wanted}.pem" != "${name}" || keep=1; done
            test -n "${keep}" || rm -f -- "${file}"
        done' sh "$@" || { err "Certificate pruning failed"; return; }

}
tls-import () {

    local certificate="${1:-}" key="${2:-}" public="" private="" groups=""
    local -a names=()

    [[ -f "${certificate}" && -f "${key}" ]] || { err "Usage: infra tls import CERT KEY"; return; }
    need openssl || return

    public="$(openssl x509 -in "${certificate}" -pubkey -noout)" || { err "Unreadable certificate: ${certificate}"; return; }
    private="$(openssl pkey -in "${key}" -pubout)" || { err "Unreadable private key"; return; }
    [[ "${public}" == "${private}" ]] || { err "Certificate and key do not match"; return; }

    mapfile -t names < <(openssl x509 -in "${certificate}" -noout -text | grep -oE 'DNS:[^,[:space:]]+' | sed -e 's/^DNS://' -e 's/^\*\.//')
    (( ${#names[@]} > 0 )) || { err "The certificate names no DNS host"; return; }
    groups="$(tls-groups "${names[@]}")" || return
    [[ "${groups}" != *$'\n'* ]] || { err "The certificate spans several registrable domains; import one per domain"; return; }

    tls-volumes || return

    cat -- "${certificate}" "${key}" | docker-oneshot -i --user 1000:1000 --entrypoint sh \
        --mount "type=volume,source=${CONFIG[COMPOSE_PROJECT]}-tls,target=/tls" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c 'set -eu; umask 077; mkdir -p /tls/certs /tls/.staging; cat > "/tls/.staging/$1.pem"; mv "/tls/.staging/$1.pem" "/tls/certs/$1.pem"' sh "${groups%% *}" ||
        { err "Certificate import failed"; return; }

    out "${groups%% *}"

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
