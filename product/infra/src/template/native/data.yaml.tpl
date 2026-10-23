x-data: &data
  read_only: true
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  networks: [data]
  restart: unless-stopped
  mem_limit: {{DATA_MEMORY|json}}
  cpus: {{CPUS|json}}
  pids_limit: 512
  logging:
    driver: local
    options: {max-size: 10m, max-file: '3'}
  stop_grace_period: 60s

services:
  postgres:
    <<: *data
    image: {{IMAGE_POSTGRES|json}}
    user: '999:999'
    env_file: [./postgres.env]
    tmpfs: [/tmp, '/var/run/postgresql:uid=999,gid=999,mode=0700']
    volumes:
      - postgres:/var/lib/postgresql
      - ./postgres.sql:/docker-entrypoint-initdb.d/10-application.sql:ro
      - ./pg_hba.conf:/etc/postgresql/pg_hba.conf:ro
      - type: bind
        source: {{BACKUP_WAL_ROOT|json}}
        target: /wal
    command:
      - postgres
      - -c
      - hba_file=/etc/postgresql/pg_hba.conf
      - -c
      - 'shared_buffers={{DB_MEMORY}}'
      - -c
      - password_encryption=scram-sha-256
      - -c
      - archive_mode=on
      - -c
      - archive_timeout=60
      - -c
      - 'archive_command=test ! -f /wal/enabled || test -f /wal/archive/%f || { cp %p /wal/archive/%f.part && mv /wal/archive/%f.part /wal/archive/%f; }'
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"']
      interval: 5s
      timeout: 3s
      retries: 18
  rabbitmq:
    <<: *data
    image: {{IMAGE_RABBITMQ|json}}
    user: '999:999'
    env_file: [./rabbitmq.env]
    tmpfs: [/tmp, '/var/log/rabbitmq:uid=999,gid=999,mode=0700']
    volumes: [rabbitmq:/var/lib/rabbitmq]
    healthcheck:
      test: [CMD, rabbitmq-diagnostics, -q, ping]
      interval: 10s
      timeout: 5s
      retries: 18
  redis:
    <<: *data
    image: {{IMAGE_REDIS|json}}
    user: '999:999'
    env_file: [./redis.env]
    entrypoint: [sh, -c]
    command: ['umask 077; printf "%s" "$$REDIS_CONFIG" > /tmp/redis.conf; exec redis-server /tmp/redis.conf']
    tmpfs: ['/tmp:uid=999,gid=999,mode=0700']
    volumes: [redis:/data]
    healthcheck:
      test: [CMD-SHELL, 'redis-cli ping | grep -qx PONG']
      interval: 5s
      timeout: 3s
      retries: 18

networks:
  data:
    external: true
    name: '{{COMPOSE_PROJECT}}-data'

volumes:
  postgres:
    external: true
    name: '{{COMPOSE_PROJECT}}-postgres'
  rabbitmq:
    external: true
    name: '{{COMPOSE_PROJECT}}-rabbitmq'
  redis:
    external: true
    name: '{{COMPOSE_PROJECT}}-redis'
