source-include module/docker.sh || return
source-include module/huggingface.sh || return

native-models () {

    native-dispatch models "$@"

}
native-models-status () {

    local name="" UI_WIDTH=12

    config-validate || return
    [[ -n "$(config-models)" ]] || { ui-row models "none; MODELS names the ones to serve (${CONFIG_MODELS[*]})"; return 0; }

    while IFS= read -r name; do
        ui-row "${name}" "$(native-model-state "${name}") ${CONFIG[${name^^}_URL]}"
    done < <(config-models)

}
native-models-pull () {

    config-validate || return
    state-locked "${CONFIG[STATE_ROOT]}/models.lock" native-models-fetch || return

    ui-result models-pull true safe

}
native-models-verify () {

    local name=""

    config-validate || return

    while IFS= read -r name; do
        rm -f -- "$(native-model-stamp "${name}")"
    done < <(config-models)

    state-locked "${CONFIG[STATE_ROOT]}/models.lock" native-models-fetch || return

    ui-result models-verify true safe

}
native-models-apply () {

    config-validate || return
    native-models-sync || return

    ui-result models-apply true safe

}
native-models-sync () {

    local name="" bytes=0 free=0 total=0

    docker-ready || return
    fs-dir "${CONFIG[STATE_ROOT]}/models" || return

    if [[ -z "$(config-models)" ]]; then
        native-models-render || return
        native-compose-models down --remove-orphans || return
        return 0
    fi

    state-locked "${CONFIG[STATE_ROOT]}/models.lock" native-models-fetch || return

    while IFS= read -r name; do
        bytes="$(parse-bytes "${CONFIG[${name^^}_MEMORY]}")" || return
        total=$(( total + bytes ))
    done < <(config-models)

    free="$(docker-memory "${CONFIG[COMPOSE_PROJECT]}-models")" || return
    (( free >= total )) || { err "The models need $(( total / 1048576 ))MiB of unreserved Docker memory"; return; }

    native-models-render || return
    docker-network "${CONFIG[COMPOSE_PROJECT]}-models" "${CONFIG[COMPOSE_PROJECT]}" internal || return
    native-compose-models up -d --remove-orphans || return
    run-until "${CONFIG[HEALTH_TIMEOUT]}" 3 native-models-healthy || { err "A model did not turn healthy within HEALTH_TIMEOUT; read infra logs MODEL"; return; }

    succ "Models serving: $(config-models | paste -sd ' ' -)"

}
native-models-converge () {

    native-models-sync && return 0

    warn "The models did not converge; the release is unaffected, see infra models and infra logs MODEL"
    native-announce models.failed "the models $(config-models | paste -sd ' ' -) did not converge; the release is unaffected"

    return 0

}
native-models-render () {

    local directory="${CONFIG[STATE_ROOT]}/models" name="" image="" file=""

    for file in "${directory}"/model-*.yaml; do
        [[ ! -f "${file}" ]] || rm -f -- "${file}"
    done

    while IFS= read -r name; do

        image="${CONFIG_MODEL[runner.${CONFIG_MODEL[${name}.runner]}.image]^^}"
        image="IMAGE_${image//-/_}"

        cfg-set MODEL_NAME "${name}"
        cfg-set MODEL_IMAGE "${CONFIG[${image}]}"
        cfg-set MODEL_ROOT "$(native-model-directory "${name}")"
        cfg-set MODEL_REVISION "${CONFIG_MODEL[${name}.revision]}"
        cfg-set MODEL_MEMORY "${CONFIG[${name^^}_MEMORY]}"
        cfg-set MODEL_CPUS "${CONFIG[${name^^}_CPUS]}"
        cfg-set MODEL_ARGS "$(native-words "$(config-model-args "${name}")")"

        template-render "${MANIFEST[paths.templates]}/native/model.yaml.tpl" "${directory}/model-${name}.yaml" || return

    done < <(config-models)

}
native-models-fetch () {

    local name=""

    while IFS= read -r name; do
        native-model-fetch "${name}" || return
    done < <(config-models)

}
native-model-fetch () {

    local name="${1}" root="" directory="" stamp="" spec="" source="" file="" size="" digest="" url="" path="" relative=""
    local -A listed=()

    root="$(native-model-root "${name}")" || return
    directory="$(native-model-directory "${name}")" || return
    stamp="$(native-model-stamp "${name}")" || return
    spec="$(native-model-spec "${name}")" || return

    if [[ "$(fs-read "${stamp}" 2>/dev/null)" == "${spec}" ]] && ! native-model-missing "${name}"; then
        return 0
    fi

    native-model-space "${name}" || return
    fs-dir "${root}" 755 || return
    fs-dir "${directory}" 755 || return
    rm -f -- "${stamp}"

    while read -r file _; do
        [[ -z "${file}" ]] || listed["${file}"]=1
    done <<< "${CONFIG_MODEL[${name}.files]}"

    while IFS= read -r -d '' path; do
        relative="${path#"${directory}/"}"
        [[ -n "${listed[${relative}]:-}" || -n "${listed[${relative%.part}]:-}" ]] || { warn "Removing ${name}/${relative}: the models table does not list it"; rm -f -- "${path}"; }
    done < <(fs-files "${directory}")

    source="${CONFIG_MODEL[${name}.source]}"

    while read -r file size digest; do

        [[ -n "${file}" ]] || continue
        path="${directory}/${file}"

        if [[ -f "${path}" ]]; then
            [[ "$(( $(wc -c < "${path}") ))" == "${size}" && "$(fs-hash "${path}")" == "${digest}" ]] && continue
            warn "Fetching ${name}/${file} again: it differs from the models table"
            rm -f -- "${path}"
        fi

        fs-dir "${path%/*}" 755 || return
        url="$("${source%%:*}-url" "${source#*:}" "${CONFIG_MODEL[${name}.revision]}" "${file}")" || return
        info "Fetching ${name}/${file} ($(( size / 1048576 )) MiB)"
        net-fetch "${url}" "${path}" "${size}" "${digest}" "${CONFIG[MODELS_TOKEN]}" || return

    done <<< "${CONFIG_MODEL[${name}.files]}"

    printf '%s\n' "${spec}" | fs-write "${stamp}" 644 || return

    for path in "${root}"/*; do
        [[ "${path}" == "${directory}" || "${path}" == "${stamp}" || ! -e "${path}" ]] || fs-remove-tree "${root}" "${path}" || return
    done

    succ "${name} ${CONFIG_MODEL[${name}.revision]} verified"

}
native-model-root () {

    out "${CONFIG[MODELS_ROOT]}/${1}"

}
native-model-directory () {

    out "${CONFIG[MODELS_ROOT]}/${1}/${CONFIG_MODEL[${1}.revision]}"

}
native-model-stamp () {

    out "${CONFIG[MODELS_ROOT]}/${1}/${CONFIG_MODEL[${1}.revision]}.verified"

}
native-model-spec () {

    printf '%s %s' "${CONFIG_MODEL[${1}.source]}" "${CONFIG_MODEL[${1}.files]}" | fs-hash -

}
native-model-missing () {

    local directory="" file="" size=""

    directory="$(native-model-directory "${1}")" || return 0

    while read -r file size _; do
        [[ -z "${file}" ]] || [[ -f "${directory}/${file}" && "$(( $(wc -c < "${directory}/${file}") ))" == "${size}" ]] || return 0
    done <<< "${CONFIG_MODEL[${1}.files]}"

    return 1

}
native-model-space () {

    local name="${1}" directory="" file="" size="" have=0 needed=0 available="" probe=""

    directory="$(native-model-directory "${name}")" || return

    while read -r file size _; do
        [[ -n "${file}" ]] || continue
        have=0
        if [[ -f "${directory}/${file}" ]]; then have="$(( $(wc -c < "${directory}/${file}") ))"
        elif [[ -f "${directory}/${file}.part" ]]; then have="$(( $(wc -c < "${directory}/${file}.part") ))"
        fi
        (( have >= size )) || needed=$(( needed + size - have ))
    done <<< "${CONFIG_MODEL[${name}.files]}"

    probe="${directory}"
    until [[ -d "${probe}" ]]; do
        probe="${probe%/*}"
    done

    available="$(df -Pk "${probe:-/}" | awk 'NR == 2 { print $4 }')" || return
    (( available * 1024 >= needed + 1073741824 )) || { err "${name} needs $(( needed / 1048576 ))MiB plus 1024MiB of headroom under ${CONFIG[MODELS_ROOT]}; $(( available / 1024 ))MiB are free"; return; }

}
native-model-state () {

    local name="${1}" cache=missing container="" health=stopped

    if [[ "$(fs-read "$(native-model-stamp "${name}")" 2>/dev/null)" == "$(native-model-spec "${name}")" ]]; then cache=verified
    elif [[ -d "$(native-model-directory "${name}")" ]]; then cache=partial
    fi

    container="$(native-compose-models ps -q "${name}" 2>/dev/null)" || container=""
    [[ -z "${container}" ]] || health=running
    [[ -z "${container}" ]] || ! native-model-healthy "${name}" || health=healthy

    out "${cache}, ${health}"

}
native-models-healthy () {

    local name=""

    while IFS= read -r name; do
        native-model-healthy "${name}" || return 1
    done < <(config-models)

}
native-model-healthy () {

    local name="${1}" runner="${CONFIG_MODEL[${1}.runner]}"

    docker-oneshot --network "${CONFIG[COMPOSE_PROJECT]}-models" --memory 64m -- "${CONFIG[IMAGE_CURL]}" \
        --silent --fail --max-time 5 --output /dev/null "http://${name}:${CONFIG_MODEL[runner.${runner}.port]}${CONFIG_MODEL[runner.${runner}.health]}" >/dev/null 2>&1

}
