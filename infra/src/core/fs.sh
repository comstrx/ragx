#!/usr/bin/env bash

ensure_dir () {

    local dir="${1:-}"

    [[ -d "${dir}" ]] || mkdir -p "${dir}" || die "Cannot mkdir: ${dir}"

}
tmp_file () {

    mktemp || die "Cannot create temp file"

}
tmp_dir () {

    mktemp -d || die "Cannot create temp dir"

}
placeholders () {

    local file="${1:-}"

    grep -oE '\$\{[A-Za-z_][A-Za-z0-9_]*\}' "${file}" 2>/dev/null | sort -u | tr -d "\${}"

}
render () {

    local src="${1:-}" dst="${2:-}" key="" list=""

    [[ -f "${src}" ]] || die "Missing template: ${src}"

    ensure envsubst

    for key in $(placeholders "${src}"); do

        [[ -n "${!key+x}" ]] || die "Render '$(basename "${src}")' missing: ${key}"

        list+="\${${key}} "

    done

    ensure_dir "$(dirname "${dst}")"

    envsubst "${list}" < "${src}" > "${dst}" || die "Cannot render: ${src}"

}
path_expand () {

    printf '%s' "${1/#\~/${HOME}}"

}
