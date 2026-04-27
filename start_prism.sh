#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UVICORN_BIN="$ROOT_DIR/.venv/bin/uvicorn"
FRONTEND_DIR="$ROOT_DIR/apps/web"
NEXT_BIN="$FRONTEND_DIR/node_modules/.bin/next"
NEXT_DEV_WRAPPER="$FRONTEND_DIR/scripts/dev.mjs"

APP_MODULE="${PRISM_APP_MODULE:-control_panel.app:app}"
BACKEND_HOST="${PRISM_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PRISM_BACKEND_PORT:-8001}"
WEB_HOST="${PRISM_WEB_HOST:-127.0.0.1}"
WEB_PORT="${PRISM_WEB_PORT:-8000}"
BACKEND_ORIGIN="${PRISM_BACKEND_ORIGIN:-http://$BACKEND_HOST:$BACKEND_PORT}"

if [[ ! -x "$UVICORN_BIN" ]]; then
  echo "[prism] Missing uvicorn at $UVICORN_BIN" >&2
  echo "[prism] Please create the local Python virtualenv first." >&2
  exit 1
fi

if [[ ! -x "$NEXT_BIN" ]]; then
  echo "[prism] Missing Next.js binary at $NEXT_BIN" >&2
  echo "[prism] Please install the web app dependencies in apps/web first." >&2
  exit 1
fi

if [[ ! -f "$NEXT_DEV_WRAPPER" ]]; then
  echo "[prism] Missing Next dev wrapper at $NEXT_DEV_WRAPPER" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[prism] Starting Prism backend API..."
echo "[prism] Backend: $BACKEND_ORIGIN"
"$UVICORN_BIN" "$APP_MODULE" --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[prism] Starting Prism Next web app..."
echo "[prism] URL: http://$WEB_HOST:$WEB_PORT"
echo "[prism] Stop: Ctrl+C"

cd "$FRONTEND_DIR"
PRISM_BACKEND_ORIGIN="$BACKEND_ORIGIN" node "$NEXT_DEV_WRAPPER" --hostname "$WEB_HOST" --port "$WEB_PORT"
