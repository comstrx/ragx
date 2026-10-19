test-operations-topology () {

    fixture-release
    expect-equal "$(native-services)" api
    expect-equal "$(native-routes)" "api|api.shop.test|${CONFIG[API_PORT]}|/health|leastconn|200"

    fixture-web
    expect-equal "$(native-services | tr '\n' ' ')" 'api web-admin web-client '
    expect-equal "$(native-replicas web-client)" 3
    expect-equal "$(native-replicas web-admin)" 2
    expect-equal "$(native-replicas api)" 2
    expect-equal "$(native-variable client-one)" WEB_CLIENT_ONE_REPLICAS
    expect-equal "$(native-service-image web-admin)" "example/admin@$(fixture-digest 3)"
    expect-equal "$(native-hosts | tr '\n' ' ')" 'api.shop.test admin.shop.test shop.test '
    expect-contains "$(native-routes)" "web-client|shop.test|${CONFIG[WEB_PORT]}|/|roundrobin|200-399"

    mkdir -p "${CONFIG[STATE_ROOT]}"
    state-write "${CONFIG[STATE_ROOT]}" slot-green r1
    expect-contains "$(native-interpolation r1)" DEPLOY_SLOT=green
    expect-contains "$(native-interpolation r1)" "RELEASE_ROOT=${CONFIG[STATE_ROOT]}/releases/r1"
    expect-contains "$(native-interpolation r1)" WEB_CLIENT_REPLICAS=3
    expect-contains "$(native-interpolation r9)" DEPLOY_SLOT=blue

}
test-operations-backup-retention () {

    local root="${CONFIG[STATE_ROOT]}/backups" name=""

    mkdir -p "${root}"
    cfg-set BACKUP_DAYS 1

    for name in old latest recent; do
        printf '%s\n' "${name}" > "${root}/${name}.dump"
        printf 'sum\n' > "${root}/${name}.dump.sha256"
    done

    printf 'keep\n' > "${root}/unrelated"
    touch -t 200001010000 "${root}/old.dump" "${root}/latest.dump"
    state-write "${root}" latest latest.dump

    native-backup-prune

    expect-fail test -e "${root}/old.dump"
    expect-fail test -e "${root}/old.dump.sha256"
    expect-equal "$(fs-read "${root}/latest.dump")" latest
    expect-equal "$(fs-read "${root}/recent.dump")" recent
    expect-equal "$(fs-read "${root}/unrelated")" keep

}
test-operations-guards () {

    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp 443/udp '
    cfg-set HTTP3_ENABLED false
    expect-equal "$(native-firewall-ports | tr '\n' ' ')" '80/tcp 443/tcp '
    expect-equal "$(native-protocols)" 'http/1.1 h2'

    expect-error 'repeat with --force' native-firewall-apply
    expect-error 'Repeat with --force' native-uninstall
    expect-error 'recover --force removes a dead lock' native-recover
    expect-error 'Install timers from the staged release bundle' native-timer-install backup 3600
    expect-error 'Usage: timer install' native-timer-install shell 60
    expect-error 'Usage: restore BACKUP_FILE NEW_DATABASE' native-restore one
    expect-error 'Unknown command: drop' native-tls drop
    expect-error 'Usage: image build api|web TAG [SPEC]' native-image-build other example/x:1
    expect-error 'Image builds need the monorepo checkout' native-image-build api example/api:1

    cfg-set PROJECT shop
    cfg-set REGISTRY_NAMESPACE org
    expect-equal "$(native-registry-reference api 1.0.0)" ghcr.io/org/shop-api:1.0.0
    cfg-set REGISTRY_DRIVER dockerhub
    expect-equal "$(native-registry-host)" docker.io
    expect-error 'Image outside docker.io/org' native-registry-push ghcr.io/org/shop-api:1

}
