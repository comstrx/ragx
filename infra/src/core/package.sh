package-capabilities () {

    case "${1:-}" in
        apt|apk|dnf|yum|pacman|zypper|xbps|brew|port) out 'install remove refresh' ;;
        nix)                                          out 'install remove' ;;
        *)                                            err "Unknown package manager: ${1:-}"; return ;;
    esac

}
package-capability () {

    local capabilities=""

    capabilities="$(package-capabilities "${1:-}" 2>/dev/null)" || return 1

    [[ " ${capabilities} " == *" ${2:-} "* ]]

}
package-call () {

    local manager="${1:-}" action="${2:-}" package=""
    local -a command=()

    shift 2
    package-capability "${manager}" "${action}" || { err "Unsupported package operation: ${manager} ${action}"; return; }

    for package in "$@"; do
        [[ "${package}" =~ ^[A-Za-z0-9][A-Za-z0-9@+._:/=-]*$ ]] || { err "Invalid package name: ${package}"; return; }
    done

    case "${manager}:${action}" in
        apt:install)    command=( apt-get install -y -- ) ;;
        apt:remove)     command=( apt-get remove -y -- ) ;;
        apt:refresh)    command=( apt-get update ) ;;
        apk:install)    command=( apk add -- ) ;;
        apk:remove)     command=( apk del -- ) ;;
        apk:refresh)    command=( apk update ) ;;
        dnf:install)    command=( dnf install -y -- ) ;;
        dnf:remove)     command=( dnf remove -y -- ) ;;
        dnf:refresh)    command=( dnf makecache ) ;;
        yum:install)    command=( yum install -y -- ) ;;
        yum:remove)     command=( yum remove -y -- ) ;;
        yum:refresh)    command=( yum makecache ) ;;
        pacman:install) command=( pacman -S --needed --noconfirm -- ) ;;
        pacman:remove)  command=( pacman -R --noconfirm -- ) ;;
        pacman:refresh) command=( pacman -Sy --noconfirm ) ;;
        zypper:install) command=( zypper --non-interactive install -- ) ;;
        zypper:remove)  command=( zypper --non-interactive remove -- ) ;;
        zypper:refresh) command=( zypper refresh ) ;;
        xbps:install)   command=( xbps-install -y -- ) ;;
        xbps:remove)    command=( xbps-remove -y -- ) ;;
        xbps:refresh)   command=( xbps-install -S ) ;;
        brew:install)   command=( brew install -- ) ;;
        brew:remove)    command=( brew uninstall -- ) ;;
        brew:refresh)   command=( brew update ) ;;
        port:install)   command=( port install ) ;;
        port:remove)    command=( port uninstall ) ;;
        port:refresh)   command=( port selfupdate ) ;;
        nix:install)    command=( nix profile install ) ;;
        nix:remove)     command=( nix profile remove ) ;;
    esac

    case "${manager}" in
        brew|nix) run-cmd "${command[@]}" "$@" ;;
        *)        run-sudo "${command[@]}" "$@" ;;
    esac

}
package-artifact () {

    local url="${1}" checksum="${2}" entry="${3}" destination="${4}" archive="" status=0

    fs-relative "${entry}" || { err "Archive entry must be relative: ${entry}"; return; }
    need tar || return

    archive="$(fs-temp-file)" || return

    if net-download "${url}" "${archive}" "${checksum}"; then fs-produce "${destination}" 755 tar -xOf "${archive}" "${entry}" || status=$?
    else status=$?
    fi

    rm -f -- "${archive}"
    return "${status}"

}
