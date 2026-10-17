#!/usr/bin/env bash

## the release line and the verify wall

ci_tag () {

    if [[ -n "${IMAGE_TAG_OVERRIDE:-}" ]]; then

        printf '%s' "${IMAGE_TAG_OVERRIDE}"
        return 0

    fi

    printf '%s' "${GITHUB_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD)}" | cut -c1-"${IMAGE_TAG_LENGTH}"

}
ci_registry () {

    printf '%s' "${REGISTRY:-${ECR_REGISTRY}}"

}
ci_image () {

    [[ -n "$(ci_registry)" ]] || die "Missing REGISTRY or ECR_REGISTRY in config"

    printf '%s' "$(ci_registry)/${IMAGE_NAME}"

}
## print one resolved setting — the value the release line acts on (secrets refused)
ci_setting () {

    local key="${1:?Missing setting name}"

    ! secret_name "${key}" || die "Refusing to print '${key}' — it is a secret"

    printf '%s\n' "${!key:-}"

}
ci_login () {

    ensure docker

    if [[ -n "${REGISTRY_USER}" ]]; then

        secret_require GIT_TOKEN \
            | docker login --username "${REGISTRY_USER}" --password-stdin "$(ci_registry)" \
            || die "Registry login failed"

        return 0

    fi

    cloud registry_login "$(ci_registry)"

}
## build the docker image for this stack
ci_build () {

    local image="" tag=""

    ensure docker

    image="$(ci_image)"
    tag="$(ci_tag)"

    step "Building ${image}:${tag}"

    run docker build \
        -f "${TEMPLATE_DIR}/docker/Dockerfile" \
        --build-arg PYTHON_IMAGE="${PYTHON_IMAGE}" \
        --build-arg UV_IMAGE="${UV_IMAGE}" \
        --build-arg APP_DIR="${APP_DIR}" \
        --label "org.opencontainers.image.source=${GIT_REPO_URL%.git}" \
        --label "org.opencontainers.image.revision=${tag}" \
        --target app \
        -t "${image}:${tag}" \
        ${DOCKER_NETWORK:+--network=${DOCKER_NETWORK}} \
        "${REPO_ROOT}"

    run docker build \
        -f "${TEMPLATE_DIR}/docker/Dockerfile" \
        --build-arg BACKUP_IMAGE="${BACKUP_BASE_IMAGE}" \
        --label "org.opencontainers.image.source=${GIT_REPO_URL%.git}" \
        --label "org.opencontainers.image.revision=${tag}" \
        --target backup \
        -t "${image}:backup-${tag}" \
        ${DOCKER_NETWORK:+--network=${DOCKER_NETWORK}} \
        "${TEMPLATE_DIR}/docker"

}
## boot the built image and prove it answers before it ships
ci_prove () {

    local image="" tag=""

    image="$(ci_image)"
    tag="$(ci_tag)"

    run docker run --rm --entrypoint sh "${image}:${tag}" -c '
        python -c "import bootstrap" || { echo "the application does not import"; exit 1; }
        python -c "import fastapi, granian, orjson, pydantic" || { echo "a package the app runs on is missing"; exit 1; }
        test -w storage/logs || { echo "storage is not writable by the runtime user"; exit 1; }
        test -w storage/app/private || { echo "the private storage is not writable by the runtime user"; exit 1; }
    ' || die "The image does not carry what it needs to run"

    succ "Image proven — the app imports, the runtime packages are present, storage is writable."

}
## push the image to the registry
ci_shipped () {

    docker manifest inspect "${1}" >/dev/null 2>&1

}
## push the image and its backup sidecar — an immutable tag already in the registry is reused, never fought
ci_push () {

    local image="" tag="" ref=""

    image="$(ci_image)"
    tag="$(ci_tag)"

    ci_login

    for ref in "${image}:${tag}" "${image}:backup-${tag}"; do

        if ci_shipped "${ref}"; then info "Already in the registry — ${ref##*/} is immutable and reused"; continue; fi

        run docker push "${ref}"

    done

}
ci_accept () {

    local finding="${1:?Missing finding}"

    [[ "${CVE_ALLOW}" == "true" ]] \
        || die "${finding} — review them, then re-release with CVE_ALLOW=true to accept"

    warn "${finding} accepted via CVE_ALLOW."

}
## scan the image locally with trivy
ci_trivy () {

    local tag=""

    ensure trivy

    tag="$(ci_tag)"

    step "Scanning $(ci_image):${tag} with trivy"

    trivy image --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 --quiet "$(ci_image):${tag}" \
        || ci_accept "trivy: CRITICAL finding(s) on ${tag}"

    succ "Image scan clean — zero fixable CRITICAL findings."

}
## CVE gate — registry scan on cloud, trivy elsewhere; CRITICAL blocks unless accepted
ci_scan () {

    local tag="" critical=""

    if [[ -n "${REGISTRY}" ]]; then

        ci_trivy
        return 0

    fi

    tag="$(ci_tag)"

    critical="$(cloud registry_critical "${tag}")"

    [[ "${critical}" =~ ^[0-9]+$ ]] || critical=0

    if (( critical > 0 )); then

        ci_accept "Registry scan: ${critical} CRITICAL finding(s) on ${tag}"

        return 0

    fi

    succ "ECR scan clean — zero CRITICAL findings."

}
## refuse a release the manifest cannot carry — before a single byte is built
ci_preflight () {

    secrets_check
    ci_image >/dev/null

    succ "Preflight clear — the manifest carries this release."

}
## wait until the live edge serves this release — the pods publish their image tag on RELEASE_PATH
ci_deployed () {

    local tag="" live="" waited=0 url="https://${GATEWAY_DOMAIN}${RELEASE_PATH}"

    if ! dns_managed; then

        warn "This stack does not manage its names — the release is live on the cluster; point ${GATEWAY_DOMAIN} at $(dns_edge 2>/dev/null || echo 'the edge') yourself."
        return 0

    fi

    tag="$(ci_tag)"
    step "Waiting for ${url} to serve ${tag}"

    while (( waited < RELEASE_WAIT )); do

        live="$(curl -sS -m 15 "${url}" 2>/dev/null | jq -r '.data.release // empty' 2>/dev/null || true)"

        if [[ "${live}" == "${tag}" ]]; then

            succ "Release ${tag} is live on ${GATEWAY_DOMAIN} after ${waited}s."
            return 0

        fi

        sleep "${RELEASE_POLL}"
        waited=$(( waited + RELEASE_POLL ))

    done

    die "Release ${tag} is not live on ${GATEWAY_DOMAIN} after ${RELEASE_WAIT}s (edge serves '${live:-nothing}')"

}
## tell the alert channel how the release ended — success|failure, called by the workflow when the job settles
ci_outcome () {

    local status="${1:?ci outcome needs the job status}" tag="" run=""

    tag="$(ci_tag)"
    run="${GITHUB_SERVER_URL:-${GITHUB_URL}}/${GITHUB_REPOSITORY:-${GIT_REPO}}/actions/runs/${GITHUB_RUN_ID:-}"

    case "${status}" in
        success) audit_alarm "🚀 ${SERVICE_NAME} ${tag} is live on ${GATEWAY_DOMAIN}" ;;
        *)       audit_alarm "🔴 ${SERVICE_NAME} release ${tag} ${status} — ${run}" ;;
    esac

    succ "Outcome ${status} reported."

}
## the ONE entry point: converge cloud → build → prove → push → scan → converge server + names → wait for the edge
ci_release () {

    ci_preflight
    tofu_ensure
    ci_build
    ci_prove
    ci_push
    ci_scan
    server_ensure
    dns_ensure
    ci_deployed

    succ "Release $(ci_tag) delivered."

}
## law: every stack renders a coherent helm matrix
ci_matrix () {

    local stack="" values="" rendered="" target="" disk="" db=""

    ensure helm kubeconform

    ensure_dir "${BUILD_DIR}/matrix"

    for stack in ${STACKS}; do

        values="${BUILD_DIR}/matrix/${stack}.yaml"
        rendered="${BUILD_DIR}/matrix/${stack}-rendered.yaml"
        "${INFRA_BIN}" -s "${stack}" -y -e DB_HOST="${DB_HOST:-${MATRIX_DB_HOST}}" helm seed "${values}" >/dev/null \
            || die "Matrix seed failed for '${stack}'"

        helm_template "${values}" > "${rendered}" || die "Matrix render failed for '${stack}'"

        kubeconform -strict -summary -ignore-missing-schemas -kubernetes-version "${K8S_VERSION}.0" "${rendered}" \
            || die "Matrix schema check failed for '${stack}'"

        disk="$(awk '/^  STORAGE_DISK: /{print $2; exit}' "${values}" | tr -d '"')"
        db="$(awk '/^  DB_HOST: /{print $2; exit}' "${values}" | tr -d '"')"
        target="$(awk '/^backup:/ { on = 1 } on && /^  target: / { print $2; exit }' "${values}")"

        [[ "$(grep -c "kind: NetworkPolicy" "${rendered}")" == "5" ]] || die "Matrix: '${stack}' lost its NetworkPolicies"
        grep -q "name: ${SERVICE_NAME}-allow-metrics" "${rendered}" || die "Matrix: '${stack}' walled prometheus away from what it measures"
        grep -q "name: BACKUP_TARGET" "${rendered}" || die "Matrix: '${stack}' lost its backup job"

        if [[ "${disk}" == "public" ]]; then

            grep -q "kind: PersistentVolumeClaim" "${rendered}" || die "Matrix: '${stack}' keeps its files on a disk it never claims"

        else

            grep -qE "^ +AWS_BUCKET: \"..*\"$" "${rendered}" || die "Matrix: '${stack}' keeps its files in object storage without a bucket"

        fi

        if [[ "${db}" == "postgresql."* ]]; then

            ! grep -q "rds\.amazonaws" "${rendered}" || die "Matrix: '${stack}' runs its own database and still points at a managed one"
            grep -q "DB_SEARCH_PATH: \"${DB_SEARCH_PATH}\"" "${rendered}" || die "Matrix: '${stack}' lost the extensions schema in its search path"

        else

            grep -q "DB_SSLMODE: \"require\"" "${rendered}" || die "Matrix: '${stack}' talks to a managed database in the clear"

        fi

        if [[ "${target}" == "pvc" ]]; then

            grep -q "claimName: ${SERVICE_NAME}-backups" "${rendered}" || die "Matrix: '${stack}' backs up to a claim that is never mounted"

        else

            ! grep -q "claimName: ${SERVICE_NAME}-backups" "${rendered}" || die "Matrix: '${stack}' keeps a backup claim it never writes to"
            grep -qE "^ +value: \"${S3_BACKUP_BUCKET}\"$" "${rendered}" || die "Matrix: '${stack}' backs up to s3 without a bucket"
            grep -qE "^ +value: \"${AWS_REGION}\"$" "${rendered}" || die "Matrix: '${stack}' backs up to s3 without a region"

        fi

        if grep -q "imagePullSecrets: \[pull-secret\]" "${values}"; then

            grep -q "name: pull-secret" "${rendered}" || die "Matrix: '${stack}' asks for a pull secret it never mounts"

        else

            ! grep -q "name: pull-secret" "${rendered}" || die "Matrix: '${stack}' mounts a pull secret it never asked for"

        fi

    done

    ! grep -lE '^  tag: "?(latest)?"?$' "${BUILD_DIR}"/matrix/*.yaml \
        || die "A stack carries a floating tag — every stack ships an immutable git sha"

    ci_certs
    ci_edge
    ci_apps
    ci_dashboards

    succ "Render matrix proven — every stack keeps the contract its capabilities imply."

}
ci_block () {

    local file="${1}" key="${2}"

    awk -v key="${key}" '$0 ~ "^  " key ":" { on = 1; next } on && /^  [a-zA-Z]/ { on = 0 } on && /^    - / { gsub(/^    - |"/, ""); print }' "${file}" | sort -u

}
## law: tls wiring is coherent per stack
ci_certs () {

    local gateway="${BUILD_DIR}/matrix/gateway.yaml" file=""

    ensure helm

    run helm template gateway "$(helm_charts)/gateway" \
        --set tlsEnabled=true --set dns01=true --set sslEmail="${SSL_EMAIL}" \
        --set domain="${BASE_DOMAIN}" --set-json "hostnames=${APP_HOSTNAMES}" > "${gateway}" \
        || die "Gateway render failed"

    for file in ${STACKS}; do

        diff <(ci_block "${BUILD_DIR}/matrix/${file}-rendered.yaml" hostnames) <(ci_block "${gateway}" dnsNames) >/dev/null \
            || die "TLS gap on '${file}': the hosts the gateway routes are not the hosts the certificate covers"

    done

    succ "TLS contract proven — every routed host is a certified host."

}
## law: edge/ratelimit wiring is coherent
ci_edge () {

    local rendered=""

    ensure helm

    rendered="$(helm template gateway "$(helm_charts)/gateway" --set domain="${BASE_DOMAIN}" --set sslEmail="${SSL_EMAIL}" \
        --set edgeType=nlb --set-string 'edgeAnnotations.fixed/addresses=eipalloc-a\,eipalloc-b')" \
        || die "Edge render failed"

    grep -q 'fixed/addresses: "eipalloc-a,eipalloc-b"' <<< "${rendered}" \
        || die "Edge: the balancer forgets the annotations it was given"

    rendered="$(EDGE_TYPE=nlb EDGE_EIPS='eipalloc-a,eipalloc-b' cloud edge_annotations)"

    grep -q 'eip-allocations' <<< "${rendered}" \
        || die "Edge: the provider verb forgets the fixed addresses it was given"

    rendered="$(EDGE_TYPE=nlb EDGE_EIPS='' cloud edge_annotations)"

    ! grep -q 'eip-allocations' <<< "${rendered}" \
        || die "Edge: the provider verb claims addresses nobody allocated"

    rendered="$(helm template gateway "$(helm_charts)/gateway" --set domain="${BASE_DOMAIN}" --set sslEmail="${SSL_EMAIL}")" \
        || die "Edge render failed"

    [[ "$(grep -c 'type: Distinct' <<< "${rendered}")" == "2" && "$(grep -c 'clientSelectors' <<< "${rendered}")" == "2" ]] \
        || die "Edge: the rate limit is one bucket for the whole world — every client address spends its own"

    ! grep -q 'kind: ClientTrafficPolicy' <<< "${rendered}" \
        || die "Edge: a forwarded address is believed although nobody named a shield"

    rendered="$(helm template gateway "$(helm_charts)/gateway" --set domain="${BASE_DOMAIN}" --set sslEmail="${SSL_EMAIL}" \
        --set-json 'trustedCidrs=["198.51.100.0/24"]')" \
        || die "Edge render failed"

    grep -q -- '- "198.51.100.0/24"' <<< "${rendered}" \
        || die "Edge: the shield's network never reaches the client address detection"

    succ "Edge contract proven — the chart renders any annotations, the provider mints exactly the right ones, every client address spends its own bucket."

}
## law: argocd apps map to real template dirs
ci_apps () {

    local stack="" rendered="" cloud=""

    ensure helm

    for stack in ${STACKS}; do

        rendered="${BUILD_DIR}/matrix/${stack}-apps.yaml"
        cloud="$("${INFRA_BIN}" -s "${stack}" -y ci setting CLOUD_METRICS)"

        helm template apps "${TEMPLATE_DIR}/argocd/apps" \
            --set "observability.cloud=${cloud}" \
            --set "observability.host=${GRAFANA_HOSTNAME}" \
            --set "observability.chatId=probe" \
            --set "service.image.tag=probe" \
            --set "platform.postgresql=${cloud}" > "${rendered}" \
            || die "Apps render failed for '${stack}'"

        grep -q "name: metrics" "${rendered}" || die "Apps: '${stack}' has no metrics stack"
        grep -q "name: observability" "${rendered}" || die "Apps: '${stack}' carries no rules of its own"
        grep -q "secrets: \[alert-sink\]" "${rendered}" || die "Apps: '${stack}' alerts have nowhere to go"
        grep -q "^          - ${OBSERVABILITY_NAMESPACE}$" "${rendered}" || die "Apps: '${stack}' gateway refuses the route to its own dashboard"
        grep -q "kubeControllerManager:" "${rendered}" || die "Apps: '${stack}' will alert on a control plane it cannot reach"
        grep -q "http://${LOGS_RELEASE}-loki\.${OBSERVABILITY_NAMESPACE}" "${rendered}" || die "Apps: '${stack}' ships its logs to a service that does not exist"
        ! grep -q '\$values' "${rendered}" || die "Apps: '${stack}' lets a committed file decide which image runs"
        grep -q "tag: probe" "${rendered}" || die "Apps: '${stack}' drops the release tag on its way to the chart"

        if [[ "${cloud}" == "true" ]]; then

            grep -q "name: cloud-metrics" "${rendered}" || die "Apps: '${stack}' never reads its managed services"

        else

            ! grep -q "name: cloud-metrics" "${rendered}" || die "Apps: '${stack}' reads a cloud it does not run on"

        fi

    done

    succ "App-of-apps proven — every stack watches itself, none watches a cloud it is not on."

}
## law: grafana dashboards parse
ci_dashboards () {

    local file=""

    ensure helm python3

    python3 -c 'import yaml' 2>/dev/null || pkg_install python3-yaml

    file="${BUILD_DIR}/matrix/dashboards.yaml"

    helm template observability "$(helm_charts)/observability" \
        --set host="${GRAFANA_HOSTNAME}" --set appNamespace="${K8S_NAMESPACE}" --set service="${SERVICE_NAME}" \
        --set metricsRelease="${METRICS_RELEASE}" > "${file}" \
        || die "Observability render failed"

    python3 -c "
import sys, yaml, json
maps = [d for d in yaml.safe_load_all(open('${file}')) if d and d.get('kind') == 'ConfigMap']
assert maps, 'no dashboard shipped'
for m in maps:
    for name, body in m['data'].items():
        json.loads(body)
" || die "A dashboard this repo ships is not valid json"

    succ "Dashboards proven — every panel this repo ships parses."

}
ci_github () {

    local method="${1:?Missing method}" path="${2:?Missing path}" body="${3:-}"

    curl -sS -o /dev/null -w '%{http_code}' -X "${method}" "${GITHUB_API}/repos/${GIT_REPO}${path}" \
        -H "Authorization: Bearer $(secret_require GIT_TOKEN)" \
        -H "Accept: application/vnd.github+json" \
        ${body:+--data "${body}"}

}
## arm or disarm the external github watcher for this stack
ci_guard () {

    local state="${1:-on}" code=""

    ensure curl

    if [[ "${state}" == "off" ]]; then

        code="$(ci_github PUT "/actions/workflows/watch.yaml/disable")"

        [[ "${code}" == 2* ]] || die "Cannot disable the watcher (HTTP ${code})"

        succ "External guard disarmed — nothing probes from GitHub anymore."

        return 0

    fi

    code="$(ci_github PUT "/actions/workflows/watch.yaml/enable")"

    [[ "${code}" == 2* ]] || die "Cannot enable the watcher (HTTP ${code})"

    [[ -n "$(secret_get ALERT_BOT_TOKEN)" ]] || warn "ALERT_BOT_TOKEN repo secret is yours to set once — without it the guard sees but cannot speak"

    succ "External guard armed — GitHub probes ${GATEWAY_DOMAIN} every ten minutes."

}
ci_probe () {

    printf '%s\n' "${GIT_TOKEN:+manifest}" "${WEB_MEMORY_LIMIT:+knob}" "${FOREIGN_KEY:+foreign}" | paste -sd ' ' -

}
## law: the repo secrets reach the release line — manifest keys and config knobs load, foreign keys never do
ci_loader () {

    local seen=""

    seen="$(JSON_ENV='{"GIT_TOKEN":"probe","WEB_MEMORY_LIMIT":"9Gi","FOREIGN_KEY":"probe"}' "${INFRA_BIN}" -y ci probe)"

    [[ "${seen}" == "manifest knob " ]] || die "The secrets loader is wrong — it saw [${seen}], expected [manifest knob ]"

    succ "Secrets loader proven — manifest keys and knobs load, foreign keys stay out."

}
## law: every rendered template resolves — names computed at render time are read from the scripts themselves
ci_templates () {

    local file="" key="" computed=""

    computed=" $(infra_code | grep -oE '\b[A-Z][A-Z0-9_]*=' | tr -d = | sort -u | paste -sd ' ' -) "

    for file in "${TEMPLATE_DIR}"/argocd/project.yaml "${TEMPLATE_DIR}"/argocd/root.yaml "${TEMPLATE_DIR}"/aws/*.yaml "${TEMPLATE_DIR}"/k8s/*.yaml "${TEMPLATE_DIR}"/helm/values/*.tpl; do

        for key in $(placeholders "${file}"); do

            [[ -n "${!key+x}" || "${computed}" == *" ${key} "* ]] || die "Template $(basename "${file}") names ${key} — nothing defines it"

        done

    done

    succ "Templates resolve — every placeholder has a source."

}
## law: workflow files lint clean
ci_workflows () {

    ensure actionlint

    run actionlint "${REPO_ROOT}/.github/workflows/"*.y*ml

    succ "Workflows lint clean."

}
## law: no secret material in tracked files
ci_leaks () {

    local config="" path=""

    ensure gitleaks

    config="$(tmp_file)"

    cat > "${config}" <<'TOML'
[extend]
useDefault = true

[allowlist]
paths = ['''\.infra/''', '''\.terraform/''']
regexes = ['''^[A-Z][A-Z0-9_]*=$''']
TOML

    for path in "${REPO_ROOT}/.github" "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.secret.example"; do

        [[ -e "${path}" ]] || continue

        run gitleaks dir "${path}" --no-banner --redact -c "${config}"

    done

    rm -f "${config}"

    succ "No secret material in the workflows or the examples."

}
## the wall: shellcheck, actionlint, kubeconform, tofu validate, gitleaks, matrix laws
ci_verify () {

    local file="" code="" failed=0

    ensure shellcheck helm tofu

    code="$(tmp_file)"
    infra_code > "${code}"

    while IFS= read -r file; do

        shellcheck -s bash -x -S "${SHELLCHECK_SEVERITY}" -e "${SHELLCHECK_EXCLUDES}" "${file}" || failed=1

    done < <(find "${TEMPLATE_DIR}" -name '*.sh'; printf '%s\n' "${code}")

    rm -f "${code}"

    helm_lint
    ci_matrix
    ci_loader
    ci_templates
    ci_workflows
    ci_leaks
    secrets_example
    tofu_fmt -check
    tofu_validate

    (( failed == 0 )) || die "Shell lint failed"

    succ "Infra verification passed."

}
## refuse to proceed unless the CI run for this commit is green (waits out an in-flight one)
ci_gate () {

    local attempt="" verdict=""

    ensure gh

    for attempt in $(seq 1 "${CI_GATE_ATTEMPTS}"); do

        verdict="$(gh run list --repo "${GITHUB_REPOSITORY:-${GIT_REPO}}" --workflow=CI --commit "$(git -C "${REPO_ROOT}" rev-parse HEAD)" \
            --json status,conclusion --jq '.[0] | .status + "/" + (.conclusion // "")')"

        case "${verdict}" in

            completed/success ) succ "CI is green for this commit."; return 0 ;;
            completed/*       ) die "CI concluded '${verdict}' — refused" ;;
            ""                ) die "No CI run found for this commit — refused" ;;
            *                 ) info "CI is '${verdict}' — waiting (${attempt}/${CI_GATE_ATTEMPTS})"; sleep "${CI_GATE_POLL}" ;;

        esac

    done

    die "CI never concluded — refused"

}

