#!/usr/bin/env bash

## the aws provider — every aws byte lives here, dispatched through `cloud <verb>`

## show the caller identity and region
aws_whoami () {

    ensure aws

    run aws sts get-caller-identity --output table
    info "Region: ${AWS_REGION}"

}
## create a hardened s3 bucket: versioning, encryption, public block, optional lifecycle
aws_bucket () {

    local name="${1:?Missing bucket name}" region="${2:-${AWS_REGION}}" expire="${3:-}"

    ensure aws

    if aws s3api head-bucket --bucket "${name}" 2>/dev/null; then

        info "Bucket exists: ${name}"

    else

        step "Creating bucket: ${name}"

        if [[ "${region}" == "us-east-1" ]]; then

            aws s3api create-bucket --bucket "${name}" --region "${region}" \
                || die "Cannot create bucket: ${name}"

        else

            aws s3api create-bucket --bucket "${name}" --region "${region}" \
                --create-bucket-configuration "LocationConstraint=${region}" \
                || die "Cannot create bucket: ${name}"

        fi

    fi

    aws s3api put-bucket-versioning --bucket "${name}" \
        --versioning-configuration Status=Enabled

    aws s3api put-bucket-encryption --bucket "${name}" \
        --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

    aws s3api put-public-access-block --bucket "${name}" \
        --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

    [[ -z "${expire}" ]] || aws s3api put-bucket-lifecycle-configuration --bucket "${name}" \
        --lifecycle-configuration "{\"Rules\":[{\"ID\":\"hygiene\",\"Status\":\"Enabled\",\"Filter\":{},\"Expiration\":{\"Days\":${expire}},\"NoncurrentVersionExpiration\":{\"NoncurrentDays\":${expire}},\"AbortIncompleteMultipartUpload\":{\"DaysAfterInitiation\":7}}]}"

    succ "Bucket ready: ${name}"

}
aws_state_bucket () {

    aws_bucket "${TF_STATE_BUCKET}" "${TF_STATE_REGION:-${AWS_REGION}}"

}
aws_backup_bucket () {

    aws_bucket "${S3_BACKUP_BUCKET}" "${AWS_REGION}" "${S3_BACKUP_KEEP_DAYS}"

}
## drop a state lock no run can hold anymore — a killed run leaves one behind, every later run would wait then die
aws_stale_lock () {

    local key="${PROJECT}/${STACK}.tfstate.tflock" born="" age=0

    ensure aws jq

    born="$(aws s3 cp "s3://${TF_STATE_BUCKET}/${key}" - 2>/dev/null | jq -r '.Created // empty' 2>/dev/null)" || true

    [[ -n "${born}" ]] || return 0

    age=$(( $(date +%s) - $(date -d "${born}" +%s) ))

    (( age > TOFU_LOCK_STALE )) || die "The '${STACK}' state is locked by a run ${age}s old — let it finish, or free it: infra tofu unlock"

    warn "Dropping a ${age}s-old state lock — no run lives that long"

    aws_unlock

}
aws_unlock () {

    ensure aws

    run aws s3 rm "s3://${TF_STATE_BUCKET}/${PROJECT}/${STACK}.tfstate.tflock"

}
aws_hcl_list () {

    local item="" out=""

    for item in ${1//,/ }; do

        out+="\"${item}\","

    done

    printf '[%s]' "${out%,}"

}
aws_tofu_prereqs () {

    aws_state_bucket
    aws_backup_bucket
    aws_stale_lock

}
aws_backend_flags () {

    printf '%s\n' \
        "-backend-config=bucket=${TF_STATE_BUCKET}" \
        "-backend-config=key=${PROJECT}/${STACK}.tfstate" \
        "-backend-config=region=${TF_STATE_REGION:-${AWS_REGION}}" \
        "-backend-config=encrypt=true" \
        "-backend-config=use_lockfile=true"

}
aws_db_unguard () {

    ensure aws

    aws rds describe-db-instances --db-instance-identifier "${PROJECT}" >/dev/null 2>&1 || return 0

    step "Lowering the database deletion guard — this destroy names it on purpose"

    run aws rds modify-db-instance --db-instance-identifier "${PROJECT}" \
        --no-deletion-protection --apply-immediately >/dev/null \
        || die "Cannot lower deletion protection on '${PROJECT}' — the destroy would die against it"

}
aws_registry_login () {

    ensure aws

    aws ecr get-login-password --region "${AWS_REGION}" \
        | docker login --username AWS --password-stdin "${1:?Missing registry}" \
        || die "ECR login failed"

}
aws_registry_critical () {

    local tag="${1:?Missing image tag}" critical=""

    ensure aws

    step "Waiting for the ECR scan of ${tag}"

    aws ecr wait image-scan-complete --repository-name "${IMAGE_NAME}" \
        --image-id imageTag="${tag}" --region "${AWS_REGION}" \
        || die "ECR scan never completed for ${tag}"

    critical="$(aws ecr describe-image-scan-findings --repository-name "${IMAGE_NAME}" \
        --image-id imageTag="${tag}" --region "${AWS_REGION}" --no-paginate \
        --query 'imageScanFindings.findingSeverityCounts.CRITICAL' --output text | head -1)"

    [[ "${critical}" =~ ^[0-9]+$ ]] || critical=0

    printf '%s' "${critical}"

}
aws_registry_refresher () {

    ensure kubectl

    [[ -n "${ECR_REGISTRY}" ]] || die "Missing ECR_REGISTRY — the refresher is ECR-only"

    render "${TEMPLATE_DIR}/aws/ecr-refresher.yaml" "${BUILD_DIR}/k8s/ecr-refresher.yaml"

    run kubectl apply -f "${BUILD_DIR}/k8s/ecr-refresher.yaml"

    succ "ECR pull-secret refresher scheduled — 6h cadence against the 12h token."

}
aws_tofu_vars () {

        printf 'name             = "%s"\n' "${PROJECT}"
        printf 'region           = "%s"\n' "${AWS_REGION}"
        printf 'vpc_cidr         = "%s"\n' "${VPC_CIDR}"
        printf 'az_count         = %s\n'   "${AZ_COUNT}"
        printf 's3_bucket        = "%s"\n' "${S3_BUCKET}"
        printf 'backup_bucket    = "%s"\n' "${S3_BACKUP_BUCKET}"
        printf 'ecr_repository   = "%s"\n' "${IMAGE_NAME}"
        printf 'ecr_keep_images  = %s\n'   "${ECR_KEEP_IMAGES}"

        if [[ "${DATABASE}" != "managed" ]]; then

            printf 'ec2_type       = "%s"\n' "${EC2_TYPE}"
            printf 'ec2_disk_gb    = %s\n'   "${EC2_DISK_GB}"
            printf 'ec2_ubuntu     = "%s"\n' "${EC2_UBUNTU}"
            printf 'admin_cidrs    = %s\n'   "$(aws_hcl_list "${ADMIN_CIDRS}")"
            printf 'ssh_cidrs      = %s\n'   "$(aws_hcl_list "${SSH_CIDRS}")"
            printf 'ssh_public_key = "%s"\n' "${SSH_PUBLIC_KEY}"

        else

            printf 'admin_cidrs        = %s\n'   "$(aws_hcl_list "${ADMIN_CIDRS}")"
            printf 'log_retention_days = %s\n'   "${LOG_RETENTION_DAYS}"
            printf 'alarm_email        = "%s"\n' "${ALARM_EMAIL}"
            printf 'cluster_name       = "%s"\n' "${CLUSTER_NAME}"
            printf 'k8s_version        = "%s"\n' "${K8S_VERSION}"
            printf 'node_type          = "%s"\n' "${NODE_TYPE}"
            printf 'node_disk_gb       = %s\n'   "${NODE_DISK_GB}"
            printf 'node_min           = %s\n'   "${NODE_MIN}"
            printf 'node_desired       = %s\n'   "${NODE_DESIRED}"
            printf 'node_max           = %s\n'   "${NODE_MAX}"
            printf 'node_max_pods      = %s\n'   "${NODE_MAX_PODS}"
            printf 'db_engine_version  = "%s"\n' "${DB_ENGINE_VERSION}"
            printf 'db_instance_class  = "%s"\n' "${DB_INSTANCE_CLASS}"
            printf 'db_disk_gb         = %s\n'   "${DB_DISK_GB}"
            printf 'db_max_disk_gb     = %s\n'   "${DB_MAX_DISK_GB}"
            printf 'db_name            = "%s"\n' "${DB_NAME}"
            printf 'db_user            = "%s"\n' "${DB_USER}"
            printf 'db_backup_days     = %s\n'   "${DB_BACKUP_DAYS}"
            printf 'db_multi_az        = %s\n'   "${DB_MULTI_AZ}"
            printf 'db_replicas        = %s\n'   "${DB_REPLICAS}"
            printf 'db_apply_now       = %s\n'   "${DB_APPLY_NOW}"
            printf 'k8s_namespace      = "%s"\n' "${K8S_NAMESPACE}"
            printf 'service_name       = "%s"\n' "${SERVICE_NAME}"
            printf 'db_alarm_cpu       = %s\n'   "${DB_ALARM_CPU}"
            printf 'db_alarm_free_gb   = %s\n'   "${DB_ALARM_FREE_GB}"

        fi

}
aws_registry_user () {

    printf 'AWS'

}
aws_registry_token () {

    ensure aws

    aws ecr get-login-password --region "${AWS_REGION}"

}
aws_edge_annotations () {

    [[ -n "${EDGE_TYPE}" ]] || { printf '{}'; return 0; }

    printf '{"service.beta.kubernetes.io/aws-load-balancer-type":"%s","service.beta.kubernetes.io/aws-load-balancer-scheme":"internet-facing","service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled":"true"%s}' \
        "${EDGE_TYPE}" \
        "${EDGE_EIPS:+,\"service.beta.kubernetes.io/aws-load-balancer-eip-allocations\":\"${EDGE_EIPS}\"}"

}

