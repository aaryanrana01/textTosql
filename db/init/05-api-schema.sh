#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE api_user LOGIN PASSWORD '${API_USER_PASSWORD}';

CREATE TABLE app.users (
    id            bigserial PRIMARY KEY,
    email         text UNIQUE,
    password_hash text,
    is_guest      boolean NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (is_guest OR (email IS NOT NULL AND password_hash IS NOT NULL))
);

CREATE TABLE app.queries (
    id             bigserial PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    question       text NOT NULL,
    sql            text,
    status         text NOT NULL CHECK (status IN ('ok', 'error', 'refused')),
    refusal_reason text,
    error          text,
    result_columns jsonb NOT NULL DEFAULT '[]',
    result_rows    jsonb NOT NULL DEFAULT '[]',
    row_count      int NOT NULL DEFAULT 0,
    truncated      boolean NOT NULL DEFAULT false,
    latency_ms     int,
    feedback       smallint CHECK (feedback IN (-1, 1)),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX queries_user_created_idx ON app.queries (user_id, created_at DESC);

GRANT USAGE ON SCHEMA app TO api_user;
GRANT SELECT, INSERT, UPDATE ON app.users, app.queries TO api_user;
GRANT USAGE ON SEQUENCE app.users_id_seq, app.queries_id_seq TO api_user;
EOSQL