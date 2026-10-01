"""اختبارات دفتر التجارب (§29.1) — القياس والحتمية والأساس الموثق.

البوابة 8.6: كتابة سجل التجربة عند إغلاق أي سيناريو مُقيَّم — بنية
السبعة عشر حقلاً كاملة، وMFE/MAE بوحدات R من الدخول المخطط، والمرفوض
يُسجل بأصفار موثقة لا بأرقام مختلقة.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from _risk_fixtures import (
    ATR,
    DECISION_TIME,
    decision_candle,
    fusion_snapshot_for,
    healthy_context,
    triggered_scenario,
)
from learning.ledger import (
    build_experience_record,
    experience_id_for,
    measure_excursions,
)
from risk.engine import RiskEngine
from schemas import (
    Candle,
    Direction,
    EvidenceRecord,
    RiskDecision,
    Scenario,
    ScenarioState,
    ScenarioTransition,
    SessionType,
)


def _authorized_setup() -> tuple[Scenario, RiskDecision, list[EvidenceRecord]]:
    """سيناريو مُرخَّص بقرار كامل — أساس قياس الصفقة الورقية."""
    scenario = triggered_scenario()
    snapshot, records = fusion_snapshot_for(scenario)
    engine = RiskEngine()
    evaluation = engine.evaluate(
        scenario,
        snapshot=snapshot,
        records=records,
        market_state=scenario.context_snapshot,
        candle=decision_candle(),
        atr=ATR,
        context=healthy_context(),
        trigger_reason="مشغل DISPLACEMENT_CONFIRM رُصد",
    )
    assert evaluation.decision.approved
    return scenario, evaluation.decision, records


def _closing_transition(
    scenario_id: str,
    from_state: ScenarioState,
    to_state: ScenarioState,
    *,
    reason: str,
    minutes_after_decision: float,
) -> ScenarioTransition:
    return ScenarioTransition(
        scenario_id=scenario_id,
        from_state=from_state,
        to_state=to_state,
        transition_time=DECISION_TIME + timedelta(minutes=minutes_after_decision),
        reason=reason,
    )


def _path_candles(count: int, *, base: float = 59_880.0, drift: float = 40.0) -> list[Candle]:
    """شموع مسار بعد القرار — بداية عند الدقيقة 2 (بعد شمعة القرار)."""
    candles = []
    for index in range(2, 2 + count):
        close = base + drift * (index - 1)
        minute = DECISION_TIME + timedelta(minutes=index - 1)
        candles.append(decision_candle(close=close, bar_time=minute))
    return candles


class TestExcursionMeasurement:
    """MFE/MAE بوحدات R — من الدخول المخطط عبر مسار السوق."""

    def test_long_favorable_and_adverse(self) -> None:
        # مسار مختلط: هبوط أول (mae) ثم صعود (mfe) — كل جهة تقاس
        closes = [59_870.0, 59_950.0, 60_010.0]
        candles = [
            decision_candle(
                close=close,
                bar_time=DECISION_TIME + timedelta(minutes=minute),
            )
            for minute, close in enumerate(closes, start=1)
        ]
        mfe, mae = measure_excursions(
            candles,
            entry_reference=59_900.0,
            stop_distance=400.0,
            direction=Direction.LONG,
        )
        # أعلى قمة: الشمعة الأخيرة close=60_010 وhigh=60_040
        assert mfe == pytest.approx((60_040.0 - 59_900.0) / 400.0)
        # أدنى قاع: الشمعة الأولى low = 59_850
        assert mae == pytest.approx((59_900.0 - 59_850.0) / 400.0)

    def test_empty_path_is_zero_zero(self) -> None:
        mfe, mae = measure_excursions(
            [], entry_reference=59_900.0, stop_distance=400.0, direction=Direction.LONG
        )
        assert (mfe, mae) == (0.0, 0.0)

    def test_nonpositive_stop_distance_is_loud(self) -> None:
        with pytest.raises(ValueError, match="غير موجبة"):
            measure_excursions(
                _path_candles(1),
                entry_reference=59_900.0,
                stop_distance=0.0,
                direction=Direction.LONG,
            )


class TestExperienceRecordConstruction:
    """بنية §29.1 — سبعة عشر حقلاً بمصادر موثقة."""

    def test_authorized_then_invalidated_full_measurement(self) -> None:
        scenario, decision, records = _authorized_setup()
        closed = scenario.model_copy(update={"state": ScenarioState.INVALIDATED})
        # مسار صاعد قليلاً ثم هابط — MFE من أول شمعة وMAE من آخرها
        closes = [59_940.0, 59_910.0, 59_840.0, 59_760.0, 59_680.0]
        path = [
            decision_candle(
                close=close,
                bar_time=DECISION_TIME + timedelta(minutes=minute),
            )
            for minute, close in enumerate(closes, start=1)
        ]
        closing = _closing_transition(
            scenario.scenario_id,
            ScenarioState.AUTHORIZED,
            ScenarioState.INVALIDATED,
            reason="إبطال §18.5: قبول خلف المستوى البنيوي 59600.0",
            minutes_after_decision=5.0,
        )
        record = build_experience_record(
            closed,
            decision=decision,
            closing_transition=closing,
            records=records,
            market_path=path,
            session=SessionType.UTC_DAY,
        )
        # exit_reason حرفي من انتقال النهاية — التوثيق يعاد استهلاكه
        assert record.exit_reason == closing.reason
        assert record.holding_time == pytest.approx(300.0)
        assert record.mfe > 0.0  # الشمعة الأولى صاعدة قبل الهبوط
        assert record.mae > 0.0
        # قياس ورقي: الخروج عند إغلاق شمعة النهاية
        exit_price = float(path[-1].close)
        assert decision.sizing is not None and decision.stop is not None
        size = decision.sizing.position_size
        entry = decision.stop.entry_reference
        assert record.gross_pnl == pytest.approx((exit_price - entry) * size)
        assert record.costs > 0.0
        assert record.net_pnl == pytest.approx(record.gross_pnl - record.costs)
        assert record.net_r < 0.0  # هبوط وإبطال — صفقة خاسرة ورقيًا
        assert record.risk_snapshot is decision  # مشدود نموذجيًا (المرحلة 8)
        assert record.execution_snapshot["position_taken"] is True
        assert record.execution_snapshot["exit_price"] == exit_price
        assert record.session is SessionType.UTC_DAY

    def test_rejected_scenario_recorded_with_documented_zeros(self) -> None:
        """المرفوض: لا صفقة قامت — الحقول التنفيذية أصفار موثقة."""
        scenario = triggered_scenario()
        snapshot, records = fusion_snapshot_for(scenario)
        engine = RiskEngine()
        evaluation = engine.evaluate(
            scenario,
            snapshot=snapshot,
            records=records,
            market_state=scenario.context_snapshot,
            candle=decision_candle(),
            atr=ATR,
            context=healthy_context(kill_switch=True),
        )
        assert not evaluation.decision.approved
        rejected_scenario = scenario.model_copy(update={"state": ScenarioState.REJECTED_BY_RISK})
        record = build_experience_record(
            rejected_scenario,
            decision=evaluation.decision,
            closing_transition=ScenarioTransition(
                scenario_id=scenario.scenario_id,
                from_state=ScenarioState.TRIGGERED,
                to_state=ScenarioState.REJECTED_BY_RISK,
                transition_time=DECISION_TIME,
                reason=evaluation.transition_reason,
            ),
            records=records,
            market_path=[],
        )
        assert record.mfe == 0.0 and record.mae == 0.0
        assert record.holding_time == 0.0
        assert record.gross_pnl == 0.0
        assert record.costs == 0.0
        assert record.net_pnl == 0.0 and record.net_r == 0.0
        assert record.execution_snapshot["position_taken"] is False
        assert record.exit_reason == evaluation.transition_reason
        # قيمة المرفوض الإسنادية: سلسلة الدليل التي كادت ترخّصه محفوظة
        assert record.evidence_snapshot == list(records)

    def test_experience_id_deterministic_per_scenario(self) -> None:
        scenario, _decision, _records = _authorized_setup()
        first = experience_id_for(scenario.scenario_id)
        second = experience_id_for(scenario.scenario_id)
        assert first == second
        assert first != experience_id_for("scenario-آخر")

    def test_decision_without_stop_is_loud(self) -> None:
        """قرار بلا وقف لا يُقاس — رفض صاخب لا تفييم صامت."""
        scenario, decision, records = _authorized_setup()
        stopless: RiskDecision = decision.model_copy(update={"stop": None})
        with pytest.raises(ValueError, match="بلا وقف"):
            build_experience_record(
                scenario,
                decision=stopless,
                closing_transition=_closing_transition(
                    scenario.scenario_id,
                    ScenarioState.AUTHORIZED,
                    ScenarioState.INVALIDATED,
                    reason="إبطال",
                    minutes_after_decision=5.0,
                ),
                records=records,
                market_path=_path_candles(2),
            )

    def test_record_is_frozen(self) -> None:
        scenario, decision, records = _authorized_setup()
        closed = scenario.model_copy(update={"state": ScenarioState.INVALIDATED})
        record = build_experience_record(
            closed,
            decision=decision,
            closing_transition=_closing_transition(
                scenario.scenario_id,
                ScenarioState.AUTHORIZED,
                ScenarioState.INVALIDATED,
                reason="إبطال",
                minutes_after_decision=3.0,
            ),
            records=records,
            market_path=_path_candles(2),
        )
        with pytest.raises(Exception, match=r"frozen|immutable|Cannot|Instance"):
            # تعيين ديناميكي: يرفضه النموذج المجمّد وقت التشغيل (mypy يمنع
            # التعيين الساكن على الخاصية للقراءة فقط — العقد مفروض طبقتين)
            setattr(record, "exit_reason", "تحريف")  # noqa: B010
