from __future__ import annotations

import importlib.util
from pathlib import Path

from screener.capital_flow_contract import (
    UNIT_YUAN,
    normalize_capital_flow_payload,
    normalize_capital_flow_row,
)


def load_module(module_name: str, relative_path: str):
    target = Path(relative_path).resolve()
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_legacy_screener_payload_from_yuan_gets_normalized():
    payload = normalize_capital_flow_payload(
        {
            "trend": "今日流入",
            "today": 123456789,
            "5day_total": 345678901,
        },
        legacy_source_unit=UNIT_YUAN,
    )

    assert payload["unit"] == "wan_yuan"
    assert payload["today"] == 12345.68
    assert payload["today_wan"] == 12345.68
    assert payload["today_yi"] == 1.23
    assert payload["5day_total"] == 34567.89
    assert payload["five_day_total_wan"] == 34567.89
    assert payload["five_day_total_yi"] == 3.46


def test_capital_flow_row_from_em_yuan_is_normalized_to_wan():
    row = normalize_capital_flow_row(
        {
            "date": "2026-04-23",
            "main_net": 98765432,
            "super_large": 12345678,
        },
        source_unit=UNIT_YUAN,
    )

    assert row == {
        "date": "2026-04-23",
        "unit": "wan_yuan",
        "main_net": 9876.54,
        "main_net_wan": 9876.54,
        "main_net_yi": 0.99,
        "super_large": 1234.57,
        "super_large_wan": 1234.57,
        "super_large_yi": 0.12,
    }


def test_canonical_candidate_keeps_legacy_scan_payload_readable():
    canonical = load_module("prism_canonical_test", "apps/scripts/prism_canonical.py")

    candidate = canonical.normalize_candidate(
        {
            "code": "000001",
            "name": "测试股份",
            "capital_flow": {
                "trend": "今日流入",
                "today": 220000000,
                "5day_total": 540000000,
            },
        },
        "batch:test",
    )

    assert candidate["capital_flow"]["today_wan"] == 22000.0
    assert candidate["capital_flow"]["today_yi"] == 2.2
    assert candidate["capital_flow"]["five_day_total_yi"] == 5.4


def test_watchlist_flow_history_exposes_explicit_unit_fields():
    fetch = load_module("watchlist_fetch_test", "stock-analyzer/scripts/fetch.py")

    flow = fetch._build_capital_flow_from_history(
        [
            {"date": "2026-04-17", "main_net": -500.0, "super_net": 100.0},
            {"date": "2026-04-18", "main_net": 700.0, "super_net": 200.0},
            {"date": "2026-04-21", "main_net": 1200.0, "super_net": 300.0},
            {"date": "2026-04-22", "main_net": 900.0, "super_net": 400.0},
            {"date": "2026-04-23", "main_net": 1500.0, "super_net": 500.0},
        ]
    )

    assert flow["unit"] == "wan_yuan"
    assert flow["main_net"] == 1500.0
    assert flow["main_net_wan"] == 1500.0
    assert flow["main_net_yi"] == 0.15
    assert flow["today_wan"] == 1500.0
    assert flow["today_yi"] == 0.15
    assert flow["five_day_total_wan"] == 3800.0
    assert flow["five_day_total_yi"] == 0.38
