#!/usr/bin/env bash

## the stack — one compose project carrying the edge, the api, the web, the data services and the operations

compose_docker () {

    if docker info >/dev/null 2>&1; then

        docker "$@"

    elif sudo -n docker info >/dev/null 2>&1; then

        sudo -n docker "$@"

    else

        die "Docker is not reachable — is the daemon up, and are you in the docker group?"

    fi

}
## the credentials certbot reads as a file — handed to compose through its environment, never written to disk
compose_ini () {

    printf 'dns_cloudflare_api_token = %s\n' "$(secret_get CLOUDFLARE_API_TOKEN)"

}
compose_cmd () {

    [[ -f "${COMPOSE_DIR}/compose.yaml" ]] || die "No rendered stack at ${COMPOSE_DIR} — run: infra compose render"

    COMPOSE_PROFILES="${COMPOSE_PROFILES}" CLOUDFLARE_INI="$(compose_ini)" \
        compose_docker compose --project-directory "${COMPOSE_DIR}" "$@"

}
compose_file () {

    render "${TEMPLATE_DIR}/${1:?Missing template}" "${COMPOSE_DIR}/${2:?Missing destination}"

}
compose_secret () {

    compose_file "${1}" "${2}"
    chmod 600 "${COMPOSE_DIR}/${2}"

}
compose_copy () {

    ensure_dir "$(dirname "${COMPOSE_DIR}/${2:?Missing destination}")"
    install -m "${3:-0644}" "${TEMPLATE_DIR}/${1:?Missing template}" "${COMPOSE_DIR}/${2}"

}
## true when the named profile is active on this stack
compose_enabled () {

    [[ ",${COMPOSE_PROFILES}," == *",${1:?Missing profile},"* ]]

}
## the edge placeholders for the mode the stack runs in — https behind a certificate, plain http otherwise
compose_mode () {

    export HTTP_FALLBACK='return 444;' SITE_LISTEN=8080 SITE_QUIC='' SITE_TLS=''

    [[ "${TLS_ENABLED}" == "true" ]] || return 0

    export HTTP_FALLBACK='return 301 https://$host$request_uri;'
    export SITE_LISTEN='8443 ssl' SITE_QUIC='listen 8443 quic;' SITE_TLS='include /etc/nginx/platform/tls.inc;'

}
compose_realip () {

    local file="${COMPOSE_DIR}/nginx/conf.d/05-realip.conf" cidr=""

    rm -f "${file}"

    [[ -n "${EDGE_TRUSTED_CIDRS}" ]] || return 0

    {

        for cidr in ${EDGE_TRUSTED_CIDRS//,/ }; do printf 'set_real_ip_from %s;\n' "${cidr}"; done

        printf 'real_ip_header %s;\nreal_ip_recursive on;\n' "${REAL_IP_HEADER}"

    } > "${file}"

}
## the templates the stack renders — the law that every placeholder resolves reads this list
compose_templates () {

    printf '%s\n' compose/compose.yaml compose/api.env compose/postgres.env compose/rabbitmq.env compose/redis.env compose/backup.env \
        nginx/nginx.conf nginx/proxy.inc nginx/site.inc nginx/tls.inc nginx/conf.d/00-http.conf nginx/conf.d/10-tls.conf nginx/conf.d/20-api.conf nginx/conf.d/30-web.conf \
        postgres/postgresql.conf postgres/pg_hba.conf redis/redis.conf \
        systemd/stack.service systemd/backup.service systemd/backup.timer systemd/renew.service systemd/renew.timer systemd/sysctl.conf

}
## render the whole stack into COMPOSE_DIR — compose file, env files, the edge, the data services, the units
compose_render () {

    ensure envsubst

    IMAGE_TAG="$(ci_tag)"
    export IMAGE_TAG

    compose_mode

    compose_file compose/compose.yaml compose.yaml
    compose_secret compose/api.env api.env
    secret_env_extra "${COMPOSE_DIR}/api.env"
    compose_secret compose/postgres.env postgres.env
    compose_secret compose/rabbitmq.env rabbitmq.env
    compose_secret compose/redis.env redis.env
    compose_secret compose/backup.env backup.env

    compose_file nginx/nginx.conf nginx/nginx.conf
    compose_file nginx/proxy.inc nginx/proxy.inc
    compose_file nginx/site.inc nginx/site.inc
    compose_file nginx/conf.d/00-http.conf nginx/conf.d/00-http.conf
    compose_file nginx/conf.d/20-api.conf nginx/conf.d/20-api.conf
    compose_realip

    rm -f "${COMPOSE_DIR}/nginx/conf.d/30-web.conf" "${COMPOSE_DIR}/nginx/conf.d/10-tls.conf" "${COMPOSE_DIR}/nginx/tls.inc"

    ! compose_enabled web || compose_file nginx/conf.d/30-web.conf nginx/conf.d/30-web.conf

    if [[ "${TLS_ENABLED}" == "true" ]]; then

        compose_file nginx/tls.inc nginx/tls.inc
        compose_file nginx/conf.d/10-tls.conf nginx/conf.d/10-tls.conf

    fi

    compose_file postgres/postgresql.conf postgres/postgresql.conf
    compose_file postgres/pg_hba.conf postgres/pg_hba.conf
    compose_copy postgres/init.sh postgres/init.sh 0755
    compose_copy rabbitmq/platform.conf rabbitmq/platform.conf
    compose_file redis/redis.conf redis/redis.conf

    rm -rf "${COMPOSE_DIR}/systemd"

    compose_file systemd/stack.service "systemd/${COMPOSE_PROJECT}.service"
    compose_file systemd/backup.service "systemd/${COMPOSE_PROJECT}-backup.service"
    compose_file systemd/backup.timer "systemd/${COMPOSE_PROJECT}-backup.timer"

    if [[ "${TLS_ENABLED}" == "true" ]]; then

        compose_file systemd/renew.service "systemd/${COMPOSE_PROJECT}-renew.service"
        compose_file systemd/renew.timer "systemd/${COMPOSE_PROJECT}-renew.timer"

    fi

    succ "Stack rendered → ${COMPOSE_DIR} (${IMAGE_TAG}, profiles: ${COMPOSE_PROFILES:-none}, edge: ${SITE_LISTEN%% *})"

}
## let docker compose itself validate the rendered stack
compose_config () {

    compose_cmd config -q && succ "compose.yaml is valid — ${COMPOSE_PROJECT}"

}
## pull every image the stack names
compose_pull () {

    compose_cmd pull -q

}
## start or converge the stack in place — a cold start or a maintenance restart; releases use deploy
compose_up () {

    compose_cmd up -d --remove-orphans --wait --wait-timeout "${COMPOSE_WAIT}" "$@"

}
## stop every container of every profile and keep them — the boot unit's way down
compose_stop () {

    COMPOSE_PROFILES='*' compose_cmd stop

}
## stop the stack and remove every container of every profile — the volumes stay (confirmed)
compose_down () {

    confirm "Stop '${COMPOSE_PROJECT}' and remove its containers? The volumes stay."

    COMPOSE_PROFILES='*' compose_cmd down --remove-orphans

}
## every container of every profile and its health
compose_ps () {

    COMPOSE_PROFILES='*' compose_cmd ps -a

}
## the logs of one service or all — pass -f to follow
compose_logs () {

    compose_cmd logs --tail "${LOG_TAIL}" "$@"

}
## restart one service or all
compose_restart () {

    compose_cmd restart "$@"

}
## run a command inside a running service
compose_exec () {

    compose_cmd exec "$@"

}
compose_running () {

    compose_cmd ps -q "${1:?Missing service}" 2>/dev/null

}
compose_healthy () {

    local state=""

    state="$(compose_docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${1:?Missing container}" 2>/dev/null)"

    [[ "${state}" == "healthy" || "${state}" == "running" ]]

}
compose_retire () {

    local id=""

    for id in "$@"; do

        compose_docker stop -t "${ROLL_GRACE}" "${id}" >/dev/null 2>&1 || true
        compose_docker rm -f "${id}" >/dev/null 2>&1 || true

    done

}
## roll one service onto this release without downtime: new containers start beside the old, the old retire once the new are healthy
compose_roll () {

    local service="${1:?Missing service}" id="" ok=0 left="${ROLL_TRIES}" count=0
    local -a old=() fresh=()

    mapfile -t old < <(compose_running "${service}")
    count="${#old[@]}"

    if (( count == 0 )); then

        compose_up "${service}"
        return 0

    fi

    compose_cmd up -d --no-deps --no-recreate --scale "${service}=$(( count * 2 ))" "${service}" >/dev/null 2>&1 \
        || die "Cannot start the new ${service} beside the old"

    mapfile -t fresh < <(compose_running "${service}" | grep -vxF -f <(printf '%s\n' "${old[@]}") || true)

    (( ${#fresh[@]} )) || die "No new ${service} container appeared"

    step "Rolling ${service} — ${#fresh[@]} new beside ${count} old"

    while (( left-- )); do

        ok=1

        for id in "${fresh[@]}"; do compose_healthy "${id}" || ok=0; done

        (( ok == 0 )) || break

        sleep "${ROLL_POLL}"

    done

    if (( ok == 0 )); then

        compose_docker logs --tail "${LOG_TAIL}" "${fresh[0]}" >&2 || true
        compose_retire "${fresh[@]}"

        die "The new ${service} never became healthy — the old containers still serve"

    fi

    compose_retire "${old[@]}"
    compose_cmd up -d --no-deps --scale "${service}=${count}" "${service}" >/dev/null 2>&1 || true

    succ "${service} rolled onto $(ci_tag)"

}
compose_record () {

    printf '%s %s\n' "$(date -u +%FT%TZ)" "${IMAGE_TAG}" >> "${COMPOSE_DIR}/releases"

}
## forget the images of releases nobody runs anymore — the last ROLL_KEEP stay for a rollback
compose_prune () {

    local keep="" image="" line=""

    keep="$(tail -n "${ROLL_KEEP}" "${COMPOSE_DIR}/releases" 2>/dev/null | awk '{ print $2 }' | paste -sd '|' -)"

    for image in "${IMAGE_API}" "${IMAGE_WEB}"; do

        while IFS= read -r line; do

            [[ -n "${line}" ]] || continue
            [[ -z "${keep}" || ! "${line##*:}" =~ (${keep})$ ]] || continue

            compose_docker image rm "${line}" >/dev/null 2>&1 || true

        done < <(compose_docker image ls "${image}" --format '{{.Repository}}:{{.Tag}}' 2>/dev/null)

    done

    compose_docker image prune -f >/dev/null 2>&1 || true

}
## the release step on the box: render, pull, converge the data services, roll the apps, reload the edge
compose_deploy () {

    local service=""

    server_here || { server_forward compose deploy; return; }

    compose_render
    compose_pull
    compose_cmd up -d --remove-orphans --wait --wait-timeout "${COMPOSE_WAIT}" postgres rabbitmq redis

    compose_roll api

    if compose_enabled web; then

        for service in web-super web-admin web-client; do compose_roll "${service}"; done

    fi

    ! compose_enabled worker || compose_up worker
    ! compose_enabled scheduler || compose_up scheduler

    compose_up
    edge_reload
    compose_record
    compose_prune

    succ "Release ${IMAGE_TAG} deployed — ${COMPOSE_PROJECT}"

}
## redeploy the release before this one — the box remembers every release it ran
compose_rollback () {

    local previous=""

    server_here || { server_forward compose rollback; return; }

    previous="$(tail -n 2 "${COMPOSE_DIR}/releases" 2>/dev/null | head -1 | awk '{ print $2 }')"

    [[ -n "${previous}" && "${previous}" != "$(ci_tag)" ]] || die "No previous release recorded on this box"

    confirm "Roll back to ${previous}?"

    IMAGE_TAG_OVERRIDE="${previous}" compose_deploy

}
## the releases this box ran, newest last
compose_releases () {

    server_here || { server_forward compose releases; return; }

    cat "${COMPOSE_DIR}/releases" 2>/dev/null || info "No release recorded yet"

}
