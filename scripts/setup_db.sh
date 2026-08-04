#!/usr/bin/env bash
# Provisions the local PostgreSQL role/database and applies src/db/schema.sql.
# Usage: ./scripts/setup_db.sh
set -euo pipefail

DB_NAME="${EVIDENCE_DB_NAME:-evidence_db}"
DB_USER="${EVIDENCE_DB_USER:-evidence_user}"
DB_PASS="${EVIDENCE_DB_PASS:-evidence_pass}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../src/db/schema.sql"

echo "==> Ensuring PostgreSQL server is running (brew services)"
brew services start postgresql@14 >/dev/null 2>&1 || brew services start postgresql >/dev/null 2>&1 || true
sleep 2

echo "==> Creating role '$DB_USER' (if missing)"
psql postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 \
  || psql postgres -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"

echo "==> Creating database '$DB_NAME' (if missing)"
psql postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
  || psql postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

echo "==> Applying schema.sql"
PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE"

echo "==> Done. Connection string:"
echo "postgresql+psycopg2://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
