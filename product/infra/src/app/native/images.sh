source-include module/docker.sh || return
source-include module/registry.sh || return

native-registry () {

    native-dispatch registry "$@"

}
native-registry-host () {

    registry-host

}
native-registry-reference () {

    registry-reference "$@"

}
native-registry-login () {

    local host=""

    cfg-require REGISTRY_USER REGISTRY_TOKEN || return
    host="$(registry-host)" || return

    docker-login "${host}" "${CONFIG[REGISTRY_USER]}" "${CONFIG[REGISTRY_TOKEN]}" || return
    ui-result registry-login true safe

}
native-registry-push () {

    registry-owns "${1:-}" || return

    docker-push "${1}"

}
native-registry-logout () {

    local host=""

    host="$(registry-host)" || return

    docker-logout "${host}"

}
native-image () {

    native-dispatch image "$@"

}
native-image-part () {

    [[ -n "${1:-}" && " ${CONFIG_PARTS[*]} " == *" ${1} "* ]] || { err "Unknown part: ${1:-} (expected ${CONFIG_PARTS[*]})"; return; }

}
native-image-env () {

    local name="${1}" build="" target=""

    build="${CONFIG[${name^^}_BUILD]:-}"

    while [[ "${build}" =~ \{([a-z0-9]+)\} ]]; do
        target="${BASH_REMATCH[1]}"
        build="${build//"{${target}}"/${CONFIG[${target^^}_URL]}}"
    done

    out "${build}"

}
native-image-available () {

    native-image-part "${1:-}" || return
    [[ "${TOOL_BUNDLED:-false}" != true ]] || return 1

    [[ -e "${TOOL_ROOT%/*/*}/${CONFIG[${1^^}_SOURCE]}" ]]

}
native-image-build () {

    local name="${1:-}" tag="${2:-}" root="${TOOL_ROOT%/*/*}" dockerfile="" line="" argument=""
    local -a arguments=()

    native-image-part "${name}" || return
    [[ "${TOOL_BUNDLED:-false}" != true ]] || { err "Image builds need the monorepo checkout"; return; }
    parse-image "${tag}" || { err "Invalid image tag: ${tag}"; return; }
    native-image-available "${name}" || { err "Part ${name} has no source at ${CONFIG[${name^^}_SOURCE]}; nothing to build"; return; }

    dockerfile="${TOOL_ROOT}/${MANIFEST[paths.templates]}/image/${CONFIG[${name^^}_DOCKERFILE]}.Dockerfile"
    [[ -f "${dockerfile}" ]] || { err "Missing image recipe: ${dockerfile}"; return; }

    while IFS= read -r line; do
        [[ "${line}" =~ ^ARG\ ([A-Z][A-Z0-9_]*)$ ]] || continue
        argument="${BASH_REMATCH[1]}"
        case "${argument}" in
            BUILD_ENV)
                arguments+=( --build-arg "BUILD_ENV=$(native-image-env "${name}")" )
            ;;
            *_IMAGE)
                cfg-has "IMAGE_${argument%_IMAGE}" || { err "${dockerfile##*/} needs IMAGE_${argument%_IMAGE} from Bash.toml"; return; }
                arguments+=( --build-arg "${argument}=${CONFIG[IMAGE_${argument%_IMAGE}]}" )
            ;;
            *)
                err "${dockerfile##*/} declares an argument the infrastructure does not fill: ${argument}"
                return
            ;;
        esac
    done < "${dockerfile}"

    docker-client build --tag "${tag}" --file "${dockerfile}" "${arguments[@]}" "${root}" || { err "Image build failed: ${name}"; return; }

}
native-image-reference () {

    local name="${1:-}" tag="${2:-}" build="" suffix=""

    native-image-part "${name}" || return
    build="$(native-image-env "${name}")" || return
    [[ -z "${build}" ]] || suffix="-$(printf '%s' "${build}" | fs-hash - | cut -c1-8)"

    registry-reference "${name}" "${tag}${suffix}"

}
native-image-inputs () {

    local name="${1:-}" build="" target="" key=""
    local -a keys=( PROJECT TLS_ENABLED HTTP_PORT HTTPS_PORT )

    native-image-part "${name}" || return
    build="${CONFIG[${name^^}_BUILD]:-}"

    while [[ "${build}" =~ \{([a-z0-9]+)\} ]]; do
        target="${BASH_REMATCH[1]}"
        build="${build//"{${target}}"/}"
        keys+=( "${target^^}_DOMAIN" )
    done

    for key in "${keys[@]}"; do
        out "${key}=${CONFIG[${key}]}"
    done

}
native-image-resolve () {

    local tag="${1:-}" name="" reference="" image="" host="" status=0

    [[ -n "${tag}" ]] || { err "Usage: infra image resolve TAG"; return; }

    if [[ -n "${CONFIG[REGISTRY_TOKEN]}" ]]; then
        host="$(registry-host)" || return
        docker-login "${host}" "${CONFIG[REGISTRY_USER]}" "${CONFIG[REGISTRY_TOKEN]}" || return
    fi

    while IFS= read -r name; do
        reference="$(native-image-reference "${name}" "${tag}")" || { status=1; break; }
        if image="$(docker-remote "${reference}")"; then out "${name^^}_IMAGE=${image}"
        else warn "No image ${reference}; ${name} keeps its live image or stays out of this release"
        fi
    done < <(native-routed)

    [[ -z "${host}" ]] || docker-logout "${host}" || warn "Registry logout failed: ${host}"

    return "${status}"

}
native-image-digest () {

    docker-digests "${1:-}"

}
native-image-remote () {

    docker-remote "${1:-}" || { err "Image not found in the registry: ${1:-}"; return; }

}
