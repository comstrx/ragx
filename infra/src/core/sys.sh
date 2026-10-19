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
is-gui () {

    if is-linux; then
        [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]
        return
    fi

    is-macos || return 1
    [[ -z "${SSH_CONNECTION:-}${SSH_TTY:-}" ]] || return 1

    has launchctl && launchctl print "gui/${EUID}" >/dev/null 2>&1

}
is-headless () {

    ! is-gui

}

ci-name () {

    is-true "${GITHUB_ACTIONS:-}"          && { out github;    return; }
    is-true "${GITLAB_CI:-}"               && { out gitlab;    return; }
    is-true "${TF_BUILD:-}"                && { out azure;     return; }
    is-true "${CIRCLECI:-}"                && { out circleci;  return; }
    is-true "${TRAVIS:-}"                  && { out travis;    return; }
    is-true "${BUILDKITE:-}"               && { out buildkite; return; }
    is-true "${DRONE:-}"                   && { out drone;     return; }
    [[ -n "${JENKINS_URL:-}" ]]            && { out jenkins;   return; }
    [[ -n "${TEAMCITY_VERSION:-}" ]]       && { out teamcity;  return; }
    [[ -n "${BITBUCKET_BUILD_NUMBER:-}" ]] && { out bitbucket; return; }
    [[ -n "${CODEBUILD_BUILD_ID:-}" ]]     && { out codebuild; return; }
    is-true "${CI:-}"                      && { out generic;   return; }

    return 1

}
is-ci () {

    ci-name >/dev/null

}
is-ci-pull () {

    local provider=""

    provider="$(ci-name)" || return 1

    case "${provider}" in
        github)    [[ "${GITHUB_EVENT_NAME:-}" == pull_request || "${GITHUB_EVENT_NAME:-}" == pull_request_target ]] ;;
        gitlab)    [[ "${CI_PIPELINE_SOURCE:-}" == merge_request_event ]] ;;
        azure)     [[ "${BUILD_REASON:-}" == PullRequest ]] ;;
        bitbucket) [[ -n "${BITBUCKET_PR_ID:-}" ]] ;;
        circleci)  [[ -n "${CIRCLE_PULL_REQUEST:-}" ]] ;;
        travis)    [[ -n "${TRAVIS_PULL_REQUEST:-}" && "${TRAVIS_PULL_REQUEST}" != false ]] ;;
        buildkite) [[ -n "${BUILDKITE_PULL_REQUEST:-}" && "${BUILDKITE_PULL_REQUEST}" != false ]] ;;
        jenkins)   [[ -n "${CHANGE_ID:-}" ]] ;;
        drone)     [[ "${DRONE_BUILD_EVENT:-}" == pull_request ]] ;;
        *)         return 1 ;;
    esac

}
is-ci-tag () {

    local provider=""

    provider="$(ci-name)" || return 1
    is-ci-pull && return 1

    case "${provider}" in
        github)    [[ "${GITHUB_REF_TYPE:-}" == tag ]] ;;
        gitlab)    [[ -n "${CI_COMMIT_TAG:-}" ]] ;;
        azure)     [[ "${BUILD_SOURCEBRANCH:-}" == refs/tags/* ]] ;;
        bitbucket) [[ -n "${BITBUCKET_TAG:-}" ]] ;;
        circleci)  [[ -n "${CIRCLE_TAG:-}" ]] ;;
        travis)    [[ -n "${TRAVIS_TAG:-}" ]] ;;
        buildkite) [[ -n "${BUILDKITE_TAG:-}" ]] ;;
        drone)     [[ "${DRONE_BUILD_EVENT:-}" == tag ]] ;;
        *)         return 1 ;;
    esac

}
is-ci-push () {

    local provider=""

    provider="$(ci-name)" || return 1
    is-ci-pull && return 1
    is-ci-tag  && return 1

    case "${provider}" in
        github)    [[ "${GITHUB_EVENT_NAME:-}" == push ]] ;;
        gitlab)    [[ "${CI_PIPELINE_SOURCE:-}" == push ]] ;;
        azure)     [[ "${BUILD_REASON:-}" == IndividualCI || "${BUILD_REASON:-}" == BatchedCI ]] ;;
        bitbucket) [[ -n "${BITBUCKET_COMMIT:-}" ]] ;;
        drone)     [[ "${DRONE_BUILD_EVENT:-}" == push ]] ;;
        *)         return 1 ;;
    esac

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
