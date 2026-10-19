haproxy-render () {

    local directory="${1}" route="" name="" host="" port="" path="" balance="" expect="" slot="" suffix="" certificate="/etc/haproxy-tls/site.pem"
    local hostnames="" routing="" backends="" binds="" candidate="    bind :8081" security="" redirect=""

    shift
    (( $# > 0 )) || { err "HAProxy needs at least one route"; return; }

    if cfg-true TLS_ENABLED; then

        [[ "${CONFIG[HTTPS_PORT]}" == 443 ]] || suffix=":${CONFIG[HTTPS_PORT]}"

        binds="    bind :8443 ssl crt ${certificate} strict-sni alpn h2,http/1.1"
        candidate="    bind :8444 ssl crt ${certificate} strict-sni alpn h2,http/1.1"
        redirect="    http-request redirect prefix https://%[req.hdr(host),lower,field(1,:)]${suffix} code 308 unless { ssl_fc } || { path_beg /.well-known/acme-challenge/ }"
        security="    http-after-response set-header Strict-Transport-Security \"max-age=63072000\" if { ssl_fc }"

        if cfg-true HTTP3_ENABLED; then
            binds+=$'\n'"    bind quic4@:8443 ssl crt ${certificate} strict-sni ssl-min-ver TLSv1.3 alpn h3"
            security+=$'\n'"    http-after-response set-header Alt-Svc 'h3=\":${CONFIG[HTTPS_PORT]}\"; ma=86400' if { ssl_fc }"
        fi

    fi

    for route in "$@"; do

        IFS='|' read -r name host port path balance expect <<< "${route}"

        [[ "${name}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { err "Invalid backend name: ${name}"; return; }
        parse-host "${host}" || { err "Invalid route host for ${name}: ${host}"; return; }
        parse-port "${port}" || { err "Invalid route port for ${name}: ${port}"; return; }
        parse-path "${path}" || { err "Invalid readiness path for ${name}: ${path}"; return; }
        [[ "${balance}" == roundrobin || "${balance}" == leastconn ]] || { err "Invalid balance for ${name}: ${balance}"; return; }
        [[ "${expect}" =~ ^[1-5][0-9]{2}(-[1-5][0-9]{2})?$ ]] || { err "Invalid readiness status for ${name}: ${expect}"; return; }

        hostnames+="${hostnames:+ }${host}"
        routing+="    use_backend ${name}_%[var(txn.slot)] if { req.hdr(host),lower,field(1,:) -m str ${host} }"$'\n'

        for slot in blue green; do
            backends+="$(haproxy-backend "${name}" "${slot}" "${host}" "${port}" "${path}" "${balance}" "${expect}")"$'\n\n'
        done

    done

    cfg-set HAPROXY_HOSTS "${hostnames}"
    cfg-set HAPROXY_BINDS "${binds}"
    cfg-set HAPROXY_CANDIDATE "${candidate}"
    cfg-set HAPROXY_REDIRECT "${redirect}"
    cfg-set HAPROXY_SECURITY "${security}"
    cfg-set HAPROXY_ROUTES "${routing}    default_backend unavailable"
    cfg-set HAPROXY_BACKENDS "${backends%$'\n'}"

    fs-dir "${directory}" 755 || return
    template-render "${MANIFEST[paths.templates]}/native/haproxy.cfg" "${directory}/haproxy.cfg" 644

}
haproxy-backend () {

    local name="${1}" slot="${2}" host="${3}" port="${4}" path="${5}" balance="${6}" expect="${7}"

    out "backend ${name}_${slot}" \
        "    balance ${balance}" \
        '    http-reuse safe' \
        '    option httpchk' \
        "    http-check send meth GET uri ${path} ver HTTP/1.1 hdr Host ${host}" \
        "    http-check expect status ${expect}" \
        "    default-server inter 2s fastinter 1s downinter 2s fall 3 rise 2 slowstart 10s maxconn ${CONFIG[BACKEND_MAXCONN]} maxqueue ${CONFIG[BACKEND_MAXCONN]} observe layer7 error-limit 10 on-error mark-down init-state fully-down" \
        "    server-template replica 1-32 ${name}-${slot}:${port} check resolvers docker resolve-prefer ipv4 init-addr none"

}
haproxy-check () {

    local directory="${1}" volume="${2}"

    docker-oneshot --user 1000:1000 --entrypoint haproxy \
        --mount "type=bind,source=${directory},target=/etc/haproxy,readonly" \
        --mount "type=volume,source=${volume},target=/etc/haproxy-tls,readonly" \
        -- "${CONFIG[IMAGE_HAPROXY]}" -c -q -f /etc/haproxy/haproxy.cfg || { err "HAProxy rejected ${directory}/haproxy.cfg"; return; }

}
haproxy-features () {

    local details=""

    details="$(docker-oneshot --entrypoint haproxy -- "${CONFIG[IMAGE_HAPROXY]}" -vv)" || { err "HAProxy build unreadable"; return; }

    [[ "${details}" == *+PROMEX* ]] || { err "HAProxy build lacks the Prometheus exporter"; return; }
    ! cfg-true HTTP3_ENABLED || [[ "${details}" == *+QUIC* ]] || { err "HAProxy build lacks QUIC; set HTTP3_ENABLED=false or change the image"; return; }

}

haproxy-runtime () {

    local container="${1}" instruction="${2}" output=""

    [[ -n "${container}" ]] || { err "Edge container not running"; return; }
    output="$(printf '%s\n' "${instruction}" | docker exec -i "${container}" nc -w 3 127.0.0.1 9999)" || { err "HAProxy runtime API unreachable"; return; }

    case "${output}" in
        *'Unknown command'*|*'not found'*|*"Can't "*|*'Permission denied'*|*'No such'*) err "HAProxy refused: ${instruction%% *}"; return ;;
    esac

    out "${output}"

}
haproxy-select () {

    local container="${1}" slot="${2}" release="${3}" file="${4}" selected=""

    [[ "${slot}" == blue || "${slot}" == green || "${slot}" == unavailable ]] || { err "Invalid slot: ${slot}"; return; }
    parse-identifier "${release}" || { err "Invalid release: ${release}"; return; }

    haproxy-runtime "${container}" "set map /etc/haproxy/active.map active ${slot}:${release}" >/dev/null || return
    selected="$(haproxy-runtime "${container}" 'show map /etc/haproxy/active.map')" || return
    [[ "${selected}" == *"active ${slot}:${release}"* ]] || { err "HAProxy did not apply ${slot}:${release}"; return; }

    printf 'active %s:%s\n' "${slot}" "${release}" | fs-write "${file}" 644

}
haproxy-stats () {

    haproxy-runtime "${1}" 'show stat'

}
haproxy-field () {

    local stats="${1}" backend="${2}" server="${3}" column="${4}" line=""
    local -a fields=()

    while IFS= read -r line; do
        IFS=, read -r -a fields <<< "${line}"
        [[ "${fields[0]:-}" == "${backend}" && "${fields[1]:-}" == "${server}" ]] || continue
        out "${fields[${column}]:-}"
        return
    done <<< "${stats}"

    return 1

}
haproxy-up () {

    local stats="${1}" backend="${2}" line="" count=0
    local -a fields=()

    while IFS= read -r line; do
        IFS=, read -r -a fields <<< "${line}"
        [[ "${fields[0]:-}" == "${backend}" && "${fields[1]:-}" == replica* && "${fields[17]:-}" == UP ]] || continue
        count=$(( count + 1 ))
    done <<< "${stats}"

    out "${count}"

}
haproxy-idle () {

    local container="${1}" backend="${2}" server="${3:-BACKEND}" stats="" sessions=""

    stats="$(haproxy-stats "${container}")" || return
    sessions="$(haproxy-field "${stats}" "${backend}" "${server}" 4)" || { err "Unknown HAProxy server: ${backend}/${server}"; return; }

    [[ "${sessions}" == 0 ]]

}
haproxy-server () {

    local stats="${1}" backend="${2}" address="${3}" line=""
    local -a fields=()

    while IFS= read -r line; do
        IFS=, read -r -a fields <<< "${line}"
        [[ "${fields[0]:-}" == "${backend}" && "${fields[1]:-}" == replica* && "${line}" == *",${address}:"* ]] || continue
        out "${fields[1]}"
        return
    done <<< "${stats}"

    return 1

}
haproxy-state () {

    local container="${1}" backend="${2}" server="${3}" state="${4}"

    [[ "${state}" == ready || "${state}" == drain || "${state}" == maint ]] || { err "Invalid server state: ${state}"; return; }

    haproxy-runtime "${container}" "set server ${backend}/${server} state ${state}" >/dev/null

}
