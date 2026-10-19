postgresql-render () {

    local directory="${1}" templates="${MANIFEST[paths.templates]}/native"

    cfg-set POSTGRES_DB postgres
    cfg-set POSTGRES_USER postgres
    cfg-set POSTGRES_PASSWORD "${CONFIG[DB_ADMIN_PASSWORD]}"
    cfg-set POSTGRES_INITDB_ARGS '--auth-local=peer --auth-host=scram-sha-256'

    template-compose-env "${directory}/postgres.env" POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_INITDB_ARGS DB_NAME DB_USER DB_PASSWORD || return
    template-render "${templates}/postgres.sql" "${directory}/postgres.sql" 644 || return
    template-render "${templates}/pg_hba.conf" "${directory}/pg_hba.conf" 644

}
postgresql-dump () {

    local destination="${1}"

    shift
    (( $# > 0 )) || { err "Container execution prefix required"; return; }

    "$@" sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$DB_NAME" --format=custom --no-owner --no-acl' | fs-write "${destination}"

}
postgresql-create () {

    local database="${1}"

    shift
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }

    "$@" sh -c 'exec createdb -U "$POSTGRES_USER" --owner "$DB_USER" "$1"' create "${database}"

}
postgresql-restore () {

    local source="${1}" database="${2}"

    shift 2
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }

    fs-read "${source}" | "$@" sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error --no-owner --no-acl --role "$DB_USER"' restore "${database}"

}
