#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MODE="baseline"

usage() {
  cat <<'EOF'
Usage: ./start_stock_evaluation.sh [baseline|professional|product] [extra evaluator args...]

Modes:
  baseline      Refresh the latest baseline report only. This is the default.
  professional  Require at least professional_usable and fail on hard gates.
  product       Require at least product_ready and fail on hard gates.

Environment overrides:
  PYTHON_BIN        Python executable to use.
  MANIFEST_PATH     Evaluation manifest path.
  OUTPUT_JSON_PATH  Scorecard JSON output path.
  OUTPUT_MD_PATH    Markdown report output path.

Examples:
  ./start_stock_evaluation.sh
  ./start_stock_evaluation.sh professional
  ./start_stock_evaluation.sh product
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    baseline|report)
      MODE="baseline"
      shift
      ;;
    professional|pro)
      MODE="professional"
      shift
      ;;
    product|prod)
      MODE="product"
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
  esac
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "[prism-eval] Missing python interpreter: $PYTHON_BIN" >&2
    exit 1
  fi
fi

MANIFEST_PATH="${MANIFEST_PATH:-data/evaluation/stock_analysis/manifest.json}"
OUTPUT_JSON_PATH="${OUTPUT_JSON_PATH:-data/evaluation/stock_analysis/latest_scorecard.json}"
OUTPUT_MD_PATH="${OUTPUT_MD_PATH:-data/history/reports/evaluation/prism_stock_analysis_evaluation_latest.md}"

MODE_ARGS=()
case "$MODE" in
  baseline)
    ;;
  professional)
    MODE_ARGS+=(--min-tier professional_usable --fail-on-hard-gates)
    ;;
  product)
    MODE_ARGS+=(--min-tier product_ready --fail-on-hard-gates)
    ;;
  *)
    echo "[prism-eval] Unsupported mode: $MODE" >&2
    usage >&2
    exit 1
    ;;
esac

cd "$ROOT_DIR"

echo "[prism-eval] mode -> $MODE"
echo "[prism-eval] manifest -> $MANIFEST_PATH"
echo "[prism-eval] json -> $OUTPUT_JSON_PATH"
echo "[prism-eval] markdown -> $OUTPUT_MD_PATH"

COMMAND=(
  "$PYTHON_BIN"
  apps/scripts/evaluate_stock_analysis.py
  --manifest "$MANIFEST_PATH"
  --output-json "$OUTPUT_JSON_PATH"
  --output-md "$OUTPUT_MD_PATH"
)
if [[ ${#MODE_ARGS[@]} -gt 0 ]]; then
  COMMAND+=("${MODE_ARGS[@]}")
fi
if [[ $# -gt 0 ]]; then
  COMMAND+=("$@")
fi

set +e
"${COMMAND[@]}"
STATUS=$?
set -e

echo "[prism-eval] exit -> $STATUS"
echo "[prism-eval] scorecard -> $OUTPUT_JSON_PATH"
echo "[prism-eval] report -> $OUTPUT_MD_PATH"

exit "$STATUS"
