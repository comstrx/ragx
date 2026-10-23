source-include module/postgresql.sh || return
source-include module/s3.sh || return

native-backup () {

    native-dispatch backup "$@"

}
native-backup-create () {

    local destination="" copied="" based=""

    fs-dir "${CONFIG[STATE_ROOT]}" || return
    fs-dir "${CONFIG[BACKUP_ROOT]}" || return
    fs-dir "${CONFIG[BACKUP_SQL_ROOT]}" || return

    if destination="$(state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-backup-locked)"; then
        [[ -z "${CONFIG[BACKUP_URI]}" ]] || copied=", copied to ${CONFIG[BACKUP_URI]%%:*}"
        ! cfg-true BACKUP_WAL || based=" with a point-in-time base"
        native-announce backup.succeeded "database backup ${destination##*/} saved ($(native-size "$(wc -c < "${destination}")"))${based}${copied}"
        out "${destination}"
        return 0
    fi

    native-announce backup.failed "the database backup failed"
    return 1

}
native-backup-locked () {

    local destination=""

    destination="$(native-backup-dump)" || return
    native-backup-base >&2 || return

    out "${destination}"

}
native-backup-dump () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" name="" staging="" destination=""

    fs-dir "${root}" || return
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
        s3-upload "${destination}" "${CONFIG[BACKUP_URI]%/}/sql/${name}.dump" || return
        s3-upload "${destination}.sha256" "${CONFIG[BACKUP_URI]%/}/sql/${name}.dump.sha256" || return
    fi

    native-backup-prune || return
    out "${destination}"

}
native-backup-base () {

    local -a data=( native-compose-data exec -T postgres )

    postgresql-archiving "${CONFIG[BACKUP_WAL]}" "${data[@]}" || return
    cfg-true BACKUP_WAL || return 0

    postgresql-base "$(date -u +%Y%m%dT%H%M%SZ)" "${data[@]}" > /dev/null || return
    postgresql-prune "$(( CONFIG[BACKUP_RETENTION] / 60 ))" "${data[@]}" || return

    native-archive-sync

}
native-backup-prune () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" latest="" file="" now="" modified=""

    latest="$(state-read "${root}" latest)" || return
    now="$(date +%s)"

    for file in "${root}"/*.dump; do
        [[ -f "${file}" && ! -L "${file}" && "${file##*/}" != "${latest}" ]] || continue
        modified="$(fs-modified "${file}")" || return
        (( now - modified > CONFIG[BACKUP_RETENTION] )) || continue
        rm -f -- "${file}" "${file}.sha256" || return
    done

}
native-backup-list () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" latest="" file="" marker="" stamp="" finished="" index=0
    local -a files=()

    [[ ! -d "${root}" ]] || files=( "${root}"/*.dump )
    latest="$(state-read "${root}" latest 2>/dev/null)" || latest=""

    if [[ -f "${files[0]:-}" ]]; then

        for (( index = ${#files[@]} - 1; index >= 0; index-- )); do
            file="${files[index]}"
            [[ -f "${file}" && ! -L "${file}" ]] || continue
            marker=""
            [[ "${file##*/}" != "${latest}" ]] || marker=" latest"
            ui-row "${file##*/}" "$(native-size "$(wc -c < "${file}")")${marker}"
        done

    else
        info "No dumps in ${root}"
    fi

    cfg-true BACKUP_WAL || return 0
    native-data-healthy || return 0

    while read -r stamp _ finished; do
        [[ -n "${stamp}" ]] || continue
        ui-row "base ${stamp}" "point in time from ${finished}"
    done < <(postgresql-bases native-compose-data exec -T postgres 2>/dev/null | sort -r)

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
native-backup-archive () {

    (( $# == 0 )) || { err "Usage: infra backup archive"; return; }
    cfg-true BACKUP_WAL || { info "BACKUP_WAL is off; there is no WAL archive to copy"; return 0; }
    [[ -n "${CONFIG[BACKUP_URI]}" ]] || { info "BACKUP_URI is empty; the WAL archive stays local"; return 0; }
    docker-ready || return

    native-archive-sync || return
    ui-result backup-archive true safe

}
native-archive-sync () {

    local source=""

    [[ -n "${CONFIG[BACKUP_URI]}" ]] || return 0
    source="$(native-archive-source)" || return

    s3-sync "${source}" "${CONFIG[BACKUP_URI]%/}/wal"

}
native-archive-source () {

    local container="" source=""

    container="$(native-compose-data ps -q postgres)" || return
    [[ -n "${container}" ]] || { err "PostgreSQL is not running"; return; }
    source="$(docker-inspect "${container}" '{{range .Mounts}}{{if eq .Destination "/wal"}}{{.Source}}{{end}}{{end}}')" || return
    [[ "${source}" == /* ]] || { err "PostgreSQL has no WAL archive mount; recreate the data services"; return; }

    out "${source}"

}
native-archive-root () {

    local root="${CONFIG[BACKUP_WAL_ROOT]}"

    [[ -d "${root}" ]] || fs-dir "${root}" || return

    docker-oneshot --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --entrypoint sh \
        --mount "type=bind,source=${root},target=/wal" -- "${CONFIG[IMAGE_POSTGRES]}" \
        -c 'mkdir -p /wal/archive /wal/base && chown 999:999 /wal /wal/archive /wal/base && chmod 700 /wal /wal/archive /wal/base' ||
        { err "The WAL archive ${root} could not be given to PostgreSQL"; return; }

}
native-backup-resolve () {

    local root="${CONFIG[BACKUP_SQL_ROOT]}" name="${1:-}"

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

    if ! postgresql-extensions "${database}" "${CONFIG[DB_EXTENSIONS]}" "${data[@]}" || ! postgresql-restore "${CONFIG[BACKUP_SQL_ROOT]}/${name}" "${database}" "${data[@]}"; then
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

    local moment=""

    (( $# <= 1 )) || { err "Usage: infra restore [BACKUP] --force, or infra restore --at TIME --force"; return; }
    cli-flag --force || { err "Restore replaces the live database; rerun with --force"; return; }

    if moment="$(cli-value --at)"; then
        (( $# == 0 )) || { err "Restore takes a BACKUP or --at TIME, not both"; return; }
        moment="$(native-moment "${moment}")" || return
    fi

    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}" || return

    if [[ -n "${moment}" ]]; then
        state-locked "${CONFIG[STATE_ROOT]}/lock" state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-restore-point "${moment}" && return
    else
        state-locked "${CONFIG[STATE_ROOT]}/lock" state-locked "${CONFIG[STATE_ROOT]}/backup-lock" native-restore-locked "$@" && return
    fi

    native-announce restore.failed "the database restore failed; read the restore output before retrying"
    return 1

}
native-moment () {

    local value="${1:-}" stamp=""

    [[ "${value}" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})[T\ ]([0-9]{2}):([0-9]{2}):([0-9]{2})Z?$ ]] || { err "Name the moment in UTC as YYYY-MM-DDTHH:MM:SSZ: ${value}"; return; }
    stamp="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}T${BASH_REMATCH[4]}${BASH_REMATCH[5]}${BASH_REMATCH[6]}Z"
    [[ ! "${stamp}" > "$(date -u +%Y%m%dT%H%M%SZ)" ]] || { err "The moment ${value} is in the future"; return; }

    out "${stamp}"

}
native-restore-locked () {

    local name="" stamp="" restored="" kept="" saved="" current=""
    local -a data=( native-compose-data exec -T postgres )

    name="$(native-backup-resolve "${1:-}")" || return
    stamp="$(date -u +%Y%m%d%H%M%S)"
    restored="${CONFIG[DB_NAME]}_restore_${stamp}"
    kept="${CONFIG[DB_NAME]}_before_${stamp}"

    native-wait-data || return
    saved="$(native-backup-dump)" || { err "The pre-restore backup failed; the live database is unchanged"; return; }
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
native-restore-point () {

    local moment="${1}" target="" base="" stamp="" finished="" source="" saved="" current="" kept=""
    local -a data=( native-compose-data exec -T postgres )

    target="${moment:0:4}-${moment:4:2}-${moment:6:2} ${moment:9:2}:${moment:11:2}:${moment:13:2}+00"
    cfg-true BACKUP_WAL || { err "A point-in-time restore needs BACKUP_WAL=true and its archive"; return; }
    native-wait-data || return

    while read -r stamp _ finished; do
        [[ -n "${finished}" && ! "${finished}" > "${moment}" ]] || continue
        base="${stamp}"
    done < <(postgresql-bases "${data[@]}" | sort)

    [[ -n "${base}" ]] || { err "No base backup finished before ${target}; read infra backup list"; return; }
    source="$(native-archive-source)" || return
    saved="$(native-backup-dump)" || { err "The pre-restore backup failed; the live database is unchanged"; return; }
    info "Saved the live database as ${saved##*/}; restoring ${target} from base ${base}"

    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""
    [[ -z "${current}" ]] || native-current || return
    [[ -z "${current}" ]] || native-background-stop "${current}" || return

    stamp="$(date -u +%Y%m%d%H%M%S)"
    kept="before-${stamp}"

    native-compose-data stop postgres || { native-restore-resume "${current}"; err "PostgreSQL did not stop; the live database is unchanged"; return; }

    if ! postgresql-unpack "${CONFIG[IMAGE_POSTGRES]}" "${CONFIG[COMPOSE_PROJECT]}-postgres" "${source}" "${base}" "${target}" "${stamp}"; then
        native-compose-data start postgres || warn "Start PostgreSQL by hand"
        native-restore-resume "${current}"
        err "The live database is unchanged"
        return
    fi

    if ! native-compose-data start postgres || ! native-replay; then
        warn "Recovery to ${target} did not finish; putting the previous data back"
        native-compose-data stop postgres || warn "Stop PostgreSQL by hand"
        postgresql-repack "${CONFIG[IMAGE_POSTGRES]}" "${CONFIG[COMPOSE_PROJECT]}-postgres" "${stamp}" || return
        native-compose-data start postgres || warn "Start PostgreSQL by hand"
        native-wait-data || warn "PostgreSQL is not healthy after putting the previous data back"
        native-restore-resume "${current}"
        err "The point-in-time restore failed; the previous data is back"
        return
    fi

    postgresql-settle "${data[@]}" || warn "Reset the recovery settings by hand: ALTER SYSTEM RESET restore_command"
    native-compose-data restart postgres || warn "Restart PostgreSQL by hand to drop the recovery target"
    native-wait-data || return
    native-restore-resume "${current}"
    [[ -z "${current}" ]] || run-until 60 2 native-probe-public || { err "Restored ${target}, but ${current} does not answer; the previous data directory is kept as ${kept}"; return; }
    native-backup-base || warn "Take a new base backup now with infra backup; the restore started a new timeline"

    native-announce restore.succeeded "the database was restored to ${target} from base ${base}; the previous data directory is kept as ${kept} and the live data in backup ${saved##*/}"
    ui-row restored "${target}"
    ui-row base "${base}"
    ui-row kept "PGDATA.${kept}, remove it once the restore is checked"
    ui-row saved "${saved##*/}"
    ui-result restore true safe

}
native-restore-resume () {

    [[ -z "${1:-}" ]] || native-background-start "${1}" || warn "Start the worker and scheduler of ${1} by hand"

}
native-replay () {

    local container="" restarts="" started="${SECONDS}"

    container="$(native-compose-data ps -q postgres)" || return
    restarts="$(docker-inspect "${container}" '{{.RestartCount}}')" || return

    while (( SECONDS - started < 3600 )); do
        postgresql-primary native-compose-data exec -T postgres && return 0
        [[ "$(docker-inspect "${container}" '{{.RestartCount}}' 2>/dev/null)" == "${restarts}" ]] || { err "PostgreSQL stopped during recovery; read its log"; return; }
        sleep 2
    done

    err "Recovery did not finish within an hour"

}
