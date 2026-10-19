if [[ "${TOOL_BUNDLED:-false}" != true ]]; then

    TOOL_SOURCE="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)"
    TOOL_ROOT="${TOOL_SOURCE%/*}"
    TOOL_BIN="${TOOL_SOURCE}/main.sh"
    TOOL_BUILD=dev

    source "${TOOL_SOURCE}/core/load.sh" || return

fi

source-include core/log.sh || return
source-include core/ui.sh || return
source-include core/sys.sh || return
source-include core/parse.sh || return
source-include core/fs.sh || return
source-include core/config.sh || return
source-include core/cli.sh || return
source-include core/asset.sh || return
source-include core/template.sh || return
source-include core/state.sh || return
source-include core/net.sh || return
source-include core/git.sh || return
source-include core/ssh.sh || return
source-include core/package.sh || return
source-include core/bundle.sh || return
source-include core/test.sh || return
source-include config/index.sh || return
source-include bootstrap/build.sh || return
source-include bootstrap/check.sh || return
source-include bootstrap/laws.sh || return
source-include bootstrap/test.sh || return
source-include bootstrap/cli.sh || return
