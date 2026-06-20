from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

import dashboard_data as dd  # noqa: E402


def test_resolve_readiness_returns_cached_when_base_has_it():
    """When base carries a readiness dict, resolve_readiness returns it verbatim
    (no recompute) — this is the cache-hit path most views use."""
    cached = {"readiness_mode": "live_ready", "expected_trade_date": "2026-06-19"}
    result = dd.resolve_readiness(base={"readiness": cached})
    assert result is cached


def test_resolve_readiness_recomputes_when_base_missing(monkeypatch):
    """When base has no readiness, resolve_readiness falls back to compute_readiness."""
    called = {"n": 0}

    def fake_compute(**kwargs):
        called["n"] += 1
        return {"readiness_mode": "shadow_only", "expected_trade_date": "2026-06-19"}

    monkeypatch.setattr(dd, "compute_readiness", fake_compute)
    result = dd.resolve_readiness(base={}, watchlist=[], screening_batch=None)
    assert called["n"] == 1
    assert result["readiness_mode"] == "shadow_only"


def test_resolve_readiness_force_recompute_overrides_cache(monkeypatch):
    """force_recompute=True ignores a cached readiness and recomputes.

    This is the path views that need fresh data (e.g. opportunities) use."""
    cached = {"readiness_mode": "live_ready"}
    called = {"n": 0}

    def fake_compute(**kwargs):
        called["n"] += 1
        return {"readiness_mode": "blocked", "expected_trade_date": "2026-06-19"}

    monkeypatch.setattr(dd, "compute_readiness", fake_compute)
    result = dd.resolve_readiness(base={"readiness": cached}, force_recompute=True, watchlist=[])
    assert called["n"] == 1
    assert result["readiness_mode"] == "blocked"


def test_resolve_readiness_base_none_recomputes(monkeypatch):
    """base=None (no shared cache available) recomputes."""
    called = {"n": 0}

    def fake_compute(**kwargs):
        called["n"] += 1
        return {"readiness_mode": "live_ready", "expected_trade_date": "2026-06-19"}

    monkeypatch.setattr(dd, "compute_readiness", fake_compute)
    result = dd.resolve_readiness(base=None, watchlist=[], screening_batch=None)
    assert called["n"] == 1
    assert result["readiness_mode"] == "live_ready"


def test_resolve_readiness_no_base_no_kwargs_recomputes(monkeypatch):
    """Bare call with no base recomputes (compute_readiness has its own defaults)."""
    monkeypatch.setattr(dd, "compute_readiness", lambda **kw: {"readiness_mode": "live_ready"})
    result = dd.resolve_readiness()
    assert result["readiness_mode"] == "live_ready"
