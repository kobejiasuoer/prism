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
