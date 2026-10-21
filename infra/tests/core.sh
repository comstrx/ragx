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

    cli-parse --target 203.0.113.10 -e PROJECT=value --config a --config b --force deploy extra -- --raw
    expect-equal "${CLI_FLAGS[--target]}" 203.0.113.10
    expect-equal "${CLI_OVERRIDES[0]}" PROJECT=value
    expect-equal "${#CLI_CONFIGS[@]}" 2
    expect-equal "${CLI_ARGS[*]}" 'deploy extra --raw'
    cli-flag --force

    expect-error 'Value required: --config' cli-parse --config
    expect-error 'Repeated flag: --project' cli-parse --project a --project b
    expect-error 'Unknown flag: --JSON' cli-parse --JSON
    expect-error 'Unknown flag: -x' cli-parse -x
    expect-error 'Expected KEY=VALUE after -e' cli-parse -e lower=value
    expect-error 'Unknown tls action: drop (expected issue or renew)' cli-dispatch native-tls drop 'issue renew'
    expect-error 'Unknown backup action: lst; did you mean list? (expected create, list or verify)' cli-dispatch native-backup lst 'create list verify'
    expect-equal "$(cli-actions 'present=a|issue=b|import CERT KEY=c (x=y)')" 'present issue import'
    expect-error 'No actions declared' cli-actions ''

    cli-parse notify hello --channel=telegram --token 123:abc --chat -1001 --force
    expect-equal "$(cli-value --channel)" telegram
    expect-equal "$(cli-value --chat)" -1001 'a value may start with a dash'
    expect-equal "${CLI_ARGS[*]}" 'notify hello'
    expect-fail cli-flag --token
    expect-fail cli-value --force
    expect-error '--force takes no value' cli-parse --force=yes
    expect-error 'Value required: --token' cli-parse notify --token
    expect-error 'Repeated flag: --chat' cli-parse --chat 1 --chat=2
    expect-error 'notify does not take --force' bash "${TOOL_BIN}" --project "${TMPDIR}" notify hi --force
    expect-error 'status does not take --token' bash "${TOOL_BIN}" --project "${TMPDIR}" status --token x
    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" help notify)" '--token TOKEN'
    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" help restore)" 'Runs on SSH_HOST over SSH'

    cli-parse -h deploy --dry-run
    cli-flag --help
    expect-equal "$(cli-switches)" --dry-run
    expect-equal "$(cli-distance kitten sitting)" 3
    expect-equal "$(cli-suggest deplox deploy rollback render)" deploy
    expect-equal "$(cli-suggest res restore render)" restore
    expect-equal "$(cli-suggest zzzzzz deploy rollback)" ''

    expect-error 'Unknown command: deplox; did you mean deploy?' bash "${TOOL_BIN}" --project "${TMPDIR}" deplox
    expect-error 'Unknown command: arbitrary' bash "${TOOL_BIN}" --project "${TMPDIR}" arbitrary
    expect-error 'deploy does not take --list; see infra help deploy' bash "${TOOL_BIN}" --project "${TMPDIR}" deploy --list
    expect-error 'status does not take --force' bash "${TOOL_BIN}" --project "${TMPDIR}" status --force

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
test-cli-help () {

    local output="" name="" group="" usage="" summary="" actions="" action="" column="" line=""

    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" help)"
    expect-contains "${output}" 'Ships, guards and operates one server'
    expect-contains "${output}" $'\nData\n'
    expect-contains "${output}" 'restore [BACKUP] [--at TIME] --force'
    expect-contains "${output}" 'Global flags'
    expect-contains "${output}" 'config [KEY] [--changed]'
    expect-absent "${output}" '__test'

    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" restore --help)"
    expect-equal "$(bash "${TOOL_BIN}" --project "${TMPDIR}" help restore)" "${output}"
    expect-contains "${output}" 'infra restore [BACKUP] [--at TIME] --force'
    expect-contains "${output}" 'Required: replaces the live database'
    expect-contains "${output}" 'infra restore 20261020T112013Z-jcQdcHui.dump --force'
    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" -h)" 'Global flags'
    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" help test)" '--list'
    expect-error 'Unknown command: restroe; did you mean restore?' bash "${TOOL_BIN}" --project "${TMPDIR}" help restroe

    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" help backup)"
    expect-contains "${output}" 'infra backup [create|list|verify|archive] [BACKUP]'
    expect-contains "${output}" $'\nActions\n'
    expect-contains "${output}" 'prune what is older than BACKUP_DAYS (default)' 'the first action is marked as the default'
    expect-contains "${output}" '  verify [BACKUP]  Restore a dump'

    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" help notify | sed -n '/^Flags$/,/^$/p' | grep -- '--')"
    while IFS= read -r line; do
        [[ "${line}" =~ ^(\ \ --[a-z-]+(\ [A-Z]+)?\ +) ]] || err "Unexpected flag row: ${line}"
        [[ -z "${column}" ]] || expect-equal "${#BASH_REMATCH[1]}" "${column}" "every flag description starts in one column: ${line}"
        column="${#BASH_REMATCH[1]}"
    done <<< "${output}"
    expect-contains "${output}" '  --secret SECRET  HMAC key'
    expect-contains "${output}" '  --chat ID        Telegram chat'

    expect-error 'Unknown timer action: lst; did you mean list?' bash "${TOOL_BIN}" --project "${TMPDIR}" --local timer lst

    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" --version)" "${MANIFEST[name]} ${MANIFEST[version]} (stack native"
    expect-equal "$(bash "${TOOL_BIN}" --project "${TMPDIR}" version)" "$(bash "${TOOL_BIN}" --project "${TMPDIR}" --version)"

    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" -e PROJECT=shop -e TELEGRAM_BOT_TOKEN=123:secret-sentinel config --changed)"
    expect-contains "${output}" 'PROJECT'
    expect-contains "${output}" 'shop  (cli)'
    expect-contains "${output}" '[redacted]  (cli)'
    expect-absent "${output}" secret-sentinel
    expect-absent "${output}" 'HTTP_PORT'
    expect-contains "$(bash "${TOOL_BIN}" --project "${TMPDIR}" config)" '80  (defaults)'
    printf 'HTTP_PORT=80\nHTTPS_PORT=8443\nSLACK_WEBHOOK_URL=\n' > "${TMPDIR}/staged.env"
    output="$(bash "${TOOL_BIN}" --project "${TMPDIR}" --config "${TMPDIR}/staged.env" config --changed)"
    expect-contains "${output}" '8443  (file)'
    expect-absent "${output}" 'HTTP_PORT ' 'a staged default is not a change'
    expect-absent "${output}" SLACK_WEBHOOK_URL
    expect-equal "$(bash "${TOOL_BIN}" --project "${TMPDIR}" --config "${TMPDIR}/staged.env" config SLACK_WEBHOOK_URL)" '' 'an empty secret prints empty'
    expect-equal "$(bash "${TOOL_BIN}" --project "${TMPDIR}" -e PROJECT=shop config PROJECT)" shop

    while IFS='|' read -r name group usage summary; do
        declare -F "native-${name}" >/dev/null || err "${name} is listed without a native-${name} function"
        [[ -n "${group}" && -n "${usage}" && -n "${summary}" ]] || err "${name} has an incomplete row"
    done < <(printf '%s\n' "${STACK_COMMANDS[@]}")

    for name in "${!COMMAND_ABOUT[@]}" "${!COMMAND_NOTES[@]}" "${!COMMAND_EXAMPLES[@]}" "${!COMMAND_FLAGS[@]}" "${!COMMAND_WHERE[@]}" "${!COMMAND_ACTIONS[@]}"; do
        bootstrap-row "${name}" >/dev/null || err "The manual describes an unknown command: ${name}"
    done

    for name in "${!COMMAND_ACTIONS[@]}"; do
        usage="$(bootstrap-usage "${name}" "$(bootstrap-row "${name}" | cut -d'|' -f3)")"
        actions="$(cli-actions "${COMMAND_ACTIONS[${name}]}")"
        expect-contains "${usage}" "${name} [${actions// /|}]" "the overview of ${name} lists its actions, the default first"
        for action in ${actions}; do
            declare -F "native-${name}-${action}" >/dev/null || err "${name} ${action} is listed without a native-${name}-${action} function"
        done
        [[ "$(declare -f "native-${name}")" == *"native-dispatch ${name} "* ]] || err "native-${name} must dispatch through the action table"
    done

}
