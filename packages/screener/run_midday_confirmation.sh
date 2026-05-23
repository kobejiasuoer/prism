#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BASE_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/packages:${PYTHONPATH:-}"
RUN_STAMP="$(date "+%F_%H-%M-%S")_$$"
TARGET_DATE="${TARGET_DATE:-$(date "+%F")}"

POOL="aggressive"
TOP="10"
MORNING_PATH=""
SKIP_SCAN="false"
SCAN_RESULT_PATH="$BASE_DIR/data/scan_result.json"
MIDDAY_OUTPUT_PATH="$BASE_DIR/data/midday_verification_result.json"
AI_HISTORY_DIR="$BASE_DIR/data/ai_history"
STALE_OUTPUT_DIR="$BASE_DIR/data/stale_outputs"
QUALITY_OUTPUT_PATH="$BASE_DIR/data/quality_gate_midday_${RUN_STAMP}.json"
QUALITY_REPORT_PATH="${QUALITY_REPORT_PATH:-$BASE_DIR/reports/quality_gate_midday_${RUN_STAMP}.md}"
QUALITY_GATE_SCRIPT="$REPO_ROOT/apps/scripts/feishu_quality_gate.py"
QUALITY_DASHBOARD_SCRIPT="$REPO_ROOT/apps/scripts/quality_gate_dashboard.py"
QUALITY_DASHBOARD_PATH="${QUALITY_DASHBOARD_PATH:-$REPO_ROOT/data/runtime/reports/command_brief/feishu-quality-dashboard.md}"
MESSAGE_OUTPUT_PATH="/tmp/stock_midday_confirmation.txt"
ATTACHMENT_OUTPUT_PATH="$BASE_DIR/reports/stock_midday_confirmation_${RUN_STAMP}.txt"
REPORT_OUTPUT_PATH="$BASE_DIR/reports/stock_midday_confirmation_${RUN_STAMP}.md"
SENDABLE_OUTPUT_PATH="$BASE_DIR/reports/stock_midday_confirmation_${RUN_STAMP}.docx"
SEND_TO_FEISHU="${SEND_TO_FEISHU:-0}"
FEISHU_CHANNEL="${FEISHU_CHANNEL:-feishu}"
FEISHU_TARGET="${FEISHU_TARGET:-}"
FEISHU_APPEND_LINE="${FEISHU_APPEND_LINE:-}"

if [[ -f "$SCRIPT_DIR/prism_artifact_helpers.sh" ]]; then
  source "$SCRIPT_DIR/prism_artifact_helpers.sh"
  prism_init_artifact_helpers "$REPO_ROOT" "$RUN_STAMP" "$TARGET_DATE"
fi
if ! declare -F prism_mirror_artifact >/dev/null; then
  prism_mirror_artifact() { return 0; }
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --morning)
      MORNING_PATH="$2"
      shift 2
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
    --output)
      MIDDAY_OUTPUT_PATH="$2"
      shift 2
      ;;
    --ai-history-dir)
      AI_HISTORY_DIR="$2"
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
    --skip-scan)
      SKIP_SCAN="true"
      shift
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
    prism_mirror_artifact "$backup_path" "screener/stale_outputs/$(basename "$backup_path")" "stale_output" "screener"
  fi
  local sidecar_path=""
  if [[ "$target_path" == *.* ]]; then
    sidecar_path="${target_path%.*}.manifest.json"
  fi
  if [[ -n "$sidecar_path" && -f "$sidecar_path" ]]; then
    mkdir -p "$STALE_OUTPUT_DIR"
    local sidecar_backup_path="$STALE_OUTPUT_DIR/${label}_${RUN_STAMP}.manifest.json"
    mv "$sidecar_path" "$sidecar_backup_path"
    echo "  旧 manifest 已隔离: $sidecar_path -> $sidecar_backup_path"
    prism_mirror_artifact "$sidecar_backup_path" "screener/stale_outputs/$(basename "$sidecar_backup_path")" "stale_manifest" "screener"
  fi
}

mirror_midday_confirmation_artifacts() {
  prism_mirror_artifact "$MIDDAY_OUTPUT_PATH" "screener/midday_confirmation/midday_verification_${RUN_STAMP}.json" "midday_confirmation_result" "screener"
  prism_mirror_artifact "$ATTACHMENT_OUTPUT_PATH" "screener/reports/$(basename "$ATTACHMENT_OUTPUT_PATH")" "midday_confirmation_brief" "screener"
  prism_mirror_artifact "$REPORT_OUTPUT_PATH" "screener/reports/$(basename "$REPORT_OUTPUT_PATH")" "midday_confirmation_report" "screener"
  prism_mirror_artifact "$SENDABLE_OUTPUT_PATH" "screener/reports/$(basename "$SENDABLE_OUTPUT_PATH")" "midday_confirmation_sendable" "screener"
  prism_mirror_artifact "$QUALITY_OUTPUT_PATH" "screener/quality_gates/$(basename "$QUALITY_OUTPUT_PATH")" "quality_gate" "screener"
  prism_mirror_artifact "$QUALITY_REPORT_PATH" "screener/quality_gates/$(basename "$QUALITY_REPORT_PATH")" "quality_gate_report" "screener"
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

run_quality_gate() {
  python3 "$QUALITY_GATE_SCRIPT" \
    --mode screener \
    --generator "$SCRIPT_DIR/generate_feishu_message.py" \
    --ai-input "$MORNING_PATH" \
    --midday-input "$MIDDAY_OUTPUT_PATH" \
    --message "$MESSAGE_OUTPUT_PATH" \
    --report "$REPORT_OUTPUT_PATH" \
    --output "$QUALITY_OUTPUT_PATH" \
    --report-output "$QUALITY_REPORT_PATH"
}

refresh_quality_dashboard() {
  python3 "$QUALITY_DASHBOARD_SCRIPT" \
    --output "$QUALITY_DASHBOARD_PATH" >/dev/null
}

write_status_output() {
  local status="$1"
  local reason="${2:-}"
  local runner_status="${3:-completed}"
  local include_scan_metadata="${4:-false}"
  STATUS="$status" \
  REASON="$reason" \
  RUNNER_STATUS="$runner_status" \
  INCLUDE_SCAN_METADATA="$include_scan_metadata" \
  OUTPUT_PATH="$MIDDAY_OUTPUT_PATH" \
  MORNING_PATH="$MORNING_PATH" \
  SCAN_RESULT_PATH="$SCAN_RESULT_PATH" \
  TARGET_DATE="$TARGET_DATE" \
  python3 - <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path

from prism_data import build_pipeline_manifest, write_sidecar_manifest


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


morning_path = os.environ.get("MORNING_PATH", "")
scan_path = os.environ.get("SCAN_RESULT_PATH", "")
morning = load_json(morning_path)
scan = load_json(scan_path) if os.environ.get("INCLUDE_SCAN_METADATA") == "true" else {}
reason = os.environ.get("REASON", "").strip()

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
output = {
    "timestamp": timestamp,
    "validation_status": os.environ.get("STATUS", "unknown"),
    "validation_errors": [reason] if reason else [],
    "runner_status": os.environ.get("RUNNER_STATUS", "completed"),
    "baseline_search_date": os.environ.get("TARGET_DATE", ""),
    "selected_morning_file": morning_path,
    "source_morning_timestamp": morning.get("timestamp", ""),
    "source_scan_timestamp": morning.get("source_scan_timestamp", ""),
    "verified_against_scan_timestamp": scan.get("timestamp", ""),
    "target_codes": [],
    "confirmed": [],
    "downgraded": [],
    "items": [],
}

output_path = Path(os.environ["OUTPUT_PATH"]).expanduser()
output_path.parent.mkdir(parents=True, exist_ok=True)
ingress_manifest = build_pipeline_manifest(
    dataset="screening.confirmation",
    trade_date=os.environ.get("TARGET_DATE", "") or timestamp[:10],
    payload=output,
    upstream_manifests=[],
    ttl_seconds=900,
    required_dataset_groups=[{"screening.batch"}, {"screening.scan_result"}],
    fetched_at=timestamp,
    quality_flags=list(output.get("validation_errors") or []) + [f"status:{output.get('validation_status')}"],
)
output["data_ingress"] = {
    "dataset": ingress_manifest.get("dataset"),
    "manifest_path": "",
    "freshness_status": ingress_manifest.get("freshness_status"),
    "live_small_allowed": bool(ingress_manifest.get("live_small_allowed")),
}
output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
manifest_path = write_sidecar_manifest(output_path, ingress_manifest)
output["data_ingress"]["manifest_path"] = str(manifest_path)
output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

auto_select_morning_baseline() {
  TARGET_DATE="$TARGET_DATE" AI_HISTORY_DIR="$AI_HISTORY_DIR" python3 - <<'PY'
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


target_date = os.environ["TARGET_DATE"]
ai_history_dir = Path(os.environ["AI_HISTORY_DIR"]).expanduser()

if not ai_history_dir.exists():
    sys.exit(1)

candidates = []
for path in sorted(ai_history_dir.glob("ai_screening_*.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    timestamp = parse_ts(data.get("timestamp"))
    source_scan_timestamp = parse_ts(data.get("source_scan_timestamp"))
    reference_ts = source_scan_timestamp or timestamp
    if not reference_ts:
        continue
    if reference_ts.strftime("%Y-%m-%d") != target_date:
        continue
    candidates.append({
        "path": str(path),
        "timestamp": timestamp,
        "source_scan_timestamp": source_scan_timestamp,
        "reference_ts": reference_ts,
        "is_morning_window": reference_ts.hour < 12,
        "is_ten_oclock_batch": reference_ts.hour == 10,
    })

if not candidates:
    sys.exit(1)

morning_window = [item for item in candidates if item["is_morning_window"]]
ten_oclock = [item for item in morning_window if item["is_ten_oclock_batch"]]
if ten_oclock:
    chosen = max(
        ten_oclock,
        key=lambda item: (
            item["reference_ts"],
            item["timestamp"] or item["reference_ts"],
            item["path"],
        ),
    )
elif morning_window:
    chosen = max(
        morning_window,
        key=lambda item: (
            item["reference_ts"],
            item["timestamp"] or item["reference_ts"],
            item["path"],
        ),
    )
else:
    chosen = max(
        candidates,
        key=lambda item: (
            item["reference_ts"],
            item["timestamp"] or item["reference_ts"],
            item["path"],
        ),
    )

print(chosen["path"])
PY
}

generate_midday_reports() {
  local validation_status="$1"

  if [[ "$validation_status" == "ok" ]]; then
    python3 "$SCRIPT_DIR/generate_feishu_message.py" \
      --input "$MORNING_PATH" \
      --midday-input "$MIDDAY_OUTPUT_PATH" \
      --format brief \
      --output "$MESSAGE_OUTPUT_PATH"

    python3 "$SCRIPT_DIR/generate_feishu_message.py" \
      --input "$MORNING_PATH" \
      --midday-input "$MIDDAY_OUTPUT_PATH" \
      --format full \
      --output "$REPORT_OUTPUT_PATH"
  else
    VALIDATION_STATUS="$validation_status" \
    MIDDAY_OUTPUT_PATH="$MIDDAY_OUTPUT_PATH" \
    MORNING_PATH="$MORNING_PATH" \
    MESSAGE_OUTPUT_PATH="$MESSAGE_OUTPUT_PATH" \
    REPORT_OUTPUT_PATH="$REPORT_OUTPUT_PATH" \
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
midday_path = os.environ.get("MIDDAY_OUTPUT_PATH", "")
morning_path = os.environ.get("MORNING_PATH", "")
message_output = Path(os.environ["MESSAGE_OUTPUT_PATH"]).expanduser()
report_output = Path(os.environ["REPORT_OUTPUT_PATH"]).expanduser()

midday = load_json(midday_path)
morning = load_json(morning_path)

timestamp = (
    midday.get("verified_against_scan_timestamp")
    or midday.get("timestamp")
    or morning.get("source_scan_timestamp")
    or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
reason = "；".join(midday.get("validation_errors") or []) or "本轮午盘确认未形成有效结果"

status_map = {
    "missing_baseline": ("午盘确认未执行", "缺少有效晨间基线"),
    "invalid": ("午盘确认无效", "晨间基线与当前午盘扫描不匹配"),
    "scan_failed": ("午盘扫描失败", "午盘实时扫描未成功"),
    "verify_failed": ("午盘确认失败", "承接确认脚本执行失败"),
    "quality_blocked": ("午盘确认已拦截", "本轮报告未通过发送前质检"),
    "failed": ("午盘确认失败", "本轮执行失败"),
    "unknown": ("午盘确认状态未知", "未读取到明确状态"),
}
title, summary = status_map.get(status, ("午盘确认未完成", "本轮午盘结果不可用"))

lines = [
    f"{title} | {timestamp}",
    summary + "。",
    f"原因：{reason}",
]

source_morning_ts = midday.get("source_morning_timestamp") or morning.get("timestamp")
verified_scan_ts = midday.get("verified_against_scan_timestamp")
if source_morning_ts:
    lines.append(f"晨间基线：{source_morning_ts}")
if verified_scan_ts:
    lines.append(f"午盘扫描：{verified_scan_ts}")
if morning_path:
    lines.append("建议：先检查晨间 AI 基线是否生成，再重跑午盘确认。")

text_report = "\n".join(lines).strip() + "\n"
md_report = (
    f"# {title}\n\n"
    f"时间：{timestamp}\n\n"
    f"- 摘要：{summary}\n"
    f"- 原因：{reason}\n"
    f"- 晨间基线：{source_morning_ts or '-'}\n"
    f"- 午盘扫描：{verified_scan_ts or '-'}\n"
    f"- 晨间文件：{morning_path or '-'}\n"
    f"- 午盘结果文件：{midday_path or '-'}\n"
)

message_output.parent.mkdir(parents=True, exist_ok=True)
report_output.parent.mkdir(parents=True, exist_ok=True)
message_output.write_text(text_report, encoding="utf-8")
report_output.write_text(md_report, encoding="utf-8")
PY
  fi

  if [[ "$ATTACHMENT_OUTPUT_PATH" != "$MESSAGE_OUTPUT_PATH" ]]; then
    cp "$MESSAGE_OUTPUT_PATH" "$ATTACHMENT_OUTPUT_PATH"
  fi

  if command -v textutil >/dev/null 2>&1; then
    textutil -convert docx -inputencoding UTF-8 "$REPORT_OUTPUT_PATH" -output "$SENDABLE_OUTPUT_PATH" >/dev/null 2>&1 || true
  fi
}

mkdir -p \
  "$(dirname "$SCAN_RESULT_PATH")" \
  "$(dirname "$MIDDAY_OUTPUT_PATH")" \
  "$(dirname "$QUALITY_OUTPUT_PATH")" \
  "$(dirname "$QUALITY_REPORT_PATH")" \
  "$(dirname "$QUALITY_DASHBOARD_PATH")" \
  "$(dirname "$MESSAGE_OUTPUT_PATH")" \
  "$(dirname "$ATTACHMENT_OUTPUT_PATH")" \
  "$(dirname "$REPORT_OUTPUT_PATH")" \
  "$(dirname "$SENDABLE_OUTPUT_PATH")"

echo "=== 进攻型选股午盘确认工作流 ==="

echo "[1] 清理旧午盘确认产物"
quarantine_stale_output "$MIDDAY_OUTPUT_PATH" "midday_verification_previous"

echo "[2] 选择晨间基线"
if [[ -z "$MORNING_PATH" ]]; then
  if MORNING_PATH="$(auto_select_morning_baseline)"; then
    echo "  晨间基线: $MORNING_PATH"
  else
    write_status_output "missing_baseline" "未找到当天有效的晨间 AI shortlist 基线" "skipped" "false"
    generate_midday_reports "missing_baseline"
    mirror_midday_confirmation_artifacts
    echo "  无有效晨间基线，已写入状态文件: $MIDDAY_OUTPUT_PATH"
    echo "完成："
    echo "  midday_result -> $MIDDAY_OUTPUT_PATH"
    echo "  feishu_message -> $MESSAGE_OUTPUT_PATH"
    echo "  markdown_report -> $REPORT_OUTPUT_PATH"
    echo "  validation_status -> missing_baseline"
    exit 1
  fi
else
  MORNING_PATH="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser())' "$MORNING_PATH")"
  echo "  使用显式晨间基线: $MORNING_PATH"
fi

if [[ ! -f "$MORNING_PATH" ]]; then
  write_status_output "missing_baseline" "指定的晨间基线文件不存在" "failed" "false"
  generate_midday_reports "missing_baseline"
  mirror_midday_confirmation_artifacts
  echo "ERROR: 指定的晨间基线文件不存在: $MORNING_PATH" >&2
  exit 1
fi

if [[ "$SKIP_SCAN" == "true" ]]; then
  echo "[3] 跳过实时扫描，使用现有结果: $SCAN_RESULT_PATH"
else
  echo "[3] 执行实时扫描"
  quarantine_stale_output "$SCAN_RESULT_PATH" "scan_result_previous_midday"
  SCAN_ERR_FILE="$(mktemp)"
  set +e
  python3 "$SCRIPT_DIR/scan.py" \
    --strategy all \
    --top "$TOP" \
    --pool "$POOL" \
    --output "$SCAN_RESULT_PATH" \
    2>"$SCAN_ERR_FILE"
  scan_exit=$?
  set -e
  if [[ $scan_exit -ne 0 ]]; then
    cat "$SCAN_ERR_FILE" >&2 || true
    rm -f "$SCAN_ERR_FILE"
    write_status_output "scan_failed" "scan.py 执行失败，请查看 stderr" "failed" "false"
    generate_midday_reports "scan_failed"
    mirror_midday_confirmation_artifacts
    exit "$scan_exit"
  fi
  rm -f "$SCAN_ERR_FILE"
fi

if [[ ! -f "$SCAN_RESULT_PATH" ]]; then
  write_status_output "scan_failed" "未生成有效的 scan_result.json" "failed" "false"
  generate_midday_reports "scan_failed"
  mirror_midday_confirmation_artifacts
  echo "ERROR: scan 结果文件不存在: $SCAN_RESULT_PATH" >&2
  exit 1
fi

echo "[4] 执行午盘确认"
VERIFY_ERR_FILE="$(mktemp)"
set +e
python3 "$SCRIPT_DIR/midday_verify.py" \
  --morning "$MORNING_PATH" \
  --scan "$SCAN_RESULT_PATH" \
  --output "$MIDDAY_OUTPUT_PATH" \
  2>"$VERIFY_ERR_FILE"
verify_exit=$?
set -e

if [[ $verify_exit -ne 0 ]]; then
  cat "$VERIFY_ERR_FILE" >&2 || true
  rm -f "$VERIFY_ERR_FILE"
  if [[ -f "$MIDDAY_OUTPUT_PATH" ]]; then
    validation_status="$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text(encoding="utf-8")).get("validation_status",""))' "$MIDDAY_OUTPUT_PATH")"
    if [[ "$validation_status" == "invalid" ]]; then
      generate_midday_reports "invalid"
      mirror_midday_confirmation_artifacts
      echo "完成："
      echo "  morning_baseline -> $MORNING_PATH"
      echo "  scan_result      -> $SCAN_RESULT_PATH"
      echo "  midday_result    -> $MIDDAY_OUTPUT_PATH"
      echo "  feishu_message   -> $MESSAGE_OUTPUT_PATH"
      echo "  markdown_report  -> $REPORT_OUTPUT_PATH"
      echo "  validation_status -> invalid"
      exit 1
    fi
  fi
  write_status_output "verify_failed" "midday_verify.py 执行失败，请查看 stderr" "failed" "true"
  generate_midday_reports "verify_failed"
  mirror_midday_confirmation_artifacts
  exit "$verify_exit"
fi
rm -f "$VERIFY_ERR_FILE"

validation_status="$(python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text(encoding="utf-8")).get("validation_status",""))' "$MIDDAY_OUTPUT_PATH")"
generate_midday_reports "${validation_status:-unknown}"

if [[ "${validation_status:-unknown}" == "ok" ]]; then
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
    quarantine_stale_output "$MIDDAY_OUTPUT_PATH" "midday_verification_quality_blocked"
    write_status_output "quality_blocked" "$quality_reason" "completed" "true"
    generate_midday_reports "quality_blocked"
    echo "ERROR: 午盘确认发送前质检未通过: $quality_reason" >&2
    if [[ "$SEND_TO_FEISHU" == "1" || "$SEND_TO_FEISHU" == "true" ]]; then
      if ! send_to_feishu; then
        exit 2
      fi
    fi
    refresh_quality_dashboard
    mirror_midday_confirmation_artifacts
    exit 1
  fi
  rm -f "$QUALITY_ERR_FILE"
fi
refresh_quality_dashboard
mirror_midday_confirmation_artifacts

echo "完成："
echo "  morning_baseline -> $MORNING_PATH"
echo "  scan_result      -> $SCAN_RESULT_PATH"
echo "  midday_result    -> $MIDDAY_OUTPUT_PATH"
echo "  quality_json     -> $QUALITY_OUTPUT_PATH"
echo "  quality_report   -> $QUALITY_REPORT_PATH"
echo "  feishu_message   -> $MESSAGE_OUTPUT_PATH"
echo "  feishu_attachment -> $ATTACHMENT_OUTPUT_PATH"
echo "  markdown_report  -> $REPORT_OUTPUT_PATH"
echo "  sendable_doc     -> $SENDABLE_OUTPUT_PATH"
echo "  validation_status -> ${validation_status:-unknown}"

send_to_feishu

if [[ "${validation_status:-unknown}" != "ok" ]]; then
  exit 1
fi
