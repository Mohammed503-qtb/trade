"""اختبارات دورة الحياة (§18.2) — الانتقالات غير القابلة للتخريب.

«اختبار خاصية §38.2: لا عودة من COMPLETED» — وهنا أوسع: لا خروج من
أي حالة نهائية أبدًا (لا إنقاذ §18.5)، وكل انتقال غير قانوني يُرفض
صاخبًا باسم الحالتين، والسجل ملحق-فقط بنسخ مجمّدة لا طفرة صامتة.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from _scenario_fixtures import (
    ANCHOR_TIME,
    ATR,
    make_market_state,
    make_sweep_payload,
    make_target_map,
    sell_zone,
)
from scenarios.lifecycle import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    apply_transition,
    is_terminal,
    validate_transition,
)
from scenarios.proposer import AnchorEvent, ScenarioProposer
from schemas import EventType, Scenario, ScenarioState


def _state_value(state: ScenarioState) -> str:
    """مفتاح ترتيب معلن للنهائيات — معرف صريح بدل لامدا مبهمة النوع."""
    return state.value


_SORTED_TERMINALS = sorted(TERMINAL_STATES, key=_state_value)


# ───────────────────────── خريطة §18.2 ─────────────────────────


class TestTransitionMap:
    """الخريطة القانونية — الدرب الأساسي والنهايات الست البديلة."""

    def test_main_path_exists(self) -> None:
        """الدرب السبعي: DRAFT→ACTIVE→TRIGGERED→AUTHORIZED→EXECUTING→IN_TRADE→COMPLETED."""
        path = [
            (ScenarioState.DRAFT, ScenarioState.ACTIVE),
            (ScenarioState.ACTIVE, ScenarioState.TRIGGERED),
            (ScenarioState.TRIGGERED, ScenarioState.AUTHORIZED),
            (ScenarioState.AUTHORIZED, ScenarioState.EXECUTING),
            (ScenarioState.EXECUTING, ScenarioState.IN_TRADE),
            (ScenarioState.IN_TRADE, ScenarioState.COMPLETED),
        ]
        for from_state, to_state in path:
            validate_transition(from_state, to_state)

    def test_alternative_endings_from_licensing_states(self) -> None:
        """النهايات البديلة تصل من كل حالة ترخيص (ما قبل الترخيص كله)."""
        for source in (ScenarioState.DRAFT, ScenarioState.ACTIVE, ScenarioState.TRIGGERED):
            for ending in (
                ScenarioState.INVALIDATED,
                ScenarioState.EXPIRED,
                ScenarioState.SUPPRESSED,
                ScenarioState.CANCELLED_BY_DATA_QUALITY,
            ):
                assert ending in LEGAL_TRANSITIONS[source], f"{source}→{ending}"

    def test_rejected_by_risk_only_from_triggered(self) -> None:
        """رفض المخاطرة قرار ترخيص — من TRIGGERED حصرًا (§33.5)."""
        assert ScenarioState.REJECTED_BY_RISK in LEGAL_TRANSITIONS[ScenarioState.TRIGGERED]
        for source in (
            ScenarioState.DRAFT,
            ScenarioState.ACTIVE,
            ScenarioState.AUTHORIZED,
        ):
            assert ScenarioState.REJECTED_BY_RISK not in LEGAL_TRANSITIONS[source]

    def test_suppressed_not_after_authorization(self) -> None:
        """الكتم قرار تنافس على الترخيص — ما تجاوزه لا يُكتم صامتًا."""
        for source in (ScenarioState.AUTHORIZED, ScenarioState.EXECUTING, ScenarioState.IN_TRADE):
            assert ScenarioState.SUPPRESSED not in LEGAL_TRANSITIONS[source]

    def test_terminals_have_no_exits(self) -> None:
        """النهائيات الست بلا صادرة أبدًا — §38.2/§18.5 لا إنقاذ."""
        assert (
            frozenset(
                {
                    ScenarioState.COMPLETED,
                    ScenarioState.INVALIDATED,
                    ScenarioState.EXPIRED,
                    ScenarioState.SUPPRESSED,
                    ScenarioState.REJECTED_BY_RISK,
                    ScenarioState.CANCELLED_BY_DATA_QUALITY,
                }
            )
            == TERMINAL_STATES
        )
        for terminal in TERMINAL_STATES:
            assert LEGAL_TRANSITIONS[terminal] == frozenset()
            assert is_terminal(terminal)

    def test_no_backward_transitions(self) -> None:
        """لا رجوع في الدرب أبدًا — كل خريطة الصعود بلا عكوس."""
        rank = {
            ScenarioState.DRAFT: 0,
            ScenarioState.ACTIVE: 1,
            ScenarioState.TRIGGERED: 2,
            ScenarioState.AUTHORIZED: 3,
            ScenarioState.EXECUTING: 4,
            ScenarioState.IN_TRADE: 5,
        }
        for source, targets in LEGAL_TRANSITIONS.items():
            if source in rank:
                for target in targets:
                    assert target not in rank or rank[target] > rank[source], (
                        f"انتقال للخلف: {source}→{target}"
                    )


# ───────────────────────── الحصانة (§38.2) ─────────────────────────


class TestNoSubversion:
    """لا عودة من حالة نهائية — ولا انتقال غير قانوني يمر صامتًا."""

    @pytest.mark.parametrize(
        "terminal",
        _SORTED_TERMINALS,
    )
    def test_no_exit_from_any_terminal(self, terminal: ScenarioState) -> None:
        """كل انتقال من أي نهائية يُرفض — «a new scenario must be opened»."""
        for target in ScenarioState:
            with pytest.raises(IllegalTransitionError):
                validate_transition(terminal, target)

    @pytest.mark.parametrize(
        "terminal",
        _SORTED_TERMINALS,
    )
    def test_invalidated_scenario_cannot_authorize(self, terminal: ScenarioState) -> None:
        """«an invalidated scenario cannot authorize a trade» (§38.2 حرفيًا)."""
        scenario = _draft()
        invalidated = _drive_to(scenario, terminal)
        with pytest.raises(IllegalTransitionError):
            apply_transition(
                invalidated,
                ScenarioState.AUTHORIZED,
                transition_time=ANCHOR_TIME + timedelta(minutes=5),
                reason="محاولة إنقاذ بعد الإبطال",
            )

    def test_illegal_jump_rejected_loudly(self) -> None:
        """قفز الدرب (DRAFT→TRIGGERED) رفض صاخب — لا أفضل جهد."""
        with pytest.raises(IllegalTransitionError, match="DRAFT → TRIGGERED"):
            validate_transition(ScenarioState.DRAFT, ScenarioState.TRIGGERED)

    def test_completed_never_back_to_active(self) -> None:
        """الخاصية الحرفية §38.2: لا عودة من COMPLETED إلى ACTIVE."""
        with pytest.raises(IllegalTransitionError):
            validate_transition(ScenarioState.COMPLETED, ScenarioState.ACTIVE)


# ───────────────────────── السجل الملحق-فقط ─────────────────────────


class TestImmutableApplication:
    """الانتقال نسخة جديدة مجمّدة + سجل موثق — لا طفرة صامتة."""

    def test_apply_returns_frozen_copy_and_record(self) -> None:
        draft = _draft()
        when = ANCHOR_TIME + timedelta(minutes=1)
        active, record = apply_transition(
            draft,
            ScenarioState.ACTIVE,
            transition_time=when,
            reason="ترقية §18.4: مجموعتان داعمتان",
        )
        assert draft.state is ScenarioState.DRAFT  # الأصل لم يُمس
        assert active.state is ScenarioState.ACTIVE
        assert active.scenario_id == draft.scenario_id
        assert record.from_state is ScenarioState.DRAFT
        assert record.to_state is ScenarioState.ACTIVE
        assert record.transition_time == when
        assert "مجموعتان" in record.reason

    def test_empty_reason_rejected(self) -> None:
        """لا انتقال بلا سبب موثق (§31.3 «with timestamp and reason»)."""
        draft = _draft()
        with pytest.raises(ValueError, match="سبب الانتقال فارغ"):
            apply_transition(
                draft,
                ScenarioState.ACTIVE,
                transition_time=ANCHOR_TIME,
                reason="   ",
            )

    def test_full_path_records_every_step(self) -> None:
        """درب كامل يوثق كل خطوة — سجل قابل للتدقيق (§31.3)."""
        scenario = _draft()
        when = ANCHOR_TIME
        path = [
            ScenarioState.ACTIVE,
            ScenarioState.TRIGGERED,
            ScenarioState.AUTHORIZED,
            ScenarioState.EXECUTING,
            ScenarioState.IN_TRADE,
            ScenarioState.COMPLETED,
        ]
        records = []
        for state in path:
            when = when + timedelta(minutes=1)
            scenario, record = apply_transition(
                scenario, state, transition_time=when, reason=f"خطوة إلى {state.value}"
            )
            records.append(record)
        assert [r.to_state for r in records] == path
        assert scenario.state is ScenarioState.COMPLETED


# ───────────────────────── مساعدات ─────────────────────────


def _draft() -> Scenario:
    proposer = ScenarioProposer()
    outcome = proposer.propose(
        AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
        zone=sell_zone(),
        targets=make_target_map(),
        state=make_market_state(),
        atr=ATR,
    )
    scenario = outcome.proposals[0]
    assert scenario.state is ScenarioState.DRAFT
    return scenario


def _drive_to(scenario: Scenario, terminal: ScenarioState) -> Scenario:
    """قيادة السيناريو إلى حالة نهائية عبر أقصر درب قانوني في الخريطة."""
    from scenarios.lifecycle import LEGAL_TRANSITIONS

    step = 0

    def advance_to(current: Scenario, target: ScenarioState) -> Scenario:
        nonlocal step
        step += 1
        updated, _ = apply_transition(
            current,
            target,
            transition_time=ANCHOR_TIME + timedelta(minutes=step),
            reason=f"قيادة اختبارية إلى {target.value}",
        )
        return updated

    # المسارات الخاصة للحالات التي تحتاج دربًا كاملًا
    if terminal is ScenarioState.COMPLETED:
        current = advance_to(scenario, ScenarioState.ACTIVE)
        current = advance_to(current, ScenarioState.TRIGGERED)
        current = advance_to(current, ScenarioState.AUTHORIZED)
        current = advance_to(current, ScenarioState.EXECUTING)
        current = advance_to(current, ScenarioState.IN_TRADE)
        return advance_to(current, ScenarioState.COMPLETED)
    if terminal is ScenarioState.REJECTED_BY_RISK:
        current = advance_to(scenario, ScenarioState.ACTIVE)
        current = advance_to(current, ScenarioState.TRIGGERED)
        return advance_to(current, ScenarioState.REJECTED_BY_RISK)

    if terminal in LEGAL_TRANSITIONS[scenario.state]:
        return advance_to(scenario, terminal)
    current = advance_to(scenario, ScenarioState.ACTIVE)
    return advance_to(current, terminal)
