"""اختبارات مقيّم الإبطال الفوري (§18.5) وحسم التنافس (7.4).

الإبطال: الأسباب الخمسة المقيَّسة بشموع محسوبة يدويًا (الانجراف حدث
المشغل في المحرك — هنا الواجهة الصرفة)، ونطاق القبول (فتيل لا يكفي
عند accept_through=True)، والحدث المعاكس على منطقة المرسِم مشروطًا
بأطروحة الرفض (الانعكاس/الاستمرار-من-اجتياح دون الاختراق).

التنافس: الأسبقية الحتمية (مجموعات ثم درجة ثم معرف) والخاسر SUPPRESSED
بسبب يسمي فائزه — لا إلغاء صامت، والناجي شرط غياب الأعلى.
"""

from __future__ import annotations

import pytest
from _scenario_fixtures import (
    ANCHOR_TIME,
    ATR,
    make_break_accept_payload,
    make_candle,
    make_market_state,
    make_sweep_payload,
    make_target_map,
    sell_zone,
)
from scenarios.competition import (
    CompetingScenario,
    precedence_key,
    resolve_conflicts,
)
from scenarios.invalidation import InvalidationEvaluator, entry_drift_atr
from scenarios.proposer import AnchorEvent, ProposalOutcome, ScenarioProposer
from schemas import EventType, Scenario, ScenarioState, ScenarioTemplate
from schemas.liquidity import BreakAcceptEventPayload, SweepEventPayload

BUFFER = 0.5 * ATR  # العازلة الافتراضية من الإعداد


# ───────────────────────── §18.5 الإبطال ─────────────────────────


class TestStructuralBreach:
    """الشرطان 1/3: القبول عبر منطقة الإبطال — إغلاق لا فتيل."""

    def test_long_invalidated_by_close_below(self) -> None:
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()  # إبطاله 59_600 بعازلة 100
        # إغلاق دون 59_500 — قبول كامل عبر المستوى
        breaching = make_candle(1, open_=59_650.0, high=59_700.0, low=59_450.0, close=59_480.0)
        verdict = evaluator.check(reversal, candle=breaching)
        assert verdict is not None
        assert verdict.state is ScenarioState.INVALIDATED
        assert "شرط 1/3" in verdict.reason

    def test_wick_below_does_not_invalidate(self) -> None:
        """accept_through=True: الفتيل وحده لا يبطِل — إغلاق يُطلب."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        # فتيل عميق دون الإغلاق فوق مستوى الأمان
        wick = make_candle(1, open_=59_700.0, high=59_750.0, low=59_550.0, close=59_720.0)
        assert evaluator.check(reversal, candle=wick) is None

    def test_short_invalidated_by_close_above(self) -> None:
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        breakout = _breakout_from_sweep()  # إبطاله 59_900 بعازلة 100
        breaching = make_candle(1, open_=59_950.0, high=60_050.0, low=59_900.0, close=60_020.0)
        verdict = evaluator.check(breakout, candle=breaching)
        assert verdict is not None
        assert verdict.state is ScenarioState.INVALIDATED
        assert "فوق المستوى البنيوي 59900.00" in verdict.reason

    def test_touch_mode_wick_suffices(self) -> None:
        """accept_through=False: اللمس يكفي — عقد الحقل منذ المرحلة 0."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        scenario = _reversal().model_copy(
            update={
                "invalidation": _reversal().invalidation.model_copy(
                    update={"accept_through": False}
                )
            }
        )
        wick = make_candle(1, open_=59_700.0, high=59_750.0, low=59_650.0, close=59_720.0)
        # الفتيل دون level−buffer؟ 59_650 > 59_500 — لا. نحتاج فتيلًا أعمق:
        deep_wick = make_candle(1, open_=59_700.0, high=59_750.0, low=59_450.0, close=59_720.0)
        assert evaluator.check(scenario, candle=wick) is None
        assert evaluator.check(scenario, candle=deep_wick) is not None


class TestOpposingLiquidityEvent:
    """الشرط 2: فشل حدث الأطروحة بالاتجاه المعاكس — كسر-قبول على المرسِم."""

    def test_reversal_killed_by_zone_acceptance(self) -> None:
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        accept = make_break_accept_payload()  # على lz-sell-001 نفسها
        verdict = evaluator.check(
            reversal,
            candle=make_candle(1),
            events=((EventType.BREAK_AND_ACCEPT_LOW, accept),),
        )
        assert verdict is not None
        assert verdict.state is ScenarioState.INVALIDATED
        assert "شرط 2" in verdict.reason

    def test_breakout_not_killed_by_same_event(self) -> None:
        """أطروحة الاختراق القبولُ نفسه — الحادث تأكيد له لا فشل."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        breakout = _breakout_from_sweep()
        accept = make_break_accept_payload()
        verdict = evaluator.check(
            breakout,
            candle=make_candle(1),
            events=((EventType.BREAK_AND_ACCEPT_LOW, accept),),
        )
        # لا حدث معاكس (الاختراق غير مشروط بالرفض) — ولا قبول سعري بعد
        assert verdict is None

    def test_foreign_zone_acceptance_ignored(self) -> None:
        """قبول على منطقة أخرى لا يقتل الأطروحة — الربط بمعرف المرسِم."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        foreign = make_break_accept_payload(zone_id="lz-elsewhere")
        verdict = evaluator.check(
            reversal,
            candle=make_candle(1),
            events=((EventType.BREAK_AND_ACCEPT_LOW, foreign),),
        )
        assert verdict is None


class TestTimingAndQuality:
    """الشرطان 4/5: الانقضاء وجودة البيانات — عبر أعلام المحرك."""

    def test_expired_is_expiring_state(self) -> None:
        """الانقضاء حالة EXPIRED متخصصة — لا صورة من الإبطال (§18.2)."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        verdict = evaluator.check(reversal, candle=make_candle(1), expired=True)
        assert verdict is not None
        assert verdict.state is ScenarioState.EXPIRED
        assert "شرط 4" in verdict.reason

    def test_unsafe_quality_is_cancellation_state(self) -> None:
        """الجودة غير الآمنة إلغاء متخصص — CANCELLED_BY_DATA_QUALITY (§18.2)."""
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        verdict = evaluator.check(reversal, candle=make_candle(1), data_quality_unsafe=True)
        assert verdict is not None
        assert verdict.state is ScenarioState.CANCELLED_BY_DATA_QUALITY
        assert "شرط 5" in verdict.reason


class TestEntryDrift:
    """حارس الانجراف §18.4 — «moved too far from the planned entry»."""

    def test_drift_zero_inside_zone(self) -> None:
        reversal = _reversal()  # دخول [59_800, 59_900]
        assert entry_drift_atr(reversal, close=59_850.0, atr=ATR) == 0.0

    def test_drift_measured_outside(self) -> None:
        reversal = _reversal()
        # إغلاق 400 دون الحافة السفلى ⇒ انجراف 2.0 ATR
        assert entry_drift_atr(reversal, close=59_400.0, atr=ATR) == pytest.approx(2.0)

    def test_drift_exceeded_reason(self) -> None:
        evaluator = InvalidationEvaluator(max_entry_drift_atr=2.0)
        reversal = _reversal()
        verdict = evaluator.check(reversal, candle=make_candle(1), entry_drift_exceeded=True)
        assert verdict is not None
        assert verdict.state is ScenarioState.INVALIDATED
        assert "شرط 6" in verdict.reason
        assert "§25.2" in verdict.reason  # التأجيل المكلف موثق لا صامت

    def test_non_positive_atr_rejected(self) -> None:
        reversal = _reversal()
        try:
            entry_drift_atr(reversal, close=59_400.0, atr=0.0)
        except ValueError as exc:
            assert "ATR غير موجب" in str(exc)
        else:
            raise AssertionError("ATR صفري قبل بدون رفض")


# ───────────────────────── 7.4 التنافس ─────────────────────────


class TestPrecedence:
    """مفتاح الأسبقية: المجموعات ثم الدرجة ثم المعرف — أصغر يفوز."""

    def test_more_supporting_groups_win(self) -> None:
        strong = CompetingScenario(_reversal(), supporting_groups=3)
        weak = CompetingScenario(_breakout_from_sweep(), supporting_groups=1)
        assert precedence_key(strong) < precedence_key(weak)

    def test_score_breaks_group_tie(self) -> None:
        first = CompetingScenario(_reversal(), supporting_groups=2)
        second = CompetingScenario(
            _reversal().model_copy(update={"scenario_score": 0.9}), supporting_groups=2
        )
        assert precedence_key(second) < precedence_key(first)

    def test_id_breaks_full_tie(self) -> None:
        base = _reversal()
        left = CompetingScenario(base, supporting_groups=2)
        right = CompetingScenario(
            base.model_copy(update={"scenario_id": "zzz-last"}), supporting_groups=2
        )
        assert precedence_key(left) < precedence_key(right)  # الأصغر معجميًا


class TestConflictResolution:
    """الحسم بالأسبقية لا الإلغاء الصامت — الخاسر يعلن فائزه."""

    def test_opposites_resolve_with_suppression_reason(self) -> None:
        long_scenario = _reversal().model_copy(update={"state": ScenarioState.TRIGGERED})
        short_scenario = _breakout_from_sweep().model_copy(
            update={"state": ScenarioState.TRIGGERED}
        )
        outcome = resolve_conflicts(
            [
                CompetingScenario(long_scenario, supporting_groups=2),
                CompetingScenario(short_scenario, supporting_groups=1),
            ]
        )
        assert len(outcome.suppressions) == 1
        loser, winner, reason = outcome.suppressions[0]
        assert loser.scenario_id == short_scenario.scenario_id
        assert winner.scenario_id == long_scenario.scenario_id
        assert "لا إلغاء صامت" in reason
        assert winner.scenario_id in reason  # الفائز مسمى
        assert outcome.survivors == (long_scenario,)

    def test_same_direction_no_conflict(self) -> None:
        """الاتجاه الواحد لا يتنافس على الترخيص — التعرض شأن المخاطرة."""
        first = _reversal().model_copy(update={"state": ScenarioState.TRIGGERED})
        second = _reversal().model_copy(
            update={"scenario_id": "sc-other-long", "state": ScenarioState.TRIGGERED}
        )
        outcome = resolve_conflicts([CompetingScenario(first, 2), CompetingScenario(second, 2)])
        assert outcome.suppressions == ()
        assert len(outcome.survivors) == 2

    def test_two_longs_both_survive_against_weak_short(self) -> None:
        """القصمان قد يقهران قصيرًا واحدًا — قرار أزواج موضوعي."""
        long_a = _reversal().model_copy(update={"state": ScenarioState.TRIGGERED})
        long_b = _reversal().model_copy(
            update={"scenario_id": "sc-long-b", "state": ScenarioState.TRIGGERED}
        )
        short_weak = _breakout_from_sweep().model_copy(update={"state": ScenarioState.TRIGGERED})
        outcome = resolve_conflicts(
            [
                CompetingScenario(long_a, supporting_groups=3),
                CompetingScenario(long_b, supporting_groups=2),
                CompetingScenario(short_weak, supporting_groups=1),
            ]
        )
        assert len(outcome.suppressions) == 1
        loser, _winner, _reason = outcome.suppressions[0]
        assert loser.scenario_id == short_weak.scenario_id
        assert {s.scenario_id for s in outcome.survivors} == {
            long_a.scenario_id,
            long_b.scenario_id,
        }

    def test_strong_short_suppresses_both_longs(self) -> None:
        long_a = _reversal().model_copy(update={"state": ScenarioState.TRIGGERED})
        long_b = _reversal().model_copy(
            update={"scenario_id": "sc-long-b", "state": ScenarioState.TRIGGERED}
        )
        short_strong = _breakout_from_sweep().model_copy(
            update={"state": ScenarioState.TRIGGERED, "scenario_score": 0.95}
        )
        outcome = resolve_conflicts(
            [
                CompetingScenario(long_a, supporting_groups=1),
                CompetingScenario(long_b, supporting_groups=1),
                CompetingScenario(short_strong, supporting_groups=3),
            ]
        )
        suppressed_ids = {loser.scenario_id for loser, _w, _r in outcome.suppressions}
        assert suppressed_ids == {long_a.scenario_id, long_b.scenario_id}
        assert outcome.survivors == (short_strong,)


# ───────────────────────── مساعدات ─────────────────────────


def _propose(
    payload: SweepEventPayload | BreakAcceptEventPayload, event_type: EventType
) -> ProposalOutcome:
    proposer = ScenarioProposer()
    return proposer.propose(
        AnchorEvent(event_type, ANCHOR_TIME, payload),
        zone=sell_zone(),
        targets=make_target_map(),
        state=make_market_state(),
        atr=ATR,
    )


def _reversal() -> Scenario:
    outcome = _propose(make_sweep_payload(), EventType.LIQUIDITY_SWEEP_LOW)
    (scenario,) = [s for s in outcome.proposals if s.template is ScenarioTemplate.REVERSAL]
    return scenario


def _breakout_from_sweep() -> Scenario:
    outcome = _propose(make_sweep_payload(), EventType.LIQUIDITY_SWEEP_LOW)
    (scenario,) = [s for s in outcome.proposals if s.template is ScenarioTemplate.BREAKOUT]
    return scenario
