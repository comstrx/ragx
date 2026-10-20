source-include module/docker.sh || return
source-include module/registry.sh || return

native-registry () {

    cli-dispatch native-registry "${1:-host}" 'host reference login push logout' "${@:2}"

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

    cli-dispatch native-image "${1:-digest}" 'build digest remote' "${@:2}"

}
native-image-build () {

    local component="${1:-}" tag="${2:-}" spec="${3:-}" root="${TOOL_ROOT%/*}" dockerfile="" build=""
    local -a arguments=()

    [[ "${component}" == api || "${component}" == web ]] || { err "Usage: image build api|web TAG [SPEC]"; return; }
    [[ "${TOOL_BUNDLED:-false}" != true ]] || { err "Image builds need the monorepo checkout"; return; }
    parse-image "${tag}" || { err "Invalid image tag: ${tag}"; return; }

    case "${component}" in
        api)
            arguments=( --build-arg "PYTHON_IMAGE=${CONFIG[IMAGE_PYTHON]}" --build-arg "UV_IMAGE=${CONFIG[IMAGE_UV]}" )
        ;;
        web)
            [[ "${spec}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { err "Usage: image build web TAG SPEC"; return; }
            [[ -z "${CONFIG[WEB_SPEC_VARIABLE]}" ]] || build="${CONFIG[WEB_SPEC_VARIABLE]}=${spec}"
            if [[ -n "${CONFIG[WEB_API_VARIABLE]}" ]]; then
                cfg-require API_HOST || return
                build+="${build:+ }${CONFIG[WEB_API_VARIABLE]}=${CONFIG[API_URL]}"
            fi
            arguments=( --build-arg "BUN_IMAGE=${CONFIG[IMAGE_BUN]}" --build-arg "NODE_IMAGE=${CONFIG[IMAGE_NODE]}" --build-arg "BUILD_ENV=${build}" )
        ;;
    esac

    dockerfile="${TOOL_ROOT}/${MANIFEST[paths.templates]}/image/${component}.Dockerfile"

    docker-client build --tag "${tag}" --file "${dockerfile}" "${arguments[@]}" "${root}" || { err "Image build failed: ${component}"; return; }

}
native-image-digest () {

    docker-digests "${1:-}"

}
native-image-remote () {

    docker-remote "${1:-}" || { err "Image not found in the registry: ${1:-}"; return; }

}
