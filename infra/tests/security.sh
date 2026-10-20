test-secret-ssh-transport () {

    local log="${TMPDIR}/ssh.args" secret="${TMPDIR}/ssh.secret" key="${TMPDIR}/id" certificate="${TMPDIR}/id-cert.pub" recorded=""

    ssh () { printf '%s\n' "$@" > "${log}"; }
    sshpass () { printf '%s\n' "$@" > "${log}"; cat <&"${2}" > "${secret}"; }

    cfg-set SSH_HOST 203.0.113.10
    cfg-set SSH_USER deploy
    cfg-set SSH_METHOD password
    cfg-set SSH_PASSWORD "pass 'word' \$(id) sentinel"
    ssh-command true
    recorded="$(fs-read "${log}")"
    expect-equal "$(fs-read "${secret}")" "pass 'word' \$(id) sentinel"
    expect-absent "${recorded}" sentinel
    expect-contains "${recorded}" StrictHostKeyChecking=yes
    expect-contains "${recorded}" ForwardAgent=no
    expect-contains "${recorded}" PubkeyAuthentication=no

    cfg-set SSH_METHOD agent
    ssh-command true
    recorded="$(fs-read "${log}")"
    expect-contains "${recorded}" BatchMode=yes
    expect-contains "${recorded}" deploy@203.0.113.10
    expect-absent "${recorded}" IdentitiesOnly

    : > "${key}"
    : > "${certificate}"
    cfg-set SSH_METHOD certificate
    cfg-set SSH_KEY "${key}"
    cfg-set SSH_CERTIFICATE "${certificate}"
    ssh-command true
    recorded="$(fs-read "${log}")"
    expect-contains "${recorded}" IdentitiesOnly=yes
    expect-contains "${recorded}" "CertificateFile=${certificate}"

    cfg-set SSH_METHOD auto
    cfg-set SSH_PASSWORD ''
    cfg-set SSH_CERTIFICATE ''
    cfg-set SSH_KEY $'-----BEGIN OPENSSH PRIVATE KEY-----\nkey-sentinel\n-----END OPENSSH PRIVATE KEY-----'
    cfg-set SSH_KNOWN_HOSTS "$(printf '203.0.113.10 ssh-ed25519 AAAAC3Nza\n' | openssl base64 -A)"
    ssh-command true
    recorded="$(fs-read "${log}")"
    expect-contains "${recorded}" IdentitiesOnly=yes 'auto picks the key'
    expect-absent "${recorded}" key-sentinel
    expect-contains "$(fs-read "${TOOL_TEMP:-${TMPDIR}}/ssh-ssh_key")" key-sentinel 'key content lands in a private file'
    expect-equal "$(fs-mode "${TOOL_TEMP:-${TMPDIR}}/ssh-ssh_key")" 600
    expect-equal "$(fs-read "${TOOL_TEMP:-${TMPDIR}}/ssh-ssh_known_hosts")" '203.0.113.10 ssh-ed25519 AAAAC3Nza' 'base64 known hosts decode'
    expect-contains "${recorded}" "UserKnownHostsFile=${TOOL_TEMP:-${TMPDIR}}/ssh-ssh_known_hosts"

    cfg-set SSH_KEY "${TMPDIR}/absent-key"
    expect-error 'SSH_KEY file not found' ssh-command true

    cfg-set SSH_METHOD pem
    expect-error 'Unsupported SSH_METHOD: pem' ssh-command true
    cfg-set SSH_HOST 'host;reboot'
    expect-error 'Invalid SSH_HOST' ssh-command true

}
test-secret-ssh-arguments () {

    local argument="" invocation="" actual="" sentinel="${TMPDIR}/executed"
    local -a arguments=( '' 'two words' "quote ' and double \"" '$HOME; false' $'line\ntwo' "\$(touch ${sentinel})" )

    for argument in "${arguments[@]}"; do
        invocation="$(ssh-encode printf '%s' "${argument}")"
        actual="$(sh -c "${invocation}")"
        expect-equal "${actual}" "${argument}"
    done

    expect-fail test -e "${sentinel}"
    expect-error 'Remote command required' ssh-encode
    expect-error 'relative path below the SSH home' ssh-upload /missing ../escape

}
test-secret-ssh-upload () {

    local directory="${TMPDIR}/home" script="" checksum=""

    mkdir -p "${directory}"
    script="$(ssh-upload-script)"
    printf complete > "${TMPDIR}/source"
    checksum="$(fs-hash "${TMPDIR}/source")"

    env HOME="${directory}" bash -c "${script}" upload child/result 600 "${checksum}" < "${TMPDIR}/source"
    expect-equal "$(fs-read "${directory}/child/result")" complete
    expect-equal "$(fs-mode "${directory}/child/result")" 600

    printf tampered > "${TMPDIR}/other"
    expect-fail env HOME="${directory}" bash -c "${script}" upload child/result 600 "${checksum}" < "${TMPDIR}/other"
    expect-equal "$(fs-read "${directory}/child/result")" complete

    ln -s "${directory}/child" "${directory}/link"
    expect-fail env HOME="${directory}" bash -c "${script}" upload link/result 600 "${checksum}" < "${TMPDIR}/source"
    expect-fail env HOME="${directory}" bash -c "${script}" upload ../outside 600 "${checksum}" < "${TMPDIR}/source"

}
test-secret-http-credentials () {

    local log="${TMPDIR}/curl.args" config="${TMPDIR}/curl.config"

    curl () {

        local next="" previous=""

        printf '%s\n' "$@" > "${log}"
        cat > "${config}"
        for next in "$@"; do
            [[ "${previous}" != --output ]] || printf '{"ok":true}' > "${next}"
            previous="${next}"
        done

    }

    net-request POST https://api.example.test/v1/items "${TMPDIR}/response" X-API-Key 'tok"en\sentinel'
    expect-absent "$(fs-read "${log}")" sentinel
    expect-equal "$(fs-read "${config}")" $'url = "https://api.example.test/v1/items"\nheader = "X-API-Key: tok\\"en\\\\sentinel"'
    expect-contains "$(fs-read "${log}")" '=https'
    expect-equal "$(fs-read "${TMPDIR}/response")" '{"ok":true}'

    expect-error 'HTTPS URL without credentials required' net-request GET https://user:pass@api.example.test/ "${TMPDIR}/response"
    expect-error 'HTTPS URL without credentials required' net-request GET http://api.example.test/ "${TMPDIR}/response"
    expect-error 'Credential must be a single line' net-request GET https://api.example.test/ "${TMPDIR}/response" X-API-Key $'a\nb'
    expect-error 'Unsupported HTTP method' net-request TRACE https://api.example.test/ "${TMPDIR}/response"

}
test-secret-git-credentials () {

    local log="${TMPDIR}/git.args" vault=""

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" > "${TMPDIR}/git.args"' \
        'printf "%s|%s\n" "$("${GIT_ASKPASS}" "Username for x")" "$("${GIT_ASKPASS}" "Password for x")" > "${TMPDIR}/git.answers"' \
        'printf "%s\n" "${INFRA_GIT_VAULT}" > "${TMPDIR}/git.vault"' > "${TMPDIR}/bin/git"
    chmod 700 "${TMPDIR}/bin/git"
    PATH="${TMPDIR}/bin:${PATH}"

    git-checkout https://git.example.test/org/repo main "${TMPDIR}/clone" reader 'git-sentinel-token'
    vault="$(fs-read "${TMPDIR}/git.vault")"

    expect-equal "$(fs-read "${TMPDIR}/git.answers")" 'reader|git-sentinel-token'
    expect-absent "$(fs-read "${log}")" git-sentinel-token
    expect-contains "$(fs-read "${log}")" credential.helper=
    expect-contains "$(fs-read "${log}")" protocol.file.allow=never
    expect-fail test -e "${vault}"

    expect-error 'HTTPS repository URL without credentials' git-checkout https://user:pw@git.example.test/org/repo main "${TMPDIR}/x" u t
    expect-error 'Invalid Git reference' git-checkout https://git.example.test/org/repo 'main;false' "${TMPDIR}/x" u t
    expect-error 'Invalid Git reference' git-checkout https://git.example.test/org/repo '-upload-pack=x' "${TMPDIR}/x" u t

}
test-secret-tool-credentials () {

    local log="${TMPDIR}/tool.args"

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" > "${TMPDIR}/tool.args"' 'printf "%s\n" "${AWS_SECRET_ACCESS_KEY:-}" > "${TMPDIR}/aws.env"' > "${TMPDIR}/bin/docker"
    chmod 700 "${TMPDIR}/bin/docker"
    PATH="${TMPDIR}/bin:${PATH}"
    docker-client () { printf '%s\n' "$@" > "${log}"; cat > "${TMPDIR}/docker.stdin"; }

    printf 'dump\n' > "${TMPDIR}/file"
    cfg-set BACKUP_KEY key-id
    cfg-set BACKUP_SECRET 's3-sentinel-secret'
    cfg-set BACKUP_REGION eu-west-1
    s3-upload "${TMPDIR}/file" s3://bucket/daily/file
    expect-absent "$(fs-read "${log}")" s3-sentinel-secret
    expect-equal "$(fs-read "${TMPDIR}/aws.env")" s3-sentinel-secret
    expect-contains "$(fs-read "${log}")" $'/upload/file\ns3://bucket/daily/file'
    expect-contains "$(fs-read "${log}")" "${CONFIG[IMAGE_AWS]}"
    expect-absent "$(fs-read "${log}")" --endpoint-url

    cfg-set BACKUP_REGION ''
    s3-upload "${TMPDIR}/file" gs://bucket/daily/file
    expect-contains "$(fs-read "${log}")" $'--endpoint-url\nhttps://storage.googleapis.com'
    expect-contains "$(fs-read "${log}")" s3://bucket/daily/file 'gs:// travels through the S3-compatible API'
    expect-contains "$(fs-read "${log}")" AWS_REQUEST_CHECKSUM_CALCULATION
    expect-error 'Backup destination must start with s3:// or gs://' s3-upload "${TMPDIR}/file" https://bucket/file
    expect-error 'Regular file required' s3-upload "${TMPDIR}/missing" s3://bucket/missing

    docker-login ghcr.io reader 'registry-sentinel-token'
    expect-absent "$(fs-read "${log}")" registry-sentinel-token
    expect-contains "$(fs-read "${log}")" --password-stdin
    expect-equal "$(fs-read "${TMPDIR}/docker.stdin")" registry-sentinel-token

}
test-secret-http-status () {

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf 204' > "${TMPDIR}/bin/curl"
    chmod 700 "${TMPDIR}/bin/curl"
    PATH="${TMPDIR}/bin:${PATH}"

    net-status https://localhost:9443/api/system/status 204
    expect-fail net-status https://localhost:9443/api/system/status 200
    expect-error 'HTTP URL required' net-status ftp://localhost/ 200
    expect-error 'URL must be a single line' net-status $'https://a/\nb' 200

}
test-secret-notifications () {

    local output="" name="" event="" expected=""

    mkdir -p "${TMPDIR}/bin"
    cat > "${TMPDIR}/bin/curl" <<'CURL'
#!/usr/bin/env bash
config="$(cat)"
count=$(( $(cat "${TMPDIR}/curl.count" 2>/dev/null || printf 0) + 1 ))
printf '%s' "${count}" > "${TMPDIR}/curl.count"
printf '%s\n' "$@" >> "${TMPDIR}/curl.args"
printf '%s\n' "${config}" > "${TMPDIR}/curl.${count}.config"
previous=""
for next in "$@"; do
    [[ "${previous}" != --data-binary ]] || cp -- "${next#@}" "${TMPDIR}/curl.${count}.body"
    [[ "${previous}" != --output ]] || printf '{"ok":true}' > "${next}"
    previous="${next}"
done
failures="$(cat "${TMPDIR}/curl.failures" 2>/dev/null || printf 0)"
if [[ "${config}" == *flaky* ]] && (( failures > 0 )); then
    printf '%s' "$(( failures - 1 ))" > "${TMPDIR}/curl.failures"
    exit 22
fi
[[ "${config}" != *broken* ]]
CURL
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "${TMPDIR}/bin/sleep"
    chmod 700 "${TMPDIR}/bin/curl" "${TMPDIR}/bin/sleep"
    PATH="${TMPDIR}/bin:${PATH}"
    cfg-set PROJECT shop
    config-derive

    expect-contains "$(native-notify hello 2>&1)" 'No notification channel is configured; nothing sent'
    expect-equal "$(native-announce deploy.succeeded 'r2 is live' 2>&1)" '' 'no channel means silent success'
    expect-fail test -e "${TMPDIR}/curl.count"
    expect-error 'Usage: notify MESSAGE' native-notify

    cli-parse notify hello --channel telegram --token 123456:flag-sentinel-token-0123456789 --chat -1009
    native-notify hello >/dev/null
    expect-equal "$(fs-read "${TMPDIR}/curl.count")" 1
    expect-equal "$(fs-read "${TMPDIR}/curl.1.config")" 'url = "https://api.telegram.org/bot123456:flag-sentinel-token-0123456789/sendMessage"'
    expect-contains "$(fs-read "${TMPDIR}/curl.1.body")" '"chat_id":"-1009"'
    expect-absent "$(fs-read "${TMPDIR}/curl.args")" flag-sentinel 'flag values travel like settings, never in argv'
    cli-parse notify hello --channel slack
    expect-error 'slack is not configured; pass its flags or set its settings' native-notify hello
    cli-parse notify hello --channel pager
    expect-error 'Unknown channel: pager (expected telegram, slack or webhook)' native-notify hello
    cli-parse notify hello --token 'not a token'
    expect-error 'Invalid TELEGRAM_BOT_TOKEN' native-notify hello
    cli-parse notify hello --token 123456:flag-sentinel-token-0123456789
    cfg-set TELEGRAM_CHAT_ID ''
    expect-error 'TELEGRAM settings are partial; missing TELEGRAM_CHAT_ID' native-notify hello
    cli-parse
    cfg-set TELEGRAM_BOT_TOKEN ''
    rm -f -- "${TMPDIR}/curl.count" "${TMPDIR}/curl.args" "${TMPDIR}"/curl.1.*

    cfg-set TELEGRAM_BOT_TOKEN '123456:telegram-sentinel-token-0123456789'
    cfg-set TELEGRAM_CHAT_ID -1001234567890
    cfg-set SLACK_WEBHOOK_URL 'https://hooks.slack.com/services/T0/B0/slack-sentinel'
    cfg-set WEBHOOK_URL 'https://hooks.example.test/infra?token=webhook-sentinel'
    cfg-set WEBHOOK_SECRET 'signing "sentinel" secret'
    cfg-set RELEASE r2

    native-announce deploy.succeeded 'release "r2" is live'
    expect-equal "$(fs-read "${TMPDIR}/curl.count")" 3
    expect-absent "$(fs-read "${TMPDIR}/curl.args")" sentinel 'tokens and webhook URLs never enter argv'
    expect-equal "$(head -1 "${TMPDIR}/curl.args")" --disable 'a user curlrc never applies'
    expect-equal "$(fs-read "${TMPDIR}/curl.1.config")" 'url = "https://api.telegram.org/bot123456:telegram-sentinel-token-0123456789/sendMessage"'
    expect-equal "$(fs-read "${TMPDIR}/curl.1.body")" '{"chat_id":"-1001234567890","text":"🚀 shop: release \"r2\" is live"}'
    expect-equal "$(fs-read "${TMPDIR}/curl.2.body")" '{"text":"🚀 shop: release \"r2\" is live"}'
    output="$(fs-read "${TMPDIR}/curl.3.body")"
    jq -e '.event == "deploy.succeeded" and .level == "info" and .project == "shop" and .release == "r2" and .text == "release \"r2\" is live"' <<< "${output}" >/dev/null || err "Unexpected webhook payload: ${output}"
    expected="$(openssl dgst -sha256 -hmac 'signing "sentinel" secret' "${TMPDIR}/curl.3.body" | awk '{print $NF}')"
    expect-contains "$(fs-read "${TMPDIR}/curl.3.config")" "header = \"X-Infra-Signature: sha256=${expected}\""
    expect-equal "$(ls -A "${TOOL_TEMP}")" '' 'request bodies are removed'

    cfg-set TELEGRAM_BOT_TOKEN ''
    cfg-set TELEGRAM_CHAT_ID ''
    cfg-set SLACK_WEBHOOK_URL ''
    cfg-set WEBHOOK_URL 'https://hooks.example.test/flaky'
    printf 2 > "${TMPDIR}/curl.failures"
    rm -f -- "${TMPDIR}/curl.count"
    output="$(native-announce backup.succeeded 'backup saved' 2>&1)"
    expect-equal "$(fs-read "${TMPDIR}/curl.count")" 3 'two failures are retried'
    expect-contains "${output}" 'Attempt 2 of 3 failed; retrying in 4s'
    expect-absent "${output}" 'did not reach every channel'

    cfg-set WEBHOOK_URL 'https://hooks.example.test/broken'
    output="$(native-announce backup.failed 'backup failed' 2>&1)" || err "An undelivered announcement failed its caller"
    expect-contains "${output}" 'The backup.failed notification did not reach every channel'
    expect-error 'Notification failed on webhook' native-notify 'operator message'
    expect-error 'Unknown notification event: deploy.done' native-deliver deploy.done text
    expect-equal "$(cfg-show WEBHOOK_URL)" '[redacted]'
    cfg-set SLACK_WEBHOOK_URL 'https://hooks.slack.com/services/T0/B0/slack-sentinel'
    expect-equal "$(cfg-show SLACK_WEBHOOK_URL)" '[redacted]'

    while IFS= read -r name; do
        while read -r event; do
            native-event "${event}" >/dev/null || err "${name} announces an unknown event: ${event}"
        done < <(declare -f "${name}" | grep -o 'native-announce [a-z][a-z.-]*' | cut -d' ' -f2)
    done < <(declare -F | awk '$3 ~ /^native-/ { print $3 }')

}
test-secret-transient-credentials () {

    local log="${TMPDIR}/ssh.args" input="${TMPDIR}/ssh.stdin"

    mkdir -p "${TMPDIR}/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$@" >> "${TMPDIR}/ssh.args"' 'cat >> "${TMPDIR}/ssh.stdin"' > "${TMPDIR}/bin/ssh"
    chmod 700 "${TMPDIR}/bin/ssh"
    PATH="${TMPDIR}/bin:${PATH}"

    printf 'bundle\n' > "${TMPDIR}/bundle"
    TOOL_BUNDLED=true
    TOOL_BUILD=release
    TOOL_BIN="${TMPDIR}/bundle"
    cfg-set SSH_HOST 203.0.113.10
    cfg-set SSH_USER deploy
    cfg-set REMOTE_DIR app
    cfg-set PROJECT shop
    cfg-set REGISTRY_USER robot file
    cfg-set REGISTRY_TOKEN registry-sentinel-token process
    cfg-set GITOPS_USER reader file
    cfg-set GITOPS_TOKEN gitops-permanent-sentinel file

    expect-equal "$(native-server-transient | tr '\n' ' ')" 'REGISTRY_TOKEN '
    expect-contains "$(native-server-stage 2>&1)" 'API env not staged: export API_ENV_FILE; the server keeps its current copy'
    expect-contains "$(fs-read "${input}")" "PROJECT='shop'"
    expect-contains "$(fs-read "${input}")" gitops-permanent-sentinel 'permanent credentials from the env file are staged'
    expect-absent "$(fs-read "${input}")" registry-sentinel 'credentials from the process environment are never staged'
    expect-absent "$(fs-read "${log}")" .env.api

    : > "${input}"
    : > "${log}"
    export API_ENV_FILE=$'APP_ENV=production\nAUTH_SECRET=api-env-sentinel\n'
    native-server-stage >/dev/null 2>&1
    expect-contains "$(fs-read "${input}")" $'APP_ENV=production\nAUTH_SECRET=api-env-sentinel'
    expect-contains "$(fs-read "${log}")" app/.env.api
    expect-absent "$(fs-read "${log}")" api-env-sentinel 'the application env never enters argv'
    expect-absent "$(fs-read "${input}")" "API_ENV_FILE='" 'the application env stays out of the infrastructure settings'
    unset API_ENV_FILE

    : > "${input}"
    native-server-run -- deploy --force
    expect-equal "$(tr '\0' '|' < "${input}")" 'REGISTRY_TOKEN=registry-sentinel-token|'
    expect-contains "$(fs-read "${log}")" 'read -r -d'
    expect-absent "$(fs-read "${log}")" registry-sentinel

    : > "${input}"
    cfg-set REGISTRY_TOKEN registry-sentinel-token file
    native-server-run status < /dev/null
    expect-equal "$(fs-read "${input}")" ''

}
