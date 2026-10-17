#!/usr/bin/env bash
# shellcheck disable=SC2034
# shellcheck disable=SC2034

## the forge's identity — read from the same defaults the bundle ships, never a second source

forge_key () {

    sed -n "s/^${1}=//p" "${ROOT_DIR}/.env.example" | head -1

}
forge_meta () {

    INFRA_NAME="$(forge_key INFRA_NAME)"
    INFRA_VERSION="$(forge_key INFRA_VERSION)"
    INFRA_REPO="$(forge_key INFRA_REPO)"
    INFRA_INSTALL_DIR="$(path_expand "$(forge_key INFRA_INSTALL_DIR)")"
    TARGET_DIR="${ROOT_DIR}/$(forge_key TARGET_DIR)"
    SHELLCHECK_EXCLUDES="$(forge_key SHELLCHECK_EXCLUDES)"
    SHELLCHECK_SEVERITY="$(forge_key SHELLCHECK_SEVERITY)"

    SOURCE_DIR="${ROOT_DIR}/src"
    TEST_DIR="${ROOT_DIR}/tests"
    TARGET="dev"
    BIN=""

    [[ -n "${INFRA_NAME}" && -n "${INFRA_VERSION}" ]] || die "The defaults file names no INFRA_NAME / INFRA_VERSION"

}
prepare () {

    BIN="${TARGET_DIR}/${TARGET}/${INFRA_NAME}.sh"

    ensure_dir "$(dirname -- "${BIN}")"

}
