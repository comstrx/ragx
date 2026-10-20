gitops-read () {

    local file="${1}" key=""
    local -A desired=()

    parse-pairs desired "${file}" || return

    for key in "${!desired[@]}"; do

        case "${key}" in
            VERSION|RELEASE|API_IMAGE|WEB_IMAGES|MIGRATION_POLICY|COMPOSE_SHA256|RELEASE_REF|API_ENV_SHA256|WEB_ENV_SHA256) ;;
            *) err "Unexpected desired-state key: ${key}"; return ;;
        esac

    done

    parse-identifier "${desired[RELEASE]:-}" || { err "Desired RELEASE must be an identifier"; return; }
    [[ -z "${desired[VERSION]:-}" || "${desired[RELEASE]}" == "${desired[VERSION]}"-* ]] || { err "Desired RELEASE must extend VERSION"; return; }
    parse-pinned "${desired[API_IMAGE]:-}" || { err "Desired API_IMAGE must be pinned by digest"; return; }
    [[ "${desired[COMPOSE_SHA256]:-}" =~ ^[a-f0-9]{64}$ ]] || { err "Desired COMPOSE_SHA256 must be a SHA-256"; return; }
    [[ "${desired[RELEASE_REF]:-}" =~ ^refs/tags/[A-Za-z0-9][A-Za-z0-9._/-]*$ && "${desired[RELEASE_REF]}" != *..* ]] || { err "Desired RELEASE_REF must name a tag"; return; }
    [[ "${desired[MIGRATION_POLICY]:-none}" == none || "${desired[MIGRATION_POLICY]:-none}" == expand ]] || { err "Desired MIGRATION_POLICY must be none or expand"; return; }
    [[ "${desired[API_ENV_SHA256]:-}" =~ ^([a-f0-9]{64})?$ && "${desired[WEB_ENV_SHA256]:-}" =~ ^([a-f0-9]{64})?$ ]] || { err "Desired env digests must be SHA-256"; return; }

    desired[MIGRATION_POLICY]="${desired[MIGRATION_POLICY]:-none}"
    desired[WEB_IMAGES]="${desired[WEB_IMAGES]:-}"
    desired[VERSION]="${desired[VERSION]:-}"
    desired[API_ENV_SHA256]="${desired[API_ENV_SHA256]:-}"
    desired[WEB_ENV_SHA256]="${desired[WEB_ENV_SHA256]:-}"

    for key in "${!desired[@]}"; do
        cfg-set "${key}" "${desired[${key}]}" gitops
    done

}
gitops-fetch () {

    local directory="${1}" commit="" head=""

    cfg-require GITOPS_URL GITOPS_USER GITOPS_TOKEN || return

    git-checkout "${CONFIG[GITOPS_URL]}" "${CONFIG[GITOPS_BRANCH]}" "${directory}/branch" "${CONFIG[GITOPS_USER]}" "${CONFIG[GITOPS_TOKEN]}" || { err "Desired branch checkout failed"; return; }
    commit="$(git -C "${directory}/branch" rev-parse HEAD)" || return
    fs-produce "${directory}/desired.env" 600 git-file "${directory}/branch" "${commit}" "${CONFIG[GITOPS_DESIRED]}" || return
    gitops-read "${directory}/desired.env" || return

    git-checkout "${CONFIG[GITOPS_URL]}" "${CONFIG[RELEASE_REF]#refs/tags/}" "${directory}/release" "${CONFIG[GITOPS_USER]}" "${CONFIG[GITOPS_TOKEN]}" || { err "Release tag checkout failed: ${CONFIG[RELEASE_REF]}"; return; }
    commit="$(git -C "${directory}/release" rev-parse "${CONFIG[RELEASE_REF]}^{commit}")" || { err "Release tag unresolved: ${CONFIG[RELEASE_REF]}"; return; }
    head="$(git -C "${directory}/release" rev-parse HEAD)" || return
    [[ "${commit}" == "${head}" ]] || { err "Release tag does not resolve to the checked out commit"; return; }

    fs-produce "${directory}/tagged.env" 600 git-file "${directory}/release" "${commit}" "${CONFIG[GITOPS_DESIRED]}" || return
    [[ "$(fs-hash "${directory}/desired.env")" == "$(fs-hash "${directory}/tagged.env")" ]] || { err "Tagged desired state differs from the branch"; return; }

    fs-produce "${directory}/application.yaml" 600 git-file "${directory}/release" "${commit}" "${CONFIG[GITOPS_COMPOSE]}" || return
    [[ "$(fs-hash "${directory}/application.yaml")" == "${CONFIG[COMPOSE_SHA256]}" ]] || { err "Desired Compose checksum mismatch"; return; }

    cfg-set GITOPS_COMMIT "${commit}" gitops

}
gitops-relocate () {

    jq --arg root "${1}" 'del(.name) | walk(if type == "string" then split($root + "/${RELEASE_ROOT") | join("${RELEASE_ROOT") | split($root) | join("${RELEASE_ROOT}") else . end)' "${2}"

}
gitops-export () {

    local project="${1}" directory="${2}" destination="${3}" source="" status=0

    shift 3
    need jq || return
    fs-dir "${destination}" || return
    source="$(fs-temp-file)" || return

    docker-compose "${project}" "$@" --profile '*' config --no-interpolate --no-env-resolution --format json > "${source}" || status=$?

    (( status != 0 )) || fs-produce "${destination}/application.yaml" 600 gitops-relocate "${directory}" "${source}" || status=$?

    rm -f -- "${source}"
    (( status == 0 )) || { err "Compose export failed"; return; }

    cfg-set COMPOSE_SHA256 "$(fs-hash "${destination}/application.yaml")"
    cfg-set RELEASE_REF "refs/tags/release-${CONFIG[RELEASE]}"

    template-env "${destination}/desired.env" VERSION RELEASE API_IMAGE WEB_IMAGES MIGRATION_POLICY COMPOSE_SHA256 RELEASE_REF API_ENV_SHA256 WEB_ENV_SHA256

}
gitops-publish () {

    local source="${1}" url="${CONFIG[GITOPS_URL]}" branch="${CONFIG[GITOPS_BRANCH]}" tag="release-${CONFIG[RELEASE]}" work="" tagged=""
    local -a auth=( "${CONFIG[GITOPS_USER]}" "${CONFIG[GITOPS_TOKEN]}" )

    git-url "${url}" || { err "HTTPS repository URL without credentials required"; return; }
    git-ref "${branch}" || { err "Invalid GitOps branch: ${branch}"; return; }
    git-ref "${tag}" || { err "Invalid release tag: ${tag}"; return; }
    work="$(fs-temp)" || return

    git init --quiet "${work}" || return
    git -C "${work}" config user.name infra && git -C "${work}" config user.email infra@localhost.invalid || return

    if git-run "${auth[@]}" -C "${work}" fetch --quiet --depth 1 -- "${url}" "+refs/heads/${branch}:refs/remotes/desired/${branch}" 2>/dev/null; then
        git -C "${work}" checkout --quiet -B "${branch}" "desired/${branch}" || return
    else
        git -C "${work}" checkout --quiet --orphan "${branch}" || return
    fi

    fs-copy "${source}/application.yaml" "${work}/${CONFIG[GITOPS_COMPOSE]}" 644 || return
    fs-copy "${source}/desired.env" "${work}/${CONFIG[GITOPS_DESIRED]}" 644 || return
    git -C "${work}" add -- "${CONFIG[GITOPS_COMPOSE]}" "${CONFIG[GITOPS_DESIRED]}" || return
    git -C "${work}" diff --cached --quiet || git -C "${work}" commit --quiet -m "deploy ${CONFIG[RELEASE]}" || return

    if git-run "${auth[@]}" -C "${work}" fetch --quiet --depth 1 -- "${url}" "+refs/tags/${tag}:refs/tags/${tag}" 2>/dev/null; then
        tagged="$(git -C "${work}" show "refs/tags/${tag}:${CONFIG[GITOPS_DESIRED]}")" || return
        [[ "${tagged}" == "$(fs-read "${source}/desired.env")" ]] || { err "Tag ${tag} already holds another desired state; publish a new release"; return; }
        git-run "${auth[@]}" -C "${work}" push --quiet -- "${url}" "HEAD:refs/heads/${branch}" || { err "Desired branch push failed: ${branch}"; return; }
        return
    fi

    git -C "${work}" tag "${tag}" || return
    git-run "${auth[@]}" -C "${work}" push --quiet --atomic -- "${url}" "HEAD:refs/heads/${branch}" "refs/tags/${tag}" || { err "Desired state push failed: ${branch} ${tag}"; return; }

}
