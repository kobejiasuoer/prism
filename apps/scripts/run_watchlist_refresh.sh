#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INVEST_FLOW_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$INVEST_FLOW_ROOT/../.." && pwd)"
RUN_DATE="${RUN_DATE:-$(date "+%F")}"
RUN_STAMP="${RUN_STAMP:-$(date "+%F_%H-%M-%S")}"
WATCHLIST_SEND_TO_FEISHU="${WATCHLIST_SEND_TO_FEISHU:-0}"
COMMAND_SEND_TO_FEISHU="${COMMAND_SEND_TO_FEISHU:-0}"

cd "$WORKSPACE_ROOT"

echo "[stage] refresh:start 自选股全流程已启动"
echo "[stage] watchlist:start 正在更新自选股链路"
RUN_DATE="$RUN_DATE" \
SEND_TO_FEISHU="$WATCHLIST_SEND_TO_FEISHU" \
bash "skills/stock-analyzer/scripts/run_watchlist_cron.sh"
echo "[stage] watchlist:done 自选股链路已完成"

echo "[stage] command_brief:start 正在刷新总控简报"
TRADE_DATE="$RUN_DATE" \
RUN_STAMP="$RUN_STAMP" \
SEND_TO_FEISHU="$COMMAND_SEND_TO_FEISHU" \
bash "skills/invest-flow/scripts/run_command_brief.sh"
echo "[stage] command_brief:done 总控简报已刷新"

echo "[stage] refresh:done 自选股全流程已完成"
echo "watchlist_workflow -> $RUN_DATE"
echo "command_brief -> $RUN_STAMP"
