test-gitops-desired () {

    local file="${TMPDIR}/desired.env" accepted='VERSION RELEASE MIGRATION_POLICY COMPOSE_SHA256 RELEASE_REF CORE_IMAGE CORE_ENV_SHA256'

    printf 'RELEASE=r2\nCORE_IMAGE=ghcr.io/org/core@%s\nCOMPOSE_SHA256=%064d\nRELEASE_REF=refs/tags/release-r2\n' "$(fixture-digest 4)" 5 > "${file}"
    gitops-read "${file}" "${accepted}"
    expect-equal "${CONFIG[RELEASE]}" r2
    expect-equal "${CONFIG[RELEASE_REF]}" refs/tags/release-r2
    expect-equal "${CONFIG[MIGRATION_POLICY]}" none
    expect-equal "${CONFIG_SOURCE[RELEASE]}" gitops
    expect-equal "${CONFIG[CORE_ENV_SHA256]}" ''

    printf 'CORE_ENV_SHA256=%064d\n' 7 >> "${file}"
    gitops-read "${file}" "${accepted}"
    expect-equal "${CONFIG[CORE_ENV_SHA256]}" "$(printf '%064d' 7)"

    printf 'VERSION=v2\n' >> "${file}"
    expect-error 'Desired RELEASE must extend VERSION' gitops-read "${file}" "${accepted}"
    sed -i.bak 's/^VERSION=v2$/VERSION=r2/; s/^RELEASE=r2$/RELEASE=r2-0a1b2c3d/' "${file}"
    gitops-read "${file}" "${accepted}"
    expect-equal "${CONFIG[VERSION]}" r2

    gitops-read "${file}" "${accepted} SHOP_IMAGE SHOP_ENV_SHA256"
    expect-equal "${CONFIG[SHOP_IMAGE]}" '' 'a part without an image is simply not shipped'
    printf 'SHOP_IMAGE=ghcr.io/org/shop@%s\nSHOP_ENV_SHA256=short\n' "$(fixture-digest 6)" >> "${file}"
    expect-error 'Desired SHOP_ENV_SHA256 must be a SHA-256' gitops-read "${file}" "${accepted} SHOP_IMAGE SHOP_ENV_SHA256"
    expect-error 'Unexpected desired-state key: SHOP_' gitops-read "${file}" "${accepted}"

    printf 'REGISTRY_TOKEN=forbidden\n' >> "${file}"
    expect-error 'Unexpected desired-state key: REGISTRY_TOKEN' gitops-read "${file}" "${accepted} SHOP_IMAGE SHOP_ENV_SHA256"

    printf 'RELEASE=r3\nCORE_IMAGE=ghcr.io/org/core:latest\nCOMPOSE_SHA256=%064d\nRELEASE_REF=refs/tags/r3\n' 5 > "${file}"
    expect-error 'Desired CORE_IMAGE must be pinned by digest' gitops-read "${file}" "${accepted}"

    printf 'RELEASE=r3\nCORE_IMAGE=ghcr.io/org/core@%s\nCOMPOSE_SHA256=%064d\nRELEASE_REF=refs/heads/main\n' "$(fixture-digest 4)" 5 > "${file}"
    expect-error 'Desired RELEASE_REF must name a tag' gitops-read "${file}" "${accepted}"

    fixture-release
    fixture-sites
    expect-equal "$(native-desired-keys)" 'VERSION RELEASE MIGRATION_POLICY COMPOSE_SHA256 RELEASE_REF CORE_IMAGE CORE_ENV_SHA256 SHOP_IMAGE SHOP_ENV_SHA256 DESK_IMAGE DESK_ENV_SHA256'

}
test-gitops-portainer-payload () {

    local body="${TMPDIR}/payload" text="" captured="${TMPDIR}/captured"

    cfg-set GITOPS_URL https://git.example.test/org/deploy
    cfg-set GITOPS_USER reader
    cfg-set GITOPS_TOKEN 'git-sentinel"token'
    cfg-set RELEASE_REF refs/tags/release-r1

    fs-produce "${body}" 600 portainer-payload shop-r1 CORE_REPLICAS=3 'DEPLOY_SLOT=blue' 'RELEASE_ROOT=/srv/state dir/r1'
    text="$(fs-read "${body}")"
    expect-equal "$(fs-mode "${body}")" 600
    expect-contains "${text}" '"RepositoryReferenceName":"refs/tags/release-r1"'
    expect-contains "${text}" '"ComposeFile":"deploy/application.yaml"'
    expect-contains "${text}" '"RepositoryPassword":"git-sentinel\"token"'
    expect-contains "${text}" '"TLSSkipVerify":false'
    expect-contains "${text}" '{"name":"RELEASE_ROOT","value":"/srv/state dir/r1"}'
    expect-absent "${text}" AutoUpdate
    jq -e . "${body}" >/dev/null || err "Portainer payload is not valid JSON"

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" > "${TMPDIR}/captured"' 'cat > "${TMPDIR}/captured.config"' \
        'while (( $# > 1 )); do [[ "$1" != --output ]] || printf "{\"Id\":42}" > "$2"; shift; done' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set PORTAINER_TOKEN portainer-sentinel
    expect-equal "$(portainer-create shop-r1 CORE_REPLICAS=2)" 42
    expect-contains "$(fs-read "${TMPDIR}/captured.config")" 'url = "https://localhost:9443/api/stacks/create/standalone/repository?endpointId=1"'
    expect-contains "$(fs-read "${TMPDIR}/captured.config")" 'header = "X-API-Key: portainer-sentinel"'
    expect-absent "$(fs-read "${captured}")" portainer-sentinel
    expect-equal "$(ls -A "${TOOL_TEMP}")" '' 'request bodies are removed'

}
test-gitops-relocate () {

    local root="/srv/state dir/releases/r1" text=""

    printf '{"name":"x","services":{"core":{"volumes":[{"type":"bind","source":"%s/${RELEASE_ROOT:?RELEASE_ROOT required}/core.env","target":"/app/.env"},"%s/data:/data"]}}}\n' "${root}" "${root}" > "${TMPDIR}/compose.json"
    text="$(gitops-relocate "${root}" "${TMPDIR}/compose.json")"

    expect-contains "${text}" '"source": "${RELEASE_ROOT:?RELEASE_ROOT required}/core.env"'
    expect-contains "${text}" '"${RELEASE_ROOT}/data:/data"'
    expect-absent "${text}" "${root}"
    expect-absent "${text}" '"name"'

}
test-gitops-control-plane () {

    local directory="${TMPDIR}/control" text=""

    openssl req -help 2>&1 | grep -q -- -addext || return 0

    tls-authority "${directory}" 'lab control' localhost localhost 127.0.0.1
    expect-fail test -e "${directory}/ca.key"
    expect-equal "$(fs-mode "${directory}/server.key")" 600
    openssl verify -CAfile "${directory}/ca.pem" "${directory}/server.pem" >/dev/null || err "Server certificate does not chain to the private authority"
    text="$(openssl x509 -in "${directory}/server.pem" -noout -text)"
    expect-contains "${text}" 'DNS:localhost, IP Address:127.0.0.1'
    expect-contains "${text}" 'CA:FALSE'

    printf 'keep\n' > "${directory}/marker"
    tls-authority "${directory}" 'lab control' other.test
    expect-absent "$(openssl x509 -in "${directory}/server.pem" -noout -text)" other.test 'existing authorities are kept'

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" >> "${TMPDIR}/portainer.args"' 'cat >> "${TMPDIR}/portainer.stdin"' \
        'body=""; out=""; while (( $# > 1 )); do [[ "$1" != --output ]] || out="$2"; [[ "$1" != --data-binary ]] || body="${2#@}"; shift; done' \
        'case "$(cat "${body}")" in *Username*) printf "{\"jwt\":\"jwt-value\"}" > "${out}" ;; *) printf "{\"rawAPIKey\":\"ptr_key\"}" > "${out}" ;; esac' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    cfg-set PORTAINER_ADMIN_PASSWORD 'admin "sentinel" password'
    portainer-api-key "${TMPDIR}/api-key"
    expect-equal "$(fs-read "${TMPDIR}/api-key")" ptr_key
    expect-equal "$(fs-mode "${TMPDIR}/api-key")" 600
    expect-absent "$(fs-read "${TMPDIR}/portainer.args")" sentinel
    expect-contains "$(fs-read "${TMPDIR}/portainer.stdin")" 'Authorization: Bearer jwt-value'
    expect-contains "$(fs-read "${TMPDIR}/portainer.stdin")" https://localhost:9443/api/users/1/tokens

}
