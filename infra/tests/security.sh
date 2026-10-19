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
    expect-equal "$(fs-read "${config}")" 'header = "X-API-Key: tok\"en\\sentinel"'
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

    aws () { local name=AWS_SECRET_ACCESS_KEY; printf '%s\n' "$@" > "${log}"; printf '%s\n' "${!name}" > "${TMPDIR}/aws.env"; }
    docker-client () { printf '%s\n' "$@" > "${log}"; cat > "${TMPDIR}/docker.stdin"; }

    cfg-set BACKUP_S3_KEY key-id
    cfg-set BACKUP_S3_SECRET 's3-sentinel-secret'
    cfg-set BACKUP_S3_REGION eu-west-1
    s3-upload "${TMPDIR}/file" s3://bucket/file
    expect-absent "$(fs-read "${log}")" s3-sentinel-secret
    expect-equal "$(fs-read "${TMPDIR}/aws.env")" s3-sentinel-secret
    expect-error 'S3 destination must start with s3://' s3-upload "${TMPDIR}/file" https://bucket/file

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
