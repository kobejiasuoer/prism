#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
unset http_proxy https_proxy all_proxy
python3 scan.py --strategy all --top 5
