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
## single quotes carry a value literally through docker compose — a value holding one has no safe spelling
secret_quote () {

    local value="${1-}" name="${2:-A value}"

    [[ "${value}" != *\'* && "${value}" != *$'\n'* ]] || die "${name} carries a single quote or a newline — no env file can hold it literally; choose another value"

    printf "'%s'" "${value}"

}
## law: every secret the manifest carries survives an env file literally
secret_clean () {

    local key=""

    while IFS= read -r key; do

        secret_quote "$(secret_get "${key}")" "${key}" >/dev/null

    done < <(secret_keys)

}
## the extra app keys ENV_FILE carries, appended behind what the platform renders — never over it
secret_env_extra () {

    local dst="${1:?secret_env_extra needs a destination}" line="" key="" managed=""

    managed=" $(config_managed_keys | paste -sd ' ' -) "

    while IFS= read -r line; do

        key="${line%%=*}"

        [[ "${managed}" != *" ${key} "* ]] || continue

        grep -qE "^${key}=" "${dst}" || printf '%s=%s\n' "${key}" "$(secret_quote "${line#*=}" "${key}")" >> "${dst}"

    done < <(secret_env_pairs)

    return 0

}
