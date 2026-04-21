#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".woff", ".woff2", ".docx", ".pyc"}
SKIP_PATHS = {
    Path("tests/test_secret_scrub.py"),
    Path("scripts/scrub-secrets.py"),
}
STRING_REPLACEMENTS = {
    "http://127.0.0.1:7897": "${PRISM_PROXY_URL}",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/reports/": "data/history/reports/screener/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/scripts/": "packages/screener/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/data/ai_history/": "data/history/ai_history/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/data/stale_outputs/": "data/history/stale_outputs/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/data/cron_logs/": "data/history/cron_logs/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-screener/data/": "runtime/stock-screener/data/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-analyzer/data/daily_snapshots/": "data/history/daily_snapshots/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/stock-analyzer/reports/": "external/stock-analyzer/reports/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/invest-flow/reports/": "data/history/reports/command_brief/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/invest-flow/data/command_brief/": "data/history/command_brief/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/invest-flow/data/control_panel_runs/logs/": "data/history/control_panel_runs/logs/",
    "/Users/yangbishang/.openclaw/workspace-invest/skills/invest-flow/data/control_panel_runs/": "data/history/control_panel_runs/",
    "/Users/yangbishang/workSpace/skills/stock-screener/": "legacy/stock-screener/",
}
REGEX_REPLACEMENTS = [
    (re.compile(r"user:ou_[A-Za-z0-9]+"), "user:<redacted>"),
    (re.compile(r"/Users/yangbishang/[^\s\"')]+"), "<redacted-path>"),
]
BAD_PATTERNS = [
    "cookie=",
    "gho_",
    "xoxb-",
    "Authorization: Bearer",
    "/Users/yangbishang",
    "user:ou_",
]

def should_skip(path: Path) -> bool:
    if path in SKIP_PATHS:
        return True
    return any(part in {".git", ".venv", "__pycache__"} for part in path.parts)

def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path

def scrub_text(text: str) -> str:
    for old, new in STRING_REPLACEMENTS.items():
        text = text.replace(old, new)
    for pattern, replacement in REGEX_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text

def main() -> None:
    root = Path(".")
    changed = 0
    for path in iter_text_files(root):
        original = path.read_text(encoding="utf-8", errors="ignore")
        scrubbed = scrub_text(original)
        if scrubbed != original:
            path.write_text(scrubbed, encoding="utf-8")
            changed += 1
        for marker in BAD_PATTERNS:
            if marker in scrubbed:
                raise SystemExit(f"manual review required: {marker} in {path}")
    print(f"scrubbed files: {changed}")

if __name__ == "__main__":
    main()
