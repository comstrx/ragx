declare -ga CONFIG_MODELS=()
declare -ga CONFIG_RUNNER_COLUMNS=( name image port health args )
declare -ga CONFIG_MODEL_COLUMNS=( name runner source revision memory cpus batch args )
declare -ga CONFIG_MODEL_FILE_COLUMNS=( model file size sha256 )
declare -gA CONFIG_MODEL=()

CONFIG_RUNNERS_TABLE='
name      image     port  health   args
tei       tei       8080  /health  --model-id /model --hostname 0.0.0.0 --port {port} --max-batch-tokens {batch}
llamacpp  llamacpp  8080  /health  --host 0.0.0.0 --port {port} --batch-size {batch}
'

CONFIG_MODELS_TABLE='
name      runner  source                               revision                                  memory  cpus  batch  args
embedder  tei     huggingface:BAAI/bge-m3              9a0624b896d81da7492a910ffa53731274b6cf3d  4g      2     2048   --auto-truncate
ranker    tei     huggingface:BAAI/bge-reranker-v2-m3  953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e  4g      2     2048   --auto-truncate
'

CONFIG_MODEL_FILES='
model     file                     size        sha256
embedder  1_Pooling/config.json    191         e54c164a07274f2eb45bb724f54a79d1efcc90c41573887cd9a29aeee0597352
embedder  config.json              687         26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa
embedder  modules.json             349         84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf
embedder  special_tokens_map.json  964         8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835
embedder  tokenizer_config.json    444         a62b2b6784f990259fddef5f16388693a8043be4f69179e6a5257eeb3f9abac4
embedder  tokenizer.json           17098108    21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08
embedder  model.safetensors        2271064456  993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e
ranker    config.json              795         13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a
ranker    special_tokens_map.json  964         8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835
ranker    tokenizer_config.json    1173        7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4
ranker    tokenizer.json           17098273    69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15
ranker    model.safetensors        2271071852  d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286
'

config-models-load () {

    local records="" name="" image="" port="" health="" args="" runner="" source="" revision="" memory="" cpus="" batch="" file="" size="" digest="" failed=0

    config-inputs-forget models
    CONFIG_MODELS=()
    CONFIG_MODEL=()

    records="$(config-table Runners "${CONFIG_RUNNERS_TABLE}" "${CONFIG_RUNNER_COLUMNS[@]}")" || return

    while IFS=$'\x1f' read -r name image port health args; do
        [[ -n "${name}" ]] || continue
        [[ "${name}" =~ ^[a-z][a-z0-9]{0,30}$ ]] || { err "Runner name must be lowercase letters and digits: ${name}"; failed=1; continue; }
        [[ -n "${MANIFEST[images.${image}]:-}" ]] || { err "Runner ${name}: Bash.toml has no image ${image}"; failed=1; }
        parse-port "${port}" || { err "Runner ${name}: invalid port"; failed=1; }
        parse-path "${health}" || { err "Runner ${name}: invalid health path"; failed=1; }
        CONFIG_MODEL["runner.${name}.image"]="${image}"
        CONFIG_MODEL["runner.${name}.port"]="${port}"
        CONFIG_MODEL["runner.${name}.health"]="${health}"
        CONFIG_MODEL["runner.${name}.args"]="${args}"
    done <<< "${records}"

    records="$(config-table Models "${CONFIG_MODELS_TABLE}" "${CONFIG_MODEL_COLUMNS[@]}")" || return

    while IFS=$'\x1f' read -r name runner source revision memory cpus batch args; do
        [[ -n "${name}" ]] || continue
        [[ "${name}" =~ ^[a-z][a-z0-9]{0,30}$ ]] || { err "Model name must be lowercase letters and digits: ${name}"; failed=1; continue; }
        [[ " ${CONFIG_MODELS[*]} ${CONFIG_PARTS[*]} worker scheduler grafana acme unavailable " != *" ${name} "* ]] || { err "Model name ${name} is taken by a part, a service or another model"; failed=1; continue; }
        [[ -n "${CONFIG_MODEL[runner.${runner}.image]:-}" ]] || { err "Model ${name}: unknown runner ${runner}"; failed=1; }
        [[ "${source}" =~ ^[a-z]+:[A-Za-z0-9][A-Za-z0-9._/-]*$ && "/${source#*:}/" != */../* ]] || { err "Model ${name}: source must be SCHEME:LOCATION"; failed=1; }
        [[ "${revision}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { err "Model ${name}: invalid revision"; failed=1; }
        [[ "${args}" != - ]] || args=""
        CONFIG_MODELS+=( "${name}" )
        CONFIG_MODEL["${name}.runner"]="${runner}"
        CONFIG_MODEL["${name}.source"]="${source}"
        CONFIG_MODEL["${name}.revision"]="${revision}"
        CONFIG_MODEL["${name}.args"]="${args}"
        CONFIG_MODEL["${name}.files"]=""
        config-input models "${name^^}_MEMORY" "${memory}" || failed=1
        config-input models "${name^^}_CPUS" "${cpus}" || failed=1
        config-input models "${name^^}_BATCH" "${batch}" || failed=1
    done <<< "${records}"

    records="$(config-table Model-files "${CONFIG_MODEL_FILES}" "${CONFIG_MODEL_FILE_COLUMNS[@]}")" || return

    while IFS=$'\x1f' read -r name file size digest; do
        [[ -n "${name}" ]] || continue
        [[ -n "${CONFIG_MODEL[${name}.runner]:-}" ]] || { err "Model file for an unknown model: ${name} ${file}"; failed=1; continue; }
        config-model-file "${name}" "${file}" "${size}" "${digest}" || { failed=1; continue; }
        CONFIG_MODEL["${name}.files"]+="${file} ${size} ${digest}"$'\n'
    done <<< "${records}"

    for name in "${CONFIG_MODELS[@]}"; do
        [[ -n "${CONFIG_MODEL[${name}.files]}" ]] || { err "Model ${name} lists no file"; failed=1; }
    done

    (( failed == 0 ))

}
config-model-file () {

    local name="${1}" file="${2}" size="${3}" digest="${4}"

    [[ "${file}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$ ]] || { err "Model ${name}: unsafe file path ${file}"; return; }
    [[ ! "${file,,}" =~ \.(bin|pt|pth|pkl|pickle|ckpt|joblib|npy|npz)$ ]] || { err "Model ${name}: ${file} is a pickle format that can run code on load; pin safetensors, GGUF or ONNX"; return; }
    [[ "${file}" != *.part && $'\n'"${CONFIG_MODEL[${name}.files]}" != *$'\n'"${file} "* ]] || { err "Model ${name}: ${file} is listed twice or reserved"; return; }
    [[ "${size}" =~ ^[1-9][0-9]{0,14}$ ]] || { err "Model ${name}: ${file} needs its size in bytes"; return; }
    [[ "${digest}" =~ ^[a-f0-9]{64}$ ]] || { err "Model ${name}: ${file} needs its SHA-256"; return; }

}
config-models-derive () {

    local name="" runner=""

    cfg-set MODELS_ROOT "${CONFIG[MODELS_DIR]:-${CONFIG[STATE_ROOT]}/models}"

    for name in "${CONFIG_MODELS[@]}"; do
        runner="${CONFIG_MODEL[${name}.runner]}"
        cfg-set "${name^^}_URL" "http://${name}:${CONFIG_MODEL[runner.${runner}.port]}"
    done

}
config-models () {

    config-list "${CONFIG[MODELS]:-}"

}
config-models-valid () {

    local name="" failed=0
    local -A seen=()

    while IFS= read -r name; do
        [[ -n "${CONFIG_MODEL[${name}.runner]:-}" ]] || { err "MODELS names an unknown model: ${name} (the models table has ${CONFIG_MODELS[*]})"; failed=1; continue; }
        [[ -z "${seen[${name}]:-}" ]] || { err "MODELS names ${name} twice"; failed=1; continue; }
        seen["${name}"]=1
        config-check memory "${name^^}_MEMORY" || failed=1
        config-check cpus "${name^^}_CPUS" || failed=1
        config-check positive "${name^^}_BATCH" || failed=1
    done < <(config-models)

    (( failed == 0 ))

}
config-model-args () {

    local name="${1}" runner="${CONFIG_MODEL[${1}.runner]}" args=""

    args="${CONFIG_MODEL[runner.${runner}.args]} ${CONFIG_MODEL[${name}.args]}"
    args="${args//\{port\}/${CONFIG_MODEL[runner.${runner}.port]}}"
    args="${args//\{batch\}/${CONFIG[${name^^}_BATCH]}}"

    out "${args% }"

}
