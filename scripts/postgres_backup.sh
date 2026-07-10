#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PRODUCTION_ENV_FILE:-${DATASPACE_ENV_FILE:-.env}}"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

COMPOSE_PROJECT_NAME_VALUE="${COMPOSE_PROJECT_NAME:-dataspaces-prod}"
BACKUP_DIR="${BACKUP_DIR:-data/backups/postgres}"
REPORT_DIR="${REPORT_DIR:-reports/operations}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
DATABASES="${DATABASES:-connector provenance}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OPERATOR="${OPERATOR:-${USER:-unknown}}"

compose_files=(
  -f docker-compose.yml
  -f docker-compose.runtime.yml
  -f docker-compose.production.yml
)

compose() {
  COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME_VALUE" COMPOSE_IGNORE_ORPHANS=true \
    docker compose --env-file "$ENV_FILE" "${compose_files[@]}" "$@"
}

mkdir -p "$BACKUP_DIR" "$REPORT_DIR"

json_items=()
md_items=()

for database in $DATABASES; do
  dump_id="${database}_${TIMESTAMP}"
  dump_path="${BACKUP_DIR}/${dump_id}.dump"
  sha_path="${dump_path}.sha256"

  compose exec -T postgres sh -c '
    if [ -f /run/secrets/postgres_password ]; then
      export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    else
      export PGPASSWORD="${PGPASSWORD:-postgres}"
    fi
    pg_dump -U postgres -Fc "$1"
  ' sh "$database" > "$dump_path"

  sha256sum "$dump_path" > "$sha_path"
  sha256="$(cut -d " " -f1 "$sha_path")"
  size_bytes="$(wc -c < "$dump_path" | tr -d " ")"

  json_items+=("$(python3 - "$database" "$dump_id" "$dump_path" "$sha256" "$size_bytes" <<'PY'
import json
import sys
database, dump_id, path, sha256, size = sys.argv[1:]
print(json.dumps({
    "database": database,
    "dump_id": dump_id,
    "path": path,
    "sha256": sha256,
    "size_bytes": int(size),
}))
PY
)")
  md_items+=("- database=${database} dump_id=${dump_id} path=${dump_path} sha256=${sha256} size_bytes=${size_bytes}")
done

if [ "$RETENTION_DAYS" -gt 0 ]; then
  find "$BACKUP_DIR" -type f \( -name '*.dump' -o -name '*.dump.sha256' \) -mtime +"$RETENTION_DAYS" -print -delete > "${REPORT_DIR}/postgres-backup-retention-${TIMESTAMP}.log"
fi

python3 - "$REPORT_DIR" "$TIMESTAMP" "$OPERATOR" "$RETENTION_DAYS" "${json_items[@]}" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
timestamp = sys.argv[2]
operator = sys.argv[3]
retention_days = int(sys.argv[4])
items = [json.loads(raw) for raw in sys.argv[5:]]
payload = {
    "type": "postgres-backup",
    "timestamp": timestamp,
    "operator": operator,
    "retention_days": retention_days,
    "dumps": items,
}
json_path = report_dir / f"postgres-backup-{timestamp}.json"
md_path = report_dir / f"postgres-backup-{timestamp}.md"
json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
lines = [
    "# PostgreSQL Backup Evidence",
    "",
    f"Timestamp: `{timestamp}`",
    f"Operator: `{operator}`",
    f"Retention days: `{retention_days}`",
    "",
    "| Database | Dump id | Size bytes | SHA256 | Path |",
    "| --- | --- | ---: | --- | --- |",
]
for item in items:
    lines.append(
        f"| {item['database']} | {item['dump_id']} | {item['size_bytes']} | {item['sha256']} | `{item['path']}` |"
    )
md_path.write_text("\n".join(lines) + "\n")
print(json_path)
print(md_path)
PY

printf 'PostgreSQL backup PASS timestamp=%s databases="%s" backup_dir=%s\n' "$TIMESTAMP" "$DATABASES" "$BACKUP_DIR"
