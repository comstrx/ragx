x-application: &application
  image: {{API_IMAGE|json}}
  user: '10001:10001'
  init: true
  read_only: true
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  env_file: ['${RELEASE_ROOT:?RELEASE_ROOT required}/api.env']
  tmpfs: ['/tmp:uid=10001,gid=10001,mode=0700']
  volumes: [storage:/app/storage]
  networks: [data, apps]
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
  api:
    <<: *application
    scale: ${API_REPLICAS:?API_REPLICAS required}
    command: [python, -m, bootstrap, serve]
    environment: {QUEUE_WORKERS: '0', SCHEDULE_ENABLED: 'false'}
    networks:
      data: {}
      apps:
        aliases: ['api-${DEPLOY_SLOT:?DEPLOY_SLOT required}']
    healthcheck:
      test: [CMD, python, -c, 'import socket; socket.create_connection(("127.0.0.1", {{API_PORT}}), 2).close()']
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 30s
  worker:
    <<: *application
    scale: ${WORKER_REPLICAS:?WORKER_REPLICAS required}
    profiles: [worker]
    command: [python, -m, bootstrap, work]
    environment: {SCHEDULE_ENABLED: 'false'}
  scheduler:
    <<: *application
    profiles: [scheduler]
    command: [python, -m, bootstrap, schedule]
    environment: {QUEUE_WORKERS: '0', SCHEDULE_ENABLED: 'true'}

networks:
  data:
    external: true
    name: '{{COMPOSE_PROJECT}}-data'
  apps:
    external: true
    name: '{{COMPOSE_PROJECT}}-apps'

volumes:
  storage:
    external: true
    name: '{{COMPOSE_PROJECT}}-storage'
