#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE app_user LOGIN PASSWORD '${APP_USER_PASSWORD}';
CREATE SCHEMA app AUTHORIZATION app_user;

CREATE TABLE app.request_log (
    id                bigserial PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    question          text NOT NULL,
    final_sql         text,
    status            text NOT NULL CHECK (status IN ('ok', 'error', 'refused', 'llm_error')),
    error_stage       text,
    error             text,
    attempts          int NOT NULL DEFAULT 1,
    attempt_errors    jsonb NOT NULL DEFAULT '[]',
    row_count         int,
    truncated         boolean,
    query_cost        double precision,
    latency_ms        int,
    prompt_tokens     int,
    completion_tokens int,
    model             text
);
ALTER TABLE app.request_log OWNER TO app_user;
CREATE INDEX request_log_created_at_idx ON app.request_log (created_at);
EOSQL
