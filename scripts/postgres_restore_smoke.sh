#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${DATASPACE_ENV_FILE:-.env}"
DATABASE="${1:-connector}"
TMP_DB="restore_smoke_${DATABASE}_$(date +%s)"
DUMP_PATH="/tmp/${TMP_DB}.dump"

compose() {
  COMPOSE_PROJECT_NAME=dataspaces COMPOSE_IGNORE_ORPHANS=true docker compose --env-file "$ENV_FILE" "$@"
}

compose ps postgres >/dev/null
compose exec -T postgres pg_isready -U postgres >/dev/null
compose exec -T postgres pg_dump -U postgres -Fc "$DATABASE" -f "$DUMP_PATH"
compose exec -T postgres createdb -U postgres "$TMP_DB"
trap 'compose exec -T postgres dropdb -U postgres --if-exists "$TMP_DB" >/dev/null 2>&1 || true; compose exec -T postgres rm -f "$DUMP_PATH" >/dev/null 2>&1 || true' EXIT
compose exec -T postgres pg_restore -U postgres -d "$TMP_DB" "$DUMP_PATH"
compose exec -T postgres psql -U postgres -d "$TMP_DB" -v ON_ERROR_STOP=1 -c 'select 1;' >/dev/null

echo "PostgreSQL restore smoke PASS database=$DATABASE restored_to=$TMP_DB"
