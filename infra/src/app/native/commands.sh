COMMAND_GROUPS=( Release Data Operate 'Edge and certificates' 'Server and runtime' 'GitOps and control plane' Images )

STACK_COMMANDS=(
    'deploy|Release|deploy [--dry-run] [--force]|Ship the release through readiness gates, a blue/green switch and a verify window'
    'rollback|Release|rollback|Reject the pending release, or switch back to the retained previous release'
    'render|Release|render|Render and pin the release files without deploying them'
    'recover|Release|recover --force|Clear a dead deploy lock and resume the pending release'
    'backup|Data|backup [create/list/verify] [BACKUP]|Dump the database with a checksum, list the dumps, or prove one restores'
    'restore|Data|restore [BACKUP] --force|Replace the live database with a dump, the latest by default, keeping the old one'
    'status|Operate|status|Show the releases, phase, slots, desired state, latest backup and channels'
    'doctor|Operate|doctor|Check runtime, settings, env files, disk, edge, certificate, data, backups, timers and channels'
    'plan|Operate|plan|Describe the stack, mode, driver, protocols, integrations and state root'
    'scale|Operate|scale|Apply the replica counts, draining connections before removing a replica'
    'start|Operate|start|Start the data services, the current release and the edge'
    'stop|Operate|stop --force|Stop the edge and the current release; the data services keep running'
    'uninstall|Operate|uninstall --force|Remove the edge, both release slots, the monitoring and the data containers; volumes stay'
    'monitor|Operate|monitor|Check health, write the platform metrics and notify on a state change'
    'notify|Operate|notify MESSAGE [--channel NAME]|Send a message to every configured channel, or to one'
    'edge|Edge and certificates|edge apply|Apply edge changes after validation, restoring the previous edge on failure'
    'tls|Edge and certificates|tls issue/renew/present/import [CERT KEY]|Issue, renew, check or import the edge certificate'
    'dns|Edge and certificates|dns check/set [HOST]|Inspect or upsert the DNS_PROVIDER record of a routed host'
    'firewall|Edge and certificates|firewall ports/apply [--force]|List the edge ports, or open them on the active host firewall'
    'server|Server and runtime|server inspect/stage/run/install|Prepare and operate the SSH target'
    'docker|Server and runtime|docker status/install|Inspect or install the pinned Docker runtime'
    'timer|Server and runtime|timer install/remove/list [NAME] [SECONDS]|Schedule the monitor, backup, renew or reconcile runs'
    'reconcile|GitOps and control plane|reconcile [--force]|Fetch the desired state from Git and deploy it once the server matches'
    'watch|GitOps and control plane|watch|Reconcile forever, every GITOPS_INTERVAL seconds'
    'export|GitOps and control plane|export [DIRECTORY]|Write the secret-free Compose artifact and the desired state'
    'publish|GitOps and control plane|publish|Commit the desired state and tag release-RELEASE in one atomic push'
    'portainer|GitOps and control plane|portainer install/registry|Install the private control plane or register the pull credential'
    'image|Images|image build/digest/remote|Build an application image, or read its local or registry digest'
    'registry|Images|registry host/reference/login/push/logout|Resolve, log in to and push to the image registry'
)

COMMAND_FLAGS[deploy]='--dry-run=Print the decision and check its inputs; change nothing|--force=Ship a release this server rejected, or switch a manual stage live'
COMMAND_ABOUT[deploy]='Names the release VERSION-<settings revision> unless RELEASE pins it, takes the deploy lock and converges: a new release goes to the idle slot, the retained previous release switches back in seconds, the live release is a no-op and a rejected one is refused.'
COMMAND_NOTES[deploy]='Gates: settings, edge drift, capacity, data services, migration (MIGRATION_POLICY=expand), healthy replicas, edge readiness, warmup|After the switch, VERIFY_FAILURES consecutive failed checks within VERIFY_SECONDS roll back automatically|A failure before the switch keeps the live release serving and remembers the candidate as rejected|Notifies deploy.succeeded, deploy.switched, deploy.rejected, deploy.unrecovered and verify.*|With SSH_HOST set it stages the bundle, the settings and the application env files there, applies the edge, then deploys; --dry-run stages nothing and previews what the server holds'
COMMAND_EXAMPLES[deploy]='infra deploy --dry-run|infra deploy|infra -e VERSION=v1-4-0 deploy|infra server run -- deploy --force'

COMMAND_ABOUT[rollback]='With a pending release, rejects it and restores the origin; otherwise switches back to the retained previous release after checking its slot was not reused.'
COMMAND_NOTES[rollback]='Schema changes are never rolled back: migrations must stay backward compatible|The release set aside is remembered as rejected|Notifies rollback.succeeded or rollback.failed'
COMMAND_EXAMPLES[rollback]='infra rollback|infra server run rollback'

COMMAND_ABOUT[render]='Writes releases/<RELEASE>: the Compose files, the data service env files, the application env snapshot and release.env. A rendered release never changes; new settings give a new release name.'
COMMAND_EXAMPLES[render]='infra render|infra -e VERSION=v1-4-0 render'

COMMAND_FLAGS[recover]='--force=Required: confirms the deploy that held the lock is gone'
COMMAND_ABOUT[recover]='For a deploy whose process died holding the lock: removes the lock only when its owner no longer runs, then resumes the pending release.'
COMMAND_EXAMPLES[recover]='infra status|infra recover --force'

COMMAND_ABOUT[backup]='create, the default, dumps the database into BACKUP_DIR, checks the archive, writes its SHA-256, copies both to BACKUP_URI (s3:// or gs://) when set and prunes dumps older than BACKUP_DAYS except the latest. list shows the dumps newest first. verify restores a dump into a scratch database and drops it, proving it restores without touching live data.'
COMMAND_NOTES[backup]='The backup timer runs create every BACKUP_INTERVAL seconds|Notifies backup.succeeded or backup.failed'
COMMAND_EXAMPLES[backup]='infra backup|infra backup list|infra backup verify|infra backup verify 20261020T112013Z-jcQdcHui.dump'

COMMAND_FLAGS[restore]='--force=Required: replaces the live database'
COMMAND_ABOUT[restore]='Checks the dump, saves the live database as a new backup, restores into a scratch database, stops the worker and scheduler, then swaps by rename; the old database stays as <db>_before_<stamp>.'
COMMAND_NOTES[restore]='Without BACKUP the latest dump is restored, so restoring again without a name undoes a restore|The API keeps serving through the copy; the rename ends its database sessions, which failed requests for about 3 seconds at 600 requests per second in the lab|Notifies restore.succeeded or restore.failed'
COMMAND_EXAMPLES[restore]='infra backup list|infra restore --force|infra restore 20261020T112013Z-jcQdcHui.dump --force'

COMMAND_EXAMPLES[status]='infra status|infra server run status'

COMMAND_ABOUT[doctor]='Runs read-only checks and prints ✓, ! or ✗ with what to do next. Exits non-zero when a check fails, so it can gate automation.'
COMMAND_EXAMPLES[doctor]='infra doctor|infra server run doctor'

COMMAND_EXAMPLES[plan]='infra plan|infra --config production.env plan'

COMMAND_ABOUT[scale]='Reads API_REPLICAS, WORKER_REPLICAS and WEB_REPLICAS, drains replicas above the target in HAProxy before Compose removes them, then waits for new replicas to pass readiness.'
COMMAND_NOTES[scale]='Data services and the scheduler never scale|Notifies scale.applied'
COMMAND_EXAMPLES[scale]='infra -e API_REPLICAS=4 scale|infra -e WEB_REPLICAS=client=3 scale'

COMMAND_NOTES[start]='Notifies service.started'
COMMAND_EXAMPLES[start]='infra start'

COMMAND_FLAGS[stop]='--force=Required: takes the service offline'
COMMAND_ABOUT[stop]='Stops the edge first, so no request reaches a stopping replica, then the worker, scheduler and front services.'
COMMAND_NOTES[stop]='Notifies service.stopped'
COMMAND_EXAMPLES[stop]='infra stop --force|infra start'

COMMAND_FLAGS[uninstall]='--force=Required: removes every container of the project'
COMMAND_NOTES[uninstall]='Data volumes, certificates, backups and releases stay; deploy recreates the containers|Notifies service.uninstalled'
COMMAND_EXAMPLES[uninstall]='infra uninstall --force'

COMMAND_ABOUT[monitor]='Checks every replica, the data services, the public endpoint, the backup age and the certificate, writes metrics/platform.prom and notifies only when the platform turns degraded or recovers.'
COMMAND_NOTES[monitor]='The monitor timer runs it every MONITOR_INTERVAL seconds and it skips while a deploy holds the lock'
COMMAND_EXAMPLES[monitor]='infra monitor'

COMMAND_ABOUT[notify]='Delivers to every channel whose settings exist: Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), Slack (SLACK_WEBHOOK_URL) and a custom webhook (WEBHOOK_URL, signed with WEBHOOK_SECRET). Each delivery is retried NOTIFY_RETRIES times.'
COMMAND_NOTES[notify]='With no channel configured it sends nothing and succeeds|Flags fill the settings of the same channels for this run; their values show in process listings, so shared hosts keep them in the environment|Webhook body: {event, level, project, release, host, time, text}; X-Infra-Signature: sha256=HMAC(WEBHOOK_SECRET, body)'
COMMAND_FLAGS[notify]='--channel NAME=Send to this channel only: telegram, slack or webhook|--token TOKEN=Telegram bot token (TELEGRAM_BOT_TOKEN)|--chat ID=Telegram chat (TELEGRAM_CHAT_ID)|--hook URL=Slack incoming webhook (SLACK_WEBHOOK_URL)|--url URL=Custom webhook endpoint (WEBHOOK_URL)|--secret SECRET=HMAC key that signs the custom webhook (WEBHOOK_SECRET)'
COMMAND_EXAMPLES[notify]='infra notify "maintenance at 22:00 UTC"|infra notify "deployed" --channel telegram --token "$BOT" --chat -1001234567890|infra notify "deployed" --channel slack --hook "$SLACK_HOOK"|infra notify "deployed" --channel webhook --url https://hooks.example.com/infra --secret "$SIGNING_KEY"'

COMMAND_ABOUT[edge]='Renders the HAProxy configuration and Compose file, validates them in a scratch container, then reloads seamlessly, or recreates the edge when its ports change, restoring the previous edge on any failure.'
COMMAND_NOTES[edge]='deploy refuses to run while the live edge differs from the rendered one|Upserts the records of every routed host when DNS_PROVIDER is set|Refreshes the TRUSTED_PROXIES lists published at https URLs and keeps the recorded ones when unreachable|Notifies edge.rolled-back'
COMMAND_EXAMPLES[edge]='infra edge apply'

COMMAND_ABOUT[tls]='issue requests an ACME certificate (HTTP-01 through the edge, or DNS-01 through DNS_PROVIDER), renew renews it, present reports whether one exists and import installs CERT and KEY.'
COMMAND_NOTES[tls]='The renew timer runs every RENEW_INTERVAL seconds; a failed renewal notifies tls.renewal-failed'
COMMAND_EXAMPLES[tls]='infra tls issue|infra tls import site.pem site.key|infra tls present'

COMMAND_ABOUT[dns]='check prints the DNS_PROVIDER record of HOST, API_HOST by default; set upserts it to DNS_ADDRESS, proxied by the provider when DNS_PROXIED=true.'
COMMAND_EXAMPLES[dns]='infra dns check|infra dns set grafana.example.com'

COMMAND_FLAGS[firewall]='--force=Required by apply: changes the host firewall'
COMMAND_ABOUT[firewall]='ports lists what the edge needs: TCP for HTTP and HTTPS, UDP for HTTP/3. apply opens them on an active ufw or firewalld and never removes a rule.'
COMMAND_EXAMPLES[firewall]='infra firewall ports|infra firewall apply --force'

COMMAND_ABOUT[server]='inspect checks SSH and the remote Docker; stage uploads the release bundle, the infrastructure settings and the application env files; run executes a command there as a detached job that survives a dropped connection; install installs Docker remotely.'
COMMAND_NOTES[server]='Flags after -- belong to the remote command|Credentials from the process environment are never staged; run hands them to that one command over SSH stdin'
COMMAND_EXAMPLES[server]='infra server stage|infra server run -- deploy --dry-run|infra server run status'

COMMAND_ABOUT[docker]='status prints the engine and Compose versions and whether Docker runs rootless; install installs the checksum-pinned packages on Ubuntu 24.04 and refuses to replace a runtime.'
COMMAND_EXAMPLES[docker]='infra docker status|infra server install'

COMMAND_ABOUT[timer]='install writes a systemd user timer, or a launchd agent on macOS, running NAME every SECONDS from the staged bundle; remove stops and deletes it; list shows the timers of this project.'
COMMAND_NOTES[timer]='NAME: monitor, backup, renew or reconcile|deploy installs monitor, backup and renew, and reconcile under GitOps|User timers outlive SSH sessions only with loginctl enable-linger'
COMMAND_EXAMPLES[timer]='infra timer list|infra timer install backup 21600|infra timer remove reconcile'

COMMAND_FLAGS[reconcile]='--force=Deploy the desired release even though this server rejected it'
COMMAND_ABOUT[reconcile]='Reads the desired branch, checks the protected release tag and the Compose checksum, waits while the staged env files or the settings revision differ from the desired state, skips a release this server rejected, then deploys.'
COMMAND_EXAMPLES[reconcile]='infra reconcile|infra timer install reconcile 60'

COMMAND_EXAMPLES[watch]='infra watch'

COMMAND_EXAMPLES[export]='infra export deploy|infra -e VERSION=v1-4-0 export /tmp/desired'

COMMAND_ABOUT[publish]='Commits application.yaml and desired.env to GITOPS_BRANCH and tags release-RELEASE in one atomic push. Repeating it is idempotent; a tag that holds another desired state is refused.'
COMMAND_EXAMPLES[publish]='GITOPS_USER=x-access-token GITOPS_TOKEN=... infra publish'

COMMAND_ABOUT[portainer]='install runs Portainer CE on loopback behind a private CA and creates an API key; registry registers the pull credential.'
COMMAND_NOTES[portainer]='It holds the Docker socket: reach it through SSH port forwarding only'
COMMAND_EXAMPLES[portainer]='infra portainer install|infra portainer registry'

COMMAND_ABOUT[image]='build builds api or a web SPEC from the monorepo on pinned base images; digest prints the local repository digest; remote prints the registry digest of a reference without pulling it.'
COMMAND_EXAMPLES[image]='infra image build api ghcr.io/org/api:v1|infra image build web ghcr.io/org/client:v1 client|infra image remote ghcr.io/org/api:v1'

COMMAND_ABOUT[registry]='host and reference print the registry host and a full image reference; login and logout pass the token on stdin; push pushes a built image.'
COMMAND_EXAMPLES[registry]='infra registry reference api v1-4-0|infra registry login'

COMMAND_WHERE=(
    [deploy]=server [rollback]=server [recover]=server [backup]=server [restore]=server [status]=server [doctor]=server
    [scale]=server [start]=server [stop]=server [uninstall]=server [monitor]=server [edge]=server [tls]=server
    [firewall]=server [timer]=server [reconcile]=server [watch]=server [portainer]=server
)
