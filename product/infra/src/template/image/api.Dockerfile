ARG PYTHON_IMAGE
ARG UV_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build/product/api
COPY engine/python /build/engine/python
COPY product/api/pyproject.toml product/api/uv.lock ./
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-install-project --no-editable
FROM ${PYTHON_IMAGE}
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes --no-input pip
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY --from=dependencies /build/product/api/.venv /app/.venv
COPY --chown=10001:10001 product/api/app /app/app
COPY --chown=10001:10001 product/api/bootstrap /app/bootstrap
COPY --chown=10001:10001 product/api/config /app/config
COPY --chown=10001:10001 product/api/database /app/database
COPY --chown=10001:10001 product/api/public /app/public
COPY --chown=10001:10001 product/api/routes /app/routes
COPY --chown=10001:10001 product/api/storage /app/storage
COPY --chown=10001:10001 product/api/views /app/views
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-c", "import socket; socket.create_connection((\"127.0.0.1\", 8000), 2).close()"]
CMD ["python", "-m", "bootstrap", "serve"]
