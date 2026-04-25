from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load_module(module_name: str, relative_path: str):
    target = Path(relative_path).resolve()
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_migrate_screener_artifact_normalizes_nested_capital_flow():
    script = load_module("capital_flow_migration_test", "scripts/migrate_capital_flow_artifacts.py")

    migrated = script.migrate_screener_artifact(
        {
            "verification_universe": [
                {
                    "code": "000001",
                    "capital_flow": {
                        "trend": "连续2日流入",
                        "today": 200000000,
                        "5day_total": 350000000,
                    },
                }
            ],
            "strategies": {
                "growth": [
                    {
                        "code": "000001",
                        "capital_flow": {
                            "trend": "连续2日流入",
                            "today": 200000000,
                            "5day_total": 350000000,
                        },
                    }
                ]
            },
        }
    )

    capital_flow = migrated["verification_universe"][0]["capital_flow"]
    assert capital_flow["unit"] == "wan_yuan"
    assert capital_flow["today_wan"] == 20000.0
    assert capital_flow["today_yi"] == 2.0
    assert capital_flow["five_day_total_wan"] == 35000.0
    assert capital_flow["five_day_total_yi"] == 3.5

    strategy_flow = migrated["strategies"]["growth"][0]["capital_flow"]
    assert strategy_flow["today_wan"] == 20000.0
    assert strategy_flow["5day_total"] == 35000.0


def test_migrate_watchlist_flow_cache_adds_explicit_unit_fields():
    script = load_module("capital_flow_migration_watchlist_test", "scripts/migrate_capital_flow_artifacts.py")

    migrated = script.migrate_watchlist_flow_cache(
        [
            {
                "date": "2026-04-23",
                "main_net": 1500.0,
                "super_net": 300.0,
                "mid_large_net": -100.0,
                "retail_net": -200.0,
                "small_net": 0.0,
            }
        ]
    )

    assert migrated == [
        {
            "date": "2026-04-23",
            "unit": "wan_yuan",
            "main_net": 1500.0,
            "main_net_wan": 1500.0,
            "main_net_yi": 0.15,
            "super_net": 300.0,
            "super_net_wan": 300.0,
            "super_net_yi": 0.03,
            "mid_large_net": -100.0,
            "mid_large_net_wan": -100.0,
            "mid_large_net_yi": -0.01,
            "retail_net": -200.0,
            "retail_net_wan": -200.0,
            "retail_net_yi": -0.02,
            "small_net": 0.0,
            "small_net_wan": 0.0,
            "small_net_yi": 0.0,
        }
    ]


def test_migrate_file_dry_run_reports_change_without_writing(tmp_path):
    script = load_module("capital_flow_migration_file_test", "scripts/migrate_capital_flow_artifacts.py")

    path = tmp_path / "scan_result.json"
    original = {
        "verification_universe": [
            {
                "code": "000001",
                "capital_flow": {
                    "trend": "今日流入",
                    "today": 120000000,
                    "5day_total": 280000000,
                },
            }
        ]
    }
    path.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")

    changed = script.migrate_file(path, apply=False)

    assert changed is True
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == original
