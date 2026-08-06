#!/usr/bin/env bash
# Provision a THROWAWAY Postgres for the backend test suite.
#
# The tests must never touch the application database, so they refuse to run
# without TEST_DATABASE_URL. This script gets one up by whatever means the
# machine has, in order of preference:
#
#   1. a server already listening on TEST_DB_PORT   (nothing to do)
#   2. Docker                                       (postgres:16-alpine)
#   3. a local Postgres install                     (initdb into a temp cluster)
#
# Usage:  ./scripts/test_db.sh start|stop
set -euo pipefail

PORT="${TEST_DB_PORT:-55432}"
DB="${TEST_DB_NAME:-majordairy_test}"
CONTAINER="${TEST_DB_CONTAINER:-majordairy-test-db}"
CLUSTER="${TMPDIR:-/tmp}/majordairy-test-pg"

have()      { command -v "$1" >/dev/null 2>&1; }
listening() { (exec 3<>"/dev/tcp/127.0.0.1/$PORT") >/dev/null 2>&1; }
docker_up() { have docker && docker info >/dev/null 2>&1; }

# Something answering on the port is NOT proof it's ours — it may be an
# unrelated server we have no business writing to. Only reuse a cluster we can
# actually authenticate against with the test credentials.
ours() {
  have psql || return 1
  PGPASSWORD=postgres psql -h 127.0.0.1 -p "$PORT" -U postgres \
    -tAc 'SELECT 1' >/dev/null 2>&1
}

wait_ready() {
  printf 'waiting for test db on :%s' "$PORT"
  for _ in $(seq 1 60); do
    if listening; then printf ' ready\n'; return 0; fi
    printf '.'; sleep 1
  done
  printf '\n' >&2
  echo "test database never came up on port $PORT" >&2
  return 1
}

ensure_db() {
  # Create the database if this cluster doesn't have it yet.
  if have psql; then
    PGPASSWORD=postgres psql -h 127.0.0.1 -p "$PORT" -U postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$DB'" 2>/dev/null | grep -q 1 && return 0
    PGPASSWORD=postgres createdb -h 127.0.0.1 -p "$PORT" -U postgres "$DB" 2>/dev/null || true
  fi
}

start() {
  if listening; then
    if ours; then
      echo "reusing Postgres already listening on :$PORT"
      ensure_db
      return 0
    fi
    cat >&2 <<EOF
Port $PORT is taken by a server these credentials cannot authenticate against.
That is somebody else's database — refusing to touch it.

Pick a free port:  make test TEST_DB_PORT=<port>
EOF
    return 1
  fi

  if docker_up; then
    docker start "$CONTAINER" >/dev/null 2>&1 || \
      docker run -d --name "$CONTAINER" \
        -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB="$DB" \
        -p "$PORT:5432" postgres:16-alpine >/dev/null
    wait_ready
    return 0
  fi

  if have initdb && have pg_ctl; then
    if [ ! -d "$CLUSTER" ]; then
      echo "no Docker — creating a local throwaway cluster in $CLUSTER"
      # Force the C locale: initdb fails outright on hosts with an unset or
      # inconsistent LANG/LC_*, which is common in non-login shells.
      LC_ALL=C LANG=C initdb -D "$CLUSTER" -U postgres --auth=trust \
        --locale=C --encoding=UTF8 >/dev/null
    fi
    # LC_ALL must be set for the server too — macOS postmasters abort with
    # "became multithreaded during startup" under an unset locale.
    LC_ALL=C LANG=C pg_ctl -D "$CLUSTER" -o "-p $PORT -k $CLUSTER" \
      -l "$CLUSTER/server.log" start >/dev/null
    wait_ready
    ensure_db
    return 0
  fi

  cat >&2 <<'EOF'
Cannot provision a test database: no server on the port, no running Docker
daemon, and no local Postgres (initdb/pg_ctl) on PATH.

Install one of:
  · Docker Desktop, then re-run `make test`
  · brew install postgresql@16 && brew link postgresql@16

Or point the suite at any throwaway database yourself:
  TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db make test
EOF
  return 1
}

stop() {
  if docker_up && docker inspect "$CONTAINER" >/dev/null 2>&1; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "removed container $CONTAINER"
  fi
  if [ -d "$CLUSTER" ]; then
    pg_ctl -D "$CLUSTER" stop >/dev/null 2>&1 || true
    rm -rf "$CLUSTER"
    echo "removed cluster $CLUSTER"
  fi
}

case "${1:-start}" in
  start) start ;;
  stop)  stop ;;
  *)     echo "usage: $0 start|stop" >&2; exit 2 ;;
esac
