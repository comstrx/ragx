#!/usr/bin/env bash

## the application — one-off commands on the release, the same image, env and secrets the api runs with

## run one bootstrap command on the release — migrate, rollback, status, seed, runbook, check — or any argv after --
app_run () {

    [[ "${1:-}" != "--" ]] || shift

    (( $# )) || die "Usage: app run -- <command...>"

    server_here || { server_forward app run -- "$@"; return; }

    compose_cmd run --rm --no-deps api "$@"

}
## apply the pending migrations on the live database
app_migrate () {

    app_run migrate

}
## the migration status of the live database
app_status () {

    app_run status

}
## the operational facts of the release — routes, channels, schedule, queues, config with secrets redacted
app_runbook () {

    app_run runbook

}
## a shell inside the running api container
app_shell () {

    server_here || { server_forward app shell; return; }

    compose_cmd exec api sh

}
