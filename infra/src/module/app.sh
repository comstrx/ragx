#!/usr/bin/env bash

## the application itself — one-off commands inside the release, wherever the cluster lives

app_argv () {

    local arg="" out=""

    for arg in "$@"; do

        arg="${arg//\\/\\\\}"
        arg="${arg//\"/\\\"}"
        out+="${out:+,}\"${arg}\""

    done

    printf '[%s]' "${out}"

}
app_image () {

    kubectl -n "${K8S_NAMESPACE}" get "deploy/${SERVICE_NAME}-web" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true

}
app_reachable () {

    command -v kubectl >/dev/null 2>&1 && kubectl get --raw=/readyz --request-timeout="${APP_RUN_REACH}s" >/dev/null 2>&1

}
## hand the verb to the bundle on the server when the cluster is out of reach from here
app_forward () {

    local verb="${1:?Missing verb}" path=""

    shift

    [[ "${CLUSTER_SOURCE}" != "managed" ]] || die "No cluster reach — run: infra k8s kubeconfig"

    path="$(server_path)"

    server_run "cd '${path}' && ./infra --config .env -s ${STACK} -y app ${verb} -- $(printf '%q ' "$@")"

}
app_phase () {

    kubectl -n "${K8S_NAMESPACE}" get pod -l "job-name=${1}" -o jsonpath='{.items[*].status.phase}' 2>/dev/null || true

}
app_outcome () {

    kubectl -n "${K8S_NAMESPACE}" get "job/${1}" -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null || true

}
app_settled () {

    [[ "${1}" != "/" ]]

}
app_verdict () {

    [[ "${1}" == 1/* ]]

}
## render the job that runs one command on the release — the image, env, secrets and storage the app itself runs with
app_manifest () {

    local dst="${1:?Missing destination}" name="${2:?Missing job name}" image="${3:?Missing image}"

    shift 3

    APP_RUN_COMMAND="$(app_argv "$@")"

    export APP_RUN_COMMAND APP_RUN_NAME="${name}" APP_RUN_IMAGE="${image}"
    export APP_RUN_PULL_SECRETS="[]" APP_RUN_MOUNTS="[]" APP_RUN_VOLUMES="[]"

    [[ "${REGISTRY_PULL}" != "true" ]] || APP_RUN_PULL_SECRETS="[{name: pull-secret}]"

    if [[ "${APP_STORAGE}" == "pvc" ]]; then

        APP_RUN_MOUNTS="[{name: storage, mountPath: ${APP_STORAGE_MOUNT}}]"
        APP_RUN_VOLUMES="[{name: storage, persistentVolumeClaim: {claimName: ${SERVICE_NAME}-storage}}]"

    fi

    render "${TEMPLATE_DIR}/k8s/run.yaml" "${dst}"

}
## run one command as a job on this release — same image, env and secrets as the app; the job's exit code is yours
app_run () {

    local name="" image="" file="" phase="" waited=0

    [[ "${1:-}" != "--" ]] || shift

    (( $# )) || die "Usage: app run -- <command...>"

    if ! app_reachable; then app_forward run "$@"; return $?; fi

    ensure kubectl envsubst

    image="$(app_image)"

    [[ -n "${image}" ]] || die "No '${SERVICE_NAME}-web' deployment in '${K8S_NAMESPACE}' — is the release live?"

    name="${SERVICE_NAME}-run-$(date +%s)"
    file="$(tmp_file)"

    app_manifest "${file}" "${name}" "${image}" "$@"

    step "Running on ${image##*:} — $*"

    kubectl apply -f "${file}" >/dev/null || die "Cannot create job ${name}"

    phase="$(app_phase "${name}")"

    while [[ -z "${phase}" || "${phase}" == "Pending" ]]; do

        if (( waited >= APP_RUN_START )); then

            kubectl -n "${K8S_NAMESPACE}" describe pod -l "job-name=${name}" | tail -n "${POD_LOG_LINES}"
            die "Job ${name} never started within ${APP_RUN_START}s — the events above carry the reason"

        fi

        sleep "${APP_RUN_POLL}"
        waited=$(( waited + APP_RUN_POLL ))
        phase="$(app_phase "${name}")"

    done

    kubectl -n "${K8S_NAMESPACE}" logs -f "job/${name}" 2>/dev/null || true

    until app_settled "$(app_outcome "${name}")"; do sleep "${APP_RUN_POLL}"; done

    app_verdict "$(app_outcome "${name}")" || die "Job ${name} failed — kubectl -n ${K8S_NAMESPACE} describe job/${name}"

    succ "Job ${name} succeeded."

}
## list the one-off runs still on the cluster
app_runs () {

    if ! app_reachable; then app_forward runs; return $?; fi

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" get jobs -l "app.kubernetes.io/name=${SERVICE_NAME},app.kubernetes.io/component=run" --no-headers

}
