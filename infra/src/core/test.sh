expect-equal () {

    [[ "${1-}" == "${2-}" ]] || { err "Expected '${2-}' but got '${1-}': ${3:-values differ}"; return; }

}
expect-contains () {

    [[ "${1-}" == *"${2-}"* ]] || { err "Missing '${2-}': ${3:-content differs}"; return; }

}
expect-absent () {

    [[ "${1-}" != *"${2-}"* ]] || { err "Unexpected '${2-}': ${3:-content differs}"; return; }

}
expect-status () {

    local expected="${1}" status=0

    shift
    "$@" >/dev/null 2>&1 || status=$?

    expect-equal "${status}" "${expected}" "exit status of ${1-}"

}
expect-fail () {

    ! "$@" >/dev/null 2>&1 || { err "Expected failure: $*"; return; }

}
expect-error () {

    local message="${1}" output="" status=0

    shift
    output="$("$@" 2>&1 >/dev/null)" || status=$?

    (( status != 0 )) || { err "Expected failure: $*"; return; }
    expect-contains "${output}" "${message}" "error of ${1-}"

}
tests-discover () {

    local name=""

    while IFS= read -r name; do
        [[ "${name}" == test-* ]] && out "${name}"
    done < <(compgen -A function test-)

    return 0

}
