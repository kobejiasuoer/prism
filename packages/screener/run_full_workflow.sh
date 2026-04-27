#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BASE_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/packages:${PYTHONPATH:-}"
RUN_STAMP="$(date "+%F_%H-%M")"

POOL="aggressive"
TOP="10"
RUN_SCAN="true"
HANDOFF_ANALYZER="false"
HANDOFF_TOP="3"
HANDOFF_MIN_CONSISTENCY="6"
SCAN_RESULT_PATH="$BASE_DIR/data/scan_result.json"
AI_OUTPUT_PATH="$BASE_DIR/data/ai_screening_result.json"
MESSAGE_OUTPUT_PATH="/tmp/stock_recommendation.txt"
ATTACHMENT_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_${RUN_STAMP}.txt"
REPORT_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_${RUN_STAMP}.md"
SENDABLE_OUTPUT_PATH="$BASE_DIR/reports/stock_recommendation_${RUN_STAMP}.docx"
HANDOFF_OUTPUT_PATH="$BASE_DIR/../stock-analyzer/reports/analysis-handoff_${RUN_STAMP}.md"
LIFECYCLE_OUTPUT_DIR="$BASE_DIR/data"
LIFECYCLE_JSON_PATH="$LIFECYCLE_OUTPUT_DIR/lifecycle_${RUN_STAMP}.json"
LIFECYCLE_MD_PATH="$LIFECYCLE_OUTPUT_DIR/lifecycle_${RUN_STAMP}.md"
LIFECYCLE_REPORT_PATH="$BASE_DIR/reports/lifecycle_${RUN_STAMP}.md"
AI_HISTORY_DIR="$BASE_DIR/data/ai_history"
RUN_LIFECYCLE="false"
STALE_OUTPUT_DIR="$BASE_DIR/data/stale_outputs"
QUALITY_OUTPUT_PATH="$BASE_DIR/data/quality_gate_${RUN_STAMP}.json"
QUALITY_REPORT_PATH="${QUALITY_REPORT_PATH:-$BASE_DIR/reports/quality_gate_${RUN_STAMP}.md}"
QUALITY_GATE_SCRIPT="$REPO_ROOT/apps/scripts/feishu_quality_gate.py"
QUALITY_DASHBOARD_SCRIPT="$REPO_ROOT/apps/scripts/quality_gate_dashboard.py"
QUALITY_DASHBOARD_PATH="${QUALITY_DASHBOARD_PATH:-$REPO_ROOT/data/history/reports/command_brief/feishu-quality-dashboard.md}"
SEND_TO_FEISHU="${SEND_TO_FEISHU:-0}"
FEISHU_CHANNEL="${FEISHU_CHANNEL:-feishu}"
FEISHU_TARGET="${FEISHU_TARGET:-}"
FEISHU_APPEND_LINE="${FEISHU_APPEND_LINE:-}"

if [[ -f "$SCRIPT_DIR/prism_artifact_helpers.sh" ]]; then
  source "$SCRIPT_DIR/prism_artifact_helpers.sh"
  prism_init_artifact_helpers "$REPO_ROOT" "$RUN_STAMP" "$(date "+%F")"
fi
if ! declare -F prism_mirror_artifact >/dev/null; then
  prism_mirror_artifact() { return 0; }
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-scan)
      RUN_SCAN="false"
      shift
      ;;
    --pool)
      POOL="$2"
      shift 2
      ;;
    --top)
      TOP="$2"
      shift 2
      ;;
    --scan-output)
      SCAN_RESULT_PATH="$2"
      shift 2
      ;;
    --handoff-analyzer)
      HANDOFF_ANALYZER="true"
      shift
      ;;
    --handoff-top)
      HANDOFF_TOP="$2"
      shift 2
      ;;
    --handoff-min-consistency)
      HANDOFF_MIN_CONSISTENCY="$2"
      shift 2
      ;;
    --handoff-output)
      HANDOFF_OUTPUT_PATH="$2"
      shift 2
      ;;
    --ai-output)
      AI_OUTPUT_PATH="$2"
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
    --lifecycle)
      RUN_LIFECYCLE="true"
      shift
      ;;
    --lifecycle-output-dir)
      LIFECYCLE_OUTPUT_DIR="$2"
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
    local backup_path="$STALE_OUTPUT_DIR/${label}_${RUN_STAMP}.$(basename "$target_path" | awk -F. '{print $NF}')"
    mv "$target_path" "$backup_path"
    echo "  旧产物已隔离: $target_path -> $backup_path"
    prism_mirror_artifact "$backup_path" "screener/stale_outputs/$(basename "$backup_path")" "stale_output" "screener"
  fi
}

mirror_full_workflow_artifacts() {
  prism_mirror_artifact "$ATTACHMENT_OUTPUT_PATH" "screener/reports/$(basename "$ATTACHMENT_OUTPUT_PATH")" "screener_brief" "screener"
  prism_mirror_artifact "$REPORT_OUTPUT_PATH" "screener/reports/$(basename "$REPORT_OUTPUT_PATH")" "screener_report" "screener"
  prism_mirror_artifact "$SENDABLE_OUTPUT_PATH" "screener/reports/$(basename "$SENDABLE_OUTPUT_PATH")" "screener_sendable" "screener"
  prism_mirror_artifact "$QUALITY_OUTPUT_PATH" "screener/quality_gates/$(basename "$QUALITY_OUTPUT_PATH")" "quality_gate" "screener"
  prism_mirror_artifact "$QUALITY_REPORT_PATH" "screener/quality_gates/$(basename "$QUALITY_REPORT_PATH")" "quality_gate_report" "screener"
  if [[ "$HANDOFF_ANALYZER" == "true" ]]; then
    prism_mirror_artifact "$HANDOFF_OUTPUT_PATH" "analyzer/handoffs/$(basename "$HANDOFF_OUTPUT_PATH")" "analyzer_handoff" "screener"
  fi
  if [[ "$RUN_LIFECYCLE" == "true" ]]; then
    prism_mirror_artifact "$LIFECYCLE_JSON_PATH" "screener/lifecycle/$(basename "$LIFECYCLE_JSON_PATH")" "lifecycle_json" "screener"
    prism_mirror_artifact "$LIFECYCLE_MD_PATH" "screener/lifecycle/$(basename "$LIFECYCLE_MD_PATH")" "lifecycle_markdown" "screener"
    prism_mirror_artifact "$LIFECYCLE_REPORT_PATH" "screener/reports/$(basename "$LIFECYCLE_REPORT_PATH")" "lifecycle_report" "screener"
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

read_quality_reason() {
  if [[ ! -f "$QUALITY_OUTPUT_PATH" ]]; then
    echo ""
    return
  fi
  python3 - <<'PY' "$QUALITY_OUTPUT_PATH"
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)

errors = data.get("errors") or []
print("；".join(str(item) for item in errors[:6]))
PY
}

write_quality_failure_outputs() {
  local reason="$1"
  local timestamp="$2"
  local title="进攻型选股报告已拦截"
  local summary="本轮报告未通过发送前质检，已自动拦截，避免错报。"

  quarantine_stale_output "$MESSAGE_OUTPUT_PATH" "quality_blocked_message"
  if [[ "$ATTACHMENT_OUTPUT_PATH" != "$MESSAGE_OUTPUT_PATH" ]]; then
    quarantine_stale_output "$ATTACHMENT_OUTPUT_PATH" "quality_blocked_attachment"
  fi
  quarantine_stale_output "$REPORT_OUTPUT_PATH" "quality_blocked_report"
  quarantine_stale_output "$SENDABLE_OUTPUT_PATH" "quality_blocked_sendable"

  TITLE="$title" \
  SUMMARY="$summary" \
  REASON="$reason" \
  TIMESTAMP="$timestamp" \
  MESSAGE_OUTPUT_PATH="$MESSAGE_OUTPUT_PATH" \
  ATTACHMENT_OUTPUT_PATH="$ATTACHMENT_OUTPUT_PATH" \
  REPORT_OUTPUT_PATH="$REPORT_OUTPUT_PATH" \
  SENDABLE_OUTPUT_PATH="$SENDABLE_OUTPUT_PATH" \
  python3 - <<'PY'
import os
import subprocess
from pathlib import Path

title = os.environ["TITLE"]
summary = os.environ["SUMMARY"]
reason = os.environ["REASON"]
timestamp = os.environ["TIMESTAMP"]
message_output = Path(os.environ["MESSAGE_OUTPUT_PATH"]).expanduser()
attachment_output = Path(os.environ["ATTACHMENT_OUTPUT_PATH"]).expanduser()
report_output = Path(os.environ["REPORT_OUTPUT_PATH"]).expanduser()
sendable_output = Path(os.environ["SENDABLE_OUTPUT_PATH"]).expanduser()

text_report = (
    f"{title} | {timestamp}\n"
    f"{summary}\n"
    f"原因：{reason}\n"
    "建议：检查本轮 source json、正文和附件产物链路后再重跑。\n"
)
md_report = (
    f"# {title}\n\n"
    f"时间：{timestamp}\n\n"
    f"- 摘要：{summary}\n"
    f"- 原因：{reason}\n"
    "- 建议：检查本轮 source json、正文和附件产物链路后再重跑。\n"
)

message_output.parent.mkdir(parents=True, exist_ok=True)
report_output.parent.mkdir(parents=True, exist_ok=True)
attachment_output.parent.mkdir(parents=True, exist_ok=True)
message_output.write_text(text_report, encoding="utf-8")
attachment_output.write_text(text_report, encoding="utf-8")
report_output.write_text(md_report, encoding="utf-8")

if Path("/usr/bin/textutil").exists():
    sendable_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["/usr/bin/textutil", "-convert", "docx", "-inputencoding", "UTF-8", str(report_output), "-output", str(sendable_output)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
PY
}

run_quality_gate() {
  local gate_cmd=(
    python3 "$QUALITY_GATE_SCRIPT"
    --mode screener
    --generator "$SCRIPT_DIR/generate_feishu_message.py"
    --scan-input "$SCAN_RESULT_PATH"
    --ai-input "$AI_OUTPUT_PATH"
    --message "$MESSAGE_OUTPUT_PATH"
    --report "$REPORT_OUTPUT_PATH"
    --output "$QUALITY_OUTPUT_PATH"
    --report-output "$QUALITY_REPORT_PATH"
  )
  if [[ "$RUN_LIFECYCLE" == "true" ]]; then
    gate_cmd+=(--lifecycle-input "$LIFECYCLE_JSON_PATH")
  fi
  "${gate_cmd[@]}"
}

refresh_quality_dashboard() {
  python3 "$QUALITY_DASHBOARD_SCRIPT" \
    --output "$QUALITY_DASHBOARD_PATH" >/dev/null
}

mkdir -p \
  "$(dirname "$SCAN_RESULT_PATH")" \
  "$(dirname "$AI_OUTPUT_PATH")" \
  "$(dirname "$QUALITY_OUTPUT_PATH")" \
  "$(dirname "$QUALITY_REPORT_PATH")" \
  "$(dirname "$QUALITY_DASHBOARD_PATH")" \
  "$(dirname "$MESSAGE_OUTPUT_PATH")" \
  "$(dirname "$ATTACHMENT_OUTPUT_PATH")" \
  "$(dirname "$REPORT_OUTPUT_PATH")" \
  "$(dirname "$SENDABLE_OUTPUT_PATH")" \
  "$(dirname "$HANDOFF_OUTPUT_PATH")"

echo "=== 进攻型选股 v2 工作流 ==="
echo "[0] 清理可能复用的旧产物"
quarantine_stale_output "$AI_OUTPUT_PATH" "ai_screening_previous_preflight"
quarantine_stale_output "$MESSAGE_OUTPUT_PATH" "message_previous"
if [[ "$ATTACHMENT_OUTPUT_PATH" != "$MESSAGE_OUTPUT_PATH" ]]; then
  quarantine_stale_output "$ATTACHMENT_OUTPUT_PATH" "attachment_previous"
fi
quarantine_stale_output "$REPORT_OUTPUT_PATH" "report_previous"
quarantine_stale_output "$SENDABLE_OUTPUT_PATH" "sendable_previous"

if [[ "$RUN_SCAN" == "true" ]]; then
  echo "[1] 执行 scan.py"
  quarantine_stale_output "$SCAN_RESULT_PATH" "scan_result_previous"
  python3 "$SCRIPT_DIR/scan.py" \
    --strategy all \
    --top "$TOP" \
    --pool "$POOL" \
    --output "$SCAN_RESULT_PATH"
else
  echo "[1] 跳过实时扫描，使用现有结果: $SCAN_RESULT_PATH"
fi

echo "[2] 执行 ai_screening.py"
quarantine_stale_output "$AI_OUTPUT_PATH" "ai_screening_previous"
python3 "$SCRIPT_DIR/ai_screening.py" \
  --input "$SCAN_RESULT_PATH" \
  --output "$AI_OUTPUT_PATH"

if [[ "$RUN_LIFECYCLE" == "true" ]]; then
  echo "[3] 执行候选生命周期管理"
  python3 "$SCRIPT_DIR/candidate_lifecycle.py" \
    --ai-input "$AI_OUTPUT_PATH" \
    --midday-input "$BASE_DIR/data/midday_verification_result.json" \
    --history-dir "$BASE_DIR/data/history" \
    --ai-history-dir "$AI_HISTORY_DIR" \
    --output-dir "$LIFECYCLE_OUTPUT_DIR" \
    --output-json "$LIFECYCLE_JSON_PATH" \
    --output-md "$LIFECYCLE_MD_PATH" \
    --report-output "$LIFECYCLE_REPORT_PATH"
fi

echo "[4] 生成飞书消息与 Markdown 报告"
GEN_ARGS=(--input "$AI_OUTPUT_PATH")
if [[ "$RUN_LIFECYCLE" == "true" ]]; then
  GEN_ARGS+=(--lifecycle-input "$LIFECYCLE_JSON_PATH")
fi

python3 "$SCRIPT_DIR/generate_feishu_message.py" \
  "${GEN_ARGS[@]}" \
  --format brief \
  --output "$MESSAGE_OUTPUT_PATH"

python3 "$SCRIPT_DIR/generate_feishu_message.py" \
  "${GEN_ARGS[@]}" \
  --format full \
  --output "$REPORT_OUTPUT_PATH"

if [[ "$ATTACHMENT_OUTPUT_PATH" != "$MESSAGE_OUTPUT_PATH" ]]; then
  cp "$MESSAGE_OUTPUT_PATH" "$ATTACHMENT_OUTPUT_PATH"
fi

if ! command -v textutil >/dev/null 2>&1; then
  echo "缺少 textutil，无法生成可发送的 .docx 附件" >&2
  exit 1
fi

textutil -convert docx -inputencoding UTF-8 "$REPORT_OUTPUT_PATH" -output "$SENDABLE_OUTPUT_PATH"

if [[ "$HANDOFF_ANALYZER" == "true" ]]; then
  echo "[5] 执行 screener → analyzer handoff"
  set +e
  handoff_output="$(
    python3 "$SCRIPT_DIR/screener_to_analyzer.py" \
      --input "$AI_OUTPUT_PATH" \
      --top "$HANDOFF_TOP" \
      --min-consistency "$HANDOFF_MIN_CONSISTENCY" \
      --output "$HANDOFF_OUTPUT_PATH" 2>&1
  )"
  handoff_exit=$?
  set -e
  if [[ -n "$handoff_output" ]]; then
    printf '%s\n' "$handoff_output"
  fi
  if [[ $handoff_exit -ne 0 ]]; then
    echo "[warn] analyzer handoff 失败，已降级跳过，不阻断主流程" >&2
  fi
fi

echo "[6] 发送前质检"
QUALITY_ERR_FILE="$(mktemp)"
set +e
run_quality_gate >"$QUALITY_ERR_FILE" 2>&1
quality_exit=$?
set -e
if [[ $quality_exit -ne 0 ]]; then
  quality_reason="$(read_quality_reason)"
  if [[ -z "$quality_reason" ]]; then
    quality_reason="$(tr '\n' ' ' <"$QUALITY_ERR_FILE" | sed 's/[[:space:]]\+/ /g' | cut -c1-240)"
  fi
  rm -f "$QUALITY_ERR_FILE"
  failure_timestamp="$(python3 - <<'PY' "$AI_OUTPUT_PATH" "$SCAN_RESULT_PATH"
import json
import pathlib
import sys

def load(path_str):
    path = pathlib.Path(path_str)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

ai = load(sys.argv[1])
scan = load(sys.argv[2])
print(ai.get("source_scan_timestamp") or ai.get("timestamp") or scan.get("timestamp") or "")
PY
)"
  if [[ -z "$failure_timestamp" ]]; then
    failure_timestamp="$(date "+%F %T")"
  fi
  write_quality_failure_outputs "$quality_reason" "$failure_timestamp"
  echo "ERROR: 发送前质检未通过: $quality_reason" >&2
  if [[ "$SEND_TO_FEISHU" == "1" || "$SEND_TO_FEISHU" == "true" ]]; then
    if ! send_to_feishu; then
      exit 2
    fi
  fi
  refresh_quality_dashboard
  mirror_full_workflow_artifacts
  exit 1
fi
rm -f "$QUALITY_ERR_FILE"
refresh_quality_dashboard
mirror_full_workflow_artifacts

echo "完成："
echo "  scan_result     -> $SCAN_RESULT_PATH"
echo "  ai_screening    -> $AI_OUTPUT_PATH"
echo "  quality_json    -> $QUALITY_OUTPUT_PATH"
echo "  quality_report  -> $QUALITY_REPORT_PATH"
echo "  feishu_message  -> $MESSAGE_OUTPUT_PATH"
echo "  feishu_attachment -> $ATTACHMENT_OUTPUT_PATH"
echo "  markdown_report -> $REPORT_OUTPUT_PATH"
echo "  sendable_doc    -> $SENDABLE_OUTPUT_PATH"
if [[ "$HANDOFF_ANALYZER" == "true" ]]; then
  echo "  analyzer_handoff -> $HANDOFF_OUTPUT_PATH"
fi
if [[ "$RUN_LIFECYCLE" == "true" ]]; then
  echo "  lifecycle_json   -> $LIFECYCLE_JSON_PATH"
  echo "  lifecycle_md     -> $LIFECYCLE_MD_PATH"
  echo "  lifecycle_report -> $LIFECYCLE_REPORT_PATH"
fi

send_to_feishu
