ssh-command () {

    local host="${CONFIG[SSH_HOST]:-}" user="${CONFIG[SSH_USER]:-}" port="${CONFIG[SSH_PORT]:-22}" method="${CONFIG[SSH_METHOD]:-agent}"
    local key="${CONFIG[SSH_KEY]:-}" certificate="${CONFIG[SSH_CERTIFICATE]:-}" known="${CONFIG[SSH_KNOWN_HOSTS]:-}"
    local descriptor="" status=0
    local -a arguments=()

    [[ "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9.:-]*$ ]] || { err "Invalid SSH_HOST"; return; }
    [[ "${user}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]] || { err "Invalid SSH_USER"; return; }
    parse-port "${port}" || { err "Invalid SSH_PORT"; return; }
    need ssh || return

    arguments=(
        -T -p "${port}"
        -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2
        -o ForwardAgent=no -o ForwardX11=no -o ClearAllForwardings=yes -o LogLevel=ERROR
    )
    [[ -z "${known}" ]] || arguments+=( -o "UserKnownHostsFile=${known}" )

    case "${method}" in
        agent)
            arguments+=( -o BatchMode=yes )
        ;;
        key|certificate)
            [[ -f "${key}" ]] || { err "SSH_KEY must name a private key file"; return; }
            arguments+=( -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -i "${key}" )

            if [[ "${method}" == certificate ]]; then
                [[ -f "${certificate}" ]] || { err "SSH_CERTIFICATE must name a certificate file"; return; }
                arguments+=( -o "CertificateFile=${certificate}" )
            fi
        ;;
        password)
            need sshpass || return
            [[ -n "${CONFIG[SSH_PASSWORD]:-}" ]] || { err "Missing setting: SSH_PASSWORD"; return; }
            arguments+=( -o BatchMode=no -o 'PreferredAuthentications=password,keyboard-interactive' -o PubkeyAuthentication=no )
        ;;
        *)
            err "Unsupported SSH_METHOD: ${method}"
            return
        ;;
    esac

    [[ "${method}" == password ]] || { ssh "${arguments[@]}" -- "${user}@${host}" "$@"; return; }

    exec {descriptor}<<< "${CONFIG[SSH_PASSWORD]}"
    sshpass -d "${descriptor}" ssh "${arguments[@]}" -- "${user}@${host}" "$@" || status=$?
    exec {descriptor}<&-

    return "${status}"

}
ssh-encode () {

    local argument="" invocation="exec"

    (( $# > 0 )) || { err "Remote command required"; return; }

    for argument in "$@"; do
        invocation+=" '${argument//\'/\'\"\'\"\'}'"
    done

    out "${invocation}"

}
ssh-run () {

    local invocation=""

    invocation="$(ssh-encode "$@")" || return

    ssh-command "${invocation}"

}
ssh-ready () {

    ssh-run bash -c 'test "${BASH_VERSINFO[0]}" -ge 5 && id -u && uname -s && command -v docker'

}
ssh-upload-script () {

    cat <<'UPLOAD'
set -euo pipefail
umask 077
cd -- "$HOME"
path=$1
mode=$2
expected=$3
walked=.
IFS=/ read -r -a parts <<< "$path"
for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != . && "$part" != .. ]] || exit 65
    walked+="/$part"
    [[ ! -L "$walked" ]] || exit 65
done
parent=${path%/*}
[[ "$parent" != "$path" ]] || parent=.
mkdir -p -- "$parent"
temporary=$(mktemp "${path}.XXXXXXXX")
trap 'rm -f -- "$temporary"' EXIT
cat > "$temporary"
if command -v sha256sum >/dev/null; then actual=$(sha256sum -- "$temporary")
else actual=$(shasum -a 256 -- "$temporary")
fi
[[ "${actual%% *}" == "$expected" ]] || exit 65
chmod "$mode" "$temporary"
mv -f -- "$temporary" "$path"
UPLOAD

}
ssh-upload () {

    local source="${1}" destination="${2}" mode="${3:-600}" checksum="" script=""

    [[ "${mode}" == 600 || "${mode}" == 700 ]] || { err "Upload mode must be 600 or 700"; return; }
    fs-relative "${destination}" || { err "Use a relative path below the SSH home: ${destination}"; return; }
    [[ -f "${source}" && ! -L "${source}" ]] || { err "Regular file required: ${source}"; return; }

    checksum="$(fs-hash "${source}")" || return
    script="$(ssh-upload-script)" || return

    ssh-run bash -c "${script}" infra-upload "${destination}" "${mode}" "${checksum}" < "${source}" || { err "Upload failed: ${destination}"; return; }

}
