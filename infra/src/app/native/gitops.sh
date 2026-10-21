source-include module/docker.sh || return
source-include module/gitops.sh || return
source-include module/portainer.sh || return
source-include module/registry.sh || return
source-include module/tls.sh || return

native-reconcile () {

    local scratch="" current="" reason="" status=0

    scratch="$(fs-temp)" || return

    if ! gitops-fetch "${scratch}"; then
        status=1
    elif current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null || true)" && [[ "${current}" != "${CONFIG[RELEASE]}" ]] &&
        reason="$(native-rejected "${CONFIG[RELEASE]}")" && ! cli-flag --force; then
        warn "Desired release ${CONFIG[RELEASE]} was rejected (${reason}); waiting for a new release"
    elif ! reason="$(native-stale)"; then
        status=1
    elif [[ -n "${reason}" ]]; then
        warn "The server ${reason} differ from the desired state of ${CONFIG[RELEASE]}; waiting for server stage"
    elif native-deploy; then
        state-write "${CONFIG[STATE_ROOT]}" desired "${CONFIG[GITOPS_COMMIT]}" || status=$?
    else
        status=1
    fi

    rm -rf -- "${scratch}"
    return "${status}"

}
native-stale () {

    local app="" digest="" revision=""

    for app in API WEB; do
        digest="$(native-env-digest "${app}")" || return
        [[ "${digest}" == "${CONFIG[${app}_ENV_SHA256]:-}" ]] || { out "${app} env files"; return 0; }
    done

    [[ -n "${CONFIG[VERSION]:-}" ]] || return 0
    revision="$(native-revision)" || return
    [[ "${CONFIG[RELEASE]}" == "${CONFIG[VERSION]}-${revision}" ]] || out settings

}
native-watch () {

    while true; do
        native-reconcile || warn "Reconciliation failed; inspect status before the next attempt"
        sleep "${CONFIG[GITOPS_INTERVAL]}"
    done

}
native-export () {

    local destination="${1:-${TOOL_ROOT}/${MANIFEST[paths.build]}/desired}"

    native-desired "${destination}" || return

    succ "Desired state written to ${destination}; commit it and protect tag ${CONFIG[RELEASE_REF]}"

}
native-desired () {

    local destination="${1}" scratch="" status=0

    config-validate || return
    native-release-id || return
    cfg-require PROJECT RELEASE API_IMAGE API_HOST || return
    native-env-digests || return
    scratch="$(fs-temp)" || return

    native-render-compose "${scratch}" || status=$?
    (( status != 0 )) || gitops-export "${CONFIG[COMPOSE_PROJECT]}-${CONFIG[RELEASE]}" "${scratch}" "${destination}" \
        -f "${scratch}/application.yaml" -f "${scratch}/web.yaml" || status=$?

    rm -rf -- "${scratch}"
    return "${status}"

}
native-publish () {

    local scratch="" status=0

    cfg-require GITOPS_URL GITOPS_USER GITOPS_TOKEN || return
    scratch="$(fs-temp)" || return

    native-desired "${scratch}" || status=$?
    (( status != 0 )) || gitops-publish "${scratch}" || status=$?

    rm -rf -- "${scratch}"
    (( status == 0 )) || return "${status}"

    ui-result publish true safe

}
native-portainer-deploy () {

    local release="${1}" name="${CONFIG[COMPOSE_PROJECT]}-${1}" directory="" id="" commit="" pair=""
    local -a variables=()

    cfg-require GITOPS_COMMIT || return
    directory="$(native-directory "${release}")" || return

    while IFS= read -r pair; do
        variables+=( "${pair}" )
    done < <(native-interpolation "${release}")

    native-portainer-context || return
    id="$(portainer-stack "${name}")" || return

    if [[ -n "${id}" ]]; then
        info "Portainer stack ${name} exists; resuming its containers"
        native-resume "${release}" || return
    else
        id="$(portainer-create "${name}" "${variables[@]}")" || { err "Portainer stack creation failed: ${name}"; return; }
    fi

    state-write "${directory}" portainer-id "${id}" || return
    commit="$(portainer-commit "${id}")" || return
    [[ "${commit}" == "${CONFIG[GITOPS_COMMIT]}" ]] || { err "Portainer deployed ${commit:-nothing} instead of ${CONFIG[GITOPS_COMMIT]}"; return; }

}
native-portainer-retire () {

    local id=""

    native-portainer-context || return
    id="$(portainer-stack "${CONFIG[COMPOSE_PROJECT]}-${1}")" || return
    [[ -z "${id}" ]] || portainer-delete "${id}"

}
native-portainer-context () {

    local control="${CONFIG[STATE_ROOT]}/control"

    [[ -n "${CONFIG[PORTAINER_CA]}" || ! -f "${control}/tls/ca.pem" ]] || cfg-set PORTAINER_CA "${control}/tls/ca.pem" state
    [[ -n "${CONFIG[PORTAINER_TOKEN]}" || ! -f "${control}/secrets/api-key" ]] || cfg-set PORTAINER_TOKEN "$(fs-read "${control}/secrets/api-key")" state

    return 0

}
native-portainer () {

    native-dispatch portainer "$@"

}
native-portainer-install () {

    local control="${CONFIG[STATE_ROOT]}/control" secrets="${CONFIG[STATE_ROOT]}/control/secrets" socket="" uid="" gid=""
    local host="${CONFIG[PORTAINER_URL]#https://}"

    cfg-require PORTAINER_ADMIN_PASSWORD PORTAINER_SECRET_KEY || return
    (( ${#CONFIG[PORTAINER_ADMIN_PASSWORD]} >= 12 )) || { err "PORTAINER_ADMIN_PASSWORD needs at least 12 characters"; return; }
    (( ${#CONFIG[PORTAINER_SECRET_KEY]} >= 32 )) || { err "PORTAINER_SECRET_KEY needs at least 32 characters"; return; }
    docker-ready || return
    [[ "${CONFIG[ENV_MODE]}" != production ]] || docker-versions || return

    socket="$(docker-socket)" || return
    uid="$(docker-uid)" || return
    gid="$(stat -c %g "${socket}" 2>/dev/null || stat -f %g "${socket}")" || { err "Docker socket ownership unreadable"; return; }
    ! docker-rootless || gid=0

    fs-dir "${secrets}" 755 || return

    if [[ -f "${secrets}/portainer-key" ]]; then
        [[ "$(fs-read "${secrets}/portainer-key")" == "${CONFIG[PORTAINER_SECRET_KEY]}" ]] || { err "PORTAINER_SECRET_KEY differs from the installed key; rotation needs a recovery plan"; return; }
    else
        printf '%s' "${CONFIG[PORTAINER_SECRET_KEY]}" | fs-write "${secrets}/portainer-key" 600 || return
    fi

    printf '%s' "${CONFIG[PORTAINER_ADMIN_PASSWORD]}" | fs-write "${secrets}/admin-password" 600 || return

    host="${host%%[:/]*}"
    tls-authority "${control}/tls" "${CONFIG[COMPOSE_PROJECT]} control" "${host}" localhost 127.0.0.1 || return

    cfg-set CONTROL_USER "${uid}:${uid}"
    cfg-set CONTROL_GROUP "${gid}"
    cfg-set CONTROL_SOCKET "${socket}"
    cfg-set CONTROL_ROOT "${secrets}"
    cfg-set CONTROL_TLS "${control}/tls"

    docker-volume "${CONFIG[COMPOSE_PROJECT]}-portainer" "${CONFIG[COMPOSE_PROJECT]}" "${uid}" "${CONFIG[IMAGE_POSTGRES]}" || return
    portainer-render "${control}" || return
    docker-compose "${CONFIG[COMPOSE_PROJECT]}-control" -f "${control}/control.yaml" up -d portainer || return

    native-portainer-context || return
    run-until "${CONFIG[HEALTH_TIMEOUT]}" 2 portainer-ready || { err "Portainer API did not answer over verified TLS"; return; }
    [[ -f "${secrets}/api-key" ]] || portainer-api-key "${secrets}/api-key" || return

    ui-result portainer-install true safe

}
native-portainer-registry () {

    local host="" type=""

    host="$(registry-host)" || return
    type="$(portainer-registry-type "${CONFIG[REGISTRY_DRIVER]}")" || return
    native-portainer-context || return

    portainer-registry "${host}" "${type}" "${CONFIG[COMPOSE_PROJECT]}-pull" || return
    ui-result portainer-registry true safe

}
