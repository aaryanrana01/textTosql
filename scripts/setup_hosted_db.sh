#!/usr/bin/env bash
# Fills an EMPTY hosted Postgres database (such as Neon) with everything the project needs:
# the Pagila data, the three roles and the app tables, using the same setup scripts as local
# development and CI, then builds the vector indexes.
# Usage: bash scripts/setup_hosted_db.sh
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -p "Database host (e.g. ep-xxx.ap-southeast-1.aws.neon.tech): " DB_HOST
read -r -p "Admin user [neondb_owner]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-neondb_owner}
read -r -p "Database name [pagila]: " DB_NAME
DB_NAME=${DB_NAME:-pagila}
read -r -s -p "Admin password (from Neon): " ADMIN_PASSWORD; echo
read -r -s -p "New READER_PASSWORD: " READER_PASSWORD; echo
read -r -s -p "New APP_USER_PASSWORD: " APP_USER_PASSWORD; echo
read -r -s -p "New API_USER_PASSWORD: " API_USER_PASSWORD; echo

# The Pagila file says its tables belong to the local 'postgres' superuser, which doesn't exist on
# hosted databases, so those lines are left out of a temporary copy.
SCHEMA_COPY=$(mktemp)
trap 'rm -f "$SCHEMA_COPY"' EXIT
sed '/OWNER TO/d' db/init/01-pagila-schema.sql > "$SCHEMA_COPY"

echo "Loading data, roles and app tables (this can take a minute)..."
# createrole_self_grant: lets the admin account act as the roles it creates, so the setup scripts
# can hand tables over to app_user and api_user (a local superuser never needed this).
docker run --rm \
  -v "$PWD/db/init:/init:ro" -v "$SCHEMA_COPY:/tmp/schema.sql:ro" \
  -e PGHOST="$DB_HOST" -e PGUSER="$ADMIN_USER" -e PGPASSWORD="$ADMIN_PASSWORD" \
  -e PGDATABASE="$DB_NAME" -e PGSSLMODE=require \
  -e PGOPTIONS="-c createrole_self_grant=set,inherit" \
  -e POSTGRES_USER="$ADMIN_USER" -e POSTGRES_DB="$DB_NAME" \
  -e READER_PASSWORD="$READER_PASSWORD" -e APP_USER_PASSWORD="$APP_USER_PASSWORD" \
  -e API_USER_PASSWORD="$API_USER_PASSWORD" \
  pgvector/pgvector:pg18 bash -c '
    psql -v ON_ERROR_STOP=1 -q -f /tmp/schema.sql &&
    psql -v ON_ERROR_STOP=1 -q -f /init/02-pagila-data.sql &&
    bash /init/03-readonly-role.sh &&
    bash /init/04-app-schema.sh &&
    bash /init/05-api-schema.sh'

echo "Building vector indexes..."
source .venv/bin/activate
DB_HOST="$DB_HOST" DB_SSLMODE=require POSTGRES_DB="$DB_NAME" \
  READER_PASSWORD="$READER_PASSWORD" APP_USER_PASSWORD="$APP_USER_PASSWORD" \
  python scripts/build_indexes.py

echo "ALL DONE: the hosted database is ready."