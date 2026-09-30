#!/usr/bin/env bash
# Start the full stack: provider gateway, then the app.
# The MCP server is not started here — the agent launches it over stdio.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-.venv/bin/python}"
PORT="${PROVIDER_API_PORT:-8000}"
# Access logs are on so you can watch the agent's calls arrive. Set
# PROVIDER_API_TRACE=1 for a timing/size line per request, or =body to print
# each response body as well.
LOG_LEVEL="${PROVIDER_API_LOG_LEVEL:-info}"

if [ ! -f db/cases.db ]; then
  echo "Seeding the case database..."
  "$PYTHON" db/seed.py
fi

echo "Starting provider gateway on :$PORT  (docs: http://127.0.0.1:$PORT/docs)"
"$PYTHON" -m uvicorn provider_api.main:app --port "$PORT" --log-level "$LOG_LEVEL" &
GATEWAY_PID=$!
trap 'kill $GATEWAY_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "Gateway did not start; the app will fall back to in-process lookups." >&2
fi

echo "Starting Streamlit..."
"$PYTHON" -m streamlit run app.py
