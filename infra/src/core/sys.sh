declare -g SYS_KERNEL="" SYS_DISTRO="" SYS_MANAGER=""

is-true () {

    case "${1,,}" in
        1|true|yes|on) return 0 ;;
    esac

    return 1

}
has () {

    [[ -n "${1:-}" && "${1}" != -* ]] || return 1

    command -v -- "${1}" >/dev/null 2>&1

}
need () {

    has "${1:-}" || { err "Missing tool: ${1:-unnamed}"; return; }

}
has-all () {

    local tool=""

    for tool in "$@"; do
        has "${tool}" || return 1
    done

    return 0

}
need-all () {

    local tool="" failed=0

    for tool in "$@"; do
        need "${tool}" || failed=1
    done

    (( failed == 0 ))

}

is-linux () {

    [[ "${OSTYPE:-}" == linux* ]]

}
is-macos () {

    [[ "${OSTYPE:-}" == darwin* ]]

}
is-unix () {

    is-linux || is-macos

}
is-posix () {

    is-unix

}
kernel () {

    [[ -n "${SYS_KERNEL}" ]] || SYS_KERNEL="$(uname -s 2>/dev/null)" || { err "Kernel detection failed"; return; }

    out "${SYS_KERNEL}"

}
runtime () {

    local release=""

    is-macos && { out macos; return; }
    is-linux || { out unsupported; return 1; }

    [[ -z "${WSL_DISTRO_NAME:-}${WSL_INTEROP:-}" ]] || { out wsl; return; }
    [[ ! -r /proc/sys/kernel/osrelease ]] || IFS= read -r release < /proc/sys/kernel/osrelease || release=""
    [[ "${release,,}" != *microsoft* ]] || is-container || { out wsl; return; }

    out linux

}
os () {

    is-linux && { out linux; return; }
    is-macos && { out macos; return; }

    err "Unsupported operating system: ${OSTYPE:-unknown}"

}
distro () {

    local file="" line="" value="" open=false

    is-macos && { out macos; return; }
    is-linux || { err "Unsupported operating system: ${OSTYPE:-unknown}"; return; }
    [[ -z "${SYS_DISTRO}" ]] || { out "${SYS_DISTRO}"; return; }

    for file in /etc/os-release /usr/lib/os-release; do

        [[ -r "${file}" ]] || continue

        while IFS= read -r line; do
            [[ "${line}" == ID=* ]] || continue
            parse-string value "${line#ID=}" env open || { err "Invalid distribution identity: ${file}"; return; }
            SYS_DISTRO="${value,,}"
            out "${SYS_DISTRO}"
            return
        done < "${file}"

    done

    SYS_DISTRO=linux
    out "${SYS_DISTRO}"

}
manager () {

    local system="" tool=""
    local -a candidates=()

    [[ -z "${SYS_MANAGER}" ]] || { out "${SYS_MANAGER}"; return; }
    system="$(distro)" || return

    case "${system}" in
        macos)                              candidates=( brew port nix ) ;;
        ubuntu|debian|linuxmint|pop)        candidates=( apt brew nix ) ;;
        alpine)                             candidates=( apk brew nix ) ;;
        fedora|rhel|rocky|almalinux|centos) candidates=( dnf yum brew nix ) ;;
        arch|manjaro|endeavouros)           candidates=( pacman brew nix ) ;;
        opensuse*|sles)                     candidates=( zypper brew nix ) ;;
        void)                               candidates=( xbps brew nix ) ;;
        nixos)                              candidates=( nix ) ;;
        *)                                  candidates=( apt apk dnf yum pacman zypper xbps brew nix ) ;;
    esac

    for tool in "${candidates[@]}"; do

        case "${tool}" in
            apt)  has apt-get      || continue ;;
            xbps) has xbps-install || continue ;;
            *)    has "${tool}"    || continue ;;
        esac

        SYS_MANAGER="${tool}"
        out "${SYS_MANAGER}"
        return

    done

    err "No supported package manager on ${system}"

}

is-container () {

    [[ -f /.dockerenv || -f /run/.containerenv || -s /run/systemd/container ]]

}
is-terminal () {

    [[ -t 0 || -t 1 || -t 2 ]]

}
is-interactive () {

    [[ "$-" == *i* ]]

}
is-root () {

    (( EUID == 0 ))

}

run-cmd () {

    (( $# > 0 )) || { err "Command required"; return; }

    "$@"

}
run-ok () {

    run-cmd "$@" >/dev/null 2>&1

}
run-sudo () {

    (( $# > 0 )) || { err "Command required"; return; }
    is-root && { "$@"; return; }

    need sudo || return
    sudo -n -- "$@" || { err "Noninteractive sudo permission required for: ${1}"; return; }

}
run-sudo-ok () {

    run-sudo "$@" >/dev/null 2>&1

}
run-retry () {

    local attempts="${1:-}" delay="${2:-}" attempt=1

    shift 2
    [[ "${attempts}" =~ ^[1-9][0-9]?$ && "${delay}" =~ ^[0-9]+$ ]] || { err "Invalid retry policy: ${attempts}/${delay}"; return; }
    (( $# > 0 )) || { err "Command required"; return; }

    until "$@"; do
        (( attempt < attempts )) || return 1
        warn "Attempt ${attempt} of ${attempts} failed; retrying in $(( delay * attempt ))s"
        sleep "$(( delay * attempt ))"
        attempt=$(( attempt + 1 ))
    done

}
run-until () {

    local seconds="${1:-}" interval="${2:-}" started="${SECONDS}"

    shift 2
    [[ "${seconds}" =~ ^[0-9]+$ && "${interval}" =~ ^[1-9][0-9]*$ ]] || { err "Invalid wait window: ${seconds}/${interval}"; return; }
    (( $# > 0 )) || { err "Command required"; return; }

    until run-ok "$@"; do
        (( SECONDS - started < seconds )) || return 1
        sleep "${interval}"
    done

}
run-timeout () {

    local seconds="${1:-}" child=0 watcher=0 status=0 started="${SECONDS}"

    shift
    [[ "${seconds}" =~ ^[1-9][0-9]*$ ]] || { err "Invalid timeout: ${seconds}"; return; }
    (( $# > 0 )) || { err "Command required"; return; }

    "$@" 0<&0 &
    child=$!

    (
        trap 'kill "${sleeper}" 2>/dev/null; exit 0' TERM
        sleep "${seconds}" &
        sleeper=$!
        wait "${sleeper}" && kill -TERM "${child}" 2>/dev/null
    ) >/dev/null 2>&1 &
    watcher=$!

    wait "${child}" || status=$?
    kill -TERM "${watcher}" 2>/dev/null || true
    wait "${watcher}" 2>/dev/null || true

    (( status == 0 || SECONDS - started < seconds )) || err "Timed out after ${seconds}s: ${1}"

    return "${status}"

}
