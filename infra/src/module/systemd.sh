systemd-timer () {

    local name="${1}" directory="${2}" root="${3}" execution="${4}" interval="${5}" target="${HOME}/.config/systemd/user"

    [[ "${name}" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || { err "Invalid unit name: ${name}"; return; }
    parse-positive "${interval}" || { err "Invalid timer interval: ${interval}"; return; }
    need systemctl || return

    cfg-set UNIT_NAME "${name}"
    cfg-set UNIT_DIRECTORY "${root}"
    cfg-set UNIT_COMMAND "${execution}"
    cfg-set UNIT_INTERVAL "${interval}"

    template-render "${MANIFEST[paths.templates]}/native/service.unit" "${directory}/${name}.service" || return
    template-render "${MANIFEST[paths.templates]}/native/timer.unit" "${directory}/${name}.timer" || return
    fs-copy "${directory}/${name}.service" "${target}/${name}.service" || return
    fs-copy "${directory}/${name}.timer" "${target}/${name}.timer" || return

    systemctl --user daemon-reload || { err "systemd user manager unavailable"; return; }
    systemctl --user enable --now "${name}.timer" || { err "Timer activation failed: ${name}"; return; }

}
systemd-stop () {

    systemctl --user disable --now "${1}.timer" || { err "Timer stop failed: ${1}"; return; }

}
