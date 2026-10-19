bundle-relative () {

    [[ "${1:-}" =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ && "/${1}/" != */../* ]]

}
bundle-sources () {

    local root="${1}" source="${2}" entry="${3}" templates="${4}" file="" relative=""
    local -a embedded=()

    printf 'embedded-source () {\n\n    case "${1}" in\n'

    while IFS= read -r -d '' file; do

        [[ "${file}" != "${root}/${entry}" && "${file}" != "${root}/${templates}/"* ]] || continue

        relative="${file#"${root}/${source}/"}"
        [[ "${relative}" =~ ^[a-z0-9_-]+(/[a-z0-9_-]+)*\.sh$ ]] || { err "Invalid source name: ${relative}"; return; }
        embedded+=( "${relative}" )

        printf "        '%s')\n" "${relative}"
        fs-read "${file}" || return
        printf '\n        ;;\n'

    done < <(fs-files "${root}/${source}" .sh)

    printf '        *) err "Missing source: ${1}" ;;\n    esac\n\n}\n'
    printf 'embedded-sources () {\n\n'
    printf '    printf '"'"'%%s\\n'"'"
    printf " '%s'" "${embedded[@]}"
    printf '\n\n}\n'

}
bundle-assets () {

    local root="${1}" templates="${2}" file="" relative="" digest=""
    local -a assets=( "${root}/Bash.toml" "${root}/.env.example" )

    while IFS= read -r -d '' file; do
        assets+=( "${file}" )
    done < <(fs-files "${root}/${templates}")

    printf 'embedded-asset () {\n\n    case "${1}" in\n'

    for file in "${assets[@]}"; do

        relative="${file#"${root}/"}"
        bundle-relative "${relative}" || { err "Invalid asset name: ${relative}"; return; }
        digest="$(fs-hash "${file}")" || return

        printf "        '%s') cat <<'ASSET_%s'\n" "${relative}" "${digest}"
        fs-read "${file}" || return
        printf '\nASSET_%s\n        ;;\n' "${digest}"

    done

    printf '        *) err "Missing asset: ${1}" ;;\n    esac\n\n}\n'

}
bundle-create () {

    local root="${1}" output="${2}" mode="${3}" source="${4}" tests="${5}" templates="${6}" entry="${7}" initialize="${8}"
    local file="" line="" temporary=""

    [[ "${mode}" == dev || "${mode}" == release ]] || { err "Unknown bundle mode: ${mode}"; return; }
    fs-dir "${output%/*}" || return
    temporary="$(mktemp "${output}.XXXXXXXX")" || { err "Cannot stage bundle: ${output}"; return; }

    (
        printf '%s\n' '#!/usr/bin/env bash' 'set -Eeuo pipefail' 'TOOL_BUNDLED=true' "TOOL_BUILD=${mode}"
        printf '%s\n' 'TOOL_ROOT="${PWD}"' 'TOOL_SOURCE=""' 'TOOL_BIN="${BASH_SOURCE[0]}"' ''
        printf '%s\n' 'declare -gA SOURCE_STATE=()'
        declare -f source-include source-list

        bundle-sources "${root}" "${source}" "${entry}" "${templates}" || exit
        bundle-assets "${root}" "${templates}" || exit

        if [[ "${mode}" == dev ]]; then

            while IFS= read -r -d '' file; do
                fs-read "${file}" || exit
                printf '\n'
            done < <(fs-files "${root}/${tests}" .sh)

        fi

        printf 'source-include %q || exit\n' "${initialize}"

        while IFS= read -r line || [[ -n "${line}" ]]; do
            [[ "${line}" == '#!'* || "${line}" == 'source '* || "${line}" == 'set '* ]] || printf '%s\n' "${line}"
        done < "${root}/${entry}"

    ) > "${temporary}" || { rm -f -- "${temporary}"; err "Bundle assembly failed: ${output}"; return; }

    bash -n "${temporary}" || { rm -f -- "${temporary}"; err "Bundle syntax check failed: ${output}"; return; }

    chmod 755 "${temporary}" && mv -f -- "${temporary}" "${output}"

}
