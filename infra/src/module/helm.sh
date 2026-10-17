#!/usr/bin/env bash

## chart shaping — values generation and direct installs

helm_charts () {

    printf '%s' "${TEMPLATE_DIR}/helm"

}
helm_values_dir () {

    printf '%s' "${BUILD_DIR}/helm"

}
helm_values () {

    printf '%s' "$(helm_values_dir)/${SERVICE_NAME}.${STACK}.yaml"

}
## the stack values, seeded on first use — a run never reads values it did not generate
helm_seeded () {

    [[ -f "$(helm_values)" ]] || helm_seed >/dev/null

    printf '%s' "$(helm_values)"

}
## the image tag this run releases
helm_tag () {

    ci_tag

}
## lint the charts
helm_lint () {

    ensure helm

    run helm lint "$(helm_charts)/service" -f "$(helm_seeded)"
    run helm lint "$(helm_charts)/platform"
    run helm lint "$(helm_charts)/gateway" --set domain="${LINT_DOMAIN}" --set sslEmail="${LINT_EMAIL}"
    run helm lint "$(helm_charts)/observability" --set host="${LINT_DOMAIN}"
    run helm lint "${TEMPLATE_DIR}/argocd/apps"

    succ "Helm charts lint clean."

}
## render a chart to stdout for eyeballing
helm_template () {

    local file=""

    file="$(helm_values)"

    if [[ $# -gt 0 && -f "${1}" ]]; then file="${1}"; shift; fi

    ensure helm

    helm template "${SERVICE_NAME}" "$(helm_charts)/service" -f "${file}" -n "${K8S_NAMESPACE}" "$@"

}
## generate the stack values file from config — overwrites hand edits, commit the result
helm_seed () {

    local file="${1:-$(helm_values)}" registry="" tag=""

    registry="$(ci_registry)"

    [[ "${CLOUD_IDENTITY}" == "true" || -n "${REGISTRY}" ]] || die "Without a cloud identity the cluster needs REGISTRY — a registry it can log into"

    [[ -n "${registry}" ]] || registry="$(tofu_output registry 2>/dev/null)" || true
    [[ -n "${registry}" ]] || die "Missing REGISTRY — set it in your config or apply the stack"

    tag="$(ci_tag)"

    export SEED_IMAGE="${registry}/${IMAGE_NAME}"
    export SEED_TAG="${tag}"
    export SEED_SECTION="${GATEWAY_SECTION}" SEED_PULL_SECRETS=[]
    export SEED_APP_URL="https://${GATEWAY_DOMAIN:-${BASE_DOMAIN}}"

    export SEED_BACKUP_BUCKET="" SEED_BACKUP_PVC=true SEED_BACKUP_REGION=""

    [[ "${REGISTRY_PULL}" != "true" ]] || SEED_PULL_SECRETS="[pull-secret]"

    if [[ "${BACKUP_TARGET}" != "s3" ]]; then

        [[ "${APP_STORAGE}" == "pvc" ]] || die "BACKUP_TARGET=pvc needs a cluster with local storage — set BACKUP_TARGET=s3 on '${STACK}'"

    else

        [[ -n "${S3_BACKUP_BUCKET}" ]] || die "BACKUP_TARGET=s3 needs S3_BACKUP_BUCKET — set it, or use BACKUP_TARGET=pvc"

        [[ -n "${S3_ENDPOINT}" || -n "${AWS_REGION}" ]] || die "BACKUP_TARGET=s3 needs AWS_REGION — the job cannot reach a bucket without one"

        export SEED_BACKUP_BUCKET="${S3_BACKUP_BUCKET}" SEED_BACKUP_PVC=false SEED_BACKUP_REGION="${AWS_REGION}"

    fi

    export SEED_DB_APP_USER="${DB_APP_USER:-${DB_USER}}"
    export SEED_TRUST_PROXIES="${TRUST_PROXIES:-$([[ "${CLUSTER_SOURCE}" == "managed" ]] && printf '%s' "${VPC_CIDR}" || printf '%s' "${POD_CIDR}")}${EDGE_TRUSTED_CIDRS:+,${EDGE_TRUSTED_CIDRS}}"

    if [[ "${PLATFORM_PG_ENABLED}" == "true" ]]; then

        export SEED_DB_HOST="postgresql.${K8S_NAMESPACE}.svc.cluster.local" SEED_DB_SSLMODE=prefer SEED_DB_SEARCH_PATH="${DB_SEARCH_PATH}" SEED_DB_READ_HOST=""

    else

        [[ -n "${DB_HOST}" ]] || DB_HOST="$(tofu_output db_host 2>/dev/null)" || die "Missing DB_HOST — set it in your config or apply the stack"

        export SEED_DB_HOST="${DB_HOST%:5432}" SEED_DB_SSLMODE="${DB_SSLMODE}" SEED_DB_SEARCH_PATH="${DB_SEARCH_PATH}" SEED_DB_READ_HOST="${DB_READ_HOST}"

    fi

    if [[ "${APP_STORAGE}" == "pvc" ]]; then

        export SEED_DISK=public SEED_BUCKET="" SEED_REGION="" SEED_PVC=true

    else

        [[ "${CLOUD_IDENTITY}" == "true" ]] || die "APP_STORAGE=s3 needs a cloud identity for the pods — use pvc"

        export SEED_DISK=s3 SEED_BUCKET="${S3_BUCKET}" SEED_REGION="${AWS_REGION}" SEED_PVC=false

    fi

    render "$(helm_charts)/values/${SERVICE_NAME}.tpl" "${file}"

    succ "Seeded $(basename "${file}") for '${STACK}' on ${SEED_TAG}."

}
## install the service chart directly, bypassing argocd (confirmed)
helm_deploy () {

    ensure helm

    confirm "Deploy '${SERVICE_NAME}' directly with helm (bypassing ArgoCD)?"

    run helm upgrade --install "${SERVICE_NAME}" "$(helm_charts)/service" \
        -f "$(helm_seeded)" \
        -n "${K8S_NAMESPACE}" --create-namespace \
        --wait --timeout "${HELM_TIMEOUT}"

}
## install the platform chart directly, bypassing argocd (confirmed)
helm_platform () {

    ensure helm

    confirm "Deploy the platform chart directly with helm (bypassing ArgoCD)?"

    run helm upgrade --install platform "$(helm_charts)/platform" \
        --set redis.enabled="${PLATFORM_REDIS_ENABLED}" \
        --set redis.image="${PLATFORM_REDIS_IMAGE}" \
        --set redis.size="${PLATFORM_REDIS_SIZE}" \
        --set postgresql.enabled="${PLATFORM_PG_ENABLED}" \
        --set postgresql.image="${PLATFORM_PG_IMAGE}" \
        --set postgresql.size="${PLATFORM_PG_SIZE}" \
        --set postgresql.database="${DB_NAME}" \
        --set postgresql.username="${DB_USER}" \
        --set storageClass="${PLATFORM_STORAGE_CLASS}" \
        -n "${K8S_NAMESPACE}" --create-namespace \
        --wait --timeout "${HELM_TIMEOUT}"

}
## diff the rendered chart against the cluster
helm_diff () {

    ensure helm kubectl

    helm_template "$@" | kubectl diff -f - || true

}
## remove the direct helm release
helm_uninstall () {

    ensure helm

    confirm "Uninstall release '${SERVICE_NAME}' from '${K8S_NAMESPACE}'?"

    run helm uninstall "${SERVICE_NAME}" -n "${K8S_NAMESPACE}"

}
