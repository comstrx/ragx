test-parse-env-literals () {

    local file="${TMPDIR}/literal.env" value=""
    local -A parsed=()

    printf '%s\n' 'PLAIN=value' 'EMPTY=' "QUOTED=''" "MULTI='line one" "line two'" 'COMMAND="$(touch /tmp/infra-never)"' \
        '  SPACED  =  padded  ' "ESCAPED='it\\'s'" 'TABS="a\tb"' '# comment' '' > "${file}"
    parse-pairs parsed "${file}"

    expect-equal "${parsed[PLAIN]}" value
    expect-equal "${parsed[EMPTY]}" ''
    expect-equal "${parsed[QUOTED]}" ''
    expect-equal "${parsed[MULTI]}" $'line one\nline two'
    expect-equal "${parsed[COMMAND]}" '$(touch /tmp/infra-never)'
    expect-equal "${parsed[SPACED]}" padded
    expect-equal "${parsed[ESCAPED]}" "it's"
    expect-equal "${parsed[TABS]}" $'a\tb'
    expect-fail test -e /tmp/infra-never

    for value in "a'b\\c \$ dollar"$'\n'"second" "ends with \\" "quote ' and \" double" '$HOME ${PATH} `id`' $'\ttab' ''; do
        printf 'VALUE=%s\n' "$(parse-env-string "${value}")" > "${file}"
        parsed=()
        parse-pairs parsed "${file}"
        expect-equal "${parsed[VALUE]}" "${value}" 'env round trip'
    done

}
test-parse-env-refusals () {

    local file="${TMPDIR}/bad.env"
    local -A parsed=()

    printf '%s\n' 'NAME=one' 'NAME=two' > "${file}"
    expect-error 'Duplicate setting: NAME' parse-pairs parsed "${file}"

    printf '%s\n' 'NAME="unfinished' > "${file}"
    expect-error 'Unterminated value: NAME' parse-pairs parsed "${file}"

    printf '%s\n' 'lower=value' > "${file}"
    expect-error 'Invalid key' parse-pairs parsed "${file}"

    printf '%s\n' 'NAME=value # trailing' > "${file}"
    expect-error 'Invalid value for NAME' parse-pairs parsed "${file}"

    printf 'NAME=before\000after\n' > "${file}"
    expect-error 'NUL bytes are forbidden' parse-pairs parsed "${file}"

    head -c 1048577 /dev/zero | tr '\0' 'a' > "${file}"
    expect-error 'exceeds 1 MiB' parse-pairs parsed "${file}"

    ln -s "${file}" "${TMPDIR}/link.env"
    expect-error 'Regular file required' parse-pairs parsed "${TMPDIR}/link.env"
    expect-equal "${#parsed[@]}" 0

}
test-parse-manifest () {

    local file="${TMPDIR}/Bash.toml"
    local -A parsed=()

    printf '%s\n' 'name = "tool"' 'count = 3' 'enabled = true' '[paths]' 'entry = "src/main.sh"' "raw = 'C:\\path'" 'cmd = "$(false)"' > "${file}"
    parse-pairs parsed "${file}" toml

    expect-equal "${parsed[name]}" tool
    expect-equal "${parsed[count]}" 3
    expect-equal "${parsed[enabled]}" true
    expect-equal "${parsed[paths.entry]}" src/main.sh
    expect-equal "${parsed[paths.raw]}" 'C:\path'
    expect-equal "${parsed[paths.cmd]}" '$(false)'

    printf '%s\n' 'list = [1, 2]' > "${file}"
    expect-error 'Unsupported manifest value type' parse-pairs parsed "${file}" toml

}
test-parse-grammars () {

    local image="" digest=""

    digest="sha256:$(printf '%064d' 7)"

    for image in postgres postgres:18 "postgres:18@${digest}" ghcr.io/org/app:1.2.3 "localhost:5000/team/app@${digest}" \
        registry.example.com:443/a/b/c:tag_1 docker.io/library/redis:8.4-alpine; do
        parse-image "${image}" || err "Expected a valid image: ${image}"
    done

    for image in 'repo/image:tag; echo' UPPER/case 'a@@b' 'image:' '/leading' 'trailing/' 'a//b' "image@sha256:short" 'a b'; do
        expect-fail parse-image "${image}"
    done

    parse-pinned "ghcr.io/org/app@${digest}"
    expect-fail parse-pinned ghcr.io/org/app:latest

    parse-host api.example.com
    parse-host a
    expect-fail parse-host -bad.example.com
    expect-fail parse-host bad-.example.com
    expect-fail parse-host 'bad..example'
    expect-fail parse-host Upper.example.com
    expect-fail parse-host "$(printf 'a%.0s' {1..64}).com"

    parse-address 0.0.0.0
    parse-address 255.255.255.255
    expect-fail parse-address 256.0.0.1
    expect-fail parse-address 1.2.3
    parse-cidr 173.245.48.0/20
    parse-cidr 2400:cb00::/32
    parse-cidr 0.0.0.0/0
    expect-fail parse-cidr 173.245.48.0
    expect-fail parse-cidr 256.0.0.0/8
    expect-fail parse-cidr 10.0.0.0/33
    expect-fail parse-cidr 2400:cb00::/129
    expect-fail parse-cidr 'bad;range/8'

    parse-port 65535
    expect-fail parse-port 65536
    expect-fail parse-port 0
    expect-fail parse-port 08080

    parse-path /v1/health
    expect-fail parse-path '/health;false'
    expect-fail parse-path '/../etc'
    expect-fail parse-path relative

    expect-equal "$(parse-url-component "space ' \$ /@:é")" 'space%20%27%20%24%20%2F%40%3A%C3%A9'
    expect-equal "$(parse-json-string $'q"b\\n\nt\t')" '"q\"b\\n\nt\t"'

}
test-parse-map () {

    local -A mapped=()

    parse-map mapped 'client=repo/client:1,admin=repo/admin:2'
    expect-equal "${mapped[client]}" repo/client:1
    expect-equal "${mapped[admin]}" repo/admin:2

    expect-error 'Duplicate map key: client' parse-map mapped 'client=a,client=b'
    expect-error 'Invalid map key' parse-map mapped '../escape=a'
    expect-error 'Empty map value: client' parse-map mapped 'client='
    expect-error 'Expected key=value' parse-map mapped 'client'

    parse-map mapped ''
    expect-equal "${#mapped[@]}" 0

}
test-parse-content () {

    local text=$'APP_ENV=production\nKEY="a b"\nLONG=0123456789012345678901234567890123456789012345678901234567890123456789'

    expect-equal "$(parse-content "$(printf '%s\n' "${text}" | openssl base64 -A)")" "${text}" 'one base64 line decodes'
    expect-equal "$(parse-content "${text}")" "${text}" 'plain text passes through'
    expect-equal "$(parse-content APP_ENV=production)" APP_ENV=production
    expect-equal "$(parse-content "$(printf 'bin\000ary' | openssl base64 -A)")" "$(printf 'bin\000ary' | openssl base64 -A)" 'binary is never decoded'
    expect-equal "$(parse-content abc)" abc
    expect-equal "$(parse-content "$(printf '%s\n' "${text}" | openssl base64)")" "$(printf '%s\n' "${text}" | openssl base64)" 'wrapped base64 is not one line'

}
