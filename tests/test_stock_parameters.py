import json
import importlib.util
from pathlib import Path


def test_stock_parameter_schema_exists_and_covers_core_layers():
    schema_path = Path("data/schemas/stock-parameters.json")
    config_path = Path("data/config/stock-parameters.json")

    assert schema_path.exists()
    assert config_path.exists()

    schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    layer_names = {item["name"] for item in schema_payload["layers"]}
    statuses = {item["status"] for item in schema_payload["parameters"]}
    threshold_sets = config_payload["threshold_sets"]

    assert {
        "market",
        "theme",
        "stock_core",
        "setup",
        "execution",
        "governance",
    }.issubset(layer_names)
    assert {"retain", "recalibrate", "remove", "add"}.issubset(statuses)
    assert {
        "execution_gate",
        "final_score_weights",
        "setup_thresholds",
        "capital_score",
        "execution_quality",
        "ai_screening_evaluation",
        "attack_profile",
        "trade_note",
        "setup_plan",
        "entry_output_defaults",
        "emotion_score",
        "fundamental_score",
        "missing_data_penalties",
        "overheat_penalty",
    }.issubset(threshold_sets)
    assert schema_payload["threshold_sets"] == threshold_sets


def test_scan_uses_shared_parameter_helpers():
    import screener.scan as scan
    import screener.parameters as parameters

    assert parameters.PARAMETER_CONFIG_PATH.exists()
    assert scan.build_execution_gate is parameters.build_execution_gate
    assert scan.compute_final_score is parameters.compute_final_score


def test_ai_screening_execution_gate_matches_shared_logic():
    import screener.ai_screening as ai_screening
    import screener.parameters as parameters

    regime = {
        "score": 2,
        "metrics": {
            "positive_ratio": 0.48,
            "avg_change_pct": 0.10,
            "avg_turnover": 2.10,
            "strong_ratio": 0.12,
        },
        "candidate_view": {
            "score": 6,
            "metrics": {
                "strong_ratio": 0.20,
            },
        },
    }

    shared_gate = parameters.build_execution_gate(regime, regime["candidate_view"])
    ai_gate = ai_screening.execution_gate_of(regime)

    assert ai_gate["status"] == shared_gate["status"]
    assert ai_gate["position_cap"] == shared_gate["position_cap"]
    assert ai_gate["allowed_setups"] == shared_gate["allowed_setups"]


def test_setup_thresholds_are_centralized():
    import screener.parameters as parameters

    assert parameters.SETUP_THRESHOLDS["leader_continuation"]["min_change_pct"] == 4.5
    assert parameters.SETUP_THRESHOLDS["leader_continuation"]["min_amount_yi"] == 15
    assert parameters.SETUP_THRESHOLDS["low_reversal"]["max_position_20d"] == 0.38
    assert parameters.SETUP_THRESHOLDS["breakout_follow"]["min_position_20d"] == 0.72


def test_batch2_screener_threshold_maps_are_centralized():
    import screener.ai_screening as ai_screening
    import screener.parameters as parameters
    import screener.scan as scan

    assert scan.CAPITAL_SCORE_THRESHOLDS is parameters.CAPITAL_SCORE_THRESHOLDS
    assert ai_screening.EXECUTION_QUALITY_RULES is parameters.EXECUTION_QUALITY_RULES
    assert ai_screening.AI_SCREENING_EVALUATION_RULES is parameters.AI_SCREENING_EVALUATION_RULES

    assert parameters.CAPITAL_SCORE_THRESHOLDS["today_flow_wan"][0]["above"] == 5000
    assert parameters.EXECUTION_QUALITY_RULES["amount_yi"]["high"]["at_least"] == 12
    assert parameters.AI_SCREENING_EVALUATION_RULES["approved_downgrade"]["at_most"] == -2


def test_batch3_output_rules_are_centralized():
    import screener.ai_screening as ai_screening
    import screener.parameters as parameters
    import screener.scan as scan

    assert scan.ATTACK_PROFILE_RULES is parameters.ATTACK_PROFILE_RULES
    assert scan.TRADE_NOTE_RULES is parameters.TRADE_NOTE_RULES
    assert ai_screening.SETUP_PLAN_RULES is parameters.SETUP_PLAN_RULES
    assert ai_screening.ENTRY_OUTPUT_DEFAULTS is parameters.ENTRY_OUTPUT_DEFAULTS

    assert parameters.ATTACK_PROFILE_RULES["status"]["exclude_at_or_below"] == -7
    assert parameters.TRADE_NOTE_RULES["watch"]["trend_breakout"]["items"][0] == "明天别高开低走"
    assert parameters.SETUP_PLAN_RULES["modifiers"]["trend_setup_overheat"]["overheat_penalty_at_least"] == 4


def test_batch4_stage2_score_rules_are_centralized():
    import screener.parameters as parameters
    import screener.scan as scan

    assert scan.EMOTION_SCORE_RULES is parameters.EMOTION_SCORE_RULES
    assert scan.FUNDAMENTAL_SCORE_RULES is parameters.FUNDAMENTAL_SCORE_RULES
    assert scan.MISSING_DATA_PENALTIES is parameters.MISSING_DATA_PENALTIES
    assert scan.OVERHEAT_PENALTY_RULES is parameters.OVERHEAT_PENALTY_RULES
    assert scan.clamp_fundamental_score is parameters.clamp_fundamental_score
    assert scan.compute_emotion_score is parameters.compute_emotion_score
    assert scan.compute_missing_cap_penalty is parameters.compute_missing_cap_penalty
    assert scan.compute_overheat_penalty is parameters.compute_overheat_penalty

    assert parameters.EMOTION_SCORE_RULES["cap"] == 20
    assert parameters.FUNDAMENTAL_SCORE_RULES["max"] == 12
    assert parameters.FUNDAMENTAL_SCORE_RULES["min"] == -8
    assert parameters.MISSING_DATA_PENALTIES["capital_flow_missing"] == 4
    assert parameters.OVERHEAT_PENALTY_RULES["extension_risk"][0]["change_pct_at_least"] == 9.8


def test_capital_score_thresholds_drive_scan_scoring():
    import screener.scan as scan

    score, signals = scan.calc_cap_score(
        [
            {"main_net": 600.0},
            {"main_net": 800.0},
            {"main_net": 2500.0},
        ]
    )

    assert score == 24
    assert signals == ["主力流入0.25亿", "连续3日流入"]


def test_ai_screening_quality_and_consistency_labels_follow_shared_thresholds():
    import screener.ai_screening as ai_screening

    stock = {
        "code": "000001",
        "name": "测试股份",
        "amount_yi": 10.0,
        "change_pct": 4.0,
        "theme": "机器人",
        "fundamentals": {"pe_ttm": 40.0, "roe": 10.0},
        "capital_flow": {"today_yi": 3.2, "trend": "主力净流入"},
        "trade_note": {"watch_condition": "回踩不破 5 日线"},
        "attack_profile": {"status": "keep"},
        "overheat_penalty": 0.0,
        "has_capital_flow": True,
        "signals": [],
        "notice_risk_tags": [],
    }
    market_themes = {
        "themes": [
            {"theme": "机器人", "persistence": {"label": "持续增强", "score": 20}},
            {"theme": "算力", "persistence": {"label": "强势延续", "score": 12}},
        ]
    }
    market_regime = {"score": 7.0, "execution_gate": {"status": "on"}}

    quality = ai_screening.build_execution_quality(
        stock,
        decision={"consistency_score": 5},
        setup_plan={"setup_type": "pullback_continuation"},
        market_regime=market_regime,
        market_themes=market_themes,
    )
    decision = ai_screening.evaluate_stock(
        stock,
        market_regime=market_regime,
        market_themes=market_themes,
    )

    assert quality["score"] == 9
    assert quality["label"] == "高执行质量"
    assert decision["status"] == "approved"
    assert decision["consistency_score"] == 9
    assert decision["consistency_label"] == "高一致性"


def test_attack_profile_and_trade_note_follow_shared_rules():
    import screener.scan as scan

    stock = {
        "name": "测试芯片",
        "turnover": 4.5,
        "change_pct": 5.2,
        "position_20d": 0.8,
        "amount": 35e8,
        "flows": [{"main_net": 1200.0}, {"main_net": 2200.0}],
        "fundamentals": {"industry": "半导体", "concept": "算力", "pe_ttm": 40.0},
    }

    attack = scan.classify_attack_profile(stock)
    trade_note = scan.build_trade_note(stock)

    assert attack["status"] == "keep"
    assert attack["bias_score"] == 22
    assert attack["reason"] == "趋势、资金和弹性较匹配，适合作为进攻型候选。"
    assert attack["tags"][:5] == ["偏好行业:半导体", "高换手", "涨幅强", "资金配合", "连续2日流入"]
    assert trade_note["entry_reason"] == "趋势突破+资金配合 + 换手充分"
    assert trade_note["main_risk"] == "留意次日承接强度"
    assert trade_note["watch_condition"] == "明天别高开低走；量能别明显萎缩；主力资金别转负"


def test_setup_plan_copy_follows_shared_templates():
    import screener.ai_screening as ai_screening

    stock = {
        "price": 10.0,
        "theme": "机器人",
        "change_pct": 5.0,
        "amount_yi": 20.0,
        "overheat_penalty": 5.0,
        "signals": [],
        "capital_flow": {"today_yi": 2.0, "trend": "主力净流入"},
        "attack_profile": {"status": "keep"},
        "technical_state": {
            "ma5": 10.0,
            "ma10": 9.8,
            "ma20": 9.5,
            "high20": 10.2,
            "low20": 8.8,
            "position_20d": 0.8,
        },
    }
    market_themes = {
        "themes": [
            {"theme": "机器人", "persistence": {"label": "持续增强", "score": 18}},
            {"theme": "算力", "persistence": {"label": "强势延续", "score": 12}},
        ]
    }

    setup = ai_screening.build_setup_plan(
        stock,
        decision={"consistency_score": 0},
        market_themes=market_themes,
    )

    assert setup["setup_type"] == "leader_continuation"
    assert setup["setup_label"] == "热点龙头"
    assert setup["setup_summary"] == "主线强票，优先看分时承接和二次上冲，不做情绪顶接力。 当前一致性一般，执行上要更保守。"
    assert setup["entry_plan"]["trigger"] == "优先看 10.00 一带承接，或再站稳 10.20 后轻仓试错。"
    assert setup["entry_plan"]["avoid"] == "情绪偏热，第一波拉高不追，优先等换手后的二次机会。"
    assert setup["entry_plan"]["invalidate"] == "跌破 9.80 或主力转负就取消。"


def test_stage2_emotion_and_overheat_helpers_follow_shared_rules():
    import screener.parameters as parameters

    emotion_score = parameters.compute_emotion_score(
        change_pct=7.2,
        amount=16e8,
        turnover=8.1,
    )
    overheat_penalty, overheat_tags = parameters.compute_overheat_penalty(
        position_20d=0.86,
        change_pct=9.9,
        turnover=8.2,
    )

    assert emotion_score == 20
    assert parameters.clamp_fundamental_score(20) == 12
    assert parameters.clamp_fundamental_score(-20) == -8
    assert parameters.clamp_fundamental_score(6.5) == 6.5
    assert parameters.compute_missing_cap_penalty(has_capital_flow=False) == 4
    assert parameters.compute_missing_cap_penalty(has_capital_flow=True) == 0
    assert overheat_penalty == 12
    assert overheat_tags == ["高位高潮", "爆量过热", "涨停退潮风险"]


def load_watchlist_fetch_module():
    target = Path("stock-analyzer/scripts/fetch.py").resolve()
    spec = importlib.util.spec_from_file_location("prism_watchlist_fetch", target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_watchlist_parameters_are_centralized():
    import stock_parameters as parameters

    assert parameters.PARAMETER_CONFIG_PATH.exists()
    assert parameters.WATCHLIST_RULE_THRESHOLDS["roe"]["weak_below"] == 8
    assert parameters.WATCHLIST_RULE_THRESHOLDS["pe"]["high_above"] == 50
    assert parameters.WATCHLIST_RULE_THRESHOLDS["action"]["avoid_severe_negatives_at"] == 5
    assert parameters.FLOW_CONFIDENCE_RULES["stale_intraday_penalty"] == 1


def test_watchlist_stale_flow_is_penalized_in_rule_snapshot():
    fetch = load_watchlist_fetch_module()

    snapshot = fetch.build_rule_snapshot(
        stock={"code": "000001", "name": "测试股份"},
        realtime={"price": 10.0, "change_pct": 2.0},
        news=[],
        announcements=[{"title": "公司中标重大订单"}],
        tech_indicators={
            "backtest_bias": "bull",
            "price_position": {"pct_from_high": -5.0, "pct_from_low": 10.0},
            "ma": {"MA20": 9.8, "MA60": 9.4},
        },
        capital_flow={
            "intraday_unconfirmed": True,
            "as_of_date": "2026-04-22",
            "signal": "历史参考（截至2026-04-22）",
        },
        fundamentals={"roe": 12.0, "pe": 15.0, "pb": 3.0},
        sector_data={"change_pct": 1.0},
    )

    assert snapshot["action"] == "观望"
    assert snapshot["flow_confidence"]["label"] == "历史参考"
    assert snapshot["flow_confidence"]["penalty"] == 1
