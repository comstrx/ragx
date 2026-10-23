# Infrastructure

The infrastructure is a Bash 5 framework delivered as one self-contained executable. Its current stack is `native`: Docker Engine and Compose with a persistent HAProxy edge and a Portainer CE control plane. Kubernetes, Helm, Argo CD, Kustomize and OpenTofu are future stacks added through `module/`, `template/` and a new `app/<stack>/` folder only.

## Layout and layers

| Path                 | Owns                                                                                                                                                                                                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Bash.toml`          | Identity, `stack`, paths (`entrypoint source build tests templates cache`), tool versions, the runtime commands the tool needs (`[requires]`), image digests, check policy, endpoints, download and package checksums: build constants that change only with the code.                                                         |
| `.env.example`       | The one environment schema: every key with its default, in owner blocks, each under one short comment line and a blank line; `.env.production` and `.env.local` repeat its keys, order and comments with their own values.                                                                                                     |
| `src/main.sh`        | Strict mode, then `bootstrap/index.sh`, then `bootstrap-main`.                                                                                                                                                                                                                                                                 |
| `src/bootstrap/`     | The only entry. Loads core and config, assembles `app/<stack>/*.sh` from the manifest's stack, owns governance (`help build build-release checksum prepare check test run config`) and the laws.                                                                                                                               |
| `src/core/`          | Generic verbs, biased to no stack: `log ui sys parse fs config cli asset template state net git ssh package bundle test load`.                                                                                                                                                                                                 |
| `src/config/`        | `index.sh`, the schema load, precedence, validation, derivation, release snapshots, and the tables read by one parser (`config-table`): `parts.sh` (the only code that names a part), `data.sh` (the data services), `models.sh` (runners, models and their pinned files) and `domains.sh` (the dynamic-domain payload shape). |
| `src/module/`        | One file per tool: `docker haproxy portainer registry postgresql rabbitmq redis tls s3 gitops systemd launchd firewall monitoring telegram slack webhook huggingface`.                                                                                                                                                         |
| `src/app/native/`    | Orchestration of the native stack, one domain per file: `commands` (the command manual), `topology render deploy control scale edge domains data backup gitops observe notify inspect models server images host network`.                                                                                                      |
| `src/template/`      | `native/` Compose (`server.yaml.tpl`, `site.yaml.tpl` per part kind, `model.yaml.tpl` per model), HAProxy, unit and plist templates, `native/monitor/` Prometheus, Alertmanager and Grafana; `image/` Dockerfiles; `generated/suffixes.dat` the Public Suffix List.                                                            |
| `tests/`, `benches/` | Offline tests discovered by name; the HTTP/3 client image, the protocol bench and the lab evidence.                                                                                                                                                                                                                            |

Laws enforced by `check` (`src/bootstrap/laws.sh`) on every source and test file:

- Layer calls: core calls core; config calls core; a module calls core and the `docker` runtime module only; app calls core, config, modules and its own stack; bootstrap calls core, config and bootstrap. A tool combining two others belongs in app.
- Names: `module/<tool>.sh` defines `<tool>-*`, `app/<stack>/` defines `<stack>-*`, config `config-*`, bootstrap `bootstrap-*`, tests `test-*` or `fixture-*`. A function is defined once.
- Style: `name () {`, a blank line after the opening and before the closing brace, no consecutive blank lines, four-space indentation, no tabs, no trailing spaces, zero comments.
- Errors: `err "message"` prints `[-]` on stderr, redacted, and returns 1; callers write `|| return`. No manual status codes outside signal traps.
- Layout: flat `core config bootstrap module`, one folder per stack under `app/`.
- Parts: only `config/` and `.env.example` name a part. A source, test or template outside them that writes a part's key prefix (`API_`, `CLIENT_` …, read from the table) fails the check; tests run on their own fixture table.

## Runtime and core

An operational framework in Bash, not a deploy script: from the needle to the rocket it prepares the host, installs pinned tools, renders every file from templates and settings, runs the services, deploys with zero downtime, rolls back, backs up, restores, monitors and notifies. Linux and macOS only (never Windows, WSL shims, MSYS, Cygwin or Git Bash), Bash 5.2/5.3.

- `sys`: silent predicates on exit codes (`has need has-all need-all is-linux is-macos is-unix is-posix os runtime kernel distro manager is-terminal is-interactive is-container is-root`), safe execution (`run-cmd run-sudo run-ok run-sudo-ok`, never a silent privilege escalation), results through `out`, errors through `err`, minimal forks, no false positives.
- `config` and `parse`: one resolution with a fixed precedence, unknown keys fail atomically, values are data and never become executable; content inputs (`ENV_FILE`, every `<PART>_ENV_FILE`, SSH material) are plain text or one base64 line, auto-detected.
- Secrets: names matching `PASSWORD SECRET TOKEN CREDENTIAL WEBHOOK_URL _KEY _KEYS` are redacted everywhere; secrets never enter argv; files that hold them are 600; every authenticated HTTPS call goes through one `net-request` with credentials on stdin and `curl --disable`.
- Every integration turns on only when its keys exist and is all-or-none; provider code lives in a driver behind neutral keys.

The host: OS predicates read `OSTYPE` without forks; kernel, distribution and package manager are detected once and cached. The package table covers exactly apt, apk, dnf, yum, pacman, zypper, xbps (+ brew, nix) on Linux and brew, port, nix on macOS, chosen by real priority, and declares unsupported actions, such as nix refresh. `run-sudo` uses `sudo -n` and never prompts. `run-timeout` is portable, keeps stdin and reports the timeout. `run-until` polls with a deadline and `run-retry` retries with a growing pause.

SSH supports agent, key, certificate and password authentication with `-T`, `StrictHostKeyChecking=yes` and forwarding disabled, so a `restrict` authorized key works. `SSH_METHOD=auto` (the default) picks password > certificate > key > agent from what is set; PEM is a format, not a method; host keys are always verified. `SSH_KEY`, `SSH_CERTIFICATE` and `SSH_KNOWN_HOSTS` take a path or the content itself, plain or one base64 line; content lands in a mode-600 file inside the session directory. Passwords travel through an `sshpass -d` descriptor, and remote arguments are single-quote encoded. Uploads are checksum-verified, atomic and refuse symlinks. Tokens never enter argv:

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
- a `server run` start that never reached the server: started again up to three times. The server claims each job id atomically before launching it, so a start cut off after its claim is reported as possibly running and never repeated, and a connection lost after the start follows the job;
- HTTPS reads (`GET`, downloads): curl `--retry 3 --retry-connrefused`; writes to remote APIs are never repeated blindly;
- model files (`net-fetch`): five attempts that resume the `.part` file with a range request; no total time limit, but a transfer slower than 1 KiB/s for 60 seconds is cut; the size and SHA-256 are checked before an atomic move, a mismatch deletes the download, and a bearer token rides curl's stdin config;
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
- `PARTS`, the parts that have a domain, in table order; every table column as `<PART>_<COLUMN>` (source `parts`); `<PART>_URL` (first domain and path) and `GRAFANA_URL`, with default ports omitted.
- `MODELS_ROOT`, which is `MODELS_DIR` or `<state root>/models`, and `<MODEL>_URL` (`http://<model>:<port>`) for every model of the table.

The environment controls everything a deployment may change: replicas, strategy, domains, health paths, ports, balance per service type, timeouts, warmup, drain, retention, the verify window, timer intervals, metrics retention, PostgreSQL extensions, memory, CPU and connection limits, data-service credentials, integrations and the application runtime contract. `Bash.toml` keeps only what changes with the code, so changing it means a new bundle.

Validation reports every invalid key at once. The rules:

- A value with spaces or a line break around it is refused with `check how it was pasted`: a pasted secret otherwise fails far from its cause.

- Ports, counts and paths must be well formed.
- Images and every `<PART>_IMAGE` must be pinned by digest. Every domain in `<PART>_DOMAIN` and `GRAFANA_DOMAIN` follows RFC 1123; a domain and path pair is routed once; an image without a domain is ignored.
- The parts table is checked at every load: its columns, one server part, names, kinds, ports, paths (the readiness path under the part's path), statuses, balances, replicas, limits, mounts and the `{part}` references of its build variables, and `<PART>_DOMAIN` declared in `.env.example`.
- `DB_USER` must not be `postgres`. Production requires TLS. `HTTP3_ENABLED=true` requires `TLS_ENABLED=true`, the only HTTP/3 rule. `TLS_STAGING` is a boolean, and production warns while it is on.
- `MODELS` names models of the table, each once; `<MODEL>_MEMORY`, `_CPUS` and `_BATCH` follow the memory, CPU and count rules.
- Operator inputs that reach commands or mounts are checked as data: `TLS_EMAIL` an address, `HEALTH_CA` and `PORTAINER_CA` absolute paths (a comma could otherwise add mount options), `GITOPS_BRANCH` a Git reference, `BACKUP_REGION` a region name, `REGISTRY_NAMESPACE` a registry namespace, `SSH_HOST` and `SSH_USER` the forms SSH accepts, and `REMOTE_DIR` a path relative to the SSH home.
- Every integration is all-or-none: a partial offsite backup, trusted proxy, Telegram, Grafana, registry or GitOps group names its missing keys. GitOps without a permanent `REGISTRY_TOKEN` warns, because the server pulls private images itself. Rates read `REQUESTS/PERIOD` with `s`, `m` or `h`; path limits must not nest.
- `TRUSTED_PROXIES` takes CIDRs and https URLs only, `TRUSTED_HEADER` a header name. `DOMAINS_ENDPOINT` is an https URL, `DOMAINS_INTERVAL` a count of seconds (0 turns syncing off), `DOMAINS_MAX_DROP` a percentage; a partial dynamic-domain group warns and stays off, never blocks.
- Forced and role variables are `NAME=VALUE` words, the three role commands are required, `MIGRATION_POLICY=expand` requires the server part's `<PART>_MIGRATE_COMMAND`, mounts are absolute, GitOps paths are relative and distinct, and extensions are identifiers.
- Deploys require the data-service credentials, each password at least 16 characters. The application validates its own env file when it migrates and boots, before any switch.

### Parts

A part is one deployable surface: the api server, the super, admin, supplier, vendor and delivery panels and the client and tenant sites, and later any other surface. Each is its own image, Compose service, HAProxy backend pair and replica count; nothing groups them. They are known in exactly two places:

- **`src/config/parts.sh`**: the table, one row per part. `kind` is `server` (exactly one: the worker and scheduler roles, migrations, the storage volume, the data network and a required env file, run by the `<PART>_*` runtime keys of `.env.example`) or `site` (receives `PORT` and `HOSTNAME`). `port`, `path` (a prefix the part owns on its domains, `/` for the whole domain), `ready` (a path under it) and `expect` drive health checks and probes; `balance`, `replicas` (the default) and `limit` (`REQUESTS/PERIOD` per client address, `-` for none) shape the edge; `env_mount` is where the part's env file mounts (`-` for none); `source` is the path, from the repository root, whose presence makes the part buildable (`image available PART`); `dockerfile` names the recipe under `template/image/` and `build` its build variables, where `{part}` becomes that part's public URL.
- **`.env.example`**: `<PART>_DOMAIN`, a list separated by spaces or commas; every domain in it shares the row's settings, and an empty value leaves the part out. The table adds `<PART>_IMAGE` (a pinned digest, supplied by the deploy) and `<PART>_REPLICAS` (its default from the row) to the schema; declaring them in `.env.example` is refused.

Policies belong to the part, never to a domain: every domain of a part, fixed or dynamic, one or ten, shares its rate limit (one stick table per part, per client address), backends, balance, health check and path. A part with a fixed domain is routed (`ROUTED`: the edge and its certificates); a part with an image ships (`PARTS`: the release, its Compose files, health gates and snapshot) when it has a fixed domain or dynamic domains are on. A missing part never fails anything: the workflows skip a part without source, a failed build leaves its siblings to ship, `image resolve` reports a missing image instead of failing, and the deploy keeps the live release's image for a part with no new one, or leaves the part out when it never shipped; a routed part with no usable replica answers 503 (HAProxy's own answer for a backend without servers), and a part without a domain does not exist for the edge; only a release with no part at all is refused. The worker, scheduler and migrations run only when the server part ships.

Adding a part is a row in the table, its `<PART>_DOMAIN` in `.env.example` (and its value in the env files), and its entry in the image matrix of `deploy.yml` and `infra.yml`, which lists only the parts this repository builds (`api super tenant` today); the infrastructure itself supports every part of the table on any project. A part that needs a runtime env file adds its `<PART>_ENV_FILE` secret to `deploy.yml` and `release.yml`.

### Data services

`src/config/data.sh` is the one list of data services: `service module prefix names secrets` per row (`postgres postgresql DB DB_USER,DB_NAME DB_PASSWORD,DB_ADMIN_PASSWORD`, then RabbitMQ and Redis). Everything that walks the data services reads it: rendering (each module's `<module>-render` and `<module>-files`), health, volumes, `start`, the doctor, the release snapshot (`IMAGE_<SERVICE>` and every `<PREFIX>_*` key) and the change detection, which hashes the secrets and calls the module's `<module>-identity` when the names or secrets of that service moved. A new data service is a row, its module and its image in `Bash.toml`.

### Dynamic domains

Fixed domains live in `<PART>_DOMAIN`. Domains that appear at run time (a tenant's own domain, for example) come from `DOMAINS_ENDPOINT`, an https URL the infrastructure reads with `DOMAINS_TOKEN` as a bearer token. Dynamic domains are on only when the endpoint, the token and `DOMAINS_INTERVAL` above 0 are all set (3600 seconds by default); otherwise nothing syncs, no timer runs and the edge routes the fixed domains only. Where a domain is registered, who serves its DNS and whether a proxy sits in front are outside the infrastructure: it only routes and certifies what it is given.

- **The payload is config.** `src/config/domains.sh` holds `CONFIG_DOMAINS_SHAPE`, the jq program that turns the endpoint's JSON into `domain part` lines (by default `{"domains": [{"domain": "shop.example.com", "part": "client"}]}`), so a new payload shape is one line there and the endpoint's settings are the env schema: the two places that know the contract. Entries with an invalid host, an unknown part or a domain already routed are skipped with a warning; the list is the endpoint's to decide, the edge never second-guesses it.
- **Durations.** Every duration in the env files is in seconds with a short comment beside it (`BACKUP_INTERVAL=3600 # 1 hour`); an unquoted value ends at a space followed by `#`, as dotenv reads it, so a value holding ` #` is quoted.
- **Pull, never push.** `edge sync` (by hand, or the `domains` timer every `DOMAINS_INTERVAL` seconds) fetches the list, refuses one that drops more than `DOMAINS_MAX_DROP` percent of the current domains (at least one domain may always go; `--force` accepts it), issues the certificates of new registrable domains, writes the routed domains to `edge/domains.map` and reloads once, seamlessly, after `haproxy -c`. An unreachable endpoint, a payload outside the shape or a refused reload keeps the current domains serving; the application never touches the edge.
- **The edge.** With `DOMAINS_ENDPOINT` set every part of the table gets its backends, and a request whose host matches no fixed domain looks its part up in the map (`map_str`), so the part's policies apply to it; an unknown host answers 404, and ACME challenges pass for any host so a new domain is certified before it is routed. Deploys read the recorded map and never call the endpoint.
- **Certificates.** A run issues at most `CERTIFICATE_BATCH` new certificates (100), so a first list of a thousand domains spreads over runs and stays under the ACME rate limits; issuance holds its own lock (`certificates.lock`), never the deploy lock, and a deploy that finds it busy leaves certificates to the running sync. A failed issuance never blocks the others: its registrable domain waits `CERTIFICATE_RETRY` seconds. A certificate whose domains all left is kept `CERTIFICATE_RETENTION` seconds (7 days) before it is removed, so a domain that comes back needs no new issuance. The map routes a dynamic domain only once its certificate exists (with TLS on); until then it is pending and its ACME challenge still passes.
- **Cost.** The list is fetched with `--compressed`, and with `If-None-Match` once the endpoint sent an `ETag`: a `304` reuses the recorded list. `edge/domains.wanted` keeps the full list, `edge/domains.map` the routed part of it; lookups use associative arrays and a run reloads the edge once.

### Application env files

Each part owns one env file and nothing crosses: `product/infra/.env.production` holds every infrastructure control, `product/api/.env.production` is a complete copy of `product/api/.env` with production values, and the values both sides need (database, broker and cache credentials, the port) are repeated on purpose. The infrastructure never reads, writes or validates a key inside an application file; it receives the file, pins it, and mounts it.

- **Source.** `<PART>_ENV_FILE` carries a part's file content, plain or one base64 line: required for the server part, optional for a site, ignored for a part without `env_mount`. The content comes from that exported, non-empty variable, otherwise from `.env.<part>` beside the infrastructure env file, which `server stage` writes with mode 600. A missing server file fails the deploy; a site without one runs without it.
- **Checks.** At most 48 KiB, no NUL, no carriage return, not blank. Nothing else, because a dotenv line check would refuse values `python-dotenv` accepts.
- **Release.** The content is copied once into `releases/<release>/<part>.env`, mode 644 inside the 700 release directory so the non-root container can read it, and its SHA-256 is pinned as `<PART>_ENV_SHA256` in `release.env`. A changed file gives a new release name (or is refused under a pinned `RELEASE`), and a rollback mounts the file of the release it restores.
- **Mount.** A read-only bind to the part's `env_mount` (`/app/.env` for the api, which it loads as its base `.env`; `/app/product/web/.env` for the sites, the web's working directory). Values never pass through Compose `env_file`, so `$` and quotes keep their dotenv meaning and secrets stay out of `docker inspect` and Portainer.
- **Runtime contract.** The facts the infrastructure owns reach the containers as process variables, which outrank the file: the server part's `<PART>_FORCED_ENV` (bind address, port, storage root, migrations off), the per-role `<PART>_SERVE_ENV`, `_WORK_ENV` and `_SCHEDULE_ENV`, and `<PART>_RELEASE_VARIABLE=<release>`; a site gets `PORT` and `HOSTNAME=0.0.0.0`. The role commands (`<PART>_SERVE_COMMAND`, `_WORK_COMMAND`, `_SCHEDULE_COMMAND`, `_MIGRATE_COMMAND`) and `<PART>_STORAGE_MOUNT` are settings too, words split on spaces and `$` escaped for Compose. Emptying the forced variables leaves a pure pass-through.
- **Image builds.** A part's `build` variables are compiled in (the sites' `NEXT_PUBLIC_SPEC` and `SPEC_API_URL`), so a site's runtime file serves server-side code only. The image reference carries the first eight hex digits of their SHA-256 after the release tag (`<project>-<part>:<tag>-<digest>`), so a changed address builds a new image and an unchanged one reuses it.

## Command line

`infra help` groups every command by purpose (Release, Data, Operate, Edge and certificates, Server and runtime, GitOps and control plane, Images, Tool) with its usage and one line. `infra help COMMAND`, or `COMMAND --help`, prints the full manual: what it does, its actions, its flags in one aligned column, where it runs, notes (gates, notifications, timers) and examples. Headings are bold and command columns colored on a terminal, plain otherwise or with `NO_COLOR`. The manual lives as data in `app/native/commands.sh`, and a test proves every listed command has a function and every manual entry names a command.

Commands with actions (`backup edge tls firewall server docker timer portainer models image registry`) declare them once in `COMMAND_ACTIONS`, the default first, and dispatch through `native-dispatch`. The dispatch, the overview usage (`backup [create|list|verify] [BACKUP]`) and the manual's Actions section all read that table, so the help cannot drift from what the code accepts, and a test proves every action has its function. A mistyped action names the closest one and the alternatives (`Unknown backup action: lst; did you mean list? (expected create, list or verify)`), and a routed command checks its action here before opening an SSH connection.

- Global flags: `--config FILE` (repeatable), `--project DIR`, `--target HOST`, `-e KEY=VALUE` (repeatable), `--local`, `-h/--help`, `--version`.
- Command flags are declared per command and checked before anything runs: `deploy --list` fails with `deploy does not take --list; see infra help deploy`. A flag declared with a value (`--token TOKEN`) takes `--token X` or `--token=X`. Flags after `--` belong to the remote command of `server run`.
- Server commands (`deploy rollback recover backup restore status doctor scale start stop uninstall monitor logs models edge tls firewall timer reconcile watch portainer`) run on `SSH_HOST` when it is set: the arguments and flags travel to a detached `server run` job, the server reads its staged settings, and `-e` overrides travel with that one command over SSH stdin (never `SSH_*` or `REMOTE_*`, never argv), so `infra -e API_REPLICAS=4 scale` scales the server. `deploy` first stages the bundle, the settings and the application env files and applies the edge; `deploy --dry-run` stages nothing. `--local` runs any of them here. On the server the staged settings carry no `SSH_*`, so the same command runs locally there. CI therefore needs only `ENV_FILE`, `API_ENV_FILE` and the `SSH_*` variables to call `infra deploy`, `rollback`, `restore` or `backup`.
- A mistyped command suggests the closest one by edit distance (`rolback` → `did you mean rollback?`).
- Commands that interrupt or remove require `--force`: `stop`, `uninstall`, `restore`, `recover` and `firewall apply`.
- `config` prints every setting with its source (`defaults file process cli release gitops derived manifest`), `--changed` keeps only overrides, and secrets print as `[redacted]`.
- `logs SERVICE [--since TIME] [--tail LINES]` finds the service in the live release, the data, the edge, the models or the monitoring and prints its logs with timestamps, every secret of the settings replaced by `[redacted]` line by line; secrets only an application env file holds are unknown to it.
- `doctor` runs read-only checks (runtime commands from `Bash.toml [requires]`, Docker and Compose versions, settings, env files, disk, edge, certificate, data services, models, release state, backup age, WAL archiving and the oldest point in time, timers and linger, channels, and containers of `<project>-*` Compose projects that are neither a slot, the data, edge, models, monitor nor control) and prints ✓, ! or ✗ with the next step; a ✗ exits non-zero. On rootless Docker with published ports it warns that RootlessKit's port forwarding shows every client as the network gateway (logs, `RATE_LIMIT_IP` and `TRUSTED_PROXIES` then act on one address) and points at the relay mode; rootful Docker, which `docker install` sets up, keeps client addresses.
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

| Settings                                                                     | Effect                                                                                                                                                                         |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `BACKUP_URI`, `BACKUP_KEY`, `BACKUP_SECRET`                                  | Every dump and its checksum are also copied to `s3://` (AWS, or `BACKUP_ENDPOINT`) or `gs://` (Google Cloud Storage HMAC keys) under `sql/`, and the WAL archive under `wal/`. |
| `DOMAINS_ENDPOINT`, `DOMAINS_TOKEN`, `DOMAINS_INTERVAL` above 0              | The edge also routes the domains the endpoint lists, each to its part, and certifies them (see Dynamic domains).                                                               |
| `TRUSTED_PROXIES`, `TRUSTED_HEADER`                                          | A proxy or load balancer in front of the hosts: the edge takes the client from the last address in `TRUSTED_HEADER` only on connections from the listed ranges.                |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SLACK_WEBHOOK_URL`, `WEBHOOK_URL` | Each configured channel receives the infrastructure events (see Notifications); Telegram and Slack also receive the Alertmanager alerts.                                       |
| `GRAFANA_DOMAIN`, `GRAFANA_PASSWORD`                                         | The monitoring stack runs and Grafana is routed through the edge and the certificates.                                                                                         |
| `RATE_LIMIT_GLOBAL`, `_IP`, `_PATHS`, a part's `limit`                       | HAProxy stick-table limits answer `429` with `Retry-After`; ACME challenges are exempt.                                                                                        |

## Native stack

Projects and boundaries:

- `<project>-data`: PostgreSQL, RabbitMQ and Redis on an internal network, guarded by a fingerprint. A change of their settings is treated as an incident and applied by the next deploy, whatever else changed: the deploy saves a dump, cuts every connection and applies the change inside the running service (PostgreSQL: the application role goes `NOLOGIN`, its sessions are terminated, the role and database are renamed when their names changed, and the new passwords are set with `log_min_error_statement=panic` so no statement reaches the server log; RabbitMQ: the user is imported with a salted SHA-256 hash over stdin, then the old user is deleted or its connections closed; Redis: its configuration), recreates the changed services and announces `data.changed`. No credential crosses argv; the infrastructure records only hashes of the passwords (`data/identity`). A PostgreSQL major upgrade is refused, because a restart cannot convert the data; it needs a planned dump and restore. A retained release still holds the old credentials, so a rollback across a credential change fails its readiness and is refused.
- `<project>-edge`: HAProxy. The edge and control plane are never recreated by an application deploy.
- `<project>-<release>`: every routed part (one `part-<name>.yaml` each), plus the server part's worker and scheduler.
- `<project>-control`: Portainer.
- `<project>-monitor`: Prometheus, Grafana, node and PostgreSQL exporters, and Alertmanager when Telegram or Slack is configured.
- `<project>-models`: the self-hosted models `MODELS` names, one `model-<name>.yaml` each, on the internal `<project>-models` network that every server part and its worker and scheduler join.

Networks and volumes carry an `io.infra.owner` label and are refused when another owner holds the name. Every container runs non-root (data services as uid 999), read-only, with `cap_drop: [ALL]`, `no-new-privileges`, pid and memory limits, `nofile 65536` where sockets matter, and local log rotation. No scalable service has `container_name` or a host port.

The release Compose files interpolate `${<PART>_REPLICAS}`, `${WORKER_REPLICAS}`, `${DEPLOY_SLOT}` and `${RELEASE_ROOT}` at run time. One rendered release therefore serves native Compose and Portainer, any slot and any replica count, and its snapshot (`release.env`) changes only when application inputs change.

### Edge

HAProxy 3.4.7 LTS (AWS-LC, QUIC) terminates TLS 1.2/1.3 with Mozilla intermediate ciphers, `X25519MLKEM768:X25519:P-256:P-384` curves, no session tickets and strict SNI over `/etc/haproxy-tls/certs/`, one PEM per registrable domain.

- **Routing:** each part's domains and path select it once per request (`txn.part`), the longest path first, so `example.com/desk` reaches a part mounted at `/desk` and `/desktop` does not; an allowed host with no matching part answers 404. The candidate frontend selects the same way.
- **Certificates:** every routed domain is grouped by its registrable domain from the Public Suffix List (ICANN section, `example.com.eg` and `example.co.uk` included), and each group is one ACME lineage named after it with its domains as names (`--cert-name example.com -d api.example.com -d example.com`). Edge prepare and apply issue the groups that are new or changed, keep an imported one, remove the certificates no route uses and reload; `certificates` in the state root records each group. `tls import CERT KEY` installs a certificate for the registrable domain its names belong to. `TLS_STAGING=true` issues from the Let's Encrypt staging CA for labs; the record marks such a lineage (`@staging`), so turning it on or off reissues every lineage with `--force-renewal`. A first TLS edge starts plain to answer HTTP-01, then renders TLS, recreates and reloads, so a relay socket serves the TLS configuration at once.

- **HTTP/1.1 and HTTP/2:** run on TCP 443 with ALPN `h2,http/1.1`.
- **HTTP/3:** with `HTTP3_ENABLED=true` (the default), `bind quic4@:8443 … ssl-min-ver TLSv1.3 alpn h3` on the frontend only, `Alt-Svc h3=":<port>"; ma=86400`, and UDP published on the same port. Clients fall back to TCP. Backends stay HTTP/1.1, and 0-RTT is never enabled.
- **Relay mode:** a non-empty `EDGE_SOCKETS` directory replaces the published ports with `unix@/sockets/http.sock` and `https.sock`, `mode 666 accept-proxy`, for a TCP relay (nginx stream with `proxy_protocol on`) that owns `HTTP_PORT` and `HTTPS_PORT`. The PROXY header carries the real client, HTTP/3 and Alt-Svc are off because the relay owns UDP, and the redirect still targets `HTTPS_PORT`. Emptying `EDGE_SOCKETS` returns to published ports with HTTP/3, without another change. The edge runs as uid 1000; `edge apply` and `doctor` prove the directory is writable for it and print the exact `setfacl` grant otherwise (rootless Docker maps uid 1000 to the user's subordinate start + 999). Public probes and the certificate check then speak the PROXY protocol to the socket from a curl container.
- **Trusted proxies:** with `TRUSTED_PROXIES` and `TRUSTED_HEADER`, `http-request set-src req.hdr_ip(<header>,-1)` runs only on connections from the listed ranges, so logs, `X-Forwarded-For` and per-IP limits see the visitor whichever proxy or load balancer is in front (its client header, or `X-Forwarded-For`, whose last address is the one the proxy saw). A malformed value keeps the peer address. Lists published at https URLs are fetched by `edge apply`, every CIDR in the body extracted, validated and sorted, and recorded with their source; deploys render from the record and never depend on the network, an unreachable list keeps the record, and a changed source is fetched again. Behind the relay the PROXY header supplies the peer, so both layers compose.
- **Security behavior:** Host allowlist (404 otherwise), 308 HTTP to HTTPS, HSTS two years, overwritten `X-Forwarded-For`, a UUIDv7 `X-Request-ID`, `nosniff`, an `X-Release` header and no `Server` header, set through `http-after-response` so generated responses carry them too.
- **Logs:** JSON log lines record the path without the query string (`%HP`).
- **Discovery:** each service gets `server-template replica 1-32 <service>-<slot>:<port>` through the Docker resolver.
- **Health:** active `GET <ready>` checks with the part's first domain as `Host` expect the part's `expect` status. Settings are `inter 2s fall 3 rise 2 slowstart 10s`.
- **Never routing to unready replicas:** `init-state fully-down` keeps a discovered replica out until it passes `rise` checks.
- **Failure handling:** `observe layer7 error-limit 10 on-error mark-down` is the passive circuit. `maxconn`/`maxqueue` per server provide fail-fast back-pressure. `retry-on conn-failure empty-response` with `option redispatch 1` and `timeout connect 1s` handles retries on the local bridge.
- **Timeouts:** `tunnel 1h` for WebSockets, `client-fin` and `server-fin`, and `hard-stop-after 1h` with `expose-fd listeners` for seamless reloads.
- **Rate limits:** `sc0` global, `sc1` per client address within a part (its `limit`), `sc2` per client address and `sc3` per path prefix, each in its own stick table sized to twice its period, evaluated after the Host allowlist and the part selection.
- **Static routes:** Grafana is a single-server backend outside the blue/green slots, so candidate probes never depend on it.
- **Admin surfaces:** the Runtime API listens on 127.0.0.1:9999 inside the container only. Prometheus `/metrics` and `/live` sit on :9090 on the apps network, and on host loopback when `METRICS_ENABLED=true`.

The live map `active.map` selects `slot:release`, switched atomically through the Runtime API and persisted on disk. A candidate frontend (8081/8444, header `X-Slot`) reaches the inactive slot from the apps network only.

### Deploy, rollback and draining

`deploy` validates, locks `STATE_ROOT/lock` and records every phase in `phase` and `audit.log`. The sequence:

1. Preflight edge drift; a changed edge needs `edge apply` first. `edge apply` refuses a new path, readiness path or port of a part while the live release pins the old value, because the live slot would fail its health checks until the next release switches in; ship a release that serves both, or accept the gap with `edge apply --force`.
2. Retire the inactive slot, but only after `RETENTION_SECONDS` since the active release went live and only when HAProxy reports zero sessions on it within `DRAIN_TIMEOUT`.
3. Render or verify the immutable release.
4. Log in to the registry when `REGISTRY_TOKEN` is set, pull digest-pinned images, log out, check memory and disk capacity, then ensure networks, volumes, data and the `DB_EXTENSIONS` (pgvector) as the local superuser.
5. Migrate with the server part's `<PART>_MIGRATE_COMMAND` when `MIGRATION_POLICY=expand`, reading the release's env file. An interrupted migration refuses to rerun.
6. Start the candidate front, wait for healthy containers with the right image, then pass HAProxy readiness and an HTTPS probe through the candidate frontend.
7. Warm up and probe again.
8. Switch the map, move worker and scheduler, and verify the release header on the public port. Without `EXTERNAL_HEALTH_URL` the probe resolves the server part's first domain to the local bind address, so it checks the real certificate and SNI without depending on hairpin NAT; set `EXTERNAL_HEALTH_URL` for a check through public DNS.

9. Verify for `VERIFY_SECONDS`: every replica healthy with the right image and the public probe answering, checked every `VERIFY_INTERVAL`. `VERIFY_FAILURES` consecutive failures roll back to the retained previous release automatically, or record `degraded` when none exists.
10. Converge monitoring (a fingerprint recreates it only when its files change, and `GRAFANA_PASSWORD` is reapplied) and install the monitor, backup and renew timers from the release bundle. Neither can fail a live release.
11. Converge the models (`models apply`) for every intent, the no-change deploy included, so a `MODELS` change alone takes effect; a failure warns and notifies `models.failed` and never touches the release.

Any failure before the switch restores the origin slot and background services and records `rejected`. An unrecoverable restore records `recovery-required` and keeps the pending state. Every outcome is sent to Telegram when configured, and so is a manual `rollback`: ↩️ when a pending release is rejected or the retained one is live again, 🆘 when it fails.

A release that failed its migration, readiness or verification, or that a rollback left behind, is remembered under `rejected/` with the reason. `deploy` refuses it and `reconcile` skips it until a new release or `deploy --force`. Asking for the retained previous release switches back to it in seconds instead of redeploying it.

`manual` stages without switching until `deploy --force`. Redeploying the current release is idempotent. `rollback` rejects a pending candidate, or switches back to the retained previous release after checking its slot was not reused. `scale` drains replicas above the target in HAProxy, waits for idle, then lets Compose remove them. Data services and the scheduler never scale. `recover --force` removes only a dead-owner lock. Long-lived WebSockets stay on the old slot after a switch, and retirement refuses while they live. Schema rollback is never attempted, so application rollback needs backward-compatible expansion migrations.

### Monitoring

Prometheus scrapes the edge, RabbitMQ, the PostgreSQL exporter, node exporter and itself, and evaluates twelve rules: edge down, no API replica, 5xx share above 2%, slow answers, a queue not draining, broker or database unreachable, disk or memory exhausted, a missing backup, an expiring certificate and a degraded platform. Grafana provisions the Prometheus datasource and the `Platform` dashboard read-only. Exporters and Alertmanager sit on a private network; Prometheus joins apps and data to scrape. Volumes are chowned to the runtime user with copy-up disabled, secrets are mode-600 files mounted one by one, and every container is read-only with all capabilities dropped.

### Models

Self-hosted models run beside the stack, outside the release slots, so a deploy never waits on a model and a model never pins a release. `src/config/models.sh` pins them in three tables:

- **Runners:** the image (a `Bash.toml` digest: `tei` for Text Embeddings Inference, `llamacpp` for GGUF models), its port, health path and arguments with `{port}` and `{batch}` placeholders.
- **Models:** the runner, the source as `SCHEME:LOCATION` (`huggingface:BAAI/bge-m3`), the revision (a commit), the default memory, CPUs and batch, and fixed arguments. Each row registers `<MODEL>_MEMORY`, `<MODEL>_CPUS` and `<MODEL>_BATCH` in the schema, as the parts table registers its keys.
- **Files:** every file a model needs with its size and SHA-256. Pickle formats (`.bin .pt .pth .pkl .ckpt` …) are refused at load, because loading them runs code; safetensors, GGUF and ONNX only.

`MODELS` (spaces or commas) names the ones to serve; empty serves none. `MODELS_TOKEN` reaches gated repositories. The scheme picks a module driver (`huggingface-url`), and `net-fetch` downloads each file into `MODELS_ROOT/<model>/<revision>/<file>` (directories 755, files 644, so the unprivileged runner reads them on rootful and rootless Docker), resuming partial files. A `<revision>.verified` stamp beside the directory records the files table; with it and every size right, a run fetches and hashes nothing. Without it each file is hashed, a differing one fetched again, a file the table does not list removed, and the space checked first (missing bytes plus 1 GiB). Once a revision verifies, the older revisions of that model are deleted.

Each model container runs read-only as uid 65534 with every capability dropped, `no-new-privileges`, its own memory, CPU and pid limits, `HF_HUB_OFFLINE=1`, a tmpfs `/tmp` and its directory bound read-only at `/model`, on the internal `<project>-models` network: no egress, reachable only by the server parts at `<MODEL>_URL`. Health is a curl container on that network against the runner's health path; `models apply` waits up to `HEALTH_TIMEOUT` for every model, after checking that the unreserved Docker memory covers them. `models status` prints the cache and container state, `models verify` hashes everything again, `start` brings the models back, `uninstall` removes their containers and keeps the cache, `monitor` turns degraded when a model fails its health check, and `doctor` checks the cache and the health.

### Backup and restore

`BACKUP_ROOT` (`BACKUP_DIR`, or `<state root>/backups`) holds two folders, mirrored under `BACKUP_URI`: `sql/` for the logical dumps and `wal/` for the point-in-time archive.

`backup` dumps the application database (`pg_dump --format=custom`) into `sql/`, refuses an archive whose catalog does not read back, writes a SHA-256 beside it, records it as `latest`, copies both to `BACKUP_URI/sql/` when set (the pinned `aws-cli` image, `gs://` through the S3-compatible endpoint `storage.googleapis.com`), and removes dumps older than `BACKUP_RETENTION` except the latest.

With `BACKUP_WAL=true` (the default) PostgreSQL archives every finished WAL segment into `wal/archive`, and at least once a minute (`archive_timeout=60`), so a local restore can reach any second up to about a minute ago. Archiving is always configured in the data stack and acts only while `/wal/enabled` exists, so `BACKUP_WAL` switches it on and off on the next deploy or backup without touching the fingerprinted data settings or restarting PostgreSQL. The `wal/` folder belongs to the PostgreSQL user (uid 999) with mode 700, and every operation on it runs inside a container as that user. Each `backup` then takes a base backup into `wal/base/<stamp>` (`pg_basebackup`, tar and gzip, WAL from the archive), records its first WAL segment from the backup manifest, removes base backups older than `BACKUP_RETENTION` except the newest, and `pg_archivecleanup` drops the segments the oldest kept base no longer needs. `backup archive` copies `wal/` to `BACKUP_URI/wal` with `aws s3 sync` as uid 999, and the archive timer runs it every `BACKUP_ARCHIVE_INTERVAL` seconds (300 by default) when `BACKUP_URI` is set, so the offsite copy lags by at most that interval. Offsite copies never delete: a sync from an emptied server cannot wipe the bucket, so retention there is a bucket lifecycle rule. The host path of the archive is fixed when the data services are created; host-side commands read it from the running PostgreSQL mount, so a later `BACKUP_DIR` change never splits the archive. The backup timer runs it every `BACKUP_INTERVAL` seconds. Telegram receives 💾 with the name and size, or 🔴 on failure. `backup list` prints the dumps newest first, and `backup verify [BACKUP]` restores one into a scratch database, counts its tables and drops it, proving it restores without touching live data. Only the database is backed up: the edge, certificates, the control plane and releases are recreated by their commands, and the env files live in GitHub secrets.

`restore --at TIME --force` restores the whole cluster to a UTC moment (`YYYY-MM-DDTHH:MM:SSZ`) under the deploy and backup locks: it saves the live database as a dump, stops the worker, scheduler and PostgreSQL, moves `PGDATA` aside as `PGDATA.before-<stamp>`, unpacks the newest base backup finished before the moment, and starts PostgreSQL with `recovery_target_time` and a `restore_command` reading the archive. Once it promotes, the recovery settings are reset and PostgreSQL restarts once to drop them from memory, the worker and scheduler start, the public probe answers, and a new base backup anchors the new timeline. If PostgreSQL stops during recovery (the archive ends before the moment, for one) the previous data directory is moved back and started, so a failed attempt changes nothing. The API answers 503 while PostgreSQL is down. A lab restored deleted rows to the second, twice in a row (timelines 2 and 3), and a moment beyond the archive failed and put every row back, the unarchived one included.

`restore [BACKUP] --force` takes a dump by name, the latest by default, under the deploy and backup locks:

1. Verify the checksum, then save the live database as a new backup, which becomes the latest.
2. Restore into `<db>_restore_<stamp>`, with the declared extensions created by the superuser first and the extension entries skipped from the dump catalog (only their owner may comment them), as the application role. The live database keeps serving.
3. Stop the worker and scheduler, disallow connections to the live database, end its sessions, rename it to `<db>_before_<stamp>` (connections stay disallowed) and give the restored copy the live name, owner and `CONNECT` grant.
4. Start the worker and scheduler, wait for the public probe, and send ♻️.

A failure before the rename drops the copy and leaves the live database unchanged, and the channels receive 🔴. Running `restore --force` again restores the pre-restore backup, which undoes it. API replicas reconnect by themselves: a lab restore under a health probe every 50 ms lost 4 of 362 probes, and under 600 requests per second the swap failed requests for about 3 seconds while the pools reconnected; the copy itself cost nothing.

`monitor` skips while a deployment holds the lock. It checks replicas, data, the public endpoint, the backup age and the certificate expiry, writes `metrics/platform.prom` for node exporter, and alerts only on a change between healthy and degraded.

### Delivery

Delivery is two workflows. Auto or manual, who may deploy and from which ref are repository policy, kept in the workflows and repository variables; the infrastructure only executes the command it is given:

- **`release.yml`**, on a `v*` tag on main: every gate, then the GitHub release (the version), then, with `DEPLOY_AUTO=true` and only once the release published, its `deploy` job calls `deploy.yml` with the tag (what is live is recorded by the `production` environment, not the release page), passing the secrets by name; the `production` environment must then admit `v*` tags beside main.
- **`deploy.yml`**, dispatched by hand from main with a tag and `deploy`, `rollback`, `backup` or `restore`, or called by Release: a secret-free `plan` job checks the trigger (a dispatch from main, a call from the tag's own ref), that `github.actor` and `github.triggering_actor` are both in `DEPLOY_ACTORS` (the repository owner by default), the tag and the dump name. The plan also proves the tag is on main. For `deploy`, an `images` job in the `production` environment runs once per part of its matrix, in parallel: one step reads `ENV_FILE` and keeps only what the part's image depends on (`infra image inputs PART`: the project, the TLS port settings and the domains its `{part}` build variables name), skips a part without a domain, and the next builds, scans with Trivy and pushes that one image with the job token through `infra registry push`, which owns the push retry; `infra image reference PART TAG` names it, so an existing reference reuses its digest through `image remote`. It holds no SSH key. A `mode` job then reads `GITOPS_URL` and pins every routed part's digest from the registry (`infra image resolve TAG`) with read-only packages. With GitOps a `publish` job, the only one with `contents: write` and holding no SSH secret, commits the desired state; otherwise the `deploy` job, read-only and one at a time in the same environment, runs the routed command, and `deploy` stages the settings and applies the edge on the server before shipping. A `notify` job posts the run link to every configured channel when any of them failed.

Push or pull follows `GITOPS_URL` in `ENV_FILE`:

- **Push** (empty) keeps no permanent token anywhere: the job's `GITHUB_TOKEN` becomes the registry credential for GHCR, `server stage` never writes credentials that came from the process environment, and `server run` hands them to that one remote command over SSH stdin. A permanent read-only `REGISTRY_TOKEN` in `ENV_FILE` wins instead, for servers that pull by themselves. The application env files travel as `.env.api` and `.env.web`, never inside `.env.production`. Automatic rollback and `rollback` need no token.
- **Pull** keeps a read-only `GITOPS_TOKEN` and a `read:packages` `REGISTRY_TOKEN` on the server, and `GITHUB_TOKEN` fills both for `https://github.com/` repositories and GHCR when they are empty. `publish` commits `deploy/application.yaml` and `deploy/desired.env` to `GITOPS_BRANCH` (a dedicated branch) and tags `release-<RELEASE>` in one atomic push, idempotently; a tag that holds another desired state is refused. Rolling back means publishing the previous tag. The desired state carries `VERSION` and every routed part's `<PART>_IMAGE` and `<PART>_ENV_SHA256`, and `reconcile` waits while the staged env files or the server's settings revision differ from them, so new code never runs with an old env. The reconcile timer is installed whenever `GITOPS_URL` is set.

Secrets: `ENV_FILE` (the infrastructure env), `API_ENV_FILE` and optionally `SUPER_ENV_FILE` and `TENANT_ENV_FILE` (the env files of the parts RagX builds today), plus `SSH_HOST`, `SSH_USER`, `SSH_KEY` (a dedicated deploy key, `restrict` is fine) and `SSH_KNOWN_HOSTS`. Repository variables: `REGISTRY_DRIVER` and `REGISTRY_NAMESPACE` default to GHCR and the owner, `DEPLOY_ACTORS` lists the logins allowed to deploy, and `DEPLOY_AUTO=true` deploys every released tag. The workflows name every secret literally: indexing `secrets` by a computed name hands the runner every secret (zizmor `overprovisioned-secrets`).

### GitOps and control plane

`export` needs no application secrets: it renders only the Compose files and writes a secret-free `application.yaml` with variables kept and no host path, plus `desired.env` (`VERSION`, `RELEASE`, `MIGRATION_POLICY`, `COMPOSE_SHA256`, `RELEASE_REF`, and every routed part's `<PART>_IMAGE` and `<PART>_ENV_SHA256`); the gitops module knows no key of its own, the app hands it the list.

`reconcile` reads the desired branch through the askpass vault, checks out the protected `refs/tags/release-*` tag, and requires the tagged desired state to match the branch and the Compose checksum. It then creates the Portainer Git stack with the replica and slot variables and verifies `GitConfig.ConfigHash` equals that commit before the gates and the switch. `watch` repeats it; a `timer` can too. Portainer auto-update and webhooks stay off, because a Compose update alone is no blue/green.

`portainer install` runs CE 2.45.2 on loopback 9443 with `-H unix:///var/run/docker.sock`, so local environment 1 exists. It also:

- mints a private CA and a `localhost`/`127.0.0.1` server certificate, then deletes the CA key;
- feeds the admin password and the encryption key as files, and refuses a changed key;
- creates an API key into `control/secrets/api-key`.

Later commands fall back to that CA and key when `PORTAINER_CA`/`PORTAINER_TOKEN` are empty. `portainer registry` registers the pull credential (GHCR as custom type 3, Docker Hub type 6). The control plane holds the Docker socket and is a host administrator; reach it through SSH forwarding only.

## Runbook

1. Provision Docker 29.9.1 and Compose 5.6.0 (`docker install` covers Ubuntu 24.04 amd64 from checksummed packages and refuses to replace a runtime), plus Bash 5, curl, git, jq and openssl.
2. Write the private env file: `PROJECT`, `VERSION` (or a pinned `RELEASE`), every part's `<PART>_DOMAIN`, `BIND_ADDRESS`, TLS settings, data-service credentials, `REGISTRY_*` pull credentials, `GITOPS_*` read credentials and the `PORTAINER_ADMIN_PASSWORD`/`PORTAINER_SECRET_KEY` pair.
3. Export `ENV_FILE`, `API_ENV_FILE` (`"$(< ../api/.env.production)"` or one base64 line) and the `SSH_*` variables, then run `server stage`, which uploads the release bundle, `.env.production` and `.env.api` with modes 700, 600 and 600. Server commands then run there by themselves; `server run -- COMMAND` runs anything else, remote flags after `--`.
4. Run `registry login`, `portainer install` and `portainer registry`. For TLS, the domains must reach the edge on port 80 before HTTP-01 (`tls issue`), or use `tls import CERT KEY`; where a domain points and who serves its DNS is outside the infrastructure. Open TCP 80/443 and UDP 443 in the cloud firewall (TCP only behind a relay); `firewall ports` lists them and `firewall apply --force` updates an active ufw/firewalld. Behind an nginx relay, create `EDGE_SOCKETS` with the grant `doctor` prints and point the relay at it:

   ```nginx
   stream {
       server { listen 80;  proxy_pass unix:/srv/edge/http.sock;  proxy_protocol on; }
       server { listen 443; proxy_pass unix:/srv/edge/https.sock; proxy_protocol on; }
   }
   ```

5. Run `export DIR`, commit `deploy/application.yaml` and `deploy/desired.env`, and push a protected `release-<RELEASE>` tag. Then `reconcile`, or `deploy` with `DEPLOY_DRIVER=compose`.
6. Check with `doctor` and `deploy --dry-run`, then operate with `status`, `scale`, `rollback`, `edge apply`, `backup [list|verify|archive]`, `restore [BACKUP] --force`, `restore --at TIME --force`, `monitor`, `notify MESSAGE`, `timer install|remove|list`, `publish`, `image remote REF` and `recover --force`. User timers outlive the SSH session only with `loginctl enable-linger`.

Images are built with `image build PART REFERENCE` from the repository root two levels above `product/infra`, with the recipe and build variables of the part's row, so the api image installs `engine/python` as a wheel and each site image links `engine/bun` beside the surface; every `ARG` of a recipe is filled by the infrastructure (`<NAME>_IMAGE` from `Bash.toml`, `BUILD_ENV` from the row) or refused. Deploys pin them with `image resolve TAG` (or `-e <PART>_IMAGE=…`); the release pipeline publishes them.

## Verification

The gate is `bash src/main.sh test --check` with `PATH="${PWD}/target/tools:${PATH}"` so the pinned ShellCheck runs (`src/main.sh prepare` installs it): bash syntax, ShellCheck at the pinned version over the bundle, the laws above, and 82 isolated tests. The tests cover:

- literal data, refusals and grammars; the TOML subset (trailing comments, dotted and duplicate tables, leading zeros, escapes) and keys kept in file order; every embedded asset equal to its file, with or without a final newline;
- precedence, schema and validation; the env file chain, `ENV_FILE` plain and base64, `parse-content`, and `GITHUB_TOKEN` filling the GHCR and GitHub credentials while staying transient;
- redaction in every output and secrets kept out of argv for SSH, curl, git, the `aws-cli` container (`s3://` and `gs://`) and Docker; SSH material given as content or base64, the `auto` method and refused paths;
- atomic failures, locks and state;
- bundle determinism and release isolation;
- render immutability, edge protocols and stats parsing, with Runtime API refusals read from the first reply line only, so a health-check reason such as `File not found` inside `show stat` stays data; relay binds on `unix@` sockets with no published port and no QUIC, firewall ports and protocols per mode, and the trusted-proxy `set-src` rules from literal and fetched ranges, the recorded fallback and a changed source;
- GitOps payloads, export relocation and the control-plane CA and API key;
- application env files passed through byte for byte, mounted read-only and pinned by digest, unsafe variable names refused unevaluated, staged beside but never inside the infrastructure settings, and reconcile waiting for a stale server env;
- release names derived from `VERSION` and the settings revision, kept by operational changes, moved by env and pinned changes, and overridden by an explicit `RELEASE`;
- backup naming, checksum, notification and listing in `sql/`; the WAL switch, the base backup and its start segment computed from the manifest LSN and the segment size, retention and the offsite sync as uid 999 without `--delete`; the restore flow, its failure path and refusals; the point-in-time restore (base selection, the moment's grammar, the recovery, restart and new base, and the data put back when recovery fails); the readiness guard; the swap SQL with psql-quoted names; extension entries skipped from the dump catalog;
- the remote job protocol run end to end through a fake SSH: the exit status, a dropped connection, a start lost before the job existed (run once more, exactly once), a start cut off after its claim (reported, never repeated), a job that never started, an unreachable host, `-e` overrides forwarded without the SSH target, and an unknown action refused before any connection;
- transient credentials kept out of staged settings and forwarded over stdin, rejected releases refused by deploy and skipped by reconcile, the instant switch to a retained release, delivery settings;
- the command line: flags with values, flag validation per command, routing of server commands over SSH with their arguments and flags, suggestions for commands and actions, the overview and per-command manual with its Actions section and aligned flags, `--version`, `config` with sources, and a manual that matches the dispatch action by action;
- notifications on all three channels with secrets out of argv, `notify` flags limited to one channel and validated like settings, the webhook signature checked against OpenSSL, retries, silent success without channels, and every raised event declared; the deploy plan for each decision; the doctor checks; backup verification;
- rate-limit and static-route rendering, integration groups, the monitoring render, verification thresholds, automatic rollback outcomes, monitor transitions and PostgreSQL extensions;
- the parts table and its refusals on a fixture table, domain lists split on spaces and commas, routes refused twice, part selection by the longest path, per-part limits and Compose files, release snapshots that switch off the parts they lack, image references that follow their baked addresses, and the registrable-domain grouping (`com.eg`, `co.uk`, wildcard and exception rules); dynamic domains (the on switch, the payload shape, skipped entries, the bearer token kept out of argv, compression and `ETag` revalidation, the drop guard and `--force`, routing only certified domains, a refused list changing nothing) and certificates (the per-run batch, the retry wait, retention before pruning, imported ones kept, a busy lock skipped and a dead one recovered); inline comments after unquoted env values; data settings changes (a dump first, the PostgreSQL and RabbitMQ commands with no credential in argv, recreated services, a refused major upgrade); the first TLS edge reloading after its plain bootstrap; staging certificates and the reissue when `TLS_STAGING` flips; values pasted with spaces or line breaks;
- the models tables and their refusals (pickles, unsafe paths, duplicates, names taken by a part, unknown runners), the registered inputs and runner arguments; `net-fetch` (resume after a cut transfer, an oversized partial discarded, a checksum mismatch deleted, no total time limit, the token out of argv); `models apply` end to end on fixture files (the fetch URLs, modes 755 and 644, the stamp that skips a second fetch, verify fetching only the differing file, an unlisted file removed, older revisions pruned, the hardened Compose file, the memory and space guards, `models.failed` without touching the release, removal when `MODELS` empties); `logs` (service lookup, flags, redaction); the orphan-project doctor check.

CI runs the gate on Ubuntu and macOS, then builds and scans the images; a release builds them once per tag, and Deploy reuses them by digest.

`benches/results.json` is the evidence: every lab with its date, host, commands and numbers. Proven there on real hosts: HTTP/2 and HTTP/3 through the edge (HTTP/3 keeps 1.3x–1.7x HTTP/2 throughput at 1–3% loss for 15–25% more edge CPU); blue/green, instant switch-back (7 s) and automatic rollback (16–18 s) under load without a failed request; scaling, replica crash and hang; rejected candidates and every guard (retention, draining, locks, stale lock, edge drift, memory); backup, verify, restore by name and point-in-time restore including its failure path; relay mode behind an nginx stream with real client addresses; trusted proxies from literal and fetched lists; private GHCR, Portainer GitOps, reconcile and publish; env separation (read-only 644 files, nothing in `docker inspect`); a dropped SSH client reattaching to a running deploy; the release and deploy workflows end to end on GitHub. Known limit: readiness paths and ports render from staged settings, so changing them is guarded (`edge apply --force` accepts the gap). The part selection, path boundaries and a 404 for an unrouted host were exercised against HAProxy 3.4.7, and `haproxy -c` accepts the rendered configuration with a certificate directory, QUIC and every limit; per-domain certificate issuance against Let's Encrypt is unverified.

Still unverified: a successful `gs://` upload with real HMAC keys, Telegram with a real bot, Docker Hub with real credentials, Let's Encrypt and public UDP through a cloud firewall, a rootful fresh host. A capability is claimed only after its success and failure paths were observed.

References: [HAProxy 3.4](https://docs.haproxy.org/3.4/configuration.html), [Portainer CLI](https://docs.portainer.io/advanced/cli), [Portainer Git stacks](https://docs.portainer.io/user/docker/stacks/add), [Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Traps

- ShellCheck SC2178/SC2190 fire when a variable name is an array elsewhere in the bundle: rename it. Never pipe a docker or infra command into `head` or `grep -q` under pipefail (the early exit fails the writer and the pipeline); capture the output, then match it.
- Rootless Docker maps container uid 1000 to host subuid start + 999; HAProxy needs a writable socket directory for that uid. Its port forwarding shows every standalone client as the bridge gateway, so per-IP limits, logs and `TRUSTED_PROXIES` see one address unless the edge sits behind a relay (`doctor` warns).
- Compose env files: single quotes are literal, double quotes and bare values interpolate `$`; a `secrets: file:` mount keeps the host mode; Docker copy-up overwrites a pre-chowned named volume on first mount (`volume: {nocopy: true}`).
- The candidate memory guard sums the memory limits of every running container on the host, a neighbor's included, and blue/green needs room for both slots at once; the retention guard keeps the previous slot for `RETENTION_SECONDS` after a switch.
- A nameref helper resolves names dynamically: a caller's array must never share a name with a local of the function in between (`parse-pairs` keeps its order holder as `_sequence`).
- `curl --haproxy-clientip` is ignored over a unix socket (use `--interface` for distinct sources); `pgrep -f` inside an SSH command matches its own command line; pg_restore as the app role fails on `COMMENT ON EXTENSION` (filter extension entries, create extensions as superuser first).
- The image build context is the repository root (`TOOL_ROOT` two levels up); an image ignore file names files and globs only, because re-including a directory re-includes its `.venv` and `node_modules`.
