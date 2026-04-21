#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
unset http_proxy https_proxy all_proxy
python3 -c "
import sys
sys.argv = ['scan.py', '--strategy', 'all', '--top', '5', '--pool', 'aggressive']
import scan
scan.main()
"
