# Infrastructure

The infrastructure is a Bash 5 framework delivered as one self-contained executable. Its current stack is `native`: Docker Engine and Compose with a persistent HAProxy edge and a Portainer CE control plane. Kubernetes, Helm, Argo CD, Kustomize and OpenTofu are future stacks added through `module/`, `template/` and a new `app/<stack>/` folder only.

## Layout and layers

| Path                 | Owns                                                                                                                                                                                                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Bash.toml`          | Identity, `stack`, paths (`entrypoint source build tests templates cache`), tool versions, the runtime commands the tool needs (`[requires]`), image digests, check policy, endpoints, download and package checksums: build constants that change only with the code. |
| `.env.example`       | The one environment schema: every key with its default, in owner blocks, each under one short comment line and a blank line; `.env.production` and `.env.local` repeat its keys, order and comments with their own values.                                             |
| `src/main.sh`        | Strict mode, then `bootstrap/index.sh`, then `bootstrap-main`.                                                                                                                                                                                                         |
| `src/bootstrap/`     | The only entry. Loads core and config, assembles `app/<stack>/*.sh` from the manifest's stack, owns governance (`help build build-release checksum prepare check test run config`) and the laws.                                                                       |
| `src/core/`          | Generic verbs, biased to no stack: `log ui sys parse fs config cli asset template state net git ssh package bundle test load`.                                                                                                                                         |
| `src/config/`        | `index.sh`, the schema load, precedence, validation, derivation and release snapshots.                                                                                                                                                                                 |
| `src/module/`        | One file per tool: `docker haproxy portainer registry postgresql rabbitmq redis tls cloudflare s3 gitops systemd launchd firewall monitoring telegram slack webhook`.                                                                                                  |
| `src/app/native/`    | Orchestration of the native stack, one domain per file: `commands` (the command manual), `topology render deploy control scale edge backup gitops observe notify inspect server images host network`.                                                                  |
| `src/template/`      | `native/` Compose, HAProxy, unit and plist templates, `native/monitor/` Prometheus, Alertmanager and Grafana; `image/` Dockerfiles.                                                                                                                                    |
| `tests/`, `benches/` | Offline tests discovered by name; the HTTP/3 client image, the protocol bench and the lab evidence.                                                                                                                                                                    |

Laws enforced by `check` on every source and test file:

- Layer calls: core calls core; config calls core; a module calls core and the `docker` runtime module only; app calls core, config, modules and its own stack; bootstrap calls core, config and bootstrap. A tool combining two others belongs in app.
- Names: `module/<tool>.sh` defines `<tool>-*`, `app/<stack>/` defines `<stack>-*`, config `config-*`, bootstrap `bootstrap-*`, tests `test-*` or `fixture-*`. A function is defined once.
- Style: `name () {`, a blank line after the opening and before the closing brace, no consecutive blank lines, four-space indentation, no tabs, no trailing spaces, zero comments.
- Errors: `err "message"` prints `[-]` on stderr, redacted, and returns 1; callers write `|| return`. No manual status codes outside signal traps.
- Layout: flat `core config bootstrap module`, one folder per stack under `app/`.

## Runtime and core

Linux and macOS with Bash 5.2/5.3. OS predicates read `OSTYPE` without forks; kernel, distribution and package manager are detected once and cached. The package table covers apt, apk, dnf, yum, pacman, zypper, xbps, brew, port and nix, and declares unsupported actions, such as nix refresh. `run-sudo` uses `sudo -n` and never prompts. `run-timeout` is portable, keeps stdin and reports the timeout. `run-until` polls with a deadline and `run-retry` retries with a growing pause.

SSH supports agent, key, certificate and password authentication with `-T`, `StrictHostKeyChecking=yes` and forwarding disabled, so a `restrict` authorized key works. `SSH_METHOD=auto` (the default) picks password, certificate, key, then agent from what is set. `SSH_KEY`, `SSH_CERTIFICATE` and `SSH_KNOWN_HOSTS` take a path or the content itself, plain or one base64 line; content lands in a mode-600 file inside the session directory. Passwords travel through an `sshpass -d` descriptor, and remote arguments are single-quote encoded. Uploads are checksum-verified, atomic and refuse symlinks. Tokens never enter argv:

- HTTP credentials reach curl through `--config -` on stdin, and every curl call starts with `--disable`, so a user `~/.curlrc` can never weaken TLS or redirect a request.
- Webhook signatures are HMAC-SHA256 computed with Bash builtins and `od`, so the signing secret never reaches a process argument.
- Git credentials reach git through a temporary askpass vault.
- Backup keys reach the pinned `aws-cli` container as `--env NAME` from a subshell, never as values in argv.
- Registry passwords use `--password-stdin`.

`server run` starts the remote command as a detached job (`setsid nohup`), with its output, pid and exit status under `<paths.cache>/jobs/` (mode 700, pruned after 14 days). It streams the output and, when the connection drops, asks for the job's status and follows it again, up to ten times six seconds apart, replaying the log. The command's own exit status is returned, so a network drop never interrupts a deploy, its verify window or its automatic rollback.

Writes are atomic, through a staging file and `mv`. A failed producer leaves the destination untouched. All temporary files live in a per-run session directory that is removed on exit.

Retries sit where a transient failure would otherwise fail an operation, and only where repeating is safe:

- image pulls and registry logins: three attempts, 5 and 10 seconds apart;
- image pushes: three attempts, 20 and 40 seconds apart, which covers GHCR granting a brand-new package to the repository after its first push;
- `server stage` uploads: three attempts (they are atomic and checksum-verified);
- a `server run` start lost before the job existed: started again up to three times; a connection lost after the start follows the job instead of starting it twice;
- HTTPS reads (`GET`, downloads): curl `--retry 3 --retry-connrefused`; writes to remote APIs are never repeated blindly;
- offsite backups: aws-cli standard retry mode with five attempts, which never repeats an authentication failure;
- notifications: `NOTIFY_RETRIES`.

The release bundle embeds every source and asset byte for byte: an asset without a final newline keeps it missing, and a test compares each embedded asset with its file. `Bash.toml` is read by a strict TOML subset: dotted tables declared once, bare lowercase keys, basic and literal strings, integers without leading zeros, booleans and trailing comments; anything else is refused with its line.

## Configuration

Resolution order: `.env.example` defaults, then the env file(s), then the process environment, then `-e KEY=VALUE`. Explicit CLI input wins, the order Docker Compose and Terraform document. File selection works as follows:

- Development picks `.env.local`, otherwise `.env`.
- A release bundle picks `.env.production`, then `.env.prod`, then `.env`.
- `ENV_FILE`, the content itself (plain or one base64 line), replaces the files; this is how CI hands over the infrastructure env.
- `--config FILE` repeated replaces both, in order.

Unknown keys fail the whole load atomically. Values are data, never sourced or evaluated. Multiline values, quotes, `$` and backslashes round-trip.

`ENV_MODE` is fixed by the build: release means production, which requires TLS and the pinned Docker and Compose versions. There is no deployment environment setting: the infrastructure targets one server, and a second copy on the same host is a second `PROJECT`. `--target` chooses `SSH_HOST`. Derived values:

- `STACK`, plus every `Bash.toml` image as `IMAGE_*`. A collision with the schema is an error.
- `RELEASE`, when empty, as `<VERSION>-<revision>`: the revision is the first 8 hex digits of the SHA-256 over every pinned release setting except the name, the env file digests included. A release name therefore always means the same images and settings: a rotated secret under the same tag is a new release deployed through blue/green without rebuilding images, and returning to the old settings computes the retained release's name and switches back in seconds. An explicit `RELEASE` pins a name instead.
- `COMPOSE_PROJECT=<project>`, `STATE_ROOT=<project root>/<paths.cache>/<project>`, and `BACKUP_ROOT`, which is `BACKUP_DIR` or `<state root>/backups`.
- `WEB_ENABLED`, `API_URL` and `GRAFANA_URL`, with default ports omitted.

The environment controls everything a deployment may change: replicas, strategy, domains, health paths, ports, balance per service type, timeouts, warmup, drain, retention, the verify window, timer intervals, metrics retention, PostgreSQL extensions, memory, CPU and connection limits, data-service credentials, integrations and the application runtime contract. `Bash.toml` keeps only what changes with the code, so changing it means a new bundle.

Validation reports every invalid key at once. The rules:

- Ports, counts and paths must be well formed.
- Images, `API_IMAGE` and every `WEB_IMAGES` entry must be pinned by digest. Host names follow RFC 1123.
- Web specs, hosts and replica maps must agree.
- `DB_USER` must not be `postgres`. Production requires TLS. `HTTP3_ENABLED=true` requires `TLS_ENABLED=true`, the only HTTP/3 rule.
- Operator inputs that reach commands or mounts are checked as data: `TLS_EMAIL` an address, `HEALTH_CA` and `PORTAINER_CA` absolute paths (a comma could otherwise add mount options), `GITOPS_BRANCH` a Git reference, `BACKUP_REGION` a region name, `REGISTRY_NAMESPACE` a registry namespace, `SSH_HOST` and `SSH_USER` the forms SSH accepts, and `REMOTE_DIR` a path relative to the SSH home.
- Every integration is all-or-none: a partial offsite backup, DNS, trusted proxy, Telegram, Grafana, registry or GitOps group names its missing keys. GitOps without a permanent `REGISTRY_TOKEN` warns, because the server pulls private images itself. Rates read `REQUESTS/PERIOD` with `s`, `m` or `h`; path limits must not nest; a host is routed once.
- `TLS_CHALLENGE=dns` and `DNS_PROXIED=true` require `DNS_PROVIDER`. `DNS_PROXIED=true` warns, never blocks, with origin HTTP/3 (the provider terminates public QUIC) and without `TRUSTED_HEADER` (the edge would see the provider's addresses). `TRUSTED_PROXIES` takes CIDRs and https URLs only, `TRUSTED_HEADER` a header name.
- Forced and role variables are `NAME=VALUE` words, the three role commands are required, `MIGRATION_POLICY=expand` requires `API_MIGRATE_COMMAND`, mounts are absolute, GitOps paths are relative and distinct, and extensions are identifiers.
- Deploys require the data-service credentials, each password at least 16 characters. The application validates its own env file when it migrates and boots, before any switch.

### Application env files

Each part owns one env file and nothing crosses: `infra/.env.production` holds every infrastructure control, `api/.env.production` is a complete copy of `api/.env` with production values, and the values both sides need (database, broker and cache credentials, the port) are repeated on purpose. The infrastructure never reads, writes or validates a key inside an application file; it receives the file, pins it, and mounts it.

- **Source.** `API_ENV_FILE` (required) and `WEB_ENV_FILE` (optional) carry each file's content, plain or one base64 line. The content comes from that exported, non-empty variable, otherwise from `.env.api` or `.env.web` beside the infrastructure env file, which `server stage` writes with mode 600. A missing API file fails the deploy; a missing web file means the web specs run without one.
- **Checks.** At most 48 KiB, no NUL, no carriage return, not blank. Nothing else, because a dotenv line check would refuse values `python-dotenv` accepts.
- **Release.** The content is copied once into `releases/<release>/api.env` (`web.env`), mode 644 inside the 700 release directory so the non-root container can read it, and its SHA-256 is pinned as `API_ENV_SHA256` (`WEB_ENV_SHA256`) in `release.env`. A changed file gives a new release name (or is refused under a pinned `RELEASE`), and a rollback mounts the file of the release it restores.
- **Mount.** A read-only bind to `API_ENV_MOUNT` (`WEB_ENV_MOUNT`), default `/app/.env`, which the API loads as its own base `.env`. Values never pass through Compose `env_file`, so `$` and quotes keep their dotenv meaning and secrets stay out of `docker inspect` and Portainer.
- **Runtime contract.** The facts the infrastructure owns reach the containers as process variables, which outrank the file: `API_FORCED_ENV` (bind address, port, storage root, migrations off), the per-role `API_SERVE_ENV`, `API_WORK_ENV` and `API_SCHEDULE_ENV`, `API_RELEASE_VARIABLE=<release>` and `WEB_FORCED_ENV`. The role commands (`API_SERVE_COMMAND`, `API_WORK_COMMAND`, `API_SCHEDULE_COMMAND`, `API_MIGRATE_COMMAND`) and `API_STORAGE_MOUNT` are settings too, words split on spaces and `$` escaped for Compose. Emptying the forced variables leaves a pure pass-through.
- **Web builds.** `WEB_SPEC_VARIABLE` and `WEB_API_VARIABLE` name the build-time variables that receive the spec and `API_URL`; public values are compiled in, so a web runtime file serves server-side code only.

## Command line

`infra help` groups every command by purpose (Release, Data, Operate, Edge and certificates, Server and runtime, GitOps and control plane, Images, Tool) with its usage and one line. `infra help COMMAND`, or `COMMAND --help`, prints the full manual: what it does, its actions, its flags in one aligned column, where it runs, notes (gates, notifications, timers) and examples. Headings are bold and command columns colored on a terminal, plain otherwise or with `NO_COLOR`. The manual lives as data in `app/native/commands.sh`, and a test proves every listed command has a function and every manual entry names a command.

Commands with actions (`backup edge tls dns firewall server docker timer portainer image registry`) declare them once in `COMMAND_ACTIONS`, the default first. The dispatch, the overview usage (`backup [create|list|verify] [BACKUP]`) and the manual's Actions section all read that table, so the help cannot drift from what the code accepts, and a test proves every action has its function. A mistyped action names the closest one and the alternatives (`Unknown backup action: lst; did you mean list? (expected create, list or verify)`), and a routed command checks its action here before opening an SSH connection.

- Global flags: `--config FILE` (repeatable), `--project DIR`, `--target HOST`, `-e KEY=VALUE` (repeatable), `--local`, `-h/--help`, `--version`.
- Command flags are declared per command and checked before anything runs: `deploy --list` fails with `deploy does not take --list; see infra help deploy`. A flag declared with a value (`--token TOKEN`) takes `--token X` or `--token=X`. Flags after `--` belong to the remote command of `server run`.
- Server commands (`deploy rollback recover backup restore status doctor scale start stop uninstall monitor edge tls firewall timer reconcile watch portainer`) run on `SSH_HOST` when it is set: the arguments and flags travel to a detached `server run` job, the server reads its staged settings, and `-e` overrides travel with that one command over SSH stdin (never `SSH_*` or `REMOTE_*`, never argv), so `infra -e API_REPLICAS=4 scale` scales the server. `deploy` first stages the bundle, the settings and the application env files and applies the edge; `deploy --dry-run` stages nothing. `--local` runs any of them here. On the server the staged settings carry no `SSH_*`, so the same command runs locally there. CI therefore needs only `ENV_FILE`, `API_ENV_FILE` and the `SSH_*` variables to call `infra deploy`, `rollback`, `restore` or `backup`.
- A mistyped command suggests the closest one by edit distance (`rolback` → `did you mean rollback?`).
- Commands that interrupt or remove require `--force`: `stop`, `uninstall`, `restore`, `recover` and `firewall apply`.
- `config` prints every setting with its source (`defaults file process cli release gitops derived manifest`), `--changed` keeps only overrides, and secrets print as `[redacted]`.
- `doctor` runs read-only checks (runtime commands from `Bash.toml [requires]`, Docker and Compose versions, settings, env files, disk, edge, certificate, data services, release state, backup age, timers and linger, channels) and prints ✓, ! or ✗ with the next step; a ✗ exits non-zero. On rootless Docker with published ports it warns that RootlessKit's port forwarding shows every client as the network gateway (logs, `RATE_LIMIT_IP` and `TRUSTED_PROXIES` then act on one address) and points at the relay mode; rootful Docker, which `docker install` sets up, keeps client addresses.
- `deploy --dry-run` prints the release name, the live release, the images, the migration policy and the decision the deploy would take, checks edge drift, and changes nothing. The decision comes from the same `native-intent` function the deploy uses, so the plan cannot drift from the run.

## Notifications

One dispatcher (`app/native/notify.sh`) serves every event. A channel is on when its settings exist, and with none configured a notification sends nothing and succeeds:

| Channel  | Settings                                 | Body                                                                                                                  |
| -------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `<emoji> <project>: <text>`                                                                                           |
| Slack    | `SLACK_WEBHOOK_URL`                      | `{"text": "<emoji> <project>: <text>"}`                                                                               |
| Webhook  | `WEBHOOK_URL`, optional `WEBHOOK_SECRET` | `{event, level, project, release, host, time, text}`, signed as `X-Infra-Signature: sha256=<HMAC-SHA256 of the body>` |

`infra notify MESSAGE` takes the same channels from flags: `--channel telegram|slack|webhook` limits the delivery to one, and `--token`/`--chat`, `--hook` and `--url`/`--secret` fill `TELEGRAM_*`, `SLACK_WEBHOOK_URL` and `WEBHOOK_*` for that run through the same dispatcher, validated like settings. Flag values show in process listings, so shared hosts keep them in the environment.

Every delivery is retried `NOTIFY_RETRIES` times (default 2) with a growing pause. An automatic notification never fails the operation that raised it; `infra notify MESSAGE` fails when a configured channel stays unreachable. Webhook URLs are secrets: they never reach argv or output. Events: `deploy.succeeded deploy.switched deploy.rejected deploy.unrecovered verify.rolled-back verify.degraded verify.unrecovered rollback.succeeded rollback.failed backup.succeeded backup.failed restore.succeeded restore.failed monitor.degraded monitor.recovered edge.rolled-back tls.renewal-failed service.started service.stopped service.uninstalled scale.applied notice`; a test proves every event raised in the code is declared. Alertmanager routes the Prometheus alerts to Telegram and Slack; the webhook receives the infrastructure events only, all signed.

## Integrations

Each integration turns on when its settings are present and stays off otherwise; nothing else selects a driver.

| Settings                                                                     | Effect                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BACKUP_URI`, `BACKUP_KEY`, `BACKUP_SECRET`                                  | Every backup and its checksum are also copied to `s3://` (AWS, or `BACKUP_ENDPOINT`) or `gs://` (Google Cloud Storage HMAC keys).                                                                                                                  |
| `DNS_PROVIDER`, `DNS_TOKEN`, `DNS_ZONE`, `DNS_ADDRESS`                       | The provider's driver (`cloudflare` today) upserts every routed host (API, web specs, Grafana) on each edge prepare and apply, leaving current records untouched, and serves `TLS_CHALLENGE=dns`. `DNS_PROXIED=true` asks it to proxy the records. |
| `TRUSTED_PROXIES`, `TRUSTED_HEADER`                                          | A CDN or load balancer in front of the hosts: the edge takes the client from the last address in `TRUSTED_HEADER` only on connections from the listed ranges.                                                                                      |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SLACK_WEBHOOK_URL`, `WEBHOOK_URL` | Each configured channel receives the infrastructure events (see Notifications); Telegram and Slack also receive the Alertmanager alerts.                                                                                                           |
| `GRAFANA_HOST`, `GRAFANA_PASSWORD`                                           | The monitoring stack runs and Grafana is routed through the edge and the certificate.                                                                                                                                                              |
| `RATE_LIMIT_GLOBAL`, `_HOST`, `_IP`, `_PATHS`                                | HAProxy stick-table limits answer `429` with `Retry-After`; ACME challenges are exempt.                                                                                                                                                            |

## Native stack

Projects and boundaries:

- `<project>-data`: PostgreSQL, RabbitMQ and Redis on an internal network, guarded by a fingerprint. Changed data settings need a planned migration.
- `<project>-edge`: HAProxy. The edge and control plane are never recreated by an application deploy.
- `<project>-<release>`: API, worker, scheduler and web specs.
- `<project>-control`: Portainer.
- `<project>-monitor`: Prometheus, Grafana, node and PostgreSQL exporters, and Alertmanager when Telegram or Slack is configured.

Networks and volumes carry an `io.infra.owner` label and are refused when another owner holds the name. Every container runs non-root (data services as uid 999), read-only, with `cap_drop: [ALL]`, `no-new-privileges`, pid and memory limits, `nofile 65536` where sockets matter, and local log rotation. No scalable service has `container_name` or a host port.

The release Compose files interpolate `${API_REPLICAS}`, `${WORKER_REPLICAS}`, `${WEB_<SPEC>_REPLICAS}`, `${DEPLOY_SLOT}` and `${RELEASE_ROOT}` at run time. One rendered release therefore serves native Compose and Portainer, any slot and any replica count, and its snapshot (`release.env`) changes only when application inputs change.

### Edge

HAProxy 3.4.7 LTS (AWS-LC, QUIC) terminates TLS 1.2/1.3 with Mozilla intermediate ciphers, `X25519MLKEM768:X25519:P-256:P-384` curves, no session tickets and strict SNI.

- **HTTP/1.1 and HTTP/2:** run on TCP 443 with ALPN `h2,http/1.1`.
- **HTTP/3:** with `HTTP3_ENABLED=true` (the default), `bind quic4@:8443 … ssl-min-ver TLSv1.3 alpn h3` on the frontend only, `Alt-Svc h3=":<port>"; ma=86400`, and UDP published on the same port. Clients fall back to TCP. Backends stay HTTP/1.1, and 0-RTT is never enabled.
- **Relay mode:** a non-empty `EDGE_SOCKETS` directory replaces the published ports with `unix@/sockets/http.sock` and `https.sock`, `mode 666 accept-proxy`, for a TCP relay (nginx stream with `proxy_protocol on`) that owns `HTTP_PORT` and `HTTPS_PORT`. The PROXY header carries the real client, HTTP/3 and Alt-Svc are off because the relay owns UDP, and the redirect still targets `HTTPS_PORT`. Emptying `EDGE_SOCKETS` returns to published ports with HTTP/3, without another change. The edge runs as uid 1000; `edge apply` and `doctor` prove the directory is writable for it and print the exact `setfacl` grant otherwise (rootless Docker maps uid 1000 to the user's subordinate start + 999). Public probes and the certificate check then speak the PROXY protocol to the socket from a curl container.
- **Trusted proxies:** with `TRUSTED_PROXIES` and `TRUSTED_HEADER`, `http-request set-src req.hdr_ip(<header>,-1)` runs only on connections from the listed ranges, so logs, `X-Forwarded-For` and per-IP limits see the visitor whichever CDN or load balancer is in front (`CF-Connecting-IP`, `True-Client-IP`, `Fastly-Client-IP`, or `X-Forwarded-For`, whose last address is the one the proxy saw). A malformed value keeps the peer address. Lists published at https URLs are fetched by `edge apply`, every CIDR in the body extracted, validated and sorted, and recorded with their source; deploys render from the record and never depend on the network, an unreachable list keeps the record, and a changed source is fetched again. Behind the relay the PROXY header supplies the peer, so both layers compose.
- **Security behavior:** Host allowlist (404 otherwise), 308 HTTP to HTTPS, HSTS two years, overwritten `X-Forwarded-For`, a UUIDv7 `X-Request-ID`, `nosniff`, an `X-Release` header and no `Server` header, set through `http-after-response` so generated responses carry them too.
- **Logs:** JSON log lines record the path without the query string (`%HP`).
- **Discovery:** each service gets `server-template replica 1-32 <service>-<slot>:<port>` through the Docker resolver.
- **Health:** active `GET <path>` checks expect 200 for the API and 200-399 for web front ends. Settings are `inter 2s fall 3 rise 2 slowstart 10s`.
- **Never routing to unready replicas:** `init-state fully-down` keeps a discovered replica out until it passes `rise` checks.
- **Failure handling:** `observe layer7 error-limit 10 on-error mark-down` is the passive circuit. `maxconn`/`maxqueue` per server provide fail-fast back-pressure. `retry-on conn-failure empty-response` with `option redispatch 1` and `timeout connect 1s` handles retries on the local bridge.
- **Timeouts:** `tunnel 1h` for WebSockets, `client-fin` and `server-fin`, and `hard-stop-after 1h` with `expose-fd listeners` for seamless reloads.
- **Rate limits:** `sc0` global, `sc1` per host, `sc2` per client address and `sc3` per path prefix, each in its own stick table sized to twice its period, evaluated after the Host allowlist.
- **Static routes:** Grafana is a single-server backend outside the blue/green slots, so candidate probes never depend on it.
- **Admin surfaces:** the Runtime API listens on 127.0.0.1:9999 inside the container only. Prometheus `/metrics` and `/live` sit on :9090 on the apps network, and on host loopback when `METRICS_ENABLED=true`.

The live map `active.map` selects `slot:release`, switched atomically through the Runtime API and persisted on disk. A candidate frontend (8081/8444, header `X-Slot`) reaches the inactive slot from the apps network only.

### Deploy, rollback and draining

`deploy` validates, locks `STATE_ROOT/lock` and records every phase in `phase` and `audit.log`. The sequence:

1. Preflight edge drift; a changed edge needs `edge apply` first.
2. Retire the inactive slot, but only after `RETENTION_SECONDS` since the active release went live and only when HAProxy reports zero sessions on it within `DRAIN_TIMEOUT`.
3. Render or verify the immutable release.
4. Log in to the registry when `REGISTRY_TOKEN` is set, pull digest-pinned images, log out, check memory and disk capacity, then ensure networks, volumes, data and the `DB_EXTENSIONS` (pgvector) as the local superuser.
5. Migrate with `API_MIGRATE_COMMAND` when `MIGRATION_POLICY=expand`, reading the release's env file. An interrupted migration refuses to rerun.
6. Start the candidate front, wait for healthy containers with the right image, then pass HAProxy readiness and an HTTPS probe through the candidate frontend.
7. Warm up and probe again.
8. Switch the map, move worker and scheduler, and verify the release header on the public port. Without `EXTERNAL_HEALTH_URL` the probe resolves the API host to the local bind address, so it checks the real certificate and SNI without depending on hairpin NAT; set `EXTERNAL_HEALTH_URL` for a check through public DNS.

9. Verify for `VERIFY_SECONDS`: every replica healthy with the right image and the public probe answering, checked every `VERIFY_INTERVAL`. `VERIFY_FAILURES` consecutive failures roll back to the retained previous release automatically, or record `degraded` when none exists.
10. Converge monitoring (a fingerprint recreates it only when its files change, and `GRAFANA_PASSWORD` is reapplied) and install the monitor, backup and renew timers from the release bundle. Neither can fail a live release.

Any failure before the switch restores the origin slot and background services and records `rejected`. An unrecoverable restore records `recovery-required` and keeps the pending state. Every outcome is sent to Telegram when configured, and so is a manual `rollback`: ↩️ when a pending release is rejected or the retained one is live again, 🆘 when it fails.

A release that failed its migration, readiness or verification, or that a rollback left behind, is remembered under `rejected/` with the reason. `deploy` refuses it and `reconcile` skips it until a new release or `deploy --force`. Asking for the retained previous release switches back to it in seconds instead of redeploying it.

`manual` stages without switching until `deploy --force`. Redeploying the current release is idempotent. `rollback` rejects a pending candidate, or switches back to the retained previous release after checking its slot was not reused. `scale` drains replicas above the target in HAProxy, waits for idle, then lets Compose remove them. Data services and the scheduler never scale. `recover --force` removes only a dead-owner lock. Long-lived WebSockets stay on the old slot after a switch, and retirement refuses while they live. Schema rollback is never attempted, so application rollback needs backward-compatible expansion migrations.

### Monitoring

Prometheus scrapes the edge, RabbitMQ, the PostgreSQL exporter, node exporter and itself, and evaluates twelve rules: edge down, no API replica, 5xx share above 2%, slow answers, a queue not draining, broker or database unreachable, disk or memory exhausted, a missing backup, an expiring certificate and a degraded platform. Grafana provisions the Prometheus datasource and the `Platform` dashboard read-only. Exporters and Alertmanager sit on a private network; Prometheus joins apps and data to scrape. Volumes are chowned to the runtime user with copy-up disabled, secrets are mode-600 files mounted one by one, and every container is read-only with all capabilities dropped.

### Backup and restore

`backup` dumps the application database (`pg_dump --format=custom`) into `BACKUP_ROOT`, refuses an archive whose catalog does not read back, writes a SHA-256 beside it, records it as `latest`, copies both to `BACKUP_URI` when set (the pinned `aws-cli` image, `gs://` through the S3-compatible endpoint `storage.googleapis.com`), and removes dumps older than `BACKUP_DAYS` except the latest. The backup timer runs it every `BACKUP_INTERVAL` seconds. Telegram receives 💾 with the name and size, or 🔴 on failure. `backup list` prints the dumps newest first, and `backup verify [BACKUP]` restores one into a scratch database, counts its tables and drops it, proving it restores without touching live data. Only the database is backed up: the edge, certificates, the control plane and releases are recreated by their commands, and the env files live in GitHub secrets.

`restore [BACKUP] --force` takes a dump by name, the latest by default, under the deploy and backup locks:

1. Verify the checksum, then save the live database as a new backup, which becomes the latest.
2. Restore into `<db>_restore_<stamp>`, with the declared extensions created by the superuser first and the extension entries skipped from the dump catalog (only their owner may comment them), as the application role. The live database keeps serving.
3. Stop the worker and scheduler, disallow connections to the live database, end its sessions, rename it to `<db>_before_<stamp>` (connections stay disallowed) and give the restored copy the live name, owner and `CONNECT` grant.
4. Start the worker and scheduler, wait for the public probe, and send ♻️.

A failure before the rename drops the copy and leaves the live database unchanged, and the channels receive 🔴. Running `restore --force` again restores the pre-restore backup, which undoes it. API replicas reconnect by themselves: a lab restore under a health probe every 50 ms lost 4 of 362 probes, and under 600 requests per second the swap failed requests for about 3 seconds while the pools reconnected; the copy itself cost nothing.

`monitor` skips while a deployment holds the lock. It checks replicas, data, the public endpoint, the backup age and the certificate expiry, writes `metrics/platform.prom` for node exporter, and alerts only on a change between healthy and degraded.

### Delivery

Delivery is two workflows. Auto or manual, who may deploy and from which ref are repository policy, kept in the workflows and repository variables; the infrastructure only executes the command it is given:

- **`release.yml`**, on a `v*` tag on main: the gates (global, api, infra, web), then the GitHub release. With `DEPLOY_AUTO=true` its `deploy` job calls `deploy.yml` with the tag, passing the secrets by name; the `production` environment must then admit `v*` tags beside main.
- **`deploy.yml`**, dispatched by hand from main with a tag and `deploy`, `rollback`, `backup` or `restore`, or called by Release: a secret-free `plan` job checks the trigger (a dispatch from main, a call from the tag's own ref), that `github.actor` and `github.triggering_actor` are both in `DEPLOY_ACTORS` (the repository owner by default), the tag and the dump name. The plan also proves the tag is on main. For `deploy`, an `images` job in the `production` environment reads only the project and the API address from `ENV_FILE`, then builds, scans with Trivy and pushes the images with the job token through `infra registry push`, which owns the push retry: the API once per tag, each web spec once per tag and API address because the address is baked into it (an existing reference reuses its digest through `image remote`). It holds no SSH key. The `deploy` job then runs one at a time in the same environment with read-only packages, pins those digests and runs the routed command; `deploy` stages the settings and applies the edge on the server before shipping. A failure posts the run link to every configured channel.

Push or pull follows `GITOPS_URL` in `ENV_FILE`:

- **Push** (empty) keeps no permanent token anywhere: the job's `GITHUB_TOKEN` becomes the registry credential for GHCR, `server stage` never writes credentials that came from the process environment, and `server run` hands them to that one remote command over SSH stdin. A permanent read-only `REGISTRY_TOKEN` in `ENV_FILE` wins instead, for servers that pull by themselves. The application env files travel as `.env.api` and `.env.web`, never inside `.env.production`. Automatic rollback and `rollback` need no token.
- **Pull** keeps a read-only `GITOPS_TOKEN` and a `read:packages` `REGISTRY_TOKEN` on the server, and `GITHUB_TOKEN` fills both for `https://github.com/` repositories and GHCR when they are empty. `publish` commits `deploy/application.yaml` and `deploy/desired.env` to `GITOPS_BRANCH` (a dedicated branch) and tags `release-<RELEASE>` in one atomic push, idempotently; a tag that holds another desired state is refused. Rolling back means publishing the previous tag. The desired state carries `VERSION`, `API_ENV_SHA256` and `WEB_ENV_SHA256`, and `reconcile` waits while the staged env files or the server's settings revision differ from them, so new code never runs with an old env. The reconcile timer is installed whenever `GITOPS_URL` is set.

Secrets: `ENV_FILE` (the infrastructure env), `API_ENV_FILE` and optionally `WEB_ENV_FILE` (the application env files), plus `SSH_HOST`, `SSH_USER`, `SSH_KEY` (a dedicated deploy key, `restrict` is fine) and `SSH_KNOWN_HOSTS`. Repository variables: `REGISTRY_DRIVER` and `REGISTRY_NAMESPACE` default to GHCR and the owner, `WEB_SPECS` lists the web specs to build and ship (empty ships the API only), `DEPLOY_ACTORS` lists the logins allowed to deploy, and `DEPLOY_AUTO=true` deploys every released tag. The workflows name every secret literally: indexing `secrets` by a computed name hands the runner every secret (zizmor `overprovisioned-secrets`).

### GitOps and control plane

`export` needs no application secrets: it renders only the Compose files and writes a secret-free `application.yaml` with variables kept and no host path, plus `desired.env` (`VERSION`, `RELEASE`, `API_IMAGE`, `WEB_IMAGES`, `MIGRATION_POLICY`, `COMPOSE_SHA256`, `RELEASE_REF`, `API_ENV_SHA256`, `WEB_ENV_SHA256`).

`reconcile` reads the desired branch through the askpass vault, checks out the protected `refs/tags/release-*` tag, and requires the tagged desired state to match the branch and the Compose checksum. It then creates the Portainer Git stack with the replica and slot variables and verifies `GitConfig.ConfigHash` equals that commit before the gates and the switch. `watch` repeats it; a `timer` can too. Portainer auto-update and webhooks stay off, because a Compose update alone is no blue/green.

`portainer install` runs CE 2.45.2 on loopback 9443 with `-H unix:///var/run/docker.sock`, so local environment 1 exists. It also:

- mints a private CA and a `localhost`/`127.0.0.1` server certificate, then deletes the CA key;
- feeds the admin password and the encryption key as files, and refuses a changed key;
- creates an API key into `control/secrets/api-key`.

Later commands fall back to that CA and key when `PORTAINER_CA`/`PORTAINER_TOKEN` are empty. `portainer registry` registers the pull credential (GHCR as custom type 3, Docker Hub type 6). The control plane holds the Docker socket and is a host administrator; reach it through SSH forwarding only.

## Runbook

1. Provision Docker 29.9.1 and Compose 5.6.0 (`docker install` covers Ubuntu 24.04 amd64 from checksummed packages and refuses to replace a runtime), plus Bash 5, curl, git, jq and openssl.
2. Write the private env file: `PROJECT`, `VERSION` (or a pinned `RELEASE`), digest-pinned `API_IMAGE`/`WEB_IMAGES`, `API_HOST`/`WEB_HOSTS`, `BIND_ADDRESS`, TLS settings, data-service credentials, `REGISTRY_*` pull credentials, `GITOPS_*` read credentials and the `PORTAINER_ADMIN_PASSWORD`/`PORTAINER_SECRET_KEY` pair.
3. Export `ENV_FILE`, `API_ENV_FILE` (`"$(< ../api/.env.production)"` or one base64 line) and the `SSH_*` variables, then run `server stage`, which uploads the release bundle, `.env.production` and `.env.api` with modes 700, 600 and 600. Server commands then run there by themselves; `server run -- COMMAND` runs anything else, remote flags after `--`.
4. Run `registry login`, `portainer install` and `portainer registry`. For TLS, DNS must point at the host before HTTP-01 (`tls issue`); alternatively use the DNS-01 challenge through `DNS_PROVIDER` or `tls import CERT KEY`. Open TCP 80/443 and UDP 443 in the cloud firewall (TCP only behind a relay); `firewall ports` lists them and `firewall apply --force` updates an active ufw/firewalld. Behind an nginx relay, create `EDGE_SOCKETS` with the grant `doctor` prints and point the relay at it:

   ```nginx
   stream {
       server { listen 80;  proxy_pass unix:/srv/edge/http.sock;  proxy_protocol on; }
       server { listen 443; proxy_pass unix:/srv/edge/https.sock; proxy_protocol on; }
   }
   ```

5. Run `export DIR`, commit `deploy/application.yaml` and `deploy/desired.env`, and push a protected `release-<RELEASE>` tag. Then `reconcile`, or `deploy` with `DEPLOY_DRIVER=compose`.
6. Check with `doctor` and `deploy --dry-run`, then operate with `status`, `scale`, `rollback`, `edge apply`, `backup [list|verify]`, `restore [BACKUP] --force`, `monitor`, `notify MESSAGE`, `timer install|remove|list`, `publish`, `image remote REF` and `recover --force`. User timers outlive the SSH session only with `loginctl enable-linger`.

Images are built with `image build api|web TAG [SPEC]`; the release pipeline publishes them.

## Verification

The gate is `bash src/main.sh test --check`: bash syntax, ShellCheck at the pinned version over the bundle, the laws above, and 68 isolated tests. The tests cover:

- literal data, refusals and grammars; the TOML subset (trailing comments, dotted and duplicate tables, leading zeros, escapes) and keys kept in file order; every embedded asset equal to its file, with or without a final newline;
- precedence, schema and validation; the env file chain, `ENV_FILE` plain and base64, `parse-content`, and `GITHUB_TOKEN` filling the GHCR and GitHub credentials while staying transient;
- redaction in every output and secrets kept out of argv for SSH, curl, git, the `aws-cli` container (`s3://` and `gs://`) and Docker; SSH material given as content or base64, the `auto` method and refused paths;
- atomic failures, locks and state;
- bundle determinism and release isolation;
- render immutability, edge protocols and stats parsing; relay binds on `unix@` sockets with no published port and no QUIC, firewall ports and protocols per mode, and the trusted-proxy `set-src` rules from literal and fetched ranges, the recorded fallback and a changed source;
- GitOps payloads, export relocation and the control-plane CA and API key;
- application env files passed through byte for byte, mounted read-only and pinned by digest, unsafe variable names refused unevaluated, staged beside but never inside the infrastructure settings, and reconcile waiting for a stale server env;
- release names derived from `VERSION` and the settings revision, kept by operational changes, moved by env and pinned changes, and overridden by an explicit `RELEASE`;
- backup naming, checksum, notification and listing; the restore flow, its failure path and refusals; the swap SQL with psql-quoted names; extension entries skipped from the dump catalog;
- the remote job protocol run end to end through a fake SSH: the exit status, a dropped connection, a start lost before the job existed (run once more, exactly once), a job that never started, an unreachable host, `-e` overrides forwarded without the SSH target, and an unknown action refused before any connection;
- transient credentials kept out of staged settings and forwarded over stdin, rejected releases refused by deploy and skipped by reconcile, the instant switch to a retained release, delivery settings;
- the command line: flags with values, flag validation per command, routing of server commands over SSH with their arguments and flags, suggestions for commands and actions, the overview and per-command manual with its Actions section and aligned flags, `--version`, `config` with sources, and a manual that matches the dispatch action by action;
- notifications on all three channels with secrets out of argv, `notify` flags limited to one channel and validated like settings, the webhook signature checked against OpenSSL, retries, silent success without channels, and every raised event declared; the deploy plan for each decision; the doctor checks; backup verification;
- rate-limit and static-route rendering, integration groups, the monitoring render, verification thresholds, automatic rollback outcomes, monitor transitions and PostgreSQL extensions.

CI runs the gate on Ubuntu and macOS, then builds and scans the images; a release builds them once per tag, and Deploy reuses them by digest.

`benches/results.json` records the 2026-10-19 lab on a 4 vCPU rootless-Docker host. That covers HTTP/3 through the published UDP port, the HTTP/2 vs HTTP/3 measurements, scale, crash and hang under load, blue/green and rollback under load, a rejected candidate, web specs, the guards (retention, live-session draining, locks, stale lock, edge drift), backup and restore of 50,000 rows, timers and the control plane. A GitHub Actions run in a private repository proves the private paths with a job-scoped token read from the environment: GHCR push, private pull at deploy, Portainer registry registration, reconcile and Portainer Git stacks from the private repository, a release under load, idempotent reconcile, tamper refusal, rollback and a secret audit. The same lab uploads a backup to an S3-compatible store with enforced credentials, serves the ACME HTTP-01 route through the edge, and measures HTTP/2 against HTTP/3 under emulated latency and loss: HTTP/3 keeps its throughput at 1% and 3% loss (1.3x and 1.7x HTTP/2) for roughly 15-25% more edge CPU, and the two tie without loss. A macOS run installs and removes a launchd timer from the release bundle. A second lab on the same host bootstraps the edge with `edge apply`, deploys with pgvector migrations, serves Grafana over HTTP/2 through the edge with the provisioned dashboard and all five scrape targets up, answers `429` with `Retry-After: 60` on the sixth auth request, and rolls a release frozen during its verify window back to the previous one in 16 seconds. A third lab proves delivery: the instant switch back to a retained release in 7 seconds against 2.5 minutes for a fresh deploy, the rejection guard and its `--force` override, credentials from the process environment absent from `.env.production` yet present for the forwarded command, the reconcile timer install and removal, and `publish` against a private repository (commit and tag, an idempotent repeat, a refused tampered tag, and a rollback that moves only the branch). A fourth lab proves the env separation on rootless Docker with a production API env file and a web spec built through `WEB_SPEC_VARIABLE`: uid 10001 reads the 644 file in the 700 release directory and cannot change it, `docker inspect` shows no application secret, the API boots in production with only the forced variables in its process environment, a changed file under the same release is refused, and a rollback in 4 seconds remounts the restored release's own file while the server holds the newer one. Killing the SSH client during a verify window left the deploy running on the server; the client reattached, replayed the log and returned the deploy's exit status. A fifth lab restores the real schema (pgvector, migrations) from `BACKUP_DIR` outside the state root: by name in 6 seconds with the vector values back and the old database kept, then without a name to undo it. A sixth lab deploys one tag three times: the first env, a rotated `AUTH_SECRET` as a new release through blue/green with the same image, and the first env again, which named the retained release and switched back in 7 seconds. A final lab at about 600 requests per second against the deep `/health` check served a full deploy (99,000 requests), an instant switch, a crashed replica and scaling in both directions without one failed request; a restore failed requests for about 3 seconds at the rename; freezing every new replica rolled back in 18 seconds; a crashed deploy tree resumed through `recover --force`; 15 signed webhook deliveries verified; and the security probes passed (TLS 1.2+, headers, SNI and Host allowlists, rate limits, hardened containers, file modes). A relay lab (2026-10-20, same host) drove everything the way CI does, through `infra` with `ENV_FILE` and `API_ENV_FILE` as base64 lines, `SSH_KEY` as base64 content of a `restrict` key and `SSH_KNOWN_HOSTS` inline: stage, certificate import, a routed deploy with HTTP/3, then the relay settings. `edge apply` refused the socket directory until the printed `setfacl` grant (uid 166535 = 165536 + 999), then recreated the edge on `http.sock` and `https.sock` (owner 166535, mode 666, no published port, no UDP) behind a user-level nginx stream relay with `proxy_protocol on`. HAProxy logged the real clients 127.0.0.2-4, a per-IP limit answered `429` to a single-address flood, the redirect kept the public port, a foreign SNI was refused, and the certificate check read the expiry through the socket. A switch under load through nginx served 119,773 requests without a failure (64,244 old, 55,529 new release, max 0.235 s); routed `rollback`, `backup` and `status` worked; emptying `EDGE_SOCKETS` alone returned to published ports with Alt-Svc h3. With Cloudflare's published list trusted, `edge apply` recorded its 22 ranges, and a PROXY header from a Cloudflare address restored `CF-Connecting-IP` while one from another address kept its own; the keys have since become the provider-neutral `TRUSTED_PROXIES` and `TRUSTED_HEADER` and the rule reads the header's last address, re-checked against the pinned HAProxy 3.4.7 (a trusted peer's chained `X-Forwarded-For` and IPv6 value restored, a malformed value and an untrusted peer kept). A `gs://` upload with fake HMAC keys reached `storage.googleapis.com` and was answered `SignatureDoesNotMatch`, proving the container's route, the endpoint and the signing. A release lab (2026-10-21) drove the workflows themselves on GitHub: tag `v1.1.0` ran every gate on Linux and macOS, published the release and, with `DEPLOY_AUTO=true`, called Deploy, whose `images` job built and scanned the API and three web images for the deployment's address before the `deploy` job shipped them over SSH with a `restrict` key; Deploy dispatched by hand from main then ran a backup, a deploy into relay mode behind a user-level nginx stream relay (clients 127.0.0.2-4 logged from distinct sources, no published edge port), a deploy back to standalone with HTTP/3, an env change and a rollback, 18,122 requests across the last switch and the rollback without a failure. The memory guard rejected a candidate the shared host could not hold and restored the live release, the retention guard refused a deploy while the previous slot was kept, GHCR refused the first push of each new package until it granted the repository (hence a bounded retry), and the first `uninstall` left the slot kept for rollback and the monitoring running (fixed and rerun). A final lab (2026-10-21, same host) drove the 0.2.0 bundle from a checkout over SSH with an API-only release on the pinned `python:3.15-slim` image: a staged bundle byte-identical to the local build, HTTP/2 and HTTP/3 (200 with `X-Release` through the published UDP port), HSTS, Alt-Svc, the 308 that keeps the port, strict SNI, Grafana, backups created, listed and verified, a post-switch probe refused by the per-IP limit (rejected, the live release restored), a forced redeploy under load (14,803 requests, all 200, max 0.024 s), a rollback in 7 seconds under load (1,187, all 200), relay mode behind a user-level nginx stream relay with a switch under load from two sources (12,832, all 200, max 0.066 s), the trusted-proxy rule in both modes (a trusted peer's `CF-Connecting-IP` restored, an untrusted or malformed one ignored, the Cloudflare list fetched by URL), the return to standalone as an instant switch to the retained release, offsite uploads with fake keys answered by Google (`SignatureDoesNotMatch`) and AWS (`InvalidAccessKeyId`) through forwarded `-e` overrides with the secret absent from every output, and `-e API_REPLICAS=3 scale` and back on the server. It also showed that rootless Docker's port forwarding presents every standalone client as the bridge gateway, now a `doctor` warning. Still unverified: a successful Google Cloud Storage upload with real HMAC keys, Telegram delivery with a real bot, Docker Hub with real credentials, public UDP through a cloud firewall with Let's Encrypt issuance, and the live Cloudflare DNS API. Claim a capability only after observing its success and failure paths.

References: [HAProxy 3.4](https://docs.haproxy.org/3.4/configuration.html), [Portainer CLI](https://docs.portainer.io/advanced/cli), [Portainer Git stacks](https://docs.portainer.io/user/docker/stacks/add), [Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
