#!/usr/bin/env sh
set -eu

MODE="${1:-dump}"
STAMP="${2:-}"
RESTORE_DB="${3:-}"

BACKUP_TARGET="${BACKUP_TARGET:-local}"
BACKUP_PATH="${BACKUP_PATH:-/backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

: "${DB_HOST:?Missing DB_HOST}"
: "${DB_PORT:=5432}"
: "${DB_NAME:?Missing DB_NAME}"
: "${DB_USER:?Missing DB_USER}"
: "${PGPASSWORD:?Missing PGPASSWORD}"

export PGPASSWORD

FILE="$(mktemp /tmp/backup.XXXXXX)"

trap 'rm -f "${FILE}"' EXIT

s3 () {

    if [ -n "${S3_ENDPOINT:-}" ]; then aws s3 --endpoint-url "${S3_ENDPOINT}" "$@"; else aws s3 "$@"; fi

}
fetch () {

    if [ "${BACKUP_TARGET}" = "s3" ]; then

        : "${S3_BACKUP_BUCKET:?Missing S3_BACKUP_BUCKET}"

        s3 cp "s3://${S3_BACKUP_BUCKET}/${DB_NAME}/${1}.dump" "${FILE}"

    else

        cp "${BACKUP_PATH}/${DB_NAME}/${1}.dump" "${FILE}"

    fi

}
store () {

    if [ "${BACKUP_TARGET}" = "s3" ]; then

        s3 cp "${FILE}" "${1}"

    else

        mkdir -p "${BACKUP_PATH}/${DB_NAME}"
        cp "${FILE}" "${1}"
        chmod 0600 "${1}"

        find "${BACKUP_PATH}/${DB_NAME}" -name '*.dump' -type f -mtime "+${BACKUP_KEEP_DAYS}" -delete

    fi

}
listing () {

    if [ "${BACKUP_TARGET}" = "s3" ]; then

        : "${S3_BACKUP_BUCKET:?Missing S3_BACKUP_BUCKET}"

        s3 ls "s3://${S3_BACKUP_BUCKET}/${DB_NAME}/" --human-readable

    else

        ls -lh "${BACKUP_PATH}/${DB_NAME}" 2>/dev/null || echo "no backups yet"

    fi

}
await () {

    WAITED=0

    until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -q; do

        [ "${WAITED}" -lt 60 ] || { echo "❌ ${DB_HOST}:${DB_PORT} never accepted a connection"; exit 1; }

        WAITED=$(( WAITED + 2 ))
        sleep 2

    done

}

if [ "${MODE}" = "list" ]; then

    listing

    exit 0

fi

if [ "${MODE}" = "restore" ]; then

    [ -n "${STAMP}" ] || { echo "❌ Usage: backup restore <stamp> [target-db]"; exit 1; }

    RESTORE_DB="${RESTORE_DB:-${DB_NAME}_restore}"

    [ "${RESTORE_DB}" != "${DB_NAME}" ] || { echo "❌ Refusing to restore over '${DB_NAME}' — promotion is a deliberate act"; exit 1; }

    echo "🚀 Restoring ${STAMP} → ${RESTORE_DB}"

    await
    fetch "${STAMP}"

    [ -s "${FILE}" ] || { echo "❌ Backup '${STAMP}' not found"; exit 1; }

    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 \
        -tc "SELECT 1 FROM pg_database WHERE datname = '${RESTORE_DB}'" | grep -q 1 \
        || createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${RESTORE_DB}"

    pg_restore --clean --if-exists --single-transaction --exit-on-error --no-owner --no-privileges \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${RESTORE_DB}" "${FILE}"

    echo "✅ Restored into '${RESTORE_DB}' — verify it, then promote deliberately."

    exit 0

fi

STAMP="$(date -u +%Y%m%d-%H%M%S)"

if [ "${BACKUP_TARGET}" = "s3" ]; then

    : "${S3_BACKUP_BUCKET:?Missing S3_BACKUP_BUCKET}"
    TARGET="s3://${S3_BACKUP_BUCKET}/${DB_NAME}/${STAMP}.dump"

else

    TARGET="${BACKUP_PATH}/${DB_NAME}/${STAMP}.dump"

fi

echo "🚀 Backing up ${DB_NAME} → ${TARGET}"

await

pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-privileges -Fc -Z zstd -f "${FILE}"

SIZE="$(wc -c < "${FILE}")"

[ "${SIZE}" -gt 1024 ] || { echo "❌ Dump suspiciously small: ${SIZE} bytes"; exit 1; }

store "${TARGET}"

echo "✅ Backup complete (${SIZE} bytes) — ${STAMP}"
