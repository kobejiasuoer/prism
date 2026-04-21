#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_STAMP="${RUN_STAMP:-$(date "+%F_%H-%M-%S")}"
TRADE_DATE="${TRADE_DATE:-$(date "+%F")}"
BRIEF_OUTPUT_PATH="${BRIEF_OUTPUT_PATH:-$BASE_DIR/reports/prism_command_brief_${RUN_STAMP}.txt}"
REPORT_OUTPUT_PATH="${REPORT_OUTPUT_PATH:-$BASE_DIR/reports/prism_command_brief_${RUN_STAMP}.md}"
JSON_OUTPUT_PATH="${JSON_OUTPUT_PATH:-$BASE_DIR/data/command_brief/prism_command_brief_${RUN_STAMP}.json}"
SEND_TO_FEISHU="${SEND_TO_FEISHU:-0}"
FEISHU_CHANNEL="${FEISHU_CHANNEL:-feishu}"
FEISHU_TARGET="${FEISHU_TARGET:-}"

send_to_feishu() {
  if [[ "$SEND_TO_FEISHU" != "1" && "$SEND_TO_FEISHU" != "true" ]]; then
    return 0
  fi
  if [[ -z "$FEISHU_TARGET" ]]; then
    echo "SEND_TO_FEISHU 已开启，但 FEISHU_TARGET 为空" >&2
    return 1
  fi
  if ! command -v openclaw >/dev/null 2>&1; then
    echo "缺少 openclaw，无法发送飞书消息" >&2
    return 1
  fi
  if [[ ! -f "$BRIEF_OUTPUT_PATH" ]]; then
    echo "总控简报正文不存在，无法发送: $BRIEF_OUTPUT_PATH" >&2
    return 1
  fi

  local body
  body="$(cat "$BRIEF_OUTPUT_PATH")"
  local send_cmd=(
    openclaw message send
    --channel "$FEISHU_CHANNEL"
    --target "$FEISHU_TARGET"
    --message "$body"
  )
  if [[ -f "$REPORT_OUTPUT_PATH" ]]; then
    send_cmd+=(--media "$REPORT_OUTPUT_PATH")
  fi
  "${send_cmd[@]}" >/dev/null
}

python3 "$SCRIPT_DIR/generate_command_brief.py" \
  --date "$TRADE_DATE" \
  --brief-output "$BRIEF_OUTPUT_PATH" \
  --report-output "$REPORT_OUTPUT_PATH" \
  --json-output "$JSON_OUTPUT_PATH"

send_to_feishu

echo "brief -> $BRIEF_OUTPUT_PATH"
echo "report -> $REPORT_OUTPUT_PATH"
echo "json -> $JSON_OUTPUT_PATH"
