#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BASE_DIR/.." && pwd)"
RUN_STAMP="${RUN_STAMP:-$(date "+%F_%H-%M-%S")}"
TRADE_DATE="${TRADE_DATE:-$(date "+%F")}"
COMMAND_BRIEF_ARTIFACT_DIR="${COMMAND_BRIEF_ARTIFACT_DIR:-$REPO_ROOT/data/artifacts/command_brief}"
BRIEF_OUTPUT_PATH="${BRIEF_OUTPUT_PATH:-$COMMAND_BRIEF_ARTIFACT_DIR/prism_command_brief_${RUN_STAMP}.txt}"
REPORT_OUTPUT_PATH="${REPORT_OUTPUT_PATH:-$COMMAND_BRIEF_ARTIFACT_DIR/prism_command_brief_${RUN_STAMP}.md}"
JSON_OUTPUT_PATH="${JSON_OUTPUT_PATH:-$COMMAND_BRIEF_ARTIFACT_DIR/prism_command_brief_${RUN_STAMP}.json}"
LEGACY_BRIEF_OUTPUT_PATH="${LEGACY_BRIEF_OUTPUT_PATH:-$BASE_DIR/reports/prism_command_brief_${RUN_STAMP}.txt}"
LEGACY_REPORT_OUTPUT_PATH="${LEGACY_REPORT_OUTPUT_PATH:-$BASE_DIR/reports/prism_command_brief_${RUN_STAMP}.md}"
LEGACY_JSON_OUTPUT_PATH="${LEGACY_JSON_OUTPUT_PATH:-$BASE_DIR/data/command_brief/prism_command_brief_${RUN_STAMP}.json}"
PRISM_WRITE_LEGACY_ARTIFACTS="${PRISM_WRITE_LEGACY_ARTIFACTS:-1}"
SEND_TO_FEISHU="${SEND_TO_FEISHU:-0}"
FEISHU_CHANNEL="${FEISHU_CHANNEL:-feishu}"
FEISHU_TARGET="${FEISHU_TARGET:-}"
ALLOW_STALE_WATCHLIST="${ALLOW_STALE_WATCHLIST:-0}"

send_to_feishu() {
  if [[ "$SEND_TO_FEISHU" != "1" && "$SEND_TO_FEISHU" != "true" ]]; then
    return 0
  fi
  if [[ -z "$FEISHU_TARGET" ]]; then
    echo "SEND_TO_FEISHU 已开启，但 FEISHU_TARGET 为空" >&2
    return 0
  fi
  if ! command -v openclaw >/dev/null 2>&1; then
    echo "缺少 openclaw，无法发送飞书消息" >&2
    return 0
  fi
  if [[ ! -f "$BRIEF_OUTPUT_PATH" ]]; then
    echo "总控简报正文不存在，无法发送: $BRIEF_OUTPUT_PATH" >&2
    return 0
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
  if ! "${send_cmd[@]}" >/dev/null; then
    echo "飞书发送失败，但总控简报已生成" >&2
  fi
  return 0
}

copy_if_different() {
  local source_path="$1"
  local target_path="$2"
  if [[ "$source_path" == "$target_path" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$target_path")"
  cp "$source_path" "$target_path"
}

write_legacy_artifacts() {
  if [[ "$PRISM_WRITE_LEGACY_ARTIFACTS" != "1" && "$PRISM_WRITE_LEGACY_ARTIFACTS" != "true" ]]; then
    return 0
  fi
  copy_if_different "$BRIEF_OUTPUT_PATH" "$LEGACY_BRIEF_OUTPUT_PATH"
  copy_if_different "$REPORT_OUTPUT_PATH" "$LEGACY_REPORT_OUTPUT_PATH"
  copy_if_different "$JSON_OUTPUT_PATH" "$LEGACY_JSON_OUTPUT_PATH"
}

register_artifact() {
  local path="$1"
  local artifact_type="$2"
  local generated_time="${RUN_STAMP#*_}"
  generated_time="${generated_time//-/:}"
  if [[ ! -f "$path" ]]; then
    return 0
  fi
  case "$path" in
    "$REPO_ROOT"/*) ;;
    *) return 0 ;;
  esac
  PYTHONPATH="$REPO_ROOT:$REPO_ROOT/packages:${PYTHONPATH:-}" \
    python3 -m prism_storage.cli \
      --repo-root "$REPO_ROOT" \
      register-file "$path" \
      --artifact-type "$artifact_type" \
      --source "command_brief" \
      --trade-date "$TRADE_DATE" \
      --generated-at "$TRADE_DATE $generated_time" \
      --metadata-json "{\"run_stamp\":\"$RUN_STAMP\"}" >/dev/null 2>&1 || true
}

register_command_brief_artifacts() {
  register_artifact "$BRIEF_OUTPUT_PATH" "command_brief"
  register_artifact "$REPORT_OUTPUT_PATH" "command_report"
  register_artifact "$JSON_OUTPUT_PATH" "command_brief_json"
}

mkdir -p "$(dirname "$BRIEF_OUTPUT_PATH")" "$(dirname "$REPORT_OUTPUT_PATH")" "$(dirname "$JSON_OUTPUT_PATH")"

generate_args=(
  "$SCRIPT_DIR/generate_command_brief.py"
  --date "$TRADE_DATE"
  --brief-output "$BRIEF_OUTPUT_PATH"
  --report-output "$REPORT_OUTPUT_PATH"
  --json-output "$JSON_OUTPUT_PATH"
)
if [[ "$ALLOW_STALE_WATCHLIST" == "1" || "$ALLOW_STALE_WATCHLIST" == "true" ]]; then
  generate_args+=(--allow-stale-watchlist)
fi

python3 "${generate_args[@]}"

write_legacy_artifacts
register_command_brief_artifacts
send_to_feishu

echo "brief -> $BRIEF_OUTPUT_PATH"
echo "report -> $REPORT_OUTPUT_PATH"
echo "json -> $JSON_OUTPUT_PATH"
if [[ "$PRISM_WRITE_LEGACY_ARTIFACTS" == "1" || "$PRISM_WRITE_LEGACY_ARTIFACTS" == "true" ]]; then
  echo "legacy_brief -> $LEGACY_BRIEF_OUTPUT_PATH"
  echo "legacy_report -> $LEGACY_REPORT_OUTPUT_PATH"
  echo "legacy_json -> $LEGACY_JSON_OUTPUT_PATH"
fi
