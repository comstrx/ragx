services:
  portainer:
    image: {{IMAGE_PORTAINER|json}}
    user: {{CONTROL_USER|json}}
    group_add: [{{CONTROL_GROUP|json}}]
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    command: [-H, unix:///var/run/docker.sock, --http-disabled, --sslcert, /certs/server.pem, --sslkey, /certs/server.key, --admin-password-file, /run/secrets/admin-password, --secret-key-name, portainer-key, --tunnel-addr, 127.0.0.1]
    ports: ['127.0.0.1:{{PORTAINER_PORT}}:9443']
    volumes:
      - portainer:/data
      - type: bind
        source: {{CONTROL_SOCKET|json}}
        target: /var/run/docker.sock
      - type: bind
        source: {{STATE_ROOT|json}}
        target: {{STATE_ROOT|json}}
        read_only: true
      - type: bind
        source: {{CONTROL_ROOT|json}}
        target: /run/secrets
        read_only: true
      - type: bind
        source: {{CONTROL_TLS|json}}
        target: /certs
        read_only: true
    tmpfs: [/tmp]
    restart: unless-stopped
    mem_limit: 512m
    cpus: '1'
    pids_limit: 512
    logging:
      driver: local
      options: {max-size: 10m, max-file: '3'}
    stop_grace_period: 30s

volumes:
  portainer:
    external: true
    name: '{{COMPOSE_PROJECT}}-portainer'
