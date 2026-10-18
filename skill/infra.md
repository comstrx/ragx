# Infra

One bash bundle under `infra/` that turns any Linux box reachable over ssh into the whole platform as a Docker Compose monolith. Gate: `bash src/main.sh test --check`.

## Shape

```
infra/
├── src/main.sh        the entry: sources core/{log,fs,sys}, module/tool and forge/*, then forge_main
├── src/core/          cli config fs log proc secret sys template ui     (the runtime of the bundle)
├── src/forge/         build check cli install meta payload release source test   (the build of the bundle)
├── src/module/        app audit backup ci compose dns edge pg secrets self server tool   (the verbs)
├── src/template/      compose/ nginx/ postgres/ rabbitmq/ redis/ systemd/ docker/   (rendered or copied onto the box)
├── tests/             assert.sh + flat *.sh, functions test_* run one per process inside the dev bundle
├── .env.example       every knob with its default; the only home of literals (urls, images, versions, limits)
└── .secret.example    every secret the platform expects from outside (names only)
```

- `bash src/main.sh build` assembles `target/dev/infra.sh` (tests included, templates read live) and `build-release` assembles `target/release/infra.sh` (tests stripped) + `SHA256SUMS`; the templates ride as a deterministic tar payload with a sha stamped in the header and verified on first use; `check` runs `bash -n`, shellcheck at the configured severity, payload integrity and the literals law; `test [glob] [--check]` runs the bash tests; `install` installs the checked release bundle; `self update` replaces a running bundle with a released one, checksum verified.
- A module is a file `module/<name>.sh` emitted under a `# @module <name>` banner; a verb is `<name>_<verb> ()` preceded by one `## doc` line, called as `infra <name> <verb>`; `infra help <module> [verb]` and `infra -l` read the banners and the docs. A new module is one file; nothing else registers it.
- Config precedence: flags (`-e KEY=VALUE`) > process env > `JSON_ENV` (a json object of repository secrets; only manifest keys load, local keys never) > `--config` files (last wins) > `.env.example` defaults; secrets default to empty strings so a render never dies on an unset secret. `-s <stack>` picks the stack (`STACKS=production staging`; staging uses the ACME staging directory). `config_derive` computes everything else (hosts, names, urls, profiles, tuning) and `config_reset` forgets it between loads.
- Laws enforced by `secrets example` and the tests: the two examples are disjoint; every key they name is read by the code or a template; no literal url or shellcheck knob in `src/`; every template placeholder has a source; defaults are project-neutral.

## Verbs

| Module    | Verbs                                                                                                                                                                                                                                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `server`  | `setup` (docker, compose, sysctl on the box), `deploy` (push the bundle and the resolved config, then `bootstrap` on the box: prepare, registry login, names, certificate, stack, units, verify), `ensure` (bootstrap or refresh), `refresh` (push + `compose deploy` + verify), `run`, `copy`, `status`, `verify` |
| `compose` | `render` (the whole stack into `COMPOSE_DIR`), `config`, `pull`, `up`, `stop`, `down`, `ps`, `logs`, `restart`, `exec`, `roll <service>` (zero downtime), `deploy` (render → pull → data services → roll api and web → workers → reload the edge → record → prune), `rollback`, `releases`                         |
| `edge`    | `issue` (dns-01 through Cloudflare when a token exists, http-01 through the running edge otherwise), `renew`, `reload` (tested first), `test`, `days`, `names`                                                                                                                                                     |
| `pg`      | `shell` (superuser over the socket, args reach psql), `activity`, `size`, `slow` (pg_stat_statements from the maintenance database), `tune`                                                                                                                                                                        |
| `backup`  | `now`, `list`, `fetch <stamp>`, `restore <stamp> [db]` (always into a side database, never over the live one)                                                                                                                                                                                                      |
| `app`     | `run -- <bootstrap verb…>` (a one-off container on the release with the same image, env and secrets), `migrate`, `status`, `runbook`, `shell`                                                                                                                                                                      |
| `dns`     | `sync`, `ensure`, `show`, `names` (Cloudflare only, only when `DNS_MANAGED` is true)                                                                                                                                                                                                                               |
| `audit`   | `edge`, `tls`, `services`, `backup`, `all`, `watch` (external probe with a Telegram alarm when configured)                                                                                                                                                                                                         |
| `ci`      | `release` (preflight → build → prove → push → scan → `server ensure` → wait for the edge), `images`, `build`, `prove`, `push`, `scan`, `setting <KEY>` (secrets refused), `verify` (the wall), `gate`, the laws `compose nginx loader templates workflows leaks`                                                   |
| `secrets` | `check` (required keys grow with the features; a quote or a newline in any secret is refused), `drift`, `env`, `example`, `keys`                                                                                                                                                                                   |
| `self`    | `version`, `where`, `keys`, `update`                                                                                                                                                                                                                                                                               |
| `tool`    | `ensure <tool…>` (docker, jq, trivy, gitleaks, actionlint, …)                                                                                                                                                                                                                                                      |

Every box verb begins with `server_here || { server_forward <module> <verb> …; return; }`: on the box (the bundle lives at `SERVER_PATH`) or with no `SSH_HOST` at all (local, CI) it acts locally; anywhere else it travels over ssh to the bundle on the box with the same stack and overrides, attaching a tty when one is present.

## The stack it renders

`compose render` writes into `COMPOSE_DIR` (`${BUILD_DIR}/compose/<stack>` locally, `${SERVER_PATH}/stack` on the box):

- `compose.yaml` with no placeholder left (compose would interpolate), the project named `<PROJECT>-<STACK>`; env files `api.env postgres.env rabbitmq.env redis.env backup.env` at `0600` with every value single-quoted (literal under compose), the api env extended by `ENV_FILE` extras that never override a rendered key; `nginx/` (`nginx.conf`, `proxy.inc`, `site.inc`, `tls.inc`, `conf.d/00-http.conf`, `05-realip.conf` when a shield is trusted, `10-tls.conf`, `20-api.conf`, `30-web.conf` when the web profile is on); `postgres/{postgresql.conf,pg_hba.conf,init.sh}`; `rabbitmq/platform.conf`; `redis/redis.conf`; `systemd/` units (the stack on boot, the nightly backup timer, the renewal timer, each calling the bundle); a `releases` ledger.
- Secrets that a container reads as a file never touch the disk: the Redis users are declared on its command line from the container's own env; the Cloudflare token reaches certbot as a compose secret sourced from the environment that `compose_cmd` exports.

Topology laws (pinned by `tests/stack.sh` and `tests/render.sh`):

- Every container: `restart: unless-stopped`, `no-new-privileges`, `cap_drop ALL`, rotated json logs, `read_only: true` with tmpfs where it must write, its own uid; `deploy.resources.limits` from knobs.
- Networks: `edge` (nginx ↔ api ↔ web, egress) and `data` (`internal: true`: api/worker/scheduler ↔ postgres/rabbitmq/redis); no data port is ever published.
- Profiles: `web` (one container per spec in `WEB_SPECS`), `worker` (`WORKER_REPLICAS > 0`, then the http process runs no workers), `scheduler` (then the http process runs no schedule), `ops` (backup sidecar and certbot: never started by themselves). Worker and scheduler depend on a healthy api (a migrated schema, no volume race).
- nginx (unprivileged image, 8080/8443 inside, `HTTP_BIND`/`HTTPS_BIND` outside, tcp + udp): `server_tokens off`; lazy upstream resolution (`server api:8000 resolve` + a short resolver ttl) so a rolling api never breaks the edge; `limit_req` zones per client for api, auth and web with `429`; `limit_conn`; an edge cache for `/assets/` and `/storage/`; `location = /ws` upgrade with a long timeout; dotfiles denied; `X-Forwarded-For` set from the peer (never appended); the default http server serves the ACME webroot and redirects (tls) or drops (`444`); the default tls server rejects unknown names before the handshake; `tls.inc`: TLS 1.2 + 1.3, AEAD ciphers only, `X25519MLKEM768` first, tickets off, early data off, HSTS preload, `Alt-Svc h3`.
- PostgreSQL 18 (uid 999, data under `/var/lib/postgresql`): tuned from `PG_MEMORY_MB` (`pg tune` prints it), scram only, `pg_hba`: `postgres` over the socket by peer and never over the network, the app role from the stack network only, everything else rejected; `init.sh` creates the app role `LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS CREATEDB`, the database owned by it with `REVOKE CONNECT FROM PUBLIC`, trusted extensions in the app database and `pg_stat_statements` in the maintenance database (a dump restored by the app role cannot recreate a superuser-only extension); `io_method = worker`, `wal_compression = zstd`, `jit = off`, idle-in-transaction and statement timeouts, slow statement logging.
- RabbitMQ 4.2 (`loopback_users = none`, quorum queues by default, memory watermark and disk limit, user/pass/vhost from env) and Redis 8 (`save ""`, no volume, `allkeys-lru`, the default user disabled, an ACL-scoped app user, `REDISCLI_AUTH` feeding the healthcheck).
- Health probes with `start_interval` so a roll completes in seconds; the api image's own `HEALTHCHECK` carries them.

## The release line

`ci release`:

1. `ci preflight`: `secrets check` (required keys: project, domain, repository, token, ssh host, every data password, `AUTH_SECRET`; plus `SSL_EMAIL` with TLS, the Cloudflare token with managed names or dns-01, the S3 keys with S3 backups or S3 files; one way onto the box among `SSH_PRIVATE_KEY`, `SSH_KEY`, `SSH_PASSWORD`).
2. `ci build`: the api image (`docker/Dockerfile --target app`), its backup sidecar (`--target backup`), one web image per spec (`docker/Dockerfile.web --target runtime --build-arg SPEC=<spec> SPEC_API_URL=<api origin>`), all tagged with the git sha under `<REGISTRY>/<repository>/{api,web}`.
3. `ci prove`: the api imports with every runtime package, storage and assets in place; the sidecar carries `pg_dump`, `aws` and the script; each web image carries its compiled spec and build.
4. `ci push` (immutable tags already in the registry are reused), `ci scan` (trivy, fixable CRITICAL blocks unless `CVE_ALLOW=true`).
5. `server ensure`: a box that already runs the stack gets `refresh` (push + `compose deploy` + verify); a fresh box gets `deploy` (push + `server bootstrap`: `prepare` → `ci login` → `dns ensure` → `edge prepare` → `compose deploy` → `server units` → `server verify`).
6. `ci deployed`: `curl --resolve <api host>:<port>:<box> …/health` until `data.release` equals the tag, independent of DNS propagation.

`compose roll <service>`: start the new containers beside the old (`up --no-deps --no-recreate --scale`), wait until every new one is healthy, retire the old, normalize the scale; verified with zero failed requests during a roll. `compose rollback` redeploys the previous recorded release.

## Tests

`tests/{cli,config,payload,render,secret,stack,app,release,laws}.sh`, run one function per process inside the dev bundle: the module list, config precedence and neutral defaults, the ACME directory per stack, the payload (extract once, verify, refuse tampering, keep modes), a full render per stack with every service wired (encoded broker and cache urls, origins, profiles, worker and schedule switches), the edge in both tls states, the limits and the honest client address, the web and wildcard knobs, `docker compose config` and a real `nginx -t` against the rendered edge, the app env and the extras, refused quotes and placeholders, the required-secrets growth, the server env without the way in, the topology laws, the data service settings, the backup script, the image users, the postgres memory derivation, the roll order, every chain verb existing, the templates and loader laws, url encoding and origins. A new knob, template or verb lands with its assertion in the matching file.

## How to add

- **A knob**: `.env.example` (with a neutral default), read it in a script or a template, derive from it in `config_derive` when other keys follow, assert it in a test; the examples law refuses an unread key.
- **A secret**: `.secret.example`, `secrets_required` when a feature makes it mandatory, consumed through `secret_get`/`secret_require`, never printed; `config_render` carries it to the box unless it is a local or ssh key.
- **A template**: under `src/template/<area>/`, placeholders as `${KEY}` only for keys the config defines (nginx's own variables stay `$var`), listed in `compose_templates`, rendered in `compose_render` (`compose_file` for config, `compose_secret` for `0600`, `compose_copy` for scripts that carry their own `${}`), asserted in `tests/render.sh` or `tests/stack.sh`.
- **A module**: `src/module/<name>.sh` with its `##` docs, verbs that forward from off-box, tests in a new flat file, a row in the table above.
- **A service**: the compose template (hardened like its neighbors, on the right network, with a health probe and limits), its config template, its env file, its knobs, `compose deploy` ordering, the topology test, and the audit that proves it alive.

## Local verification

A lab on a developer machine: a config with `SSH_HOST=` (empty, so every verb acts locally), `TLS_ENABLED=false`, `WEB_ENABLED=false` or a built web image, high `HTTP_PORT`/`HTTPS_PORT` bound to `127.0.0.1`, `IMAGE_API` pointing at a locally built image, `IMAGE_TAG_OVERRIDE`, probe secrets and `COMPOSE_DIR` under a scratch folder; then `compose render`, `compose config`, `compose up`, the probes through nginx with a `Host` header (`/health`, `/v1/hello`, `/assets/…`, `/robots.txt`, `/ws`, an unknown host, a traversal, the auth limit), `app run status`, `backup now|list|fetch|restore`, `pg size|slow`, `compose roll api` under a request loop, `audit services`, and `compose down` (every profile) when done. Every claim about the platform in a report comes from such a run or from a real box.
