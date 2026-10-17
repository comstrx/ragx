#!/usr/bin/env bash

test_every_verb_a_chain_calls_exists () {

    local chain="" verb="" missing=""

    for chain in ci_release server_ensure server_refresh server_deploy server_bootstrap compose_deploy edge_prepare audit_all; do

        while IFS= read -r verb; do

            [[ -n "$(bash -c "source '${INFRA_BIN}'; type -t '${verb}'")" ]] || missing+=" ${chain}→${verb}"

        done < <(bash -c "source '${INFRA_BIN}'; declare -f ${chain}" | grep -oE '^\s+[a-z_]+;?$' | tr -d ' ;')

    done

    assert_eq "${missing}" "" "every verb a chain calls is defined — a chain that names a ghost dies on the runner:${missing}"

}
test_the_release_line_ships_every_image () {

    local file="" build="" images=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    stack_probe_config "${file}"

    export BUILD_DIR="${build}"

    images="$("${INFRA_BIN}" --config "${file}" -y -e IMAGE_TAG_OVERRIDE=abc123 ci images)"

    assert_contains "${images}" "ghcr.io/comstrx/ragx/api:abc123" "the api ships"
    assert_contains "${images}" "ghcr.io/comstrx/ragx/api:backup-abc123" "the backup sidecar ships"
    assert_contains "${images}" "ghcr.io/comstrx/ragx/web:super-abc123" "the super panel ships"
    assert_contains "${images}" "ghcr.io/comstrx/ragx/web:client-abc123" "the client site ships"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -y -e IMAGE_TAG_OVERRIDE=abc123 -e WEB_ENABLED=false ci images | wc -l)" "2" "without the web only the api and its sidecar ship"

    rm -rf "${file}" "${build}"

}
test_the_roll_keeps_the_old_until_the_new_is_healthy () {

    local body="" up="" wait="" retire=""

    body="$(declare -f compose_roll)"
    up="$(grep -n -- '--no-recreate --scale' <<< "${body}" | head -1 | cut -d: -f1)"
    wait="$(grep -n 'compose_healthy' <<< "${body}" | head -1 | cut -d: -f1)"
    retire="$(grep -n 'compose_retire "${old\[@\]}"' <<< "${body}" | head -1 | cut -d: -f1)"

    assert_ne "${up}" "" "the roll starts the new beside the old"
    assert_ne "${retire}" "" "the roll retires the old"
    assert_ok "the new starts, is awaited, and only then the old retire" test "${up}" -lt "${wait}" -a "${wait}" -lt "${retire}"

}
