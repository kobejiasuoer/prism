"""Triage verdict computation for the discovery page.

Computes the per-stock gate (can I buy?) and action_state (should I prioritise?)
from already-structured signals. Spec: docs/superpowers/specs/2026-06-14-discovery-triage-funnel-design.md §8.4, §8.5.

These functions are pure and tested in isolation; build_opportunities_view wires
them onto each candidate card.
"""

# Valve (portfolio) status, from execution_gate_of(market_regime).
VALVE_ON = "on"
VALVE_LIMITED = "limited"
VALVE_OFF = "off"

# gate.state — permission axis.
GATE_OPEN = "open"
GATE_CAPPED = "capped"
GATE_CLOSED = "closed"

# action_state — triage axis.
ACTION_FOCUS = "focus"
ACTION_ON_TRIGGER = "on_trigger"
ACTION_WATCH = "watch"
ACTION_DROP = "drop"

# risk_level values that affect the gate (RiskLevel enum on StockListCard).
_RISK_BLOCK = "block"
_RISK_DEGRADE = "degrade"


def compute_gate_state(*, valve_status, can_trade_live, trust_level, risk_level):
    """Permission axis: can I buy this stock at all / at full size? See spec §8.4."""
    if (not can_trade_live) or valve_status == VALVE_OFF or risk_level == _RISK_BLOCK:
        return GATE_CLOSED
    if valve_status == VALVE_LIMITED or trust_level != "trusted":
        return GATE_CAPPED
    return GATE_OPEN


def compute_action_state(*, v2_action, gate_state, risk_level, eliminated):
    """Triage axis: should I prioritise this stock? See spec §8.5.

    gate is the permission filter; action_state is the priority that survives it.
    A closed/capped gate degrades priority to watch (protocol §10.5).
    """
    if eliminated:
        return ACTION_DROP
    if risk_level == _RISK_DEGRADE:
        # degrade demotes to watch even when actionable (resolves spec ambiguity).
        return ACTION_WATCH
    if v2_action == "actionable" and gate_state == GATE_OPEN:
        return ACTION_FOCUS
    if v2_action == "trial" and gate_state != GATE_CLOSED:
        return ACTION_ON_TRIGGER
    return ACTION_WATCH


def compute_gate_blocker(
    *,
    valve_status,
    can_trade_live,
    trust_level,
    risk_level,
    hard_gate_block_reason,
):
    """The FIRST single reason the gate is not open, in operator language. None if open."""
    if not can_trade_live:
        return "账户处于研究态，不能真钱执行"
    if valve_status == VALVE_OFF:
        return "进攻阀门关闭，今天不开新仓"
    if risk_level == _RISK_BLOCK:
        return "硬拦截"
    if valve_status == VALVE_LIMITED:
        return "进攻阀门半开，仓位受限"
    if trust_level != "trusted":
        return "数据未完全可信"
    if hard_gate_block_reason:
        return hard_gate_block_reason
    return None


def triage_fields_for_card(
    card,
    *,
    valve_status,
    can_trade_live,
    trust_level,
    eliminated=False,
    legacy=False,
):
    """Compute the structured triage fields for one candidate card.

    Callers: build_screening_candidate_card / build_confirmation_candidate_card in
    apps/control-panel/dashboard_data.py. Spread the returned dict onto the card.
    """
    risk_level = card.get("risk_level") or "info"
    v2_action = str(card.get("suggested_action") or "").strip()
    hard_gate_block_reason = card.get("hard_gate_block_reason") or ""

    gate_state = compute_gate_state(
        valve_status=valve_status,
        can_trade_live=can_trade_live,
        trust_level=trust_level,
        risk_level=risk_level,
    )
    action_state = compute_action_state(
        v2_action=v2_action,
        gate_state=gate_state,
        risk_level=risk_level,
        eliminated=eliminated,
    )
    blocker = (
        compute_gate_blocker(
            valve_status=valve_status,
            can_trade_live=can_trade_live,
            trust_level=trust_level,
            risk_level=risk_level,
            hard_gate_block_reason=hard_gate_block_reason,
        )
        if gate_state != GATE_OPEN
        else None
    )
    return {
        "triage_action_state": action_state,
        "triage_gate_state": gate_state,
        "triage_gate_blocker": blocker,
        "triage_legacy": bool(legacy),
    }
