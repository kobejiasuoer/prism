import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_data_assets_status_exposes_feature_usage(tmp_path):
    import importlib
    import data_assets

    root = tmp_path / "datasets"
    d = root / "corporate_action.pledge_stat" / "2026-05-29"
    d.mkdir(parents=True)
    (d / "all.json").write_text(json.dumps([{"ts_code": "600519.SH", "pledge_ratio": 40}]), encoding="utf-8")
    (d / "all.manifest.json").write_text(json.dumps({"trade_date": "2026-05-29", "provider": "tushare"}), encoding="utf-8")
    importlib.reload(data_assets)
    data_assets.DATASET_ROOT = root

    status = data_assets.build_data_assets_status("2026-05-29")
    row = next(item for item in status["datasets"] if item["dataset"] == "corporate_action.pledge_stat")
    assert row["feature_group"] == "risk_event"
    assert row["decision_use"] == "risk_penalty"
    assert row["live_permission"] == "research_only"
    assert "stock_profile" in row["intended_surfaces"]
    assert row["formal_decision_allowed"] is False
