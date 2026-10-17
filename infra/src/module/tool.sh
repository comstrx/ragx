#!/usr/bin/env bash

## self-provisioning — every verb installs its own missing tools

tool_arch () {

    local arch=""

    arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"

    case "${arch}" in
        x86_64  ) arch=amd64 ;;
        aarch64 ) arch=arm64 ;;
    esac

    printf '%s' "${arch}"

}
tool_curl () {

    pkg_install curl

}
tool_envsubst () {

    pkg_install gettext-base

}
tool_flock () {

    pkg_install util-linux

}
tool_jq () {

    pkg_install jq

}
tool_sshpass () {

    pkg_install sshpass

}
tool_openssl () {

    pkg_install openssl

}
tool_certs () {

    [[ -f "${CA_BUNDLE}" ]] || pkg_install ca-certificates

}
tool_bin () {

    local file="${1:?Missing binary}" name="${2:?Missing name}"

    if [[ "$(id -u)" == "0" ]] || sudo -n true 2>/dev/null; then

        as_root install -o root -g root -m 0755 "${file}" "${TOOL_BIN_DIR}/${name}"

    else

        ensure_dir "$(path_expand "${INFRA_INSTALL_DIR}")"
        install -m 0755 "${file}" "$(path_expand "${INFRA_INSTALL_DIR}")/${name}"

    fi

}
tool_actionlint () {

    local dir=""

    ensure curl tar
    tool_certs

    dir="$(tmp_dir)"

    curl -fsSL "${ACTIONLINT_RELEASES}/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_$(tool_arch).tar.gz" \
        | tar xz -C "${dir}" actionlint || die "Cannot download actionlint ${ACTIONLINT_VERSION}"

    tool_bin "${dir}/actionlint" actionlint

    rm -rf "${dir}"

}
tool_gitleaks () {

    local dir="" arch=""

    ensure curl tar
    tool_certs

    dir="$(tmp_dir)"
    arch="$(tool_arch)"

    [[ "${arch}" != "amd64" ]] || arch=x64

    curl -fsSL "${GITLEAKS_RELEASES}/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${arch}.tar.gz" \
        | tar xz -C "${dir}" gitleaks || die "Cannot download gitleaks ${GITLEAKS_VERSION}"

    tool_bin "${dir}/gitleaks" gitleaks

    rm -rf "${dir}"

}
tool_trivy () {

    local dir="" arch=""

    ensure curl tar
    tool_certs

    dir="$(tmp_dir)"
    arch="$(tool_arch)"

    [[ "${arch}" != "amd64" ]] || arch=64bit
    [[ "${arch}" != "arm64" ]] || arch=ARM64

    curl -fsSL "${TRIVY_RELEASES}/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${arch}.tar.gz" \
        | tar xz -C "${dir}" trivy || die "Cannot download trivy ${TRIVY_VERSION}"

    tool_bin "${dir}/trivy" trivy

    rm -rf "${dir}"

}
tool_docker () {

    local os="" codename="" conflict=""

    ensure curl
    tool_certs

    os="$(. /etc/os-release && printf '%s' "${ID}")"
    codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}")"

    case "${os}" in
        ubuntu | debian | raspbian ) ;;
        * ) os="$(. /etc/os-release && printf '%s' "${ID_LIKE%% *}")" ;;
    esac

    [[ -n "${os}" && -n "${codename}" ]] || die "Cannot resolve the distro for the docker repo"

    for conflict in docker.io docker-doc docker-compose podman-docker containerd runc; do

        as_root apt-get remove -y "${conflict}" >/dev/null 2>&1 || true

    done

    as_root install -m 0755 -d "${APT_KEYRINGS}"

    curl -fsSL "${DOCKER_APT_URL}/${os}/gpg" | as_root tee "${APT_KEYRINGS}/docker.asc" >/dev/null || die "Cannot fetch the docker signing key"
    as_root chmod a+r "${APT_KEYRINGS}/docker.asc"

    printf 'deb [arch=%s signed-by=%s/docker.asc] %s/%s %s stable\n' \
        "$(tool_arch)" "${APT_KEYRINGS}" "${DOCKER_APT_URL}" "${os}" "${codename}" | as_root tee "${APT_SOURCES}/docker.list" >/dev/null

    pkg_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    ! has systemctl || as_root systemctl enable --now docker

    [[ "$(id -u)" == "0" ]] || as_root usermod -aG docker "$(id -un)"

}
## install any listed tool if missing (docker, jq, trivy, gitleaks, actionlint, ...)
tool_ensure () {

    ensure "$@"

}
