#!/usr/bin/env bash

test_every_verb_a_chain_calls_exists () {

    local chain="" verb="" missing=""

    for chain in ci_release server_ensure server_refresh server_deploy server_bootstrap k8s_bootstrap argocd_bootstrap k8s_rotate; do

        while IFS= read -r verb; do

            [[ -n "$(bash -c "source '${INFRA_BIN}'; type -t '${verb}'")" ]] || missing+=" ${chain}→${verb}"

        done < <(bash -c "source '${INFRA_BIN}'; declare -f ${chain}" | grep -oE '^\s+[a-z_]+;?$' | tr -d ' ;')

    done

    assert_eq "${missing}" "" "every verb a chain calls is defined — a chain that names a ghost dies on the runner:${missing}"

}
