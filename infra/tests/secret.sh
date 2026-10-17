#!/usr/bin/env bash

test_the_app_env_carries_the_runtime_secrets_and_the_extras_never_override () {

    local file="" build="" dir="" env=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dir="${build}/stack"

    stack_probe_config "${file}" "ENV_FILE=$(printf 'MAIL_PASSWORD=mail-pw\nDB_PASSWORD=stale-pw\nAPP_DEBUG=true\nMAIL_SENDER="hello@probe.test"\n' | base64 -w0)"

    export BUILD_DIR="${build}"

    stack_render "${file}" "${dir}"

    env="$(cat "${dir}/api.env")"

    assert_contains "${env}" "DB_PASSWORD='db-pw'" "the api logs in with the manifest password"
    assert_contains "${env}" "AUTH_SECRET='auth-pw'" "the api signs with the manifest secret"
    assert_contains "${env}" "MAIL_PASSWORD='mail-pw'" "an extra key rides in from ENV_FILE"
    assert_contains "${env}" "MAIL_SENDER='hello@probe.test'" "an extra key is requoted literally"
    assert_eq "$(grep -c 'stale-pw' "${dir}/api.env")" "0" "the manifest outranks a password ENV_FILE still carries"
    assert_eq "$(grep -c '^APP_DEBUG=' "${dir}/api.env")" "1" "a key the platform renders is rendered once"
    assert_contains "${env}" "APP_DEBUG='false'" "and the platform's value wins"

    rm -rf "${file}" "${build}"

}
test_a_quote_or_a_placeholder_in_a_secret_is_refused () {

    local file=""

    file="$(mktemp)"

    stack_probe_config "${file}" "DB_PASSWORD=it's"

    assert_fails "a single quote in a secret is refused — no env file carries it literally" env INFRA_CONFIG="${file}" bash -c "source '${INFRA_BIN}'; config_load; secret_clean"

    stack_probe_config "${file}" "ENV_FILE=$(printf 'MAIL_URL=${MAIL_HOST}\n' | base64 -w0)"

    assert_fails "a placeholder in ENV_FILE is refused — the containers expand nothing" env INFRA_CONFIG="${file}" bash -c "source '${INFRA_BIN}'; config_load; secrets_drift"

    stack_probe_config "${file}"

    assert_ok "clean secrets pass" env INFRA_CONFIG="${file}" bash -c "source '${INFRA_BIN}'; config_load; secret_clean; secrets_drift"

    rm -f "${file}"

}
test_required_secrets_grow_with_the_features () {

    local file="" required=""

    file="$(mktemp)"

    stack_probe_config "${file}"

    required="$(env INFRA_CONFIG="${file}" bash -c "source '${INFRA_BIN}'; config_load; secrets_required")"

    assert_contains "${required}" " PG_PASSWORD " "the cluster superuser password is required"
    assert_contains "${required}" " RABBITMQ_PASSWORD " "the broker password is required"
    assert_contains "${required}" " SSL_EMAIL " "tls needs an acme account owner"
    assert_eq "$(grep -c 'CLOUDFLARE_API_TOKEN' <<< "${required}")" "0" "no managed names, no token required"
    assert_eq "$(grep -c 'BACKUP_AWS' <<< "${required}")" "0" "local backups need no cloud keys"

    required="$(env INFRA_CONFIG="${file}" DNS_MANAGED=true BACKUP_TARGET=s3 APP_STORAGE=s3 TLS_ENABLED=false bash -c "source '${INFRA_BIN}'; config_load; secrets_required")"

    assert_contains "${required}" " CLOUDFLARE_API_TOKEN " "managed names require the token"
    assert_contains "${required}" " BACKUP_AWS_SECRET_ACCESS_KEY " "s3 backups require their keys"
    assert_contains "${required}" " STORAGE_S3_SECRET " "s3 files require their keys"
    assert_eq "$(grep -c 'SSL_EMAIL' <<< "${required}")" "0" "no tls, no acme owner"

    rm -f "${file}"

}
test_the_server_env_never_carries_the_way_in () {

    local file="" build="" rendered=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    rendered="${build}/.env"

    stack_probe_config "${file}" "SSH_PRIVATE_KEY=$(printf 'probe' | base64)" "SSH_PASSWORD=ssh-pw" "SSH_KEY=/tmp/nowhere"

    export BUILD_DIR="${build}"

    env INFRA_CONFIG="${file}" bash -c "source '${INFRA_BIN}'; config_load; config_render '${rendered}'"

    assert_eq "$(stat -c %a "${rendered}")" "600" "the server env is private"
    assert_eq "$(grep -c '^SSH_PRIVATE_KEY=\|^SSH_PASSWORD=\|^SSH_KEY=' "${rendered}")" "0" "the box never receives the way onto itself"
    assert_contains "$(cat "${rendered}")" "GIT_TOKEN=probe-token" "the box can pull its images"
    assert_contains "$(cat "${rendered}")" "DB_PASSWORD=db-pw" "the box can render its stack"
    assert_contains "$(cat "${rendered}")" "SSH_HOST=203.0.113.10" "the box knows it is the box"

    rm -rf "${file}" "${build}"

}
