haproxy-render () {

    local directory="${1}" route="" name="" listed="" port="" path="" ready="" balance="" expect="" limit="" kind="" slot="" domain="" match="" host=""
    local select="" routing="" backends=""
    local -a ordered=() list=() limits=()

    shift
    (( $# > 0 )) || { err "HAProxy needs at least one route"; return; }

    mapfile -t ordered < <(haproxy-order "$@")
    haproxy-protocols || return
    haproxy-client || return

    for route in "${ordered[@]}"; do

        IFS='|' read -r name listed port path ready balance expect limit kind <<< "${route}"
        read -r -a list <<< "${listed}"

        [[ "${name}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { err "Invalid backend name: ${name}"; return; }
        (( ${#list[@]} > 0 )) || cfg-true HAPROXY_DOMAINS || { err "Route ${name} needs a domain"; return; }
        parse-port "${port}" || { err "Invalid route port for ${name}: ${port}"; return; }
        parse-path "${path}" && [[ "${path}" == / || "${path}" != */ ]] || { err "Invalid route path for ${name}: ${path}"; return; }
        parse-path "${ready}" || { err "Invalid readiness path for ${name}: ${ready}"; return; }
        [[ "${balance}" == roundrobin || "${balance}" == leastconn ]] || { err "Invalid balance for ${name}: ${balance}"; return; }
        [[ "${expect}" =~ ^[1-5][0-9]{2}(-[1-5][0-9]{2})?$ ]] || { err "Invalid readiness status for ${name}: ${expect}"; return; }
        [[ "${kind:-slot}" == slot || "${kind}" == static ]] || { err "Invalid route kind for ${name}: ${kind}"; return; }

        for domain in "${list[@]}"; do
            parse-host "${domain}" || { err "Invalid route domain for ${name}: ${domain}"; return; }
        done

        host="${list[0]:-localhost}"
        [[ -z "${limit}" ]] || limits+=( "${name}=${limit}" )

        if (( ${#list[@]} > 0 )); then

            match="part_${name}_host"
            select+="    acl part_${name}_host req.hdr(host),lower,field(1,:) -m str ${list[*]}"$'\n'

            if [[ "${path}" != / ]]; then
                match+=" part_${name}_path"
                select+="    acl part_${name}_path path ${path}"$'\n'"    acl part_${name}_path path_beg ${path}/"$'\n'
            fi

            select+="    http-request set-var(txn.part) str(${name}) if !{ var(txn.part) -m found } ${match}"$'\n'

        fi

        if [[ "${kind}" == static ]]; then
            routing+="    use_backend ${name} if { var(txn.part) -m str ${name} }"$'\n'
            backends+="$(haproxy-backend "${name}" "" "${host}" "${port}" "${ready}" "${balance}" "${expect}")"$'\n\n'
            continue
        fi

        routing+="    use_backend ${name}_%[var(txn.slot)] if { var(txn.part) -m str ${name} }"$'\n'

        for slot in blue green; do
            backends+="$(haproxy-backend "${name}" "${slot}" "${host}" "${port}" "${ready}" "${balance}" "${expect}")"$'\n\n'
        done

    done

    haproxy-limits "${limits[@]}" || return

    ! cfg-true HAPROXY_DOMAINS || select+="    http-request set-var(txn.part) req.hdr(host),lower,field(1,:),map_str(/etc/haproxy/domains.map) if !{ var(txn.part) -m found }"$'\n'

    cfg-set HAPROXY_SELECT "${select%$'\n'}"
    cfg-set HAPROXY_ROUTES "${routing}    default_backend unavailable"
    cfg-set HAPROXY_BACKENDS "${backends}${CONFIG[HAPROXY_TABLES]}"

    fs-dir "${directory}" 755 || return
    template-render "${MANIFEST[paths.templates]}/native/haproxy.cfg" "${directory}/haproxy.cfg" 644

}
haproxy-order () {

    local route="" path="" index=0

    for route in "$@"; do
        IFS='|' read -r _ _ _ path _ <<< "${route}"
        printf '%05d\t%05d\t%s\n' "$(( 10000 - ${#path} ))" "${index}" "${route}"
        index=$(( index + 1 ))
    done | LC_ALL=C sort | cut -f3-

}
haproxy-protocols () {

    local tls="ssl crt /etc/haproxy-tls/certs/ strict-sni alpn h2,http/1.1" relay="mode 666 accept-proxy" suffix="" binds="    bind :8080"
    local candidate="    bind :8081" security="" redirect=""

    [[ -z "${CONFIG[EDGE_SOCKETS]}" ]] || binds="    bind unix@/sockets/http.sock ${relay}"

    if cfg-true TLS_ENABLED; then

        [[ "${CONFIG[HTTPS_PORT]}" == 443 ]] || suffix=":${CONFIG[HTTPS_PORT]}"

        if [[ -n "${CONFIG[EDGE_SOCKETS]}" ]]; then binds+=$'\n'"    bind unix@/sockets/https.sock ${relay} ${tls}"
        else binds+=$'\n'"    bind :8443 ${tls}"
        fi

        candidate="    bind :8444 ${tls}"
        redirect="    http-request redirect prefix https://%[req.hdr(host),lower,field(1,:)]${suffix} code 308 unless { ssl_fc } || { path_beg /.well-known/acme-challenge/ }"
        security="    http-after-response set-header Strict-Transport-Security \"max-age=63072000\" if { ssl_fc }"

        if haproxy-quic; then
            binds+=$'\n'"    bind quic4@:8443 ssl crt /etc/haproxy-tls/certs/ strict-sni ssl-min-ver TLSv1.3 alpn h3"
            security+=$'\n'"    http-after-response set-header Alt-Svc 'h3=\":${CONFIG[HTTPS_PORT]}\"; ma=86400' if { ssl_fc }"
        fi

    fi

    cfg-set HAPROXY_BINDS "${binds}"
    cfg-set HAPROXY_CANDIDATE "${candidate}"
    cfg-set HAPROXY_REDIRECT "${redirect}"
    cfg-set HAPROXY_SECURITY "${security}"

}
haproxy-quic () {

    cfg-true TLS_ENABLED && cfg-true HTTP3_ENABLED && [[ -z "${CONFIG[EDGE_SOCKETS]}" ]]

}
haproxy-client () {

    local header="${CONFIG[TRUSTED_HEADER]}" range="" rules="" line=""
    local -a ranges=()

    read -r -a ranges <<< "${CONFIG[TRUSTED_RANGES]:-}"

    for range in "${ranges[@]}"; do
        parse-cidr "${range}" || { err "Invalid trusted range: ${range}"; return; }
        line+=" ${range}"
        (( ${#line} < 160 )) || { rules+="    acl trusted src${line}"$'\n'; line=""; }
    done

    [[ -z "${line}" ]] || rules+="    acl trusted src${line}"$'\n'
    [[ -z "${rules}" ]] || rules+="    http-request set-src req.hdr_ip(${header},-1) if trusted { req.hdr(${header}) -m found }"

    cfg-set HAPROXY_CLIENT "${rules}"

}
haproxy-limits () {

    local exempt='unless { path_beg /.well-known/acme-challenge/ }' rules="" tables="" rule="" name="" prefix="" window="" count="" seconds="" index=0
    local -a paths=()

    if [[ -n "${CONFIG[RATE_LIMIT_GLOBAL]}" ]]; then
        window="$(haproxy-rate "${CONFIG[RATE_LIMIT_GLOBAL]}")" || return
        read -r count seconds <<< "${window}"
        tables+="$(haproxy-table limit_global 'integer size 1' "${seconds}")"$'\n\n'
        rules+="    http-request track-sc0 int(1) table limit_global ${exempt}"$'\n'
        rules+="    http-request deny deny_status 429 hdr Retry-After ${seconds} if { sc_http_req_rate(0) gt ${count} }"$'\n'
    fi

    for rule in "$@"; do
        name="${rule%%=*}"
        window="$(haproxy-rate "${rule#*=}")" || return
        read -r count seconds <<< "${window}"
        tables+="$(haproxy-table "limit_part_${name}" 'ipv6 size 1m' "${seconds}")"$'\n\n'
        rules+="    http-request track-sc1 src table limit_part_${name} if { var(txn.part) -m str ${name} } !{ path_beg /.well-known/acme-challenge/ }"$'\n'
        rules+="    http-request deny deny_status 429 hdr Retry-After ${seconds} if { var(txn.part) -m str ${name} } { sc_http_req_rate(1) gt ${count} }"$'\n'
    done

    if [[ -n "${CONFIG[RATE_LIMIT_IP]}" ]]; then
        window="$(haproxy-rate "${CONFIG[RATE_LIMIT_IP]}")" || return
        read -r count seconds <<< "${window}"
        tables+="$(haproxy-table limit_ip 'ipv6 size 1m' "${seconds}")"$'\n\n'
        rules+="    http-request track-sc2 src table limit_ip ${exempt}"$'\n'
        rules+="    http-request deny deny_status 429 hdr Retry-After ${seconds} if { sc_http_req_rate(2) gt ${count} }"$'\n'
    fi

    [[ -z "${CONFIG[RATE_LIMIT_PATHS]}" ]] || IFS=, read -r -a paths <<< "${CONFIG[RATE_LIMIT_PATHS]}"

    for rule in "${paths[@]}"; do
        index=$(( index + 1 ))
        prefix="${rule%%=*}"
        window="$(haproxy-rate "${rule#*=}")" || return
        read -r count seconds <<< "${window}"
        tables+="$(haproxy-table "limit_path_${index}" 'ipv6 size 1m' "${seconds}")"$'\n\n'
        rules+="    http-request track-sc3 src table limit_path_${index} if { path_beg ${prefix} }"$'\n'
        rules+="    http-request deny deny_status 429 hdr Retry-After ${seconds} if { path_beg ${prefix} } { sc_http_req_rate(3) gt ${count} }"$'\n'
    done

    cfg-set HAPROXY_LIMITS "${rules%$'\n'}"
    cfg-set HAPROXY_TABLES "${tables}"

}
haproxy-rate () {

    local rate="${1}" count="" amount="" seconds=""

    [[ "${rate}" =~ ^([1-9][0-9]*)/([1-9][0-9]*)([smh])$ ]] || { err "Invalid rate: ${rate}"; return; }
    count="${BASH_REMATCH[1]}"
    amount="${BASH_REMATCH[2]}"

    case "${BASH_REMATCH[3]}" in
        s) seconds="${amount}" ;;
        m) seconds=$(( amount * 60 )) ;;
        h) seconds=$(( amount * 3600 )) ;;
    esac

    out "${count} ${seconds}"

}
haproxy-table () {

    out "backend ${1}" "    stick-table type ${2} expire $(( ${3} * 2 ))s store http_req_rate(${3}s)"

}
haproxy-backend () {

    local name="${1}" slot="${2}" host="${3}" port="${4}" ready="${5}" balance="${6}" expect="${7}" target="${1}" slots="1-32"

    [[ -z "${slot}" ]] || target="${name}-${slot}"
    [[ -n "${slot}" ]] || slots="1-1"

    out "backend ${name}${slot:+_${slot}}" \
        "    balance ${balance}" \
        '    http-reuse safe' \
        '    option httpchk' \
        "    http-check send meth GET uri ${ready} ver HTTP/1.1 hdr Host ${host}" \
        "    http-check expect status ${expect}" \
        "    default-server inter 2s fastinter 1s downinter 2s fall 3 rise 2 slowstart 10s maxconn ${CONFIG[BACKEND_MAXCONN]} maxqueue ${CONFIG[BACKEND_MAXCONN]} observe layer7 error-limit 10 on-error mark-down init-state fully-down" \
        "    server-template replica ${slots} ${target}:${port} check resolvers docker resolve-prefer ipv4 init-addr none"

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
    ! haproxy-quic || [[ "${details}" == *+QUIC* ]] || { err "HAProxy build lacks QUIC; set HTTP3_ENABLED=false or change the image"; return; }

}

haproxy-runtime () {

    local container="${1}" instruction="${2}" output=""

    [[ -n "${container}" ]] || { err "Edge container not running"; return; }
    output="$(printf '%s\n' "${instruction}" | docker exec -i "${container}" nc -w 3 127.0.0.1 9999)" || { err "HAProxy runtime API unreachable"; return; }

    case "${output%%$'\n'*}" in
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
