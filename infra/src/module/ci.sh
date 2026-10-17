#!/usr/bin/env bash

## the release line and the verify wall

ci_tag () {

    if [[ -n "${IMAGE_TAG_OVERRIDE:-}" ]]; then

        printf '%s' "${IMAGE_TAG_OVERRIDE}"
        return 0

    fi

    printf '%s' "${GITHUB_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD)}" | cut -c1-"${IMAGE_TAG_LENGTH}"

}
## print one resolved setting — the value the release line acts on (secrets refused)
ci_setting () {

    local key="${1:?Missing setting name}"

    ! secret_name "${key}" || die "Refusing to print '${key}' — it is a secret"

    printf '%s\n' "${!key:-}"

}
## every image this release ships — the api, its backup sidecar, one web image per spec
ci_images () {

    local tag="" spec=""

    tag="$(ci_tag)"

    printf '%s\n' "${IMAGE_API}:${tag}" "${IMAGE_API}:backup-${tag}"

    [[ "${WEB_ENABLED}" != "true" ]] || for spec in ${WEB_SPECS}; do printf '%s\n' "${IMAGE_WEB}:${spec}-${tag}"; done

}
## log into the registry — a registry password when the manifest carries one, the git token otherwise
ci_login () {

    local password=""

    ensure docker

    password="$(secret_get REGISTRY_PASSWORD)"
    [[ -n "${password}" ]] || password="$(secret_require GIT_TOKEN)"

    printf '%s' "${password}" | compose_docker login --username "${REGISTRY_USER}" --password-stdin "${REGISTRY}" >/dev/null \
        || die "Registry login failed for ${REGISTRY_USER}@${REGISTRY}"

}
ci_docker_build () {

    run docker build \
        --label "org.opencontainers.image.source=${GIT_REPO_URL%.git}" \
        --label "org.opencontainers.image.revision=$(ci_tag)" \
        ${DOCKER_NETWORK:+--network=${DOCKER_NETWORK}} \
        "$@"

}
## build the api image, its backup sidecar and one web image per spec
ci_build () {

    local tag="" spec=""

    ensure docker

    tag="$(ci_tag)"

    step "Building ${IMAGE_API}:${tag}"

    ci_docker_build -f "${TEMPLATE_DIR}/docker/Dockerfile" --target app \
        --build-arg PYTHON_IMAGE="${PYTHON_IMAGE}" --build-arg UV_IMAGE="${UV_IMAGE}" --build-arg APP_DIR="${APP_DIR}" \
        -t "${IMAGE_API}:${tag}" "${REPO_ROOT}"

    ci_docker_build -f "${TEMPLATE_DIR}/docker/Dockerfile" --target backup \
        --build-arg BACKUP_IMAGE="${BACKUP_BASE_IMAGE}" \
        -t "${IMAGE_API}:backup-${tag}" "${TEMPLATE_DIR}/docker"

    [[ "${WEB_ENABLED}" == "true" ]] || return 0

    for spec in ${WEB_SPECS}; do

        step "Building ${IMAGE_WEB}:${spec}-${tag} against ${WEB_API_URL:-${API_URL}}"

        ci_docker_build -f "${TEMPLATE_DIR}/docker/Dockerfile.web" --target runtime \
            --build-arg NODE_IMAGE="${NODE_IMAGE}" --build-arg BUN_IMAGE="${BUN_IMAGE}" --build-arg WEB_DIR="${WEB_DIR}" \
            --build-arg SPEC="${spec}" --build-arg SPEC_API_URL="${WEB_API_URL:-${API_URL}}" \
            -t "${IMAGE_WEB}:${spec}-${tag}" "${REPO_ROOT}"

    done

}
## boot the built images and prove they carry what they need before they ship
ci_prove () {

    local tag="" spec=""

    tag="$(ci_tag)"

    run docker run --rm --entrypoint sh "${IMAGE_API}:${tag}" -c '
        python -c "import bootstrap" || { echo "the application does not import"; exit 1; }
        python -c "import fastapi, granian, orjson, pydantic, aio_pika, redis, sqlalchemy" || { echo "a package the app runs on is missing"; exit 1; }
        test -w src/storage/logs || { echo "the logs folder is not writable by the runtime user"; exit 1; }
        test -w src/storage/app/private || { echo "the private storage is not writable by the runtime user"; exit 1; }
        test -f src/public/robots.txt || { echo "the public assets are missing"; exit 1; }
    ' || die "The api image does not carry what it needs to run"

    run docker run --rm --entrypoint sh "${IMAGE_API}:backup-${tag}" -c 'command -v pg_dump >/dev/null && command -v aws >/dev/null && command -v backup >/dev/null' \
        || die "The backup image lacks pg_dump, aws or the backup script"

    if [[ "${WEB_ENABLED}" == "true" ]]; then

        for spec in ${WEB_SPECS}; do

            run docker run --rm --entrypoint sh "${IMAGE_WEB}:${spec}-${tag}" -c '
                test -f node_modules/.cache/spec/production/meta.json || { echo "the spec was not compiled"; exit 1; }
                test -d .next/out || { echo "the build output is missing"; exit 1; }
                bun --version >/dev/null && node --version >/dev/null || { echo "the runtimes are missing"; exit 1; }
            ' || die "The web image for ${spec} does not carry what it needs to run"

        done

    fi

    succ "Images proven — the api imports with every runtime package, storage and assets in place; the web images carry their builds."

}
ci_shipped () {

    docker manifest inspect "${1}" >/dev/null 2>&1

}
## push every image — an immutable tag already in the registry is reused, never fought
ci_push () {

    local ref=""

    ci_login

    while IFS= read -r ref; do

        if ci_shipped "${ref}"; then info "Already in the registry — ${ref##*/} is immutable and reused"; continue; fi

        run docker push "${ref}"

    done < <(ci_images)

}
ci_accept () {

    local finding="${1:?Missing finding}"

    [[ "${CVE_ALLOW}" == "true" ]] \
        || die "${finding} — review them, then re-release with CVE_ALLOW=true to accept"

    warn "${finding} accepted via CVE_ALLOW."

}
## CVE gate — trivy on every image; a fixable CRITICAL blocks unless accepted
ci_scan () {

    local ref=""

    ensure trivy

    while IFS= read -r ref; do

        step "Scanning ${ref##*/} with trivy"

        trivy image --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 --quiet "${ref}" \
            || ci_accept "trivy: CRITICAL finding(s) on ${ref##*/}"

    done < <(ci_images)

    succ "Image scan clean — zero fixable CRITICAL findings."

}
## refuse a release the manifest cannot carry — before a single byte is built
ci_preflight () {

    secrets_check

    succ "Preflight clear — the manifest carries this release: $(ci_images | paste -sd ' ' -)"

}
## wait until the edge on the box serves this release — the api publishes its release tag on RELEASE_PATH
ci_deployed () {

    local tag="" live="" waited=0 url="" host=""

    ensure curl jq

    tag="$(ci_tag)"
    host="$(server_host)"
    url="$(config_origin "${API_HOST}")${RELEASE_PATH}"

    step "Waiting for ${url} on ${host} to serve ${tag}"

    while (( waited < RELEASE_WAIT )); do

        live="$(curl -sk -m 15 --resolve "${API_HOST}:${PUBLIC_PORT}:${host}" "${url}" 2>/dev/null | jq -r '.data.release // empty' 2>/dev/null || true)"

        if [[ "${live}" == "${tag}" ]]; then

            succ "Release ${tag} is live on ${API_HOST} after ${waited}s."

            dns_managed || warn "This stack does not manage its names — point ${TLS_NAMES} at ${host} yourself."

            return 0

        fi

        sleep "${RELEASE_POLL}"
        waited=$(( waited + RELEASE_POLL ))

    done

    die "Release ${tag} is not live on ${API_HOST} after ${RELEASE_WAIT}s (the edge serves '${live:-nothing}')"

}
## tell the alert channel how the release ended — success|failure, called by the workflow when the job settles
ci_outcome () {

    local status="${1:?ci outcome needs the job status}" tag="" run=""

    tag="$(ci_tag)"
    run="${GITHUB_SERVER_URL:-${GITHUB_URL}}/${GITHUB_REPOSITORY:-${GIT_REPO}}/actions/runs/${GITHUB_RUN_ID:-}"

    case "${status}" in
        success) audit_alarm "🚀 ${PROJECT} ${tag} is live on ${API_HOST}" ;;
        *)       audit_alarm "🔴 ${PROJECT} release ${tag} ${status} — ${run}" ;;
    esac

    succ "Outcome ${status} reported."

}
## the ONE entry point: preflight → build → prove → push → scan → converge the server → wait for the edge
ci_release () {

    ci_preflight
    ci_build
    ci_prove
    ci_push
    ci_scan
    server_ensure
    ci_deployed

    succ "Release $(ci_tag) delivered."

}
ci_probe () {

    printf '%s\n' "${GIT_TOKEN:+manifest}" "${API_MEMORY:+knob}" "${FOREIGN_KEY:+foreign}" | paste -sd ' ' -

}
## law: the repo secrets reach the release line — manifest keys and config knobs load, foreign keys never do
ci_loader () {

    local seen=""

    seen="$(JSON_ENV='{"GIT_TOKEN":"probe","API_MEMORY":"9g","FOREIGN_KEY":"probe"}' "${INFRA_BIN}" -y ci probe)"

    [[ "${seen}" == "manifest knob " ]] || die "The secrets loader is wrong — it saw [${seen}], expected [manifest knob ]"

    succ "Secrets loader proven — manifest keys and knobs load, foreign keys stay out."

}
## law: every rendered template resolves — names computed at render time are read from the scripts themselves
ci_templates () {

    local file="" key="" computed=""

    computed=" $(infra_code | grep -oE '\b[A-Z][A-Z0-9_]*=' | tr -d = | sort -u | paste -sd ' ' -) "

    compose_mode

    while IFS= read -r file; do

        for key in $(placeholders "${TEMPLATE_DIR}/${file}"); do

            [[ -n "${!key+x}" || "${computed}" == *" ${key} "* ]] || die "Template ${file} names ${key} — nothing defines it"

        done

    done < <(compose_templates)

    succ "Templates resolve — every placeholder has a source."

}
## law: every stack renders, and docker compose accepts what it renders
ci_compose () {

    local stack="" dir=""

    ensure docker

    for stack in ${STACKS}; do

        dir="${BUILD_DIR}/matrix/${stack}"

        "${INFRA_BIN}" -s "${stack}" -y -e COMPOSE_DIR="${dir}" -e IMAGE_TAG_OVERRIDE=probe -e PROJECT="${PROJECT:-probe}" -e BASE_DOMAIN="${BASE_DOMAIN:-probe.test}" compose render >/dev/null \
            || die "Matrix render failed for '${stack}'"

        COMPOSE_DIR="${dir}" compose_cmd config -q || die "docker compose refuses the '${stack}' stack"

        grep -q 'internal: true' "${dir}/compose.yaml" || die "Matrix: '${stack}' exposes its data network"
        ! grep -qE '^\s+- "[0-9.]+:(5432|5672|6379):' "${dir}/compose.yaml" || die "Matrix: '${stack}' publishes a data service port"

    done

    succ "Render matrix proven — every stack renders and docker compose accepts it."

}
## law: the rendered edge passes nginx's own test, with a throwaway certificate standing in for the real one
ci_nginx () {

    local dir="" live=""

    ensure docker openssl

    dir="${BUILD_DIR}/matrix/edge"
    live="${dir}/live/${BASE_DOMAIN:-probe.test}"

    "${INFRA_BIN}" -s "${STACK}" -y -e COMPOSE_DIR="${dir}" -e IMAGE_TAG_OVERRIDE=probe -e TLS_ENABLED=true -e WEB_ENABLED=true \
        -e PROJECT="${PROJECT:-probe}" -e BASE_DOMAIN="${BASE_DOMAIN:-probe.test}" compose render >/dev/null || die "Edge render failed"

    ensure_dir "${live}"

    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1 -subj "/CN=${BASE_DOMAIN:-probe.test}" \
        -keyout "${live}/privkey.pem" -out "${live}/fullchain.pem" >/dev/null 2>&1 || die "Cannot mint a throwaway certificate"

    chmod 644 "${live}/privkey.pem" "${live}/fullchain.pem"

    docker run --rm -v "${dir}/nginx:/etc/nginx/platform:ro" -v "${dir}/live:/etc/letsencrypt/live:ro" "${NGINX_IMAGE}" \
        nginx -t -c /etc/nginx/platform/nginx.conf || die "nginx refuses the rendered edge"

    succ "Edge proven — nginx accepts the rendered configuration with tls, http/3 and the rate limits."

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
paths = ['''\.infra/''']
regexes = ['''^[A-Z][A-Z0-9_]*=$''']
TOML

    for path in "${REPO_ROOT}/.github" "${ROOT_DIR:-${REPO_ROOT}/infra}/.env.example" "${ROOT_DIR:-${REPO_ROOT}/infra}/.secret.example"; do

        [[ -e "${path}" ]] || continue

        run gitleaks dir "${path}" --no-banner --redact -c "${config}"

    done

    rm -f "${config}"

    succ "No secret material in the workflows or the examples."

}
## the wall: shellcheck, the render matrix, the edge, the loader, the templates, actionlint, gitleaks, the examples law
ci_verify () {

    local file="" code="" failed=0

    ensure shellcheck

    code="$(tmp_file)"
    infra_code > "${code}"

    while IFS= read -r file; do

        shellcheck -s bash -x -S "${SHELLCHECK_SEVERITY}" -e "${SHELLCHECK_EXCLUDES}" "${file}" || failed=1

    done < <(find "${TEMPLATE_DIR}" -name '*.sh'; printf '%s\n' "${code}")

    rm -f "${code}"

    (( failed == 0 )) || die "Shell lint failed"

    ci_compose
    ci_nginx
    ci_loader
    ci_templates
    ci_workflows
    ci_leaks
    secrets_example

    succ "Infra verification passed."

}
## refuse to proceed unless the CI run for this commit is green (waits out an in-flight one)
ci_gate () {

    local attempt="" verdict=""

    ensure gh

    for attempt in $(seq 1 "${CI_GATE_ATTEMPTS}"); do

        verdict="$(gh run list --repo "${GITHUB_REPOSITORY:-${GIT_REPO}}" --workflow=Infra --commit "$(git -C "${REPO_ROOT}" rev-parse HEAD)" \
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
