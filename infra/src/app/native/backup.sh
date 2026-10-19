source-include module/docker.sh || return
source-include module/postgresql.sh || return
source-include module/s3.sh || return

native-backup () {

    fs-dir "${CONFIG[STATE_ROOT]}/backups" || return

    state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-backup-locked

}
native-backup-locked () {

    local root="${CONFIG[STATE_ROOT]}/backups" name="" staging="" destination=""

    name="$(date -u +%Y%m%dT%H%M%SZ)" || return
    staging="$(mktemp "${root}/.dump.XXXXXXXX")" || { err "Cannot stage a backup in ${root}"; return; }
    name+="-${staging##*.}"
    destination="${root}/${name}.dump"

    postgresql-dump "${staging}" native-compose-data exec -T postgres || { rm -f -- "${staging}"; err "Database dump failed; no backup published"; return; }
    mv -- "${staging}" "${destination}" || return

    fs-hash "${destination}" | fs-write "${destination}.sha256" || return
    state-write "${root}" latest "${name}.dump" || return

    if [[ "${CONFIG[BACKUP_DRIVER]}" == s3 ]]; then
        s3-upload "${destination}" "${CONFIG[BACKUP_S3_URI]%/}/${name}.dump" || return
        s3-upload "${destination}.sha256" "${CONFIG[BACKUP_S3_URI]%/}/${name}.dump.sha256" || return
    fi

    native-backup-prune || return
    out "${destination}"

}
native-backup-prune () {

    local root="${CONFIG[STATE_ROOT]}/backups" latest="" file="" now="" modified=""

    latest="$(state-read "${root}" latest)" || return
    now="$(date +%s)"

    for file in "${root}"/*.dump; do
        [[ -f "${file}" && ! -L "${file}" && "${file##*/}" != "${latest}" ]] || continue
        modified="$(fs-modified "${file}")" || return
        (( now - modified > CONFIG[BACKUP_DAYS] * 86400 )) || continue
        rm -f -- "${file}" "${file}.sha256" || return
    done

}
native-restore () {

    (( $# == 2 )) || { err "Usage: restore BACKUP_FILE NEW_DATABASE"; return; }

    state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-restore-locked "$@"

}
native-restore-locked () {

    local source="${1}" database="${2}" expected=""

    [[ "${database}" != "${CONFIG[DB_NAME]}" ]] || { err "Restore into a new database, validate it, then plan the cutover"; return; }
    expected="$(fs-read "${source}.sha256")" || return
    [[ "${expected}" == "$(fs-hash "${source}")" ]] || { err "Backup checksum mismatch: ${source}"; return; }

    postgresql-create "${database}" native-compose-data exec -T postgres || { err "Cannot create database ${database}"; return; }
    postgresql-restore "${source}" "${database}" native-compose-data exec -T postgres || { err "Restore into ${database} failed"; return; }

    ui-result restore true safe

}
native-monitor () {

    local release="" healthy=true root="${CONFIG[STATE_ROOT]}/backups" latest="" age=0

    native-current || return
    release="${CONFIG[RELEASE]}"

    native-healthy "${release}" api "$(native-replicas api)" || { warn "API replicas are not all healthy"; healthy=false; }
    native-data-healthy || { warn "Data services are not all healthy"; healthy=false; }
    native-probe-public || { warn "Public endpoint does not serve ${release}"; healthy=false; }

    if latest="$(state-read "${root}" latest 2>/dev/null)"; then
        age=$(( $(date +%s) - $(fs-modified "${root}/${latest}") ))
        (( age <= CONFIG[BACKUP_MAX_AGE] )) || { warn "Latest backup is ${age}s old"; healthy=false; }
    else
        warn "No backup recorded"
        healthy=false
    fi

    ui-row release "${release}"
    ui-row healthy "${healthy}"

    [[ "${healthy}" == true ]] || { native-notify "${CONFIG[COMPOSE_PROJECT]} is degraded" 2>/dev/null || true; return 1; }

}
native-notify () {

    local message="${1:-Infrastructure notification}" payload="" result="" header="" status=0

    cfg-require NOTIFY_URL || return
    payload="$(fs-temp-file)" || return
    result="$(fs-temp-file)" || return

    printf '{"project":%s,"environment":%s,"message":%s}\n' "$(parse-json-string "${CONFIG[PROJECT]}")" \
        "$(parse-json-string "${CONFIG[DEPLOY_ENV]}")" "$(parse-json-string "${message}")" | fs-write "${payload}" || status=$?

    [[ -z "${CONFIG[NOTIFY_TOKEN]}" ]] || header=Authorization
    (( status != 0 )) || net-request POST "${CONFIG[NOTIFY_URL]}" "${result}" "${header}" "Bearer ${CONFIG[NOTIFY_TOKEN]}" "${payload}" || status=$?

    rm -f -- "${payload}" "${result}"
    return "${status}"

}
