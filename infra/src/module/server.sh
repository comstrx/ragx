#!/usr/bin/env bash

## any linux over ssh — the standard road: credentials in, platform out

server_host () {

    [[ -n "${SSH_HOST}" ]] || die "Missing SSH_HOST — the address of the box this stack lives on"

    printf '%s' "${SSH_HOST}"

}
server_path () {

    local path="${SERVER_PATH}" root="" ok=0

    for root in ${SERVER_ALLOWED_ROOTS}; do

        [[ "${path}" != "${root}"/*/* ]] || ok=1

    done

    (( ok )) || die "Refusing SERVER_PATH '${path}' — use a dedicated directory two levels under one of: ${SERVER_ALLOWED_ROOTS}"

    printf '%s' "${path}"

}
server_session () {

    local tool="${1:?Missing tool}" flag="${2:?Missing port flag}" password="" options=()

    shift 2

    password="$(secret_get SSH_PASSWORD)"

    if [[ -n "${SSH_HOST_KEY}" ]]; then

        ensure_dir "${BUILD_DIR}"
        printf '%s\n' "${SSH_HOST_KEY}" > "${BUILD_DIR}/known_hosts"

        options=( -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${BUILD_DIR}/known_hosts" "${flag}" "${SSH_PORT}" )

    else

        options=( -o StrictHostKeyChecking=accept-new "${flag}" "${SSH_PORT}" )

    fi

    options+=( -o ConnectTimeout="${SSH_CONNECT_TIMEOUT}" -o ServerAliveInterval="${SSH_ALIVE_INTERVAL}" -o ServerAliveCountMax="${SSH_ALIVE_COUNT}" )
    [[ -z "${SSH_KEY}" ]] || options+=( -i "${SSH_KEY}" )

    if [[ -n "${password}" ]]; then

        ensure sshpass

        SSHPASS="${password}" sshpass -e "${tool}" "${options[@]}" "$@"

    else

        "${tool}" "${options[@]}" "$@"

    fi

}
## true when this bundle runs on the box itself, or no box is named at all — the verbs then act locally instead of over ssh
server_here () {

    [[ -z "${SSH_HOST}" || "$(dirname -- "${INFRA_BIN}")" == "${SERVER_PATH}" ]]

}
## run a command on the server over ssh
server_run () {

    server_session ssh -p "${SSH_USER}@$(server_host)" "$@"

}
## run a command on the server with a terminal attached
server_tty () {

    server_session ssh -p -t "${SSH_USER}@$(server_host)" "$@"

}
## hand a verb to the bundle on the box — the same release, config and secrets it runs with
server_forward () {

    local path=""

    path="$(server_path)"

    if [[ -t 0 && -t 1 ]]; then

        server_tty "cd '${path}' && ./infra --config .env -s ${STACK} -y$(server_overrides) $(printf '%q ' "$@")"

    else

        server_run "cd '${path}' && ./infra --config .env -s ${STACK} -y$(server_overrides) $(printf '%q ' "$@")"

    fi

}
## copy a local file onto the server
server_copy () {

    local source="${1:?Usage: server copy <source> <destination>}" destination="${2:?Missing destination}"

    server_session scp -P -r "${source}" "${SSH_USER}@$(server_host):${destination}"

}
## block until the server accepts ssh — a freshly built box needs a minute to boot
server_wait () {

    local waited=0 host=""

    host="$(server_host)"

    while (( waited < SERVER_WAIT )); do

        server_run true >/dev/null 2>&1 && return 0
        sleep "${SERVER_POLL}"
        waited=$(( waited + SERVER_POLL ))

    done

    die "Server ${host} never accepted ssh within ${SERVER_WAIT}s"

}
## true when the stack already runs on the box — the converge check
server_ready () {

    server_run "test -f '${SERVER_PATH}/stack/compose.yaml' && cd '${SERVER_PATH}/stack' && [ -n \"\$(docker compose ps -q api 2>/dev/null)\" ]" 2>/dev/null

}
server_overrides () {

    local key="" out="" keys=()

    read -ra keys <<< "${INFRA_FLAGS:-}"

    for key in "${keys[@]}"; do

        secret_name "${key}" || out+=" -e ${key}='${!key}'"

    done

    printf '%s' "${out}"

}
## sync this bundle and the resolved config to the box — the box reads the release tag from the same file CI resolved
server_push () {

    local secrets="" path=""

    path="$(server_path)"
    secrets="$(tmp_file)"

    IMAGE_TAG_OVERRIDE="$(ci_tag)"
    COMPOSE_DIR="${path}/stack"

    export IMAGE_TAG_OVERRIDE COMPOSE_DIR

    config_render "${secrets}"

    server_run "mkdir -p '${path}' 2>/dev/null || { sudo mkdir -p '${path}' && sudo chown -R \$(id -un): '${path}'; }"

    server_copy "${INFRA_BIN}" "${path}/infra"
    server_copy "${secrets}" "${path}/.env"

    server_run "chmod 700 '${path}/infra' && chmod 600 '${path}/.env'"

    rm -f "${secrets}"

    succ "Bundle + config synced to ${path}."

}
## push the bundle and the resolved config, then roll this release on the box
server_refresh () {

    server_wait
    server_push
    server_forward compose deploy
    server_forward server verify

    succ "Release $(ci_tag) rolled on $(server_host)."

}
## converge the server: bootstrap it when the stack is not there yet, otherwise roll the release
server_ensure () {

    if server_ready; then

        server_refresh
        return 0

    fi

    server_deploy

}
## prepare the box without deploying: docker, compose, kernel limits (confirmed)
server_setup () {

    local host=""

    host="$(server_host)"

    confirm "Prepare '${SSH_USER}@${host}' for the platform?"

    server_wait
    server_push
    server_forward server prepare

    succ "${host} carries docker and the kernel limits — 'infra server deploy' brings the stack."

}
## the ONE verb: push everything and bootstrap the whole platform on the box
server_deploy () {

    local host=""

    host="$(server_host)"

    confirm "Deploy the '${STACK}' stack on '${SSH_USER}@${host}'?"

    server_wait
    server_push
    server_forward server bootstrap

    succ "Stack '${STACK}' live on ${host} — 'infra server status' shows it."

}
## the on-box side: docker, kernel, registry login, names, certificate, the stack, the units, the verification
server_bootstrap () {

    server_prepare
    ci_login
    dns_ensure
    edge_prepare
    compose_deploy
    server_units
    server_verify

}
## docker, compose and the kernel limits — the box is ready to carry containers
server_prepare () {

    ensure docker curl jq envsubst

    compose_docker compose version >/dev/null 2>&1 || die "The docker compose plugin is missing — install docker-compose-plugin"

    ensure_dir "${COMPOSE_DIR}"
    render "${TEMPLATE_DIR}/systemd/sysctl.conf" "${COMPOSE_DIR}/sysctl.conf"

    as_root install -m 0644 "${COMPOSE_DIR}/sysctl.conf" "/etc/sysctl.d/90-${PROJECT}.conf"
    as_root sysctl -q --system >/dev/null

    succ "Box prepared — docker $(compose_docker version --format '{{.Server.Version}}' 2>/dev/null || echo ready), kernel limits applied."

}
## install the systemd units: the stack on boot, the nightly backup, the certificate renewal
server_units () {

    local unit=""

    has systemctl || { warn "No systemd here — the stack restarts with docker, backups and renewals need a scheduler of yours"; return 0; }

    for unit in "${COMPOSE_DIR}"/systemd/*; do

        as_root install -m 0644 "${unit}" "/etc/systemd/system/$(basename "${unit}")"

    done

    as_root systemctl daemon-reload
    as_root systemctl enable "${COMPOSE_PROJECT}.service" >/dev/null 2>&1
    as_root systemctl enable --now "${COMPOSE_PROJECT}-backup.timer" >/dev/null 2>&1

    [[ "${TLS_ENABLED}" != "true" ]] || as_root systemctl enable --now "${COMPOSE_PROJECT}-renew.timer" >/dev/null 2>&1

    succ "Units installed — ${COMPOSE_PROJECT} on boot, backups at ${BACKUP_CALENDAR}, renewals twice a day."

}
## block until the edge on this box serves this release
server_verify () {

    local tag="" url="" live="" waited=0

    server_here || { server_forward server verify; return; }

    ensure curl jq

    tag="$(ci_tag)"
    url="$(config_origin "${API_HOST}")${RELEASE_PATH}"

    step "Waiting for ${API_HOST} to serve ${tag}"

    while (( waited < RELEASE_WAIT )); do

        live="$(curl -sk -m 15 --resolve "${API_HOST}:${PUBLIC_PORT}:127.0.0.1" "${url}" 2>/dev/null | jq -r '.data.release // empty' 2>/dev/null || true)"

        if [[ "${live}" == "${tag}" ]]; then

            succ "Release ${tag} is live on ${API_HOST} after ${waited}s."
            return 0

        fi

        sleep "${RELEASE_POLL}"
        waited=$(( waited + RELEASE_POLL ))

    done

    compose_cmd ps -a
    compose_cmd logs --tail "${LOG_TAIL}" api nginx

    die "Release ${tag} is not live after ${RELEASE_WAIT}s (the edge serves '${live:-nothing}') — the report above carries the reason"

}
## the containers on the box
server_status () {

    server_here || { server_forward compose ps; return; }

    compose_ps

}
