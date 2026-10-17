#!/usr/bin/env bash

test_payload_extracts_once_and_verifies () {

    local file="" build="" dir="" stamp=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\n' > "${file}"

    export BUILD_DIR="${build}" INFRA_DEV_TEMPLATE=""

    dir="$("${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"

    assert_contains "${dir}" "${build}/template/${INFRA_VERSION}-" "the templates unpack under the build dir, stamped by version"
    assert_ok "the compose file is in the payload" test -f "${dir}/compose/compose.yaml"
    assert_ok "the edge is in the payload" test -f "${dir}/nginx/nginx.conf"
    assert_ok "the web image recipe is in the payload" test -f "${dir}/docker/Dockerfile.web"
    assert_fails "no chart survived the kubernetes era" test -d "${dir}/helm"
    assert_fails "no tofu stack survived the kubernetes era" test -d "${dir}/tofu"
    assert_eq "$(cat "${dir}/.sha256")" "${INFRA_TEMPLATE_SHA}" "the extracted payload carries the header stamp"

    stamp="$(stat -c %Y "${dir}/.sha256")"
    sleep 1
    "${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR >/dev/null

    assert_eq "$(stat -c %Y "${dir}/.sha256")" "${stamp}" "a second run does not unpack again"

    rm -rf "${file}" "${build}"

}
test_payload_stays_readable_when_a_key_is_materialized () {

    local file="" build="" dir=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=production\n' > "${file}"

    export BUILD_DIR="${build}" INFRA_DEV_TEMPLATE=""

    dir="$(umask 022; SSH_PRIVATE_KEY="$(printf 'probe' | base64)" SSH_KEY="" "${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"

    assert_eq "$(stat -c %a "${dir}/docker/backup.sh")" "644" "a materialized ssh key never narrows the modes the payload unpacks with"
    assert_eq "$(stat -c %a "${dir}/compose/compose.yaml")" "644" "every template stays readable beyond the user that unpacked it"

    rm -rf "${file}" "${build}"

}
test_payload_refuses_a_tampered_bundle () {

    local file="" build="" copy="" output=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    copy="${build}/tampered.sh"

    printf 'STACK=production\n' > "${file}"

    export BUILD_DIR="${build}" INFRA_DEV_TEMPLATE=""

    sed '$ { s/^#A/#B/; t; s/^#\(.\)/#A/; }' "${INFRA_BIN}" > "${copy}"
    chmod +x "${copy}"

    output="$(INFRA_BIN="${copy}" "${copy}" --config "${file}" ci setting TEMPLATE_DIR 2>&1 || true)"

    assert_contains "${output}" "corrupt" "a bundle whose payload changed refuses to unpack"
    assert_fails "nothing was unpacked" test -d "${build}/template"

    rm -rf "${file}" "${build}"

}
