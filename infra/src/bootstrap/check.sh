bootstrap-prepare () {

    local version="${MANIFEST[tools.shellcheck]}" platform="" architecture="" digest="" path="${TOOL_ROOT}/${MANIFEST[paths.build]}/tools"

    platform="$(kernel)" || return
    platform="${platform,,}"
    architecture="$(uname -m)" || { err "Architecture detection failed"; return; }
    [[ "${architecture}" != arm64 ]] || architecture=aarch64

    digest="$(manifest-get "downloads.shellcheck_${platform}_${architecture}")" || return
    fs-dir "${path}" || return

    package-artifact "https://github.com/koalaman/shellcheck/releases/download/v${version}/shellcheck-v${version}.${platform}.${architecture}.tar.xz" \
        "${digest}" "shellcheck-v${version}/shellcheck" "${path}/shellcheck" || return

    out "${path}"

}
bootstrap-check () {

    local bundle="" file="" version="" failed=0

    if [[ "${TOOL_BUNDLED:-false}" == true ]]; then bundle="${TOOL_BIN}"
    else bundle="$(bootstrap-bundle dev)" || return
    fi

    bash -n "${bundle}" || failed=1
    need shellcheck || return

    version="$(shellcheck --version)" || { err "ShellCheck version unreadable"; return; }
    [[ "${version}" == *"version: ${MANIFEST[tools.shellcheck]}"* ]] || warn "ShellCheck differs from Bash.toml ${MANIFEST[tools.shellcheck]}; run prepare for the pinned build"

    shellcheck --shell=bash --severity="${MANIFEST[check.severity]}" --exclude="${MANIFEST[check.excludes]}" "${bundle}" || failed=1

    if [[ "${TOOL_BUNDLED:-false}" != true ]]; then

        while IFS= read -r -d '' file; do
            bash -n "${file}" || failed=1
        done < <(fs-files "${TOOL_SOURCE}" .sh)

        bootstrap-laws || failed=1

    fi

    (( failed == 0 )) || { err "Check failed"; return; }

    succ "Syntax, ShellCheck, layer and style laws passed"

}
