#!/usr/bin/env bash

test_app_argv_keeps_every_argument_exact () {

    local argv=""

    argv="$(bash -c "source '${INFRA_BIN}'; app_argv python -m bootstrap 'two words' 'q\"uote'")"

    assert_eq "${argv}" '["python","-m","bootstrap","two words","q\"uote"]' "each argument becomes one json string, quotes escaped"

}
test_app_verdict_reads_the_job_status () {

    assert_ok "one success is a pass" bash -c "source '${INFRA_BIN}'; app_verdict '1/'"
    assert_fails "one failure is not a pass" bash -c "source '${INFRA_BIN}'; app_verdict '/1'"
    assert_fails "a running job is not a pass" bash -c "source '${INFRA_BIN}'; app_verdict '/'"
    assert_fails "a running job is not settled" bash -c "source '${INFRA_BIN}'; app_settled '/'"
    assert_ok "a failed job is settled" bash -c "source '${INFRA_BIN}'; app_settled '/1'"

}
test_app_polls_survive_a_pod_that_is_not_there_yet () {

    local bin=""

    bin="$(mktemp -d)"

    printf '#!/usr/bin/env bash\necho "error: array index out of bounds" >&2\nexit 1\n' > "${bin}/kubectl"
    chmod +x "${bin}/kubectl"

    assert_eq "$(PATH="${bin}:${PATH}" K8S_NAMESPACE=probe bash -c "set -Eeuo pipefail; source '${INFRA_BIN}'; phase=\"\$(app_phase job)\"; outcome=\"\$(app_outcome job)\"; printf '%s|%s|alive' \"\${phase}\" \"\${outcome}\"")" "||alive" "a failing kubectl yields an empty poll, never a dead script"

    rm -rf "${bin}"

}
test_app_manifest_runs_on_the_release () {

    local file="" build="" dst="" manifest=""

    file="$(mktemp)"
    build="$(mktemp -d)"
    dst="${build}/run.yaml"

    printf 'STACK=light\nPROJECT=probe\nBASE_DOMAIN=probe.test\n' > "${file}"

    export BUILD_DIR="${build}"

    INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; app_manifest '${dst}' probe-run registry/probe:abc123 python -m bootstrap" >/dev/null

    manifest="$(cat "${dst}")"

    assert_contains "${manifest}" "image: registry/probe:abc123" "the job runs the release image"
    assert_contains "${manifest}" 'command: ["python","-m","bootstrap"]' "the command is the argv, untouched"
    assert_contains "${manifest}" "name: api-owner-secrets" "the job reads the owner secrets — the migrations need the owner"
    assert_contains "${manifest}" "name: api-config" "the job reads the app config"
    assert_contains "${manifest}" "namespace: probe" "the job lands in the project namespace"
    assert_contains "${manifest}" "volumes: []" "an s3 stack mounts nothing"

    INFRA_CONFIG="$(realpath "${file}")" bash -c "source '${INFRA_BIN}'; config_load; app_manifest '${dst}' probe-run registry/probe:abc123 python -m bootstrap" >/dev/null

    assert_eq "$(INFRA_CONFIG="$(realpath "${file}")" STACK=standard bash -c "source '${INFRA_BIN}'; config_load; app_manifest '${dst}' probe-run registry/probe:abc123 true; grep -c 'claimName: api-storage' '${dst}'")" "1" "a pvc stack mounts the app storage"

    rm -rf "${file}" "${build}"

}
test_rollout_strategy_follows_the_stack () {

    local file="" build=""

    file="$(mktemp)"
    build="$(mktemp -d)"

    printf 'STACK=light\n' > "${file}"

    export BUILD_DIR="${build}"

    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting ROLLOUT_SURGE)" "0" "light swaps pods — no surge to schedule"
    assert_eq "$("${INFRA_BIN}" --config "${file}" ci setting ROLLOUT_UNAVAILABLE)" "1" "light lets one pod go during a rollout"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -s standard ci setting ROLLOUT_SURGE)" "1" "standard surges"
    assert_eq "$("${INFRA_BIN}" --config "${file}" -s light -e ROLLOUT_SURGE=2 ci setting ROLLOUT_SURGE)" "2" "an explicit value beats the stack"

    rm -rf "${file}" "${build}"

}
