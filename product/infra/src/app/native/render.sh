source-include module/postgresql.sh || return
source-include module/rabbitmq.sh || return
source-include module/redis.sh || return

native-directory () {

    parse-identifier "${1:-}" || { err "Invalid release: ${1:-}"; return; }

    fs-within "${CONFIG[STATE_ROOT]}" "releases/${1}"

}
native-render () {

    local directory=""

    config-validate || return
    native-release-id || return
    config-required || return
    directory="$(native-directory "${CONFIG[RELEASE]}")" || return

    if [[ -f "${directory}/release.env" ]]; then
        native-release-match "${directory}" || return
    else
        native-env-digests || return
        native-render-files "${directory}" || return
        config-release-save "${directory}/release.env" || return
        state-write "${directory}" migration "${CONFIG[MIGRATION_POLICY]}" || return
    fi

    out "${directory}"

}
native-render-files () {

    local directory="${1}" name="" module=""

    fs-dir "${directory}" || return

    while IFS= read -r name; do
        module="$(config-data "${name}" module)" || return
        "${module}-render" "${directory}" || return
    done < <(config-data-services)

    while IFS= read -r name; do
        native-env-render "${directory}" "${name}" || return
    done < <(native-parts)

    template-render "${MANIFEST[paths.templates]}/native/data.yaml.tpl" "${directory}/data.yaml" || return
    native-render-compose "${directory}"

}
native-render-compose () {

    local directory="${1}" name="" prefix="" release="" storage="" kind=""

    fs-dir "${directory}" || return

    while IFS= read -r name; do

        prefix="${name^^}"
        kind="${CONFIG[${prefix}_KIND]}"

        cfg-set PART_NAME "${name}"
        cfg-set PART_IMAGE "${CONFIG[${prefix}_IMAGE]}"
        cfg-set PART_PORT "${CONFIG[${prefix}_PORT]}"
        cfg-set PART_VARIABLE "${prefix}_REPLICAS"

        if [[ "${kind}" == server ]]; then
            release=""
            [[ -z "${CONFIG[${prefix}_RELEASE_VARIABLE]}" ]] || release="${CONFIG[${prefix}_RELEASE_VARIABLE]}=${CONFIG[RELEASE]}"
            storage="{\"type\": \"volume\", \"source\": \"storage\", \"target\": $(parse-json-string "${CONFIG[${prefix}_STORAGE_MOUNT]}")}"
            cfg-set PART_MOUNTS "$(native-mounts "${name}" "${storage}")"
            cfg-set PART_SERVE_ARGS "$(native-words "${CONFIG[${prefix}_SERVE_COMMAND]}")"
            cfg-set PART_WORK_ARGS "$(native-words "${CONFIG[${prefix}_WORK_COMMAND]}")"
            cfg-set PART_SCHEDULE_ARGS "$(native-words "${CONFIG[${prefix}_SCHEDULE_COMMAND]}")"
            cfg-set PART_SERVE_VARIABLES "$(native-variables "${CONFIG[${prefix}_FORCED_ENV]}" "${CONFIG[${prefix}_SERVE_ENV]}" "${release}")"
            cfg-set PART_WORK_VARIABLES "$(native-variables "${CONFIG[${prefix}_FORCED_ENV]}" "${CONFIG[${prefix}_WORK_ENV]}" "${release}")"
            cfg-set PART_SCHEDULE_VARIABLES "$(native-variables "${CONFIG[${prefix}_FORCED_ENV]}" "${CONFIG[${prefix}_SCHEDULE_ENV]}" "${release}")"
        else
            cfg-set PART_MOUNTS "$(native-mounts "${name}")"
            cfg-set PART_VARIABLES "$(native-variables "PORT=${CONFIG[${prefix}_PORT]} HOSTNAME=0.0.0.0")"
        fi

        template-render "${MANIFEST[paths.templates]}/native/${kind}.yaml.tpl" "${directory}/part-${name}.yaml" || return

    done < <(native-parts)

}
native-release-id () {

    local revision=""

    native-carry || return
    [[ -z "${CONFIG[RELEASE]}" ]] || return 0
    [[ -n "${CONFIG[VERSION]}" ]] || { err "Missing setting: VERSION or RELEASE"; return; }

    revision="$(native-revision)" || return
    parse-identifier "${CONFIG[VERSION]}-${revision}" || { err "VERSION is too long for a release name: ${CONFIG[VERSION]}"; return; }
    cfg-set RELEASE "${CONFIG[VERSION]}-${revision}"

}
native-carry () {

    local current="" directory="" name="" image=""
    local -A pinned=()

    [[ -z "${CONFIG[CARRIED]:-}" ]] || return 0
    cfg-set CARRIED true
    current="$(state-read "${CONFIG[STATE_ROOT]}" current 2>/dev/null)" || current=""

    if [[ -n "${current}" ]]; then
        directory="$(native-directory "${current}")" || return
        [[ ! -f "${directory}/release.env" ]] || parse-pairs pinned "${directory}/release.env" || return
    fi

    while IFS= read -r name; do

        [[ -z "${CONFIG[${name^^}_IMAGE]}" ]] || continue
        image="${pinned[${name^^}_IMAGE]:-}"

        if [[ -n "${image}" ]]; then
            warn "${name} has no new image; it keeps ${image} from ${current}"
            cfg-set "${name^^}_IMAGE" "${image}" carried
        else
            warn "${name} has a domain but no image; it stays out of this release"
        fi

    done < <(native-routed)

    config-derive

}
native-revision () {

    local key="" digest=""
    local -a keys=()

    native-env-digests || return

    while IFS= read -r key; do
        [[ "${key}" == RELEASE ]] || keys+=( "${key}" )
    done < <(config-release-keys)

    digest="$(template-env-text false "${keys[@]}" | fs-hash -)" || return
    out "${digest:0:8}"

}
native-mounts () {

    local name="${1}" mounts="${2-}" source=""

    if native-env-enabled "${name}"; then
        source="$(parse-json-string "\${RELEASE_ROOT:?RELEASE_ROOT required}/${name}.env")"
        mounts+="${mounts:+, }{\"type\": \"bind\", \"source\": ${source}, \"target\": $(parse-json-string "${CONFIG[${name^^}_ENV_MOUNT]}"), \"read_only\": true}"
    fi

    out "[${mounts}]"

}
native-words () {

    local word="" json=""
    local -a words=()

    read -r -a words <<< "${1-}"

    for word in "${words[@]}"; do
        json+="${json:+, }$(parse-json-string "${word//\$/\$\$}")"
    done

    out "[${json}]"

}
native-variables () {

    local pair="" name="" json=""
    local -a pairs=() order=()
    local -A values=()

    read -r -a pairs <<< "$*"

    for pair in "${pairs[@]}"; do
        name="${pair%%=*}"
        [[ -n "${values[${name}]+x}" ]] || order+=( "${name}" )
        values["${name}"]="${pair#*=}"
    done

    for name in "${order[@]}"; do
        json+="${json:+, }$(parse-json-string "${name}"): $(parse-json-string "${values[${name}]//\$/\$\$}")"
    done

    out "{${json}}"

}
native-env-file () {

    out "${CONFIG[PROJECT_ROOT]}/.env.${1}"

}
native-env-enabled () {

    [[ -n "${CONFIG[${1^^}_ENV_MOUNT]:-}" ]] || return 1
    [[ "${CONFIG[${1^^}_KIND]:-}" == server ]] || native-env-present "${1}"

}
native-env-present () {

    local name="${1^^}_ENV_FILE"

    [[ -n "${!name+x}" && "${!name@a}" == *x* && -n "${!name}" ]] || [[ -f "$(native-env-file "${1}")" ]]

}
native-env-content () {

    local part="${1}" name="${1^^}_ENV_FILE" file="" content="" bytes=0

    file="$(native-env-file "${part}")"

    if [[ -n "${!name+x}" && "${!name@a}" == *x* && -n "${!name}" ]]; then
        content="$(parse-content "${!name}")"
    elif [[ -f "${file}" ]]; then
        ! IFS= read -r -d '' content < "${file}" || { err "NUL bytes are forbidden: ${file}"; return; }
        content="$(fs-read "${file}")" || return
    else
        err "${part} env content missing: export ${name} or stage ${file##*/}"
        return
    fi

    bytes="$(LC_ALL=C; out "${#content}")"
    (( bytes <= 49152 )) || { err "${name} exceeds 48 KiB"; return; }
    [[ "${content}" != *$'\r'* ]] || { err "${name} has carriage returns; save it with LF line endings"; return; }
    [[ "${content}" =~ [^[:space:]] ]] || { err "${name} is empty"; return; }

    printf '%s' "${content}"

}
native-env-digest () {

    local content=""

    native-env-enabled "${1}" || return 0
    content="$(native-env-content "${1}")" || return

    printf '%s\n' "${content}" | fs-hash -

}
native-env-digests () {

    local name="" digest=""

    while IFS= read -r name; do
        digest="$(native-env-digest "${name}")" || return
        cfg-set "${name^^}_ENV_SHA256" "${digest}"
    done < <(native-parts)

}
native-env-render () {

    local directory="${1}" name="${2}" content=""

    native-env-enabled "${name}" || return 0
    content="$(native-env-content "${name}")" || return

    printf '%s\n' "${content}" | fs-write "${directory}/${name}.env" 644

}
native-release-match () {

    local directory="${1}" scratch="" expected="" actual="" status=0

    [[ -f "${directory}/release.env" ]] || { err "Release snapshot missing: ${directory}"; return; }
    native-env-digests || return
    scratch="$(fs-temp)" || return

    if ( config-release-load "${directory}/release.env" && config-release-save "${scratch}/expected" ) && config-release-save "${scratch}/actual"; then
        expected="$(fs-hash "${scratch}/expected")" || status=$?
        actual="$(fs-hash "${scratch}/actual")" || status=$?
        [[ "${expected}" == "${actual}" ]] || err "Release ${CONFIG[RELEASE]} settings changed; publish under a new RELEASE" || status=$?
    else
        status=1
    fi

    rm -rf -- "${scratch}"
    return "${status}"

}
