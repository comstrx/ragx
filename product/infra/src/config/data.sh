declare -ga CONFIG_DATA_COLUMNS=( service module prefix names secrets )

CONFIG_DATA_TABLE='
service   module      prefix  names            secrets
postgres  postgresql  DB      DB_USER,DB_NAME  DB_PASSWORD,DB_ADMIN_PASSWORD
rabbitmq  rabbitmq    RABBIT  RABBIT_USER      RABBIT_PASSWORD
redis     redis       REDIS   -                REDIS_PASSWORD
'

config-data-services () {

    local service=""

    while IFS=$'\x1f' read -r service _; do
        out "${service}"
    done < <(config-table Data "${CONFIG_DATA_TABLE}" "${CONFIG_DATA_COLUMNS[@]}")

}
config-data () {

    local wanted="${1}" column="${2}" index=0 found=-1
    local -a fields=()

    for index in "${!CONFIG_DATA_COLUMNS[@]}"; do
        [[ "${CONFIG_DATA_COLUMNS[${index}]}" != "${column}" ]] || found="${index}"
    done

    (( found > 0 )) || { err "Unknown data column: ${column}"; return; }

    while IFS=$'\x1f' read -r -a fields; do
        [[ "${fields[0]}" == "${wanted}" ]] || continue
        [[ "${fields[${found}]}" == - ]] || out "${fields[${found}]//,/ }"
        return 0
    done < <(config-table Data "${CONFIG_DATA_TABLE}" "${CONFIG_DATA_COLUMNS[@]}")

    err "Unknown data service: ${wanted}"

}
