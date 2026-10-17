#!/usr/bin/env bash

## database backups — take, list, restore (never over the live db)

BACKUP_HOST=""
BACKUP_PORT=""
BACKUP_PID=""
ENDPOINT=()

backup_connect () {

    BACKUP_HOST="${DB_HOST}"
    BACKUP_PORT="${DB_PORT}"

    [[ "${PLATFORM_PG_ENABLED}" == "true" ]] || return 0

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" port-forward svc/postgresql "${BACKUP_FORWARD_PORT}:5432" >/dev/null 2>&1 &
    BACKUP_PID=$!

    trap backup_release EXIT

    BACKUP_HOST=127.0.0.1
    BACKUP_PORT="${BACKUP_FORWARD_PORT}"

    local left="${BACKUP_FORWARD_TRIES}"

    while (( left-- )); do

        { : > "/dev/tcp/127.0.0.1/${BACKUP_FORWARD_PORT}"; } 2>/dev/null && return 0
        sleep "${BACKUP_FORWARD_POLL}"

    done

    die "Cannot reach the in-cluster postgres over the port-forward"

}
backup_release () {

    [[ -z "${BACKUP_PID}" ]] || kill "${BACKUP_PID}" 2>/dev/null || true

    BACKUP_PID=""

}
## take a backup right now
backup_now () {

    backup_job "${SERVICE_NAME}-backup-manual-$(date -u +%s)" dump

    succ "Backup complete — 'infra backup list' shows it."

}
backup_endpoint () {

    ENDPOINT=()

    [[ -z "${S3_ENDPOINT}" ]] || ENDPOINT=( --endpoint-url "${S3_ENDPOINT}" )

}
backup_identity () {

    local id="" key=""

    id="$(secret_get BACKUP_AWS_ACCESS_KEY_ID)"
    key="$(secret_get BACKUP_AWS_SECRET_ACCESS_KEY)"

    [[ -z "${id}" || -z "${key}" ]] || printf '%s\n' "AWS_ACCESS_KEY_ID=${id}" "AWS_SECRET_ACCESS_KEY=${key}"

}
backup_cli () {

    local identity=()

    mapfile -t identity < <(backup_identity)

    env "${identity[@]}" aws "$@"

}
## a psql shell against the backup target
backup_shell () {

    local script="${1:?Missing script}" overrides=""

    ensure kubectl

    overrides="$(printf '{"spec":{"volumes":[{"name":"backups","persistentVolumeClaim":{"claimName":"%s-backups"}}],"containers":[{"name":"shell","image":"%s","command":["sh","-c","%s"],"stdin":true,"volumeMounts":[{"name":"backups","mountPath":"/backups"}]}]}}' \
        "${SERVICE_NAME}" "${BACKUP_BASE_IMAGE}" "${script}")"

    kubectl run "${SERVICE_NAME}-backup-shell-$(date -u +%s)" -n "${K8S_NAMESPACE}" \
        --rm --attach --quiet --restart=Never \
        --image="${BACKUP_BASE_IMAGE}" --overrides="${overrides}"

}
## pull a backup to this machine
backup_local () {

    local identity=()

    ensure pg_dump

    [[ "${BACKUP_TARGET}" != "s3" ]] || ensure aws

    backup_connect
    ensure_dir "${BUILD_DIR}/backups"

    mapfile -t identity < <(backup_identity)

    env "${identity[@]}" \
        DB_HOST="${BACKUP_HOST}" DB_PORT="${BACKUP_PORT}" DB_NAME="${DB_NAME}" DB_USER="${DB_USER}" \
        PGPASSWORD="$(secret_require DB_PASSWORD)" \
        BACKUP_TARGET="${BACKUP_TARGET}" BACKUP_PATH="${BUILD_DIR}/backups" BACKUP_KEEP_DAYS="${S3_BACKUP_KEEP_DAYS}" \
        S3_BACKUP_BUCKET="${S3_BACKUP_BUCKET}" S3_ENDPOINT="${S3_ENDPOINT}" AWS_DEFAULT_REGION="${AWS_REGION}" \
        bash "${TEMPLATE_DIR}/docker/backup.sh"

    backup_release

}
## list the stored backups
backup_list () {

    if [[ "${BACKUP_TARGET}" != "s3" ]]; then

        backup_shell "ls -lh '/backups/${DB_NAME}' 2>/dev/null || echo 'no backups yet'"

        return 0

    fi

    ensure aws
    backup_endpoint

    run backup_cli s3 ls "s3://${S3_BACKUP_BUCKET}/${DB_NAME}/" --human-readable "${ENDPOINT[@]}"

}
## run the backup as a k8s job and wait
backup_job () {

    local name="${1:?Missing job name}" args="" left="${BACKUP_JOB_TRIES}"

    shift

    ensure kubectl jq

    args="$(printf '%s\n' "$@" | jq -R . | jq -sc .)"

    kubectl -n "${K8S_NAMESPACE}" get "cronjob/${SERVICE_NAME}-backup" -o json \
        | jq --arg name "${name}" --argjson args "${args}" '
            { apiVersion: "batch/v1", kind: "Job", metadata: { name: $name }, spec: .spec.jobTemplate.spec }
            | .spec.backoffLimit = 0
            | .spec.template.spec.containers[0].args = $args' \
        | kubectl -n "${K8S_NAMESPACE}" apply -f - >/dev/null \
        || die "Cannot schedule '${name}' — is the backup cronjob deployed?"

    step "Waiting for ${name}"

    while (( left-- )); do

        [[ -z "$(kubectl -n "${K8S_NAMESPACE}" get "job/${name}" -o jsonpath='{.status.conditions[*].type}')" ]] || break

        sleep "${BACKUP_JOB_POLL}"

    done

    kubectl -n "${K8S_NAMESPACE}" logs "job/${name}" --tail=-1

    [[ "$(kubectl -n "${K8S_NAMESPACE}" get "job/${name}" -o jsonpath='{.status.succeeded}')" == "1" ]] \
        || die "Job '${name}' failed — the pod log above says why"

}
## restore a stamp into a SIDE database — promote deliberately, never overwrites the live one
backup_restore () {

    local stamp="${1:?Usage: backup restore <stamp> [target-db]}" target="${2:-${DB_NAME}_restore}"

    confirm "Restore '${stamp}' into isolated database '${target}'?"

    backup_job "${SERVICE_NAME}-restore-$(date -u +%s)" restore "${stamp}" "${target}"

    succ "Restored '${stamp}' into '${target}' — verify it, then promote deliberately (never restored over '${DB_NAME}')."

}
