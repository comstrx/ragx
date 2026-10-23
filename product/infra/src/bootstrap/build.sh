bootstrap-bundle () {

    local mode="${1}" output="${TOOL_ROOT}/${MANIFEST[paths.build]}/${1}/infra"

    [[ "${TOOL_BUNDLED:-false}" != true ]] || { err "Builds require the source checkout"; return; }

    bundle-create "${TOOL_ROOT}" "${output}" "${mode}" "${MANIFEST[paths.source]}" "${MANIFEST[paths.tests]}" \
        "${MANIFEST[paths.templates]}" "${MANIFEST[paths.entrypoint]}" bootstrap/index.sh || return

    out "${output}"

}
bootstrap-build () {

    bootstrap-bundle dev

}
bootstrap-build-release () {

    local output="" digest=""

    output="$(bootstrap-bundle release)" || return
    digest="$(fs-hash "${output}")" || return

    printf '%s  infra\n' "${digest}" | fs-write "${output%/*}/SHA256SUMS" 644 || return

    out "${output}"

}
bootstrap-checksum () {

    fs-hash "${TOOL_ROOT}/${MANIFEST[paths.build]}/release/infra"

}
