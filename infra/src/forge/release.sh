#!/usr/bin/env bash

## the release — a GitHub release carrying the bundle and its SHA256SUMS, notes from the changelog

release_notes () {

    local file="${ROOT_DIR}/CHANGELOG.md"

    [[ -f "${file}" ]] || { printf '%s %s\n' "${INFRA_NAME}" "v${INFRA_VERSION}"; return 0; }

    sed -n "/^## ${INFRA_VERSION}\$/,/^## /{ /^## /d; p; }" "${file}"

}
releaser () {

    local tag="v${INFRA_VERSION}" dir="" notes=""

    ensure gh

    dir="$(dirname -- "${BIN}")"
    notes="$(release_notes)"

    [[ -n "${notes}" ]] || die "CHANGELOG.md carries no section for ${INFRA_VERSION}"

    gh release view "${tag}" --repo "${INFRA_REPO}" >/dev/null 2>&1 && die "Release ${tag} already exists — bump INFRA_VERSION first"

    gh release create "${tag}" "${BIN}" "${dir}/SHA256SUMS" --repo "${INFRA_REPO}" --title "${INFRA_NAME} ${tag}" --notes "${notes}" "$@" \
        || die "Release failed"

    succ "Released ${tag}"

}
