fixture-tree () {

    local root="${1}"

    mkdir -p "${root}/src/bootstrap" "${root}/src/core" "${root}/src/template" "${root}/specs"
    printf 'name = "fixture"\n' > "${root}/Bash.toml"
    printf 'PUBLIC=safe\n' > "${root}/.env.example"
    printf 'SECRET=bundle-sentinel\n' > "${root}/.env.local"
    printf 'asset\n' > "${root}/src/template/value"
    printf '%s\n' 'declare -gi LOADED="${LOADED:-0}"' 'LOADED+=1' > "${root}/src/core/once.sh"
    printf 'exit 99\n' > "${root}/src/core/unused.sh"
    printf '%s\n' 'err () { printf "%s\n" "$*" >&2; return 1; }' 'out () { printf "%s\n" "$@"; }' \
        'source-include core/once.sh || return' 'source-include core/once.sh || return' \
        'fixture () { printf "%s %s %s\n" "${TOOL_BUILD}" "${LOADED}" "$(source-list core | tr "\n" " ")"; }' > "${root}/src/bootstrap/index.sh"
    printf '%s\n' '#!/usr/bin/env bash' 'set -Eeuo pipefail' 'source ignored' 'fixture "$@"' > "${root}/src/main.sh"
    printf 'test-fixture () { :; }\n' > "${root}/specs/example.sh"

}
test-bundle-deterministic () {

    local root="${TMPDIR}/tree" first="" second="" text=""

    fixture-tree "${root}"
    bundle-create "${root}" "${root}/out/one" release src specs src/template src/main.sh bootstrap/index.sh
    bundle-create "${root}" "${root}/out/two" release src specs src/template src/main.sh bootstrap/index.sh

    first="$(fs-hash "${root}/out/one")"
    second="$(fs-hash "${root}/out/two")"
    expect-equal "${first}" "${second}" 'identical inputs give identical bundles'
    expect-equal "$(bash "${root}/out/one")" 'release 1 core/once.sh core/unused.sh '

    text="$(fs-read "${root}/out/one")"
    expect-absent "${text}" bundle-sentinel
    expect-absent "${text}" test-fixture
    expect-contains "${text}" "'src/template/value') cat <<'ASSET_"

    bundle-create "${root}" "${root}/out/dev" dev src specs src/template src/main.sh bootstrap/index.sh
    expect-contains "$(fs-read "${root}/out/dev")" test-fixture
    expect-equal "$(fs-mode "${root}/out/dev")" 755

    printf 'broken (\n' > "${root}/src/core/broken.sh"
    expect-error 'Bundle syntax check failed' bundle-create "${root}" "${root}/out/one" release src specs src/template src/main.sh bootstrap/index.sh
    expect-equal "$(fs-hash "${root}/out/one")" "${first}" 'failed builds keep the previous bundle'

}
test-bundle-loader () {

    expect-error 'Invalid source path' source-include ../outside.sh
    expect-error 'Invalid source path' source-include core/Upper.sh
    expect-error 'Missing source: module/absent.sh' source-include module/absent.sh
    expect-equal "${SOURCE_STATE[module/absent.sh]:-}" ''
    expect-equal "${SOURCE_STATE[module/haproxy.sh]}" loaded
    expect-contains "$(source-list app/native)" app/native/deploy.sh
    expect-absent "$(source-list app)" app/native/deploy.sh
    expect-contains "$(asset-text Bash.toml)" 'stack = "native"'
    expect-error 'Missing asset: secret.env' asset-text secret.env

}
test-bundle-release-isolation () {

    expect-error 'Unknown test: out' bash "${TOOL_BIN}" --project "${TMPDIR}" __test out
    expect-error 'Unknown test: test-cli-parse;' bash "${TOOL_BIN}" --project "${TMPDIR}" __test 'test-cli-parse; out unsafe'

    TOOL_BUILD=release
    expect-error 'Release bundles exclude tests' bootstrap-isolate test-cli-parse
    expect-error 'Release bundles exclude tests' bootstrap-test

}
test-laws-enforced () {

    local root="${TMPDIR}/laws" output=""

    mkdir -p "${root}/src/core" "${root}/src/module" "${root}/src/app/native" "${root}/src/deep/nest" "${root}/tests"
    printf '%s\n' 'core-good () {' '' '    out ok' '' '}' > "${root}/src/core/good.sh"
    printf '%s\n' 'core-bad () {' '    # comment' '    native-deploy' "    return $(( 60 + 5 ))" '}' > "${root}/src/core/bad.sh"
    printf '%s\n' 'redis-call () {' '' '    haproxy-render x' '' '}' > "${root}/src/module/redis.sh"
    printf '%s\n' 'haproxy-render () {' '' '    docker-pull x' '' '}' > "${root}/src/module/haproxy.sh"
    printf '%s\n' 'docker-pull () {' '' '    out x' '' '}' > "${root}/src/module/docker.sh"
    printf '%s\n' 'native-deploy () {' '' '    haproxy-render x' '' '}' 'function legacy() {' '' '    :' '' '}' > "${root}/src/app/native/deploy.sh"
    printf '%s\n' 'wrong-name () {' '' $'\ttabbed' '' '' '}' > "${root}/src/module/web.sh"
    printf 'x\n' > "${root}/src/deep/nest/file.sh"
    printf '%s\n' 'helper () {' '' '    :' '' '}' > "${root}/tests/helper.sh"

    TOOL_SOURCE="${root}/src"
    TOOL_ROOT="${root}"
    MANIFEST[paths.tests]=tests
    output="$(bootstrap-laws 2>&1)" && err "Violations were accepted"

    expect-contains "${output}" 'core/bad.sh:2: comments are forbidden'
    expect-contains "${output}" 'core/bad.sh:3: core cannot call native-deploy'
    expect-contains "${output}" 'core/bad.sh:4: manual status codes are forbidden'
    expect-contains "${output}" 'core/bad.sh:2: blank line required after the opening'
    expect-contains "${output}" 'core/bad.sh:5: blank line required before the closing'
    expect-contains "${output}" 'module:redis.sh cannot call haproxy-render'
    expect-contains "${output}" "functions are written as 'name () {'"
    expect-contains "${output}" 'wrong-name must start with web-'
    expect-contains "${output}" 'tabs are forbidden'
    expect-contains "${output}" 'consecutive blank lines'
    expect-contains "${output}" 'Source outside the layered layout: deep/nest/file.sh'
    expect-contains "${output}" 'helper must start with test- or fixture-'
    expect-absent "${output}" 'module:haproxy.sh cannot call docker-pull'
    expect-absent "${output}" 'app:native/deploy.sh cannot call haproxy-render'
    expect-absent "${output}" 'core/good.sh'

}
