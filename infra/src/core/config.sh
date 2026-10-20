declare -gA CONFIG=() CONFIG_SOURCE=() CONFIG_DEFAULTS=() MANIFEST=()
declare -ga CONFIG_KEYS=()

cfg-key () {

    [[ "${1:-}" =~ ^[A-Z][A-Z0-9_]*$ ]]

}
cfg-has () {

    cfg-key "${1:-}" && [[ -n "${CONFIG[${1}]+x}" ]]

}
cfg-set () {

    local key="${1:-}" value="${2-}" origin="${3:-derived}"

    cfg-key "${key}" || { err "Invalid setting name: ${key}"; return; }
    [[ -n "${CONFIG[${key}]+x}" ]] || CONFIG_KEYS+=( "${key}" )

    CONFIG["${key}"]="${value}"
    CONFIG_SOURCE["${key}"]="${origin}"

}
cfg-value () {

    local -n _value="${1}"
    local key="${2:-}"

    cfg-has "${key}" || { err "Unknown setting: ${key}"; return; }
    _value="${CONFIG[${key}]}"

}
cfg-show () {

    local key="${1:-}"

    cfg-has "${key}" || { err "Unknown setting: ${key}"; return; }

    if [[ -n "${CONFIG[${key}]}" ]] && log-secret "${key}"; then out '[redacted]'
    else out "${CONFIG[${key}]}"
    fi

}
cfg-load () {

    local file="${1}" policy="${2:-any}" origin="${3:-file}" key=""
    local -A parsed=()

    parse-pairs parsed "${file}" || return

    for key in "${!parsed[@]}"; do
        [[ "${policy}" != known ]] || cfg-has "${key}" || { err "Unknown setting in ${file}: ${key}"; return; }
    done

    for key in "${!parsed[@]}"; do
        cfg-set "${key}" "${parsed[${key}]}" "${origin}"
    done

}
cfg-environment () {

    local key=""

    for key in "$@"; do
        [[ -z "${!key+x}" ]] || cfg-set "${key}" "${!key}" process
    done

}
cfg-require () {

    local key="" failed=0

    for key in "$@"; do
        [[ -n "${CONFIG[${key}]:-}" ]] || { err "Missing setting: ${key}"; failed=1; }
    done

    (( failed == 0 ))

}
cfg-true () {

    [[ "${CONFIG[${1}]:-false}" == true ]]

}

manifest-load () {

    MANIFEST=()
    parse-pairs MANIFEST "${1}" toml

}
manifest-get () {

    [[ -n "${MANIFEST[${1:-}]+x}" ]] || { err "Manifest key required: ${1:-}"; return; }

    out "${MANIFEST[${1}]}"

}
