bootstrap-layer () {

    local relative="${1}"

    case "${relative}" in
        main.sh)        out entry ;;
        core/*.sh)      out core ;;
        config/*.sh)    out config ;;
        bootstrap/*.sh) out bootstrap ;;
        module/*.sh)    out "module:${relative#module/}" ;;
        app/*/*.sh)     out "app:${relative#app/}" ;;
        *)              err "Source outside the layered layout: ${relative}"; return ;;
    esac

}
bootstrap-prefix () {

    local layer="${1}" name=""

    case "${layer}" in
        core|entry)  out '' ;;
        config)      out config- ;;
        bootstrap)   out bootstrap- ;;
        tests)       out 'test-|fixture-' ;;
        module:*)    name="${layer#module:}"; out "${name%.sh}-" ;;
        app:*)       name="${layer#app:}"; out "${name%%/*}-" ;;
    esac

}
bootstrap-allowed () {

    local caller="${1}" owner="${2}"

    [[ "${owner}" != core && "${owner}" != "${caller}" ]] || return 0

    case "${caller}" in
        core)       return 1 ;;
        config)     [[ "${owner}" == config ]] ;;
        bootstrap)  [[ "${owner}" == config || "${owner}" == bootstrap ]] ;;
        entry)      [[ "${owner}" == bootstrap ]] ;;
        tests)      return 0 ;;
        module:*)   [[ "${owner}" == module:docker.sh ]] ;;
        app:*)      [[ "${owner}" == config || "${owner}" == module:* || "${owner%%/*}" == "${caller%%/*}" ]] ;;
        *)          return 1 ;;
    esac

}
bootstrap-laws () {

    local source="${TOOL_SOURCE}" file="" relative="" layer="" prefix="" line="" previous="" token="" rest="" heredoc="" function=""
    local number=0 failed=0 indent=0
    local -A owners=() layers=()
    local -a files=()

    while IFS= read -r -d '' file; do

        relative="${file#"${source}/"}"
        [[ "${relative}" != template/* ]] || continue

        layer="$(bootstrap-layer "${relative}")" || { failed=1; continue; }
        files+=( "${file}" )
        layers["${file}"]="${layer}"

    done < <(fs-files "${source}" .sh)

    while IFS= read -r -d '' file; do
        files+=( "${file}" )
        layers["${file}"]=tests
    done < <(fs-files "${TOOL_ROOT}/${MANIFEST[paths.tests]}" .sh)

    for file in "${files[@]}"; do

        relative="${file#"${TOOL_ROOT}/"}"
        layer="${layers[${file}]}"
        prefix="$(bootstrap-prefix "${layer}")"

        while IFS= read -r line; do

            [[ "${line}" =~ ^([a-z][a-z0-9-]*)\ \(\)\ \{$ ]] || continue
            function="${BASH_REMATCH[1]}"

            [[ -z "${prefix}" || "${function}" =~ ^(${prefix}) ]] || { err "${relative}: ${function} must start with ${prefix//|/ or }"; failed=1; }
            [[ -z "${owners[${function}]:-}" ]] || { err "${relative}: ${function} is already defined"; failed=1; }
            owners["${function}"]="${layer}"

        done < "${file}"

    done

    for file in "${files[@]}"; do

        relative="${file#"${TOOL_ROOT}/"}"
        layer="${layers[${file}]}"
        number=0
        previous=""
        heredoc=""

        while IFS= read -r line || [[ -n "${line}" ]]; do

            number=$(( number + 1 ))

            if [[ -n "${heredoc}" ]]; then
                [[ "${line}" != "${heredoc}" ]] || heredoc=""
                previous="${line}"
                continue
            fi

            [[ "${line}" =~ \<\<\'([A-Z_]+)\'$ ]] && heredoc="${BASH_REMATCH[1]}"

            if [[ "${line}" =~ ^[[:space:]]*# ]] && [[ "${number}" != 1 || "${line}" != '#!'* ]]; then
                err "${relative}:${number}: comments are forbidden"; failed=1
            fi

            [[ "${line}" != *$'\t'* ]] || { err "${relative}:${number}: tabs are forbidden"; failed=1; }
            [[ "${line}" == "${line%[[:space:]]}" ]] || { err "${relative}:${number}: trailing whitespace"; failed=1; }
            [[ -n "${line}" || -n "${previous}" || "${number}" == 1 ]] || { err "${relative}:${number}: consecutive blank lines"; failed=1; }

            indent="${line%%[! ]*}"
            (( ${#indent} % 4 == 0 )) || { err "${relative}:${number}: indentation must be a multiple of four spaces"; failed=1; }

            if [[ "${line}" =~ ^(function[[:space:]]|[A-Za-z_][A-Za-z0-9_-]*[[:space:]]*\(\)) ]] && [[ ! "${line}" =~ ^[a-z][a-z0-9-]*\ \(\)\ \{$ ]]; then
                err "${relative}:${number}: functions are written as 'name () {'"; failed=1
            fi

            [[ ! "${previous}" =~ ^[a-z][a-z0-9-]*\ \(\)\ \{$ || -z "${line}" ]] || { err "${relative}:${number}: blank line required after the opening"; failed=1; }
            [[ "${line}" != '}' || -z "${previous}" ]] || { err "${relative}:${number}: blank line required before the closing"; failed=1; }

            if [[ "${line}" != *trap\ * && "${line}" =~ (^|[[:space:];{])(return|exit)\ ([2-9]|[0-9]{2,}) ]]; then
                err "${relative}:${number}: manual status codes are forbidden; print with err and return"; failed=1
            fi

            if [[ "${line}" =~ ^[[:space:]]*source-include\ ([a-z]+)/([a-z0-9_-]+)\.sh ]]; then
                bootstrap-include "${layer}" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" || { err "${relative}:${number}: ${layer} cannot load ${BASH_REMATCH[1]}/${BASH_REMATCH[2]}.sh"; failed=1; }
            fi

            rest="${line}"

            while [[ "${rest}" =~ ([a-z][a-z0-9]*(-[a-z0-9]+)+) ]]; do

                token="${BASH_REMATCH[1]}"
                rest="${rest#*"${token}"}"

                [[ -n "${owners[${token}]:-}" ]] || continue
                bootstrap-allowed "${layer}" "${owners[${token}]}" || { err "${relative}:${number}: ${layer} cannot call ${token} (${owners[${token}]})"; failed=1; }

            done

            previous="${line}"

        done < "${file}"

    done

    (( failed == 0 ))

}
bootstrap-include () {

    local layer="${1}" area="${2}" name="${3}"

    case "${layer}" in
        entry|bootstrap) [[ "${area}" == core || "${area}" == config || "${area}" == bootstrap ]] ;;
        core)            [[ "${area}" == core ]] ;;
        config)          [[ "${area}" == core || "${area}" == config ]] ;;
        module:*)        [[ "${area}" == module && ( "${name}" == docker || "${name}.sh" == "${layer#module:}" ) ]] ;;
        app:*)           [[ "${area}" == module ]] ;;
        *)               return 1 ;;
    esac

}
