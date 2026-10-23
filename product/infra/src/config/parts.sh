declare -ga CONFIG_PARTS=()
declare -ga CONFIG_PART_COLUMNS=( name kind port path ready expect balance replicas limit env_mount source dockerfile build )
declare -ga CONFIG_PART_PINNED=( DOMAIN IMAGE ENV_SHA256 KIND PORT PATH READY EXPECT BALANCE LIMIT ENV_MOUNT )
declare -ga CONFIG_SERVER_KEYS=( STORAGE_MOUNT RELEASE_VARIABLE FORCED_ENV SERVE_COMMAND SERVE_ENV WORK_COMMAND WORK_ENV SCHEDULE_COMMAND SCHEDULE_ENV MIGRATE_COMMAND )
declare -gA CONFIG_PART=()

CONFIG_PARTS_TABLE='
name      kind    port  path  ready    expect   balance     replicas  limit  env_mount              source                      dockerfile  build
api       server  8000  /     /health  200      leastconn   2         -      /app/.env              product/api                 api         -
super     site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/super     web         NEXT_PUBLIC_SPEC=super SPEC_API_URL={api}
admin     site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/admin     web         NEXT_PUBLIC_SPEC=admin SPEC_API_URL={api}
supplier  site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/supplier  web         NEXT_PUBLIC_SPEC=supplier SPEC_API_URL={api}
vendor    site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/vendor    web         NEXT_PUBLIC_SPEC=vendor SPEC_API_URL={api}
delivery  site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/delivery  web         NEXT_PUBLIC_SPEC=delivery SPEC_API_URL={api}
client    site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/client    web         NEXT_PUBLIC_SPEC=client SPEC_API_URL={api}
tenant    site    3000  /     /        200-399  roundrobin  2         -      /app/product/web/.env  product/web/specs/tenant    web         NEXT_PUBLIC_SPEC=tenant SPEC_API_URL={api}
'

config-parts-load () {

    local records="" name="" column="" value="" index=0 servers=0 failed=0
    local -a fields=()

    config-inputs-forget parts
    CONFIG_PARTS=()
    CONFIG_PART=()

    records="$(config-table Parts "${CONFIG_PARTS_TABLE}" "${CONFIG_PART_COLUMNS[@]}")" || return

    while IFS=$'\x1f' read -r -a fields; do

        [[ -n "${fields[0]:-}" ]] || continue
        name="${fields[0]}"

        [[ "${name}" =~ ^[a-z][a-z0-9]{0,30}$ ]] || { err "Part name must be lowercase letters and digits: ${name}"; failed=1; continue; }
        [[ " worker scheduler grafana acme unavailable " != *" ${name} "* ]] || { err "Part name ${name} is reserved"; failed=1; continue; }
        [[ -z "${CONFIG_PART[${name}.name]:-}" ]] || { err "Part ${name} is declared twice"; failed=1; continue; }

        CONFIG_PARTS+=( "${name}" )

        for index in "${!CONFIG_PART_COLUMNS[@]}"; do
            column="${CONFIG_PART_COLUMNS[${index}]}"
            value="${fields[${index}]}"
            [[ "${value}" != - ]] || value=""
            CONFIG_PART["${name}.${column}"]="${value}"
        done

        [[ "${CONFIG_PART[${name}.kind]}" != server ]] || servers=$(( servers + 1 ))

    done <<< "${records}"

    (( ${#CONFIG_PARTS[@]} > 0 )) || { err "The parts table declares no part"; return; }
    (( servers == 1 )) || { err "The parts table needs exactly one server part, found ${servers}"; failed=1; }

    for name in "${CONFIG_PARTS[@]}"; do
        config-part-check "${name}" || failed=1
    done

    (( failed == 0 )) || return 1

    for name in "${CONFIG_PARTS[@]}"; do
        config-input parts "${name^^}_IMAGE" "" || failed=1
        config-input parts "${name^^}_REPLICAS" "${CONFIG_PART[${name}.replicas]}" || failed=1
    done

    (( failed == 0 ))

}
config-part-names () {

    local name=""

    while IFS=$'\x1f' read -r name _; do
        out "${name}"
    done < <(config-table Parts "${CONFIG_PARTS_TABLE}" "${CONFIG_PART_COLUMNS[@]}")

}
config-part-check () {

    local name="${1}" prefix="${1^^}" path="${CONFIG_PART[${1}.path]}" ready="${CONFIG_PART[${1}.ready]}" word="" target="" key="" failed=0
    local -a words=()

    [[ " server site " == *" ${CONFIG_PART[${name}.kind]} "* ]] || { err "Part ${name}: kind must be server or site"; failed=1; }
    parse-port "${CONFIG_PART[${name}.port]}" || { err "Part ${name}: invalid port"; failed=1; }
    parse-path "${path}" && [[ "${path}" == / || "${path}" != */ ]] || { err "Part ${name}: path must be absolute without a trailing slash"; failed=1; }
    parse-path "${ready}" && [[ "${path}" == / || "${ready}" == "${path}" || "${ready}" == "${path}/"* ]] || { err "Part ${name}: ready must be a path under ${path}"; failed=1; }
    [[ "${CONFIG_PART[${name}.expect]}" =~ ^[1-5][0-9]{2}(-[1-5][0-9]{2})?$ ]] || { err "Part ${name}: expect must be a status or a range"; failed=1; }
    [[ " roundrobin leastconn " == *" ${CONFIG_PART[${name}.balance]} "* ]] || { err "Part ${name}: balance must be roundrobin or leastconn"; failed=1; }
    config-valid replicas "${CONFIG_PART[${name}.replicas]}" || { err "Part ${name}: replicas must be 1..32"; failed=1; }
    [[ -z "${CONFIG_PART[${name}.limit]}" ]] || config-valid rate "${CONFIG_PART[${name}.limit]}" || { err "Part ${name}: limit must be REQUESTS/PERIOD"; failed=1; }
    [[ -z "${CONFIG_PART[${name}.env_mount]}" ]] || parse-path "${CONFIG_PART[${name}.env_mount]}" || { err "Part ${name}: env_mount must be an absolute path"; failed=1; }
    fs-relative "${CONFIG_PART[${name}.source]}" || { err "Part ${name}: source must be a path relative to the repository root"; failed=1; }
    parse-identifier "${CONFIG_PART[${name}.dockerfile]}" || { err "Part ${name}: dockerfile must name an image recipe"; failed=1; }
    config-schema-key "${prefix}_DOMAIN" || { err "Part ${name}: declare ${prefix}_DOMAIN in .env.example"; failed=1; }

    read -r -a words <<< "${CONFIG_PART[${name}.build]}"

    for word in "${words[@]}"; do
        [[ "${word}" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*$ ]] || { err "Part ${name}: build words are NAME=VALUE: ${word}"; failed=1; continue; }
        while [[ "${word}" =~ \{([a-z0-9]*)\} ]]; do
            target="${BASH_REMATCH[1]}"
            word="${word/"{${target}}"/}"
            [[ " ${CONFIG_PARTS[*]} " == *" ${target} "* ]] || { err "Part ${name}: build references an unknown part {${target}}"; failed=1; }
        done
    done

    if [[ "${CONFIG_PART[${name}.kind]}" == server ]]; then

        [[ -n "${CONFIG_PART[${name}.env_mount]}" ]] || { err "Part ${name}: a server part needs env_mount"; failed=1; }

        for key in "${CONFIG_SERVER_KEYS[@]}"; do
            config-schema-key "${prefix}_${key}" || { err "Part ${name}: declare ${prefix}_${key} in .env.example"; failed=1; }
        done

    fi

    (( failed == 0 ))

}
config-parts-derive () {

    local name="" column="" key="" first="" routed="" shipped=""

    for name in "${CONFIG_PARTS[@]}"; do

        for column in kind port path ready expect balance limit env_mount source dockerfile build; do
            key="${name^^}_${column^^}"
            [[ "${CONFIG_SOURCE[${key}]:-}" == release ]] || cfg-set "${key}" "${CONFIG_PART[${name}.${column}]}" parts
        done

        first="$(config-first "${CONFIG[${name^^}_DOMAIN]:-}")"
        [[ -z "${first}" ]] || routed+="${routed:+ }${name}"
        [[ -z "${CONFIG[${name^^}_IMAGE]:-}" ]] || { [[ -z "${first}" ]] && ! config-domains-on; } || shipped+="${shipped:+ }${name}"
        cfg-set "${name^^}_URL" "$(config-url "${first:-localhost}" "${CONFIG[${name^^}_PATH]%/}")"

    done

    cfg-set ROUTED "${routed}"
    [[ "${CONFIG_SOURCE[PARTS]:-}" == release ]] || cfg-set PARTS "${shipped}"

}
config-list () {

    local item=""
    local -a items=()

    IFS=$' \t,' read -r -a items <<< "${1-}"

    for item in "${items[@]}"; do
        [[ -z "${item}" ]] || out "${item,,}"
    done

}
config-first () {

    local item=""
    local -a items=()

    IFS=$' \t,' read -r -a items <<< "${1-}"

    for item in "${items[@]}"; do
        [[ -z "${item}" ]] || { out "${item,,}"; return; }
    done

}
config-server () {

    local name=""

    for name in "${CONFIG_PARTS[@]}"; do
        [[ "${CONFIG_PART[${name}.kind]}" != server ]] || { out "${name}"; return; }
    done

}
