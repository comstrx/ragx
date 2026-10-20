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

    local directory="${1}"

    fs-dir "${directory}" || return
    postgresql-render "${directory}" || return
    rabbitmq-render "${directory}" || return
    redis-render "${directory}" || return
    native-env-render "${directory}" API || return
    native-env-render "${directory}" WEB || return

    template-render "${MANIFEST[paths.templates]}/native/data.yaml.tpl" "${directory}/data.yaml" || return
    native-render-compose "${directory}"

}
native-render-compose () {

    local directory="${1}" templates="${MANIFEST[paths.templates]}/native" spec="" image="" body="" release="" storage=""

    [[ -z "${CONFIG[API_RELEASE_VARIABLE]}" ]] || release="${CONFIG[API_RELEASE_VARIABLE]}=${CONFIG[RELEASE]}"
    storage="{\"type\": \"volume\", \"source\": \"storage\", \"target\": $(parse-json-string "${CONFIG[API_STORAGE_MOUNT]}")}"

    cfg-set API_MOUNTS "$(native-mounts API "${storage}")"
    cfg-set API_SERVE_ARGS "$(native-words "${CONFIG[API_SERVE_COMMAND]}")"
    cfg-set API_WORK_ARGS "$(native-words "${CONFIG[API_WORK_COMMAND]}")"
    cfg-set API_SCHEDULE_ARGS "$(native-words "${CONFIG[API_SCHEDULE_COMMAND]}")"
    cfg-set API_SERVE_VARIABLES "$(native-variables "${CONFIG[API_FORCED_ENV]}" "${CONFIG[API_SERVE_ENV]}" "${release}")"
    cfg-set API_WORK_VARIABLES "$(native-variables "${CONFIG[API_FORCED_ENV]}" "${CONFIG[API_WORK_ENV]}" "${release}")"
    cfg-set API_SCHEDULE_VARIABLES "$(native-variables "${CONFIG[API_FORCED_ENV]}" "${CONFIG[API_SCHEDULE_ENV]}" "${release}")"
    cfg-set WEB_MOUNTS "$(native-mounts WEB)"
    cfg-set WEB_VARIABLES "$(native-variables "${CONFIG[WEB_FORCED_ENV]}")"

    template-render "${templates}/application.yaml.tpl" "${directory}/application.yaml" || return

    body='services: {}'

    while IFS= read -r spec; do

        [[ -n "${spec}" ]] || continue
        [[ "${body}" != 'services: {}' ]] || body='services:'

        image="$(native-service-image "web-${spec}")" || return
        cfg-set WEB_SERVICE "web-${spec}"
        cfg-set WEB_IMAGE "${image}"
        cfg-set WEB_VARIABLE "$(native-variable "${spec}")"
        body+=$'\n'"$(template-text "${templates}/web.yaml.tpl")" || return

    done < <(native-specs)

    printf '%s\n' "${body}" | fs-write "${directory}/web.yaml"

}
native-release-id () {

    local revision=""

    [[ -z "${CONFIG[RELEASE]}" ]] || return 0
    [[ -n "${CONFIG[VERSION]}" ]] || { err "Missing setting: VERSION or RELEASE"; return; }

    revision="$(native-revision)" || return
    parse-identifier "${CONFIG[VERSION]}-${revision}" || { err "VERSION is too long for a release name: ${CONFIG[VERSION]}"; return; }
    cfg-set RELEASE "${CONFIG[VERSION]}-${revision}"

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

    local app="${1}" mounts="${2-}" source=""

    if native-env-enabled "${app}"; then
        source="$(parse-json-string "\${RELEASE_ROOT:?RELEASE_ROOT required}/${app,,}.env")"
        mounts+="${mounts:+, }{\"type\": \"bind\", \"source\": ${source}, \"target\": $(parse-json-string "${CONFIG[${app}_ENV_MOUNT]}"), \"read_only\": true}"
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

    out "${CONFIG[PROJECT_ROOT]}/.env.${1,,}"

}
native-env-enabled () {

    [[ "${1}" == API ]] || native-env-present "${1}"

}
native-env-present () {

    local name="${1}_ENV_FILE"

    [[ -n "${!name+x}" && "${!name@a}" == *x* && -n "${!name}" ]] || [[ -f "$(native-env-file "${1}")" ]]

}
native-env-content () {

    local app="${1}" name="${1}_ENV_FILE" file="" content="" bytes=0

    file="$(native-env-file "${app}")"

    if [[ -n "${!name+x}" && "${!name@a}" == *x* && -n "${!name}" ]]; then
        content="$(parse-content "${!name}")"
    elif [[ -f "${file}" ]]; then
        ! IFS= read -r -d '' content < "${file}" || { err "NUL bytes are forbidden: ${file}"; return; }
        content="$(fs-read "${file}")" || return
    else
        err "${app} env content missing: export ${name} or stage ${file##*/}"
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

    local app="" digest=""

    for app in API WEB; do
        digest="$(native-env-digest "${app}")" || return
        cfg-set "${app}_ENV_SHA256" "${digest}"
    done

}
native-env-render () {

    local directory="${1}" app="${2}" content=""

    native-env-enabled "${app}" || return 0
    content="$(native-env-content "${app}")" || return

    printf '%s\n' "${content}" | fs-write "${directory}/${app,,}.env" 644

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
