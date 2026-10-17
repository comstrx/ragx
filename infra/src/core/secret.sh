#!/usr/bin/env bash

secret_keys () {

    infra_manifest | sed -nE 's/^([A-Z][A-Z0-9_]*)=.*/\1/p'

}
secret_get () {

    local key="${1:?secret_get needs a key}"

    printf '%s' "${!key-}"

}
secret_name () {

    local key="${1:?secret_name needs a key}"

    [[ " $(secret_keys | paste -sd ' ' -) " == *" ${key} "* || "${key}" == SECRET_* || "${key}" =~ (PASSWORD|SECRET|TOKEN|_KEY)$ ]]

}
secret_require () {

    local key="${1:-}" value=""

    value="$(secret_get "${key}")"

    [[ -n "${value}" ]] || die "Missing secret: ${key}"

    printf '%s' "${value}"

}
secret_env_pairs () {

    local raw="" line="" key="" value=""

    raw="$(secret_get ENV_FILE)"
    [[ -n "${raw}" ]] || return 0

    while IFS= read -r line; do

        key="${line%%=*}"
        value="${line#*=}"

        [[ -n "${value}" && "${key}" != "ENV_FILE" ]] || continue
        [[ "${value}" =~ ^\"(.*)\"$ || "${value}" =~ ^\'(.*)\'$ ]] && value="${BASH_REMATCH[1]}"

        printf '%s=%s\n' "${key}" "${value}"

    done < <(base64 -d <<< "${raw}" 2>/dev/null | env_pairs || die "ENV_FILE is not base64")

}
## the roles are split when a runtime role exists that is not the schema owner
secret_split () {

    [[ -n "${DB_APP_USER:-}" && "${DB_APP_USER}" != "${DB_USER}" ]]

}
## the env the pods run on — scope 'app' carries the runtime login only, scope 'owner' adds the owner password for the hook, the run jobs and the backup
secret_env_file () {

    local dst="${1:?secret_env_file needs a destination}" scope="${2:-app}" key="" value="" line="" managed=""

    ( umask 077 && : > "${dst}" ) || die "Cannot write: ${dst}"
    chmod 600 "${dst}"

    for key in ${APP_SECRET_KEYS}; do

        value="$(secret_get "${key}")"

        [[ "${key}" != "DB_PASSWORD" ]] || ! secret_split || value="$(secret_require DB_APP_PASSWORD)"
        [[ -n "${value}" ]] && printf '%s=%s\n' "${key}" "${value}" >> "${dst}"

    done

    [[ "${scope}" != "owner" ]] || ! secret_split || printf 'DB_MIGRATE_PASSWORD=%s\n' "$(secret_require DB_PASSWORD)" >> "${dst}"
    [[ -z "$(secret_get APP_AWS_ACCESS_KEY_ID)" ]] || printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$(secret_get APP_AWS_ACCESS_KEY_ID)" "$(secret_require APP_AWS_SECRET_ACCESS_KEY)" >> "${dst}"

    managed=" $(config_managed_keys) "

    while IFS= read -r line; do

        key="${line%%=*}"
        [[ " ${managed} " != *" ${key} "* ]] || continue
        [[ "${scope}" == "owner" || "${key}" != "DB_MIGRATE_PASSWORD" ]] || continue
        grep -qE "^${key}=" "${dst}" || printf '%s\n' "${line}" >> "${dst}"

    done < <(secret_env_pairs)

    return 0

}
