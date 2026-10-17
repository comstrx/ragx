#!/usr/bin/env bash

## the bundle itself — version, location, update

## the running version and the template stamp it carries
self_version () {

    printf '%s %s\ntemplates %s\n' "${INFRA_NAME}" "${INFRA_VERSION}" "${INFRA_TEMPLATE_SHA:0:12}"

}
## where the running bundle lives and where its templates unpack
self_where () {

    printf '%s\n%s\n' "${INFRA_BIN}" "${TEMPLATE_DIR}"

}
## every key the bundle reads — names only, defaults then secrets
self_keys () {

    infra_defaults | sed -nE 's/^([A-Z][A-Z0-9_]*)=.*/\1/p'
    secret_keys

}
## replace this bundle with a released one — latest, or a tag — verified against its SHA256SUMS
self_update () {

    local tag="${1:-latest}" base="" dir="" version=""

    ensure curl

    [[ -n "${INFRA_REPO}" ]] || die "INFRA_REPO is empty — nowhere to update from"

    if [[ "${tag}" == "latest" ]]; then base="${GITHUB_URL}/${INFRA_REPO}/releases/latest/download"; else base="${GITHUB_URL}/${INFRA_REPO}/releases/download/${tag}"; fi

    dir="$(tmp_dir)"

    curl -fsSL "${base}/${INFRA_NAME}.sh" -o "${dir}/${INFRA_NAME}.sh" || die "Cannot download ${tag} from ${INFRA_REPO}"
    curl -fsSL "${base}/SHA256SUMS" -o "${dir}/SHA256SUMS" || die "Cannot download the checksums of ${tag}"

    ( cd "${dir}" && sha256sum --check --quiet SHA256SUMS ) || die "Checksum mismatch — refusing ${tag}"

    bash -n "${dir}/${INFRA_NAME}.sh" || die "The downloaded bundle does not parse"

    version="$(sed -n 's/^INFRA_VERSION="\(.*\)"$/\1/p' "${dir}/${INFRA_NAME}.sh")"

    if [[ -w "${INFRA_BIN}" ]]; then install -m 0755 "${dir}/${INFRA_NAME}.sh" "${INFRA_BIN}"; else as_root install -m 0755 "${dir}/${INFRA_NAME}.sh" "${INFRA_BIN}"; fi

    rm -rf "${dir}"

    succ "${INFRA_NAME} ${INFRA_VERSION} → ${version} at ${INFRA_BIN}"

}
