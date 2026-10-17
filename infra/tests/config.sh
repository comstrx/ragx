#!/usr/bin/env bash

test_config_precedence () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=light\nPROJECT=filed\nWEB_MEMORY=777Mi\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting PROJECT)" "filed" "a --config file fills an empty default"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting WEB_MEMORY)" "777Mi" "a --config file beats a built-in default"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting ARGOCD_NAMESPACE)" "argocd" "a built-in default reaches the run"
    assert_eq "$(WEB_MEMORY=999Mi "${INFRA_BIN}" --config "${file}" ci setting WEB_MEMORY)" "999Mi" "the process env beats a --config file"
    assert_eq "$(JSON_ENV='{"WEB_MEMORY":"111Mi","FOREIGN_THING":"x"}' "${INFRA_BIN}" --config "${file}" ci setting WEB_MEMORY)" "111Mi" "JSON_ENV beats a --config file"
    assert_eq "$(JSON_ENV='{"FOREIGN_THING":"x"}' "${INFRA_BIN}" --config "${file}" ci setting FOREIGN_THING)" "" "JSON_ENV cannot smuggle a foreign key"
    assert_eq "$(WEB_MEMORY=999Mi "${INFRA_BIN}" --config "${file}" -e WEB_MEMORY=1Gi ci setting WEB_MEMORY)" "1Gi" "a flag beats everything"

    rm -rf "${file}" "${build}"

}
test_config_last_file_wins () {

    local one="" two="" build=""

    one="$(mktemp)"
    two="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=light\nWEB_MEMORY=1Mi\n' > "${one}"
    printf 'WEB_MEMORY=2Mi\n' > "${two}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${one}" --config "${two}" ci setting WEB_MEMORY)" "2Mi" "the last --config file wins"
    assert_eq "$("${INFRA_BIN}" --config "${two}" --config "${one}" ci setting WEB_MEMORY)" "1Mi" "order decides, not name"

    rm -rf "${one}" "${two}" "${build}"

}
test_defaults_are_neutral () {

    local key="" value="" biased="PROJECT BASE_DOMAIN GATEWAY_DOMAIN GIT_REPO_URL SSH_HOST AWS_REGION CLUSTER_NAME K8S_NAMESPACE IMAGE_NAME SSL_EMAIL ALARM_EMAIL ECR_REGISTRY S3_BUCKET S3_BACKUP_BUCKET TF_STATE_BUCKET CLOUDFLARE_DOMAIN_ID ALERT_CHAT_ID LOAD_TARGET_HOST"

    for key in ${biased}; do

        value="$(infra_defaults | sed -n "s/^${key}=//p")"

        assert_eq "${value}" "" "${key} carries a project-biased default"

    done

}
# test
manifests_are_disjoint_and_every_key_is_read () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=light\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_ok "the examples law holds" "${INFRA_BIN}" --config "${file}" secrets example

    rm -rf "${file}" "${build}"

}
