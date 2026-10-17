#!/usr/bin/env bash

test_cli_lists_every_module () {

    local listing="" name=""

    listing="$("${INFRA_BIN}" -l)"

    for name in app audit backup ci compose dns edge pg secrets self server tool; do

        assert_contains "${listing}" "  ${name} — " "module ${name} is listed"

    done

    assert_eq "$(grep -c '  argocd — \|  helm — \|  k8s — \|  tofu — \|  aws — ' <<< "${listing}")" "0" "the kubernetes era left no module behind"

}
test_cli_refuses_the_unknown () {

    assert_fails "an unknown module is refused" "${INFRA_BIN}" -s production nothing here
    assert_fails "an unknown option is refused" "${INFRA_BIN}" --nothing
    assert_fails "a missing config file is refused" "${INFRA_BIN}" --config /nonexistent ci setting STACK
    assert_fails "an unknown stack is refused" "${INFRA_BIN}" -s moon ci setting STACK

}
test_help_names_a_command () {

    assert_contains "$("${INFRA_BIN}" help ci setting)" "print one resolved setting" "help reaches a single command"
    assert_contains "$("${INFRA_BIN}" help server)" "deploy" "help lists a module's commands"
    assert_contains "$("${INFRA_BIN}" help compose)" "roll" "the stack module rolls releases"
    assert_contains "$("${INFRA_BIN}" --version)" "${INFRA_VERSION}" "the version is the one the forge stamped"

}
