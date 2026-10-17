#!/usr/bin/env bash

test_every_template_placeholder_has_a_source () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    assert_ok "the templates law holds" "${INFRA_BIN}" --config "${file}" -y ci templates
    assert_ok "the loader law holds" "${INFRA_BIN}" --config "${file}" -y ci loader

    rm -rf "${file}" "${build}"

}
test_credentials_are_url_encoded_and_origins_elide_default_ports () {

    assert_eq "$(bash -c "source '${INFRA_BIN}'; config_encode 'p@ss/w:rd+1'")" "p%40ss%2Fw%3Ard%2B1" "every reserved character is encoded"
    assert_eq "$(bash -c "source '${INFRA_BIN}'; config_encode 'plain.pass_word-1~'")" "plain.pass_word-1~" "unreserved characters pass"
    assert_eq "$(env SCHEME=https PUBLIC_PORT=443 bash -c "source '${INFRA_BIN}'; config_origin api.probe.test")" "https://api.probe.test" "https on 443 names no port"
    assert_eq "$(env SCHEME=http PUBLIC_PORT=80 bash -c "source '${INFRA_BIN}'; config_origin api.probe.test")" "http://api.probe.test" "http on 80 names no port"
    assert_eq "$(env SCHEME=https PUBLIC_PORT=8443 bash -c "source '${INFRA_BIN}'; config_origin api.probe.test")" "https://api.probe.test:8443" "any other port is named"

}
