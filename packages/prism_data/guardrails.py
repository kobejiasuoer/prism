"""Guardrails to prevent direct external market-data access outside prism_data.

The repo-level policy is:

* production market/provider access must flow through ``packages/prism_data``;
* provider adapters under ``packages/prism_data/providers`` are the only place
  allowed to use direct HTTP / provider SDKs for these sources;
* a tiny explicit allowlist may remain for research-only or non-ingress cases,
  and every entry must carry a human-readable reason.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


DEFAULT_EXCLUDE_PATHS = [
    ".claude",
    ".venv",
    "node_modules",
    "__pycache__",
    "packages/prism_data/providers",
]

REPO_SCAN_ALLOWLIST: dict[str, str] = {
    "packages/quant/free_sources/live_smoke_runner.py": (
        "research-only free-source smoke runner; intentionally probes akshare/baostock"
    ),
}


class DirectHTTPCallVisitor(ast.NodeVisitor):
    """AST visitor that tracks import aliases and detects forbidden calls."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.violations: list[dict[str, Any]] = []
        self.requests_aliases: set[str] = set()
        self.requests_function_aliases: dict[str, str] = {}
        self.urllib_request_aliases: set[str] = set()
        self.urlopen_aliases: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            bound_name = alias.asname or name.split(".")[-1]
            if name == "requests":
                self.requests_aliases.add(bound_name)
            if name == "urllib.request":
                self.urllib_request_aliases.add(bound_name)
            if name in {"akshare", "baostock"}:
                self.violations.append(
                    {
                        "file": self.filepath,
                        "line": node.lineno,
                        "type": "direct_provider_import",
                        "import": name,
                    }
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == "requests":
            for alias in node.names:
                if alias.name in {"get", "post", "request"}:
                    self.requests_function_aliases[alias.asname or alias.name] = alias.name
        if module == "urllib.request":
            for alias in node.names:
                if alias.name == "urlopen":
                    self.urlopen_aliases.add(alias.asname or alias.name)
        if module in {"akshare", "baostock"}:
            self.violations.append(
                {
                    "file": self.filepath,
                    "line": node.lineno,
                    "type": "direct_provider_import",
                    "import": module,
                }
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name: str | None = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            base = node.func.value.id
            attr = node.func.attr
            if base in self.requests_aliases and attr in {"get", "post", "request"}:
                call_name = f"{base}.{attr}"
            if base in self.urllib_request_aliases and attr == "urlopen":
                call_name = f"{base}.urlopen"
        elif isinstance(node.func, ast.Name):
            if node.func.id in self.urlopen_aliases:
                call_name = node.func.id
            elif node.func.id in self.requests_function_aliases:
                call_name = f"requests.{self.requests_function_aliases[node.func.id]}"

        if call_name:
            self.violations.append(
                {
                    "file": self.filepath,
                    "line": node.lineno,
                    "type": "direct_http_call",
                    "call": call_name,
                }
            )
        self.generic_visit(node)


def _normalize_root(root_path: Path | str) -> Path | None:
    try:
        root = Path(root_path)
        if not root.exists():
            return None
        return root
    except (OSError, ValueError):
        return None


def _normalize_allowlist(allowlist_files: list[str] | dict[str, str] | None) -> set[str]:
    if not allowlist_files:
        return set()
    if isinstance(allowlist_files, dict):
        return set(allowlist_files)
    return set(allowlist_files)


def _iter_python_files(root: Path):
    try:
        yield from root.rglob("*.py")
    except (OSError, PermissionError):
        return


def _skip_path(rel_path: str, *, exclude_paths: list[str], allowlist: set[str]) -> bool:
    if rel_path in allowlist:
        return True
    if any(excl in rel_path for excl in exclude_paths):
        return True
    if "__pycache__" in rel_path:
        return True
    if Path(rel_path).name.startswith("test_"):
        return True
    return False


def scan_for_direct_http_calls(
    root_path: Path | str = ".",
    exclude_paths: list[str] | None = None,
    allowlist_files: list[str] | dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = _normalize_root(root_path)
    if root is None:
        return []

    exclude = list(exclude_paths or [])
    allowlist = _normalize_allowlist(allowlist_files)
    violations: list[dict[str, Any]] = []

    for py_file in _iter_python_files(root):
        try:
            rel_path = str(py_file.relative_to(root))
        except (ValueError, OSError):
            continue
        if _skip_path(rel_path, exclude_paths=exclude, allowlist=allowlist):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError, OSError, PermissionError):
            continue
        visitor = DirectHTTPCallVisitor(rel_path)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    return violations


def scan_for_hardcoded_urls(
    root_path: Path | str = ".",
    exclude_paths: list[str] | None = None,
    allowlist_files: list[str] | dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = _normalize_root(root_path)
    if root is None:
        return []

    exclude = list(exclude_paths or [])
    allowlist = _normalize_allowlist(allowlist_files)
    violations: list[dict[str, Any]] = []

    url_patterns = [
        r"https?://[^\"\s]*sinajs[^\"\s]*",
        r"https?://[^\"\s]*sina[^\"\s]*\.(?:com|cn)[^\"\s]*",
        r"https?://[^\"\s]*eastmoney[^\"\s]*\.com[^\"\s]*",
        r"https?://[^\"\s]*10jqka[^\"\s]*\.com[^\"\s]*",
        r"https?://[^\"\s]*hexun[^\"\s]*\.com[^\"\s]*",
    ]
    combined_pattern = re.compile("|".join(url_patterns))

    for py_file in _iter_python_files(root):
        try:
            rel_path = str(py_file.relative_to(root))
        except (ValueError, OSError):
            continue
        if _skip_path(rel_path, exclude_paths=exclude, allowlist=allowlist):
            continue
        try:
            for line_num, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
                match = combined_pattern.search(line)
                if match:
                    violations.append(
                        {
                            "file": rel_path,
                            "line": line_num,
                            "type": "hardcoded_provider_url",
                            "url": match.group(0),
                        }
                    )
        except (UnicodeDecodeError, OSError, PermissionError):
            continue

    return violations


def scan_repo_for_ingress_violations(
    root_path: Path | str = ".",
    *,
    exclude_paths: list[str] | None = None,
    allowlist_files: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    allowlist = dict(REPO_SCAN_ALLOWLIST)
    if allowlist_files:
        allowlist.update(allowlist_files)
    exclude = [*DEFAULT_EXCLUDE_PATHS, *(exclude_paths or [])]
    return [
        *scan_for_direct_http_calls(root_path=root_path, exclude_paths=exclude, allowlist_files=allowlist),
        *scan_for_hardcoded_urls(root_path=root_path, exclude_paths=exclude, allowlist_files=allowlist),
    ]


__all__ = [
    "DEFAULT_EXCLUDE_PATHS",
    "REPO_SCAN_ALLOWLIST",
    "scan_for_direct_http_calls",
    "scan_for_hardcoded_urls",
    "scan_repo_for_ingress_violations",
]
