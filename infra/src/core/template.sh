#!/usr/bin/env bash

## the template payload — one bundle, one extraction per version, verified

template_dir () {

    if [[ -n "${INFRA_DEV_TEMPLATE:-}" && -d "${INFRA_DEV_TEMPLATE}" ]]; then

        printf '%s' "${INFRA_DEV_TEMPLATE}"
        return 0

    fi

    printf '%s' "${BUILD_DIR}/template/${INFRA_VERSION}-${INFRA_TEMPLATE_SHA:0:12}"

}
template_payload () {

    sed -n '/^#__INFRA_PAYLOAD__$/,$p' "${INFRA_BIN}" | tail -n +2 | sed 's/^#//' | base64 -d

}
template_ensure () {

    local tmp="" archive="" sha=""

    [[ "${TEMPLATE_DIR}" != "${INFRA_DEV_TEMPLATE:-}" ]] || return 0
    [[ ! -f "${TEMPLATE_DIR}/.sha256" ]] || return 0

    tmp="$(tmp_dir)"
    archive="${tmp}/template.tgz"

    template_payload > "${archive}" || die "The bundle carries no readable template payload"

    sha="$(sha256sum "${archive}" | cut -c1-64)"

    [[ "${sha}" == "${INFRA_TEMPLATE_SHA}" ]] || die "Template payload is corrupt — expected ${INFRA_TEMPLATE_SHA:0:12}, got ${sha:0:12}"

    tar xzf "${archive}" -C "${tmp}" || die "Cannot unpack the template payload"

    ensure_dir "$(dirname "${TEMPLATE_DIR}")"
    rm -rf "${TEMPLATE_DIR}"
    mv "${tmp}/template" "${TEMPLATE_DIR}" || die "Cannot place the templates: ${TEMPLATE_DIR}"

    printf '%s\n' "${sha}" > "${TEMPLATE_DIR}/.sha256"
    rm -rf "${tmp}"

}
