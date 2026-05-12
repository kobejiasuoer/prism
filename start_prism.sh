#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UVICORN_BIN="$ROOT_DIR/.venv/bin/uvicorn"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
FRONTEND_DIR="$ROOT_DIR/apps/web"
NEXT_BIN="$FRONTEND_DIR/node_modules/.bin/next"
NEXT_DEV_WRAPPER="$FRONTEND_DIR/scripts/dev.mjs"
SCHEDULER_SCRIPT="$ROOT_DIR/apps/scripts/prism_scheduler.py"
RUNTIME_DIR="$ROOT_DIR/data/runtime"

APP_MODULE="${PRISM_APP_MODULE:-control_panel.app:app}"
BACKEND_HOST="${PRISM_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PRISM_BACKEND_PORT:-8001}"
WEB_HOST="${PRISM_WEB_HOST:-127.0.0.1}"
WEB_PORT="${PRISM_WEB_PORT:-8000}"
BACKEND_ORIGIN="${PRISM_BACKEND_ORIGIN:-http://$BACKEND_HOST:$BACKEND_PORT}"
PRISM_ENABLE_SCHEDULER="${PRISM_ENABLE_SCHEDULER:-1}"
PRISM_SCHEDULER_INTERVAL_SECONDS="${PRISM_SCHEDULER_INTERVAL_SECONDS:-20}"

if [[ ! -x "$UVICORN_BIN" ]]; then
  echo "[prism] Missing uvicorn at $UVICORN_BIN" >&2
  echo "[prism] Please create the local Python virtualenv first." >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[prism] Missing python at $PYTHON_BIN" >&2
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

if [[ "$PRISM_ENABLE_SCHEDULER" != "0" && ! -f "$SCHEDULER_SCRIPT" ]]; then
  echo "[prism] Missing Prism scheduler at $SCHEDULER_SCRIPT" >&2
  exit 1
fi

cd "$ROOT_DIR"
mkdir -p "$RUNTIME_DIR"

echo "[prism] Starting Prism backend API..."
echo "[prism] Backend: $BACKEND_ORIGIN"
"$UVICORN_BIN" "$APP_MODULE" --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!
SCHEDULER_PID=""

if [[ "$PRISM_ENABLE_SCHEDULER" != "0" ]]; then
  echo "[prism] Starting Prism scheduler..."
  PRISM_REPO_ROOT="$ROOT_DIR" \
  PRISM_SCHEDULER_INTERVAL_SECONDS="$PRISM_SCHEDULER_INTERVAL_SECONDS" \
    "$PYTHON_BIN" "$SCHEDULER_SCRIPT" >> "$RUNTIME_DIR/prism_scheduler.log" 2>&1 &
  SCHEDULER_PID=$!
  sleep 1
  if ! kill -0 "$SCHEDULER_PID" >/dev/null 2>&1; then
    echo "[prism] Scheduler failed to stay running. See $RUNTIME_DIR/prism_scheduler.log" >&2
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    exit 1
  fi
else
  echo "[prism] Scheduler disabled by PRISM_ENABLE_SCHEDULER=0"
fi

cleanup() {
  if [[ -n "$SCHEDULER_PID" ]] && kill -0 "$SCHEDULER_PID" >/dev/null 2>&1; then
    kill "$SCHEDULER_PID" >/dev/null 2>&1 || true
  fi
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[prism] Starting Prism Next web app..."
echo "[prism] URL: http://$WEB_HOST:$WEB_PORT"
echo "[prism] Stop: Ctrl+C"
if [[ "$PRISM_ENABLE_SCHEDULER" != "0" ]]; then
  echo "[prism] Scheduler: enabled (Prism internal, interval ${PRISM_SCHEDULER_INTERVAL_SECONDS}s)"
fi

cd "$FRONTEND_DIR"
PRISM_BACKEND_ORIGIN="$BACKEND_ORIGIN" node "$NEXT_DEV_WRAPPER" --hostname "$WEB_HOST" --port "$WEB_PORT"
