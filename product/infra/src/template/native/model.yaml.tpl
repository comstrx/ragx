services:
  {{MODEL_NAME}}:
    image: {{MODEL_IMAGE|json}}
    user: '65534:65534'
    init: true
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    tmpfs: ['/tmp:uid=65534,gid=65534,mode=0700']
    environment: {HOME: /tmp, HF_HOME: /tmp, HF_HUB_OFFLINE: '1', HF_HUB_DISABLE_TELEMETRY: '1'}
    command: {{MODEL_ARGS}}
    volumes:
      - type: bind
        source: {{MODEL_ROOT|json}}
        target: /model
        read_only: true
    networks:
      models:
        aliases: ['{{MODEL_NAME}}']
    restart: unless-stopped
    mem_limit: {{MODEL_MEMORY|json}}
    cpus: {{MODEL_CPUS|json}}
    pids_limit: 256
    ulimits:
      nofile: {soft: 65536, hard: 65536}
    logging:
      driver: local
      options: {max-size: 10m, max-file: '3'}
    stop_grace_period: 30s
    labels:
      io.infra.revision: {{MODEL_REVISION|json}}

networks:
  models:
    external: true
    name: '{{COMPOSE_PROJECT}}-models'
