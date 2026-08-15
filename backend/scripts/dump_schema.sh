#!/usr/bin/env bash
# Regenerate backend/schema.sql from the Alembic migrations.
#
# schema.sql is a reference snapshot, not the source of truth. It silently
# drifted to the 0004 state once, and a database provisioned from it crashed
# the ORM on the first farm query. Re-run this after adding a migration.
#
#   cd backend && ./scripts/dump_schema.sh
set -euo pipefail

PORT="${TEST_DB_PORT:-55432}"
DB="schemagen_$$"
CONTAINER="${TEST_DB_CONTAINER:-majordairy-test-db}"

cleanup() { docker exec "$CONTAINER" psql -U postgres -c "DROP DATABASE IF EXISTS $DB;" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker exec "$CONTAINER" psql -U postgres -c "CREATE DATABASE $DB;" >/dev/null
# 0001 references Supabase's auth schema, which does not exist in a bare
# Postgres — stub the two objects it needs so the chain can run.
docker exec "$CONTAINER" psql -U postgres -d "$DB" -c \
  "create schema if not exists auth;
   create table auth.users (id uuid primary key);
   create or replace function auth.uid() returns uuid as \$\$ select null::uuid \$\$ language sql;" >/dev/null

DB_HOST=localhost DB_PORT="$PORT" DB_USER=postgres DB_PASSWORD=postgres DB_NAME="$DB" \
SUPABASE_URL=x SUPABASE_SERVICE_KEY=x SUPABASE_ANON_KEY=x JWT_SECRET=x \
  .venv/bin/python -m alembic upgrade head >/dev/null

{
  cat <<'HDR'
-- Major Dairy AI — public schema, GENERATED from the Alembic migrations.
--
-- Do NOT hand-edit. Regenerate with:
--
--   cd backend && ./scripts/dump_schema.sh
--
-- Alembic remains the source of truth; this is a reference snapshot.

HDR
  docker exec "$CONTAINER" pg_dump -U postgres -d "$DB" --schema-only --no-owner --no-privileges --schema=public
} > schema.sql

echo "schema.sql regenerated ($(wc -l < schema.sql) lines)"
