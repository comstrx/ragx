groups:
  - name: platform
    rules:
      - alert: EdgeDown
        expr: up{job="edge"} == 0
        for: 2m
        labels: {severity: critical}
        annotations: {summary: The edge stopped answering Prometheus}
      - alert: ApiHasNoReplica
        expr: max(haproxy_backend_active_servers{proxy=~"api_(blue|green)"}) == 0
        for: 1m
        labels: {severity: critical}
        annotations: {summary: No API replica is serving}
      - alert: ServerErrors
        expr: sum(rate(haproxy_frontend_http_responses_total{proxy="public",code="5xx"}[5m])) / clamp_min(sum(rate(haproxy_frontend_http_responses_total{proxy="public"}[5m])), 0.001) > 0.02
        for: 5m
        labels: {severity: critical}
        annotations: {summary: More than 2% of public answers are server errors}
      - alert: SlowAnswers
        expr: max(haproxy_backend_response_time_average_seconds{proxy=~"api_(blue|green)"}) > 1
        for: 10m
        labels: {severity: warning}
        annotations: {summary: The API answers slower than one second on average}
      - alert: QueueNotDraining
        expr: sum(rabbitmq_queue_messages_ready) > 5000
        for: 10m
        labels: {severity: warning}
        annotations: {summary: More than five thousand jobs wait in RabbitMQ}
      - alert: BrokerUnreachable
        expr: up{job="rabbitmq"} == 0
        for: 2m
        labels: {severity: critical}
        annotations: {summary: RabbitMQ stopped answering Prometheus}
      - alert: DatabaseUnreachable
        expr: pg_up == 0
        for: 2m
        labels: {severity: critical}
        annotations: {summary: PostgreSQL stopped answering the exporter}
      - alert: DiskFillingUp
        expr: node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} < 0.15
        for: 15m
        labels: {severity: warning}
        annotations: {summary: Less than 15% of the root disk is free}
      - alert: MemoryExhausted
        expr: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes < 0.1
        for: 10m
        labels: {severity: warning}
        annotations: {summary: Less than 10% of host memory is available}
      - alert: BackupMissing
        expr: time() - platform_backup_timestamp_seconds > {{BACKUP_MAX_AGE}}
        for: 30m
        labels: {severity: critical}
        annotations: {summary: The latest database backup is older than BACKUP_MAX_AGE}
      - alert: CertificateExpiring
        expr: platform_certificate_expiry_timestamp_seconds - time() < 1209600
        for: 1h
        labels: {severity: critical}
        annotations: {summary: The edge certificate expires in less than fourteen days}
      - alert: PlatformDegraded
        expr: platform_healthy == 0
        for: 10m
        labels: {severity: critical}
        annotations: {summary: The platform monitor reports a degraded release}
