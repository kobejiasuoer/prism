#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UVICORN_BIN="$ROOT_DIR/.venv/bin/uvicorn"
APP_MODULE="${PRISM_APP_MODULE:-control_panel.app:app}"
HOST="${PRISM_HOST:-127.0.0.1}"
PORT="${PRISM_PORT:-8000}"

if [[ ! -x "$UVICORN_BIN" ]]; then
  echo "[prism] Missing uvicorn at $UVICORN_BIN" >&2
  echo "[prism] Please create the local virtualenv first." >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[prism] Starting Prism control panel..."
echo "[prism] URL: http://$HOST:$PORT"
echo "[prism] Stop: Ctrl+C"

exec "$UVICORN_BIN" "$APP_MODULE" --host "$HOST" --port "$PORT"
