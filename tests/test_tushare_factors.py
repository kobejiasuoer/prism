# tests/test_tushare_factors.py
import json
import os
from pathlib import Path

import pytest


@pytest.fixture()
def dataset_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    return root


def _write(root: Path, dataset: str, date: str, key: str, payload):
    d = root / dataset / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    (d / f"{key}.manifest.json").write_text(json.dumps({"trade_date": date, "provider": "tushare"}), encoding="utf-8")


def test_module_imports_and_reads_dataset(dataset_root):
    from screener import tushare_factors as tf

    _write(dataset_root, "valuation.daily", "2026-05-29", "600519",
           [{"trade_date": "2026-05-29", "pe_ttm": 30.0, "pb": 8.0}])
    rows, manifest = tf._load_dataset("valuation.daily", "2026-05-29", "600519")
    assert isinstance(rows, list) and rows[0]["pe_ttm"] == 30.0
    assert manifest["provider"] == "tushare"


def test_resolve_trade_date_falls_back_to_latest(dataset_root):
    from screener import tushare_factors as tf

    _write(dataset_root, "valuation.daily", "2026-05-27", "600519", [{"trade_date": "2026-05-27"}])
    _write(dataset_root, "valuation.daily", "2026-05-29", "600519", [{"trade_date": "2026-05-29"}])
    assert tf._resolve_trade_date("valuation.daily", "2026-05-30") == "2026-05-29"  # walk back
    assert tf._resolve_trade_date("valuation.daily", None) == "2026-05-29"          # latest
    assert tf._resolve_trade_date("valuation.daily", "2026-05-27") == "2026-05-27"  # exact
