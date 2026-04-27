#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/packages:${PYTHONPATH:-}"
cd "$SCRIPT_DIR"
unset http_proxy https_proxy all_proxy
python3 scan.py --strategy all --top 5
