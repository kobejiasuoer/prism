import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decision_ledger


def _outcome(window, ret, label="validated"):
    return {
        "window": window,
        "market_data": {"return_pct": ret, "relative_return_pct": ret},
        "classification": {"label": label},
        "quality": {"usable_for_decision_quality": True},
    }


def _rec(code, raw_snapshot, outcomes, *, tags=None, risks=None):
    return {
        "decision_id": f"d:{code}",
        "trade_date": "2026-05-15",
        "factor_snapshot": {
            "tushare_score": 70.0,
            "factor_tags": tags or [],
            "risk_flags": risks or [],
            "tushare_score_breakdown": {"quality": {"score": 70}},
            "factor_snapshot": raw_snapshot,
            "trade_date_used": "2026-05-29",
        },
        "outcome_events": outcomes,
    }


def _snapshot(*, roe=18.0, debt=30.0, pe=20.0, pb=2.0, flow=1.0, flow5=3.0,
              theme=True, event_risk=False, margin_change=0.5, chips_pressure=False):
    return {
        "fundamentals": {"roe": roe, "debt_to_assets": debt},
        "valuation": {"pe_ttm": pe, "pb": pb},
        "capital_flow": {"main_net_yi": flow, "five_day_main_net_yi": flow5},
        "theme_exposure": {"concepts": ["AI"] if theme else [], "industries": ["电子"] if theme else []},
        "event_risks": {
            "pledge_ratio": 40.0 if event_risk else 5.0,
            "share_float_total_mv": 20.0 if event_risk else 1.0,
            "block_trade_average_discount_pct": -8.0 if event_risk else 1.0,
        },
        "margin_activity": {"balance_change": margin_change, "data_available": True},
        "technical_chips": {
            "data_available": True,
            "winner_rate": 90.0 if chips_pressure else 55.0,
            "pressure_ratio": 1.12 if chips_pressure else 0.98,
        },
    }


def test_factor_learning_loop_buckets_seven_dimensions_and_windows():
    records = [
        _rec("600001", _snapshot(), [_outcome("T+1", 2.0), _outcome("T+3", 5.0), _outcome("T+5", 4.0)]),
        _rec("600002", _snapshot(roe=4.0, debt=75.0, pe=80.0, pb=9.0, flow=-1.0, flow5=-2.0,
                                  theme=False, event_risk=True, margin_change=4.0, chips_pressure=True),
             [_outcome("T+1", -2.0, "invalidated"), _outcome("T+3", -4.0, "invalidated"), _outcome("T+5", 6.0, "missed_opportunity")],
             risks=["股权质押风险", "大宗折价"]),
    ]

    loop = decision_ledger.build_factor_learning_loop(records, as_of="2026-06-01")

    assert loop["as_of"] == "2026-06-01"
    assert set(loop["dimensions"]) == {"quality", "valuation", "capital_flow", "theme", "event_risk", "margin", "chips"}
    assert set(loop["buckets"]) == set(loop["dimensions"])
    assert loop["buckets"]["quality"]["strong"]["mature_count"] == 1
    assert loop["buckets"]["quality"]["weak"]["mature_count"] == 1
    assert loop["buckets"]["quality"]["strong"]["avg_return_by_window"]["T+3"] == 5.0
    assert loop["buckets"]["quality"]["weak"]["avg_return_by_window"]["T+3"] == -4.0
    assert loop["buckets"]["event_risk"]["flagged"]["false_positive_rate_by_window"]["T+5"] == 1.0
    assert loop["buckets"]["chips"]["pressure"]["review_rate_by_window"]["T+1"] == 1.0
    assert "T+10" in loop["outcome_windows"]


def test_factor_learning_loop_ignores_records_without_outcome():
    records = [_rec("600001", _snapshot(), [])]
    loop = decision_ledger.build_factor_learning_loop(records)
    assert loop["buckets"]["quality"]["strong"]["sample_count"] == 1
    assert loop["buckets"]["quality"]["strong"]["mature_count"] == 0
    assert loop["buckets"]["quality"]["strong"]["avg_return_by_window"]["T+3"] is None


def test_factor_learning_loop_tolerates_legacy_records_without_factor_snapshot():
    records = [{"decision_id": "legacy", "trade_date": "2026-05-15", "outcome_events": [_outcome("T+1", 2.0)]}]
    loop = decision_ledger.build_factor_learning_loop(records)
    assert loop["factor_tag_stats"] == []
    assert loop["risk_flag_stats"] == []
    assert loop["learning_summary"]["sample_count"] == 0


def test_factor_learning_loop_does_not_bucket_missing_factor_dimensions_as_clean():
    records = [_rec("600001", {}, [_outcome("T+1", 1.0)])]
    loop = decision_ledger.build_factor_learning_loop(records)

    assert loop["buckets"]["theme"]["unexposed"]["sample_count"] == 0
    assert loop["buckets"]["event_risk"]["clean"]["sample_count"] == 0


def test_factor_learning_loop_summarizes_factor_tags_risks_and_score_buckets():
    records = [
        _rec("600001", _snapshot(), [_outcome("T+1", 2.0), _outcome("T+10", 6.0)], tags=["高ROE"], risks=[]),
        _rec("600002", _snapshot(), [_outcome("T+1", 3.0), _outcome("T+10", 5.0)], tags=["高ROE"], risks=[]),
        _rec("600003", _snapshot(), [_outcome("T+1", 1.0), _outcome("T+10", 4.0)], tags=["高ROE"], risks=[]),
        _rec("600004", _snapshot(event_risk=True), [_outcome("T+1", -3.0, "invalidated")], tags=["低估值"], risks=["大宗折价"]),
        _rec("600005", _snapshot(event_risk=True), [_outcome("T+1", -2.0, "invalidated")], tags=["低估值"], risks=["大宗折价"]),
        _rec("600006", _snapshot(event_risk=True), [_outcome("T+1", -4.0, "invalidated")], tags=["低估值"], risks=["大宗折价"]),
    ]
    records[3]["factor_snapshot"]["tushare_score"] = 55.0
    records[4]["factor_snapshot"]["tushare_score"] = 55.0
    records[5]["factor_snapshot"]["tushare_score"] = 55.0

    loop = decision_ledger.build_factor_learning_loop(records, as_of="2026-06-01")

    tag_rows = {row["key"]: row for row in loop["factor_tag_stats"]}
    assert tag_rows["高ROE"]["window_stats"]["T+10"]["sample_count"] == 3
    assert tag_rows["高ROE"]["window_stats"]["T+10"]["win_rate"] == 1.0
    assert tag_rows["高ROE"]["window_stats"]["T+10"]["avg_excess_return_pct"] == 5.0

    risk_rows = {row["key"]: row for row in loop["risk_flag_stats"]}
    assert risk_rows["大宗折价"]["window_stats"]["T+1"]["sample_count"] == 3
    assert risk_rows["大宗折价"]["window_stats"]["T+1"]["negative_rate"] == 1.0
    assert risk_rows["大宗折价"]["window_stats"]["T+1"]["review_rate"] == 1.0

    buckets = {row["key"]: row for row in loop["score_bucket_performance"]}
    assert buckets["60-75"]["window_stats"]["T+10"]["sample_count"] == 3
    assert buckets["40-60"]["window_stats"]["T+1"]["avg_return_pct"] == -3.0

    summary = loop["learning_summary"]
    assert summary["sample_count"] == 6
    assert summary["best_positive_factors"][0]["key"] == "高ROE"
    assert summary["worst_risk_flags"][0]["key"] == "大宗折价"
    assert all(item["auto_apply"] is False for item in summary["recommendations_for_weights"])


def test_factor_learning_loop_marks_small_samples_without_strong_conclusion():
    records = [
        _rec("600001", _snapshot(), [_outcome("T+1", 8.0)], tags=["单样本强势"], risks=["小样本风险"]),
    ]

    loop = decision_ledger.build_factor_learning_loop(records)

    tag = next(row for row in loop["factor_tag_stats"] if row["key"] == "单样本强势")
    assert tag["window_stats"]["T+1"]["sample_too_small"] is True
    summary = loop["learning_summary"]
    assert summary["best_positive_factors"] == []
    assert summary["noisy_factors"][0]["reason"] == "sample_too_small"
    assert summary["recommendations_for_weights"][0]["suggested_action"] in {
        "wait_more_samples",
        "hold_weight_wait_more_samples",
    }


def test_factor_snapshot_for_item_prefers_captured_candidate_snapshot():
    item = {
        "key": "screening:600519",
        "tushare_factors": {
            "tushare_score": 72.0,
            "data_completeness": 0.9,
            "factor_tags": ["高ROE"],
            "risk_flags": ["大宗折价"],
            "tushare_score_breakdown": {"quality": {"score": 90}},
            "factor_snapshot": _snapshot(),
            "trade_date_used": "2026-05-29",
            "risk_level": "degrade",
            "degrade_reason": "大宗折价触发降级",
        },
    }
    snap = decision_ledger._factor_snapshot_for_item(item, "2026-05-29")
    assert snap["tushare_score"] == 72.0
    assert snap["tushare_score_breakdown"]["quality"]["score"] == 90
    assert snap["risk_level"] == "degrade"
    assert snap["degrade_reason"] == "大宗折价触发降级"
    assert snap["factor_snapshot"]["fundamentals"]["roe"] == 18.0


def test_factor_snapshot_for_item_recomputes_when_only_factor_summary_present(monkeypatch):
    def build_factor_snapshot(code, trade_date):
        assert code == "600519"
        assert trade_date == "2026-05-29"
        return {
            "tushare_score": 61.0,
            "factor_tags": ["补算"],
            "risk_flags": [],
            "factor_snapshot": _snapshot(pe=18.0),
            "trade_date_used": trade_date,
        }

    screener_pkg = types.ModuleType("screener")
    factors_mod = types.ModuleType("screener.tushare_factors")
    factors_mod.build_factor_snapshot = build_factor_snapshot
    monkeypatch.setitem(sys.modules, "screener", screener_pkg)
    monkeypatch.setitem(sys.modules, "screener.tushare_factors", factors_mod)

    item = {"key": "screening:600519", "tushare_score": 72.0, "factor_tags": ["高ROE"]}

    snap = decision_ledger._factor_snapshot_for_item(item, "2026-05-29")

    assert snap["tushare_score"] == 61.0
    assert snap["factor_snapshot"]["valuation"]["pe_ttm"] == 18.0
