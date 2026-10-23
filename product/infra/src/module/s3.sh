s3-upload () {

    local source="${1}" destination="${2}" name="${2##*/}"

    [[ -f "${source}" && ! -L "${source}" ]] || { err "Regular file required: ${source}"; return; }
    [[ "${name}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { err "Invalid object name: ${name}"; return; }

    s3-aws "${destination}" "type=bind,source=${source},target=/upload/${name},readonly" '' s3 cp --only-show-errors "/upload/${name}" ||
        { err "Offsite upload failed: ${destination}"; return; }

}
s3-sync () {

    local source="${1}" destination="${2}"

    [[ -d "${source}" && ! -L "${source}" ]] || { err "Directory required: ${source}"; return; }

    s3-aws "${destination}" "type=bind,source=${source},target=/sync,readonly" 999:999 s3 sync --only-show-errors --exclude enabled --exclude '*.part' --exclude '*.part/*' /sync ||
        { err "Offsite sync failed: ${destination}"; return; }

}
s3-aws () {

    local destination="${1}" mount="${2}" user="${3}" uri="" endpoint="${CONFIG[BACKUP_ENDPOINT]}" region="${CONFIG[BACKUP_REGION]}"
    local -a arguments=() flags=()

    shift 3
    cfg-require BACKUP_KEY BACKUP_SECRET || return

    case "${destination}" in
        s3://*) uri="${destination}"; region="${region:-us-east-1}" ;;
        gs://*) uri="s3://${destination#gs://}"; endpoint="${endpoint:-https://storage.googleapis.com}"; region="${region:-auto}" ;;
        *)      err "Backup destination must start with s3:// or gs://"; return ;;
    esac

    [[ -z "${endpoint}" ]] || arguments+=( --endpoint-url "${endpoint}" )
    [[ -z "${user}" ]] || flags+=( --user "${user}" )

    (
        export AWS_ACCESS_KEY_ID="${CONFIG[BACKUP_KEY]}" AWS_SECRET_ACCESS_KEY="${CONFIG[BACKUP_SECRET]}" AWS_DEFAULT_REGION="${region}"
        export AWS_EC2_METADATA_DISABLED=true AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
        export AWS_RETRY_MODE=standard AWS_MAX_ATTEMPTS=5

        docker-oneshot --network bridge --memory 512m --cpus 1 --tmpfs /tmp "${flags[@]}" \
            --env AWS_ACCESS_KEY_ID --env AWS_SECRET_ACCESS_KEY --env AWS_DEFAULT_REGION --env AWS_EC2_METADATA_DISABLED \
            --env AWS_REQUEST_CHECKSUM_CALCULATION --env AWS_RESPONSE_CHECKSUM_VALIDATION --env AWS_RETRY_MODE --env AWS_MAX_ATTEMPTS --env HOME=/tmp \
            --mount "${mount}" -- "${CONFIG[IMAGE_AWS]}" "${arguments[@]}" "$@" "${uri}"
    )

}
