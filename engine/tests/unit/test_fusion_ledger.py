"""اختبارات باني سجل الدليل — الاصطفاف والارتباط والطراوة (§19).

العقود المفحوصة:

- الاصطفاف النسبي: direction_score = قطبية الحدث × إشارة السيناريو —
  المتحالف +1 والمعاكس −1 داخل قائمة المعارضة الصريحة (§19.5)،
  ومرآة SHORT كاملة، وFLAT مرفوض؛
- مجموعات الارتباط (§19.4): دفعة الشمعة الواحدة (نفس الأداة/الإطار/
  التأكيد) تُخصم هندسيًا بترتيب إمكانات المساهمة (1، γ، γ²، γ³) مع كسر
  تعادل حتمي بالمعرف — والدفعة تمتد عبر المجموعات (اندفاع واحد يولد
  حدث بنية وحدث تدفق)؛ والشموع والإطارات المختلفة دفعات مستقلة؛
- الحقنة الحرفية: «دفعة واحدة تنتج 4 أحداث» لا ترفع أي مجموعة فوق
  سقفها الفعلي (بوابة 6.3)؛
- الطراوة (§19.1): كاملة عند التأكيد، نصف عند نصف العمر، صفر بعده —
  بمقياس إطار الحدث نفسه (1h أبقى من 1m)، والحدث الأحدث من لحظة
  القرار يُرفض صاخبًا (لا-نظرة §26.3)؛
- دليل الانحياز المشتق من الحالة: مؤكدٌ يدخل بنية بمصدر معلن
  (market_state.htf_bias) ويعارض عند العكس، وغير المؤكد لا يُختلق؛
- الحتمية: بناءان من المدخلات نفسها ⇒ السجل نفسه بايت-بايت؛ والمعرفات
  حتمية مشتقة من (السيناريو، الحدث) — سيناريو آخر لا يسرب معرفات؛
- الحرس: الحجب الصلب يُرفض، والإطار غير المدعوم يُرفض، والإعداد مصدر
  الجودة ومعدّل السياق.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from _fusion_fixtures import (
    BASE_TIME,
    INSTRUMENT,
    TIMEFRAME,
    make_absorption,
    make_candle_pattern,
    make_displacement,
    make_structure_break,
)
from fusion.compute import FusionEngine
from fusion.ledger import EvidenceLedgerBuilder, evidence_id_for
from fusion.parameter_sets import FusionConfig
from pydantic import BaseModel
from schemas import (
    DataQuality,
    Direction,
    EventType,
    EvidenceGroup,
    HTFBias,
    MarketRegime,
    MarketStateSnapshot,
)

GAMMA = 0.5  # γ الافتراضي في الإعداد


@dataclass(frozen=True)
class Ev:
    """حدث مكشوف اختباري — العقد الثلاثي نفسه الذي تنتجه الكواشف."""

    event_type: EventType
    event_time: datetime
    payload: BaseModel


def _state(
    bias: HTFBias = HTFBias.BULLISH,
    *,
    event_time: datetime = BASE_TIME,
    timeframe: str = TIMEFRAME,
) -> MarketStateSnapshot:
    """لقطة حالة سوق موثوقة الحقول."""
    return MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe=timeframe,
        event_time=event_time,
        regime=MarketRegime.TREND_EXPANSION,
        htf_bias=bias,
        volatility_percentile=70.0,
        data_quality=DataQuality.HEALTHY,
    )


# ───────────────────────── الاصطفاف النسبي ─────────────────────────


class TestScenarioAlignment:
    """direction_score نسبي للسيناريو — والمعارضة قائمة صريحة."""

    def test_long_scenario_bullish_supported(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert records[0].direction_score == 1.0
        assert records[0].opposition is False

    def test_long_scenario_bearish_opposes(self) -> None:
        builder = EvidenceLedgerBuilder()
        down = make_structure_break(break_direction="DOWN")
        records = builder.build(
            [Ev(EventType.INTERNAL_BOS, BASE_TIME, down)],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert records[0].direction_score == -1.0
        assert records[0].opposition is True

    def test_short_scenario_mirror(self) -> None:
        """المرآة الكاملة: الهابط يساند SHORT والصاعد يعارضه."""
        builder = EvidenceLedgerBuilder()
        down = make_structure_break(break_direction="DOWN")
        records = builder.build(
            [
                Ev(EventType.INTERNAL_BOS, BASE_TIME, down),
                Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break()),
            ],
            scenario_id="scn",
            direction=Direction.SHORT,
            as_of=BASE_TIME,
        )
        assert records[0].direction_score == 1.0
        assert records[0].opposition is False
        assert records[1].direction_score == -1.0
        assert records[1].opposition is True

    def test_flat_direction_rejected(self) -> None:
        builder = EvidenceLedgerBuilder()
        with pytest.raises(ValueError, match="غير اتجاهي"):
            builder.build(
                [],
                scenario_id="scn",
                direction=Direction.FLAT,
                as_of=BASE_TIME,
            )

    def test_neutral_polarity_zero_direction(self) -> None:
        """قطبية محايدة (شمعة اتجاهها NEUTRAL) ⇒ سجل صفري المساهمة."""
        builder = EvidenceLedgerBuilder()
        neutral = make_candle_pattern(direction="NEUTRAL")
        records = builder.build(
            [Ev(EventType.REJECTION_CANDLE, BASE_TIME, neutral)],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert records[0].direction_score == 0.0
        assert records[0].opposition is False


# ──────────────────── مجموعات الارتباط — §19.4 ────────────────────


class TestCorrelationBatches:
    """دفعة الشمعة الواحدة تُخصم هندسيًا — عبر المجموعات أيضًا."""

    def test_same_bar_events_share_batch_and_decay(self) -> None:
        """أربعة أحداث عند الشمعة نفسها: 1، γ، γ²، γ³ بترتيب الإمكانات."""
        builder = EvidenceLedgerBuilder()
        events = [
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break(breach_distance_atr=3.0)),
            Ev(EventType.DISPLACEMENT_UP, BASE_TIME, make_displacement(range_zscore=2.0)),
            Ev(
                EventType.ABSORPTION_BUY,
                BASE_TIME,
                make_absorption(delta_share=-0.9),
            ),
            Ev(EventType.BULLISH_ENGULFING, BASE_TIME, make_candle_pattern(strength=0.9)),
        ]
        records = builder.build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME
        )
        # الدفعة واحدة: معرف الارتباط مشترك
        assert len({r.correlation_group_id for r in records}) == 1
        # الخصم الهندسي بترتيب الإمكانات: {1.0, 0.5, 0.25, 0.125} بالضبط
        discounts = sorted((r.independence_discount for r in records), reverse=True)
        assert discounts == [1.0, GAMMA, GAMMA**2, GAMMA**3]

    def test_different_bars_independent(self) -> None:
        """شموع مختلفة دفعات مختلفة — خصم 1.0 للجميع."""
        builder = EvidenceLedgerBuilder()
        events = [
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break()),
            Ev(
                EventType.EXTERNAL_BOS,
                BASE_TIME + timedelta(minutes=1),
                make_structure_break(1),
            ),
        ]
        records = builder.build(
            events,
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(minutes=1),
        )
        assert records[0].correlation_group_id != records[1].correlation_group_id
        assert all(r.independence_discount == 1.0 for r in records)

    def test_different_timeframes_independent(self) -> None:
        """الإطار نفسه التأكيد وإن تطابق الحائط الزمني."""
        builder = EvidenceLedgerBuilder()
        htf_break = make_structure_break().model_copy(update={"timeframe": "1h"})
        events = [
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break()),
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, htf_break),
        ]
        records = builder.build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME
        )
        assert records[0].correlation_group_id != records[1].correlation_group_id
        assert all(r.independence_discount == 1.0 for r in records)

    def test_rank_tiebreak_by_evidence_id(self) -> None:
        """إمكانات متساوٍ ⇒ الترتيب بالمعرف (حتمية تامة)."""
        builder = EvidenceLedgerBuilder()
        events = [
            Ev(EventType.BULLISH_ENGULFING, BASE_TIME, make_candle_pattern(strength=0.5)),
            Ev(EventType.BEARISH_ENGULFING, BASE_TIME, make_candle_pattern(strength=0.5)),
        ]
        records = builder.build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME
        )
        by_id = {r.evidence_id: r.independence_discount for r in records}
        first = min(by_id)
        assert by_id[first] == 1.0
        assert sum(1 for discount in by_id.values() if discount == GAMMA) == 1

    def test_state_evidence_outside_batches(self) -> None:
        """دليل الانحياز المشتق من الحالة خارج دفعات الأحداث (خصم 1.0)."""
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
            market_state=_state(),
        )
        htf = records[0]
        assert htf.source == "market_state.htf_bias"
        assert htf.correlation_group_id is None
        assert htf.independence_discount == 1.0

    def test_batch_injection_never_exceeds_group_cap(self) -> None:
        """بوابة 6.3 حرفيًا: «دفعة واحدة تنتج 4 أحداث» لا ترفع الدرجة
        فوق سقف المجموعة — أربعة أحداث بنية قوية عند شمعة واحدة."""
        builder = EvidenceLedgerBuilder()
        events = [
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break(breach_distance_atr=5.0)),
            Ev(EventType.DISPLACEMENT_UP, BASE_TIME, make_displacement(range_zscore=4.0)),
            Ev(EventType.CHOCH, BASE_TIME, make_structure_break(breach_distance_atr=4.0)),
            Ev(EventType.INTERNAL_BOS, BASE_TIME, make_structure_break(breach_distance_atr=3.0)),
        ]
        records = builder.build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME
        )
        # كل الأربعة في البنية (والبقية غائبة ⇒ سقف البنية الفعلي 1.0)
        assert {r.group for r in records} == {EvidenceGroup.STRUCTURE}
        discounts = sorted((r.independence_discount for r in records), reverse=True)
        assert discounts == [1.0, GAMMA, GAMMA**2, GAMMA**3]
        snapshot = FusionEngine().compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=BASE_TIME
        )
        (structure,) = snapshot.group_scores
        assert structure.score <= structure.effective_share
        # وبلا خصم كانت أعلى — الخصم يفعل شيئًا والسقف يحمي
        undiscounted = [r.model_copy(update={"independence_discount": 1.0}) for r in records]
        free = FusionEngine().compute(
            undiscounted, scenario_id="scn", direction=Direction.LONG, fusion_time=BASE_TIME
        )
        assert structure.score < free.group_scores[0].score


# ───────────────────────── الطراوة — §19.1 ─────────────────────────


class TestFreshness:
    """اضمحلال خطي بمقياس إطار الحدث — وحرس اللا-نظرة."""

    def test_full_at_confirmation(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert records[0].freshness == 1.0

    def test_half_at_half_ttl(self) -> None:
        """1m بعمر 60 شمعة (3600s): عند 1800s ⇒ طراوة 0.5."""
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(seconds=1800),
        )
        assert records[0].freshness == pytest.approx(0.5)

    def test_zero_beyond_ttl(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(hours=2),
        )
        assert records[0].freshness == 0.0

    def test_timeframe_scales_ttl(self) -> None:
        """الإطار الأعلى أبقى: نفس العمر الزمني، طراوة 1h أعلى من 1m."""
        builder = EvidenceLedgerBuilder()
        htf_break = make_structure_break().model_copy(update={"timeframe": "1h"})
        records = builder.build(
            [
                Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break()),
                Ev(EventType.EXTERNAL_BOS, BASE_TIME, htf_break),
            ],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(hours=1),
        )
        assert records[1].freshness > records[0].freshness
        # 1m: عمر 3600s / أجل 60 شمعة × 60s = 3600s ⇒ طراوة صفر بالضبط
        assert records[0].freshness == pytest.approx(1.0 - 3600.0 / (60.0 * 60.0))
        assert records[0].freshness == 0.0
        # 1h: نفس العمر مقابل أجل 60 شمعة × 3600s = 216000s ⇒ 0.98333
        assert records[1].freshness == pytest.approx(1.0 - 3600.0 / (60.0 * 3600.0))

    def test_future_event_rejected(self) -> None:
        """حدث أحدث من لحظة القرار خرق اللا-نظرة — رفض صاخب."""
        builder = EvidenceLedgerBuilder()
        with pytest.raises(ValueError, match=r"لا-نظرة|أحدث"):
            builder.build(
                [
                    Ev(
                        EventType.EXTERNAL_BOS,
                        BASE_TIME + timedelta(minutes=5),
                        make_structure_break(),
                    )
                ],
                scenario_id="scn",
                direction=Direction.LONG,
                as_of=BASE_TIME,
            )

    def test_future_state_rejected(self) -> None:
        builder = EvidenceLedgerBuilder()
        future_state = _state(event_time=BASE_TIME + timedelta(minutes=5))
        with pytest.raises(ValueError, match=r"لا-نظرة|أحدث"):
            builder.build(
                [],
                scenario_id="scn",
                direction=Direction.LONG,
                as_of=BASE_TIME,
                market_state=future_state,
            )


# ─────────────────── دليل الانحياز المشتق من الحالة ───────────────────


class TestHtfStateEvidence:
    """§9.2: الانحياز سياقي — يدخل الدمج دليلًا مشتقًا من الحالة معلنًا."""

    def test_confirmed_bias_supports_long(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [], scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME, market_state=_state()
        )
        (htf,) = records
        assert htf.event_type is EventType.HTF_BULLISH
        assert htf.group is EvidenceGroup.STRUCTURE
        assert htf.direction_score == 1.0
        assert htf.prior_weight == 0.90
        assert htf.raw_strength == 1.0  # حالة مؤكدة ثنائية — الوزن يحمل المقدار
        assert htf.source == "market_state.htf_bias"

    def test_bearish_bias_opposes_long(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
            market_state=_state(bias=HTFBias.BEARISH),
        )
        assert records[0].event_type is EventType.HTF_BEARISH
        assert records[0].direction_score == -1.0
        assert records[0].opposition is True

    @pytest.mark.parametrize("bias", [HTFBias.NEUTRAL, HTFBias.TRANSITION, HTFBias.UNKNOWN])
    def test_unconfirmed_bias_not_invented(self, bias: HTFBias) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
            market_state=_state(bias),
        )
        assert records == []

    def test_no_state_no_htf_record(self) -> None:
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert all(r.source != "market_state.htf_bias" for r in records)

    def test_state_comes_first_in_chain(self) -> None:
        """السياق يسبق الأحداث — ترتيب السجل حتمي."""
        builder = EvidenceLedgerBuilder()
        records = builder.build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
            market_state=_state(),
        )
        assert records[0].source == "market_state.htf_bias"
        assert records[1].source == "analysis-event:EXTERNAL_BOS"


# ───────────────────────── الحتمية والمعرفات ─────────────────────────


class TestLedgerDeterminism:
    """لا ساعة ولا عشوائية — والمعرفات مشتقة مشتملة على السيناريو."""

    def test_same_inputs_same_ledger(self) -> None:
        events = [
            Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break()),
            Ev(
                EventType.ABSORPTION_BUY,
                BASE_TIME + timedelta(minutes=1),
                make_absorption(1),
            ),
        ]
        first = EvidenceLedgerBuilder().build(
            events,
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(minutes=2),
        )
        second = EvidenceLedgerBuilder().build(
            events,
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME + timedelta(minutes=2),
        )
        assert [r.model_dump_json() for r in first] == [r.model_dump_json() for r in second]

    def test_evidence_id_deterministic_and_scenario_scoped(self) -> None:
        key = "EXTERNAL_BOS|X|1m|2026-01-05T00:00:00+00:00"
        assert evidence_id_for("scn-a", key) == evidence_id_for("scn-a", key)
        assert evidence_id_for("scn-a", key) != evidence_id_for("scn-b", key)

    def test_evidence_id_stable_across_rebuilds(self) -> None:
        """إعادة بناء السجل تعطي المعرفات نفسها — idempotent بالبناء."""
        events = [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())]
        as_of = BASE_TIME + timedelta(minutes=1)
        first = EvidenceLedgerBuilder().build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=as_of
        )
        second = EvidenceLedgerBuilder().build(
            events, scenario_id="scn", direction=Direction.LONG, as_of=as_of
        )
        assert [r.evidence_id for r in first] == [r.evidence_id for r in second]


# ───────────────────────── الحرس والإعداد ─────────────────────────


class TestLedgerGuards:
    """رفض صاخب لكسر العقود — والإعداد مصدر الجودة ومعدّل السياق."""

    def test_hard_block_event_rejected(self) -> None:
        builder = EvidenceLedgerBuilder()
        stale = Ev(EventType.DATA_STALE, BASE_TIME, make_structure_break())
        with pytest.raises(ValueError, match="حجب صلب"):
            builder.build([stale], scenario_id="scn", direction=Direction.LONG, as_of=BASE_TIME)

    def test_unsupported_timeframe_rejected(self) -> None:
        builder = EvidenceLedgerBuilder()
        odd = make_structure_break().model_copy(update={"timeframe": "7m"})
        with pytest.raises(ValueError, match="إطار غير مدعوم"):
            builder.build(
                [Ev(EventType.EXTERNAL_BOS, BASE_TIME, odd)],
                scenario_id="scn",
                direction=Direction.LONG,
                as_of=BASE_TIME,
            )

    def test_quality_and_context_from_config(self) -> None:
        config = FusionConfig(default_quality=0.8, default_context_modifier=0.9)
        records = EvidenceLedgerBuilder(config).build(
            [Ev(EventType.EXTERNAL_BOS, BASE_TIME, make_structure_break())],
            scenario_id="scn",
            direction=Direction.LONG,
            as_of=BASE_TIME,
        )
        assert records[0].quality == 0.8
        assert records[0].context_modifier == 0.9
