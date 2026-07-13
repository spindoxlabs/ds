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
PROVENANCE_RETENTION_DAYS="${PROVENANCE_RETENTION_DAYS:-365}"
ACCESS_LOG_RETENTION_DAYS="${ACCESS_LOG_RETENTION_DAYS:-365}"
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

mkdir -p "$REPORT_DIR"

result="$(
  compose exec -T postgres sh -c '
    if [ -f /run/secrets/postgres_password ]; then
      export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    else
      export PGPASSWORD="${PGPASSWORD:-postgres}"
    fi
    psql -U postgres -d provenance -v ON_ERROR_STOP=1 -At \
      -v domain_days="$1" \
      -v access_days="$2" <<'"'"'SQL'"'"'
WITH deleted_domain AS (
  DELETE FROM domain_events
  WHERE received_at < now() - (CAST(:'"'"'domain_days'"'"' AS text) || '"'"' days'"'"')::interval
  RETURNING 1
),
deleted_access AS (
  DELETE FROM access_log
  WHERE logged_at < now() - (CAST(:'"'"'access_days'"'"' AS text) || '"'"' days'"'"')::interval
  RETURNING 1
)
SELECT
  (SELECT count(*) FROM deleted_domain)::text || '"'"','"'"' ||
  (SELECT count(*) FROM deleted_access)::text;
SQL
  ' sh "$PROVENANCE_RETENTION_DAYS" "$ACCESS_LOG_RETENTION_DAYS"
)"

domain_deleted="${result%,*}"
access_deleted="${result#*,}"

python3 - "$REPORT_DIR" "$TIMESTAMP" "$OPERATOR" "$PROVENANCE_RETENTION_DAYS" "$ACCESS_LOG_RETENTION_DAYS" "$domain_deleted" "$access_deleted" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
timestamp, operator, domain_days, access_days, domain_deleted, access_deleted = sys.argv[2:]
payload = {
    "type": "provenance-retention",
    "timestamp": timestamp,
    "operator": operator,
    "domain_event_retention_days": int(domain_days),
    "access_log_retention_days": int(access_days),
    "deleted": {
        "domain_events": int(domain_deleted),
        "access_log": int(access_deleted),
    },
}
json_path = report_dir / f"provenance-retention-{timestamp}.json"
md_path = report_dir / f"provenance-retention-{timestamp}.md"
json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
md_path.write_text(
    "\n".join([
        "# Provenance Retention Evidence",
        "",
        f"Timestamp: `{timestamp}`",
        f"Operator: `{operator}`",
        f"Domain event retention days: `{domain_days}`",
        f"Access log retention days: `{access_days}`",
        f"Deleted domain events: `{domain_deleted}`",
        f"Deleted access log entries: `{access_deleted}`",
    ]) + "\n"
)
print(json_path)
print(md_path)
PY

printf 'Provenance retention PASS domain_events_deleted=%s access_log_deleted=%s\n' "$domain_deleted" "$access_deleted"
