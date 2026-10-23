huggingface-url () {

    local location="${1}" revision="${2}" file="${3}"

    [[ "${location}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { err "Hugging Face location must be OWNER/REPOSITORY: ${location}"; return; }
    [[ "${revision}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && "${file}" =~ ^[A-Za-z0-9_][A-Za-z0-9_./-]*$ && "/${file}/" != */../* ]] || { err "Invalid Hugging Face revision or file: ${revision} ${file}"; return; }

    out "${MANIFEST[endpoints.huggingface]}/${location}/resolve/${revision}/${file}"

}
