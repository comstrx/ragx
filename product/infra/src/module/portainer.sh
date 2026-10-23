portainer-request () {

    local method="${1}" path="${2}" destination="${3}" body="${4:-}"

    cfg-require PORTAINER_URL PORTAINER_TOKEN || return

    net-request "${method}" "${CONFIG[PORTAINER_URL]%/}/api${path}" "${destination}" X-API-Key "${CONFIG[PORTAINER_TOKEN]}" "${body}" "${CONFIG[PORTAINER_CA]}"

}
portainer-json () {

    local method="${1}" path="${2}" filter="${3}" body="${4:-}" response="" status=0

    shift 4
    need jq || return
    response="$(fs-temp-file)" || return

    portainer-request "${method}" "${path}" "${response}" "${body}" || status=$?
    (( status != 0 )) || jq -er "$@" "${filter}" "${response}" || status=$?

    rm -f -- "${response}"
    return "${status}"

}
portainer-stack () {

    local name="${1}"

    parse-positive "${CONFIG[PORTAINER_ENDPOINT]}" || { err "PORTAINER_ENDPOINT must be a positive integer"; return; }

    portainer-json GET /stacks '[.[] | select(.Name == $name and .EndpointId == $endpoint)] |
        if length == 0 then "" elif length == 1 then .[0].Id else error("duplicate stacks") end' '' \
        --arg name "${name}" --argjson endpoint "${CONFIG[PORTAINER_ENDPOINT]}" || { err "Portainer stack lookup failed: ${name}"; return; }

}
portainer-payload () {

    local name="${1}" pair="" first=true

    shift

    printf '{"Name":%s,"RepositoryURL":%s,"RepositoryReferenceName":%s,"ComposeFile":%s,' \
        "$(parse-json-string "${name}")" "$(parse-json-string "${CONFIG[GITOPS_URL]}")" \
        "$(parse-json-string "${CONFIG[RELEASE_REF]}")" "$(parse-json-string "${CONFIG[GITOPS_COMPOSE]}")"
    printf '"RepositoryAuthentication":true,"RepositoryUsername":%s,"RepositoryPassword":%s,"TLSSkipVerify":false,"Env":[' \
        "$(parse-json-string "${CONFIG[GITOPS_USER]}")" "$(parse-json-string "${CONFIG[GITOPS_TOKEN]}")"

    for pair in "$@"; do
        [[ "${first}" == true ]] || printf ','
        first=false
        printf '{"name":%s,"value":%s}' "$(parse-json-string "${pair%%=*}")" "$(parse-json-string "${pair#*=}")"
    done

    printf ']}\n'

}
portainer-create () {

    local name="${1}" body="" status=0

    shift
    cfg-require GITOPS_URL GITOPS_USER GITOPS_TOKEN RELEASE_REF || return
    body="$(fs-temp-file)" || return

    fs-produce "${body}" 600 portainer-payload "${name}" "$@" || status=$?
    (( status != 0 )) || portainer-json POST "/stacks/create/standalone/repository?endpointId=${CONFIG[PORTAINER_ENDPOINT]}" .Id "${body}" || status=$?

    rm -f -- "${body}"
    return "${status}"

}
portainer-commit () {

    portainer-json GET "/stacks/${1}" .GitConfig.ConfigHash ''

}
portainer-delete () {

    local response="" status=0

    response="$(fs-temp-file)" || return
    portainer-request DELETE "/stacks/${1}?endpointId=${CONFIG[PORTAINER_ENDPOINT]}" "${response}" || status=$?
    rm -f -- "${response}"

    return "${status}"

}
portainer-registry () {

    local host="${1}" type="${2}" name="${3}" id="" body="" status=0

    cfg-require REGISTRY_USER REGISTRY_TOKEN || return

    id="$(portainer-json GET /registries '[.[] | select(.URL == $host)] |
        if length == 0 then ""
        elif length == 1 and .[0].Username == $user and .[0].Authentication == true then .[0].Id
        else error("registry exists with another identity") end' '' --arg host "${host}" --arg user "${CONFIG[REGISTRY_USER]}")" || { err "Portainer registry ${host} is ambiguous; inspect it"; return; }

    [[ -z "${id}" ]] || { info "Portainer registry ${host} already registered"; return 0; }

    body="$(fs-temp-file)" || return
    printf '{"Name":%s,"URL":%s,"Type":%s,"Authentication":true,"Username":%s,"Password":%s}\n' \
        "$(parse-json-string "${name}")" "$(parse-json-string "${host}")" "${type}" \
        "$(parse-json-string "${CONFIG[REGISTRY_USER]}")" "$(parse-json-string "${CONFIG[REGISTRY_TOKEN]}")" | fs-write "${body}" || status=$?

    (( status != 0 )) || portainer-json POST /registries .Id "${body}" >/dev/null || status=$?
    rm -f -- "${body}"

    return "${status}"

}
portainer-ready () {

    net-status "${CONFIG[PORTAINER_URL]%/}/api/system/status" 200 --cacert "${CONFIG[PORTAINER_CA]}"

}
portainer-api-key () {

    local destination="${1}" body="" response="" jwt="" status=0

    need jq || return
    body="$(fs-temp-file)" || return
    response="$(fs-temp-file)" || return

    printf '{"Username":"admin","Password":%s}\n' "$(parse-json-string "${CONFIG[PORTAINER_ADMIN_PASSWORD]}")" | fs-write "${body}" || status=$?
    (( status != 0 )) || net-request POST "${CONFIG[PORTAINER_URL]%/}/api/auth" "${response}" '' '' "${body}" "${CONFIG[PORTAINER_CA]}" || status=$?
    (( status != 0 )) || jwt="$(jq -er .jwt "${response}")" || status=$?

    if (( status == 0 )); then
        printf '{"description":"infra","password":%s}\n' "$(parse-json-string "${CONFIG[PORTAINER_ADMIN_PASSWORD]}")" | fs-write "${body}" || status=$?
        (( status != 0 )) || net-request POST "${CONFIG[PORTAINER_URL]%/}/api/users/1/tokens" "${response}" Authorization "Bearer ${jwt}" "${body}" "${CONFIG[PORTAINER_CA]}" || status=$?
        (( status != 0 )) || jq -er .rawAPIKey "${response}" | fs-write "${destination}" || status=$?
    fi

    rm -f -- "${body}" "${response}"
    (( status == 0 )) || { err "Portainer API key creation failed"; return; }

}
portainer-registry-type () {

    case "${1:-}" in
        ghcr)      out 3 ;;
        dockerhub) out 6 ;;
        *)         err "Unsupported registry driver: ${1:-}"; return ;;
    esac

}
portainer-render () {

    template-render "${MANIFEST[paths.templates]}/native/control.yaml.tpl" "${1}/control.yaml"

}
