git-ref () {

    [[ "${1:-}" =~ ^[A-Za-z0-9_][A-Za-z0-9_./-]{0,254}$ && "${1}" != *..* && "${1}" != *.lock && "${1}" != */ ]]

}
git-checkout () {

    local url="${1}" ref="${2}" destination="${3}" username="${4}" credential="${5}" vault=""

    [[ "${url}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/[A-Za-z0-9_./~-]+$ ]] || { err "HTTPS repository URL without credentials required"; return; }
    git-ref "${ref}" || { err "Invalid Git reference: ${ref}"; return; }
    net-safe "${username}" || { err "Git username must be a single line"; return; }
    net-safe "${credential}" || { err "Git credential must be a single line"; return; }
    need git || return

    vault="$(fs-temp)" || return

    (
        trap 'rm -rf -- "${vault}"' EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM

        printf '%s\n' "${username}" | fs-write "${vault}/username" || exit
        printf '%s\n' "${credential}" | fs-write "${vault}/credential" || exit
        printf '%s\n' '#!/bin/sh' 'case "$1" in *sername*) exec cat "$INFRA_GIT_VAULT/username" ;; *) exec cat "$INFRA_GIT_VAULT/credential" ;; esac' |
            fs-write "${vault}/askpass" 700 || exit

        run-timeout 300 env -u GIT_DIR -u GIT_WORK_TREE -u GIT_ASKPASS -u SSH_ASKPASS \
            GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
            GIT_ASKPASS="${vault}/askpass" INFRA_GIT_VAULT="${vault}" \
            git -c credential.helper= -c core.hooksPath=/dev/null -c protocol.file.allow=never \
                -c protocol.ext.allow=never -c http.followRedirects=false \
                -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 \
                clone --quiet --no-checkout --depth 1 --single-branch --branch "${ref}" -- "${url}" "${destination}"
    )

}
git-file () {

    local root="${1}" commit="${2}" path="${3}"

    [[ "${commit}" =~ ^[a-f0-9]{40}$ ]] || { err "Full commit identifier required"; return; }
    fs-relative "${path}" || { err "Repository-relative path required: ${path}"; return; }

    git -C "${root}" show "${commit}:${path}"

}
