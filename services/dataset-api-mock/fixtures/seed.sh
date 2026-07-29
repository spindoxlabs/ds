#!/usr/bin/env bash
# Seed the real dataset-api + rec-registry for the ds end-to-end flows.
#
# Idempotent, and safe to re-run after `task docker:restart` — which recreates
# the ds Postgres and therefore takes the physical table with it. The databases
# themselves are created by `docker-compose.dataset-api.yml`; everything below
# is content.
#
#   ./services/dataset-api-mock/fixtures/seed.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PG=dataspaces-postgres-1
# API/REG container names are derived from compose below, not hardcoded: the
# committed `.env` sets COMPOSE_PROJECT_NAME=dataspaces, which docker compose
# reads and which *overrides* this file's `name:` — so the containers are
# `dataspaces-*`, not `dataspaces-real-dataset-api-*`. Asking compose for the id
# is immune to whichever project name wins.
KEYCLOAK=${KEYCLOAK_URL:-http://localhost:9080}

# `task docker:restart` recreates the ds Postgres, taking these databases with
# it. Bringing the compose up re-runs `db-create` and re-migrates; the API then
# needs a restart because its pool still holds connections to a server that went
# away. Both are no-ops when nothing changed.
echo "→ stack"
ROOT="$(cd "$HERE/../../.." && pwd)"
docker compose -f "$ROOT/docker-compose.dataset-api.yml" up -d >/dev/null
docker compose -f "$ROOT/docker-compose.dataset-api.yml" restart dataset-api-real >/dev/null
sleep 8

API=$(docker compose -f "$ROOT/docker-compose.dataset-api.yml" ps -q dataset-api-real)
REG=$(docker compose -f "$ROOT/docker-compose.dataset-api.yml" ps -q rec-registry)
if [ -z "$API" ] || [ -z "$REG" ]; then
  echo "could not resolve dataset-api/rec-registry containers from compose" >&2
  exit 1
fi

echo "→ token"
TOKEN=$(curl -sf -X POST "$KEYCLOAK/realms/dataspaces/protocol/openid-connect/token" \
  -d "grant_type=client_credentials&client_id=svc-ds-e2e&client_secret=svc-ds-e2e" |
  python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

echo "→ physical table"
# `ds-e2e-METER-9999` belongs to nobody: the negative control. A run that
# returns it has lost the row filter, and that must fail loudly rather than look
# like a bigger result set.
docker exec -i "$PG" psql -q -U postgres -d datasets <<'SQL'
CREATE SCHEMA IF NOT EXISTS ds_e2e;
CREATE TABLE IF NOT EXISTS ds_e2e.meters_15m (
  timestamp timestamptz NOT NULL,
  device_id text NOT NULL,
  kwh double precision NOT NULL
);
TRUNCATE ds_e2e.meters_15m;
INSERT INTO ds_e2e.meters_15m VALUES
  ('2026-05-11T08:00:00Z','ds-e2e-METER-0001',0.42),
  ('2026-05-11T08:15:00Z','ds-e2e-METER-0001',0.37),
  ('2026-05-11T08:00:00Z','ds-e2e-METER-0002',0.55),
  ('2026-05-11T08:15:00Z','ds-e2e-METER-0002',0.51),
  ('2026-05-11T08:00:00Z','ds-e2e-METER-9999',9.99);
SQL

echo "→ catalogue"
docker cp "$HERE/ds_e2e_catalogue.yaml" "$API:/tmp/ds_e2e_catalogue.yaml" >/dev/null
docker exec "$API" dataset-cli import catalogue \
  -i /tmp/ds_e2e_catalogue.yaml --api-url http://localhost:8001 | tail -2

echo "→ rec registry"
docker cp "$HERE/ds_e2e_rec.yaml" "$REG:/tmp/ds_e2e_rec.yaml" >/dev/null
# `--force` because a re-run finds the community already there; the import
# refuses otherwise rather than silently replacing members.
docker exec "$REG" sh -c \
  "celine-rec-registry import --file /tmp/ds_e2e_rec.yaml --api http://localhost:8004 --token '$TOKEN' --force" |
  tail -3

echo "✓ seeded"
