#!/usr/bin/env bash
# Applies src/db/schema.sql to any Postgres target -- local dev or a shared host
# (Supabase, Neon, etc). Unlike scripts/setup_db.sh, this does NOT create a role or
# database first; it assumes the target database already exists (true for every
# managed Postgres host, which auto-provisions one per project).
#
# Usage:
#   ./scripts/apply_schema.sh                          # uses DATABASE_URL from .env
#   ./scripts/apply_schema.sh "postgresql://..."       # explicit URL
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../src/db/schema.sql"

URL="${1:-}"
if [ -z "$URL" ]; then
  if [ -f "$SCRIPT_DIR/../.env" ]; then
    URL="$(grep -E '^DATABASE_URL=' "$SCRIPT_DIR/../.env" | head -1 | cut -d= -f2-)"
  fi
fi
if [ -z "$URL" ]; then
  echo "No URL given and DATABASE_URL not found in .env" >&2
  exit 1
fi

# psql wants postgresql://, SQLAlchemy uses postgresql+psycopg2:// -- normalise.
PSQL_URL="${URL/postgresql+psycopg2:\/\//postgresql://}"

echo "==> Applying schema.sql to $(echo "$PSQL_URL" | sed -E 's#(://[^:]+):[^@]+@#\1:***@#')"
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE"
echo "==> Done."
