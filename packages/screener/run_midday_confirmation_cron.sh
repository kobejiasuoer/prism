#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$BASE_DIR/data/cron_logs"
RUN_STAMP="$(date "+%F_%H-%M-%S")"
LOG_PATH="$LOG_DIR/run_midday_confirmation_${RUN_STAMP}.log"

mkdir -p "$LOG_DIR"

echo "workflow_log=$LOG_PATH"

if SEND_TO_FEISHU="${SEND_TO_FEISHU:-1}" \
  FEISHU_TARGET="${FEISHU_TARGET:-user:ou_097f5fa4a2210f7eb5466836b4b00b8d}" \
  bash "$SCRIPT_DIR/run_midday_confirmation.sh" "$@" >"$LOG_PATH" 2>&1; then
  echo "workflow_status=ok"
  exit 0
fi

status=$?
echo "workflow_status=error exit_code=$status" >&2
tail -n 40 "$LOG_PATH" >&2 || true
exit "$status"
