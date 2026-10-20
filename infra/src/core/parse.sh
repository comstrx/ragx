parse-identifier () {

    [[ "${1:-}" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]]

}
parse-positive () {

    [[ "${1:-}" =~ ^[1-9][0-9]{0,8}$ ]]

}
parse-count () {

    [[ "${1:-}" =~ ^(0|[1-9][0-9]{0,8})$ ]]

}
parse-boolean () {

    [[ "${1:-}" == true || "${1:-}" == false ]]

}
parse-port () {

    [[ "${1:-}" =~ ^[1-9][0-9]{0,4}$ ]] && (( 10#${1} <= 65535 ))

}
parse-path () {

    [[ "${1:-}" =~ ^/[A-Za-z0-9/_.~-]*$ && "/${1}/" != */../* ]]

}
parse-host () {

    local host="${1:-}" label=""
    local -a labels=()

    (( ${#host} > 0 && ${#host} <= 253 )) || return 1
    [[ "${host}" != *. && "${host}" != .* && "${host}" != *..* ]] || return 1

    IFS=. read -r -a labels <<< "${host}"

    for label in "${labels[@]}"; do
        [[ "${label}" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || return 1
    done

    return 0

}
parse-address () {

    local address="${1:-}" octet=""
    local -a octets=()

    [[ "${address}" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    IFS=. read -r -a octets <<< "${address}"

    for octet in "${octets[@]}"; do
        (( 10#${octet} <= 255 )) || return 1
    done

    return 0

}
parse-cidr () {

    local address="${1%/*}" prefix="${1##*/}"

    [[ "${1:-}" == */* && "${prefix}" =~ ^[0-9]{1,3}$ ]] || return 1

    if [[ "${address}" == *:* ]]; then [[ "${address}" =~ ^[0-9A-Fa-f:]{2,39}$ ]] && (( 10#${prefix} <= 128 ))
    else parse-address "${address}" && (( 10#${prefix} <= 32 ))
    fi

}
parse-image () {

    local component='[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?'
    local segment='[a-z0-9]+(([._]|__|-+)[a-z0-9]+)*'
    local domain="(localhost|${component}(\.${component})+|${component}:[0-9]{1,5})(:[0-9]{1,5})?"
    local pattern="^((${domain})/)?${segment}(/${segment})*(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[a-f0-9]{64})?$"

    (( ${#1} <= 512 )) && [[ "${1:-}" =~ ${pattern} ]]

}
parse-pinned () {

    parse-image "${1:-}" && [[ "${1}" =~ @sha256:[a-f0-9]{64}$ ]]

}

parse-trim () {

    local -n _trimmed="${1}"
    local _value="${2-}"

    _value="${_value#"${_value%%[![:space:]]*}"}"
    _trimmed="${_value%"${_value##*[![:space:]]}"}"

}
parse-map () {

    local -n _mapped="${1}"
    local source="${2-}" pair="" key=""
    local -a pairs=()

    _mapped=()
    [[ -n "${source}" ]] || return 0

    IFS=, read -r -a pairs <<< "${source}"

    for pair in "${pairs[@]}"; do

        [[ "${pair}" == *=* ]] || { err "Expected key=value pairs: ${pair}"; return; }

        key="${pair%%=*}"
        parse-identifier "${key}" || { err "Invalid map key: ${key}"; return; }
        [[ -z "${_mapped[${key}]+x}" ]] || { err "Duplicate map key: ${key}"; return; }
        [[ -n "${pair#*=}" ]] || { err "Empty map value: ${key}"; return; }

        _mapped["${key}"]="${pair#*=}"

    done

}
parse-string () {

    local -n _decoded="${1}" _open="${4}"
    local value="${2-}" kind="${3:-env}" quote="" char="" tail="" escaped=0 index=0

    _decoded=""
    _open=false
    parse-trim value "${value}"
    quote="${value:0:1}"

    if [[ "${quote}" != "'" && "${quote}" != '"' ]]; then
        [[ "${value}" != *'#'* && "${value}" != *$'\n'* ]] || return 1
        _decoded="${value}"
        return 0
    fi

    for (( index = 1; index < ${#value}; index++ )); do

        char="${value:index:1}"

        if (( escaped )); then

            case "${char}" in
                n)              _decoded+=$'\n' ;;
                r)              _decoded+=$'\r' ;;
                t)              _decoded+=$'\t' ;;
                b)              _decoded+=$'\b' ;;
                f)              _decoded+=$'\f' ;;
                \\|\"|\'|\$)    _decoded+="${char}" ;;
                *)              return 1 ;;
            esac

            escaped=0
            continue

        fi

        if [[ "${char}" == \\ ]]; then

            if [[ "${quote}" == "'" && ( "${kind}" == toml || "${value:index+1:1}" != "'" ) ]]; then _decoded+="${char}"
            else escaped=1
            fi

            continue

        fi

        if [[ "${char}" == "${quote}" ]]; then
            parse-trim tail "${value:index+1}"
            [[ -z "${tail}" || "${tail}" == \#* ]] || return 1
            return 0
        fi

        _decoded+="${char}"

    done

    _open=true
    return 1

}
parse-pairs () {

    local -n _pairs="${1}"
    local file="${2}" kind="${3:-env}" line="" key="" value="" decoded="" section="" pending="" open=false number=0
    local -A seen=()

    [[ -f "${file}" && ! -L "${file}" ]] || { err "Regular file required: ${file}"; return; }
    (( $(wc -c < "${file}") <= 1048576 )) || { err "Configuration exceeds 1 MiB: ${file}"; return; }
    ! IFS= read -r -d '' decoded < "${file}" || { err "NUL bytes are forbidden: ${file}"; return; }

    decoded=""

    while IFS= read -r line || [[ -n "${line}" ]]; do

        number=$(( number + 1 ))
        line="${line%$'\r'}"

        if [[ -n "${pending}" ]]; then
            value+=$'\n'"${line}"
            key="${pending}"
        else

            parse-trim line "${line}"
            [[ -n "${line}" && "${line}" != \#* ]] || continue

            if [[ "${kind}" == toml && "${line}" =~ ^\[([a-z][a-z0-9_.-]*)\]$ ]]; then
                section="${BASH_REMATCH[1]}."
                continue
            fi

            [[ "${line}" == *=* ]] || { err "Invalid setting at ${file}:${number}"; return; }
            parse-trim key "${line%%=*}"
            parse-trim value "${line#*=}"

            if [[ "${kind}" == env ]]; then
                [[ "${key}" =~ ^[A-Z][A-Z0-9_]*$ ]] || { err "Invalid key at ${file}:${number}"; return; }
            else
                [[ "${key}" =~ ^[a-z][a-z0-9_-]*$ ]] || { err "Invalid key at ${file}:${number}"; return; }
                key="${section}${key}"
                [[ "${value}" == \"* || "${value}" == \'* || "${value}" =~ ^[0-9]+$ || "${value}" == true || "${value}" == false ]] || {
                    err "Unsupported manifest value type: ${key}"
                    return
                }
            fi

        fi

        if ! parse-string decoded "${value}" "${kind}" open; then
            [[ "${open}" == true && "${kind}" == env ]] || { err "Invalid value for ${key} at ${file}:${number}"; return; }
            pending="${key}"
            continue
        fi

        [[ -z "${seen[${key}]+x}" ]] || { err "Duplicate setting: ${key}"; return; }

        seen["${key}"]=1
        _pairs["${key}"]="${decoded}"
        pending=""

    done < "${file}"

    [[ -z "${pending}" ]] || { err "Unterminated value: ${pending}"; return; }

}

parse-url-component () {

    local LC_ALL=C value="${1-}" char="" code=0 index=0

    for (( index = 0; index < ${#value}; index++ )); do

        char="${value:index:1}"

        case "${char}" in
            [a-zA-Z0-9.~_-]) printf '%s' "${char}" ;;
            *)               printf -v code '%d' "'${char}"; printf '%%%02X' "${code}" ;;
        esac

    done

}
parse-json-string () {

    local value="${1-}"

    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    value="${value//$'\b'/\\b}"
    value="${value//$'\f'/\\f}"

    printf '"%s"' "${value}"

}
parse-env-string () {

    local value="${1-}" compose="${2:-false}"

    if [[ "${value}" == *\\ ]]; then
        [[ "${compose}" != true ]] || value="${value//\$/\$\$}"
        parse-json-string "${value}"
        return
    fi

    value="${value//\'/\\\'}"
    printf "'%s'" "${value}"

}
parse-xml-string () {

    local value="${1-}"

    value="${value//&/\&amp;}"
    value="${value//</\&lt;}"
    value="${value//>/\&gt;}"
    value="${value//\"/\&quot;}"
    value="${value//\'/\&apos;}"

    printf '%s' "${value}"

}
parse-content () {

    local text="${1-}" decoded=""

    if [[ "${text}" =~ ^[A-Za-z0-9+/]{8,}={0,2}$ ]] && (( ${#text} % 4 == 0 )) && decoded="$(printf '%s' "${text}" | openssl base64 -d -A 2>/dev/null | tr '\000' '\001')" && [[ -n "${decoded}" && "${decoded}" != *$'\001'* ]]; then
        printf '%s\n' "${decoded}"
        return
    fi

    printf '%s\n' "${text}"

}
