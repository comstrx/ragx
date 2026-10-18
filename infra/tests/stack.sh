#!/usr/bin/env bash

stack_template_dir () {

    local file=""

    file="$(mktemp)"

    printf 'STACK=production\nPROJECT=topo\n' > "${file}"

    "${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR

    rm -f "${file}"

}
test_the_compose_file_carries_the_production_topology () {

    local dir="" compose=""

    dir="$(stack_template_dir)"
    compose="$(cat "${dir}/compose/compose.yaml")"

    assert_contains "${compose}" "no-new-privileges:true" "no container gains privileges"
    assert_contains "${compose}" "cap_drop:" "every container drops its capabilities"
    assert_eq "$(grep -c 'read_only: true' <<< "${compose}")" "7" "the api, the web, the edge, the data services and the backup run on a read-only root"
    assert_contains "${compose}" "internal: true" "the data network has no way out"
    assert_eq "$(grep -cE '^\s+- "[^"]*:(5432|5672|6379)"' <<< "${compose}")" "0" "no data service is published"
    assert_contains "${compose}" "user: '999:999'" "postgres runs as its own uid"
    assert_contains "${compose}" "user: '100:101'" "rabbitmq runs as its own uid"
    assert_contains "${compose}" "user: '999:1000'" "redis runs as its own uid"
    assert_contains "$(infra_defaults | sed -n 's/^NGINX_IMAGE=//p')" "nginx-unprivileged" "the edge is the unprivileged image"
    assert_contains "${compose}" ":8443/udp'" "http/3 is published"
    assert_contains "${compose}" "command: [work]" "the worker runs the queue"
    assert_contains "${compose}" "command: [schedule]" "the scheduler runs the schedule"
    assert_contains "${compose}" "profiles: [worker]" "the worker is a profile"
    assert_contains "${compose}" "profiles: [scheduler]" "the scheduler is a profile"
    assert_contains "${compose}" "profiles: [web]" "the web is a profile"
    assert_contains "${compose}" "profiles: [ops]" "the operations never run by themselves"
    assert_contains "${compose}" "condition: service_healthy" "the api waits for healthy data services"
    assert_contains "${compose}" "storage:/app/src/storage" "uploads and logs outlive the container"
    assert_contains "${compose}" "pgdata:/var/lib/postgresql" "postgres 18 keeps its data under the new mount point"
    assert_contains "${compose}" "stop_grace_period: 90s" "postgres gets time to checkpoint"
    assert_eq "$(grep -c 'privileged: true' <<< "${compose}")" "0" "nothing is privileged"
    assert_eq "$(grep -c 'latest' <<< "${compose}")" "0" "no floating tag"

}
test_the_data_services_carry_the_strongest_settings () {

    local dir=""

    dir="$(stack_template_dir)"

    assert_contains "$(cat "${dir}/postgres/postgresql.conf")" "password_encryption = scram-sha-256" "postgres hashes with scram"
    assert_contains "$(cat "${dir}/postgres/postgresql.conf")" "shared_preload_libraries = 'pg_stat_statements'" "postgres measures its statements"
    assert_contains "$(cat "${dir}/postgres/postgresql.conf")" "io_method = worker" "postgres 18 asynchronous io"
    assert_contains "$(cat "${dir}/postgres/postgresql.conf")" "wal_compression = zstd" "wal is compressed"
    assert_contains "$(cat "${dir}/postgres/postgresql.conf")" "idle_in_transaction_session_timeout = 60s" "an abandoned transaction is cut"
    assert_eq "$(grep -c 'trust' "${dir}/postgres/pg_hba.conf")" "0" "nobody is trusted"
    assert_contains "$(cat "${dir}/postgres/pg_hba.conf")" "host    all   postgres        all             reject" "the superuser never logs in over the network"
    assert_contains "$(cat "${dir}/postgres/init.sh")" "NOSUPERUSER NOCREATEROLE NOBYPASSRLS" "the app role cannot bypass row security"
    assert_contains "$(cat "${dir}/postgres/init.sh")" "REVOKE CONNECT ON DATABASE" "the public has no door"
    assert_contains "$(cat "${dir}/rabbitmq/platform.conf")" "loopback_users = none" "no default loopback user"
    assert_contains "$(cat "${dir}/rabbitmq/platform.conf")" "default_queue_type = quorum" "queues are quorum by default"
    assert_contains "$(cat "${dir}/rabbitmq/platform.conf")" "vm_memory_high_watermark.relative = 0.6" "the broker respects its memory"
    assert_contains "$(cat "${dir}/compose/compose.yaml")" "--user default off resetpass -@all" "the default redis user is dead"
    assert_contains "$(cat "${dir}/compose/compose.yaml")" "+@all -@dangerous" "the cache user never runs a dangerous command"
    assert_contains "$(cat "${dir}/redis/redis.conf")" "maxmemory-policy allkeys-lru" "the cache evicts instead of failing"
    assert_contains "$(cat "${dir}/redis/redis.conf")" 'save ""' "the cache persists nothing"

}
test_the_backup_dumps_restores_aside_and_lists () {

    local dir="" script=""

    dir="$(stack_template_dir)"
    script="$(cat "${dir}/docker/backup.sh")"

    assert_contains "${script}" "pg_dump -h" "the backup is a pg_dump"
    assert_contains "${script}" "-Fc -Z zstd" "the dump is custom format, zstd compressed"
    assert_contains "${script}" "Refusing to restore over" "a restore never lands on the live database"
    assert_contains "${script}" '"${MODE}" = "list"' "the script lists what it stored"
    assert_contains "$(cat "${dir}/systemd/backup.timer")" "Persistent=true" "a missed backup runs at the next boot"
    assert_contains "$(cat "${dir}/systemd/backup.service")" 'User=${SSH_USER}' "the backup runs as the deploy user"

}
test_the_images_run_as_nobody_special () {

    local dir=""

    dir="$(stack_template_dir)"

    assert_contains "$(cat "${dir}/docker/Dockerfile")" "USER 33:33" "the api image runs as uid 33"
    assert_contains "$(cat "${dir}/docker/Dockerfile")" "HEALTHCHECK" "the api image answers a health check"
    assert_contains "$(cat "${dir}/docker/Dockerfile")" 'ENTRYPOINT ["python", "-m", "bootstrap"]' "the api image boots the bootstrap"
    assert_contains "$(cat "${dir}/docker/Dockerfile.web")" "USER 1000:1000" "the web image runs as uid 1000"
    assert_contains "$(cat "${dir}/docker/Dockerfile.web")" 'ENTRYPOINT ["bun", "tools/serve.js"]' "the web image serves through the bundled release server"
    assert_contains "$(cat "${dir}/docker/Dockerfile.web")" "SPEC_API_URL" "the deployment decides the api origin the web is built against"
    assert_contains "$(cat "${dir}/docker/Dockerfile.web")" "bun build tools/serve.ts --target=bun" "the release server is bundled — the web image ships no node_modules"
    assert_contains "$(cat "${dir}/compose/compose.yaml")" "/app/.next/out/standalone/.next/cache:mode=1777" "a standalone site writes its cache on a tmpfs, the root stays read-only"

}
test_postgres_memory_follows_the_knob () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\nPG_MEMORY_MB=2048\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PG_SHARED_BUFFERS)" "512MB" "a quarter for shared buffers"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PG_EFFECTIVE_CACHE_SIZE)" "1536MB" "three quarters for the planner"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PG_WORK_MEM)" "5242kB" "work_mem is a quarter divided by the connections"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PG_MAINTENANCE_WORK_MEM)" "128MB" "a sixteenth for maintenance"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PG_MEMORY_LIMIT)" "2560m" "the container keeps a quarter of headroom"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e PG_MEMORY_MB=256 ci setting PG_WORK_MEM)" "4096kB" "work_mem never drops under 4MB"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -e PG_SHARED_BUFFERS=1GB ci setting PG_SHARED_BUFFERS)" "1GB" "an explicit value beats the knob"

    rm -rf "${file}" "${build}"

}
