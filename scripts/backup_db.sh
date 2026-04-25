#!/usr/bin/env bash
set -euo pipefail

# Backup Mission Control Postgres DB to a gzip-compressed dump.
# Keeps the last 30 backups and deletes older ones.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
ENV_FILE="${PROJECT_ROOT}/.env"

# Load env vars
if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

POSTGRES_DB="${POSTGRES_DB:-mission_control}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
KEEP_N="${KEEP_N:-30}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTFILE="${BACKUP_DIR}/mc-${TIMESTAMP}.sql.gz"

echo "[backup] Starting pg_dump of ${POSTGRES_DB} ..."

# Verify DB container is healthy
if ! docker compose -f "${PROJECT_ROOT}/compose.yml" ps db | grep -q "healthy"; then
  echo "[backup] ERROR: db container is not healthy. Aborting." >&2
  exit 1
fi

# Run pg_dump through the running container and gzip
PGPASSWORD="${POSTGRES_PASSWORD}" docker compose -f "${PROJECT_ROOT}/compose.yml" exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --no-privileges \
  | gzip > "${OUTFILE}"

echo "[backup] Wrote ${OUTFILE} ($(du -h "${OUTFILE}" | cut -f1))"

# Prune old backups
BACKUP_COUNT="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'mc-*.sql.gz' | wc -l)"
if [ "${BACKUP_COUNT}" -gt "${KEEP_N}" ]; then
  echo "[backup] Pruning backups older than the latest ${KEEP_N} ..."
  find "${BACKUP_DIR}" -maxdepth 1 -name 'mc-*.sql.gz' -printf '%T@ %p\n' | \
    sort -rn | tail -n +$((KEEP_N + 1)) | cut -d' ' -f2- | \
    while read -r oldfile; do
      echo "[backup] Removing ${oldfile}"
      rm -f "${oldfile}"
    done
fi

echo "[backup] Done."
