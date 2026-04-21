#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec bash "$SCRIPT_DIR/run_full_workflow.sh" \
  --pool aggressive \
  --top 10 \
  --lifecycle \
  --handoff-analyzer \
  --handoff-top 3 \
  --handoff-min-consistency 6 \
  "$@"
