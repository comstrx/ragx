test-fs-atomic () {

    local directory="${TMPDIR}/fs" digest=""

    printf original | fs-write "${directory}/deep/file"
    expect-equal "$(fs-mode "${directory}/deep/file")" 600
    expect-equal "$(fs-mode "${directory}/deep")" 700
    digest="$(fs-hash "${directory}/deep/file")"
    expect-equal "${#digest}" 64

    printf changed | fs-write "${directory}/deep/file" 644
    expect-equal "$(fs-read "${directory}/deep/file")" changed
    expect-equal "$(fs-mode "${directory}/deep/file")" 644

    ln -s "${directory}/deep/file" "${directory}/link"
    expect-error 'Refusing symlink destination' fs-write "${directory}/link" < /dev/null
    expect-error 'Regular file required' fs-read "${directory}/link"
    expect-equal "$(fs-read "${directory}/deep/file")" changed

    expect-error 'Path traverses a symlink' fs-within "${directory}" link
    expect-error 'confined relative path' fs-within "${directory}" ../escape
    expect-error 'confined relative path' fs-within "${directory}" /etc/passwd
    expect-equal "$(fs-within "${directory}" deep/file)" "${directory}/deep/file"

    expect-error 'Regular file required' fs-copy "${directory}/absent" "${directory}/deep/file"
    expect-equal "$(fs-read "${directory}/deep/file")" changed 'failed producers keep the destination'

    expect-error 'Refusing removal outside' fs-remove-tree "${directory}" /tmp
    expect-error 'Refusing removal outside' fs-remove-tree "${directory}" "${directory}/../x"
    fs-remove-tree "${directory}" "${directory}/deep"
    expect-fail test -e "${directory}/deep"
    expect-equal "$(find "${TMPDIR}" -name '*.tmp.*' | wc -l | tr -d ' ')" 0 'no staging leftovers'

}
test-state-lock () {

    local directory="${TMPDIR}/state"

    mkdir -p "${directory}"
    state-lock "${directory}/lock"
    expect-error 'Locked by another operation' state-lock "${directory}/lock"
    expect-error 'is still alive' state-recover "${directory}/lock"
    state-unlock "${directory}/lock"

    state-locked "${directory}/lock" true
    expect-fail test -e "${directory}/lock"
    expect-fail state-locked "${directory}/lock" false
    expect-fail test -e "${directory}/lock"

    mkdir "${directory}/lock"
    printf '999999\n' > "${directory}/lock/owner"
    state-recover "${directory}/lock"
    expect-fail test -e "${directory}/lock"

    state-write "${directory}" phase healthy
    expect-equal "$(state-read "${directory}" phase)" healthy
    expect-fail state-read "${directory}" absent
    expect-error 'Invalid state name' state-write "${directory}" ../escape value

    state-audit "${directory}" r1 complete
    expect-contains "$(fs-read "${directory}/audit.log")" 'release=r1 phase=complete'
    expect-error 'Invalid phase' state-audit "${directory}" r1 'bad phase'

}
test-cli-parse () {

    cli-parse --environment staging -e PROJECT=value --config a --config b --force deploy extra -- --raw
    expect-equal "${CLI_FLAGS[--environment]}" staging
    expect-equal "${CLI_OVERRIDES[0]}" PROJECT=value
    expect-equal "${#CLI_CONFIGS[@]}" 2
    expect-equal "${CLI_ARGS[*]}" 'deploy extra --raw'
    cli-flag --force

    expect-error 'Value required: --config' cli-parse --config
    expect-error 'Repeated flag: --project' cli-parse --project a --project b
    expect-error 'Unknown flag: --json' cli-parse --json
    expect-error 'Expected KEY=VALUE after -e' cli-parse -e lower=value
    expect-error 'Unknown command: drop' cli-dispatch native-tls drop 'issue renew'

    cli-has deploy "${STACK_COMMANDS[@]}"
    expect-fail cli-has native-deploy "${STACK_COMMANDS[@]}"
    expect-error 'Unknown command: arbitrary' bash "${TOOL_BIN}" --project "${TMPDIR}" arbitrary

}
test-sys-detection () {

    local family=""

    OSTYPE=linux-gnu
    is-linux
    expect-fail is-macos
    OSTYPE=darwin24
    is-macos
    expect-equal "$(distro)" macos
    OSTYPE=msys
    expect-fail is-unix
    expect-error 'Unsupported operating system' os
    expect-equal "$(runtime)" unsupported

    GITHUB_ACTIONS=false
    CI=false
    expect-fail is-ci
    GITHUB_ACTIONS=true
    GITHUB_EVENT_NAME=pull_request
    GITLAB_CI=true
    CI_COMMIT_TAG=irrelevant
    expect-equal "$(ci-name)" github
    is-ci-pull
    expect-fail is-ci-tag
    expect-fail is-ci-push
    GITHUB_EVENT_NAME=push
    GITHUB_REF_TYPE=tag
    is-ci-tag
    expect-fail is-ci-push
    GITHUB_REF_TYPE=branch
    is-ci-push

    has bash
    expect-fail has --version
    expect-error 'Missing tool: infra-absent-tool' need infra-absent-tool
    expect-fail has-all bash infra-absent-tool

    for family in apt apk dnf yum pacman zypper xbps brew port nix; do
        package-capability "${family}" install
    done

    expect-fail package-capability nix refresh
    expect-fail package-capability winget install
    expect-error 'Invalid package name' package-call apt install 'curl; reboot'
    expect-error 'Unsupported package operation' package-call nix refresh

}
test-sys-processes () {

    local started="" output=""

    expect-equal "$(run-cmd printf '%s' "spaces ' quotes \$()")" "spaces ' quotes \$()"
    expect-error 'Command required' run-cmd
    expect-status 7 run-cmd bash -c 'exit 7'

    started="${SECONDS}"
    expect-error 'Timed out after 1s: sleep' run-timeout 1 sleep 30
    (( SECONDS - started <= 3 )) || err "run-timeout did not stop the child"

    expect-equal "$(printf 'piped\n' | run-timeout 5 cat)" piped
    output="$(run-timeout 5 bash -c 'printf ok')"
    expect-equal "${output}" ok
    expect-status 3 run-timeout 5 bash -c 'exit 3'

    expect-fail run-until 1 1 false
    run-until 1 1 true

    mkdir -p "${TMPDIR}/bin"
    printf '#!/bin/sh\nexit 1\n' > "${TMPDIR}/bin/sudo"
    chmod 700 "${TMPDIR}/bin/sudo"
    PATH="${TMPDIR}/bin:${PATH}"
    is-root || expect-error 'Noninteractive sudo permission required for: true' run-sudo true

}
test-template-filters () {

    local directory="${TMPDIR}/template"

    mkdir -p "${directory}/src/template"
    printf 'raw={{PROJECT}}\njson={{PROJECT|json}}\n' > "${directory}/src/template/sample"
    TOOL_ROOT="${directory}"
    unset -f embedded-asset

    cfg-set PROJECT $'quote " back \\ line\nnext'
    expect-equal "$(template-text src/template/sample)" $'raw=quote " back \\ line\nnext\njson="quote \\" back \\\\ line\\nnext"'

    printf 'value={{MISSING_KEY}}\n' > "${directory}/src/template/sample"
    expect-error 'requires MISSING_KEY' template-text src/template/sample

    printf 'value={{lower}}\n' > "${directory}/src/template/sample"
    expect-error 'Invalid placeholder' template-text src/template/sample

}
