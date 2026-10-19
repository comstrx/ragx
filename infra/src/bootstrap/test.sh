bootstrap-test () {

    local filter="${1:-}" bundle="" name="" sandbox="" pass=0 fail=0

    [[ "${TOOL_BUILD}" == dev ]] || { err "Release bundles exclude tests"; return; }
    ! cli-flag --check || bootstrap-check || return

    if [[ "${TOOL_BUNDLED:-false}" == true ]]; then bundle="${TOOL_BIN}"
    else bundle="$(bootstrap-bundle dev)" || return
    fi

    while IFS= read -r name; do

        [[ -n "${name}" && ( -z "${filter}" || "${name}" == *"${filter}"* ) ]] || continue
        cli-flag --list && { out "${name}"; continue; }

        sandbox="$(fs-temp)" || return

        if env -i PATH="${PATH}" HOME="${sandbox}" TMPDIR="${sandbox}" LC_ALL=C.UTF-8 \
            bash "${bundle}" --project "${sandbox}" __test "${name}"; then
            info "pass ${name}"
            pass=$(( pass + 1 ))
        else
            warn "fail ${name}"
            fail=$(( fail + 1 ))
        fi

        rm -rf -- "${sandbox}"

    done < <(env -i PATH="${PATH}" HOME="${TOOL_TEMP}" TMPDIR="${TOOL_TEMP}" bash "${bundle}" --project "${TOOL_TEMP}" __tests)

    cli-flag --list && return 0
    (( pass + fail > 0 )) || { err "No tests matched: ${filter}"; return; }
    (( fail == 0 )) || { err "tests passed=${pass} failed=${fail}"; return; }

    succ "tests passed=${pass} failed=${fail}"

}
bootstrap-discover () {

    [[ "${TOOL_BUILD}" == dev ]] || { err "Release bundles exclude tests"; return; }

    tests-discover

}
bootstrap-isolate () {

    local name="${1:-}"

    [[ "${TOOL_BUILD}" == dev ]] || { err "Release bundles exclude tests"; return; }
    [[ "${name}" =~ ^test-[a-z0-9-]+$ ]] || { err "Unknown test: ${name}"; return; }
    declare -F "${name}" >/dev/null || { err "Unknown test: ${name}"; return; }

    "${name}"

}
