#!/usr/bin/env bash

## database backups — take, list, fetch, restore (never over the live db)

backup_run () {

    compose_cmd run --rm backup "$@"

}
## take a backup right now
backup_now () {

    server_here || { server_forward backup now; return; }

    backup_run dump

    succ "Backup complete — 'infra backup list' shows it."

}
## list the stored backups
backup_list () {

    server_here || { server_forward backup list; return; }

    backup_run list

}
## restore a stamp into a SIDE database — promote deliberately, never over the live one
backup_restore () {

    local stamp="${1:?Usage: backup restore <stamp> [target-db]}" target="${2:-${DB_NAME}_restore}"

    confirm "Restore '${stamp}' into isolated database '${target}'?"

    server_here || { server_forward backup restore "${stamp}" "${target}"; return; }

    backup_run restore "${stamp}" "${target}"

    succ "Restored '${stamp}' into '${target}' — verify it, then promote deliberately (never restored over '${DB_NAME}')."

}
## copy one stored backup to this machine
backup_fetch () {

    local stamp="${1:?Usage: backup fetch <stamp>}" dst=""

    ensure_dir "${BUILD_DIR}/backups"

    dst="${BUILD_DIR}/backups/${stamp}.dump"

    if server_here; then

        compose_cmd run --rm --no-deps -T --entrypoint cat backup "/backups/${DB_NAME}/${stamp}.dump" > "${dst}"

    else

        server_run "cd '${SERVER_PATH}/stack' && docker compose run --rm --no-deps -T --entrypoint cat backup '/backups/${DB_NAME}/${stamp}.dump'" > "${dst}"

    fi

    [[ -s "${dst}" ]] || { rm -f "${dst}"; die "Backup '${stamp}' is empty or missing"; }

    chmod 600 "${dst}"

    succ "Fetched → ${dst}"

}
