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


def test_data_assets_status_compact_payload_keeps_summary_but_drops_diagnostics(tmp_path):
    import importlib
    import data_assets

    root = tmp_path / "datasets"
    d = root / "bars.daily" / "2026-05-29"
    d.mkdir(parents=True)
    (d / "600519.manifest.json").write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "provider": "tushare",
                "request_key": "600519",
                "row_count": 240,
                "freshness_status": "fresh",
                "source_lane": "formal",
                "decision_scope": "formal_candidate",
            }
        ),
        encoding="utf-8",
    )
    importlib.reload(data_assets)
    data_assets.DATASET_ROOT = root

    full = data_assets.build_data_assets_status("2026-05-29")
    compact = data_assets.build_data_assets_status("2026-05-29", compact=True)

    assert compact["compact"] is True
    assert compact["datasets_deferred"] is True
    assert full["datasets_deferred"] is False
    assert compact["summary"]["available_count"] == full["summary"]["available_count"]
    assert compact["summary"]["displayed_dataset_count"] == len(compact["datasets"])
    assert len(compact["datasets"]) <= data_assets.COMPACT_DATASET_LIMIT

    compact_row = next(item for item in compact["datasets"] if item["dataset"] == "bars.daily")
    assert compact_row["provider"] == "tushare"
    assert compact_row["latest_row_count"] == 240
    assert "usage_explanation" not in compact_row
    assert "intended_surfaces" not in compact_row
    assert "source_lane" not in compact_row
    assert "decision_scope" not in compact_row

    full_row = next(item for item in full["datasets"] if item["dataset"] == "bars.daily")
    assert "usage_explanation" in full_row
    assert "intended_surfaces" in full_row


def test_data_assets_status_does_not_parse_historical_manifests_for_summary(tmp_path, monkeypatch):
    import importlib
    import data_assets

    root = tmp_path / "datasets"
    old_dir = root / "bars.daily" / "2026-05-28"
    current_dir = root / "bars.daily" / "2026-05-29"
    old_dir.mkdir(parents=True)
    current_dir.mkdir(parents=True)
    for index in range(20):
        (old_dir / f"{index:06d}.manifest.json").write_text(
            json.dumps({"trade_date": "2026-05-28", "provider": "tushare", "request_key": f"{index:06d}"}),
            encoding="utf-8",
        )
    (current_dir / "600519.manifest.json").write_text(
        json.dumps({"trade_date": "2026-05-29", "provider": "tushare", "request_key": "600519", "row_count": 100}),
        encoding="utf-8",
    )

    importlib.reload(data_assets)
    data_assets.DATASET_ROOT = root
    data_assets.clear_data_assets_status_cache()
    original_read = data_assets._read_json_or_none
    seen_manifest_paths: list[Path] = []

    def tracking_read(path: Path):
        if root in path.parents and path.name.endswith(".manifest.json"):
            seen_manifest_paths.append(path)
        return original_read(path)

    monkeypatch.setattr(data_assets, "_read_json_or_none", tracking_read)
    status = data_assets.build_data_assets_status("2026-05-29")

    row = next(item for item in status["datasets"] if item["dataset"] == "bars.daily")
    assert row["available"] is True
    assert row["provider"] == "tushare"
    assert row["manifest_count"] == 21
    assert row["key_count"] == 1
    assert seen_manifest_paths == [current_dir / "600519.manifest.json"]


def test_data_assets_status_fresh_bypasses_cache(tmp_path):
    import importlib
    import data_assets

    root = tmp_path / "datasets"
    current_dir = root / "bars.daily" / "2026-05-29"
    current_dir.mkdir(parents=True)
    manifest_path = current_dir / "600519.manifest.json"
    manifest_path.write_text(
        json.dumps({"trade_date": "2026-05-29", "provider": "first", "request_key": "600519"}),
        encoding="utf-8",
    )

    importlib.reload(data_assets)
    data_assets.DATASET_ROOT = root
    data_assets.clear_data_assets_status_cache()

    first = data_assets.build_data_assets_status("2026-05-29")
    manifest_path.write_text(
        json.dumps({"trade_date": "2026-05-29", "provider": "second", "request_key": "600519"}),
        encoding="utf-8",
    )
    cached = data_assets.build_data_assets_status("2026-05-29")
    fresh = data_assets.build_data_assets_status("2026-05-29", fresh=True)

    first_row = next(item for item in first["datasets"] if item["dataset"] == "bars.daily")
    cached_row = next(item for item in cached["datasets"] if item["dataset"] == "bars.daily")
    fresh_row = next(item for item in fresh["datasets"] if item["dataset"] == "bars.daily")
    assert first_row["provider"] == "first"
    assert cached_row["provider"] == "first"
    assert fresh_row["provider"] == "second"
