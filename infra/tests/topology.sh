#!/usr/bin/env bash

test_the_charts_carry_the_production_topology () {

    local file="" dir=""

    file="$(mktemp)"

    printf 'STACK=light\nPROJECT=topo\n' > "${file}"

    dir="$("${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"

    assert_contains "$(cat "${dir}/helm/service/templates/deployment.yaml")" 'startupProbe' "the web pod starts behind a startup probe"
    assert_contains "$(cat "${dir}/helm/service/templates/deployment.yaml")" 'preStop' "a pod with a port drains before it stops"
    assert_contains "$(cat "${dir}/helm/service/values.yaml")" 'grep -q work /proc/1/cmdline' "the worker answers a liveness probe without procps"
    assert_contains "$(cat "${dir}/helm/service/values.yaml")" 'grep -q schedule /proc/1/cmdline' "the scheduler answers a liveness probe without procps"
    assert_contains "$(cat "${dir}/helm/service/templates/runbook.yaml")" 'argocd.argoproj.io/hook: PostSync' "the genome is projected after every sync"
    assert_contains "$(cat "${dir}/helm/service/templates/networkpolicy.yaml")" '169.254.169.254/32' "the app pods never reach the instance metadata"
    assert_contains "$(cat "${dir}/helm/platform/templates/redis.yaml")" '--maxmemory-policy noeviction' "redis is capped and refuses instead of evicting"
    assert_contains "$(cat "${dir}/helm/platform/templates/postgresql.yaml")" 'priorityClassName' "postgres is scheduled before the app"
    assert_contains "$(cat "${dir}/argocd/project.yaml")" 'kind: PriorityClass' "the project admits the cluster-scoped priority class the platform chart emits"
    assert_contains "$(cat "${dir}/helm/values/api.tpl")" 'APP_WORKERS' "the worker count is a stack knob"
    assert_contains "$(cat "${dir}/helm/values/api.tpl")" 'TRUST_PROXIES' "the trusted proxies are the edge network"
    assert_contains "$(cat "${dir}/tofu/aws/stacks/light/main.tf")" 'module "keys"' "the light stack mints scoped keys per job"
    assert_eq "$(grep -c 'storage_bucket_arn = ""' "${dir}/tofu/aws/stacks/light/main.tf")" "1" "the node role keeps only the registry"
    assert_contains "$(cat "${dir}/argocd/root.yaml")" 'repoURL: ${INFRA_REPO_URL}' "argocd reads the forge itself, never the application repo"
    assert_contains "$(cat "${dir}/argocd/root.yaml")" 'path: infra/src/template/argocd/apps' "the app-of-apps is the forge's own chart"
    assert_contains "$(cat "${dir}/argocd/project.yaml")" '- ${INFRA_REPO_URL}' "the project admits the forge as a source — a root that names a repo the project refuses is an InvalidSpecError"
    assert_eq "$(grep -c 'GIT_REPO_URL' "${dir}/argocd/project.yaml" "${dir}/argocd/root.yaml" | awk -F: '{s+=$2} END {print s}')" "0" "argocd never names the application repository"
    assert_contains "$(cat "${dir}/argocd/root.yaml")" '${SERVICE_VALUES}' "the release rides the root as values, never a commit"
    assert_eq "$(grep -c 'valueFiles' "${dir}/argocd/apps/templates/api.yaml")" "0" "the service application carries its values, not a file in a repo"
    assert_fails "the forge vendors nothing into an application repo" bash -c "source '${INFRA_BIN}'; declare -F helm_vendor"
    assert_fails "the forge commits no topology bump" bash -c "source '${INFRA_BIN}'; declare -F ci_bump"

    rm -f "${file}"

}
test_the_edge_counts_every_client_on_its_own_bucket () {

    local file="" dir="" rules=""

    file="$(mktemp)"

    printf 'STACK=light\nPROJECT=edge\n' > "${file}"

    dir="$("${INFRA_BIN}" --config "${file}" ci setting TEMPLATE_DIR)"
    rules="$(cat "${dir}/helm/gateway/templates/ratelimit.yaml")"

    assert_contains "${rules}" 'type: Distinct' "every client address spends its own bucket"
    assert_contains "${rules}" 'list "0.0.0.0/0" "::/0"' "both address families are counted"
    assert_eq "$(grep -c -- '- limit:' <<< "${rules}")" "0" "no rule opens without a selector — a bare rule is one bucket for the whole world"
    assert_contains "$(cat "${dir}/helm/gateway/templates/client.yaml")" '{{- if .Values.trustedCidrs }}' "a forwarded address is believed only behind a shield somebody named"
    assert_contains "$(cat "${dir}/argocd/root.yaml")" 'edgeTrustedCidrs: ${EDGE_TRUSTED_JSON}' "the shield rides the root as values"
    assert_eq "$(EDGE_TRUSTED_CIDRS='' bash -c "source '${INFRA_BIN}'; argocd_trusted")" "[]" "no shield, no trusted network"
    assert_eq "$(EDGE_TRUSTED_CIDRS='173.245.48.0/20,2400:cb00::/32' bash -c "source '${INFRA_BIN}'; argocd_trusted")" '["173.245.48.0/20","2400:cb00::/32"]' "the shield's networks reach the edge as a list"
    assert_contains "$(bash -c "source '${INFRA_BIN}'; declare -f helm_seed")" '${EDGE_TRUSTED_CIDRS:+,${EDGE_TRUSTED_CIDRS}}' "the app skips the very networks the edge trusts"

    rm -f "${file}"

}
