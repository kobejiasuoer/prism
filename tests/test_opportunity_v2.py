from __future__ import annotations

import json

from screener.opportunity_v2 import (
    ACTION_ORDER,
    apply_v2_to_shortlist,
    build_baseline_judgment,
    tracking_records,
    validate_ai_judgment,
)


def _candidate(**overrides):
    item = {
        "code": "600001",
        "name": "样本股份",
        "themes": ["AI"],
        "setup_type": "pullback_continuation",
        "setup_label": "回踩承接",
        "entry_reason": "主线回踩后资金重新转正",
        "watch_condition": "站回 12.30 且分时承接不破",
        "main_risk": "跌破 11.80 或资金转负",
        "entry_plan": {
            "action": "触发后小仓位试错",
            "trigger": "站回 12.30 且资金不转负",
            "invalidate": "跌破 11.80 取消",
            "sizing": "0.3 成以内",
        },
        "amount_yi": 22.0,
        "change_pct": 2.6,
        "turnover": 3.2,
        "capital_flow": {"today_yi": 1.8, "trend": "今日转正"},
        "execution_quality": {"score": 8, "label": "承接较好", "warnings": []},
        "consistency": {"score": 5, "label": "跨策略一致"},
        "approved_hits": 2,
    }
    item.update(overrides)
    return item


def _market_regime(**gate_overrides):
    gate = {
        "status": "on",
        "summary": "进攻阀门放开",
        "position_cap": "0.5成",
        "allow_new_positions": True,
    }
    gate.update(gate_overrides)
    return {
        "score": 7.2,
        "metrics": {"positive_ratio": 0.68},
        "execution_gate": gate,
    }


def _market_themes():
    return {
        "themes": [
            {
                "theme": "AI",
                "persistence": {
                    "label": "持续增强",
                    "score": 4,
                    "summary": "AI 主线仍在增强",
                },
            }
        ]
    }


def test_baseline_generates_structured_opportunity_judgment() -> None:
    judgment = build_baseline_judgment(
        _candidate(),
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        rules={"mode": "assist"},
    )

    assert judgment["schema_version"] == "opportunity_v2.1"
    assert judgment["judge_source"] == "deterministic_baseline"
    assert judgment["market_phase"]["value"] in {"risk_on", "selective_risk_on"}
    assert judgment["theme_phase"]["value"] == "mainline_confirmed"
    assert judgment["stock_role"]["value"] == "acceptance_candidate"
    assert judgment["playbook"]["value"] == "pullback_acceptance"
    assert judgment["thesis"]
    assert judgment["why_now"]
    assert judgment["invalidation"]
    assert judgment["suggested_action"] in ACTION_ORDER
    assert 0 <= judgment["confidence"] <= 1
    assert judgment["evidence"]


def test_hard_gate_caps_structural_opportunity_without_removing_judgment() -> None:
    judgment = build_baseline_judgment(
        _candidate(),
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        context={"readiness_mode": "blocked", "real_trade_allowed": False},
    )

    assert judgment["hard_gate"]["maximum_allowed_action"] == "observe"
    assert judgment["suggested_action"] == "observe"
    assert judgment["desired_action"] in ACTION_ORDER
    assert "readiness 未就绪" in "；".join(judgment["hard_gate"]["block_reasons"])
    assert judgment["thesis"]


def test_ai_judgment_cannot_exceed_hard_gate_cap() -> None:
    baseline = build_baseline_judgment(
        _candidate(),
        market_regime=_market_regime(status="off", summary="进攻阀门关闭"),
        market_themes=_market_themes(),
    )
    assert baseline["hard_gate"]["maximum_allowed_action"] == "shadow"

    refined = validate_ai_judgment(
        {
            "suggested_action": "actionable",
            "confidence": 0.99,
            "thesis": "AI 认为结构很强",
        },
        baseline,
    )

    assert refined["judge_source"] == "ai_judge"
    assert refined["desired_action"] == "actionable"
    assert refined["suggested_action"] == "shadow"
    assert refined["action_label"] == "影子跟踪"
    assert refined["ai_summary"]["status"] == "used"
    assert refined["ai_delta"]["changed"] is True
    assert "thesis" in refined["ai_delta"]["changed_fields"]


def test_ai_fallback_summary_is_explicit_when_provider_missing(monkeypatch) -> None:
    for key in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "PRISM_V2_AI_API_KEY",
        "PRISM_V2_AI_BASE_URL",
        "PRISM_V2_AI_MODEL",
        "PRISM_V2_AI_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)
    rows = [_candidate()]

    summary = apply_v2_to_shortlist(
        rows,
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        rules={"mode": "assist", "ai": {"enabled": True, "max_calls": 1}},
    )

    judgment = rows[0]["opportunity_v2"]
    assert summary["judge_sources"]["deterministic_baseline"] == 1
    assert judgment["ai_status"] == "not_configured"
    assert judgment["ai_summary"]["fallback_used"] is True
    assert "deterministic baseline" in judgment["ai_summary"]["detail"]


def test_active_mode_cold_start_downgrades_to_assist_and_tightens_thresholds(tmp_path) -> None:
    calibration_path = tmp_path / "missing_calibration.json"
    rows = [_candidate()]

    summary = apply_v2_to_shortlist(
        rows,
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        rules={
            "mode": "active",
            "ai": {"enabled": False},
            "calibration": {"path": str(calibration_path)},
        },
    )

    judgment = rows[0]["opportunity_v2"]
    assert summary["mode_requested"] == "active"
    assert summary["mode_effective"] == "assist"
    assert summary["mode_guard"]["active_allowed"] is False
    assert summary["calibration"]["sample_stage"] == "cold_start"
    assert summary["calibration"]["threshold_adjustments"]["trial"] > 0
    assert summary["calibration"]["threshold_adjustments"]["actionable"] > 0
    assert judgment["mode_requested"] == "active"
    assert judgment["mode_effective"] == "assist"
    assert judgment["calibration"]["effective_thresholds"]["actionable"] > 0.80
    assert judgment["desired_action"] != "actionable"
    assert judgment["suggested_action"] != "actionable"


def test_weak_playbook_calibration_caps_structural_action(tmp_path) -> None:
    calibration_path = tmp_path / "opportunity_v2_calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "schema_version": "opportunity_v2_calibration.1",
                "sample_stage": "needs_recalibration",
                "sample_count": 4,
                "mature_samples": 4,
                "active_allowed": False,
                "guard_reason": "weak outcomes",
                "threshold_adjustments": {},
                "playbooks": {
                    "pullback_acceptance": {
                        "sample_count": 4,
                        "mature_samples": 4,
                        "positive_rate": 0.25,
                        "review_rate": 0.75,
                        "confidence_adjustment": -0.06,
                        "action_cap": "shadow",
                        "reason": "playbook weak",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    judgment = build_baseline_judgment(
        _candidate(),
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        rules={
            "mode": "assist",
            "ai": {"enabled": False},
            "calibration": {"path": str(calibration_path)},
        },
    )

    assert judgment["playbook"]["value"] == "pullback_acceptance"
    assert judgment["desired_action"] == "shadow"
    assert judgment["suggested_action"] == "shadow"
    assert judgment["confidence_components"]["calibration_adjustment"] < 0
    assert judgment["calibration"]["playbook_adjustment"]["action_cap"] == "shadow"
    assert "playbook weak" in judgment["upgrade_reason"] or "playbook weak" in str(judgment["evidence"])


def test_ai_judgment_cannot_override_calibrated_playbook_cap(tmp_path) -> None:
    calibration_path = tmp_path / "opportunity_v2_calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "schema_version": "opportunity_v2_calibration.1",
                "sample_stage": "needs_recalibration",
                "sample_count": 4,
                "mature_samples": 4,
                "active_allowed": False,
                "guard_reason": "weak outcomes",
                "threshold_adjustments": {},
                "playbooks": {
                    "pullback_acceptance": {
                        "mature_samples": 4,
                        "positive_rate": 0.25,
                        "review_rate": 0.75,
                        "confidence_adjustment": -0.06,
                        "action_cap": "shadow",
                        "reason": "playbook weak",
                    },
                    "leader_continuation": {
                        "mature_samples": 4,
                        "positive_rate": 0.75,
                        "review_rate": 0.0,
                        "confidence_adjustment": 0.0,
                        "action_cap": "",
                        "reason": "playbook ok",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rules = {
        "mode": "assist",
        "ai": {"enabled": False},
        "calibration": {"path": str(calibration_path)},
    }
    baseline = build_baseline_judgment(
        _candidate(),
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        rules=rules,
    )

    refined = validate_ai_judgment(
        {
            "suggested_action": "actionable",
            "confidence": 0.99,
            "thesis": "AI 认为可以直接买",
            "opportunity_type": "leader_continuation",
            "playbook": {
                "value": "leader_continuation",
                "opportunity_type": "leader_continuation",
            },
        },
        baseline,
        rules=rules,
    )

    assert refined["judge_source"] == "ai_judge"
    assert refined["desired_action"] == "shadow"
    assert refined["suggested_action"] == "shadow"
    assert refined["action_label"] == "影子跟踪"


def test_tracking_records_only_include_shadow_trial_actionable() -> None:
    shadow = _candidate(code="600001", name="影子样本")
    shadow["opportunity_v2"] = build_baseline_judgment(
        shadow,
        market_regime=_market_regime(status="off", summary="阀门关闭"),
        market_themes=_market_themes(),
    )
    observe = _candidate(code="600002", name="观察样本")
    observe["opportunity_v2"] = build_baseline_judgment(
        observe,
        market_regime=_market_regime(),
        market_themes=_market_themes(),
        context={"readiness_mode": "blocked"},
    )

    records = tracking_records(
        [shadow, observe],
        trade_date="2026-06-05",
        source_artifact="/tmp/screening.json",
    )

    assert [record["code"] for record in records] == ["600001"]
    assert records[0]["suggested_action"] == "shadow"
    assert records[0]["thesis"]
    assert records[0]["trigger"]
    assert records[0]["invalidation"]
    assert records[0]["source_artifact"] == "/tmp/screening.json"
