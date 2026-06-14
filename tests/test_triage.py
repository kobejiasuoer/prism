from screener.triage import (
    GATE_OPEN,
    GATE_CAPPED,
    GATE_CLOSED,
    compute_gate_state,
)


def test_gate_closed_when_cannot_trade_live():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=False,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CLOSED
    )


def test_gate_closed_when_valve_off():
    assert (
        compute_gate_state(
            valve_status="off",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CLOSED
    )


def test_gate_closed_when_risk_block():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="block",
        )
        == GATE_CLOSED
    )


def test_gate_capped_when_valve_limited():
    assert (
        compute_gate_state(
            valve_status="limited",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CAPPED
    )


def test_gate_capped_when_trust_not_trusted():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="observe_only",
            risk_level="info",
        )
        == GATE_CAPPED
    )


def test_gate_open_happy_path():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_OPEN
    )


def test_gate_open_with_risk_warn():
    # warn is a soft flag, not a block — gate stays open (action_state handles deprioritisation)
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="warn",
        )
        == GATE_OPEN
    )
