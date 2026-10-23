rabbitmq-render () {

    cfg-set RABBITMQ_DEFAULT_USER "${CONFIG[RABBIT_USER]}"
    cfg-set RABBITMQ_DEFAULT_PASS "${CONFIG[RABBIT_PASSWORD]}"

    template-compose-env "${1}/rabbitmq.env" RABBITMQ_DEFAULT_USER RABBITMQ_DEFAULT_PASS

}
rabbitmq-bytes () {

    local hex="${1}" escaped=""

    while [[ -n "${hex}" ]]; do
        escaped+="\\x${hex:0:2}"
        hex="${hex:2}"
    done

    printf '%b' "${escaped}"

}
rabbitmq-hash () {

    local password="${1}" salt="" digest=""

    need openssl || return
    salt="$(openssl rand -hex 4)" || return
    digest="$( { rabbitmq-bytes "${salt}"; printf '%s' "${password}"; } | openssl dgst -sha256 -binary | od -An -tx1 | tr -d ' \n')" || return

    rabbitmq-bytes "${salt}${digest}" | openssl base64 -A

}
rabbitmq-identity () {

    local user="${1}" name="${CONFIG[RABBIT_USER]}" hash=""

    shift
    parse-identifier "${user}" || { err "Invalid RabbitMQ user: ${user}"; return; }
    parse-identifier "${name}" || { err "Invalid RabbitMQ user: ${name}"; return; }
    need jq || return
    hash="$(rabbitmq-hash "${CONFIG[RABBIT_PASSWORD]}")" || return

    jq -cn --arg name "${name}" --arg hash "${hash}" '{users: [{name: $name, password_hash: $hash, hashing_algorithm: "rabbit_password_hashing_sha256", tags: ["administrator"]}],
        permissions: [{user: $name, vhost: "/", configure: ".*", write: ".*", read: ".*"}]}' |
        "$@" sh -c 'cat > /tmp/identity.json && rabbitmqctl -q import_definitions /tmp/identity.json; status=$?; rm -f /tmp/identity.json; exit "$status"' >/dev/null ||
        { err "RabbitMQ refused the new credentials; the previous ones stay"; return; }

    run-until 30 1 rabbitmq-applied "${name}" "${hash}" "$@" || { err "RabbitMQ did not apply the new credentials"; return; }

    if [[ "${user}" != "${name}" ]]; then "$@" rabbitmqctl -q delete_user "${user}" >/dev/null || { err "RabbitMQ kept the previous user ${user}"; return; }
    else "$@" rabbitmqctl -q close_all_user_connections "${name}" 'credentials changed' >/dev/null || { err "RabbitMQ kept the connections of ${name}"; return; }
    fi

}
rabbitmq-applied () {

    local name="${1}" hash="${2}" exported=""

    shift 2
    exported="$("$@" rabbitmqctl -q export_definitions - --format json 2>/dev/null)" || return 1

    [[ "$(jq -r --arg name "${name}" '.users[] | select(.name == $name) | .password_hash' <<< "${exported}")" == "${hash}" ]]

}
rabbitmq-files () {

    out rabbitmq.env

}
