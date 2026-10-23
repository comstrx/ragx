launchd-domain () {

    if launchctl print "gui/${EUID}" >/dev/null 2>&1; then out "gui/${EUID}"
    else out "user/${EUID}"
    fi

}
launchd-timer () {

    local name="${1}" directory="${2}" root="${3}" interval="${4}" domain="" file="${HOME}/Library/LaunchAgents/io.infra.${1}.plist" argument=""
    local program=""

    shift 4
    [[ "${name}" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || { err "Invalid agent name: ${name}"; return; }
    parse-positive "${interval}" || { err "Invalid timer interval: ${interval}"; return; }
    need-all launchctl plutil || return

    for argument in "$@"; do
        program+="        <string>$(parse-xml-string "${argument}")</string>"$'\n'
    done

    cfg-set PLIST_LABEL "io.infra.${name}"
    cfg-set PLIST_ROOT "$(parse-xml-string "${root}")"
    cfg-set PLIST_ARGUMENTS "${program%$'\n'}"
    cfg-set PLIST_INTERVAL "${interval}"

    template-render "${MANIFEST[paths.templates]}/native/launchd.plist" "${directory}/${name}.plist" || return
    plutil -lint "${directory}/${name}.plist" >/dev/null || { err "Invalid property list: ${name}"; return; }
    fs-copy "${directory}/${name}.plist" "${file}" || return

    domain="$(launchd-domain)"
    ! launchctl print "${domain}/io.infra.${name}" >/dev/null 2>&1 || launchctl bootout "${domain}/io.infra.${name}" || return
    launchctl bootstrap "${domain}" "${file}" || { err "Agent activation failed: ${name}"; return; }

}
launchd-remove () {

    ! launchd-present "${1}" || launchctl bootout "$(launchd-domain)/io.infra.${1}" || { err "Agent stop failed: ${1}"; return; }
    rm -f -- "${HOME}/Library/LaunchAgents/io.infra.${1}.plist"

}
launchd-list () {

    has launchctl || { err "Timers need launchd"; return; }
    launchctl list | awk -v prefix="io.infra.${1}-" 'index($3, prefix) == 1'

}
launchd-present () {

    has launchctl && launchctl print "$(launchd-domain)/io.infra.${1}" >/dev/null 2>&1

}
