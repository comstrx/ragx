#!/usr/bin/env bash

test_render_fills_placeholders_and_refuses_missing_ones () {

    local src="" dst=""

    src="$(mktemp)"
    dst="$(mktemp)"

    printf 'name: ${PROBE_NAME}\n' > "${src}"

    PROBE_NAME=probe render "${src}" "${dst}"

    assert_eq "$(cat "${dst}")" "name: probe" "a placeholder renders from the environment"
    assert_fails "an undefined placeholder refuses to render" env -u PROBE_NAME bash -c "source '${INFRA_BIN}'; render '${src}' '${dst}'"

    rm -f "${src}" "${dst}"

}
test_the_backup_dumps_as_the_schema_owner () {

    local file="" dir=""

    file="$(mktemp)"

    printf 'STACK=light\nPROJECT=owned\n' > "${file}"

    dir="$("${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"

    assert_contains "$(cat "${dir}/docker/backup.sh")" 'DB_MIGRATE_USERNAME:-' "the dump prefers the migrate (owner) role over the runtime role"
    assert_contains "$(cat "${dir}/docker/backup.sh")" 'DB_MIGRATE_PASSWORD:-' "the dump prefers the owner password"
    assert_contains "$("${INFRA_BIN}" --config "${file}" ci setting BACKUP_SECRET_KEYS)" 'DB_MIGRATE_USERNAME' "the backup secret carries the owner role"
    assert_contains "$("${INFRA_BIN}" --config "${file}" ci setting BACKUP_SECRET_KEYS)" 'DB_MIGRATE_PASSWORD' "the backup secret carries the owner password"

    rm -f "${file}"

}

