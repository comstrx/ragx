COMMAND_GROUPS=( Release Data Operate 'Edge and certificates' 'Server and runtime' 'GitOps and control plane' Images )

STACK_COMMANDS=(
    'deploy|Release|deploy [--dry-run] [--force]|Ship the release through readiness gates, a blue/green switch and a verify window'
    'rollback|Release|rollback|Reject the pending release, or switch back to the retained previous release'
    'render|Release|render|Render and pin the release files without deploying them'
    'recover|Release|recover --force|Clear a dead deploy lock and resume the pending release'
    'backup|Data|backup {actions} [BACKUP]|Dump the database with a checksum, list the dumps, or prove one restores'
    'restore|Data|restore [BACKUP] [--at TIME] --force|Replace the live database with a dump, or the whole cluster as it was at a moment'
    'status|Operate|status|Show the releases, phase, slots, desired state, latest backup and channels'
    'doctor|Operate|doctor|Check runtime, settings, env files, disk, edge, certificate, data, backups, timers and channels'
    'plan|Operate|plan|Describe the stack, mode, driver, protocols, integrations and state root'
    'scale|Operate|scale|Apply the replica counts, draining connections before removing a replica'
    'start|Operate|start|Start the data services, the current release and the edge'
    'stop|Operate|stop --force|Stop the edge and the current release; the data services keep running'
    'uninstall|Operate|uninstall --force|Remove the edge, both release slots, the monitoring, the models and the data containers; volumes stay'
    'logs|Operate|logs SERVICE [--since TIME] [--tail LINES]|Print the recent logs of one service with the secrets of the settings redacted'
    'models|Operate|models {actions}|Fetch, verify and serve the self-hosted models MODELS names'
    'monitor|Operate|monitor|Check health, write the platform metrics and notify on a state change'
    'notify|Operate|notify MESSAGE [--channel NAME]|Send a message to every configured channel, or to one'
    'edge|Edge and certificates|edge {actions}|Apply edge changes after validation, restoring the previous edge on failure'
    'tls|Edge and certificates|tls {actions} [CERT KEY]|Check, issue, renew or import the edge certificate'
    'firewall|Edge and certificates|firewall {actions} [--force]|List the edge ports, or open them on the active host firewall'
    'server|Server and runtime|server {actions}|Prepare and operate the SSH target'
    'docker|Server and runtime|docker {actions}|Inspect or install the pinned Docker runtime'
    'timer|Server and runtime|timer {actions} [NAME] [SECONDS]|Schedule the monitor, backup, renew or reconcile runs'
    'reconcile|GitOps and control plane|reconcile [--force]|Fetch the desired state from Git and deploy it once the server matches'
    'watch|GitOps and control plane|watch|Reconcile forever, every GITOPS_INTERVAL seconds'
    'export|GitOps and control plane|export [DIRECTORY]|Write the secret-free Compose artifact and the desired state'
    'publish|GitOps and control plane|publish|Commit the desired state and tag release-RELEASE in one atomic push'
    'portainer|GitOps and control plane|portainer {actions}|Install the private control plane or register the pull credential'
    'image|Images|image {actions} ...|Read an image digest, locally or in the registry, or build an application image'
    'registry|Images|registry {actions}|Resolve, log in to and push to the image registry'
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

COMMAND_ACTIONS[backup]='create=Dump the database into sql/ with its SHA-256 and, with BACKUP_WAL, take a base backup into wal/; copy both to BACKUP_URI and prune what is older than BACKUP_RETENTION seconds|list=Show the dumps, newest first, and the base backups a point-in-time restore can start from|verify [BACKUP]=Restore a dump, the latest by default, into a scratch database, count its tables and drop it|archive=Copy the WAL archive and base backups to BACKUP_URI/wal; the archive timer runs it every BACKUP_ARCHIVE_INTERVAL seconds'
COMMAND_NOTES[backup]='The backup timer runs create every BACKUP_INTERVAL seconds|With BACKUP_WAL=true PostgreSQL archives its WAL into wal/archive at least every 60 seconds, so a restore can reach any second since the oldest kept base backup|Offsite copies never delete: give the bucket a lifecycle rule for retention|Notifies backup.succeeded or backup.failed'
COMMAND_EXAMPLES[backup]='infra backup|infra backup list|infra backup verify|infra backup verify 20261020T112013Z-jcQdcHui.dump|infra backup archive'

COMMAND_FLAGS[restore]='--at TIME=Restore the whole database cluster to this UTC moment, YYYY-MM-DDTHH:MM:SSZ, from a base backup and the WAL archive|--force=Required: replaces the live database'
COMMAND_ABOUT[restore]='Checks the dump, saves the live database as a new backup, restores into a scratch database, stops the worker and scheduler, then swaps by rename; the old database stays as <db>_before_<stamp>.'
COMMAND_NOTES[restore]='Without BACKUP the latest dump is restored, so restoring again without a name undoes a restore|--at stops PostgreSQL, unpacks the newest base backup finished before TIME, replays the archive up to TIME and keeps the previous data directory beside it; the API answers 503 meanwhile|The API keeps serving through the copy; the rename ends its database sessions, which failed requests for about 3 seconds at 600 requests per second in the lab|Notifies restore.succeeded or restore.failed'
COMMAND_EXAMPLES[restore]='infra backup list|infra restore --force|infra restore 20261020T112013Z-jcQdcHui.dump --force|infra restore --at 2026-10-21T22:59:30Z --force'

COMMAND_EXAMPLES[status]='infra status|infra server run status'

COMMAND_ABOUT[doctor]='Runs read-only checks and prints ✓, ! or ✗ with what to do next. Exits non-zero when a check fails, so it can gate automation.'
COMMAND_EXAMPLES[doctor]='infra doctor|infra server run doctor'

COMMAND_EXAMPLES[plan]='infra plan|infra --config production.env plan'

COMMAND_ABOUT[scale]='Reads <PART>_REPLICAS of every routed part and WORKER_REPLICAS, drains replicas above the target in HAProxy before Compose removes them, then waits for new replicas to pass readiness.'
COMMAND_NOTES[scale]='Data services and the scheduler never scale|Notifies scale.applied'
COMMAND_EXAMPLES[scale]='infra -e <PART>_REPLICAS=4 scale|infra -e WORKER_REPLICAS=3 scale'

COMMAND_NOTES[start]='Notifies service.started'
COMMAND_EXAMPLES[start]='infra start'

COMMAND_FLAGS[stop]='--force=Required: takes the service offline'
COMMAND_ABOUT[stop]='Stops the edge first, so no request reaches a stopping replica, then the worker, scheduler and front services.'
COMMAND_NOTES[stop]='Notifies service.stopped'
COMMAND_EXAMPLES[stop]='infra stop --force|infra start'

COMMAND_FLAGS[uninstall]='--force=Required: removes every container of the project'
COMMAND_NOTES[uninstall]='Data volumes, certificates, backups, releases and cached models stay; deploy recreates the containers|Notifies service.uninstalled'

COMMAND_FLAGS[logs]='--since TIME=Start this long ago, such as 30m, or at a UTC moment YYYY-MM-DDTHH:MM:SSZ|--tail LINES=Print at most this many lines per container: 200 by default, 10000 at most'
COMMAND_ABOUT[logs]='Finds SERVICE in the live release (its parts, worker and scheduler), the data services, the edge, the models or the monitoring, and prints its logs with timestamps. Every secret of the settings prints as [redacted].'
COMMAND_NOTES[logs]='Secrets that only the application env files hold are not known to infra and are not redacted'
COMMAND_EXAMPLES[logs]='infra logs PART --since 30m|infra logs postgres --tail 50|infra logs edge --since 2026-10-23T10:00:00Z'

COMMAND_ACTIONS[models]='status=Show each model MODELS names: its cache, its container and its URL|pull=Fetch the pinned files of every model into MODELS_DIR, resuming partial downloads and checking each size and SHA-256|verify=Hash every cached file again and fetch the ones that differ|apply=Pull, then start, update or remove the model containers to match MODELS'
COMMAND_NOTES[models]='deploy applies the models after the release is live; a failure warns and notifies models.failed and never touches the release|Each model runs read-only as nobody with its own memory and CPU limits, offline, on the internal <project>-models network without egress; server parts reach it at <MODEL>_URL|The runners, models and files are pinned in src/config/models.sh; pickle formats are refused|MODELS_TOKEN reaches gated repositories and never leaves the download request'
COMMAND_EXAMPLES[models]='infra models|infra models pull|infra -e MODELS=MODEL models apply|infra models verify'
COMMAND_EXAMPLES[uninstall]='infra uninstall --force'

COMMAND_ABOUT[monitor]='Checks every replica, the data services, the public endpoint, the backup age and the certificate, writes metrics/platform.prom and notifies only when the platform turns degraded or recovers.'
COMMAND_NOTES[monitor]='The monitor timer runs it every MONITOR_INTERVAL seconds and it skips while a deploy holds the lock'
COMMAND_EXAMPLES[monitor]='infra monitor'

COMMAND_ABOUT[notify]='Delivers to every channel whose settings exist: Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), Slack (SLACK_WEBHOOK_URL) and a custom webhook (WEBHOOK_URL, signed with WEBHOOK_SECRET). Each delivery is retried NOTIFY_RETRIES times.'
COMMAND_NOTES[notify]='With no channel configured it sends nothing and succeeds|Flags fill the settings of the same channels for this run; their values show in process listings, so shared hosts keep them in the environment|Webhook body: {event, level, project, release, host, time, text}; X-Infra-Signature: sha256=HMAC(WEBHOOK_SECRET, body)'
COMMAND_FLAGS[notify]='--channel NAME=Send to this channel only: telegram, slack or webhook|--token TOKEN=Telegram bot token (TELEGRAM_BOT_TOKEN)|--chat ID=Telegram chat (TELEGRAM_CHAT_ID)|--hook URL=Slack incoming webhook (SLACK_WEBHOOK_URL)|--url URL=Custom webhook endpoint (WEBHOOK_URL)|--secret SECRET=HMAC key that signs the custom webhook (WEBHOOK_SECRET)'
COMMAND_EXAMPLES[notify]='infra notify "maintenance at 22:00 UTC"|infra notify "deployed" --channel telegram --token "$BOT" --chat -1001234567890|infra notify "deployed" --channel slack --hook "$SLACK_HOOK"|infra notify "deployed" --channel webhook --url https://hooks.example.com/infra --secret "$SIGNING_KEY"'

COMMAND_ACTIONS[edge]='apply=Render the HAProxy configuration and Compose file, validate them in a scratch container, then reload seamlessly, or recreate the edge when its ports change|sync=Pull the domains of DOMAINS_ENDPOINT into the domain map, issue their certificates and reload seamlessly'
COMMAND_FLAGS[edge]='--force=apply: accept a readiness path or port the live release does not serve until the next release switches in; sync: accept a list that drops more than DOMAINS_MAX_DROP percent'
COMMAND_NOTES[edge]='Any failure restores the previous edge and notifies edge.rolled-back|A part whose path, readiness path or port changed is refused while the live release serves the old value, unless --force|deploy refuses to run while the live edge differs from the rendered one|Issues a certificate for every new registrable domain and drops the ones no route uses|Refreshes the TRUSTED_PROXIES lists published at https URLs and keeps the recorded ones when unreachable|EDGE_SOCKETS switches between published ports and a TCP relay such as nginx stream; the change recreates the edge'
COMMAND_EXAMPLES[edge]='infra edge apply|infra edge sync|infra edge sync --force|infra -e EDGE_SOCKETS=/srv/edge edge apply'

COMMAND_ACTIONS[tls]='present=Report whether the edge holds a certificate|issue=Request one ACME certificate per registrable domain, naming every routed domain under it, over HTTP-01 through the edge|renew=Renew the issued certificates that near expiry and reload the edge|import CERT KEY=Install a certificate and key issued elsewhere for the registrable domain they name'
COMMAND_NOTES[tls]='The renew timer runs every RENEW_INTERVAL seconds; a failed renewal notifies tls.renewal-failed'
COMMAND_EXAMPLES[tls]='infra tls|infra tls issue|infra tls import example.com.pem example.com.key'

COMMAND_ACTIONS[firewall]='ports=List what the edge needs: TCP for HTTP and HTTPS, UDP for HTTP/3 unless a relay owns the ports|apply=Open those ports on an active ufw or firewalld; never removes a rule'
COMMAND_FLAGS[firewall]='--force=Required by apply: changes the host firewall'
COMMAND_EXAMPLES[firewall]='infra firewall ports|infra firewall apply --force'

COMMAND_ACTIONS[server]='inspect=Check SSH, Bash 5 and Docker on SSH_HOST|stage=Upload the release bundle, the settings and the application env files|run [--] COMMAND=Run an infra command there as a detached job that survives a dropped connection|install=Install the pinned Docker runtime on SSH_HOST'
COMMAND_NOTES[server]='Flags after -- belong to the remote command|Credentials from the process environment are never staged; run hands them to that one command over SSH stdin|Uploads retry, and a start lost before the job existed runs again; a dropped connection follows the job instead of restarting it'
COMMAND_EXAMPLES[server]='infra server inspect|infra server stage|infra server run -- deploy --dry-run|infra server run status'

COMMAND_ACTIONS[docker]='status=Print the engine and Compose versions and whether Docker runs rootless|install=Install the checksum-pinned packages on Ubuntu 24.04; refuses to replace a runtime'
COMMAND_EXAMPLES[docker]='infra docker|infra server install'

COMMAND_ACTIONS[timer]='list=Show the timers of this project|install NAME SECONDS=Run NAME every SECONDS from the staged bundle: a systemd user timer, or a launchd agent on macOS|remove NAME=Stop and delete the timer of NAME'
COMMAND_NOTES[timer]='NAME: monitor, backup, archive, renew, reconcile or domains|deploy installs monitor, backup and renew, archive when BACKUP_WAL and BACKUP_URI are set, reconcile under GitOps, and domains every DOMAINS_INTERVAL seconds when DOMAINS_ENDPOINT, DOMAINS_TOKEN and a DOMAINS_INTERVAL above 0 are set|User timers outlive SSH sessions only with loginctl enable-linger'
COMMAND_EXAMPLES[timer]='infra timer|infra timer install backup 21600|infra timer remove reconcile'

COMMAND_FLAGS[reconcile]='--force=Deploy the desired release even though this server rejected it'
COMMAND_ABOUT[reconcile]='Reads the desired branch, checks the protected release tag and the Compose checksum, waits while the staged env files or the settings revision differ from the desired state, skips a release this server rejected, then deploys.'
COMMAND_EXAMPLES[reconcile]='infra reconcile|infra timer install reconcile 60'

COMMAND_EXAMPLES[watch]='infra watch'

COMMAND_EXAMPLES[export]='infra export deploy|infra -e VERSION=v1-4-0 export /tmp/desired'

COMMAND_ABOUT[publish]='Commits application.yaml and desired.env to GITOPS_BRANCH and tags release-RELEASE in one atomic push. Repeating it is idempotent; a tag that holds another desired state is refused.'
COMMAND_EXAMPLES[publish]='GITOPS_USER=x-access-token GITOPS_TOKEN=... infra publish'

COMMAND_ACTIONS[portainer]='install=Run Portainer CE on loopback behind a private CA and create an API key|registry=Register the pull credential with Portainer'
COMMAND_NOTES[portainer]='It holds the Docker socket: reach it through SSH port forwarding only'
COMMAND_EXAMPLES[portainer]='infra portainer install|infra portainer registry'

COMMAND_ACTIONS[image]='digest REFERENCE=Print the local repository digest of an image|available PART=Succeed when the source of a part exists in the checkout, so its image can be built|build PART REFERENCE=Build the image of a part from the monorepo with its recipe from the parts table, on pinned base images|reference PART TAG=Print the registry reference of a part, suffixed with the digest of its build variables|inputs PART=Print the public settings the image of a part depends on|resolve TAG=Print <PART>_IMAGE pinned by registry digest for every routed part whose image exists; a missing one is reported, never fatal|remote REFERENCE=Print the registry digest of a reference without pulling it'
COMMAND_EXAMPLES[image]='infra image reference PART v1.4.0|infra image build PART ghcr.io/org/project-part:v1.4.0|infra image resolve v1.4.0|infra image remote ghcr.io/org/project-part:v1.4.0'

COMMAND_ACTIONS[registry]='host=Print the registry host of REGISTRY_DRIVER|reference NAME TAG=Print the full image reference of NAME|login=Log in with REGISTRY_USER and REGISTRY_TOKEN, the token on stdin|push REFERENCE=Push a built image, retrying while the registry refuses it|logout=Log out of the registry'
COMMAND_EXAMPLES[registry]='infra registry reference NAME v1-4-0|infra registry login'

COMMAND_WHERE=(
    [deploy]=server [rollback]=server [recover]=server [backup]=server [restore]=server [status]=server [doctor]=server
    [scale]=server [start]=server [stop]=server [uninstall]=server [monitor]=server [edge]=server [tls]=server
    [firewall]=server [timer]=server [reconcile]=server [watch]=server [portainer]=server [logs]=server [models]=server
)

native-dispatch () {

    local command="${1}" allowed=""

    shift
    allowed="$(cli-actions "${COMMAND_ACTIONS[${command}]:-}")" || return

    cli-dispatch "native-${command}" "${1:-${allowed%% *}}" "${allowed}" "${@:2}"

}
native-allowed () {

    local command="${1}" allowed=""

    [[ -n "${COMMAND_ACTIONS[${command}]:-}" && -n "${2:-}" ]] || return 0
    allowed="$(cli-actions "${COMMAND_ACTIONS[${command}]}")" || return

    cli-allowed "${command}" "${2}" "${allowed}"

}
