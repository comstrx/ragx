x-application: &application
  image: {{PART_IMAGE|json}}
  user: '10001:10001'
  init: true
  read_only: true
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  tmpfs: ['/tmp:uid=10001,gid=10001,mode=0700']
  volumes: {{PART_MOUNTS}}
  networks: [data, apps, models]
  restart: unless-stopped
  mem_limit: {{APP_MEMORY|json}}
  cpus: {{CPUS|json}}
  pids_limit: 512
  ulimits:
    nofile: {soft: 65536, hard: 65536}
  logging:
    driver: local
    options: {max-size: 10m, max-file: '3'}
  stop_grace_period: 60s

services:
  {{PART_NAME}}:
    <<: *application
    scale: ${{{PART_VARIABLE}}:?{{PART_VARIABLE}} required}
    command: {{PART_SERVE_ARGS}}
    environment: {{PART_SERVE_VARIABLES}}
    networks:
      data: {}
      apps:
        aliases: ['{{PART_NAME}}-${DEPLOY_SLOT:?DEPLOY_SLOT required}']
      models: {}
    healthcheck:
      test: [CMD, python, -c, 'import socket; socket.create_connection(("127.0.0.1", {{PART_PORT}}), 2).close()']
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 30s
  worker:
    <<: *application
    scale: ${WORKER_REPLICAS:?WORKER_REPLICAS required}
    profiles: [worker]
    command: {{PART_WORK_ARGS}}
    environment: {{PART_WORK_VARIABLES}}
    healthcheck: {disable: true}
  scheduler:
    <<: *application
    profiles: [scheduler]
    command: {{PART_SCHEDULE_ARGS}}
    environment: {{PART_SCHEDULE_VARIABLES}}
    healthcheck: {disable: true}

networks:
  data:
    external: true
    name: '{{COMPOSE_PROJECT}}-data'
  apps:
    external: true
    name: '{{COMPOSE_PROJECT}}-apps'
  models:
    external: true
    name: '{{COMPOSE_PROJECT}}-models'

volumes:
  storage:
    external: true
    name: '{{COMPOSE_PROJECT}}-storage'
