#!/usr/bin/env bash
set -Eeuo pipefail

: "${APP_DB_NAME:?Missing APP_DB_NAME}"
: "${APP_DB_USER:?Missing APP_DB_USER}"
: "${APP_DB_PASSWORD:?Missing APP_DB_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres \
    -v app_user="${APP_DB_USER}" -v app_password="${APP_DB_PASSWORD}" -v app_db="${APP_DB_NAME}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS CREATEDB PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0 ENCODING ''UTF8''', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') \gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'app_db') \gexec
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements'

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${APP_DB_NAME}" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
SQL
