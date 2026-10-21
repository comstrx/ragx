source-include module/postgresql.sh || return
source-include module/s3.sh || return

native-backup () {

    native-dispatch backup "$@"

}
native-backup-create () {

    local destination="" copied=""

    fs-dir "${CONFIG[STATE_ROOT]}" || return
    fs-dir "${CONFIG[BACKUP_ROOT]}" || return

    if destination="$(state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-backup-locked)"; then
        [[ -z "${CONFIG[BACKUP_URI]}" ]] || copied=", copied to ${CONFIG[BACKUP_URI]%%:*}"
        native-announce backup.succeeded "database backup ${destination##*/} saved ($(native-size "$(wc -c < "${destination}")"))${copied}"
        out "${destination}"
        return 0
    fi

    native-announce backup.failed "the database backup failed"
    return 1

}
native-backup-locked () {

    local root="${CONFIG[BACKUP_ROOT]}" name="" staging="" destination=""

    name="$(date -u +%Y%m%dT%H%M%SZ)" || return
    staging="$(mktemp "${root}/.dump.XXXXXXXX")" || { err "Cannot stage a backup in ${root}"; return; }
    name+="-${staging##*.}"
    destination="${root}/${name}.dump"

    postgresql-dump "${staging}" native-compose-data exec -T postgres || { rm -f -- "${staging}"; err "Database dump failed; no backup published"; return; }
    postgresql-catalog "${staging}" native-compose-data exec -T postgres || { rm -f -- "${staging}"; err "The dump is not a readable archive; no backup published"; return; }
    mv -- "${staging}" "${destination}" || return

    fs-hash "${destination}" | fs-write "${destination}.sha256" || return
    state-write "${root}" latest "${name}.dump" || return

    if [[ -n "${CONFIG[BACKUP_URI]}" ]]; then
        s3-upload "${destination}" "${CONFIG[BACKUP_URI]%/}/${name}.dump" || return
        s3-upload "${destination}.sha256" "${CONFIG[BACKUP_URI]%/}/${name}.dump.sha256" || return
    fi

    native-backup-prune || return
    out "${destination}"

}
native-backup-prune () {

    local root="${CONFIG[BACKUP_ROOT]}" latest="" file="" now="" modified=""

    latest="$(state-read "${root}" latest)" || return
    now="$(date +%s)"

    for file in "${root}"/*.dump; do
        [[ -f "${file}" && ! -L "${file}" && "${file##*/}" != "${latest}" ]] || continue
        modified="$(fs-modified "${file}")" || return
        (( now - modified > CONFIG[BACKUP_DAYS] * 86400 )) || continue
        rm -f -- "${file}" "${file}.sha256" || return
    done

}
native-backup-list () {

    local root="${CONFIG[BACKUP_ROOT]}" latest="" file="" marker="" index=0
    local -a files=()

    [[ ! -d "${root}" ]] || files=( "${root}"/*.dump )
    [[ -f "${files[0]:-}" ]] || { info "No backups in ${root}"; return 0; }
    latest="$(state-read "${root}" latest 2>/dev/null)" || latest=""

    for (( index = ${#files[@]} - 1; index >= 0; index-- )); do
        file="${files[index]}"
        [[ -f "${file}" && ! -L "${file}" ]] || continue
        marker=""
        [[ "${file##*/}" != "${latest}" ]] || marker=" latest"
        ui-row "${file##*/}" "$(native-size "$(wc -c < "${file}")")${marker}"
    done

}
native-backup-verify () {

    (( $# <= 1 )) || { err "Usage: infra backup verify [BACKUP]"; return; }
    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-backup-verify-locked "$@"

}
native-backup-verify-locked () {

    local name="" scratch="" tables="" status=0

    name="$(native-backup-resolve "${1:-}")" || return
    scratch="${CONFIG[DB_NAME]}_verify_$(date -u +%Y%m%d%H%M%S)"
    native-wait-data || return
    native-restore-copy "${name}" "${scratch}" || return

    tables="$(postgresql-tables "${scratch}" native-compose-data exec -T postgres)" || status=$?
    postgresql-drop "${scratch}" native-compose-data exec -T postgres || warn "Remove ${scratch} by hand"
    (( status == 0 )) || { err "Restored ${name}, but its tables could not be counted"; return; }

    ui-row verified "${name}"
    ui-row tables "${tables}"
    ui-result backup-verify false safe

}
native-backup-resolve () {

    local root="${CONFIG[BACKUP_ROOT]}" name="${1:-}"

    [[ -n "${name}" ]] || name="$(state-read "${root}" latest 2>/dev/null)" || { err "No backup is recorded in ${root}"; return; }
    [[ "${name}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.dump$ ]] || { err "Name a .dump file in ${root}: ${name}"; return; }
    [[ -f "${root}/${name}" && ! -L "${root}/${name}" ]] || { err "Backup not found in ${root}: ${name}"; return; }
    [[ "$(fs-read "${root}/${name}.sha256")" == "$(fs-hash "${root}/${name}")" ]] || { err "Backup checksum mismatch: ${name}"; return; }

    out "${name}"

}
native-restore-copy () {

    local name="${1}" database="${2}"
    local -a data=( native-compose-data exec -T postgres )

    (( ${#database} <= 63 )) || { err "DB_NAME is too long to restore a copy beside it"; return; }
    postgresql-create "${database}" "${data[@]}" || { err "Cannot create ${database}; the live database is unchanged"; return; }

    if ! postgresql-extensions "${database}" "${CONFIG[DB_EXTENSIONS]}" "${data[@]}" || ! postgresql-restore "${CONFIG[BACKUP_ROOT]}/${name}" "${database}" "${data[@]}"; then
        postgresql-drop "${database}" "${data[@]}" || warn "Remove ${database} by hand"
        err "Restoring ${name} failed; the live database is unchanged"
        return
    fi

}
native-size () {

    local bytes="${1// /}"

    if (( bytes >= 1073741824 )); then out "$(( bytes / 1073741824 )) GiB"
    elif (( bytes >= 1048576 )); then out "$(( bytes / 1048576 )) MiB"
    else out "$(( (bytes + 1023) / 1024 )) KiB"
    fi

}
native-restore () {

    (( $# <= 1 )) || { err "Usage: infra restore [BACKUP] --force"; return; }
    cli-flag --force || { err "Restore replaces the live database; rerun with --force"; return; }
    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    state-locked "${CONFIG[STATE_ROOT]}/lock" state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-restore-locked "$@" && return

    native-announce restore.failed "the database restore failed; read the restore output before retrying"
    return 1

}
native-restore-locked () {

    local name="" stamp="" restored="" kept="" saved="" current=""
    local -a data=( native-compose-data exec -T postgres )

    name="$(native-backup-resolve "${1:-}")" || return
    stamp="$(date -u +%Y%m%d%H%M%S)"
    restored="${CONFIG[DB_NAME]}_restore_${stamp}"
    kept="${CONFIG[DB_NAME]}_before_${stamp}"

    native-wait-data || return
    saved="$(native-backup-locked)" || { err "The pre-restore backup failed; the live database is unchanged"; return; }
    info "Saved the live database as ${saved##*/}"
    native-restore-copy "${name}" "${restored}" || return

    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""
    [[ -z "${current}" ]] || native-current || return
    [[ -z "${current}" ]] || native-background-stop "${current}" || return

    if ! postgresql-swap "${CONFIG[DB_NAME]}" "${restored}" "${kept}" "${CONFIG[DB_USER]}" "${data[@]}"; then
        [[ -z "${current}" ]] || native-background-start "${current}" || warn "Start the worker and scheduler of ${current} by hand"
        postgresql-drop "${restored}" "${data[@]}" || warn "Remove ${restored} by hand"
        err "The database swap failed; the live database is unchanged"
        return
    fi

    [[ -z "${current}" ]] || native-background-start "${current}" || { err "Restored ${name}, but the worker and scheduler of ${current} did not start"; return; }
    [[ -z "${current}" ]] || run-until 60 2 native-probe-public || { err "Restored ${name}, but ${current} does not answer; ${kept} holds the previous data"; return; }

    native-announce restore.succeeded "the database was restored from ${name}; the previous data is kept as ${kept} and in backup ${saved##*/}"
    ui-row restored "${name}"
    ui-row kept "${kept}"
    ui-row saved "${saved##*/}"
    ui-result restore true safe

}
