#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$APP_ROOT/.." && pwd)"
RUN_DATE="${RUN_DATE:-$(date "+%F")}"
RUN_STAMP="${RUN_STAMP:-$(date "+%F_%H-%M-%S")}"
WATCHLIST_SEND_TO_FEISHU="${WATCHLIST_SEND_TO_FEISHU:-0}"
COMMAND_SEND_TO_FEISHU="${COMMAND_SEND_TO_FEISHU:-0}"
WATCHLIST_SKIP_FETCH="${WATCHLIST_SKIP_FETCH:-0}"
WATCHLIST_REPORT_PATH="${WATCHLIST_REPORT_PATH:-$WORKSPACE_ROOT/data/artifacts/analyzer/reports/analysis-report-${RUN_DATE}_${RUN_STAMP}.md}"
WATCHLIST_ERROR_PATH="${WATCHLIST_ERROR_PATH:-$WORKSPACE_ROOT/data/artifacts/analyzer/reports/analysis-error-${RUN_DATE}_${RUN_STAMP}.log}"

cd "$WORKSPACE_ROOT"

echo "[stage] refresh:start 自选股全流程已启动"
echo "[stage] watchlist:start 正在更新自选股链路"
if [[ "$WATCHLIST_SKIP_FETCH" == "1" || "$WATCHLIST_SKIP_FETCH" == "true" ]]; then
  echo "watchlist_fetch -> skipped"
else
  mkdir -p "$(dirname "$WATCHLIST_REPORT_PATH")" "$(dirname "$WATCHLIST_ERROR_PATH")"
  set +e
  python3 "stock-analyzer/scripts/fetch.py" >"$WATCHLIST_REPORT_PATH" 2>"$WATCHLIST_ERROR_PATH"
  watchlist_status=$?
  set -e
  if [[ $watchlist_status -ne 0 ]]; then
    echo "[warn] 自选股刷新失败，沿用已有快照继续生成总控简报: $WATCHLIST_ERROR_PATH" >&2
  else
    PYTHONPATH="$WORKSPACE_ROOT:$WORKSPACE_ROOT/packages:${PYTHONPATH:-}" \
      python3 -m prism_storage.cli register-file "$WATCHLIST_REPORT_PATH" \
        --artifact-type analyzer_report \
        --source analyzer \
        --trade-date "$RUN_DATE" \
        --generated-at "$(date "+%F %T")" \
        --metadata-json "{\"run_stamp\":\"$RUN_STAMP\"}" >/dev/null 2>&1 || true
  fi
fi
echo "[stage] watchlist:done 自选股链路已完成"

echo "[stage] command_brief:start 正在刷新总控简报"
TRADE_DATE="$RUN_DATE" \
RUN_STAMP="$RUN_STAMP" \
SEND_TO_FEISHU="$COMMAND_SEND_TO_FEISHU" \
bash "apps/scripts/run_command_brief.sh"
echo "[stage] command_brief:done 总控简报已刷新"

echo "[stage] refresh:done 自选股全流程已完成"
echo "watchlist_workflow -> $RUN_DATE"
echo "command_brief -> $RUN_STAMP"
