#!/usr/bin/env bash

secret_probe_config () {

    local file="${1:?secret_probe_config needs a file}"

    printf 'STACK=light\nPROJECT=probe\nBASE_DOMAIN=probe.test\nDB_APP_USER=probe_app\nDB_PASSWORD=owner-pw\nDB_APP_PASSWORD=app-pw\nREDIS_PASSWORD=redis-pw\nENV_FILE=%s\n' \
        "$(printf 'APP_KEY=base64:probe\nDB_PASSWORD=stale-pw\nDB_MIGRATE_PASSWORD=leaked-pw\n' | base64 -w0)" > "${file}"

}
test_the_app_secret_carries_the_runtime_login_and_never_the_owner_password () {

    local file="" build="" app="" owner=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    app="${build}/app.env"
    owner="${build}/owner.env"

    secret_probe_config "${file}"

    export BUILD_DIR="${build}"

    INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; secret_env_file '${app}'; secret_env_file '${owner}' owner" >/dev/null

    assert_contains "$(cat "${app}")" "DB_PASSWORD=app-pw" "the pods log in as the runtime role"
    assert_eq "$(grep -c 'owner-pw' "${app}")" "0" "the owner password never reaches an app pod"
    assert_eq "$(grep -c '^DB_MIGRATE_PASSWORD=' "${app}")" "0" "the app secret carries no migrate login"
    assert_eq "$(grep -c 'stale-pw' "${app}")" "0" "the manifest outranks a password ENV_FILE still carries"
    assert_eq "$(grep -c 'leaked-pw' "${app}")" "0" "an owner password smuggled through ENV_FILE never reaches an app pod"
    assert_contains "$(cat "${owner}")" "DB_PASSWORD=app-pw" "the owner scope still runs the app as the runtime role"
    assert_contains "$(cat "${owner}")" "DB_MIGRATE_PASSWORD=owner-pw" "the owner scope carries the owner password for the hook"
    assert_contains "$(cat "${app}")" "APP_KEY=base64:probe" "the app env still rides in"

    rm -rf "${file}" "${build}"

}
test_without_a_split_one_password_serves_and_no_owner_login_is_added () {

    local file="" build="" app="" owner=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    app="${build}/app.env"
    owner="${build}/owner.env"

    printf 'STACK=light\nPROJECT=probe\nDB_PASSWORD=owner-pw\nREDIS_PASSWORD=redis-pw\n' > "${file}"

    export BUILD_DIR="${build}"

    INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; secret_env_file '${app}'; secret_env_file '${owner}' owner" >/dev/null

    assert_contains "$(cat "${app}")" "DB_PASSWORD=owner-pw" "the owner serves when the roles are not split"
    assert_eq "$(cat "${app}")" "$(cat "${owner}")" "both scopes agree when there is one role"

    rm -rf "${file}" "${build}"

}
test_the_runtime_password_is_required_once_the_roles_split () {

    local file=""

    file="$(mktemp)"

    secret_probe_config "${file}"

    assert_contains "$(INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; secrets_required")" " DB_APP_PASSWORD " "a split manifest cannot release without the runtime password"

    printf 'STACK=light\nPROJECT=probe\n' > "${file}"

    assert_eq "$(INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; secrets_required" | grep -c 'DB_APP_PASSWORD')" "0" "one role asks for one password"

    rm -f "${file}"

}
test_the_owner_secret_reaches_only_the_hook_the_run_jobs_and_the_backup () {

    local file="" dir=""

    file="$(mktemp)"

    printf 'STACK=light\nPROJECT=owned\n' > "${file}"

    dir="$("${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"

    assert_contains "$(cat "${dir}/helm/service/templates/migrate.yaml")" 'service.ownerSecretRef' "the migrate hook reads the owner secret"
    assert_contains "$(cat "${dir}/k8s/run.yaml")" 'owner-secrets' "a run job reads the owner secret"
    assert_eq "$(grep -c 'owner' "${dir}/helm/service/templates/deployment.yaml")" "0" "the app pods never read the owner secret"

    rm -f "${file}"

}
test_the_roles_take_the_passwords_before_any_secret_carries_them () {

    local body="" roles="" secrets="" pods=""

    body="$(declare -f k8s_secrets)"
    roles="$(grep -n 'k8s_platform_passwords' <<< "${body}" | head -1 | cut -d: -f1)"
    secrets="$(grep -n 'create secret generic' <<< "${body}" | head -1 | cut -d: -f1)"

    assert_ne "${roles}" "" "the secrets step moves the roles"
    assert_ok "the roles take the passwords before the first secret is written" test "${roles}" -lt "${secrets}"

    body="$(declare -f k8s_rotate)"
    secrets="$(grep -n 'k8s_secrets' <<< "${body}" | head -1 | cut -d: -f1)"
    pods="$(grep -n 'rollout restart deployment' <<< "${body}" | head -1 | cut -d: -f1)"

    assert_ok "the secrets land before the pods restart" test "${secrets}" -lt "${pods}"

}
test_the_app_secret_carries_the_scoped_storage_keys_when_the_manifest_names_them () {

    local file="" build="" app=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    app="${build}/app.env"

    printf 'STACK=light\nPROJECT=probe\nDB_PASSWORD=owner-pw\nREDIS_PASSWORD=redis-pw\nAPP_AWS_ACCESS_KEY_ID=AKIAPROBE\nAPP_AWS_SECRET_ACCESS_KEY=probe-secret\n' > "${file}"

    export BUILD_DIR="${build}"

    INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; secret_env_file '${app}'" >/dev/null

    assert_contains "$(cat "${app}")" "AWS_ACCESS_KEY_ID=AKIAPROBE" "the pods log into storage with the scoped key"
    assert_contains "$(cat "${app}")" "AWS_SECRET_ACCESS_KEY=probe-secret" "the pods carry the scoped secret"

    rm -rf "${file}" "${build}"

}
test_the_backup_secret_carries_the_scoped_backup_keys_from_the_manifest () {

    local body="" filtered="" minted="" created=""

    body="$(declare -f k8s_secrets)"
    filtered="$(grep -n 'BACKUP_SECRET_KEYS' <<< "${body}" | head -1 | cut -d: -f1)"
    minted="$(grep -n 'BACKUP_AWS_SECRET_ACCESS_KEY=%s' <<< "${body}" | head -1 | cut -d: -f1)"
    created="$(grep -n 'backup-secrets' <<< "${body}" | head -1 | cut -d: -f1)"

    assert_ne "${minted}" "" "the backup secret learns the scoped backup keys from the manifest"
    assert_ok "the keys join the filtered owner env before the backup secret is written" test "${filtered}" -lt "${minted}" -a "${minted}" -lt "${created}"

}
