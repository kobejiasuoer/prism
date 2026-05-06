from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"

for path in (REPO_ROOT, PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _baseline_payload(active_count: int = 6, archived_count: int = 1) -> dict:
    """A valid parameter payload with a known active/archived split."""
    stocks = []
    for i in range(active_count):
        stocks.append(
            {"code": f"6000{i:02d}", "name": f"Active{i}", "active": True}
        )
    for j in range(archived_count):
        stocks.append(
            {"code": f"0000{j:02d}", "name": f"Archived{j}", "active": False}
        )
    return {
        "stocks": stocks,
        "ma_periods": [5, 10, 20, 60],
        "news_count": 6,
        "kline_days": 60,
    }


# --- Block 1: parameter_evaluation pure function ---


def _eval():
    from control_panel.app import parameter_evaluation
    return parameter_evaluation


def test_baseline_payload_passes_evaluation_with_no_errors():
    parameter_evaluation = _eval()
    candidate = _baseline_payload()
    result = parameter_evaluation(candidate, current=candidate)
    assert result["ok"] is True
    assert result["errors"] == []
    # Warnings may or may not be present — baseline shouldn't produce any.
    assert result["warnings"] == []


def test_zero_active_stocks_is_a_hard_error():
    parameter_evaluation = _eval()
    candidate = _baseline_payload(active_count=0, archived_count=3)
    result = parameter_evaluation(candidate, current=_baseline_payload())
    assert result["ok"] is False
    assert any("活跃" in err or "active" in err.lower() for err in result["errors"])


def test_active_count_dropping_more_than_half_warns_but_does_not_block():
    parameter_evaluation = _eval()
    current = _baseline_payload(active_count=10)
    candidate = _baseline_payload(active_count=4)  # 60% drop
    result = parameter_evaluation(candidate, current=current)
    assert result["ok"] is True
    assert any("减少" in w or "drop" in w.lower() or "下降" in w for w in result["warnings"])


def test_duplicate_code_is_a_hard_error():
    parameter_evaluation = _eval()
    candidate = _baseline_payload()
    candidate["stocks"].append({"code": "600000", "name": "重复", "active": True})
    result = parameter_evaluation(candidate, current=_baseline_payload())
    assert result["ok"] is False
    assert any("重复" in err or "duplicate" in err.lower() for err in result["errors"])


def test_out_of_range_kline_days_warns():
    parameter_evaluation = _eval()
    too_small = _baseline_payload()
    too_small["kline_days"] = 5
    result_small = parameter_evaluation(too_small, current=_baseline_payload())
    assert result_small["ok"] is True
    assert any("kline_days" in w for w in result_small["warnings"])

    too_large = _baseline_payload()
    too_large["kline_days"] = 9999
    result_large = parameter_evaluation(too_large, current=_baseline_payload())
    assert any("kline_days" in w for w in result_large["warnings"])


def test_out_of_range_news_count_warns():
    parameter_evaluation = _eval()
    too_large = _baseline_payload()
    too_large["news_count"] = 200
    result = parameter_evaluation(too_large, current=_baseline_payload())
    assert any("news_count" in w for w in result["warnings"])


def test_evaluation_handles_missing_current_state():
    """First-time save (no prior current) must not crash on regression checks."""
    parameter_evaluation = _eval()
    candidate = _baseline_payload()
    result = parameter_evaluation(candidate, current=None)
    assert result["ok"] is True


# --- Block 2: API integration via /api/parameters ---


def _client_with_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from control_panel import app as app_module

    fake_path = tmp_path / "stocks.json"
    fake_path.write_text(json.dumps(_baseline_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(app_module, "PARAMETERS_PATH", fake_path)
    return TestClient(app_module.app), fake_path


def test_api_save_includes_evaluation_in_success_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, fake_path = _client_with_tmp_path(tmp_path, monkeypatch)
    candidate = _baseline_payload()
    candidate["news_count"] = 8

    response = client.post("/api/parameters", json={"value": candidate})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("saved") is True
    assert "evaluation" in payload
    assert payload["evaluation"]["ok"] is True


def test_api_save_blocks_on_hard_evaluation_error_without_unsafe_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _ = _client_with_tmp_path(tmp_path, monkeypatch)
    bad = _baseline_payload(active_count=0, archived_count=3)

    response = client.post("/api/parameters", json={"value": bad})
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload.get("saved") is False
    assert "evaluation" in payload
    assert payload["evaluation"]["ok"] is False
    assert payload["evaluation"]["errors"]


def test_api_save_allows_unsafe_apply_to_force_through_evaluation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, fake_path = _client_with_tmp_path(tmp_path, monkeypatch)
    bad = _baseline_payload(active_count=0, archived_count=3)

    response = client.post(
        "/api/parameters",
        json={"value": bad, "unsafe_apply": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("saved") is True
    # The evaluation result is still surfaced even though we overrode it.
    assert payload["evaluation"]["ok"] is False
    assert payload["evaluation"]["errors"]
    # File on disk reflects the forced save.
    saved = json.loads(fake_path.read_text(encoding="utf-8"))
    active_codes = [s for s in saved["stocks"] if s.get("active", True) is not False]
    assert len(active_codes) == 0
