#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

UVICORN_BIN="$ROOT_DIR/.venv/bin/uvicorn"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
FRONTEND_DIR="$ROOT_DIR/apps/web"
NEXT_BIN="$FRONTEND_DIR/node_modules/.bin/next"
NEXT_DEV_WRAPPER="$FRONTEND_DIR/scripts/dev.mjs"
SCHEDULER_SCRIPT="$ROOT_DIR/apps/scripts/prism_scheduler.py"
SCHEDULED_JOB_RUNNER="$ROOT_DIR/apps/scripts/prism_scheduled_job.py"
RUNTIME_DIR="$ROOT_DIR/data/runtime"

APP_MODULE="${PRISM_APP_MODULE:-control_panel.app:app}"
BACKEND_HOST="${PRISM_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PRISM_BACKEND_PORT:-8001}"
WEB_HOST="${PRISM_WEB_HOST:-127.0.0.1}"
WEB_PORT="${PRISM_WEB_PORT:-8000}"
BACKEND_ORIGIN="${PRISM_BACKEND_ORIGIN:-http://$BACKEND_HOST:$BACKEND_PORT}"
WEB_ORIGIN="${PRISM_WEB_ORIGIN:-http://$WEB_HOST:$WEB_PORT}"
PRISM_ENABLE_SCHEDULER="${PRISM_ENABLE_SCHEDULER:-1}"
PRISM_SCHEDULER_INTERVAL_SECONDS="${PRISM_SCHEDULER_INTERVAL_SECONDS:-20}"
PRISM_STARTUP_FORMAL_BOOTSTRAP="${PRISM_STARTUP_FORMAL_BOOTSTRAP:-1}"
PRISM_STARTUP_FORMAL_BOOTSTRAP_WAIT="${PRISM_STARTUP_FORMAL_BOOTSTRAP_WAIT:-0}"
PRISM_STARTUP_FORMAL_INDEX_BATCH_LIMIT="${PRISM_STARTUP_FORMAL_INDEX_BATCH_LIMIT:-0}"

pid_command() {
  ps -p "$1" -o command= 2>/dev/null || true
}

pid_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

path_is_under() {
  local path="$1"
  local parent="$2"
  [[ "$path" == "$parent" || "$path" == "$parent/"* ]]
}

is_prism_backend_pid() {
  local pid="$1"
  local cmd cwd
  cmd="$(pid_command "$pid")"
  cwd="$(pid_cwd "$pid")"

  [[ "$cmd" == *"$APP_MODULE"* ]] || return 1
  [[ "$cmd" == *"uvicorn"* || "$cmd" == *"$UVICORN_BIN"* ]] || return 1
  path_is_under "$cwd" "$ROOT_DIR" || [[ "$cmd" == *"$ROOT_DIR"* ]]
}

is_prism_web_pid() {
  local pid="$1"
  local cmd cwd
  cmd="$(pid_command "$pid")"
  cwd="$(pid_cwd "$pid")"

  [[ "$cmd" == *"$NEXT_DEV_WRAPPER"* || "$cmd" == *"next"* || "$cmd" == *"node"* ]] || return 1
  path_is_under "$cwd" "$FRONTEND_DIR" || [[ "$cmd" == *"$FRONTEND_DIR"* ]]
}

is_prism_scheduler_pid() {
  local pid="$1"
  local cmd cwd
  cmd="$(pid_command "$pid")"
  cwd="$(pid_cwd "$pid")"

  [[ "$cmd" == *"$SCHEDULER_SCRIPT"* ]] || return 1
  path_is_under "$cwd" "$ROOT_DIR" || [[ "$cmd" == *"$ROOT_DIR"* ]]
}

stop_pid() {
  local pid="$1"
  local label="$2"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  echo "[prism] Stopping existing Prism $label (pid=$pid)..."
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done

  echo "[prism] Existing Prism $label did not stop gracefully; forcing stop (pid=$pid)..."
  kill -9 "$pid" >/dev/null 2>&1 || true
}

stop_port_processes() {
  local label="$1"
  local port="$2"
  local matcher="$3"
  local pids pid cmd cwd port_var

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null | sort -u || true)"
  for pid in $pids; do
    if "$matcher" "$pid"; then
      stop_pid "$pid" "$label"
    else
      cmd="$(pid_command "$pid")"
      cwd="$(pid_cwd "$pid")"
      echo "[prism] Port $port is already used by a non-Prism process." >&2
      echo "[prism] pid=$pid" >&2
      echo "[prism] cwd=${cwd:-unknown}" >&2
      echo "[prism] command=${cmd:-unknown}" >&2
      case "$label" in
        backend) port_var="PRISM_BACKEND_PORT" ;;
        web) port_var="PRISM_WEB_PORT" ;;
        *) port_var="the matching PRISM_*_PORT variable" ;;
      esac
      echo "[prism] Stop that process or choose another port with $port_var." >&2
      exit 1
    fi
  done
}

stop_existing_scheduler() {
  local pids pid
  pids="$(pgrep -f "$SCHEDULER_SCRIPT" 2>/dev/null | sort -u || true)"
  for pid in $pids; do
    [[ "$pid" == "$$" ]] && continue
    if is_prism_scheduler_pid "$pid"; then
      stop_pid "$pid" "scheduler"
    fi
  done
}

setting_enabled() {
  case "${1:-}" in
    0|false|FALSE|no|NO|off|OFF) return 1 ;;
    *) return 0 ;;
  esac
}

run_formal_data_bootstrap() {
  if ! setting_enabled "$PRISM_STARTUP_FORMAL_BOOTSTRAP"; then
    echo "[prism] Formal data bootstrap disabled by PRISM_STARTUP_FORMAL_BOOTSTRAP=0"
    return 0
  fi

  if [[ ! -f "$SCHEDULED_JOB_RUNNER" ]]; then
    echo "[prism] Formal data bootstrap skipped; missing $SCHEDULED_JOB_RUNNER" >&2
    return 0
  fi

  local log_path="$RUNTIME_DIR/formal_data_bootstrap.log"
  echo "[prism] Starting formal data bootstrap..."
  PRISM_REPO_ROOT="$ROOT_DIR" \
    "$PYTHON_BIN" "$SCHEDULED_JOB_RUNNER" \
      --task-name formal_data_refresh \
      --allow-non-trading-day \
      --task-arg=--index-batch-limit \
      --task-arg "$PRISM_STARTUP_FORMAL_INDEX_BATCH_LIMIT" >> "$log_path" 2>&1 &
  FORMAL_BOOTSTRAP_PID=$!

  if setting_enabled "$PRISM_STARTUP_FORMAL_BOOTSTRAP_WAIT"; then
    if ! wait "$FORMAL_BOOTSTRAP_PID"; then
      echo "[prism] Formal data bootstrap failed; continuing. See $log_path" >&2
    fi
    FORMAL_BOOTSTRAP_PID=""
  else
    echo "[prism] Formal data bootstrap: background pid=$FORMAL_BOOTSTRAP_PID log=$log_path"
    FORMAL_BOOTSTRAP_PID=""
  fi
}

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
FORMAL_BOOTSTRAP_PID=""

echo "[prism] Checking for existing Prism services..."
stop_port_processes "backend" "$BACKEND_PORT" is_prism_backend_pid
stop_port_processes "web" "$WEB_PORT" is_prism_web_pid
stop_existing_scheduler
run_formal_data_bootstrap

echo "[prism] Starting Prism backend API..."
echo "[prism] Backend: $BACKEND_ORIGIN"
PRISM_WEB_HOST="$WEB_HOST" \
PRISM_WEB_PORT="$WEB_PORT" \
PRISM_WEB_ORIGIN="$WEB_ORIGIN" \
  "$UVICORN_BIN" "$APP_MODULE" --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!
SCHEDULER_PID=""
sleep 1
if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  echo "[prism] Backend failed to stay running on $BACKEND_ORIGIN." >&2
  exit 1
fi

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
  if [[ -n "$FORMAL_BOOTSTRAP_PID" ]] && kill -0 "$FORMAL_BOOTSTRAP_PID" >/dev/null 2>&1; then
    kill "$FORMAL_BOOTSTRAP_PID" >/dev/null 2>&1 || true
  fi
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
