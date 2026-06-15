from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from dashboard_data import build_today_action_groups, build_today_confirmation_task_item  # noqa: E402
from decision_contract import build_decision_contract  # noqa: E402


def readiness_fixture() -> dict:
    capability_ok = {"status": "ok", "granted": True, "why_not": [], "degraded_path": [], "blocking_sources": []}
    return {
        "readiness_mode": "live_ready",
        "ready": True,
        "capabilities": {
            "observe": capability_ok,
            "review": capability_ok,
            "approve": capability_ok,
            "trade": {
                "status": "blocked",
                "granted": False,
                "why_not": [{"code": "account_not_live", "message": "账户处于研究态，不参与真钱交易。"}],
                "degraded_path": [],
                "blocking_sources": ["account.book"],
            },
            "ledger_capture": {
                "status": "blocked",
                "granted": False,
                "why_not": [{"code": "ledger_capture_research", "message": "当前为研究态，不写真实账本。"}],
                "degraded_path": [],
                "blocking_sources": ["account.book"],
            },
        },
        "source_freshness": [
            {"key": "watchlist", "label": "自选股数据", "available": True, "stale": False},
            {"key": "screening", "label": "进攻型候选数据", "available": True, "stale": False},
            {"key": "confirmation", "label": "午盘承接确认", "available": True, "stale": False},
            {"key": "decision_brief", "label": "投资总控简报", "available": True, "stale": False},
        ],
        "dataset_freshness": [],
    }


def quality_status_fixture() -> dict:
    return {
        "lanes": {
            "watchlist": {"validation_status": "ok"},
            "aggressive": {"validation_status": "ok"},
            "midday_confirmation": {"validation_status": "ok"},
        }
    }


def trial_candidate(
    code: str,
    name: str,
    *,
    priority: float,
    execution: float,
    consistency: float,
    amount: float,
    flow: float,
    change: float,
    trigger: str,
    invalidate: str,
) -> dict:
    return {
        "code": code,
        "name": name,
        "screening_status": "approved",
        "theme": "AI硬件链",
        "setup_type": "low_reversal",
        "setup_label": "低位反转",
        "priority_score": priority,
        "best_score": priority,
        "change_pct": change,
        "amount_yi": amount,
        "flow_today_yi": flow,
        "capital_trend": "由负转正" if flow > 0 else "待确认",
        "execution_quality": {"score": execution, "label": "高执行质量" if execution >= 7 else "中执行质量"},
        "consistency": {"score": consistency, "label": "强一致" if consistency >= 3 else "一般"},
        "entry_plan": {
            "action": "按触发条件继续跟踪。",
            "trigger": trigger,
            "invalidate": invalidate,
            "avoid": "资金转负或承接失败就取消。",
            "sizing": "触发后小仓位试错",
        },
    }


class TodayActionQueueContractTest(unittest.TestCase):
    def test_confirmed_candidate_with_trial_plan_surfaces_as_trial_pending(self) -> None:
        task = build_today_confirmation_task_item(
            {
                "code": "600183",
                "name": "生益科技",
                "status": "confirmed",
                "theme": "PCB",
                "entry_plan": {
                    "action": "午盘确认仍在，按触发条件继续跟踪。",
                    "trigger": "放量站稳后再评估，盘中直线拉高不追。",
                    "sizing": "触发后小仓位试错",
                },
            },
            source="午盘仍可跟踪",
        )
        task["group_key"] = "do-now"
        task["actionable"] = True
        task["trust"] = {"trusted": True}

        self.assertEqual(task["status"], "试错待触发")
        self.assertTrue(any("触发后小仓位试错" in metric for metric in task["metrics"]))
        self.assertEqual(task["entry_plan"]["sizing"], "触发后小仓位试错")

        contract = build_decision_contract(
            task,
            trade_date="2026-06-03",
            expected_trade_date="2026-06-03",
            data_trade_date="2026-06-03",
            readiness=readiness_fixture(),
        )

        self.assertEqual(contract["action"], "trial_buy")
        self.assertFalse(contract["allowed_for_real_money"])

    def test_confirmed_candidates_are_ranked_by_full_screening_context(self) -> None:
        zte = trial_candidate(
            "000063",
            "中兴通讯",
            priority=80,
            execution=8,
            consistency=4,
            amount=64.1,
            flow=22.64,
            change=2.89,
            trigger="站回 36.25 上方且资金不转负，再考虑试错。",
            invalidate="跌回 36.07 下方取消。",
        )
        lingnan = trial_candidate(
            "000060",
            "中金岭南",
            priority=74,
            execution=7,
            consistency=3,
            amount=46,
            flow=4.2,
            change=1.4,
            trigger="回踩 7.71 一带不破，承接确认后再试错。",
            invalidate="跌破 7.52 取消。",
        )
        shengyi = trial_candidate(
            "600183",
            "生益科技",
            priority=52,
            execution=4,
            consistency=1,
            amount=95,
            flow=-0.6,
            change=2.1,
            trigger="放量站稳 147.90 后再评估。",
            invalidate="跌破 141.20 取消。",
        )

        groups = build_today_action_groups(
            watchlist={"stocks": [], "priority_codes": [], "observe_codes": []},
            screening_batch={"generated_at": "2026-06-03 09:40:00", "candidates": [shengyi, lingnan, zte]},
            confirmation={
                "generated_at": "2026-06-03 13:30:00",
                "validation_status": "ok",
                "confirmed": [
                    {"code": "600183", "name": "生益科技", "status": "confirmed"},
                    {"code": "000060", "name": "中金岭南", "status": "confirmed"},
                    {"code": "000063", "name": "中兴通讯", "status": "confirmed"},
                ],
                "fresh_candidates": [],
                "downgraded": [],
            },
            decision_brief=None,
            quality_status=quality_status_fixture(),
            brief_is_live=False,
            gate={"allow_new_positions": True, "label": "限制试错", "summary": "可试错，但必须等触发。"},
        )

        do_now = next(group for group in groups if group["key"] == "do-now")["items"]

        self.assertEqual([item["key"] for item in do_now], ["confirmation:000063", "confirmation:000060", "confirmation:600183"])
        self.assertEqual(do_now[0]["decision_rank_label"], "#1 先看")
        self.assertEqual(do_now[1]["decision_rank_label"], "#2 二号候补")
        self.assertIn("站回 36.25", do_now[0]["detail"])
        self.assertEqual(do_now[0]["entry_plan"]["trigger"], "站回 36.25 上方且资金不转负，再考虑试错。")
        self.assertEqual(do_now[0]["flow_today_yi"], 22.64)
        self.assertEqual(do_now[0]["capital_trend"], "由负转正")


if __name__ == "__main__":
    unittest.main()
