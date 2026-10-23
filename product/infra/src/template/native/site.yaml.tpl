services:
  {{PART_NAME}}:
    image: {{PART_IMAGE|json}}
    scale: ${{{PART_VARIABLE}}:?{{PART_VARIABLE}} required}
    user: '10001:10001'
    init: true
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    tmpfs: ['/tmp:uid=10001,gid=10001,mode=0700', '/app/product/web/.next/out/cache:uid=10001,gid=10001,mode=0700']
    volumes: {{PART_MOUNTS}}
    environment: {{PART_VARIABLES}}
    networks:
      apps:
        aliases: ['{{PART_NAME}}-${DEPLOY_SLOT:?DEPLOY_SLOT required}']
    restart: unless-stopped
    mem_limit: {{APP_MEMORY|json}}
    cpus: {{CPUS|json}}
    pids_limit: 512
    logging:
      driver: local
      options: {max-size: 10m, max-file: '3'}
    stop_grace_period: 60s
    healthcheck:
      test: [CMD, bun, -e, 'const s = await Bun.connect({hostname: "127.0.0.1", port: {{PART_PORT}}, socket: {data() {}, error() { process.exit(1) }}}); s.end(); process.exit(0)']
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 30s

networks:
  apps:
    external: true
    name: '{{COMPOSE_PROJECT}}-apps'
