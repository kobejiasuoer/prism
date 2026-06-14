from screener.triage import (
    ACTION_DROP,
    ACTION_FOCUS,
    ACTION_ON_TRIGGER,
    ACTION_WATCH,
    GATE_CAPPED,
    GATE_CLOSED,
    GATE_OPEN,
    VALVE_LIMITED,
    VALVE_OFF,
    VALVE_ON,
    _RISK_BLOCK,
    _RISK_DEGRADE,
    compute_action_state,
    compute_gate_blocker,
    compute_gate_state,
    triage_fields_for_card,
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


# ---- compute_action_state tests (Task A2) ----


def test_action_drop_overrides_everything():
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level="info",
            eliminated=True,
        )
        == ACTION_DROP
    )


def test_action_focus_when_actionable_and_open():
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_FOCUS
    )


def test_action_watch_when_actionable_but_gate_capped():
    # can't act at full size -> only watch
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_CAPPED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_on_trigger_when_trial_and_not_closed():
    assert (
        compute_action_state(
            v2_action="trial",
            gate_state=GATE_CAPPED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_ON_TRIGGER
    )


def test_action_watch_when_trial_but_gate_closed():
    assert (
        compute_action_state(
            v2_action="trial",
            gate_state=GATE_CLOSED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_watch_when_degrade_even_if_actionable():
    # degrade (e.g. 审计意见异常) demotes to watch even when actionable + open.
    # Resolves spec §8.5 ambiguity in favour of "degrade deprioritises".
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level=_RISK_DEGRADE,
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_watch_for_shadow_review_observe():
    for action in ("shadow", "review", "observe", ""):
        assert (
            compute_action_state(
                v2_action=action,
                gate_state=GATE_OPEN,
                risk_level="info",
                eliminated=False,
            )
            == ACTION_WATCH
        )


# ---- triage_fields_for_card tests (Task A3) ----


def _card(**overrides):
    base = {
        "suggested_action": "actionable",
        "risk_level": "info",
        "hard_gate_block_reason": "",
    }
    base.update(overrides)
    return base


def test_triage_fields_open_focus():
    out = triage_fields_for_card(
        _card(),
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
    )
    assert out == {
        "triage_action_state": "focus",
        "triage_gate_state": "open",
        "triage_gate_blocker": None,
        "triage_legacy": False,
    }


def test_triage_fields_closed_blocker_is_operator_language():
    out = triage_fields_for_card(
        _card(),
        valve_status=VALVE_OFF,
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
    )
    assert out["triage_gate_state"] == "closed"
    assert out["triage_gate_blocker"] == "进攻阀门关闭，今天不开新仓"


def test_triage_fields_legacy_flag_when_legacy():
    out = triage_fields_for_card(
        _card(suggested_action=""),  # no V2 action -> legacy-style
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
        legacy=True,
    )
    assert out["triage_legacy"] is True
    assert out["triage_action_state"] == "watch"


def test_triage_fields_eliminated_drops():
    out = triage_fields_for_card(
        _card(),
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
        eliminated=True,
    )
    assert out["triage_action_state"] == "drop"


# --- compute_gate_blocker priority ordering (direct tests) ---


def test_blocker_research_mode_overrides_valve_off():
    # can_trade_live=False wins over valve off
    assert compute_gate_blocker(
        valve_status=VALVE_OFF,
        can_trade_live=False,
        trust_level="trusted",
        risk_level="info",
        hard_gate_block_reason="",
    ) == "账户处于研究态，不能真钱执行"


def test_blocker_valve_off_overrides_risk_block():
    assert compute_gate_blocker(
        valve_status=VALVE_OFF,
        can_trade_live=True,
        trust_level="trusted",
        risk_level=_RISK_BLOCK,
        hard_gate_block_reason="",
    ) == "进攻阀门关闭，今天不开新仓"


def test_blocker_risk_block_before_valve_limited():
    assert compute_gate_blocker(
        valve_status=VALVE_LIMITED,
        can_trade_live=True,
        trust_level="trusted",
        risk_level=_RISK_BLOCK,
        hard_gate_block_reason="",
    ) == "硬拦截"


def test_blocker_valve_limited_returns_capped_reason():
    assert compute_gate_blocker(
        valve_status=VALVE_LIMITED,
        can_trade_live=True,
        trust_level="trusted",
        risk_level="info",
        hard_gate_block_reason="",
    ) == "进攻阀门半开，仓位受限"


def test_blocker_trust_untrusted_before_hard_reason():
    # trust != trusted shadows a downstream hard_gate_block_reason
    assert compute_gate_blocker(
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="observe_only",
        risk_level="info",
        hard_gate_block_reason="some upstream reason",
    ) == "数据未完全可信"


def test_blocker_hard_reason_as_fallback():
    assert compute_gate_blocker(
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
        risk_level="info",
        hard_gate_block_reason="个股硬闸门",
    ) == "个股硬闸门"


def test_blocker_none_when_all_clear():
    assert compute_gate_blocker(
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
        risk_level="info",
        hard_gate_block_reason="",
    ) is None


def test_triage_fields_defaults_missing_card_keys():
    # empty card exercises the defensive defaults (risk_level -> info, v2_action -> "")
    out = triage_fields_for_card(
        {},
        valve_status=VALVE_ON,
        can_trade_live=True,
        trust_level="trusted",
    )
    assert out["triage_gate_state"] == "open"
    assert out["triage_action_state"] == "watch"
