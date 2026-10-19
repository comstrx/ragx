# Infrastructure

The infrastructure is a Bash 5 framework delivered as one self-contained executable. Its current stack is `native`: Docker Engine and Compose with a persistent HAProxy edge and a Portainer CE control plane. Kubernetes, Helm, Argo CD, Kustomize and OpenTofu are future stacks added through `module/`, `template/` and a new `app/<stack>/` folder only.

## Layout and layers

| Path                 | Owns                                                                                                                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Bash.toml`          | Identity, `stack`, paths (`entrypoint source build tests templates cache`), tool versions, image digests, check policy, endpoints, download and package checksums, and the `[native]` engineering constants. |
| `.env.example`       | The one environment schema: every key with its default, grouped in owner blocks with one comment line each.                                                                                                  |
| `src/main.sh`        | Strict mode, then `bootstrap/index.sh`, then `bootstrap-main`.                                                                                                                                               |
| `src/bootstrap/`     | The only entry. Loads core and config, assembles `app/<stack>/*.sh` from the manifest's stack, owns governance (`help build build-release checksum prepare check test run config`) and the laws.             |
| `src/core/`          | Generic verbs, biased to no stack: `log ui sys parse fs config cli asset template state net git ssh package bundle test load`.                                                                               |
| `src/config/`        | `index.sh`, the schema load, precedence, validation, derivation and release snapshots.                                                                                                                       |
| `src/module/`        | One file per tool: `docker haproxy portainer registry postgresql rabbitmq redis tls cloudflare s3 gitops systemd launchd firewall`.                                                                          |
| `src/app/native/`    | Orchestration of the native stack: `commands topology render deploy edge control scale gitops backup operations`.                                                                                            |
| `src/template/`      | `native/` Compose, HAProxy, unit and plist templates; `image/` Dockerfiles.                                                                                                                                  |
| `tests/`, `benches/` | Offline tests discovered by name; the HTTP/3 client image, the protocol bench and the lab evidence.                                                                                                          |

Laws enforced by `check` on every source and test file:

- Layer calls: core calls core; config calls core; a module calls core and the `docker` runtime module only; app calls core, config, modules and its own stack; bootstrap calls core, config and bootstrap. A tool combining two others belongs in app.
- Names: `module/<tool>.sh` defines `<tool>-*`, `app/<stack>/` defines `<stack>-*`, config `config-*`, bootstrap `bootstrap-*`, tests `test-*` or `fixture-*`. A function is defined once.
- Style: `name () {`, a blank line after the opening and before the closing brace, no consecutive blank lines, four-space indentation, no tabs, no trailing spaces, zero comments.
- Errors: `err "message"` prints `[-]` on stderr, redacted, and returns 1; callers write `|| return`. No manual status codes outside signal traps.
- Layout: flat `core config bootstrap module`, one folder per stack under `app/`.

## Runtime and core

Linux and macOS with Bash 5.2/5.3. OS predicates read `OSTYPE` without forks; kernel, distribution and package manager are detected once and cached. The package table covers apt, apk, dnf, yum, pacman, zypper, xbps, brew, port and nix, and declares unsupported actions, such as nix refresh. `run-sudo` uses `sudo -n` and never prompts. `run-timeout` is portable, keeps stdin and reports the timeout. `run-until` polls with a deadline.

SSH supports agent, key, certificate and password authentication with `StrictHostKeyChecking=yes` and forwarding disabled. Passwords travel through an `sshpass -d` descriptor, and remote arguments are single-quote encoded. Uploads are checksum-verified, atomic and refuse symlinks. Tokens never enter argv:

- HTTP credentials reach curl through `--config -` on stdin.
- Git credentials reach git through a temporary askpass vault.
- S3 keys are exported only inside a subshell.
- Registry passwords use `--password-stdin`.

Writes are atomic, through a staging file and `mv`. A failed producer leaves the destination untouched. All temporary files live in a per-run session directory that is removed on exit.

## Configuration

Resolution order: `.env.example` defaults, then the env file(s), then the process environment, then `-e KEY=VALUE`. Explicit CLI input wins, the order Docker Compose and Terraform document. File selection works as follows:

- Development picks `.env.local`, otherwise `.env`.
- A release bundle picks `.env.production` or `.env.pod`, otherwise `.env`. Both production files present is an error.
- `--config FILE` repeated replaces the selection, in order.

Unknown keys fail the whole load atomically. Values are data, never sourced or evaluated. Multiline values, quotes, `$` and backslashes round-trip.

`ENV_MODE` is fixed by the build: release means production. `--environment` and `--target` choose `DEPLOY_ENV` and `SSH_HOST` independently. Derived values:

- `STACK`, plus every `Bash.toml` image as `IMAGE_*` and every `[<stack>]` constant upper-cased. A collision with the schema is an error.
- `COMPOSE_PROJECT`, and `STATE_ROOT=<project root>/<paths.cache>/<project>-<env>`.
- `WEB_ENABLED`, `API_URL` and `APP_ORIGINS`, with default ports omitted.

The environment controls replicas, strategy, domains, health paths, secrets and integrations. Engineering constants live in `Bash.toml [native]`: ports, balance per service type, timeouts, warmup, drain, retention, memory, CPU and connection limits.

Validation reports every invalid key at once. The rules:

- Ports, counts and paths must be well formed.
- Images, `API_IMAGE` and every `WEB_IMAGES` entry must be pinned by digest. Host names follow RFC 1123.
- Web specs, hosts and replica maps must agree.
- `DB_USER` must not be `postgres`. Production requires TLS. `HTTP3_ENABLED=true` requires `TLS_ENABLED=true`, the only HTTP/3 rule.
- A Cloudflare record managed with `CLOUDFLARE_PROXIED=true` while HTTP/3 is on warns and never blocks.
- Deploys require the application secrets: passwords of at least 16 characters and `AUTH_SECRET` of at least 32.

## Native stack

Projects and boundaries:

- `<project>-data`: PostgreSQL, RabbitMQ and Redis on an internal network, guarded by a fingerprint. Changed data settings need a planned migration.
- `<project>-edge`: HAProxy. The edge and control plane are never recreated by an application deploy.
- `<project>-<release>`: API, worker, scheduler and web specs.
- `<project>-control`: Portainer.

Networks and volumes carry an `io.infra.owner` label and are refused when another owner holds the name. Every container runs non-root (data services as uid 999), read-only, with `cap_drop: [ALL]`, `no-new-privileges`, pid and memory limits, `nofile 65536` where sockets matter, and local log rotation. No scalable service has `container_name` or a host port.

The release Compose files interpolate `${API_REPLICAS}`, `${WORKER_REPLICAS}`, `${WEB_<SPEC>_REPLICAS}`, `${DEPLOY_SLOT}` and `${RELEASE_ROOT}` at run time. One rendered release therefore serves native Compose and Portainer, any slot and any replica count, and its snapshot (`release.env`) changes only when application inputs change.

### Edge

HAProxy 3.4.7 LTS (AWS-LC, QUIC) terminates TLS 1.2/1.3 with Mozilla intermediate ciphers, `X25519MLKEM768:X25519:P-256:P-384` curves, no session tickets and strict SNI.

- **HTTP/1.1 and HTTP/2:** run on TCP 443 with ALPN `h2,http/1.1`.
- **HTTP/3:** with `HTTP3_ENABLED=true` (the default), `bind quic4@:8443 … ssl-min-ver TLSv1.3 alpn h3` on the frontend only, `Alt-Svc h3=":<port>"; ma=86400`, and UDP published on the same port. Clients fall back to TCP. Backends stay HTTP/1.1, and 0-RTT is never enabled.
- **Security behavior:** Host allowlist (404 otherwise), 308 HTTP to HTTPS, HSTS two years, overwritten `X-Forwarded-For`, a UUIDv7 `X-Request-ID`, `nosniff`, an `X-Release` header and no `Server` header, set through `http-after-response` so generated responses carry them too.
- **Logs:** JSON log lines record the path without the query string (`%HP`).
- **Discovery:** each service gets `server-template replica 1-32 <service>-<slot>:<port>` through the Docker resolver.
- **Health:** active `GET <path>` checks expect 200 for the API and 200-399 for web front ends. Settings are `inter 2s fall 3 rise 2 slowstart 10s`.
- **Never routing to unready replicas:** `init-state fully-down` keeps a discovered replica out until it passes `rise` checks.
- **Failure handling:** `observe layer7 error-limit 10 on-error mark-down` is the passive circuit. `maxconn`/`maxqueue` per server provide fail-fast back-pressure. `retry-on conn-failure empty-response` with `option redispatch 1` and `timeout connect 1s` handles retries on the local bridge.
- **Timeouts:** `tunnel 1h` for WebSockets, `client-fin` and `server-fin`, and `hard-stop-after 1h` with `expose-fd listeners` for seamless reloads.
- **Admin surfaces:** the Runtime API listens on 127.0.0.1:9999 inside the container only. Prometheus `/metrics` and `/live` sit on :9090 on the apps network, and on host loopback when `METRICS_ENABLED=true`.

The live map `active.map` selects `slot:release`, switched atomically through the Runtime API and persisted on disk. A candidate frontend (8081/8444, header `X-Slot`) reaches the inactive slot from the apps network only.

### Deploy, rollback and draining

`deploy` validates, locks `STATE_ROOT/lock` and records every phase in `phase` and `audit.log`. The sequence:

1. Preflight edge drift; a changed edge needs `edge apply` first.
2. Retire the inactive slot, but only after `RETENTION_SECONDS` since the active release went live and only when HAProxy reports zero sessions on it within `DRAIN_TIMEOUT`.
3. Render or verify the immutable release.
4. Pull digest-pinned images, check memory and disk capacity, then ensure networks, volumes and data.
5. Migrate when `MIGRATION_POLICY=expand`. An interrupted migration refuses to rerun.
6. Start the candidate front, wait for healthy containers with the right image, then pass HAProxy readiness and an HTTPS probe through the candidate frontend.
7. Warm up and probe again.
8. Switch the map, move worker and scheduler, and verify the public release header.

Any failure restores the origin slot and background services and records `rejected`. An unrecoverable restore records `recovery-required` and keeps the pending state.

`manual` stages without switching until `deploy --force`. Redeploying the current release is idempotent. `rollback` rejects a pending candidate, or switches back to the retained previous release after checking its slot was not reused. `scale` drains replicas above the target in HAProxy, waits for idle, then lets Compose remove them. Data services and the scheduler never scale. `recover --force` removes only a dead-owner lock. Long-lived WebSockets stay on the old slot after a switch, and retirement refuses while they live. Schema rollback is never attempted, so application rollback needs backward-compatible expansion migrations.

### GitOps and control plane

`export` writes a secret-free `application.yaml` with variables kept and no host path, plus `desired.env` (`RELEASE`, `API_IMAGE`, `WEB_IMAGES`, `MIGRATION_POLICY`, `COMPOSE_SHA256`, `RELEASE_REF`).

`reconcile` reads the desired branch through the askpass vault, checks out the protected `refs/tags/release-*` tag, and requires the tagged desired state to match the branch and the Compose checksum. It then creates the Portainer Git stack with the replica and slot variables and verifies `GitConfig.ConfigHash` equals that commit before the gates and the switch. `watch` repeats it; a `timer` can too. Portainer auto-update and webhooks stay off, because a Compose update alone is no blue/green.

`portainer install` runs CE 2.45.2 on loopback 9443 with `-H unix:///var/run/docker.sock`, so local environment 1 exists. It also:

- mints a private CA and a `localhost`/`127.0.0.1` server certificate, then deletes the CA key;
- feeds the admin password and the encryption key as files, and refuses a changed key;
- creates an API key into `control/secrets/api-key`.

Later commands fall back to that CA and key when `PORTAINER_CA`/`PORTAINER_TOKEN` are empty. `portainer registry` registers the pull credential (GHCR as custom type 3, Docker Hub type 6). The control plane holds the Docker socket and is a host administrator; reach it through SSH forwarding only.

## Runbook

1. Provision Docker 29.9.1 and Compose 5.6.0 (`docker install` covers Ubuntu 24.04 amd64 from checksummed packages and refuses to replace a runtime), plus Bash 5, curl, git, jq and openssl.
2. Write the private env file: `PROJECT`, `RELEASE`, digest-pinned `API_IMAGE`/`WEB_IMAGES`, `API_HOST`/`WEB_HOSTS`, `BIND_ADDRESS`, TLS settings, application secrets, `REGISTRY_*` pull credentials, `GITOPS_*` read credentials and the `PORTAINER_ADMIN_PASSWORD`/`PORTAINER_SECRET_KEY` pair.
3. From a checkout run `--config FILE server stage`, which uploads the release bundle and `.env.production` with modes 700 and 600. Then use `server run -- COMMAND`; remote flags follow `--`.
4. Run `registry login`, `portainer install` and `portainer registry`. For TLS, DNS must point at the host before HTTP-01 (`tls issue`); alternatively use the Cloudflare DNS challenge or `tls import CERT KEY`. Open TCP 80/443 and UDP 443 in the cloud firewall; `firewall ports` lists them and `firewall apply --force` updates an active ufw/firewalld.
5. Run `export DIR`, commit `deploy/application.yaml` and `deploy/desired.env`, and push a protected `release-<RELEASE>` tag. Then `reconcile`, or `deploy` with `DEPLOY_DRIVER=compose`.
6. Operate with `status`, `scale`, `rollback`, `edge apply`, `backup`, `restore FILE NEWDB`, `monitor`, `timer install reconcile|backup|monitor|renew SECONDS` and `recover --force`.

Images are built with `image build api|web TAG [SPEC]` and published by the manual Infra workflow (`publish=true` on main) to GHCR or Docker Hub.

## Verification

The gate is `bash src/main.sh test --check`: bash syntax, ShellCheck at the pinned version over the bundle, the laws above, and 44 isolated tests. The tests cover:

- literal data, refusals and grammars;
- precedence, schema and validation;
- redaction in every output and secrets kept out of argv for SSH, curl, git, AWS and Docker;
- atomic failures, locks and state;
- bundle determinism and release isolation;
- render immutability, edge protocols and stats parsing;
- GitOps payloads, export relocation and the control-plane CA and API key.

CI runs the gate on Ubuntu and macOS, then builds and scans the images.

`benches/results.json` records the 2026-10-19 lab on a 4 vCPU rootless-Docker host. That covers HTTP/3 through the published UDP port, the HTTP/2 vs HTTP/3 measurements, scale, crash and hang under load, blue/green and rollback under load, a rejected candidate, web specs, the guards (retention, live-session draining, locks, stale lock, edge drift), backup and restore of 50,000 rows, timers and the control plane. A GitHub Actions run in a private repository proves the private paths with a job-scoped token read from the environment: GHCR push, private pull at deploy, Portainer registry registration, reconcile and Portainer Git stacks from the private repository, a release under load, idempotent reconcile, tamper refusal, rollback and a secret audit. A macOS run installs and removes a launchd timer from the release bundle. Still unverified: Docker Hub with real credentials, public UDP through a cloud firewall, ACME, Cloudflare and S3. Claim a capability only after observing its success and failure paths.

References: [HAProxy 3.4](https://docs.haproxy.org/3.4/configuration.html), [Portainer CLI](https://docs.portainer.io/advanced/cli), [Portainer Git stacks](https://docs.portainer.io/user/docker/stacks/add), [Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
