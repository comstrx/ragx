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
postgresql-extensions () {

    local database="${1}" extensions="${2}" extension=""
    local -a wanted=()

    shift 2
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }
    [[ -z "${extensions}" ]] || IFS=, read -r -a wanted <<< "${extensions}"

    for extension in "${wanted[@]}"; do
        [[ "${extension}" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || { err "Invalid PostgreSQL extension: ${extension}"; return; }
        "$@" sh -c 'exec psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "CREATE EXTENSION IF NOT EXISTS \"$2\""' extension "${database}" "${extension}" ||
            { err "PostgreSQL extension ${extension} is unavailable in ${database}"; return; }
    done

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

    local source="${1}" database="${2}" catalog=""

    shift 2
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }

    catalog="$(fs-read "${source}" | "$@" pg_restore --list | awk '!/^[0-9]+; [0-9]+ [0-9]+ (EXTENSION|COMMENT - EXTENSION) /')" || { err "Cannot read the catalog of ${source}"; return; }

    fs-read "${source}" | "$@" sh -c 'printf "%s\n" "$2" > /tmp/restore.list || exit; pg_restore -U "$POSTGRES_USER" -d "$1" -L /tmp/restore.list --exit-on-error --no-owner --no-acl --role "$DB_USER"; status=$?; rm -f /tmp/restore.list; exit "$status"' restore "${database}" "${catalog}"

}
postgresql-drop () {

    local database="${1}"

    shift
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }

    "$@" sh -c 'exec dropdb -U "$POSTGRES_USER" --if-exists "$1"' drop "${database}"

}
postgresql-sql () {

    local -a variables=()

    while (( $# > 0 )) && [[ "${1}" != -- ]]; do
        variables+=( -v "${1}" )
        shift
    done

    shift
    "$@" sh -c 'exec psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres "$@"' sql "${variables[@]}"

}
postgresql-rename () {

    printf '%s\n' 'ALTER DATABASE :"source" RENAME TO :"target";' | postgresql-sql "source=${1}" "target=${2}" -- "${@:3}" > /dev/null 2>&1

}
postgresql-swap () {

    local live="${1}" restored="${2}" kept="${3}" owner="${4}" name=""

    shift 4

    for name in "${live}" "${restored}" "${kept}" "${owner}"; do
        parse-identifier "${name}" || { err "Invalid database name: ${name}"; return; }
    done

    printf '%s\n' 'ALTER DATABASE :"live" WITH ALLOW_CONNECTIONS false;' \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'live' AND pid <> pg_backend_pid();" |
        postgresql-sql "live=${live}" -- "$@" > /dev/null || return

    if ! run-until 15 1 postgresql-rename "${live}" "${kept}" "$@"; then
        printf '%s\n' 'ALTER DATABASE :"live" WITH ALLOW_CONNECTIONS true;' | postgresql-sql "live=${live}" -- "$@" > /dev/null || warn "Allow connections to ${live} by hand"
        err "${live} kept its connections; nothing was renamed"
        return
    fi

    printf '%s\n' 'ALTER DATABASE :"restored" RENAME TO :"live";' 'REVOKE CONNECT ON DATABASE :"live" FROM PUBLIC;' 'GRANT CONNECT ON DATABASE :"live" TO :"owner";' |
        postgresql-sql "restored=${restored}" "live=${live}" "owner=${owner}" -- "$@" > /dev/null && return

    if postgresql-rename "${kept}" "${live}" "$@"; then
        printf '%s\n' 'ALTER DATABASE :"live" WITH ALLOW_CONNECTIONS true;' | postgresql-sql "live=${live}" -- "$@" > /dev/null || warn "Allow connections to ${live} by hand"
    else
        warn "Rename ${kept} back to ${live} by hand"
    fi

    err "${restored} could not take the name ${live}"

}
postgresql-catalog () {

    local source="${1}"

    shift
    fs-read "${source}" | "$@" pg_restore --list > /dev/null

}
postgresql-tables () {

    local database="${1}"

    shift
    parse-identifier "${database}" || { err "Invalid database name: ${database}"; return; }

    "$@" sh -c 'exec psql -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('"'"'pg_catalog'"'"', '"'"'information_schema'"'"')"' tables "${database}"

}
