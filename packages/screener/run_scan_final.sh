#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Set environment and clear proxies
unset http_proxy https_proxy all_proxy

# Define the Python command as a string
PYTHON_CMD="python3 -c \"
import sys
import os
import json
from datetime import datetime

# Mock command line arguments
sys.argv = ['scan.py', '--strategy', 'all', '--top', '5']

# Import scan module
import scan

# Run main function
scan.main()
\"

# Execute the command
eval \"\$PYTHON_CMD\""
