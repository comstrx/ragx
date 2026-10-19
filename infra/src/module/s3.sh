s3-upload () {

    local source="${1}" destination="${2}"
    local -a arguments=()

    cfg-require BACKUP_S3_KEY BACKUP_S3_SECRET BACKUP_S3_REGION || return
    [[ "${destination}" == s3://* ]] || { err "S3 destination must start with s3://"; return; }
    need aws || return

    [[ -z "${CONFIG[BACKUP_S3_ENDPOINT]}" ]] || arguments+=( --endpoint-url "${CONFIG[BACKUP_S3_ENDPOINT]}" )

    (
        export AWS_ACCESS_KEY_ID="${CONFIG[BACKUP_S3_KEY]}" AWS_SECRET_ACCESS_KEY="${CONFIG[BACKUP_S3_SECRET]}"
        export AWS_DEFAULT_REGION="${CONFIG[BACKUP_S3_REGION]}" AWS_EC2_METADATA_DISABLED=true
        aws "${arguments[@]}" s3 cp --only-show-errors "${source}" "${destination}"
    ) || { err "S3 upload failed: ${destination}"; return; }

}
