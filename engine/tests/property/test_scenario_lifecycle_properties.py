"""اختبارات خصائص محرك السيناريوهات (§38.2) — حصانة دورة الحياة حتمًا.

«Verify invariants such as: score always remains within configured bounds;
scenario cannot move from COMPLETED back to ACTIVE; risk cannot exceed cap;
an invalidated scenario cannot authorize a trade» — الخصائص الأربع
المعنية بالمرحلة 7 تُفرض بـhypothesis على آلة الحياة كاملة:

- **لا خروج من نهائية أبدًا**: أي تسلسل انتقالات من حالة نهائية يُرفض
  بأكمله — «لا إنقاذ» §18.5 معماريًا لا التزامًا.
- **الدرجة داخل الحدود دائمًا**: ``scenario_score`` ∈ [0, 1] مهما اشتد
  الدليل المعارض أو المساند (إسقاط (raw+1)/2 من SignedUnit — §2.6
  ليست احتمالًا).
- **المسودة لا تُرخّص**: لا درب قانوني يقود من INVALIDATED إلى أي حالة
  ترخيص (AUTHORIZED فما فوق) — «an invalidated scenario cannot authorize
  a trade» حرفيًا.
- **أحادية السجل**: الانتقالات ملحقة-فقط بمعرفات متمايزة — إعادة
  الإرسال لا تكرر سجلًا (روح D-07).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule
from scenarios.lifecycle import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    apply_transition,
)
from scenarios.proposer import score_from_raw
from schemas import Scenario, ScenarioState

ALL_STATES = list(ScenarioState)
NON_TERMINAL = [s for s in ALL_STATES if s not in TERMINAL_STATES]
LICENSING = [
    ScenarioState.AUTHORIZED,
    ScenarioState.EXECUTING,
    ScenarioState.IN_TRADE,
    ScenarioState.COMPLETED,
]

# ───────────────────────── الخصائص الصرفة ─────────────────────────


class TransitionFsm(RuleBasedStateMachine):
    """آلة حالة hypothesis فوق خريطة §18.2 — أي تسلسل محاولات حتمًا."""

    def __init__(self) -> None:
        super().__init__()
        self._scenario = _make_draft()
        self._records: list[tuple[str, str]] = []

    @initialize()
    def start(self) -> None:
        assert self._scenario.state is ScenarioState.DRAFT

    @rule(target_state=st.sampled_from(ALL_STATES))
    def attempt(self, target_state: ScenarioState) -> None:
        source = self._scenario.state
        try:
            updated, record = apply_transition(
                self._scenario,
                target_state,
                transition_time=_make_draft_time() + timedelta(minutes=len(self._records) + 1),
                reason=f"محاولة حتمية إلى {target_state.value}",
            )
        except IllegalTransitionError:
            # الرفض هو السلوك الصحيح خارج الخريطة — ولا حالة تغيرت
            assert self._scenario.state is source
            return
        # القبول يغير الحالة ويسجل — وفق الخريطة حصرًا
        assert target_state in LEGAL_TRANSITIONS[source]
        self._scenario = updated
        identity = (record.from_state.value, record.to_state.value)
        assert identity not in self._records  # أحادية السجل
        self._records.append(identity)

    @rule()
    def terminal_is_forever(self) -> None:
        if self._scenario.state in TERMINAL_STATES:
            for target in ALL_STATES:
                try:
                    apply_transition(
                        self._scenario,
                        target,
                        transition_time=_make_draft_time(),
                        reason="محاولة إنقاذ",
                    )
                except IllegalTransitionError:
                    continue
                raise AssertionError(f"خروج من نهائية: {self._scenario.state} → {target}")

    @rule()
    def invalidated_cannot_authorize(self) -> None:
        """لا درب من الإبطال إلى أي ترخيص — ولو عبر تسلسل (النهائية)."""
        if self._scenario.state is ScenarioState.INVALIDATED:
            for licensing in LICENSING:
                try:
                    apply_transition(
                        self._scenario,
                        licensing,
                        transition_time=_make_draft_time(),
                        reason="ترخيص بعد إبطال",
                    )
                except IllegalTransitionError:
                    continue
                raise AssertionError("سيناريو مبطل رخّص صفقة — §38.2")


TransitionFsmTest = TransitionFsm.TestCase


@given(st.floats(min_value=-1.0, max_value=1.0))
@settings(max_examples=300, deadline=None)
def test_score_always_within_bounds(raw: float) -> None:
    """الدرجة داخل [0, 1] مهما اشتد الدليل — ليست احتمالًا (§2.6)."""
    score = score_from_raw(raw)
    assert 0.0 <= score <= 1.0
    # الرتابة الصارمة: دليل أعلى ⇒ درجة أعلى (إسقاط خطي)
    assert score_from_raw(min(raw + 0.1, 1.0)) >= score


@given(
    st.lists(
        st.sampled_from(ALL_STATES),
        min_size=1,
        max_size=12,
    )
)
@settings(max_examples=200, deadline=None)
def test_no_sequence_leaves_terminal(sequence: list[ScenarioState]) -> None:
    """أي محاولة متتابعة من نهائية تُرفض كلها — بلا استثناء واحد."""
    scenario = _make_draft()
    invalidated, _ = apply_transition(
        scenario,
        ScenarioState.INVALIDATED,
        transition_time=_make_draft_time(),
        reason="إبطال مرجعي",
    )
    for target in sequence:
        try:
            apply_transition(
                invalidated,
                target,
                transition_time=_make_draft_time() + timedelta(minutes=1),
                reason=f"محاولة {target.value}",
            )
        except IllegalTransitionError:
            continue
        raise AssertionError(f"إنقاذ من INVALIDATED إلى {target}")


@given(st.sampled_from(NON_TERMINAL))
@settings(max_examples=100, deadline=None)
def test_legal_map_is_deterministic(source: ScenarioState) -> None:
    """الخريطة ثابتة التعداد: نفس المصدر ⇒ نفس القانونية دائمًا."""
    first = LEGAL_TRANSITIONS[source]
    second = LEGAL_TRANSITIONS[source]
    assert first == second
    assert first.issubset(set(ALL_STATES))


# ───────────────────────── مرجع بناء المسودة ─────────────────────────

_DRAFT_CACHE: Scenario | None = None


def _make_draft() -> Scenario:
    """مسودة مرجعية — تبنى مرة وتنسخ (بناء المُقترِح مكلف نسبيًا)."""
    global _DRAFT_CACHE
    if _DRAFT_CACHE is None:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for relative in (
            "tests/unit",
            "services/scenarios/src",
            "services/fusion/src",
            "services/liquidity/src",
            "services/structure/src",
            "services/market_state/src",
            "packages/schemas/src",
            "packages/common/src",
            "packages/features/src",
        ):
            sys.path.insert(0, str(root / relative))
        from _scenario_fixtures import (
            ANCHOR_TIME,
            ATR,
            make_market_state,
            make_sweep_payload,
            make_target_map,
            sell_zone,
        )
        from scenarios.proposer import AnchorEvent, ScenarioProposer
        from schemas import EventType

        proposer = ScenarioProposer()
        outcome = proposer.propose(
            AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
            zone=sell_zone(),
            targets=make_target_map(),
            state=make_market_state(),
            atr=ATR,
        )
        draft: Scenario = outcome.proposals[0]
        _DRAFT_CACHE = draft
    draft_copy: Scenario = _DRAFT_CACHE.model_copy()  # نسخة نظيفة لكل اختبار
    return draft_copy


def _make_draft_time() -> datetime:
    from _scenario_fixtures import ANCHOR_TIME

    return ANCHOR_TIME
