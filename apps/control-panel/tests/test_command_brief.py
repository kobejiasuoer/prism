"""Unit tests for the daily command brief aggregator.

Covers mode/permits/position_cap/first_action/forbid_today/reclassify/
judgement_chain/action_lanes/midday_verify/trust derivation rules from
the design at docs/superpowers/specs/2026-05-22-daily-command-brief-design.md.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.command_brief import (  # noqa: E402
    derive_mode,
    derive_permits,
    derive_position_cap,
    derive_first_action,
    derive_forbid_today,
    derive_reclassify_when,
    derive_judgement_chain,
    derive_action_lanes,
    derive_midday_verify,
    derive_trust,
    build_today_command_brief,
)

from fastapi.testclient import TestClient  # noqa: E402

from control_panel.app import app  # noqa: E402


def _readiness(mode: str = "live_ready", **extra) -> dict[str, object]:
    base = {
        "readiness_mode": mode,
        "ready": mode == "live_ready",
        "blockers": [],
        "warnings": [],
        "expected_trade_date": "2026-05-22",
        "data_trade_date": "2026-05-22" if mode != "blocked" else None,
        "source_freshness": [],
        "quality_freshness": [],
        "recommended_tasks": [],
    }
    base.update(extra)
    return base


def _gate(allow: bool = False, label: str = "防守试错", summary: str = "弱环境，先观察") -> dict[str, object]:
    return {
        "allow_new_positions": allow,
        "label": label,
        "position_cap": "0-0.3成" if allow else "0成",
        "summary": summary,
    }


def _confirmation(confirmed: int = 0, fresh: int = 0, downgraded: int = 0) -> dict[str, object]:
    return {
        "confirmed": [{"name": f"C{i}", "code": f"60000{i}"} for i in range(confirmed)],
        "fresh_candidates": [{"name": f"F{i}", "code": f"60010{i}"} for i in range(fresh)],
        "downgraded": [{"name": f"D{i}", "code": f"60020{i}"} for i in range(downgraded)],
        "counts": {
            "confirmed": confirmed,
            "fresh_candidates": fresh,
            "downgraded": downgraded,
        },
        "validation_status": "ok",
        "generated_at": "2026-05-22 12:30:00",
    }


class ModeDerivationTest(unittest.TestCase):
    def test_blocked_readiness_forces_defense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "defense")
        self.assertEqual(mode["label"], "防守")

    def test_shadow_only_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_gate_closed_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=False, label="防守试错"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_limited_label_is_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制进攻"),
            confirmation=_confirmation(confirmed=1),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_live_ready_offense_label_with_confirmed_is_offense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(confirmed=2),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "offense")

    def test_live_ready_offense_label_without_confirmed_stays_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_decision_brief_override_wins(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(),
            confirmation=_confirmation(),
            decision_brief={"summary": {"today_mode": "offense"}},
        )
        self.assertEqual(mode["value"], "offense")
        self.assertIn("brief_override", mode["reasons"])


class PermitsTest(unittest.TestCase):
    def test_blocked_readiness_yields_off_off_none(self) -> None:
        permits = derive_permits(
            readiness=_readiness("blocked", blockers=[{"message": "watchlist 数据偏旧"}]),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "off")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "none")
        self.assertIn("watchlist 数据偏旧", permits["data"]["why"])

    def test_shadow_only_yields_shadow_off_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "shadow")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_limited_label_with_candidates_is_conditional(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制试错"),
            confirmation=_confirmation(confirmed=1, fresh=2),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "limited")
        self.assertEqual(permits["opportunity"]["value"], "conditional")
        self.assertIn("新增", permits["opportunity"]["why"])

    def test_live_ready_offense_label_without_candidates_is_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "on")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_offense_with_candidates_is_actionable(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["opportunity"]["value"], "actionable")

    def test_live_ready_but_not_approvable_is_review_only(self) -> None:
        permits = derive_permits(
            readiness=_readiness(
                "live_ready",
                capabilities={
                    "review": {"granted": True},
                    "approve": {
                        "granted": False,
                        "why_not": [{"message": "正式放行需要正式数据口径通过后再确认。"}],
                    },
                    "trade": {"granted": False},
                },
                trust_level={
                    "level": "observe_only",
                    "blocking_reasons": ["正式数据底座已接入；业务链路仍有观察级降级项。"],
                },
            ),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2, fresh=1),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "review")
        self.assertEqual(permits["data"]["label"], "可观察/复核")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "observe")
        self.assertIn("正式放行", permits["opportunity"]["why"])

    def test_v2_active_downgrade_is_visible_in_opportunity_permit(self) -> None:
        item = {
            "code": "600001",
            "suggested_action": "trial",
            "opportunity_v2": {
                "suggested_action": "trial",
                "desired_action": "trial",
                "mode_requested": "active",
                "mode_effective": "assist",
                "mode_guard": {
                    "requested_mode": "active",
                    "effective_mode": "assist",
                    "active_allowed": False,
                    "sample_stage": "cold_start",
                    "guard_reason": "V2 尚无可用 outcome 样本",
                },
                "calibration": {
                    "sample_stage": "cold_start",
                    "guard_reason": "V2 尚无可用 outcome 样本",
                },
            },
        }

        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            screening_batch={
                "candidates": [item],
                "screening_summary": {"approved_count": 1, "candidate_total": 1},
            },
        )

        self.assertEqual(permits["opportunity"]["value"], "conditional")
        self.assertIn("校准护栏", permits["opportunity"]["why"])
        self.assertIn("V2 尚无可用 outcome 样本", permits["opportunity"]["why"])


class FirstActionTest(unittest.TestCase):
    def test_defense_returns_recover_data_action(self) -> None:
        action = derive_first_action(
            mode_value="defense",
            action_queue={"items": []},
            readiness=_readiness("blocked"),
        )
        self.assertEqual(action["kind"], "recover_data")
        self.assertEqual(action["url"], "/settings")

    def test_takes_first_pending_stock_action(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={
                "items": [
                    {
                        "key": "watchlist:600519",
                        "title": "600519 茅台",
                        "detail": "止损 1620 已破",
                        "tone": "sell",
                        "url": "/stock/600519",
                        "decision": {"value": "pending", "label": "待处理", "tone": "sell"},
                        "display_state": {"value": "pending", "label": "待处理", "tone": "sell"},
                    }
                ]
            },
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "stock")
        self.assertEqual(action["url"], "/stock/600519")
        self.assertIn("600519", action["title"])

    def test_observe_with_no_pending_falls_back_to_portfolio(self) -> None:
        action = derive_first_action(
            mode_value="observe",
            action_queue={"items": []},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "system")
        self.assertEqual(action["url"], "/portfolio")

    def test_review_only_readiness_suppresses_stock_first_action(self) -> None:
        action = derive_first_action(
            mode_value="observe",
            action_queue={
                "items": [
                    {
                        "key": "watchlist:600690",
                        "title": "海尔智家 600690",
                        "detail": "ROE偏弱",
                        "tone": "watch",
                        "url": "/stock/600690",
                        "decision": {"value": "pending"},
                    }
                ]
            },
            readiness=_readiness(
                "live_ready",
                capabilities={
                    "approve": {
                        "granted": False,
                        "why_not": [{"message": "正式放行需要正式数据口径通过后再确认。"}],
                    },
                    "trade": {"granted": False},
                },
            ),
        )
        self.assertEqual(action["kind"], "review_only")
        self.assertEqual(action["url"], "#judgement-chain")
        self.assertNotIn("600690", action["title"])
        self.assertIn("正式放行", action["reason"])

    def test_probe_with_no_pending_falls_back_to_judgement_chain(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={"items": []},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "system")
        self.assertEqual(action["url"], "#judgement-chain")
        self.assertIsNone(action["action_key"])


class PositionCapTest(unittest.TestCase):
    def test_takes_gate_position_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="probe",
            gate=_gate(allow=True, label="试错"),
            decision_brief={"summary": {"position_cap": "0-0.3成"}},
        )
        self.assertEqual(cap["value"], "0-0.3成")
        self.assertEqual(cap["raw"], "0-0.3成")

    def test_defense_forces_zero_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="defense",
            gate=_gate(allow=True, label="进攻"),
            decision_brief=None,
        )
        self.assertEqual(cap["value"], "0成")
        self.assertEqual(cap["tone"], "risk")

    def test_gate_zero_position_cap_forces_defense_note(self) -> None:
        cap = derive_position_cap(
            mode_value="observe",
            gate=_gate(allow=False, label="进攻阀门关闭"),
            decision_brief={"summary": {"position_cap": "0-0.3成"}},
        )
        self.assertEqual(cap["value"], "0成")
        self.assertEqual(cap["tone"], "risk")
        self.assertIn("不开新仓", cap["note"])


class ForbidTodayTest(unittest.TestCase):
    def test_defense_injects_no_new_positions(self) -> None:
        forbid = derive_forbid_today(
            mode_value="defense",
            decision_brief=None,
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertTrue(any("不开新仓" in title for title in titles))

    def test_brief_avoid_points_are_included(self) -> None:
        forbid = derive_forbid_today(
            mode_value="probe",
            decision_brief={"focus": {"avoid_points": ["不追涨停板", "不打满仓"]}},
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertIn("不追涨停板", titles)
        self.assertIn("不打满仓", titles)


class ReclassifyWhenTest(unittest.TestCase):
    def test_defense_has_two_paths(self) -> None:
        rules = derive_reclassify_when(
            mode_value="defense",
            readiness=_readiness("blocked"),
            gate=_gate(),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 观察", labels)
        self.assertIn("→ 试探", labels)

    def test_probe_has_progress_and_regression(self) -> None:
        rules = derive_reclassify_when(
            mode_value="probe",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 进攻", labels)
        self.assertIn("→ 观察", labels)


def _watchlist(priority: int = 0, observe: int = 0) -> dict[str, object]:
    return {
        "priority_codes": [f"60000{i}" for i in range(priority)],
        "observe_codes":  [f"60010{i}" for i in range(observe)],
        "stocks": [],
    }


def _screening(top_theme: str | None = "AI 算力", approved: int = 0, total: int = 0) -> dict[str, object]:
    themes = []
    if top_theme:
        themes = [{"theme": top_theme, "score": 3}]
    return {
        "market_themes": {"top_theme": top_theme, "themes": themes},
        "screening_summary": {
            "approved_count": approved,
            "candidate_total": total,
        },
    }


class JudgementChainTest(unittest.TestCase):
    def test_four_dimensions_present(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=2),
            screening_batch=_screening("AI 算力", approved=4, total=12),
            confirmation=_confirmation(confirmed=1),
        )
        dims = [item["dim"] for item in chain]
        self.assertEqual(dims, ["market", "main_theme", "holdings_pressure", "new_quality"])

    def test_blocked_freezes_all_verdicts(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("blocked"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=3),
            screening_batch=_screening("AI 算力", approved=4, total=12),
            confirmation=_confirmation(confirmed=2),
        )
        for item in chain:
            self.assertEqual(item["verdict"], "未对齐当日")
            self.assertIn("数据未对齐当日", item["evidence"])

    def test_market_verdict_strong_for_offense_label(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(),
        )
        market = next(item for item in chain if item["dim"] == "market")
        self.assertEqual(market["verdict"], "强")

    def test_holdings_pressure_high_when_priority_or_downgraded(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=3),
            screening_batch=_screening(),
            confirmation=_confirmation(downgraded=2),
        )
        hp = next(item for item in chain if item["dim"] == "holdings_pressure")
        self.assertEqual(hp["verdict"], "高")

    def test_new_quality_good(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(confirmed=2),
        )
        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "好")

    def test_holdings_pressure_high_via_downgraded_only(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=0),
            screening_batch=_screening(),
            confirmation=_confirmation(downgraded=2),
        )
        hp = next(item for item in chain if item["dim"] == "holdings_pressure")
        self.assertEqual(hp["verdict"], "高")

    def test_holdings_pressure_low_when_nothing_pressing(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=0),
            screening_batch=_screening(),
            confirmation=_confirmation(),
        )
        hp = next(item for item in chain if item["dim"] == "holdings_pressure")
        self.assertEqual(hp["verdict"], "低")

    def test_main_theme_a_when_approved_sufficient(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening("AI 算力", approved=5, total=20),
            confirmation=_confirmation(),
        )
        theme = next(item for item in chain if item["dim"] == "main_theme")
        self.assertEqual(theme["verdict"], "A")

    def test_main_theme_none_when_top_theme_missing(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(top_theme=None),
            confirmation=_confirmation(),
        )
        theme = next(item for item in chain if item["dim"] == "main_theme")
        self.assertEqual(theme["verdict"], "无")

    def test_new_quality_mid_with_fresh_only(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(fresh=2),
        )
        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "中")

    def test_new_quality_bad_when_empty(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(),
        )
        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "差")

    def test_new_quality_mid_when_confirmed_and_downgraded(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(confirmed=1, downgraded=1),
        )
        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "中")

    def test_v2_new_quality_exposes_ai_judge_coverage(self) -> None:
        v2_item = {
            "code": "600001",
            "suggested_action": "trial",
            "ai_status": "used",
            "ai_status_label": "AI Judge 已参与结构判读",
            "opportunity_v2": {
                "suggested_action": "trial",
                "desired_action": "trial",
                "ai_status": "used",
                "ai_summary": {
                    "status": "used",
                    "label": "AI Judge 已参与结构判读",
                    "detail": "AI 改写/确认了 thesis、fake_breakout_risk；最终动作仍受 hard gate 封顶。",
                },
            },
        }

        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch={
                **_screening(),
                "candidates": [v2_item],
            },
            confirmation=_confirmation(),
        )

        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "条件")
        self.assertIn("AI=采用1/影子0/fallback0/未调用0", nq["evidence"])
        self.assertTrue(any("AI判读=AI Judge 已参与结构判读" in item for item in nq["evidence"]))


def _action_item(
    *,
    key: str,
    title: str,
    tone: str = "watch",
    detail: str = "",
    foot: str = "",
    setup_label: str | None = None,
    stop_loss: str | None = None,
    entry_plan: dict[str, object] | None = None,
    decision_rank_label: str | None = None,
    decision_summary: str | None = None,
    url: str = "",
    state: str = "pending",
) -> dict[str, object]:
    return {
        "key": key,
        "title": title,
        "tone": tone,
        "detail": detail,
        "foot": foot,
        "setup_label": setup_label,
        "stop_loss": stop_loss,
        "entry_plan": entry_plan,
        "decision_rank_label": decision_rank_label,
        "decision_summary": decision_summary,
        "url": url,
        "source": "test",
        "decision": {"value": state, "label": state, "tone": tone},
        "display_state": {"value": state, "label": state, "tone": tone},
    }


def _groups(do_now=None, watch=None, avoid=None) -> list[dict[str, object]]:
    return [
        {"key": "do-now", "items": do_now or []},
        {"key": "watch",  "items": watch  or []},
        {"key": "avoid",  "items": avoid  or []},
    ]


class ActionLanesTest(unittest.TestCase):
    def test_four_lanes_always_returned(self) -> None:
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(),
            decision_brief=None,
        )
        self.assertEqual([lane["key"] for lane in lanes], ["must", "conditional", "observe", "forbid"])

    def test_sell_item_goes_to_must(self) -> None:
        item = _action_item(key="watchlist:600519", title="600519 茅台", tone="sell", detail="止损 1620 已破")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(do_now=[item]),
            decision_brief=None,
        )
        must = next(lane for lane in lanes if lane["key"] == "must")
        self.assertEqual(must["items"][0]["code"], "600519")
        self.assertEqual(must["items"][0]["action_type"], "减仓")

    def test_watch_item_with_setup_label_goes_to_conditional(self) -> None:
        item = _action_item(
            key="screening:300750",
            title="300750 宁德",
            tone="watch",
            setup_label="突破 220",
            stop_loss="215",
        )
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )
        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        self.assertEqual(conditional["items"][0]["trigger"], "突破 220")
        self.assertEqual(conditional["items"][0]["invalidate_when"], "215")

    def test_trial_candidate_with_entry_plan_trigger_goes_to_conditional(self) -> None:
        item = _action_item(
            key="confirmation:000063",
            title="中兴通讯 000063",
            tone="positive",
            detail="站回关键位后小仓位试错",
            foot="审计意见出现异常表述，候选降级为谨慎观察。",
            entry_plan={
                "trigger": "站回 36.25 上方且资金不转负，再考虑试错。",
                "invalidate": "跌回 36.07 下方取消。",
                "sizing": "触发后小仓位试错",
            },
            decision_rank_label="#1 先看",
            decision_summary="低位反转优先；卡点：资金不能转负",
        )
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(do_now=[item]),
            decision_brief=None,
        )

        must = next(lane for lane in lanes if lane["key"] == "must")
        conditional = next(lane for lane in lanes if lane["key"] == "conditional")

        self.assertEqual(must["items"], [])
        self.assertEqual(conditional["items"][0]["code"], "000063")
        self.assertEqual(conditional["items"][0]["action_type"], "等触发")
        self.assertIn("站回 36.25", conditional["items"][0]["trigger"])
        self.assertIn("36.07", conditional["items"][0]["invalidate_when"])
        self.assertIn("#1 先看", conditional["items"][0]["reason"])

    def test_v2_trial_goes_to_conditional_even_without_legacy_trigger(self) -> None:
        item = _action_item(
            key="screening:300750",
            title="宁德时代 300750",
            tone="positive",
            detail="旧字段没有触发位",
        )
        item.update({
            "suggested_action": "trial",
            "suggested_action_label": "试错待触发",
            "thesis": "新能源主线修复，个股角色从观察转为承接接力。",
            "why_now": "资金回流且回踩不破。",
            "missing_confirmation": ["站回 210 上方", "资金不能转负"],
            "invalidation": "跌破 198 取消。",
        })

        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )

        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        self.assertEqual(conditional["items"][0]["code"], "300750")
        self.assertEqual(conditional["items"][0]["action_type"], "等触发")
        self.assertIn("还差：站回 210 上方", conditional["items"][0]["reason"])
        self.assertEqual(observe["items"], [])

    def test_v2_shadow_with_hard_gate_reason_stays_observe(self) -> None:
        item = _action_item(
            key="screening:600001",
            title="样本股份 600001",
            tone="positive",
            setup_label="突破 12.30",
            detail="旧逻辑会把 setup_label 当触发。",
        )
        item.update({
            "suggested_action": "shadow",
            "suggested_action_label": "影子跟踪",
            "thesis": "结构假设成立，但真实交易权限未放行。",
            "hard_gate_max_action": "shadow",
            "hard_gate_block_reason": "真实交易权限未放行",
            "opportunity_v2": {
                "suggested_action": "shadow",
                "desired_action": "trial",
                "hard_gate": {
                    "maximum_allowed_action": "shadow",
                    "block_reasons": ["真实交易权限未放行"],
                },
            },
        })

        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )

        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        self.assertEqual(conditional["items"], [])
        self.assertEqual(observe["items"][0]["code"], "600001")
        self.assertEqual(observe["items"][0]["action_type"], "影子跟踪")
        self.assertIn("不能买：真实交易权限未放行", observe["items"][0]["reason"])

    def test_v2_calibration_guard_is_visible_in_action_lane_reason(self) -> None:
        item = _action_item(
            key="screening:600001",
            title="样本股份 600001",
            tone="positive",
            detail="结构已成，但 active 尚未校准。",
        )
        item.update({
            "suggested_action": "trial",
            "suggested_action_label": "试错待触发",
            "thesis": "主线回踩后承接重新成立。",
            "why_now": "资金回流且触发位清楚。",
            "missing_confirmation": [],
            "invalidation": "跌破承接位取消。",
            "opportunity_v2": {
                "suggested_action": "trial",
                "desired_action": "trial",
                "mode_requested": "active",
                "mode_effective": "assist",
                "mode_guard": {
                    "requested_mode": "active",
                    "effective_mode": "assist",
                    "active_allowed": False,
                    "sample_stage": "cold_start",
                    "guard_reason": "V2 active 未放开",
                },
                "calibration": {
                    "sample_stage": "cold_start",
                    "guard_reason": "V2 active 未放开",
                },
            },
        })

        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )

        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        self.assertEqual(conditional["items"][0]["code"], "600001")
        self.assertIn("校准护栏", conditional["items"][0]["reason"])
        self.assertIn("V2 active 未放开", conditional["items"][0]["reason"])

    def test_watch_item_without_trigger_goes_to_observe(self) -> None:
        item = _action_item(key="confirmation:600000", title="600000 浦发", tone="watch", detail="午盘新增观察")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        self.assertEqual(observe["items"][0]["code"], "600000")
        self.assertEqual(observe["items"][0]["action_type"], "仅观察")

    def test_dedup_keeps_higher_priority(self) -> None:
        same = _action_item(key="watchlist:600519", title="600519 茅台", tone="sell")
        same_watch = _action_item(key="watchlist:600519", title="600519 茅台", tone="watch")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(do_now=[same], watch=[same_watch]),
            decision_brief=None,
        )
        must = next(lane for lane in lanes if lane["key"] == "must")
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        self.assertEqual(len(must["items"]), 1)
        self.assertFalse(any(it["code"] == "600519" for it in observe["items"]))
        self.assertFalse(any(it["code"] == "600519" for it in conditional["items"]))

    def test_defense_injects_no_new_positions_into_forbid(self) -> None:
        lanes = derive_action_lanes(
            mode_value="defense",
            action_groups=_groups(),
            decision_brief=None,
        )
        forbid = next(lane for lane in lanes if lane["key"] == "forbid")
        titles = [item["title"] for item in forbid["items"]]
        self.assertTrue(any("不开新仓" in t for t in titles))

    def test_minimum_output_when_everything_empty(self) -> None:
        lanes = derive_action_lanes(
            mode_value="observe",
            action_groups=_groups(),
            decision_brief=None,
        )
        total = sum(len(lane["items"]) for lane in lanes if lane["key"] in {"must", "conditional", "forbid"})
        self.assertGreaterEqual(total, 1)

    def test_minimum_must_sentinel_fires_when_no_actionable(self) -> None:
        lanes = derive_action_lanes(
            mode_value="observe",
            action_groups=_groups(),
            decision_brief=None,
        )
        must = next(lane for lane in lanes if lane["key"] == "must")
        self.assertEqual(len(must["items"]), 1)
        self.assertEqual(must["items"][0]["key"], "system:review-holdings-first")
        self.assertEqual(must["items"][0]["url"], "/portfolio")


class MiddayVerifyTest(unittest.TestCase):
    def test_unavailable_when_confirmation_missing(self) -> None:
        verify = derive_midday_verify(
            confirmation=None,
            screening_batch=None,
            decision_brief=None,
            mode_value="observe",
        )
        self.assertFalse(verify["available"])
        self.assertIn("午盘验证尚未到位", verify["midday_status"])

    def test_lists_fresh_and_downgraded(self) -> None:
        verify = derive_midday_verify(
            confirmation=_confirmation(confirmed=1, fresh=2, downgraded=1),
            screening_batch={"screening_summary": {"execution_gate_status": "弱环境"}},
            decision_brief=None,
            mode_value="probe",
        )
        self.assertTrue(verify["available"])
        self.assertEqual(len(verify["fresh_candidates"]), 2)
        self.assertEqual(len(verify["downgraded"]), 1)
        self.assertIn("弱环境", verify["morning_takeaway"])

    def test_verify_failed_is_rendered_as_execution_failure(self) -> None:
        confirmation = _confirmation()
        confirmation["validation_status"] = "verify_failed"
        confirmation["validation_errors"] = ["midday_verify.py 执行失败，请查看 stderr"]
        confirmation["runner_status"] = "failed"
        verify = derive_midday_verify(
            confirmation=confirmation,
            screening_batch={"screening_summary": {"execution_gate_status": "弱环境"}},
            decision_brief=None,
            mode_value="observe",
        )
        self.assertTrue(verify["available"])
        self.assertIn("午盘确认执行失败", verify["midday_status"])
        self.assertIn("midday_verify.py 执行失败", verify["midday_status"])
        self.assertIn("请重跑午盘确认", verify["midday_status"])
        self.assertNotIn("承接未通过", verify["midday_status"])
        self.assertNotIn("今天不触发买入", verify["midday_status"])
        self.assertNotIn("verify_failed", verify["midday_status"])

    def test_ok_zero_counts_is_rendered_as_no_buy_signal(self) -> None:
        verify = derive_midday_verify(
            confirmation=_confirmation(),
            screening_batch={"screening_summary": {"execution_gate_status": "弱环境"}},
            decision_brief=None,
            mode_value="observe",
        )
        self.assertTrue(verify["available"])
        self.assertIn("午盘已确认", verify["midday_status"])
        self.assertIn("确认 0", verify["midday_status"])
        self.assertIn("今天不触发买入", verify["midday_status"])


class TrustTest(unittest.TestCase):
    def test_summarises_readiness(self) -> None:
        trust = derive_trust(
            readiness={
                **_readiness("live_ready"),
                "source_freshness": [{"timely": True}, {"timely": True}],
                "quality_freshness": [{"timely": True}, {"timely": False}],
                "blockers": [],
                "warnings": [{"message": "w1"}],
            },
            refresh_status=None,
        )
        self.assertEqual(trust["readiness_mode"], "live_ready")
        self.assertEqual(trust["source_summary"], "2/2 timely")
        self.assertEqual(trust["quality_summary"], "1/2 ok")
        self.assertEqual(trust["warnings_count"], 1)

    def test_summarises_empty_readiness(self) -> None:
        trust = derive_trust(
            readiness={
                **_readiness("blocked"),
                "source_freshness": [],
                "quality_freshness": [],
                "blockers": [],
                "warnings": [],
            },
            refresh_status=None,
        )
        self.assertEqual(trust["source_summary"], "0/0 timely")
        self.assertEqual(trust["quality_summary"], "0/0 ok")
        self.assertEqual(trust["blockers_count"], 0)
        self.assertEqual(trust["warnings_count"], 0)


class BuildBriefTest(unittest.TestCase):
    def test_returns_complete_shape(self) -> None:
        brief = build_today_command_brief(
            trade_date="2026-05-22",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制试错"),
            decision_brief=None,
            watchlist=_watchlist(priority=1),
            screening_batch=_screening("AI 算力", approved=2, total=8),
            confirmation=_confirmation(confirmed=1, fresh=1),
            action_groups=_groups(do_now=[_action_item(key="watchlist:600519", title="600519 茅台", tone="sell")]),
            action_queue={"items": [_action_item(key="watchlist:600519", title="600519 茅台", tone="sell")]},
            refresh_status=None,
        )
        for key in (
            "trade_date", "generated_at", "mode", "permits", "position_cap", "first_action",
            "forbid_today", "reclassify_when", "judgement_chain", "action_lanes",
            "midday_verify", "trust",
        ):
            self.assertIn(key, brief)
        self.assertEqual(brief["mode"]["value"], "probe")
        self.assertEqual(brief["first_action"]["kind"], "stock")


class BuildTodayViewIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_api_today_includes_command_brief(self) -> None:
        response = self.client.get("/api/today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        # 新字段
        self.assertIn("command_brief", payload)
        brief = payload["command_brief"]
        self.assertIsNotNone(brief, "command_brief unexpectedly None — fail-soft may have triggered")
        for key in ("mode", "permits", "position_cap", "first_action", "judgement_chain", "action_lanes", "midday_verify", "trust"):
            self.assertIn(key, brief)
        # mode.value 必须落到合法枚举
        self.assertIn(brief["mode"]["value"], {"defense", "observe", "probe", "offense"})

        # 旧字段必须保留
        for legacy_key in ("command_hero", "action_queue", "radar_cards", "risk_rows", "source_cards", "quality_cards", "hero", "counts"):
            self.assertIn(legacy_key, payload)


class FirstActionRobustnessTest(unittest.TestCase):
    def test_none_item_in_queue_does_not_crash(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={"items": [None, {"key": "watchlist:600519", "title": "600519 茅台", "tone": "sell", "url": "/stock/600519", "decision": {"value": "pending"}, "display_state": {"value": "pending"}}]},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "stock")
        self.assertEqual(action["url"], "/stock/600519")


class BuildBriefRobustnessTest(unittest.TestCase):
    def test_per_section_isolation_when_inputs_are_broken(self) -> None:
        # Force derive_judgement_chain to be called with a structurally bad input.
        # ``screening_batch`` set to a string would normally raise inside the deriver.
        brief = build_today_command_brief(
            trade_date="2026-05-22",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            decision_brief=None,
            watchlist=_watchlist(),
            screening_batch="not-a-dict",  # type: ignore[arg-type]
            confirmation=_confirmation(),
            action_groups=_groups(),
            action_queue={"items": []},
            refresh_status=None,
        )
        # Brief must still be returned with all 12 keys.
        for key in (
            "mode", "permits", "position_cap", "first_action", "forbid_today",
            "reclassify_when", "judgement_chain", "action_lanes", "midday_verify", "trust", "errors",
        ):
            self.assertIn(key, brief)
        # At least one section captured an error.
        self.assertTrue(len(brief["errors"]) >= 1)


if __name__ == "__main__":
    unittest.main()
