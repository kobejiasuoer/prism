#!/usr/bin/env python3
"""Safely persist the local Tushare token for Prism.

The token is written only to the project root .env file, which is gitignored.
The script never prints the token value.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from prism_data.env import configured_env_names, project_env_path, read_project_env  # noqa: E402
from prism_data.providers.tushare import TushareProvider  # noqa: E402


TOKEN_KEY = "PRISM_TUSHARE_TOKEN"
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{16,128}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure the local Prism Tushare token without printing it.")
    parser.add_argument("--check", action="store_true", help="Only report whether a token is configured.")
    parser.add_argument("--stdin", action="store_true", help="Read the token from stdin instead of a hidden prompt.")
    return parser.parse_args()


def _validate_token(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("empty token")
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("token contains unsupported characters or has an unexpected length")
    return token


def _env_line(key: str, value: str) -> str:
    return f"{key}={value}\n"


def write_env_token(token: str) -> Path:
    env_path = project_env_path(REPO_ROOT)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True) if env_path.exists() else []
    updated = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        probe = stripped[len("export ") :].strip() if stripped.startswith("export ") else stripped
        key = probe.split("=", 1)[0].strip() if "=" in probe else ""
        if key == TOKEN_KEY:
            out.append(_env_line(TOKEN_KEY, token))
            updated = True
        else:
            out.append(line)
    if not updated:
        if out and not out[-1].endswith("\n"):
            out[-1] = f"{out[-1]}\n"
        out.append(_env_line(TOKEN_KEY, token))
    env_path.write_text("".join(out), encoding="utf-8")
    return env_path


def status_payload() -> dict[str, object]:
    env_path = project_env_path(REPO_ROOT)
    env_values = read_project_env(REPO_ROOT)
    names = TushareProvider.token_env_names()
    configured_names = configured_env_names(names, root=REPO_ROOT)
    return {
        "env_path": str(env_path),
        "env_file_exists": env_path.exists(),
        "token_configured": bool(configured_names),
        "configured_token_env_names": configured_names,
        "token_value_visible": False,
        "env_file_has_token_key": any(bool(env_values.get(name, "").strip()) for name in names),
    }


def main() -> int:
    args = parse_args()
    if args.check:
        print(json.dumps(status_payload(), ensure_ascii=False, indent=2))
        return 0

    raw_token = sys.stdin.read() if args.stdin else getpass.getpass("Tushare token: ")
    try:
        token = _validate_token(raw_token)
    except ValueError as exc:
        print(f"Token not saved: {exc}", file=sys.stderr)
        return 2
    env_path = write_env_token(token)
    payload = status_payload()
    payload["saved"] = True
    payload["env_path"] = str(env_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
