#!/usr/bin/env bash
# Starts both processes in one container. If either one stops, the container exits,
# so the hosting platform restarts the whole service instead of leaving it half-working.
set -u

cd /app/gen-service
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
GEN_PID=$!

cd /app/api
node src/server.js &
API_PID=$!

# When the platform asks the container to stop, pass that on to both processes so they shut down cleanly.
trap 'kill -TERM "$GEN_PID" "$API_PID" 2>/dev/null' TERM INT

wait -n "$GEN_PID" "$API_PID"
STATUS=$?
kill -TERM "$GEN_PID" "$API_PID" 2>/dev/null
wait
exit "$STATUS"