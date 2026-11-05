#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE reader LOGIN PASSWORD '${READER_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO reader;
GRANT USAGE ON SCHEMA public TO reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public GRANT SELECT ON TABLES TO reader;
ALTER ROLE reader SET default_transaction_read_only = on;
ALTER ROLE reader SET statement_timeout = '5s';

-- Credentials are never readable by the role that runs AI-generated SQL.
REVOKE SELECT ON staff FROM reader;
GRANT SELECT (staff_id, first_name, last_name, address_id, email, store_id, active) ON staff TO reader;
EOSQL
