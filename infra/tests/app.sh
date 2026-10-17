#!/usr/bin/env bash

test_app_run_needs_a_command () {

    assert_fails "an empty app run is refused" bash -c "source '${INFRA_BIN}'; app_run --"

}
test_the_bundle_knows_when_it_stands_on_the_box () {

    local bin=""

    bin="$(dirname -- "${INFRA_BIN}")"

    assert_ok "no box named — the verbs act here" env SSH_HOST= SERVER_PATH=/opt/x/infra bash -c "source '${INFRA_BIN}'; server_here"
    assert_fails "a box named and the bundle elsewhere — the verbs travel" env SSH_HOST=203.0.113.10 SERVER_PATH=/opt/x/infra bash -c "source '${INFRA_BIN}'; server_here"
    assert_ok "a box named and the bundle on it — the verbs act here" env SSH_HOST=203.0.113.10 SERVER_PATH="${bin}" bash -c "source '${INFRA_BIN}'; server_here"

}
test_server_path_stays_under_an_allowed_root () {

    assert_ok "a dedicated directory under /opt is allowed" env SERVER_PATH=/opt/probe/infra SERVER_ALLOWED_ROOTS='/opt /srv /home' bash -c "source '${INFRA_BIN}'; server_path"
    assert_fails "a root itself is refused" env SERVER_PATH=/opt SERVER_ALLOWED_ROOTS='/opt /srv /home' bash -c "source '${INFRA_BIN}'; server_path"
    assert_fails "a foreign root is refused" env SERVER_PATH=/etc/probe/infra SERVER_ALLOWED_ROOTS='/opt /srv /home' bash -c "source '${INFRA_BIN}'; server_path"

}
