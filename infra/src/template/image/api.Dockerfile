ARG PYTHON_IMAGE
ARG UV_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY api/pyproject.toml api/uv.lock ./
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-install-project
FROM ${PYTHON_IMAGE}
RUN python -m pip uninstall --yes --no-input pip
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY --from=dependencies /build/.venv /app/.venv
COPY --chown=10001:10001 api/src /app/src
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-c", "import socket; socket.create_connection((\"127.0.0.1\", 8000), 2).close()"]
CMD ["python", "-m", "bootstrap", "serve"]
