#!/usr/bin/env bash

test_config_precedence () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=staging\nPROJECT=filed\nAPI_MEMORY=777m\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PROJECT)" "filed" "a --config file fills an empty default"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting API_MEMORY)" "777m" "a --config file beats a built-in default"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting HTTP_PORT)" "80" "a built-in default reaches the run"
    assert_eq "$(API_MEMORY=999m "${INFRA_BIN}" --config "${file}" ci setting API_MEMORY)" "999m" "the process env beats a --config file"
    assert_eq "$(JSON_ENV='{"API_MEMORY":"111m","FOREIGN_THING":"x"}' "${INFRA_BIN}" --config "${file}" ci setting API_MEMORY)" "111m" "JSON_ENV beats a --config file"
    assert_eq "$(JSON_ENV='{"FOREIGN_THING":"x"}' "${INFRA_BIN}" --config "${file}" ci setting FOREIGN_THING)" "" "JSON_ENV cannot smuggle a foreign key"
    assert_eq "$(API_MEMORY=999m "${INFRA_BIN}" --config "${file}" -e API_MEMORY=1g ci setting API_MEMORY)" "1g" "a flag beats everything"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -s production ci setting STACK)" "production" "the stack flag beats the file"

    rm -rf "${file}" "${build}"

}
test_config_last_file_wins () {

    local one="" two="" build=""

    one="$(mktemp)"
    two="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\nAPI_MEMORY=1m\n' > "${one}"
    printf 'API_MEMORY=2m\n' > "${two}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${one}" --config "${two}" ci setting API_MEMORY)" "2m" "the last --config file wins"
    assert_eq "$("${INFRA_BIN}" --config "${two}" --config "${one}" ci setting API_MEMORY)" "1m" "order decides, not name"

    rm -rf "${one}" "${two}" "${build}"

}
test_defaults_are_neutral () {

    local key="" value="" biased="PROJECT BASE_DOMAIN GIT_REPO_URL SSH_HOST SSL_EMAIL CLOUDFLARE_ZONE_ID ALERT_CHAT_ID S3_BUCKET S3_BACKUP_BUCKET WATCH_TARGETS WEB_API_URL IMAGE_NAME"

    for key in ${biased}; do

        value="$(infra_defaults | sed -n "s/^${key}=//p")"

        assert_eq "${value}" "" "${key} carries a project-biased default"

    done

}
test_the_stack_chooses_the_acme_directory () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_contains "$("${INFRA_BIN}" --config "${file}" ci setting ACME_URL)" "acme-v02" "production asks the live directory"
    assert_contains "$("${INFRA_BIN}" --config "${file}" -s staging ci setting ACME_URL)" "acme-staging-v02" "staging asks the staging directory — rate limits never bite a rehearsal"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -s staging -e ACME_URL=https://acme.example/dir ci setting ACME_URL)" "https://acme.example/dir" "an explicit directory beats the stack"

    rm -rf "${file}" "${build}"

}
# test
manifests_are_disjoint_and_every_key_is_read () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_ok "the examples law holds" "${INFRA_BIN}" --config "${file}" secrets example

    rm -rf "${file}" "${build}"

}
