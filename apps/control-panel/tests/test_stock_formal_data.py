# apps/control-panel/tests/test_stock_formal_data.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))


def _seed(root, dataset, date, key, payload):
    d = root / dataset / date; d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    (d / f"{key}.manifest.json").write_text(json.dumps({"trade_date": date, "provider": "tushare"}), encoding="utf-8")


def test_formal_data_includes_factor_profile(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    _seed(root, "valuation.daily", "2026-05-29", "600519", [{"trade_date": "2026-05-29", "pe_ttm": 28.0, "pb": 8.0}])
    _seed(root, "financial.indicator", "2026-05-29", "600519", [{"end_date": "2026-03-31", "roe": 18.0}])
    import importlib, data_assets
    importlib.reload(data_assets)
    # point data_assets' own reader at tmp root too
    data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data("sh600519", "2026-05-29")
    fp = payload["factor_profile"]
    assert fp["tushare_score"] is not None
    assert "高ROE" in fp["factor_tags"]
    assert fp["explanation"]["evidence"]["fundamental"]["available"] is True


def test_formal_data_factor_profile_missing_is_graceful(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    import importlib, data_assets
    importlib.reload(data_assets); data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data("sh000001", "2026-05-29")
    assert payload["factor_profile"]["tushare_score"] is None      # no fabrication
