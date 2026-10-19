docker-ready () {

    need docker || return

    docker info >/dev/null 2>&1 || { err "Docker daemon unreachable"; return; }

}
docker-versions () {

    local engine="" compose=""

    engine="$(docker version --format '{{.Server.Version}}')" || { err "Docker engine version unreadable"; return; }
    compose="$(docker compose version --short)" || { err "Docker Compose version unreadable"; return; }

    [[ "${engine}" == "${MANIFEST[tools.docker]}" ]] || { err "Docker ${engine} differs from Bash.toml ${MANIFEST[tools.docker]}"; return; }
    [[ "${compose#v}" == "${MANIFEST[tools.compose]}" ]] || { err "Compose ${compose} differs from Bash.toml ${MANIFEST[tools.compose]}"; return; }

}
docker-rootless () {

    local options=""

    options="$(docker info --format '{{json .SecurityOptions}}' 2>/dev/null)" || return 1

    [[ "${options}" == *rootless* ]]

}
docker-endpoint () {

    local context="" endpoint=""

    if [[ -n "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]]; then
        out "${DOCKER_HOST}"
        return
    fi

    context="$(docker context show)" || { err "Docker context unreadable"; return; }
    endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}' "${context}")" || { err "Docker endpoint unreadable"; return; }

    out "${endpoint}"

}
docker-socket () {

    local endpoint=""

    endpoint="$(docker-endpoint)" || return
    [[ "${endpoint}" == unix://* ]] || { err "A local Unix Docker socket is required: ${endpoint}"; return; }

    out "${endpoint#unix://}"

}

docker-compose () {

    local project="${1:-}"

    shift
    parse-identifier "${project}" || { err "Invalid Compose project: ${project}"; return; }

    run-timeout 600 env COMPOSE_DISABLE_ENV_FILE=true COMPOSE_PARALLEL_LIMIT=4 \
        docker compose --ansi never --project-name "${project}" "$@"

}
docker-client () {

    local endpoint="" directory="${CONFIG[STATE_ROOT]}/registry"

    endpoint="$(docker-endpoint)" || return
    fs-dir "${directory}" || return

    env -u DOCKER_CONTEXT -u DOCKER_CONFIG docker --host "${endpoint}" --config "${directory}" "$@"

}
docker-login () {

    local host="${1}" user="${2}" credential="${3}"

    printf '%s\n' "${credential}" | docker-client login "${host}" --username "${user}" --password-stdin >/dev/null || { err "Registry login failed: ${host}"; return; }

}
docker-logout () {

    docker-client logout "${1}" >/dev/null

}
docker-pull () {

    parse-image "${1:-}" || { err "Invalid image reference: ${1:-}"; return; }

    docker-client pull --quiet "${1}" >/dev/null || { err "Image pull failed: ${1}"; return; }

}
docker-push () {

    parse-image "${1:-}" || { err "Invalid image reference: ${1:-}"; return; }

    docker-client push --quiet "${1}" >/dev/null || { err "Image push failed: ${1}"; return; }

}
docker-present () {

    docker image inspect "${1}" >/dev/null 2>&1

}
docker-digests () {

    docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "${1}"

}

docker-health () {

    local state=""

    state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${1}" 2>/dev/null)" || return 1

    [[ "${state}" == healthy ]]

}
docker-inspect () {

    docker inspect --format "${2}" "${1}"

}
docker-network () {

    local name="${1}" owner="${2}" mode="${3:-bridge}" label=""
    local -a arguments=( network create --label "io.infra.owner=${owner}" )

    if docker network inspect "${name}" >/dev/null 2>&1; then
        label="$(docker network inspect --format '{{index .Labels "io.infra.owner"}}' "${name}")" || return
        [[ "${label}" == "${owner}" ]] || { err "Network ${name} belongs to ${label:-another owner}"; return; }
        return 0
    fi

    [[ "${mode}" != internal ]] || arguments+=( --internal )

    docker "${arguments[@]}" "${name}" >/dev/null || { err "Network creation failed: ${name}"; return; }

}
docker-volume () {

    local name="${1}" owner="${2}" uid="${3:-}" image="${4:-}" label=""

    if docker volume inspect "${name}" >/dev/null 2>&1; then
        label="$(docker volume inspect --format '{{index .Labels "io.infra.owner"}}' "${name}")" || return
        [[ "${label}" == "${owner}" ]] || { err "Volume ${name} belongs to ${label:-another owner}"; return; }
        return 0
    fi

    docker volume create --label "io.infra.owner=${owner}" "${name}" >/dev/null || { err "Volume creation failed: ${name}"; return; }
    [[ -n "${uid}" ]] || return 0

    docker-oneshot --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --entrypoint sh \
        --mount "type=volume,source=${name},target=/volume" -- "${image}" \
        -c 'chown "$1:$1" /volume && chmod 700 /volume' volume "${uid}" || { err "Volume ownership failed: ${name}"; return; }

}
docker-oneshot () {

    local argument="" network=false
    local -a flags=()

    while (( $# > 0 )) && [[ "${1}" != -- ]]; do
        [[ "${1}" != --network ]] || network=true
        flags+=( "${1}" )
        shift
    done

    [[ "${1:-}" == -- && -n "${2:-}" ]] || { err "Usage: docker-oneshot [FLAGS] -- IMAGE [ARGS]"; return; }
    shift
    argument="${1}"
    shift

    [[ "${network}" == true ]] || flags+=( --network none )

    docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 \
        --memory 128m --cpus 0.5 "${flags[@]}" "${argument}" "$@"

}
docker-memory () {

    local exclude="${1}" total="" reserved=0 ids="" project="" limit=""
    local -a containers=()

    total="$(docker info --format '{{.MemTotal}}')" || { err "Docker memory unreadable"; return; }
    ids="$(docker ps -q)" || return

    while IFS= read -r project; do
        [[ -z "${project}" ]] || containers+=( "${project}" )
    done <<< "${ids}"

    if (( ${#containers[@]} > 0 )); then

        while IFS='|' read -r project limit; do
            [[ "${limit}" =~ ^[0-9]+$ ]] || { err "Unreadable container memory limit"; return; }
            [[ "${project}" == "${exclude}" ]] || reserved=$(( reserved + limit ))
        done < <(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{.HostConfig.Memory}}' "${containers[@]}")

    fi

    out "$(( total - reserved ))"

}

docker-install () {

    local directory="" architecture="" name="" status=0
    local -A system=()
    local -a packages=()

    docker-ready 2>/dev/null && { docker-versions; return; }

    parse-pairs system /etc/os-release || return
    [[ "${system[ID]:-}" == ubuntu && "${system[VERSION_ID]:-}" == 24.04 ]] || { err "The pinned installer covers Ubuntu 24.04; provision Docker ${MANIFEST[tools.docker]} first"; return; }
    need-all apt-get dpkg curl || return

    architecture="$(dpkg --print-architecture)" || return
    [[ "${architecture}" == amd64 ]] || { err "Pinned package checksums cover amd64 only"; return; }
    ! has docker || { err "An existing Docker client needs an explicit maintenance plan"; return; }
    ! dpkg-query -W docker.io containerd >/dev/null 2>&1 || { err "An existing container runtime needs an explicit maintenance plan"; return; }

    directory="$(fs-temp)" || return

    for name in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; do
        net-download "https://download.docker.com/linux/ubuntu/dists/noble/pool/stable/amd64/${MANIFEST[packages.${name//./_}_file]}" \
            "${directory}/${name}.deb" "${MANIFEST[packages.${name//./_}_sha256]}" || { status=1; break; }
        packages+=( "${directory}/${name}.deb" )
    done

    (( status != 0 )) || run-sudo apt-get install -y --no-install-recommends -- "${packages[@]}" || status=$?
    rm -rf -- "${directory}"
    (( status == 0 )) || return "${status}"

    run-sudo systemctl enable --now docker || return
    docker-versions

}
