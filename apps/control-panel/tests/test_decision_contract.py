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

from decision_contract import attach_decision_contracts, build_decision_contract, normalize_action_intent  # noqa: E402


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
                "why_not": [{"code": "account_not_live", "message": "账户处于研究态，不参与真钱交易；需要你手动切换到影子盘或小额实盘。"}],
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


def live_ready_fixture() -> dict:
    readiness = readiness_fixture()
    capability_ok = {"status": "ok", "granted": True, "why_not": [], "degraded_path": [], "blocking_sources": []}
    readiness["capabilities"]["trade"] = dict(capability_ok)
    readiness["capabilities"]["ledger_capture"] = dict(capability_ok)
    return readiness


class DecisionContractTest(unittest.TestCase):
    def test_entry_plan_trial_sizing_promotes_observe_copy_to_trial_buy(self) -> None:
        action = normalize_action_intent(
            {
                "key": "confirmation:600183",
                "title": "生益科技 600183",
                "source": "午盘仍可跟踪",
                "status": "仍可跟踪",
                "detail": "午盘确认仍在，按触发条件继续跟踪。",
                "entry_plan": {
                    "action": "午盘确认仍在，按触发条件继续跟踪。",
                    "sizing": "触发后小仓位试错",
                    "trigger": "放量站稳后再评估。",
                },
            }
        )

        self.assertEqual(action, "trial_buy")

    def test_real_money_action_requires_trade_and_ledger_capabilities(self) -> None:
        contract = build_decision_contract(
            {
                "key": "screening:600690",
                "title": "海尔智家 600690",
                "source": "观察池",
                "status": "轻仓试错",
                "detail": "突破后只做小仓验证。",
                "group_key": "do-now",
                "actionable": True,
                "trust": {"trusted": True},
            },
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness=readiness_fixture(),
        )

        self.assertEqual(contract["schema_version"], "decision_contract.v0")
        self.assertEqual(contract["action"], "trial_buy")
        self.assertEqual(contract["required_capabilities"], ["review", "approve", "trade", "ledger_capture"])
        self.assertFalse(contract["allowed_for_real_money"])
        self.assertEqual(contract["stock"]["code"], "600690")
        constraint_codes = {item["code"] for item in contract["execution_constraints"]}
        self.assertIn("capability_trade_blocked", constraint_codes)
        self.assertIn("capability_ledger_capture_blocked", constraint_codes)
        datasets = {item["dataset"] for item in contract["data_requirements"]}
        self.assertIn("quotes.batch", datasets)
        self.assertIn("account.book", datasets)
        self.assertTrue(contract["ledger_capture"]["capture_required"])
        self.assertEqual(contract["review_obligation"]["windows"], ["T+1", "T+3", "T+5", "T+10"])

    def test_attach_contracts_keeps_queue_shape_and_marks_stale_item_blocked(self) -> None:
        queue = {
            "title": "今日动作队列",
            "items": [
                {
                    "key": "watchlist:600690",
                    "title": "海尔智家 600690",
                    "source": "自选股",
                    "status": "继续持有",
                    "detail": "继续观察趋势。",
                    "group_key": "do-now",
                    "actionable": True,
                    "trust": {"trusted": True},
                }
            ],
            "stale_items": [
                {
                    "key": "screening:000001",
                    "title": "平安银行 000001",
                    "source": "观察池",
                    "status": "轻仓试错",
                    "detail": "旧数据候选。",
                    "group_key": "watch",
                    "actionable": False,
                    "trust": {"trusted": False},
                }
            ],
            "counts": {"total": 1},
        }

        enriched, payload = attach_decision_contracts(
            queue,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness=readiness_fixture(),
            source_cards=[],
            artifacts={},
        )

        self.assertIn("decision_contract", enriched["items"][0])
        self.assertIn("decision_contract", enriched["stale_items"][0])
        self.assertIn("decision_contracts", enriched)
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(payload["summary"]["review_required"], 2)
        stale_contract = enriched["stale_items"][0]["decision_contract"]
        self.assertFalse(stale_contract["allowed_for_real_money"])
        self.assertIn("item_not_trusted", {item["code"] for item in stale_contract["execution_constraints"]})

    def test_display_only_degrade_risk_does_not_block_formal_action(self) -> None:
        contract = build_decision_contract(
            {
                "key": "screening:600690",
                "title": "海尔智家 600690",
                "source": "观察池",
                "status": "轻仓试错",
                "detail": "形态成立，但质押比例偏高。",
                "group_key": "do-now",
                "actionable": True,
                "trust": {"trusted": True},
                "risk_level": "degrade",
                "degrade_reason": "质押比例偏高，候选降级观察。",
            },
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness=live_ready_fixture(),
        )

        self.assertTrue(contract["allowed_for_formal_action"])
        self.assertTrue(contract["allowed_for_real_money"])
        self.assertNotIn("risk_hard_block", {item["code"] for item in contract["execution_constraints"]})

    def test_hard_execution_risk_blocks_formal_action(self) -> None:
        contract = build_decision_contract(
            {
                "key": "screening:600690",
                "title": "海尔智家 600690",
                "source": "观察池",
                "status": "轻仓试错",
                "detail": "形态成立，但当前停牌。",
                "group_key": "do-now",
                "actionable": True,
                "trust": {"trusted": True},
                "risk_level": "block",
                "block_reason": "execution.flags 显示停牌，今天不能执行买卖。",
            },
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness=live_ready_fixture(),
        )

        self.assertFalse(contract["allowed_for_formal_action"])
        self.assertFalse(contract["allowed_for_real_money"])
        constraints = {item["code"]: item for item in contract["execution_constraints"]}
        self.assertIn("risk_hard_block", constraints)
        self.assertIn("停牌", constraints["risk_hard_block"]["message"])


if __name__ == "__main__":
    unittest.main()
