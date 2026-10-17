ARG PYTHON_IMAGE=python:3.15-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1
ARG BACKUP_IMAGE=postgres:18-alpine

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_DEV=1 \
    UV_FROZEN=1

FROM base AS vendor

ARG APP_DIR=api

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY ${APP_DIR}/pyproject.toml ${APP_DIR}/uv.lock ${APP_DIR}/.python-version ./

RUN uv sync --no-install-project

COPY ${APP_DIR}/ ./

RUN uv sync && chown -R 33:33 /app/storage

FROM base AS app

WORKDIR /app

COPY --from=vendor /app /app

ENV PATH=/app/.venv/bin:${PATH} \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_WORKERS=1 \
    HEALTH_PATH=/health \
    XDG_CACHE_HOME=/tmp \
    XDG_CONFIG_HOME=/tmp \
    XDG_DATA_HOME=/tmp

EXPOSE 8000

USER 33:33

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os, sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.environ['APP_PORT'] + os.environ['HEALTH_PATH'], timeout=4).status < 400 else 1)" || exit 1

ENTRYPOINT ["python", "-m", "bootstrap"]

FROM ${BACKUP_IMAGE} AS backup

RUN apk add --no-cache aws-cli

COPY --chmod=0755 backup.sh /usr/local/bin/backup

ENV HOME=/tmp

USER postgres

ENTRYPOINT ["backup"]
