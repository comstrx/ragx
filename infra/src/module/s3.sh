s3-upload () {

    local source="${1}" destination="${2}" uri="" endpoint="${CONFIG[BACKUP_ENDPOINT]}" region="${CONFIG[BACKUP_REGION]}" name="${2##*/}"
    local -a arguments=()

    cfg-require BACKUP_KEY BACKUP_SECRET || return
    [[ -f "${source}" && ! -L "${source}" ]] || { err "Regular file required: ${source}"; return; }
    [[ "${name}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { err "Invalid object name: ${name}"; return; }

    case "${destination}" in
        s3://*) uri="${destination}"; region="${region:-us-east-1}" ;;
        gs://*) uri="s3://${destination#gs://}"; endpoint="${endpoint:-https://storage.googleapis.com}"; region="${region:-auto}" ;;
        *)      err "Backup destination must start with s3:// or gs://"; return ;;
    esac

    [[ -z "${endpoint}" ]] || arguments+=( --endpoint-url "${endpoint}" )

    (
        export AWS_ACCESS_KEY_ID="${CONFIG[BACKUP_KEY]}" AWS_SECRET_ACCESS_KEY="${CONFIG[BACKUP_SECRET]}" AWS_DEFAULT_REGION="${region}"
        export AWS_EC2_METADATA_DISABLED=true AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required

        docker-oneshot --network bridge --memory 512m --cpus 1 --tmpfs /tmp \
            --env AWS_ACCESS_KEY_ID --env AWS_SECRET_ACCESS_KEY --env AWS_DEFAULT_REGION --env AWS_EC2_METADATA_DISABLED \
            --env AWS_REQUEST_CHECKSUM_CALCULATION --env AWS_RESPONSE_CHECKSUM_VALIDATION --env HOME=/tmp \
            --mount "type=bind,source=${source},target=/upload/${name},readonly" \
            -- "${CONFIG[IMAGE_AWS]}" "${arguments[@]}" s3 cp --only-show-errors "/upload/${name}" "${uri}"
    ) || { err "Offsite upload failed: ${destination}"; return; }

}
