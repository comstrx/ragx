source-include module/docker.sh || return
source-include module/postgresql.sh || return
source-include module/rabbitmq.sh || return
source-include module/redis.sh || return

native-data () {

    local directory="${1}" root="${CONFIG[STATE_ROOT]}/data" fingerprint="" recorded=""

    fs-dir "${root}" || return
    fingerprint="$(native-data-fingerprint "${directory}")" || return
    recorded="$(state-read "${root}" fingerprint 2>/dev/null)" || recorded=""

    if [[ -z "${recorded}" ]]; then native-data-adopt "${directory}" "${fingerprint}" || return
    elif [[ "${recorded}" != "${fingerprint}" ]]; then native-data-change "${directory}" "${fingerprint}" || return
    fi

    native-data-up --no-recreate || return
    [[ -f "${root}/identity" ]] || native-data-remember || return

    postgresql-archiving "${CONFIG[BACKUP_WAL]}" native-compose-data exec -T postgres || return
    postgresql-extensions "${CONFIG[DB_NAME]}" "${CONFIG[DB_EXTENSIONS]}" native-compose-data exec -T postgres

}
native-data-up () {

    local -a services=()

    mapfile -t services < <(config-data-services)
    native-compose-data up -d "$@" "${services[@]}" || return

    native-wait-data

}
native-data-files () {

    local service="" module=""

    out data.yaml

    while IFS= read -r service; do
        module="$(config-data "${service}" module)" || return
        "${module}-files"
    done < <(config-data-services)

}
native-data-fingerprint () {

    local file=""
    local -a paths=()

    while IFS= read -r file; do
        paths+=( "${1}/${file}" )
    done < <(native-data-files)

    fs-hashes "${paths[@]}"

}
native-data-adopt () {

    local directory="${1}" root="${CONFIG[STATE_ROOT]}/data" file=""

    while IFS= read -r file; do
        fs-copy "${directory}/${file}" "${root}/${file}" "$(fs-mode "${directory}/${file}")" || return
    done < <(native-data-files)

    state-write "${root}" fingerprint "${2}"

}
native-data-identity () {

    local service="" key=""
    local -a members=()

    while IFS= read -r service; do

        read -r -a members <<< "$(config-data "${service}" names)"
        for key in "${members[@]}"; do
            out "${key}=${CONFIG[${key}]}"
        done

        read -r -a members <<< "$(config-data "${service}" secrets)"
        for key in "${members[@]}"; do
            out "${key}=$(printf '%s' "${CONFIG[${key}]}" | fs-hash -)"
        done

    done < <(config-data-services)

}
native-data-remember () {

    native-data-identity | fs-write "${CONFIG[STATE_ROOT]}/data/identity" 600

}
native-data-change () {

    local directory="${1}" fingerprint="${2}" root="${CONFIG[STATE_ROOT]}/data" service="" known="" wanted="" changed=""

    native-data-up --no-recreate || return
    native-data-major || return

    [[ -f "${root}/identity" ]] || native-data-remember || return
    known="$(fs-read "${root}/identity")" || return
    wanted="$(native-data-identity)" || return

    warn "Data service settings changed; saving a dump, then cutting every connection before applying them"
    native-backup-dump >/dev/null || return

    while IFS= read -r service; do
        native-data-moved "${service}" "${known}" "${wanted}" || continue
        native-data-apply "${service}" "${known}" || return
        changed+=" ${service}"
    done < <(config-data-services)

    native-data-adopt "${directory}" "${fingerprint}" || return
    native-data-up || return
    native-data-remember || return

    native-announce data.changed "data service settings changed${changed:+ (identity of${changed})}; every open connection was cut and the services restarted with the new settings"

}
native-data-moved () {

    local service="${1}" known="${2}" wanted="${3}"
    local -a members=()

    read -r -a members <<< "$(config-data "${service}" names) $(config-data "${service}" secrets)"

    [[ "$(native-data-slice "${known}" "${members[@]}")" != "$(native-data-slice "${wanted}" "${members[@]}")" ]]

}
native-data-slice () {

    local text="${1}" line="" key=""

    shift

    while IFS= read -r line; do
        for key in "$@"; do
            [[ "${line}" != "${key}="* ]] || out "${line}"
        done
    done <<< "${text}"

}
native-data-apply () {

    local service="${1}" known="${2}" module="" container="" key="" value=""
    local -a plain=() hidden=() olds=() environment=()

    module="$(config-data "${service}" module)" || return
    declare -F "${module}-identity" >/dev/null || return 0

    read -r -a plain <<< "$(config-data "${service}" names)"
    read -r -a hidden <<< "$(config-data "${service}" secrets)"

    for key in "${plain[@]}"; do
        value="$(native-data-slice "${known}" "${key}")"
        olds+=( "${value#*=}" )
    done

    for key in "${plain[@]}" "${hidden[@]}"; do
        environment+=( -e "NEW_${key}" )
    done

    container="$(native-compose-data ps -q "${service}")" || return

    (
        for key in "${plain[@]}" "${hidden[@]}"; do
            export "NEW_${key}=${CONFIG[${key}]}"
        done

        "${module}-identity" "${olds[@]}" docker exec -i "${environment[@]}" "${container}"
    )

}
native-data-major () {

    local running="" wanted=""

    running="$(postgresql-cluster native-compose-data exec -T postgres)" || return
    wanted="$(postgresql-major "${CONFIG[IMAGE_POSTGRES]}")" || return

    [[ "${running}" == "${wanted}" ]] || { err "PostgreSQL ${running} holds the data and the new image is ${wanted}; a major upgrade needs a planned dump and restore, nothing was changed"; return; }

}
