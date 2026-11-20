#!/usr/bin/env bash
# Set up and start a user-managed PostgreSQL cluster for local development.
#
# This machine has no Docker, so instead of docker-compose we run a private
# cluster owned by the current user (Postgres refuses to run as root, but
# works fine unprivileged). The script is idempotent: it creates the data
# directory and role/database only if they do not exist yet.
#
# Usage: scripts/dev-db.sh
set -euo pipefail

# Locate the Postgres binaries (PATH first, then Arch/Debian layouts).
PG_BIN=""
if command -v initdb >/dev/null 2>&1; then
  PG_BIN="$(dirname "$(command -v initdb)")"
else
  for d in /usr/lib/postgresql/bin /usr/lib/postgresql/*/bin; do
    if [ -x "$d/initdb" ]; then
      PG_BIN="$d"
      break
    fi
  done
fi
if [ -z "$PG_BIN" ]; then
  echo "error: postgresql binaries not found. Install with: sudo pacman -S --needed postgresql" >&2
  exit 1
fi

DATA_DIR="${CRONOS_PG_DATA:-$HOME/.cronos/pgdata}"
SOCK_DIR="$HOME/.cronos/pgsock"
PORT="${CRONOS_PG_PORT:-5432}"

# Create the data directory on first run.
if [ ! -d "$DATA_DIR" ]; then
  echo "Initializing new cluster at $DATA_DIR ..."
  mkdir -p "$(dirname "$DATA_DIR")"
  "$PG_BIN/initdb" -D "$DATA_DIR" --auth-local=trust --auth-host=scram-sha-256
fi

# Start the server if it is not already running.
if ! "$PG_BIN/pg_ctl" -D "$DATA_DIR" status >/dev/null 2>&1; then
  echo "Starting PostgreSQL on port $PORT ..."
  mkdir -p "$(dirname "$DATA_DIR")" "$SOCK_DIR"
  # -k: use a user-writable socket directory (the default /run/postgresql
  # requires root to create). All client calls below use TCP (-h localhost).
  "$PG_BIN/pg_ctl" -D "$DATA_DIR" -o "-p $PORT -k $SOCK_DIR" -l "$HOME/.cronos/pg.log" start
  # Wait until the server accepts connections.
  for _ in $(seq 1 30); do
    if "$PG_BIN/pg_isready" -h localhost -p "$PORT" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi

# Create the application role and database if missing (idempotent).
# Admin calls go over the local socket as the OS user (trust auth); initdb
# created a superuser role matching that username.
"$PG_BIN/psql" -h "$SOCK_DIR" -U "$(id -un)" -d postgres -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cronos') THEN
      CREATE ROLE cronos LOGIN PASSWORD 'cronos';
   END IF;
END
$$;
SQL

if ! "$PG_BIN/psql" -h "$SOCK_DIR" -U "$(id -un)" -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname = 'cronos'" | grep -q 1; then
  echo "Creating database cronos ..."
  "$PG_BIN/createdb" -h "$SOCK_DIR" -U "$(id -un)" cronos
fi

# PostgreSQL 15+ no longer grants CREATE on the public schema to all users,
# so the application role must own the database (idempotent).
"$PG_BIN/psql" -h "$SOCK_DIR" -U "$(id -un)" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "ALTER DATABASE cronos OWNER TO cronos;"

echo "PostgreSQL ready: host=localhost port=$PORT role=cronos db=cronos"
echo "Data dir: $DATA_DIR (log: $HOME/.cronos/pg.log)"
