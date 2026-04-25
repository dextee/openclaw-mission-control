#!/usr/bin/env bash
set -euo pipefail

# Restore Mission Control Postgres DB from a gzip-compressed dump.
# Usage: scripts/restore_db.sh <path-to-dump.sql.gz>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <path-to-dump.sql.gz>" >&2
  exit 1
fi

DUMP_FILE="$1"

if [ ! -f "${DUMP_FILE}" ]; then
  echo "ERROR: dump file not found: ${DUMP_FILE}" >&2
  exit 1
fi

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

# Confirm
read -r -p "RESTORE ${POSTGRES_DB} from ${DUMP_FILE}? This will DESTROY existing data. Type YES: " confirm
if [ "${confirm}" != "YES" ]; then
  echo "Restore cancelled."
  exit 0
fi

# Verify DB container is healthy
if ! docker compose -f "${PROJECT_ROOT}/compose.yml" ps db | grep -q "healthy"; then
  echo "[restore] ERROR: db container is not healthy. Aborting." >&2
  exit 1
fi

echo "[restore] Dropping and recreating database ${POSTGRES_DB} ..."
PGPASSWORD="${POSTGRES_PASSWORD}" docker compose -f "${PROJECT_ROOT}/compose.yml" exec -T db \
  psql -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\";"

PGPASSWORD="${POSTGRES_PASSWORD}" docker compose -f "${PROJECT_ROOT}/compose.yml" exec -T db \
  psql -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE \"${POSTGRES_DB}\";"

echo "[restore] Restoring from ${DUMP_FILE} ..."
gunzip -c "${DUMP_FILE}" | \
  PGPASSWORD="${POSTGRES_PASSWORD}" docker compose -f "${PROJECT_ROOT}/compose.yml" exec -T db \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "[restore] Done."
