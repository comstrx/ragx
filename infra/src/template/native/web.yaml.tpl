  {{WEB_SERVICE}}:
    image: {{WEB_IMAGE|json}}
    scale: ${{{WEB_VARIABLE}}:?{{WEB_VARIABLE}} required}
    user: '10001:10001'
    init: true
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    tmpfs: ['/tmp:uid=10001,gid=10001,mode=0700', '/app/.next/out/cache:uid=10001,gid=10001,mode=0700']
    environment: {PORT: '{{WEB_PORT}}', HOSTNAME: 0.0.0.0}
    networks:
      apps:
        aliases: ['{{WEB_SERVICE}}-${DEPLOY_SLOT:?DEPLOY_SLOT required}']
    restart: unless-stopped
    mem_limit: {{APP_MEMORY|json}}
    cpus: {{CPUS|json}}
    pids_limit: 512
    logging:
      driver: local
      options: {max-size: 10m, max-file: '3'}
    stop_grace_period: 60s
    healthcheck:
      test: [CMD, bun, -e, 'const s = await Bun.connect({hostname: "127.0.0.1", port: {{WEB_PORT}}, socket: {data() {}, error() { process.exit(1) }}}); s.end(); process.exit(0)']
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 30s
