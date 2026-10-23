firewall-apply () {

    local port=""

    is-linux || { err "Host firewall management requires Linux"; return; }
    (( $# > 0 )) || { err "Ports required"; return; }

    if has firewall-cmd && firewall-cmd --state >/dev/null 2>&1; then

        for port in "$@"; do
            run-sudo firewall-cmd --permanent "--add-port=${port}" || return
            run-sudo firewall-cmd "--add-port=${port}" || return
        done

        return 0

    fi

    if has ufw && run-sudo ufw status 2>/dev/null | grep -q '^Status: active'; then

        for port in "$@"; do
            run-sudo ufw allow "${port}" || return
        done

        return 0

    fi

    err "No active ufw or firewalld; allow the ports with the host or cloud firewall"

}
