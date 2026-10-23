ssh-command () {

    local host="${CONFIG[SSH_HOST]:-}" user="${CONFIG[SSH_USER]:-}" port="${CONFIG[SSH_PORT]:-22}" method="${CONFIG[SSH_METHOD]:-auto}"
    local key="" certificate="" known="" descriptor="" status=0
    local -a arguments=()

    [[ "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9.:-]*$ ]] || { err "Invalid SSH_HOST"; return; }
    [[ "${user}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]] || { err "Invalid SSH_USER"; return; }
    parse-port "${port}" || { err "Invalid SSH_PORT"; return; }
    [[ "${method}" =~ ^(auto|agent|key|certificate|password)$ ]] || { err "Unsupported SSH_METHOD: ${method}"; return; }
    need ssh || return

    key="$(ssh-material SSH_KEY)" || return
    certificate="$(ssh-material SSH_CERTIFICATE)" || return
    known="$(ssh-material SSH_KNOWN_HOSTS)" || return

    if [[ "${method}" == auto ]]; then
        if [[ -n "${CONFIG[SSH_PASSWORD]:-}" ]]; then method=password
        elif [[ -n "${certificate}" ]]; then method=certificate
        elif [[ -n "${key}" ]]; then method=key
        else method=agent
        fi
    fi

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
    esac

    [[ "${method}" == password ]] || { ssh "${arguments[@]}" -- "${user}@${host}" "$@"; return; }

    exec {descriptor}<<< "${CONFIG[SSH_PASSWORD]}"
    sshpass -d "${descriptor}" ssh "${arguments[@]}" -- "${user}@${host}" "$@" || status=$?
    exec {descriptor}<&-

    return "${status}"

}
ssh-material () {

    local name="${1}" value="${CONFIG[${1}]:-}" file="${TOOL_TEMP:-${TMPDIR:-/tmp}}/ssh-${1,,}"

    [[ -n "${value}" ]] || return 0

    if [[ "${value}" != *$'\n'* && "${value}" != *' '* && "${value}" =~ ^[/.~] ]]; then
        value="${value/#\~/${HOME}}"
        [[ -f "${value}" ]] || { err "${name} file not found: ${value}"; return; }
        out "${value}"
        return 0
    fi

    [[ -s "${file}" ]] || parse-content "${value}" | fs-write "${file}" 600 || { err "Cannot materialize ${name}"; return; }

    out "${file}"

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
ssh-job-script () {

    cat <<'JOB'
set -uo pipefail
umask 077
action=$1
directory=$2
jobs=$3
id=$4
shift 4
[[ "$id" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ && "$jobs" != /* && "/$jobs/" != */../* ]] || exit 65
cd -- "$HOME" && cd -- "$directory" || exit 66
base=$jobs/$id
case $action in
    start)
        mkdir -p -- "$jobs" && chmod 700 "./$jobs" || exit 73
        find "$jobs" -type f -mtime +14 -delete 2>/dev/null
        ( set -o noclobber; : > "$base.claim" ) 2>/dev/null || exit 65
        while IFS= read -r -d '' pair; do export "$pair"; done
        : > "$base.out"
        : > "$base.err"
        launcher=(nohup)
        ! command -v setsid >/dev/null || launcher=(setsid nohup)
        "${launcher[@]}" bash -c './infra "${@:2}" > "$1.out" 2> "$1.err" < /dev/null; printf "%s\n" "$?" > "$1.next"; mv -f -- "$1.next" "$1.status"' infra-job "$base" "$@" > /dev/null 2>&1 < /dev/null &
        printf '%s\n' "$!" > "$base.pid"
        ;;
    follow|status)
        [[ -f "$base.pid" ]] || { [[ ! -f "$base.claim" ]] || exit 68; exit 66; }
        ;;
    *)
        exit 64
        ;;
esac
running () {
    [[ ! -f "$base.status" ]] && kill -0 "$(cat -- "$base.pid")" 2>/dev/null
}
if [[ "$action" == status ]]; then
    [[ ! -f "$base.status" ]] || { cat -- "$base.status"; exit 0; }
    running && exit 75
    [[ ! -f "$base.status" ]] || { cat -- "$base.status"; exit 0; }
    exit 69
fi
sent=0
noted=0
while :; do
    finished=false
    lost=false
    if [[ -f "$base.status" ]]; then finished=true
    elif ! running && [[ ! -f "$base.status" ]]; then lost=true
    fi
    size=$(wc -c < "$base.out")
    (( size <= sent )) || { tail -c "+$(( sent + 1 ))" -- "$base.out" | head -c "$(( size - sent ))"; sent=$size; }
    size=$(wc -c < "$base.err")
    (( size <= noted )) || { tail -c "+$(( noted + 1 ))" -- "$base.err" | head -c "$(( size - noted ))" >&2; noted=$size; }
    ! $finished || exit "$(cat -- "$base.status")"
    ! $lost || { printf 'Remote job %s ended without a status\n' "$id" >&2; exit 70; }
    sleep 1
done
JOB

}
ssh-job () {

    local script=""

    script="$(ssh-job-script)" || return

    ssh-run bash -c "${script}" infra-job "$@"

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
