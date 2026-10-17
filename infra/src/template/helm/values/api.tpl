name: ${SERVICE_NAME}

image:
  repository: ${SEED_IMAGE}
  tag: "${SEED_TAG}"

imagePullSecrets: ${SEED_PULL_SECRETS}

healthPath: "${HEALTH_PATH}"

env:
  APP_ENV: production
  APP_DEBUG: "false"
  APP_HOST: 0.0.0.0
  APP_PORT: "8000"
  APP_WORKERS: "${WEB_WORKERS}"
  APP_RELEASE: "${SEED_TAG}"
  APP_URL: ${SEED_APP_URL}
  BASE_DOMAIN: ${BASE_DOMAIN}
  HEALTH_PATH: "${HEALTH_PATH}"
  LOG_LEVEL: info
  LOG_RENDERER: json
  STORAGE_DISK: ${SEED_DISK}
  AWS_BUCKET: "${SEED_BUCKET}"
  AWS_DEFAULT_REGION: "${SEED_REGION}"
  DB_PORT: "5432"
  DB_SSLMODE: ${SEED_DB_SSLMODE}
  DB_SEARCH_PATH: ${SEED_DB_SEARCH_PATH}
  DB_HOST: ${SEED_DB_HOST}
  DB_READ_HOST: "${SEED_DB_READ_HOST}"
  DB_STICKY: "${DB_STICKY}"
  DB_DATABASE: ${DB_NAME}
  DB_USERNAME: ${SEED_DB_APP_USER}
  DB_MIGRATE_USERNAME: ${DB_USER}
  DB_MIGRATE: "false"
  QUEUE_DRIVER: memory
  SCHEDULE_ENABLED: "true"
  SOCKET_PATH: /ws
  STORAGE_URL: /storage
  API_PER_MINUTE: "${API_PER_MINUTE}"
  TRUST_PROXIES: "${SEED_TRUST_PROXIES}"
  REDIS_HOST: redis.${K8S_NAMESPACE}.svc.cluster.local
  REDIS_PORT: "6379"
processes:
  web:
    enabled: true
    port: 8000
    resources:
      requests: { cpu: ${WEB_CPU}, memory: ${WEB_MEMORY} }
      limits: { memory: ${WEB_MEMORY_LIMIT} }

  worker:
    enabled: ${WORKER_ENABLED}
    replicas: ${WORKER_REPLICAS}
    grace: 90
    resources:
      requests: { cpu: ${WORKER_CPU}, memory: ${WORKER_MEMORY} }
      limits: { memory: ${WORKER_MEMORY_LIMIT} }

  scheduler:
    enabled: ${SCHEDULER_ENABLED}
    resources:
      requests: { cpu: ${SCHEDULER_CPU}, memory: ${SCHEDULER_MEMORY} }
      limits: { memory: ${SCHEDULER_MEMORY_LIMIT} }

autoscaling:
  enabled: true
  min: ${APP_MIN_REPLICAS}
  max: ${APP_MAX_REPLICAS}
  cpu: ${APP_CPU_TARGET}

rollout:
  surge: ${ROLLOUT_SURGE}
  unavailable: ${ROLLOUT_UNAVAILABLE}

storage:
  enabled: ${SEED_PVC}
  class: ${PLATFORM_STORAGE_CLASS}
  size: ${APP_STORAGE_SIZE}
  mount: ${APP_STORAGE_MOUNT}

route:
  enabled: true
  gateway: gateway
  gatewayNamespace: ${GATEWAY_NAMESPACE}
  sectionName: ${SEED_SECTION}
  hostnames: ${APP_HOSTNAMES}

netpol:
  enabled: true
  proxyNamespace: ${ENVOY_NAMESPACE}
  metricsNamespace: ${OBSERVABILITY_NAMESPACE}

migrate:
  enabled: ${MIGRATE_ENABLED}

runbook:
  enabled: ${RUNBOOK_ENABLED}

backup:
  enabled: true
  target: ${BACKUP_TARGET}
  schedule: "${BACKUP_SCHEDULE}"
  bucket: "${SEED_BACKUP_BUCKET}"
  endpoint: "${S3_ENDPOINT}"
  region: "${SEED_BACKUP_REGION}"
  keepDays: ${S3_BACKUP_KEEP_DAYS}
  storage:
    enabled: ${SEED_BACKUP_PVC}
    class: ${PLATFORM_STORAGE_CLASS}
    size: ${BACKUP_SIZE}
