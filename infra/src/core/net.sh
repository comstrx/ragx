net-safe () {

    [[ "${1-}" != *$'\n'* && "${1-}" != *$'\r'* ]]

}
net-request () {

    local method="${1}" url="${2}" destination="${3}" header="${4:-}" credential="${5:-}" body="${6:-}" authority="${7:-}"
    local temporary="" status=0
    local -a arguments=( --disable --fail --silent --show-error --connect-timeout 10 --max-time 180 --proto '=https' --proto-redir '=https' )

    [[ "${method}" =~ ^(GET|POST|PUT|PATCH|DELETE)$ ]] || { err "Unsupported HTTP method: ${method}"; return; }
    [[ "${url}" == https://* && "${url}" != *'@'* && "${url}" != *[\"\\]* ]] || { err "HTTPS URL without credentials required"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }
    [[ -z "${header}" || "${header}" =~ ^[A-Za-z][A-Za-z0-9-]*$ ]] || { err "Invalid header name: ${header}"; return; }
    net-safe "${credential}" || { err "Credential must be a single line"; return; }
    need curl || return

    credential="${credential//\\/\\\\}"
    credential="${credential//\"/\\\"}"

    [[ "${method}" != GET ]] || arguments+=( --retry 3 --retry-connrefused --retry-max-time 60 )
    [[ -z "${body}" ]] || arguments+=( --header 'Content-Type: application/json' --data-binary "@${body}" )
    [[ -z "${authority}" ]] || arguments+=( --cacert "${authority}" )

    temporary="$(fs-temp-file)" || return

    {
        printf 'url = "%s"\n' "${url}"
        [[ -z "${header}" ]] || printf 'header = "%s: %s"\n' "${header}" "${credential}"
    } | curl "${arguments[@]}" --config - --request "${method}" --output "${temporary}" || status=$?

    if (( status == 0 )); then fs-copy "${temporary}" "${destination}" || status=$?
    else err "${method} to ${url%"${url#https://*/}"} failed; reconcile remote state before retrying a write"
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

    if curl --disable --fail --silent --show-error --location --max-redirs 3 --proto '=https' --proto-redir '=https' \
        --connect-timeout 10 --max-time 300 --retry 3 --retry-connrefused --output "${temporary}" --url "${url}"; then

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

    status="$(curl --disable --silent --output /dev/null --write-out '%{http_code}' --max-time 5 --noproxy '*' "$@" --url "${url}" 2>/dev/null)" || return 1

    [[ "${status}" == "${expected}" ]]

}
net-header () {

    local url="${1}" name="${2}" expected="${3}" headers=""

    shift 3
    [[ "${url}" == http://* || "${url}" == https://* ]] || { err "HTTP URL required: ${url}"; return; }
    net-safe "${url}" || { err "URL must be a single line"; return; }

    headers="$(curl --disable --fail --silent --max-time 5 --noproxy '*' --dump-header - --output /dev/null "$@" --url "${url}")" || return 1

    net-header-has "${headers}" "${name}" "${expected}"

}
net-header-has () {

    local headers="${1}" name="${2}" expected="${3}" line="" key="" value=""

    [[ "${name}" =~ ^[A-Za-z0-9-]+$ ]] || { err "Invalid header name: ${name}"; return; }

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
net-hmac () {

    local key="${1-}" file="${2}" hex="" pair="" inner="" outer="" digest="" index=0

    [[ -f "${file}" && ! -L "${file}" ]] || { err "Regular file required: ${file}"; return; }
    need od || return

    hex="$(printf '%s' "${key}" | od -An -v -tx1 | tr -d ' \n')" || return
    (( ${#hex} <= 128 )) || hex="$(printf '%s' "${key}" | fs-hash -)" || return

    while (( ${#hex} < 128 )); do
        hex+='00'
    done

    for (( index = 0; index < 128; index += 2 )); do
        pair="${hex:index:2}"
        printf -v inner '%s\\x%02x' "${inner}" "$(( 16#${pair} ^ 0x36 ))"
        printf -v outer '%s\\x%02x' "${outer}" "$(( 16#${pair} ^ 0x5c ))"
    done

    digest="$({ printf '%b' "${inner}"; cat -- "${file}"; } | fs-hash -)" || return
    inner=""

    for (( index = 0; index < 64; index += 2 )); do
        printf -v inner '%s\\x%s' "${inner}" "${digest:index:2}"
    done

    { printf '%b' "${outer}"; printf '%b' "${inner}"; } | fs-hash -

}
