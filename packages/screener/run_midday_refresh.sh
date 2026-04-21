#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_STAMP="$(date "+%F_%H-%M-%S")_$$"

POOL="aggressive"
TOP="10"
SKIP_SCAN="false"
SCAN_RESULT_PATH="$BASE_DIR/data/scan_result.json"
AI_OUTPUT_PATH="$BASE_DIR/data/ai_screening_result.json"
RESULT_OUTPUT_PATH="$BASE_DIR/data/midday_refresh_result.json"
STALE_OUTPUT_DIR="$BASE_DIR/data/stale_outputs"
MESSAGE_OUTPUT_PATH="/tmp/stock_midday_refresh.txt"
ATTACHMENT_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_midday_${RUN_STAMP}.txt"
REPORT_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_midday_${RUN_STAMP}.md"
SENDABLE_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_midday_${RUN_STAMP}.docx"
SEND_TO_FEISHU="${SEND_TO_FEISHU:-0}"
FEISHU_CHANNEL="${FEISHU_CHANNEL:-feishu}"
FEISHU_TARGET="${FEISHU_TARGET:-}"
FEISHU_APPEND_LINE="${FEISHU_APPEND_LINE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pool)
      POOL="$2"
      shift 2
      ;;
    --top)
      TOP="$2"
      shift 2
      ;;
    --skip-scan)
      SKIP_SCAN="true"
      shift
      ;;
    --scan-output)
      SCAN_RESULT_PATH="$2"
      shift 2
      ;;
    --ai-output)
      AI_OUTPUT_PATH="$2"
      shift 2
      ;;
    --output)
      RESULT_OUTPUT_PATH="$2"
      shift 2
      ;;
    --message-output)
      MESSAGE_OUTPUT_PATH="$2"
      shift 2
      ;;
    --attachment-output)
      ATTACHMENT_OUTPUT_PATH="$2"
      shift 2
      ;;
    --report-output)
      REPORT_OUTPUT_PATH="$2"
      shift 2
      ;;
    --sendable-output)
      SENDABLE_OUTPUT_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

quarantine_stale_output() {
  local target_path="$1"
  local label="$2"
  if [[ -f "$target_path" ]]; then
    mkdir -p "$STALE_OUTPUT_DIR"
    local basename ext backup_path
    basename="$(basename "$target_path")"
    if [[ "$basename" == *.* ]]; then
      ext="${basename##*.}"
      backup_path="$STALE_OUTPUT_DIR/${label}_${RUN_STAMP}.${ext}"
    else
      backup_path="$STALE_OUTPUT_DIR/${label}_${RUN_STAMP}"
    fi
    mv "$target_path" "$backup_path"
    echo "  旧产物已隔离: $target_path -> $backup_path"
  fi
}

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
  if [[ ! -f "$MESSAGE_OUTPUT_PATH" ]]; then
    echo "飞书正文文件不存在，无法发送: $MESSAGE_OUTPUT_PATH" >&2
    return 1
  fi

  local message_body
  message_body="$(cat "$MESSAGE_OUTPUT_PATH")"
  if [[ -n "$FEISHU_APPEND_LINE" ]]; then
    message_body="${message_body%$'\n'}"$'\n'"$FEISHU_APPEND_LINE"
  fi

  local send_cmd=(
    openclaw message send
    --channel "$FEISHU_CHANNEL"
    --target "$FEISHU_TARGET"
    --message "$message_body"
  )
  if [[ -f "$REPORT_OUTPUT_PATH" ]]; then
    send_cmd+=(--media "$REPORT_OUTPUT_PATH")
  fi

  "${send_cmd[@]}" >/dev/null
}

write_status_output() {
  local status="$1"
  local reason="${2:-}"
  local runner_status="${3:-completed}"
  STATUS="$status" \
  REASON="$reason" \
  RUNNER_STATUS="$runner_status" \
  OUTPUT_PATH="$RESULT_OUTPUT_PATH" \
  RUN_STAMP="$RUN_STAMP" \
  SCAN_RESULT_PATH="$SCAN_RESULT_PATH" \
  AI_OUTPUT_PATH="$AI_OUTPUT_PATH" \
  MESSAGE_OUTPUT_PATH="$MESSAGE_OUTPUT_PATH" \
  ATTACHMENT_OUTPUT_PATH="$ATTACHMENT_OUTPUT_PATH" \
  REPORT_OUTPUT_PATH="$REPORT_OUTPUT_PATH" \
  SENDABLE_OUTPUT_PATH="$SENDABLE_OUTPUT_PATH" \
  python3 - <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path


def load_json(path_str: str) -> dict:
    if not path_str:
        return {}
    path = Path(path_str).expanduser()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


scan_path = os.environ.get("SCAN_RESULT_PATH", "")
ai_path = os.environ.get("AI_OUTPUT_PATH", "")
message_path = Path(os.environ["MESSAGE_OUTPUT_PATH"]).expanduser()
attachment_path = Path(os.environ["ATTACHMENT_OUTPUT_PATH"]).expanduser()
report_path = Path(os.environ["REPORT_OUTPUT_PATH"]).expanduser()
sendable_path = Path(os.environ["SENDABLE_OUTPUT_PATH"]).expanduser()
scan = load_json(scan_path)
ai = load_json(ai_path)
reason = os.environ.get("REASON", "").strip()

output = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "run_stamp": os.environ.get("RUN_STAMP", ""),
    "validation_status": os.environ.get("STATUS", "unknown"),
    "validation_errors": [reason] if reason else [],
    "runner_status": os.environ.get("RUNNER_STATUS", "completed"),
    "scan_result_path": scan_path,
    "ai_output_path": ai_path,
    "scan_timestamp": scan.get("timestamp", ""),
    "ai_timestamp": ai.get("timestamp", ""),
    "source_scan_timestamp": ai.get("source_scan_timestamp", ""),
    "selected_message_path": str(message_path) if message_path.exists() else "",
    "selected_brief_path": str(attachment_path) if attachment_path.exists() else "",
    "selected_report_path": str(report_path) if report_path.exists() else "",
    "selected_sendable_path": str(sendable_path) if sendable_path.exists() else "",
}

output_path = Path(os.environ["OUTPUT_PATH"]).expanduser()
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

generate_status_reports() {
  local validation_status="$1"

  VALIDATION_STATUS="$validation_status" \
  RESULT_OUTPUT_PATH="$RESULT_OUTPUT_PATH" \
  MESSAGE_OUTPUT_PATH="$MESSAGE_OUTPUT_PATH" \
  ATTACHMENT_OUTPUT_PATH="$ATTACHMENT_OUTPUT_PATH" \
  REPORT_OUTPUT_PATH="$REPORT_OUTPUT_PATH" \
  SENDABLE_OUTPUT_PATH="$SENDABLE_OUTPUT_PATH" \
  python3 - <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path


def load_json(path_str: str) -> dict:
    if not path_str:
        return {}
    path = Path(path_str).expanduser()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


status = os.environ.get("VALIDATION_STATUS", "unknown")
result = load_json(os.environ.get("RESULT_OUTPUT_PATH", ""))
message_output = Path(os.environ["MESSAGE_OUTPUT_PATH"]).expanduser()
attachment_output = Path(os.environ["ATTACHMENT_OUTPUT_PATH"]).expanduser()
report_output = Path(os.environ["REPORT_OUTPUT_PATH"]).expanduser()
sendable_output = Path(os.environ["SENDABLE_OUTPUT_PATH"]).expanduser()

timestamp = (
    result.get("scan_timestamp")
    or result.get("source_scan_timestamp")
    or result.get("timestamp")
    or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
reason = "；".join(result.get("validation_errors") or []) or "本轮午盘刷新未形成有效报告"

status_map = {
    "workflow_failed": ("进攻型午盘刷新失败", "实时扫描或二筛流程未成功完成"),
    "invalid": ("进攻型午盘刷新未完成", "本轮报告未通过时间戳校验"),
    "terminated": ("进攻型午盘刷新中断", "流程在生成有效报告前被中断"),
    "missing_output": ("进攻型午盘刷新未完成", "未生成本轮有效报告"),
    "unknown": ("进攻型午盘刷新状态未知", "未读取到明确状态"),
}
title, summary = status_map.get(status, ("进攻型午盘刷新未完成", "本轮午盘结果不可用"))

lines = [
    f"{title} | {timestamp}",
    summary + "。",
    f"原因：{reason}",
]

scan_ts = result.get("scan_timestamp")
ai_ts = result.get("ai_timestamp")
source_scan_ts = result.get("source_scan_timestamp")
if scan_ts:
    lines.append(f"本轮 scan：{scan_ts}")
if ai_ts:
    lines.append(f"本轮二筛：{ai_ts}")
if source_scan_ts and source_scan_ts != scan_ts:
    lines.append(f"二筛引用 scan：{source_scan_ts}")
lines.append("建议：不要使用早盘报告顶替午盘结果，稍后重跑本轮午盘刷新。")

text_report = "\n".join(lines).strip() + "\n"
md_report = (
    f"# {title}\n\n"
    f"时间：{timestamp}\n\n"
    f"- 摘要：{summary}\n"
    f"- 原因：{reason}\n"
    f"- 本轮 scan：{scan_ts or '-'}\n"
    f"- 本轮二筛：{ai_ts or '-'}\n"
    f"- 二筛引用 scan：{source_scan_ts or '-'}\n"
    f"- 状态文件：{os.environ.get('RESULT_OUTPUT_PATH', '-')}\n"
)

message_output.parent.mkdir(parents=True, exist_ok=True)
attachment_output.parent.mkdir(parents=True, exist_ok=True)
report_output.parent.mkdir(parents=True, exist_ok=True)
message_output.write_text(text_report, encoding="utf-8")
attachment_output.write_text(text_report, encoding="utf-8")
report_output.write_text(md_report, encoding="utf-8")

sendable_output.parent.mkdir(parents=True, exist_ok=True)
if Path("/usr/bin/textutil").exists():
    import subprocess

    subprocess.run(
        ["/usr/bin/textutil", "-convert", "docx", "-inputencoding", "UTF-8", str(report_output), "-output", str(sendable_output)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
PY
}

normalize_reason() {
  local source_file="$1"
  if [[ ! -f "$source_file" ]]; then
    echo ""
    return
  fi
  tr '\n' ' ' <"$source_file" | sed 's/[[:space:]]\+/ /g' | cut -c1-220
}

handle_interrupt() {
  trap - TERM INT
  write_status_output "terminated" "午盘刷新命令被中断，未生成本轮有效报告" "terminated"
  generate_status_reports "terminated"
  if ! send_to_feishu; then
    exit 2
  fi
  exit 143
}

trap handle_interrupt TERM INT

mkdir -p \
  "$(dirname "$SCAN_RESULT_PATH")" \
  "$(dirname "$AI_OUTPUT_PATH")" \
  "$(dirname "$RESULT_OUTPUT_PATH")" \
  "$(dirname "$MESSAGE_OUTPUT_PATH")" \
  "$(dirname "$ATTACHMENT_OUTPUT_PATH")" \
  "$(dirname "$REPORT_OUTPUT_PATH")" \
  "$(dirname "$SENDABLE_OUTPUT_PATH")"

echo "=== 进攻型选股午盘刷新工作流 ==="
echo "[1] 清理旧午盘刷新状态"
quarantine_stale_output "$RESULT_OUTPUT_PATH" "midday_refresh_previous"

WORKFLOW_ERR_FILE="$(mktemp)"
WORKFLOW_ARGS=(
  bash "$SCRIPT_DIR/run_full_workflow.sh"
  --pool "$POOL"
  --top "$TOP"
  --scan-output "$SCAN_RESULT_PATH"
  --ai-output "$AI_OUTPUT_PATH"
  --message-output "$MESSAGE_OUTPUT_PATH"
  --attachment-output "$ATTACHMENT_OUTPUT_PATH"
  --report-output "$REPORT_OUTPUT_PATH"
  --sendable-output "$SENDABLE_OUTPUT_PATH"
)
if [[ "$SKIP_SCAN" == "true" ]]; then
  WORKFLOW_ARGS+=(--skip-scan)
fi

echo "[2] 执行午盘刷新主流程"
set +e
env \
  SEND_TO_FEISHU=0 \
  FEISHU_TARGET="" \
  FEISHU_APPEND_LINE="" \
  "${WORKFLOW_ARGS[@]}" 2>"$WORKFLOW_ERR_FILE"
workflow_exit=$?
set -e

if [[ $workflow_exit -ne 0 ]]; then
  workflow_reason="$(normalize_reason "$WORKFLOW_ERR_FILE")"
  rm -f "$WORKFLOW_ERR_FILE"
  if [[ -z "$workflow_reason" ]]; then
    workflow_reason="run_full_workflow.sh 非零退出"
  fi
  write_status_output "workflow_failed" "$workflow_reason" "failed"
  generate_status_reports "workflow_failed"
  if ! send_to_feishu; then
    exit 2
  fi
  exit "$workflow_exit"
fi
rm -f "$WORKFLOW_ERR_FILE"

scan_timestamp="$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text(encoding="utf-8")).get("timestamp","") if p.exists() else "")' "$SCAN_RESULT_PATH" 2>/dev/null || true)"
ai_timestamp="$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text(encoding="utf-8")).get("timestamp","") if p.exists() else "")' "$AI_OUTPUT_PATH" 2>/dev/null || true)"
source_scan_timestamp="$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text(encoding="utf-8")).get("source_scan_timestamp","") if p.exists() else "")' "$AI_OUTPUT_PATH" 2>/dev/null || true)"

validation_errors=()
if [[ ! -f "$SCAN_RESULT_PATH" ]]; then
  validation_errors+=("未生成本轮 scan_result.json")
fi
if [[ ! -f "$AI_OUTPUT_PATH" ]]; then
  validation_errors+=("未生成本轮 ai_screening_result.json")
fi
if [[ ! -f "$MESSAGE_OUTPUT_PATH" ]]; then
  validation_errors+=("未生成本轮手机摘要")
fi
if [[ ! -f "$ATTACHMENT_OUTPUT_PATH" ]]; then
  validation_errors+=("未生成本轮午盘 brief 附件")
fi
if [[ ! -f "$REPORT_OUTPUT_PATH" ]]; then
  validation_errors+=("未生成本轮午盘 Markdown 报告")
fi
if [[ -z "$scan_timestamp" ]]; then
  validation_errors+=("scan_result.json 缺少 timestamp")
fi
if [[ -z "$ai_timestamp" ]]; then
  validation_errors+=("ai_screening_result.json 缺少 timestamp")
fi
if [[ -z "$source_scan_timestamp" ]]; then
  validation_errors+=("ai_screening_result.json 缺少 source_scan_timestamp")
fi
if [[ -n "$scan_timestamp" && -n "$source_scan_timestamp" && "$source_scan_timestamp" != "$scan_timestamp" ]]; then
  validation_errors+=("二筛 source_scan_timestamp 与本轮 scan.timestamp 不一致：$source_scan_timestamp != $scan_timestamp")
fi

if (( ${#validation_errors[@]} > 0 )); then
  invalid_reason="$(printf '%s；' "${validation_errors[@]}")"
  invalid_reason="${invalid_reason%；}"
  write_status_output "invalid" "$invalid_reason" "completed"
  generate_status_reports "invalid"
  if ! send_to_feishu; then
    exit 2
  fi
  exit 1
fi

write_status_output "ok" "" "completed"
echo "完成："
echo "  scan_result      -> $SCAN_RESULT_PATH"
echo "  ai_screening     -> $AI_OUTPUT_PATH"
echo "  refresh_result   -> $RESULT_OUTPUT_PATH"
echo "  feishu_message   -> $MESSAGE_OUTPUT_PATH"
echo "  feishu_attachment -> $ATTACHMENT_OUTPUT_PATH"
echo "  markdown_report  -> $REPORT_OUTPUT_PATH"
echo "  sendable_doc     -> $SENDABLE_OUTPUT_PATH"
echo "  validation_status -> ok"

send_to_feishu
