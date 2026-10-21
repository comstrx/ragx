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
postgresql-archiving () {

    local switch="${1}"

    shift

    if [[ "${switch}" == true ]]; then "$@" sh -c 'umask 077 && mkdir -p /wal/archive /wal/base && : > /wal/enabled && chmod 600 /wal/enabled' || { err "The WAL archive is not writable for PostgreSQL"; return; }
    else "$@" rm -f /wal/enabled || { err "WAL archiving could not be switched off"; return; }
    fi

}
postgresql-base () {

    local stamp="${1}" range="" size="" timeline="" high="" low="" number=0 per=0 segment=""

    shift
    [[ "${stamp}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { err "Invalid base backup name: ${stamp}"; return; }

    "$@" sh -c 'umask 077 && rm -rf /wal/base/*.part && mkdir -m 700 "/wal/base/$1.part" && exec pg_basebackup -U "$POSTGRES_USER" -D "/wal/base/$1.part" --format=tar --gzip --wal-method=none --checkpoint=fast --no-password' base "${stamp}" ||
        { err "The base backup failed"; return; }

    range="$("$@" sed -n 's/.*"Timeline": *\([0-9]*\), *"Start-LSN": *"\([0-9A-F]*\)\/\([0-9A-F]*\)".*/\1 \2 \3/p' "/wal/base/${stamp}.part/backup_manifest")" || range=""
    size="$("$@" sh -c 'exec psql -q -t -A -U "$POSTGRES_USER" -d postgres -c "SHOW wal_segment_size"' 2>/dev/null)" || size=""
    read -r timeline high low <<< "${range%%$'\n'*}"

    [[ "${timeline}" =~ ^[0-9]+$ && "${high}" =~ ^[0-9A-F]{1,8}$ && "${low}" =~ ^[0-9A-F]{1,8}$ ]] || { err "The base backup manifest names no start position"; return; }
    size="$(postgresql-bytes "${size}")" || return

    number=$(( ((16#${high} << 32) | 16#${low}) / size ))
    per=$(( 0x100000000 / size ))
    printf -v segment '%08X%08X%08X' "${timeline}" "$(( number / per ))" "$(( number % per ))"

    "$@" sh -c 'umask 077 && printf "%s %s\n" "$2" "$3" > "/wal/base/$1.part/label" && mv "/wal/base/$1.part" "/wal/base/$1"' label "${stamp}" "${segment}" "$(date -u +%Y%m%dT%H%M%SZ)" ||
        { err "The base backup could not be published"; return; }

    out "${segment}"

}
postgresql-bytes () {

    local value="${1// /}"

    case "${value}" in
        *MB) out "$(( ${value%MB} * 1048576 ))" ;;
        *GB) out "$(( ${value%GB} * 1073741824 ))" ;;
        *)   err "Unexpected wal_segment_size: ${1}"; return ;;
    esac

}
postgresql-prune () {

    local age="${1}"

    shift
    parse-count "${age}" || { err "Invalid base backup age: ${age}"; return; }

    "$@" sh -c '
        cd /wal/base || exit
        newest="$(ls -1 | grep -v "\.part$" | sort | tail -n 1)"
        [ -n "$newest" ] || exit 0
        find . -mindepth 1 -maxdepth 1 -type d ! -name "$newest" ! -name "*.part" -mtime +"$1" -exec rm -rf {} + || exit
        oldest="$(ls -1 | grep -v "\.part$" | sort | head -n 1)"
        read -r segment _ < "$oldest/label" || exit
        exec pg_archivecleanup /wal/archive "$segment"' prune "${age}" || { err "The WAL archive could not be pruned"; return; }

}
postgresql-bases () {

    "$@" sh -c 'for label in /wal/base/*/label; do [ -f "$label" ] || continue; name="${label%/label}"; printf "%s " "${name##*/}"; cat "$label"; done' bases

}
postgresql-unpack () {

    local image="${1}" volume="${2}" archive="${3}" base="${4}" target="${5}" stamp="${6}"

    docker-oneshot --user 999:999 --memory 1g --cpus 1 --entrypoint sh \
        --mount "type=volume,source=${volume},target=/var/lib/postgresql" --mount "type=bind,source=${archive},target=/wal,readonly" -- "${image}" -c '
        set -eu
        data="$PGDATA"
        [ -d "$data" ] && [ ! -e "$data.before-$1" ] && [ -f "/wal/base/$2/base.tar.gz" ]
        mv "$data" "$data.before-$1"
        mkdir -m 700 "$data"
        tar -xzf "/wal/base/$2/base.tar.gz" -C "$data"
        printf "%s\n" "restore_command = '"'"'cp /wal/archive/%f %p'"'"'" "recovery_target_time = '"'"'$3'"'"'" "recovery_target_action = '"'"'promote'"'"'" >> "$data/postgresql.auto.conf"
        : > "$data/recovery.signal"' unpack "${stamp}" "${base}" "${target}" || { err "The base backup ${base} could not be unpacked"; return; }

}
postgresql-repack () {

    local image="${1}" volume="${2}" stamp="${3}"

    docker-oneshot --user 999:999 --memory 256m --entrypoint sh --mount "type=volume,source=${volume},target=/var/lib/postgresql" -- "${image}" \
        -c 'set -eu; data="$PGDATA"; [ -d "$data.before-$1" ]; rm -rf "$data"; mv "$data.before-$1" "$data"' repack "${stamp}" || { err "Move ${stamp} data back by hand"; return; }

}
postgresql-primary () {

    [[ "$("$@" sh -c 'exec psql -q -t -A -U "$POSTGRES_USER" -d postgres -c "SELECT pg_is_in_recovery()"' 2>/dev/null)" == f ]]

}
postgresql-settle () {

    printf '%s\n' 'ALTER SYSTEM RESET restore_command;' 'ALTER SYSTEM RESET recovery_target_time;' 'ALTER SYSTEM RESET recovery_target_action;' 'SELECT pg_reload_conf();' |
        postgresql-sql -- "$@" > /dev/null

}
postgresql-archiver () {

    "$@" sh -c 'exec psql -q -t -A -F " " -U "$POSTGRES_USER" -d postgres -c "SELECT coalesce(extract(epoch FROM now() - last_archived_time)::bigint, -1), coalesce(extract(epoch FROM now() - last_failed_time)::bigint, -1) FROM pg_stat_archiver"' archiver

}
