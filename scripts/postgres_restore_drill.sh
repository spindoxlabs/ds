#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PRODUCTION_ENV_FILE:-${DATASPACE_ENV_FILE:-.env}}"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

COMPOSE_PROJECT_NAME_VALUE="${COMPOSE_PROJECT_NAME:-dataspaces-prod}"
REPORT_DIR="${REPORT_DIR:-reports/operations}"
DATABASE="${DATABASE:?Set DATABASE=connector or DATABASE=provenance}"
DUMP_PATH="${DUMP_PATH:?Set DUMP_PATH to a .dump file created by scripts/postgres_backup.sh}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RESTORE_DB="restore_drill_${DATABASE}_${TIMESTAMP}"
OPERATOR="${OPERATOR:-${USER:-unknown}}"
START_SECONDS="$(date +%s)"

compose_files=(
  -f docker-compose.yml
  -f docker-compose.runtime.yml
  -f docker-compose.production.yml
)

compose() {
  COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME_VALUE" COMPOSE_IGNORE_ORPHANS=true \
    docker compose --env-file "$ENV_FILE" "${compose_files[@]}" "$@"
}

mkdir -p "$REPORT_DIR"

if [ ! -f "$DUMP_PATH" ]; then
  echo "Dump not found: $DUMP_PATH" >&2
  exit 1
fi

cleanup() {
  compose exec -T postgres sh -c '
    if [ -f /run/secrets/postgres_password ]; then
      export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    else
      export PGPASSWORD="${PGPASSWORD:-postgres}"
    fi
    dropdb -U postgres --if-exists "$1"
  ' sh "$RESTORE_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

compose exec -T postgres sh -c '
  if [ -f /run/secrets/postgres_password ]; then
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
  else
    export PGPASSWORD="${PGPASSWORD:-postgres}"
  fi
  createdb -U postgres "$1"
' sh "$RESTORE_DB"

compose exec -T postgres sh -c '
  if [ -f /run/secrets/postgres_password ]; then
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
  else
    export PGPASSWORD="${PGPASSWORD:-postgres}"
  fi
  pg_restore -U postgres -d "$1"
' sh "$RESTORE_DB" < "$DUMP_PATH"

compose exec -T postgres sh -c '
  if [ -f /run/secrets/postgres_password ]; then
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
  else
    export PGPASSWORD="${PGPASSWORD:-postgres}"
  fi
  psql -U postgres -d "$1" -v ON_ERROR_STOP=1 -c "select 1;"
' sh "$RESTORE_DB" >/dev/null

END_SECONDS="$(date +%s)"
DURATION_SECONDS="$((END_SECONDS - START_SECONDS))"
SHA256="$(sha256sum "$DUMP_PATH" | cut -d " " -f1)"

python3 - "$REPORT_DIR" "$TIMESTAMP" "$OPERATOR" "$DATABASE" "$DUMP_PATH" "$SHA256" "$RESTORE_DB" "$DURATION_SECONDS" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
timestamp, operator, database, dump_path, sha256, restore_db, duration = sys.argv[2:]
payload = {
    "type": "postgres-restore-drill",
    "timestamp": timestamp,
    "operator": operator,
    "database": database,
    "dump_path": dump_path,
    "sha256": sha256,
    "restored_to": restore_db,
    "duration_seconds": int(duration),
    "result": "pass",
}
json_path = report_dir / f"postgres-restore-drill-{database}-{timestamp}.json"
md_path = report_dir / f"postgres-restore-drill-{database}-{timestamp}.md"
json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
md_path.write_text(
    "\n".join([
        "# PostgreSQL Restore Drill Evidence",
        "",
        f"Timestamp: `{timestamp}`",
        f"Operator: `{operator}`",
        f"Database: `{database}`",
        f"Dump path: `{dump_path}`",
        f"SHA256: `{sha256}`",
        f"Restored to: `{restore_db}`",
        f"Duration seconds: `{duration}`",
        "Result: `pass`",
    ]) + "\n"
)
print(json_path)
print(md_path)
PY

printf 'PostgreSQL restore drill PASS database=%s restored_to=%s duration_seconds=%s\n' "$DATABASE" "$RESTORE_DB" "$DURATION_SECONDS"
