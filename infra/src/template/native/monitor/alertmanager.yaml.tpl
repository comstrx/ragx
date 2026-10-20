  alertmanager:
    <<: *monitor
    image: {{IMAGE_ALERTMANAGER|json}}
    command: [--config.file=/etc/alertmanager/alertmanager.yml, --storage.path=/alertmanager]
    tmpfs: [/alertmanager]
    volumes:
      - ./alertmanager:/etc/alertmanager:ro
      - ./secrets/telegram-token:/run/secrets/telegram-token:ro
      - ./secrets/slack-url:/run/secrets/slack-url:ro
    networks: [monitor]
    mem_limit: 64m
    cpus: '0.25'
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:9093/-/ready']
      interval: 10s
      timeout: 3s
      retries: 3
