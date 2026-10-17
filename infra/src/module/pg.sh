#!/usr/bin/env bash

## the database — a superuser shell on the box, activity, sizes, slow statements, the tuning

pg_query () {

    compose_cmd exec -T postgres psql -U postgres -d "${2:-${DB_NAME}}" -v ON_ERROR_STOP=1 -c "${1:?Missing statement}"

}
## an interactive psql on the live database — superuser over the socket, the app role never gets a shell; args reach psql
pg_shell () {

    server_here || { server_forward pg shell "$@"; return; }

    compose_cmd exec postgres psql -U postgres -d "${DB_NAME}" "$@"

}
## who is doing what right now
pg_activity () {

    server_here || { server_forward pg activity; return; }

    pg_query "SELECT pid, usename, state, wait_event_type, now() - query_start AS age, left(query, 90) AS query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY query_start NULLS LAST"

}
## the database and its heaviest tables
pg_size () {

    server_here || { server_forward pg size; return; }

    pg_query "SELECT pg_size_pretty(pg_database_size(current_database())) AS database"
    pg_query "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15"

}
## the statements that cost the most
pg_slow () {

    server_here || { server_forward pg slow; return; }

    pg_query "SELECT calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 2) AS mean_ms, left(query, 90) AS query FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname = '${DB_NAME}') ORDER BY total_exec_time DESC LIMIT 15" postgres

}
## the memory settings this stack derives from PG_MEMORY_MB
pg_tune () {

    printf '%s\n' \
        "memory              ${PG_MEMORY_MB}MB (limit ${PG_MEMORY_LIMIT}, shm ${PG_SHM_SIZE})" \
        "max_connections     ${PG_MAX_CONNECTIONS}" \
        "shared_buffers      ${PG_SHARED_BUFFERS}" \
        "effective_cache     ${PG_EFFECTIVE_CACHE_SIZE}" \
        "work_mem            ${PG_WORK_MEM}" \
        "maintenance_work    ${PG_MAINTENANCE_WORK_MEM}" \
        "max_wal_size        ${PG_MAX_WAL_SIZE}" \
        "statement_timeout   ${PG_STATEMENT_TIMEOUT}" \
        "slow statement      ${PG_SLOW_MS}ms"

}
