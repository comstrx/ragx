#!/usr/bin/env bash

## gitops — argocd installation and the app-of-apps

## install argocd at the pinned version
argocd_install () {

    ensure kubectl

    k8s_namespace "${ARGOCD_NAMESPACE}"

    run kubectl apply -n "${ARGOCD_NAMESPACE}" --server-side --force-conflicts \
        -f "${ARGOCD_MANIFESTS}/${ARGOCD_VERSION}/manifests/install.yaml"

    run kubectl -n "${ARGOCD_NAMESPACE}" patch configmap argocd-cm --patch-file "${TEMPLATE_DIR}/argocd/health.yaml"

    run kubectl -n "${ARGOCD_NAMESPACE}" rollout status deploy/argocd-server --timeout=300s

    succ "ArgoCD ${ARGOCD_VERSION} installed."

}
## print the current admin password
argocd_password () {

    ensure kubectl

    kubectl -n "${ARGOCD_NAMESPACE}" get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
    log ""

}
## move admin onto ARGOCD_PASSWORD and drop the bootstrap secret
argocd_rotate () {

    local hash=""

    ensure kubectl htpasswd

    hash="$(htpasswd -nbBC 10 "" "$(secret_require ARGOCD_PASSWORD)" | tr -d ':\n')"
    hash="${hash/#\$2y/\$2a}"

    kubectl -n "${ARGOCD_NAMESPACE}" patch secret argocd-secret --type merge \
        -p "{\"stringData\":{\"admin.password\":\"${hash}\",\"admin.passwordMtime\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}" >/dev/null \
        || die "Cannot move the ArgoCD admin onto ARGOCD_PASSWORD"

    run kubectl -n "${ARGOCD_NAMESPACE}" delete secret argocd-initial-admin-secret --ignore-not-found

    succ "ArgoCD admin moved onto ARGOCD_PASSWORD — the bootstrap secret is gone."

}
## the shields in front of the edge, as the json list the root carries
argocd_trusted () {

    local cidr="" list=""

    for cidr in ${EDGE_TRUSTED_CIDRS//,/ }; do

        list+="${list:+,}\"${cidr}\""

    done

    printf '[%s]' "${list}"

}
## apply the app-of-apps — argocd owns the cluster from git
argocd_bootstrap () {

    ensure kubectl

    if [[ "${AUTOSCALER_ENABLED}" == "true" && -z "${AUTOSCALER_ROLE_ARN}" ]]; then

        AUTOSCALER_ROLE_ARN="$(tofu_output autoscaler_role_arn 2>/dev/null)" || die "Missing AUTOSCALER_ROLE_ARN — apply the stack first"
        export AUTOSCALER_ROLE_ARN

    fi

    if [[ -n "${EDGE_TYPE}" && -n "${PROVISIONER}" && -z "${EDGE_EIPS}" ]]; then

        EDGE_EIPS="$(tofu_output edge_eips 2>/dev/null)" || die "Missing EDGE_EIPS — the edge holds fixed addresses, apply the stack first"
        export EDGE_EIPS

    fi

    EDGE_ANNOTATIONS="$(cloud edge_annotations)"
    EDGE_TRUSTED_JSON="$(argocd_trusted)"
    export EDGE_ANNOTATIONS EDGE_TRUSTED_JSON

    argocd_repo

    helm_seed "${BUILD_DIR}/argocd/service.yaml" >/dev/null

    SERVICE_VALUES="$(sed 's/^/          /' "${BUILD_DIR}/argocd/service.yaml")"
    export SERVICE_VALUES

    render "${TEMPLATE_DIR}/argocd/project.yaml" "${BUILD_DIR}/argocd/project.yaml"
    render "${TEMPLATE_DIR}/argocd/root.yaml" "${BUILD_DIR}/argocd/root.yaml"

    run kubectl apply -f "${BUILD_DIR}/argocd/project.yaml"

    run kubectl delete application root -n "${ARGOCD_NAMESPACE}" --cascade=orphan --ignore-not-found

    run kubectl apply -f "${BUILD_DIR}/argocd/root.yaml"

    succ "App-of-apps bootstrapped — ArgoCD reads ${INFRA_REPO_URL} at ${INFRA_TAG}; the release rides the root."

}
## apply the git repository credentials
argocd_repo () {

    local token=""

    ensure kubectl

    token="$(secret_require GIT_TOKEN)"

    k8s_upsert kubectl create secret generic repo-creds \
        -n "${ARGOCD_NAMESPACE}" \
        --from-literal=type=git \
        --from-literal=url="${INFRA_REPO_URL}" \
        --from-literal=username=git \
        --from-literal=password="${token}"

    kubectl label secret repo-creds -n "${ARGOCD_NAMESPACE}" \
        argocd.argoproj.io/secret-type=repository --overwrite

    succ "Repository credentials applied."

}
## true when an application gave up on its revision, or has held one operation longer than any sync should — a retrying operation pins argocd to the revision it started on, so the newest commit is never even looked at
argocd_stalled () {

    local app="${1:-root}" phase="" started="" age=0 terminate='{"status":{"operationState":{"phase":"Terminating"}}}'

    read -r phase started < <(kubectl -n "${ARGOCD_NAMESPACE}" get application "${app}" -o jsonpath='{.status.sync.status}/{.status.operationState.phase} {.status.operationState.startedAt}' 2>/dev/null)

    case "${phase}" in

        */Failed | */Error ) return 0 ;;
        */Running ) [[ -n "${started}" ]] || return 1 ;;
        * ) return 1 ;;

    esac

    age=$(( $(date +%s) - $(date -d "${started}" +%s) ))

    (( age > ARGOCD_SYNC_STALL )) || return 1

    warn "Sync of '${app}' has run ${age}s — terminating it so the newest revision can take over"

    kubectl -n "${ARGOCD_NAMESPACE}" patch application "${app}" --type merge -p "${terminate}" >/dev/null 2>&1 \
        || kubectl -n "${ARGOCD_NAMESPACE}" patch application "${app}" --subresource=status --type merge -p "${terminate}" >/dev/null 2>&1 \
        || true

}
## what argocd thinks of an application right now — sync, health, the revision it sits on, and why its last operation stopped
argocd_report () {

    local app="${1:-root}" report=""

    ensure kubectl

    report="$(kubectl -n "${ARGOCD_NAMESPACE}" get application "${app}" \
        -o jsonpath='{.metadata.name}: sync={.status.sync.status} health={.status.health.status} phase={.status.operationState.phase} revision={.status.sync.revision}{"\n"}  reason: {.status.operationState.message}{"\n"}{range .status.conditions[*]}  {.type}: {.message}{"\n"}{end}' 2>/dev/null || true)"

    [[ -n "${report}" ]] || return 0

    printf '%s\n' "${report}" >&2

}
## force-sync an application now
argocd_sync () {

    ensure kubectl

    run kubectl -n "${ARGOCD_NAMESPACE}" patch application "${1:-root}" \
        --type merge -p '{"operation":{"initiatedBy":{"username":"infra"},"sync":{}}}'

}
