#!/usr/bin/env bash

## the check — syntax, shellcheck at the configured severity, payload integrity, and no stray literals

check_literals () {

    local hits="" knobs=""

    hits="$(grep -nE 'https?://[a-z]' "${SOURCE_DIR}"/core/*.sh "${SOURCE_DIR}"/module/*.sh | grep -v '\${' || true)"
    knobs="$(grep -nE 'shellcheck .*(-e SC|-S [a-z])' "${SOURCE_DIR}"/core/*.sh "${SOURCE_DIR}"/module/*.sh || true)"

    [[ -z "${hits}" ]] || { printf '%s\n' "${hits}" >&2; die "Literal endpoints in src — every URL belongs in .env.example"; }
    [[ -z "${knobs}" ]] || { printf '%s\n' "${knobs}" >&2; die "Literal shellcheck knobs in src — SHELLCHECK_SEVERITY and SHELLCHECK_EXCLUDES belong in .env.example"; }

}
check_forge () {

    shellcheck -s bash -x -S "${SHELLCHECK_SEVERITY}" -e "${SHELLCHECK_EXCLUDES}" "${ROOT_DIR}/src/main.sh" "${ROOT_DIR}"/src/forge/*.sh || die "ShellCheck failed on the forge"

}
checker () {

    local code="" expected="" actual="" files=0

    ensure shellcheck

    code="$(mktemp --suffix=.sh)"
    code_of > "${code}"

    bash -n "${BIN}" || { rm -f "${code}"; die "Syntax check failed"; }
    shellcheck -s bash -x -S "${SHELLCHECK_SEVERITY}" -e "${SHELLCHECK_EXCLUDES}" "${code}" || { rm -f "${code}"; die "ShellCheck failed"; }
    rm -f "${code}"

    check_literals
    check_forge

    expected="$(payload_stamp)"
    actual="$(payload_of | sha256sum | cut -c1-64)"
    files="$(payload_of | tar tzf - | grep -c -v '/$')"

    [[ "${expected}" == "${actual}" ]] || die "Payload sha drifted: header ${expected:0:12}, payload ${actual:0:12}"
    (( files > 0 )) || die "Payload carries no files"

    succ "Check passed — ${TARGET} bundle, $(wc -l < "${BIN}") lines, ${files} template files, payload ${actual:0:12}"

}
