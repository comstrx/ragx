#!/usr/bin/env bash

## load testing with k6 inside the cluster

load_pod () {

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" get pod -l "app.kubernetes.io/name=${SERVICE_NAME},app.kubernetes.io/component=web" \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null

}
load_target () {

    ensure kubectl

    LOAD_TARGET_IP="$(k8s_gateway_address clusterIP)"

    [[ -n "${LOAD_TARGET_IP}" ]] || die "No envoy gateway service — is the gateway app synced?"

    export LOAD_TARGET_IP

}
## mint the load-test actors
load_seed () {

    local pod="" users="${1:-${LOAD_USERS}}" tokens=""

    ensure kubectl

    pod="$(load_pod)"

    [[ -n "${pod}" ]] || die "No web pod to seed load actors from"

    step "Minting ${users} load actors"

    tokens="$(kubectl -n "${K8S_NAMESPACE}" exec -i "${pod}" -- python -m bootstrap actors "${users}" 2>/dev/null | tail -1)"

    [[ -n "${tokens}" ]] || die "Actor minting returned nothing — the release has no actors command yet"

    k8s_upsert kubectl -n "${K8S_NAMESPACE}" create secret generic load-tokens \
        --from-literal=tokens="${tokens}"

    succ "Load actors ready."

}
## fire the load at the configured rate and write ratio
load_run () {

    local file=""

    ensure kubectl envsubst

    load_target

    export LOAD_RATE_PER_POD=$(( LOAD_RATE / LOAD_PODS ))

    (( LOAD_RATE_PER_POD > 0 )) || die "LOAD_RATE must be at least LOAD_PODS"

    kubectl -n "${K8S_NAMESPACE}" delete job load --ignore-not-found >/dev/null

    k8s_upsert kubectl -n "${K8S_NAMESPACE}" create configmap load-script \
        --from-file=load.js="${TEMPLATE_DIR}/k8s/load.js"

    file="$(tmp_file)"

    render "${TEMPLATE_DIR}/k8s/load.yaml" "${file}"
    run kubectl apply -f "${file}"

    succ "Load running — ${LOAD_RATE} rps across ${LOAD_PODS} pod(s), ${LOAD_WRITE_RATIO} write ratio."

}
## watch the run live
load_watch () {

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" get pods -l job-name=load --no-headers
    kubectl -n "${K8S_NAMESPACE}" get hpa --no-headers
    kubectl get nodes --no-headers

}
## summarize the last run
load_report () {

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" logs job/load --tail=-1 | sed -n '/TOTAL RESULTS/,$p'

}
## remove every load artifact
load_clean () {

    ensure kubectl

    kubectl -n "${K8S_NAMESPACE}" delete job load --ignore-not-found
    kubectl -n "${K8S_NAMESPACE}" delete configmap load-script --ignore-not-found
    kubectl -n "${K8S_NAMESPACE}" delete secret load-tokens --ignore-not-found

    succ "Load artifacts removed."

}
