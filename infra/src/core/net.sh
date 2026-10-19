net-safe () {

    [[ "${1-}" != *$'\n'* && "${1-}" != *$'\r'* ]]

}
net-request () {

    local method="${1}" url="${2}" destination="${3}" header="${4:-}" credential="${5:-}" body="${6:-}" authority="${7:-}"
    local temporary="" status=0
    local -a arguments=( --fail --silent --show-error --connect-timeout 10 --max-time 180 --proto '=https' --proto-redir '=https' )

    [[ "${method}" =~ ^(GET|POST|PUT|PATCH|DELETE)$ ]] || { err "Unsupported HTTP method: ${method}"; return; }
    [[ "${url}" == https://* && "${url}" != *'@'* ]] || { err "HTTPS URL without credentials required"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }
    [[ -z "${header}" || "${header}" =~ ^[A-Za-z][A-Za-z0-9-]*$ ]] || { err "Invalid header name: ${header}"; return; }
    net-safe "${credential}" || { err "Credential must be a single line"; return; }
    need curl || return

    credential="${credential//\\/\\\\}"
    credential="${credential//\"/\\\"}"

    [[ -z "${body}" ]] || arguments+=( --header 'Content-Type: application/json' --data-binary "@${body}" )
    [[ -z "${authority}" ]] || arguments+=( --cacert "${authority}" )

    temporary="$(fs-temp-file)" || return

    if [[ -n "${header}" ]]; then
        printf 'header = "%s: %s"\n' "${header}" "${credential}" |
            curl "${arguments[@]}" --config - --request "${method}" --output "${temporary}" --url "${url}" || status=$?
    else
        curl "${arguments[@]}" --request "${method}" --output "${temporary}" --url "${url}" </dev/null || status=$?
    fi

    if (( status == 0 )); then fs-copy "${temporary}" "${destination}" || status=$?
    else err "${method} ${url%%\?*} failed; reconcile remote state before retrying a write"
    fi

    rm -f -- "${temporary}"
    return "${status}"

}
net-download () {

    local url="${1}" destination="${2}" expected="${3}" temporary="" actual="" status=0

    [[ "${expected}" =~ ^[a-f0-9]{64}$ ]] || { err "SHA-256 checksum required for ${url}"; return; }
    [[ "${url}" == https://* ]] || { err "HTTPS URL required: ${url}"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }
    need curl || return

    temporary="$(fs-temp-file)" || return

    if curl --fail --silent --show-error --location --max-redirs 3 --proto '=https' --proto-redir '=https' \
        --connect-timeout 10 --max-time 300 --output "${temporary}" --url "${url}"; then

        actual="$(fs-hash "${temporary}")" || status=$?

        if [[ "${actual}" == "${expected}" ]]; then fs-copy "${temporary}" "${destination}" 644 || status=$?
        else err "Checksum mismatch for ${url}" || status=$?
        fi

    else
        err "Download failed: ${url}" || status=$?
    fi

    rm -f -- "${temporary}"
    return "${status}"

}
net-status () {

    local url="${1}" expected="${2}" status=""

    shift 2
    [[ "${url}" == http://* || "${url}" == https://* ]] || { err "HTTP URL required: ${url}"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }

    status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 --noproxy '*' "$@" --url "${url}" 2>/dev/null)" || return 1

    [[ "${status}" == "${expected}" ]]

}
net-header () {

    local url="${1}" name="${2}" expected="${3}" headers="" line="" key="" value=""

    shift 3
    [[ "${url}" == http://* || "${url}" == https://* ]] || { err "HTTP URL required: ${url}"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }
    [[ "${name}" =~ ^[A-Za-z0-9-]+$ ]] || { err "Invalid header name: ${name}"; return; }

    headers="$(curl --fail --silent --max-time 5 --noproxy '*' --dump-header - --output /dev/null "$@" --url "${url}")" || return 1

    while IFS= read -r line; do

        line="${line%$'\r'}"
        key="${line%%:*}"
        [[ "${line}" == *:* && "${key,,}" == "${name,,}" ]] || continue

        parse-trim value "${line#*:}"
        [[ "${value}" == "${expected}" ]]
        return

    done <<< "${headers}"

    return 1

}
