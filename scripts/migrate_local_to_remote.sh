#!/usr/bin/env bash
# One-time migration: copies all *data* (not schema) from the local evidence_db into
# a shared remote Postgres (Supabase, Neon, ...) that already has schema.sql applied
# (run scripts/apply_schema.sh against it first). Safe to re-run -- it's data-only, so
# it will fail loudly on duplicate rows rather than silently double-inserting, since
# every table's primary key is a UUID with a uniqueness constraint.
#
# Usage:
#   ./scripts/migrate_local_to_remote.sh "postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres"
set -euo pipefail

REMOTE_URL="${1:?Usage: $0 <remote-postgres-url>}"
REMOTE_URL="${REMOTE_URL/postgresql+psycopg2:\/\//postgresql://}"

LOCAL_URL="postgresql://evidence_user:evidence_pass@localhost:5432/evidence_db"
DUMP_FILE="/tmp/evidence_db_data_$(date +%s).dump"

echo "==> Dumping data-only from local evidence_db..."
pg_dump "$LOCAL_URL" --data-only --format=custom --file="$DUMP_FILE"

echo "==> Restoring into remote (schema must already exist -- run apply_schema.sh first)..."
pg_restore --data-only --no-owner --no-privileges --dbname="$REMOTE_URL" "$DUMP_FILE"

rm -f "$DUMP_FILE"
echo "==> Done. Verify with: psql \"$REMOTE_URL\" -c 'SELECT count(*) FROM videos;'"
