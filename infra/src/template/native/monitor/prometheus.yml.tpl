global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files: [/etc/prometheus/rules.yml]
{{MONITOR_ALERTING}}
scrape_configs:
  - job_name: edge
    static_configs: [{targets: ['edge:9090']}]
  - job_name: rabbitmq
    static_configs: [{targets: ['rabbitmq:15692']}]
  - job_name: postgres
    static_configs: [{targets: ['postgres-exporter:9187']}]
  - job_name: node
    static_configs: [{targets: ['node-exporter:9100']}]
  - job_name: prometheus
    static_configs: [{targets: ['127.0.0.1:9090']}]
