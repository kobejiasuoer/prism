from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"

for path in (REPO_ROOT, PACKAGES_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _load_scan(monkeypatch: pytest.MonkeyPatch | None = None):
    """Re-import screener.scan so module-level env-var parsing runs fresh."""
    sys.modules.pop("screener.scan", None)
    return importlib.import_module("screener.scan")


def _stage0_raw(code: str, name: str = "测试股", amount: float = 100.0) -> dict:
    return {
        "code": code,
        "name": name,
        "amount": amount,
        "price": 10.0,
        "prev": 9.8,
        "open": 9.9,
        "high": 10.2,
        "low": 9.7,
        "change_pct": 2.0,
        "volume": 12345,
        "pe": 18.5,
        "pb": 2.1,
        "mktcap": 1.0e10,
        "turnover": 1.5,
    }


def test_default_excluded_code_prefixes_match_legacy_30_and_68(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", raising=False)
    scan = _load_scan()
    assert scan.EXCLUDED_CODE_PREFIXES == ("30", "68")


def test_normalize_stage0_excludes_30_and_68_codes_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", raising=False)
    scan = _load_scan()

    # Excluded by default.
    assert scan._normalize_stage0_stock(_stage0_raw("300001"), source_pool="test") is None
    assert scan._normalize_stage0_stock(_stage0_raw("688001"), source_pool="test") is None

    # Mainboard codes still pass through.
    main_a = scan._normalize_stage0_stock(_stage0_raw("600001"), source_pool="test")
    assert main_a is not None
    assert main_a["code"] == "600001"


def test_normalize_stage0_respects_runtime_override(monkeypatch: pytest.MonkeyPatch):
    """Operators can rewire the universe boundary by mutating the module-level constant."""
    monkeypatch.delenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", raising=False)
    scan = _load_scan()

    monkeypatch.setattr(scan, "EXCLUDED_CODE_PREFIXES", ())

    # With an empty exclusion set, 30 and 68 codes pass through.
    chinext = scan._normalize_stage0_stock(_stage0_raw("300001"), source_pool="test")
    star = scan._normalize_stage0_stock(_stage0_raw("688001"), source_pool="test")
    assert chinext is not None and chinext["code"] == "300001"
    assert star is not None and star["code"] == "688001"


def test_env_var_empty_string_disables_exclusion(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", "")
    scan = _load_scan()

    assert scan.EXCLUDED_CODE_PREFIXES == ()
    assert scan._normalize_stage0_stock(_stage0_raw("300001"), source_pool="test") is not None
    assert scan._normalize_stage0_stock(_stage0_raw("688001"), source_pool="test") is not None


def test_env_var_with_custom_prefixes_overrides_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", "00,87")
    scan = _load_scan()

    assert scan.EXCLUDED_CODE_PREFIXES == ("00", "87")
    # Now 00 and 87 are excluded; 30/68 are NOT.
    assert scan._normalize_stage0_stock(_stage0_raw("000001"), source_pool="test") is None
    assert scan._normalize_stage0_stock(_stage0_raw("870001"), source_pool="test") is None
    assert scan._normalize_stage0_stock(_stage0_raw("300001"), source_pool="test") is not None
    assert scan._normalize_stage0_stock(_stage0_raw("688001"), source_pool="test") is not None


def test_env_var_with_whitespace_is_trimmed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRISM_SCAN_EXCLUDED_CODE_PREFIXES", "  30 ,  ,68 ")
    scan = _load_scan()
    assert scan.EXCLUDED_CODE_PREFIXES == ("30", "68")
