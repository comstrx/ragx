registry-host () {

    case "${CONFIG[REGISTRY_DRIVER]}" in
        ghcr)      out ghcr.io ;;
        dockerhub) out docker.io ;;
        *)         err "Unsupported REGISTRY_DRIVER: ${CONFIG[REGISTRY_DRIVER]}"; return ;;
    esac

}
registry-reference () {

    local component="${1:-}" tag="${2:-}" host=""

    cfg-require PROJECT REGISTRY_NAMESPACE || return
    parse-identifier "${component}" || { err "Invalid image component: ${component}"; return; }
    [[ "${tag}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || { err "Invalid image tag: ${tag}"; return; }
    [[ "${CONFIG[REGISTRY_NAMESPACE]}" =~ ^[a-z0-9]+([._-][a-z0-9]+)*$ ]] || { err "Invalid REGISTRY_NAMESPACE"; return; }

    host="$(registry-host)" || return

    out "${host}/${CONFIG[REGISTRY_NAMESPACE]}/${CONFIG[PROJECT]}-${component}:${tag}"

}
registry-owns () {

    local host=""

    host="$(registry-host)" || return

    [[ "${1:-}" == "${host}/${CONFIG[REGISTRY_NAMESPACE]}/"* ]] || { err "Image outside ${host}/${CONFIG[REGISTRY_NAMESPACE]}: ${1:-}"; return; }

}
