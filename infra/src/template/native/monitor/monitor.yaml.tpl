x-monitor: &monitor
  user: {{MONITOR_USER|json}}
  read_only: true
  cap_drop: [ALL]
  security_opt: [no-new-privileges:true]
  restart: unless-stopped
  pids_limit: 256
  logging:
    driver: local
    options: {max-size: 10m, max-file: '3'}

services:
  prometheus:
    <<: *monitor
    image: {{IMAGE_PROMETHEUS|json}}
    command: [--config.file=/etc/prometheus/prometheus.yml, --storage.tsdb.path=/prometheus, '--storage.tsdb.retention.time={{METRICS_RETENTION}}']
    volumes:
      - {type: volume, source: prometheus, target: /prometheus, volume: {nocopy: true}}
      - ./prometheus:/etc/prometheus:ro
    networks: [apps, data, monitor]
    mem_limit: 512m
    cpus: {{CPUS|json}}
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:9090/-/ready']
      interval: 10s
      timeout: 3s
      retries: 6
    stop_grace_period: 30s
  grafana:
    <<: *monitor
    image: {{IMAGE_GRAFANA|json}}
    environment:
      GF_SECURITY_ADMIN_PASSWORD__FILE: /run/secrets/grafana-password
      GF_SECURITY_COOKIE_SECURE: {{TLS_ENABLED|json}}
      GF_SECURITY_DISABLE_GRAVATAR: 'true'
      GF_SERVER_ROOT_URL: {{GRAFANA_URL|json}}
      GF_USERS_ALLOW_SIGN_UP: 'false'
      GF_AUTH_ANONYMOUS_ENABLED: 'false'
      GF_ANALYTICS_REPORTING_ENABLED: 'false'
      GF_ANALYTICS_CHECK_FOR_UPDATES: 'false'
      GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES: 'false'
      GF_NEWS_NEWS_FEED_ENABLED: 'false'
      GF_PLUGINS_PREINSTALL_DISABLED: 'true'
    volumes:
      - {type: volume, source: grafana, target: /var/lib/grafana, volume: {nocopy: true}}
      - ./grafana:/etc/grafana/provisioning:ro
      - ./secrets/grafana-password:/run/secrets/grafana-password:ro
    tmpfs: [/tmp]
    networks: [apps, monitor]
    mem_limit: 384m
    cpus: {{CPUS|json}}
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:3000/api/health']
      interval: 10s
      timeout: 3s
      retries: 12
  node-exporter:
    <<: *monitor
    image: {{IMAGE_NODE_EXPORTER|json}}
    command: [--path.rootfs=/host, --collector.textfile.directory=/textfile]
    volumes:
      - /:/host:ro
      - ../metrics:/textfile:ro
    networks: [monitor]
    mem_limit: 64m
    cpus: '0.25'
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:9100/']
      interval: 10s
      timeout: 3s
      retries: 3
  postgres-exporter:
    <<: *monitor
    image: {{IMAGE_POSTGRES_EXPORTER|json}}
    environment:
      DATA_SOURCE_URI: 'postgres:5432/{{DB_NAME}}?sslmode=disable'
      DATA_SOURCE_USER: {{DB_USER|json}}
      DATA_SOURCE_PASS_FILE: /run/secrets/db-password
    volumes:
      - ./secrets/db-password:/run/secrets/db-password:ro
    networks: [data]
    mem_limit: 64m
    cpus: '0.25'
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:9187/']
      interval: 10s
      timeout: 3s
      retries: 3
{{MONITOR_ALERTMANAGER}}
networks:
  monitor: {}
  apps:
    external: true
    name: '{{COMPOSE_PROJECT}}-apps'
  data:
    external: true
    name: '{{COMPOSE_PROJECT}}-data'

volumes:
  prometheus:
    external: true
    name: '{{COMPOSE_PROJECT}}-prometheus'
  grafana:
    external: true
    name: '{{COMPOSE_PROJECT}}-grafana'
