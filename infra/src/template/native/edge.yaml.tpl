services:
  edge:
    image: {{IMAGE_HAPROXY|json}}
    user: '1000:1000'
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    entrypoint: [haproxy, -W, -db, -f, /etc/haproxy/haproxy.cfg]
    tmpfs: ['/run/haproxy:uid=1000,gid=1000,mode=0700']
    volumes:
      - type: bind
        source: {{EDGE_ROOT|json}}
        target: /etc/haproxy
        read_only: true
      - tls:/etc/haproxy-tls:ro
    ports:
{{EDGE_PORTS}}
    networks: [apps]
    restart: unless-stopped
    mem_limit: {{EDGE_MEMORY|json}}
    cpus: {{CPUS|json}}
    pids_limit: 256
    ulimits:
      nofile: {soft: 65536, hard: 65536}
    logging:
      driver: local
      options: {max-size: 10m, max-file: '3'}
    healthcheck:
      test: [CMD, wget, -q, -O, /dev/null, 'http://127.0.0.1:9090/live']
      interval: 5s
      timeout: 2s
      retries: 3
      start_period: 10s
    stop_grace_period: 60s

networks:
  apps:
    external: true
    name: '{{COMPOSE_PROJECT}}-apps'

volumes:
  tls:
    external: true
    name: '{{COMPOSE_PROJECT}}-tls'
