# apps/control-panel/tests/test_opportunity_card_factors.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import dashboard_data


def test_screening_card_includes_factor_fields():
    candidate = {
        "code": "600519", "name": "贵州茅台", "screening_status": "caution",
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": ["短线脉冲风险(龙虎榜机构净买)"],
        "factor_explanation": {"entry_reason": "综合因子评分 72"},
        "factor_snapshot": {"valuation": {"pe_ttm": 20.0}},
        "trade_date_used": "2026-05-29",
        "tushare_positive_adjustment": 2.5,
        "tushare_risk_penalty": 1.5,
        "tushare_priority_adjustment": 1.0,
    }
    card = dashboard_data.build_screening_candidate_card(candidate)
    assert card["tushare_score"] == 72.0
    assert card["factor_tags"] == ["高ROE"]
    assert card["factor_risk_flags"] == ["短线脉冲风险(龙虎榜机构净买)"]
    assert card["factor_explanation"]["entry_reason"].startswith("综合因子评分")
    assert card["factor_snapshot"]["valuation"]["pe_ttm"] == 20.0
    assert card["trade_date_used"] == "2026-05-29"
    assert card["tushare_priority_adjustment"] == 1.0


def test_confirmation_card_includes_factor_fields():
    candidate = {
        "code": "600519", "name": "贵州茅台", "status": "caution",
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": ["短线脉冲风险(龙虎榜机构净买)"],
        "factor_explanation": {"entry_reason": "综合因子评分 72"},
        "factor_snapshot": {"valuation": {"pe_ttm": 20.0}},
    }
    card = dashboard_data.build_confirmation_candidate_card(candidate)
    assert card["tushare_score"] == 72.0
    assert card["factor_tags"] == ["高ROE"]
    assert card["factor_risk_flags"] == ["短线脉冲风险(龙虎榜机构净买)"]
    assert card["factor_explanation"]["entry_reason"].startswith("综合因子评分")
    assert card["factor_snapshot"]["valuation"]["pe_ttm"] == 20.0


def test_public_opportunity_card_drops_raw_factor_bundle_but_keeps_display_summary():
    card = {
        "code": "600519",
        "name": "贵州茅台",
        "status": "只观察",
        "tone": "watch",
        "detail": "等待更多确认",
        "position_guidance": "0.3 成",
        "upgrade_condition": "放量突破",
        "avoid_condition": "缩量回落",
        "invalid_condition": "跌破支撑",
        "entry_plan": {
            "action": "只观察",
            "sizing": "0.3 成",
            "trigger": "放量突破",
            "avoid": "缩量回落",
            "invalidate": "跌破支撑",
            "levels": {"support": 100},
        },
        "tushare_score": 72.0,
        "factor_tags": ["高ROE", "北向偏强", "回购支撑", "热门概念"],
        "factor_risk_flags": ["短线脉冲风险", "审计异常", "两融过热", "回撤偏大"],
        "factor_explanation": {"entry_reason": "综合因子评分 72", "debug": "raw details"},
        "factor_snapshot": {"valuation": {"pe_ttm": 20.0}},
        "tushare_score_breakdown": {"quality": {"score": 90}},
        "risk_items": [{"label": "质押", "detail": "raw"}],
        "risk_evidence_refs": [{"title": "raw"}],
        "risk_source_cards": [{"label": "raw"}],
        "opportunity_v2": {"suggested_action": "trial", "raw": {"large": True}},
        "suggested_action": "trial",
        "suggested_action_label": "试错待触发",
        "missing_confirmation": ["承接", "资金不能转负", "站回 210 上方"],
        "ai_status": "used",
        "ai_status_label": "AI Judge",
        "ai_summary": {"status": "used", "label": "AI Judge", "detail": "参与判读", "raw": {"large": True}},
        "ai_delta": {"changed_fields": ["a", "b", "c", "d", "e"], "raw": {"large": True}},
        "v2_playbook_adjustment": {"action_cap": "trial", "confidence_adjustment": -0.1, "extra": "raw"},
    }

    public = dashboard_data.public_opportunity_card_payload(card)

    assert public["code"] == "600519"
    assert public["suggested_action"] == "trial"
    assert "entry_plan" not in public
    assert public["position_guidance"] == "0.3 成"
    assert public["upgrade_condition"] == "放量突破"
    assert public["avoid_condition"] == "缩量回落"
    assert public["invalid_condition"] == "跌破支撑"
    assert public["factor_tags"] == ["高ROE", "北向偏强"]
    assert public["factor_risk_flags"] == ["短线脉冲风险", "审计异常"]
    assert public["missing_confirmation"] == ["承接", "资金不能转负"]
    assert public["ai_status"] == "used"
    assert public["ai_status_label"] == "AI Judge"
    for key in (
        "ai_delta",
        "ai_summary",
        "factor_snapshot",
        "factor_explanation",
        "tushare_score_breakdown",
        "risk_items",
        "risk_evidence_refs",
        "risk_source_cards",
        "opportunity_v2",
        "v2_playbook_adjustment",
    ):
        assert key not in public


def test_public_opportunity_card_deduplicates_repeated_display_text():
    card = {
        "code": "600519",
        "name": "贵州茅台",
        "detail": "结构假设等待确认",
        "thesis": "结构假设等待确认",
        "foot": "硬闸门不放行",
        "hard_gate_block_reason": "硬闸门不放行",
        "risk_tags": ["硬闸门不放行", "拥挤风险暂可控"],
    }

    public = dashboard_data.public_opportunity_card_payload(card)

    assert public["thesis"] == "结构假设等待确认"
    assert "detail" not in public
    assert public["hard_gate_block_reason"] == "硬闸门不放行"
    assert "foot" not in public
    assert public["risk_tags"] == ["拥挤风险暂可控"]


def test_public_opportunity_card_drops_repeated_v2_diagnostics():
    card = {
        "code": "600519",
        "name": "贵州茅台",
        "suggested_action": "trial",
        "suggested_action_label": "试错待触发",
        "v2_mode_requested": "active",
        "v2_mode_effective": "shadow",
        "v2_active_allowed": False,
        "v2_calibration_stage": "cold_start",
        "v2_calibration_guard_reason": "V2 尚无可用 outcome 样本，active 禁止，trial/actionable 阈值按冷启动收紧。",
        "v2_calibration_mature_samples": 0,
        "upgrade_reason": "结构假设成立但还不够买，只适合影子跟踪验证。",
        "degrade_reason": "审计意见出现非标/强调等异常表述，候选降级为谨慎观察。",
        "risk_tags": ["审计意见出现非标/强调等异常表述，候选降级为谨慎观察。", "拥挤风险"],
    }

    public = dashboard_data.public_opportunity_card_payload(card)

    assert public["suggested_action"] == "trial"
    assert public["v2_calibration_stage"] == "cold_start"
    assert public["v2_active_allowed"] is False
    assert "v2_mode_requested" not in public
    assert "v2_mode_effective" not in public
    assert "v2_calibration_guard_reason" not in public
    assert "upgrade_reason" not in public
    assert public["risk_tags"] == ["拥挤风险"]


def test_public_lifecycle_card_keeps_sidebar_fields_only():
    card = {
        "code": "600519",
        "name": "贵州茅台",
        "status": "非一日脉冲",
        "tone": "info",
        "detail": "连续两轮仍在候选池，先按延续观察处理。",
        "foot": "非一日脉冲",
        "observation_instruction": "贵州茅台：非一日脉冲：只作为跨天追踪，不直接执行；确认：明天继续留在 shortlist。",
        "upgrade_condition": "明天继续留在 shortlist。",
        "invalid_condition": "后续掉出 shortlist。",
        "risk_tags": ["连续观察"],
        "priority_label": "非一日脉冲",
        "persistence_label": "非一日脉冲",
        "action_key": "lifecycle:continued:600519",
        "score": 88,
        "detail_url": "/stock/600519",
    }

    public = dashboard_data.public_lifecycle_card_payload(card)

    assert public == {
        "code": "600519",
        "name": "贵州茅台",
        "status": "非一日脉冲",
        "tone": "info",
        "persistence_label": "非一日脉冲",
        "priority_label": "非一日脉冲",
        "detail_url": "/stock/600519",
        "detail": "连续两轮仍在候选池，先按延续观察处理。",
    }


def test_public_learning_memory_drops_duplicate_hint_copy():
    memory = {
        "key": "watchlist|observe",
        "title": "历史提醒",
        "summary": "同一段复盘提醒",
        "learning_hint": "同一段复盘提醒",
        "scope_label": "模式记忆",
        "primary_cause_label": "判断过严",
        "secondary_cause_labels": ["量能判断偏保守", "环境阀门过严", "主力资金过滤过严", "额外归因"],
        "tone": "warning",
        "sample_count": 2,
        "evidence_strength_label": "待验证模式",
    }

    public = dashboard_data.public_learning_memory_payload(memory)

    assert public["summary"] == "同一段复盘提醒"
    assert "learning_hint" not in public
    assert public["secondary_cause_labels"] == ["量能判断偏保守", "环境阀门过严", "主力资金过滤过严"]


def test_today_screening_task_carries_raw_factor_snapshot_for_ledger():
    candidate = {
        "code": "600519", "name": "贵州茅台", "screening_status": "caution",
        "tushare_score": 72.0,
        "factor_tags": ["高ROE"],
        "risk_flags": ["大宗折价"],
        "factor_snapshot": {"event_risks": {"pledge_ratio": 40.0}},
        "trade_date_used": "2026-05-29",
        "tushare_priority_adjustment": -1.5,
    }
    task = dashboard_data.build_today_screening_task_item(candidate, source="观察池观察")
    assert task["tushare_score"] == 72.0
    assert task["factor_risk_flags"] == ["大宗折价"]
    assert task["factor_snapshot"]["event_risks"]["pledge_ratio"] == 40.0
    assert task["trade_date_used"] == "2026-05-29"
    assert task["tushare_priority_adjustment"] == -1.5


def test_candidate_detail_carries_full_factor_bundle(monkeypatch):
    # build_candidate_detail_view sources candidate via find_candidate_detail; stub it.
    # dashboard_data imports find_candidate_detail by name, so patch it on dashboard_data.
    monkeypatch.setattr(dashboard_data, "find_candidate_detail", lambda code, trade_date=None: {
        "code": "600519", "name": "贵州茅台",
        "tushare_factors": {"tushare_score": 72.0, "tushare_score_breakdown": {"quality": {"score": 90}},
                            "factor_tags": ["高ROE"], "risk_flags": [], "explanation": {"entry_reason": "x"}},
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": [],
        "factor_explanation": {"entry_reason": "x"},
    })
    view = dashboard_data.build_candidate_detail_view("sh600519")
    assert view["tushare_factors"]["tushare_score"] == 72.0
    assert view["tushare_score"] == 72.0
