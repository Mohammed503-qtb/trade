"""اختبارات خريطة الدليل — تجميع §19.3 وقطبية/قوة §20 من الحمولات.

العقود المفحوصة:

- التقسيم الكامل: الأنواع الـ45 موطنة كلها (41 دليلًا + 4 حجبًا صلبًا)
  بلا تداخل وبلا فجوة — والحدود بين الدليل والحجب حرفية من §20؛
- موطن كل عائلة بحرفية أعمدة Purpose في §19.3 (POC/VA في التدفق،
  الهارمونيك في حركة السعر، الجلسات في التقلب...)؛
- ترتيب المجموعات GROUP_ORDER = ترتيب جدول §19.3؛
- saturate: صفر ثابت، رتيبة صارمة، تحت الوحدة دائمًا، وترفض السالب؛
- أوزان §20 حرفية (EXTERNAL_BOS=1.00، الاجتياح=0.95، الابتلاع=0.35)
  والحجب الصلب يرفض وزنًا (D-03-د)؛
- القطبية من الحمولة لكل عائلة قيمًا يدوية (بما فيها انعكاس فشل الكسر
  وإنهاك الجهد ومعاكسة premium)؛
- القوة الخام = «Primary measurement» §20 بقيم محسوبة يدويًا لكل عائلة؛
- الأنواع بلا حمولة موثقة تُرفض صاخبة (غياب الحمولة إعلان صريح).
"""

from __future__ import annotations

import pytest
from _fusion_fixtures import (
    make_absorption,
    make_break_accept,
    make_candle_pattern,
    make_classical,
    make_displacement,
    make_exhaustion,
    make_flow_continuation,
    make_fvg,
    make_imbalance_cluster,
    make_order_block,
    make_premium_discount,
    make_structure_break,
    make_sweep,
)
from fusion.mapping import (
    EVENT_EVIDENCE_GROUPS,
    GROUP_ORDER,
    HARD_BLOCK_EVENT_TYPES,
    extract_polarity,
    extract_raw_strength,
    htf_event_for_bias,
    prior_weight_for,
    saturate,
)
from schemas import EventType, EvidenceGroup, HTFBias
from schemas.enums import DEFAULT_EVENT_WEIGHTS
from schemas.structure import StructureConsequence

FAILED = EventType.CLASSICAL_FAILED_BREAKOUT


# ───────────────────────── التقسيم الكامل §19.3 ─────────────────────────


class TestEvidenceGroupPartition:
    """45 نوعًا: 41 دليلًا موطنًا و4 حجبًا صلبًا — لا فجوة ولا تداخل."""

    def test_all_types_accounted_for(self) -> None:
        every = set(EventType)
        assert set(EVENT_EVIDENCE_GROUPS) | set(HARD_BLOCK_EVENT_TYPES) == every
        assert not (set(EVENT_EVIDENCE_GROUPS) & set(HARD_BLOCK_EVENT_TYPES))
        assert len(EVENT_EVIDENCE_GROUPS) == 41
        assert len(HARD_BLOCK_EVENT_TYPES) == 4

    def test_hard_blocks_are_exactly_weight_none(self) -> None:
        """حدود الدليل/الحجب حرفية من عمود Weight في §20."""
        for event_type, weight in DEFAULT_EVENT_WEIGHTS.items():
            if weight is None:
                assert event_type in HARD_BLOCK_EVENT_TYPES
            else:
                assert event_type in EVENT_EVIDENCE_GROUPS

    def test_group_purposes_literal(self) -> None:
        """عيّنات موطن بحرفية أعمدة Purpose (وليس حصرًا كاملًا)."""
        assert EVENT_EVIDENCE_GROUPS[EventType.HTF_BULLISH] is EvidenceGroup.STRUCTURE
        assert EVENT_EVIDENCE_GROUPS[EventType.CHOCH] is EvidenceGroup.STRUCTURE
        sweeps = EVENT_EVIDENCE_GROUPS[EventType.LIQUIDITY_SWEEP_HIGH]
        assert sweeps is EvidenceGroup.LIQUIDITY_LOCATION
        premium = EVENT_EVIDENCE_GROUPS[EventType.PREMIUM_LOCATION]
        assert premium is EvidenceGroup.LIQUIDITY_LOCATION
        assert EVENT_EVIDENCE_GROUPS[EventType.POC_ACCEPTANCE] is EvidenceGroup.ORDER_FLOW
        assert EVENT_EVIDENCE_GROUPS[EventType.VAH_REJECTION] is EvidenceGroup.ORDER_FLOW
        harmonic = EVENT_EVIDENCE_GROUPS[EventType.HARMONIC_COMPLETION]
        assert harmonic is EvidenceGroup.PRICE_ACTION
        compression = EVENT_EVIDENCE_GROUPS[EventType.RANGE_COMPRESSION]
        assert compression is EvidenceGroup.VOLATILITY_SESSION
        reversal = EVENT_EVIDENCE_GROUPS[EventType.SESSION_REVERSAL]
        assert reversal is EvidenceGroup.VOLATILITY_SESSION
        assert EVENT_EVIDENCE_GROUPS[EventType.MACRO_HIGH_IMPACT_NEAR] is EvidenceGroup.MACRO

    def test_group_order_matches_plan_table(self) -> None:
        """ترتيب المجموعات = ترتيب جدول §19.3 (البنية أولًا والكلي أخيرًا)."""
        assert GROUP_ORDER == (
            EvidenceGroup.STRUCTURE,
            EvidenceGroup.LIQUIDITY_LOCATION,
            EvidenceGroup.ORDER_FLOW,
            EvidenceGroup.PRICE_ACTION,
            EvidenceGroup.VOLATILITY_SESSION,
            EvidenceGroup.MACRO,
        )


class TestSaturate:
    """التشبع الرتيم الحتمي — x/(1+x)."""

    def test_known_values(self) -> None:
        assert saturate(0.0) == 0.0
        assert saturate(1.0) == pytest.approx(0.5)
        assert saturate(3.0) == pytest.approx(0.75)
        assert saturate(9.0) == pytest.approx(0.9)

    def test_strictly_monotone_and_bounded(self) -> None:
        previous = -1.0
        for i in range(65):
            value = saturate(float(i))
            assert 0.0 <= value < 1.0
            assert value > previous
            previous = value

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="موجب"):
            saturate(-0.1)


class TestPriorWeights:
    """الأوزان §20 حرفية — والحجب الصلب بلا وزن اتجاهي أصلًا."""

    @pytest.mark.parametrize(
        ("event_type", "weight"),
        [
            (EventType.EXTERNAL_BOS, 1.00),
            (EventType.LIQUIDITY_SWEEP_HIGH, 0.95),
            (EventType.CHOCH, 0.75),
            (EventType.FLOW_CONTINUATION_UP, 0.70),
            (EventType.BULLISH_ENGULFING, 0.35),
            (EventType.PREMIUM_LOCATION, 0.35),
            (EventType.POC_ACCEPTANCE, 0.45),
            (EventType.MACRO_HIGH_IMPACT_NEAR, 0.00),
        ],
    )
    def test_literal_weights(self, event_type: EventType, weight: float) -> None:
        assert prior_weight_for(event_type) == weight

    def test_hard_block_has_no_weight(self) -> None:
        with pytest.raises(ValueError, match="حجب صلب"):
            prior_weight_for(EventType.DATA_STALE)


class TestHtfBiasMapping:
    """الانحياز المنشور → حدث §20 الموازي (دليل مشتق من الحالة)."""

    def test_confirmed_biases_map(self) -> None:
        assert htf_event_for_bias(HTFBias.BULLISH) is EventType.HTF_BULLISH
        assert htf_event_for_bias(HTFBias.BEARISH) is EventType.HTF_BEARISH

    @pytest.mark.parametrize("bias", [HTFBias.NEUTRAL, HTFBias.TRANSITION, HTFBias.UNKNOWN])
    def test_unconfirmed_biases_are_not_evidence(self, bias: HTFBias) -> None:
        assert htf_event_for_bias(bias) is None


# ───────────────────────── القطبية من الحمولة ─────────────────────────


class TestPolarityExtraction:
    """القطبية الذاتية ∈ {−1, 0, +1} — من حقول الحمولة حصرًا بقيم يدوية."""

    def test_structure_break(self) -> None:
        assert extract_polarity(EventType.EXTERNAL_BOS, make_structure_break()) == 1
        down = make_structure_break(break_direction="DOWN")
        assert extract_polarity(EventType.INTERNAL_BOS, down) == -1

    def test_displacement(self) -> None:
        assert extract_polarity(EventType.DISPLACEMENT_UP, make_displacement()) == 1
        down = make_displacement(direction="DOWN")
        assert extract_polarity(EventType.DISPLACEMENT_DOWN, down) == -1

    def test_fvg_and_order_block(self) -> None:
        assert extract_polarity(EventType.FVG_BULLISH, make_fvg()) == 1
        bearish = make_order_block(direction="BEARISH")
        assert extract_polarity(EventType.ORDER_BLOCK_BEARISH, bearish) == -1

    def test_premium_discount_sides(self) -> None:
        """فوق المنصف سياق بيع (−1) وتحته سياق شراء (+1) — §11.7."""
        premium = make_premium_discount(location="PREMIUM")
        assert extract_polarity(EventType.PREMIUM_LOCATION, premium) == -1
        assert extract_polarity(EventType.DISCOUNT_LOCATION, make_premium_discount()) == 1

    def test_sweep_sides(self) -> None:
        """اجتياح شرائية (قمم) ثم رفض ⇒ هبوط؛ بيعية (قيعان) ⇒ صعود."""
        buy_side = make_sweep(zone_side="BUY_SIDE")
        assert extract_polarity(EventType.LIQUIDITY_SWEEP_HIGH, buy_side) == -1
        assert extract_polarity(EventType.LIQUIDITY_SWEEP_LOW, make_sweep()) == 1

    def test_break_accept_sides(self) -> None:
        assert extract_polarity(EventType.BREAK_AND_ACCEPT_HIGH, make_break_accept()) == 1
        sell_side = make_break_accept(zone_side="SELL_SIDE")
        assert extract_polarity(EventType.BREAK_AND_ACCEPT_LOW, sell_side) == -1

    def test_absorption_pressure(self) -> None:
        """امتصاص ضغط بيعي ⇒ صاعد (ABSORPTION_BUY) وبالعكس."""
        assert extract_polarity(EventType.ABSORPTION_BUY, make_absorption()) == 1
        buy = make_absorption(absorbed_pressure="BUY", delta_share=0.4)
        assert extract_polarity(EventType.ABSORPTION_SELL, buy) == -1

    def test_flow_continuation(self) -> None:
        assert extract_polarity(EventType.FLOW_CONTINUATION_UP, make_flow_continuation()) == 1
        down = make_flow_continuation(direction="DOWN")
        assert extract_polarity(EventType.FLOW_CONTINUATION_DOWN, down) == -1

    def test_exhaustion_against_effort(self) -> None:
        """إنهاك الجهد يقوّض اتجاهه: إنهاك صعود ⇒ دلالة هبوط."""
        assert extract_polarity(EventType.EXHAUSTION_UP, make_exhaustion()) == -1
        down = make_exhaustion(direction="DOWN")
        assert extract_polarity(EventType.EXHAUSTION_DOWN, down) == 1

    def test_imbalance_cluster(self) -> None:
        assert extract_polarity(EventType.BUY_IMBALANCE_CLUSTER, make_imbalance_cluster()) == 1
        sell = make_imbalance_cluster(side="SELL")
        assert extract_polarity(EventType.SELL_IMBALANCE_CLUSTER, sell) == -1

    def test_candle_pattern_directions(self) -> None:
        assert extract_polarity(EventType.BULLISH_ENGULFING, make_candle_pattern()) == 1
        bearish = make_candle_pattern(direction="BEARISH")
        assert extract_polarity(EventType.BEARISH_ENGULFING, bearish) == -1
        neutral = make_candle_pattern(direction="NEUTRAL")
        assert extract_polarity(EventType.REJECTION_CANDLE, neutral) == 0

    def test_classical_breakout_and_failure_inversion(self) -> None:
        """فشل الكسر يقلب الدلالة (§20 Break + reclaim)."""
        assert extract_polarity(EventType.CLASSICAL_BREAKOUT, make_classical()) == 1
        assert extract_polarity(FAILED, make_classical(event_type=FAILED)) == -1
        down_failure = make_classical(event_type=FAILED, break_direction="DOWN")
        assert extract_polarity(FAILED, down_failure) == 1

    def test_unknown_payload_rejected_loudly(self) -> None:
        """حمولة خارج العقود الثلاثة عشر ⇒ رفض صاخب لا صمت موافقة."""
        with pytest.raises(ValueError, match="بلا مستخلص قطبية"):
            extract_polarity(EventType.POC_ACCEPTANCE, object())
        bare = object()
        with pytest.raises(ValueError, match="بلا مستخلص قطبية"):
            extract_polarity(EventType.HARMONIC_COMPLETION, bare)


# ───────────────────────── القوة من الحمولة ─────────────────────────


class TestRawStrengthExtraction:
    """القوة = «Primary measurement» §20 بقيم محسوبة يدويًا."""

    def test_structure_break_distance(self) -> None:
        """«Break distance / ATR» مشبعًا: 1⇒0.5 و3⇒0.75."""
        bar = make_structure_break(breach_distance_atr=1.0)
        assert extract_raw_strength(EventType.EXTERNAL_BOS, bar) == pytest.approx(0.5)
        far = make_structure_break(breach_distance_atr=3.0)
        assert extract_raw_strength(EventType.CHOCH, far) == pytest.approx(0.75)

    def test_displacement_zscore(self) -> None:
        """«Range z-score»: |−2| ⇒ 2/3."""
        down = make_displacement(range_zscore=-2.0)
        assert extract_raw_strength(EventType.DISPLACEMENT_UP, down) == pytest.approx(2.0 / 3.0)

    def test_fvg_gap_atr(self) -> None:
        assert extract_raw_strength(EventType.FVG_BULLISH, make_fvg(size_atr=1.0)) == pytest.approx(
            0.5
        )

    def test_order_block_consequence_scale(self) -> None:
        """سلّم النتيجة الرتبي §11.6: BOS=1.0، سيولة=0.75، لم يكتمل=0.5."""
        bos = make_order_block(consequence=StructureConsequence.BOS)
        assert extract_raw_strength(EventType.ORDER_BLOCK_BULLISH, bos) == 1.0
        liquidity = make_order_block(consequence=StructureConsequence.LIQUIDITY_INTERACTION)
        assert extract_raw_strength(EventType.ORDER_BLOCK_BULLISH, liquidity) == 0.75
        pending = make_order_block(consequence=StructureConsequence.NONE_YET)
        assert extract_raw_strength(EventType.ORDER_BLOCK_BULLISH, pending) == 0.5

    def test_premium_discount_clamped_distance(self) -> None:
        """«Normalized distance» مقيدًا بالوحدة: 0.6 ⇒ 0.6، و2.5 ⇒ 1.0."""
        near = make_premium_discount(normalized_distance=0.6)
        assert extract_raw_strength(EventType.DISCOUNT_LOCATION, near) == pytest.approx(0.6)
        far = make_premium_discount(location="PREMIUM", normalized_distance=2.5)
        assert extract_raw_strength(EventType.PREMIUM_LOCATION, far) == 1.0

    def test_sweep_excursion_times_reclaim_speed(self) -> None:
        """«Excursion, reclaim speed»: تجاوز 1ATR (0.5) × عامل الاسترجاع —
        فوري (0) ⇒ 0.5، وشمعة تأخير ⇒ 0.25."""
        instant = make_sweep(excursion_atr=1.0, reclaim_bars=0)
        assert extract_raw_strength(EventType.LIQUIDITY_SWEEP_LOW, instant) == pytest.approx(0.5)
        delayed = make_sweep(excursion_atr=1.0, reclaim_bars=1)
        assert extract_raw_strength(EventType.LIQUIDITY_SWEEP_LOW, delayed) == pytest.approx(0.25)

    def test_break_accept_ratio_direct(self) -> None:
        """«Acceptance ratio» مطبَّع أصلًا فيمر مباشرة."""
        accepted = make_break_accept(acceptance_ratio=0.8)
        assert extract_raw_strength(EventType.BREAK_AND_ACCEPT_HIGH, accepted) == pytest.approx(0.8)

    def test_absorption_delta_share(self) -> None:
        """«Delta vs excursion»: حصة العدوان الممتص |−0.4| ⇒ 0.4."""
        payload = make_absorption(delta_share=-0.4)
        assert extract_raw_strength(EventType.ABSORPTION_BUY, payload) == pytest.approx(0.4)

    def test_flow_efficiency(self) -> None:
        """«Delta efficiency» مشبعة: 2.0 ⇒ 2/3."""
        payload = make_flow_continuation(efficiency=2.0)
        assert extract_raw_strength(EventType.FLOW_CONTINUATION_UP, payload) == pytest.approx(
            2.0 / 3.0
        )

    def test_exhaustion_decay(self) -> None:
        """«Efficiency decay»: تراجع 0.25 ⇒ قوة 0.75؛ ولا إنهاك عند ≥1."""
        assert extract_raw_strength(
            EventType.EXHAUSTION_UP, make_exhaustion(decay_ratio=0.25)
        ) == pytest.approx(0.75)
        assert (
            extract_raw_strength(EventType.EXHAUSTION_UP, make_exhaustion(decay_ratio=1.0)) == 0.0
        )
        assert (
            extract_raw_strength(EventType.EXHAUSTION_UP, make_exhaustion(decay_ratio=1.5)) == 0.0
        )

    def test_imbalance_density(self) -> None:
        """«Imbalance density»: 6 اختلالات في 3 أشرطة ⇒ كثافة 2 ⇒ 2/3."""
        cluster = make_imbalance_cluster(bar_count=3, total_imbalances=6)
        assert extract_raw_strength(EventType.BUY_IMBALANCE_CLUSTER, cluster) == pytest.approx(
            2.0 / 3.0
        )

    def test_candle_strength_direct(self) -> None:
        payload = make_candle_pattern(strength=0.7)
        assert extract_raw_strength(EventType.BULLISH_ENGULFING, payload) == pytest.approx(0.7)

    def test_classical_breakout_quality(self) -> None:
        """«Break quality» — جودة §13.2 مباشرة."""
        assert extract_raw_strength(
            EventType.CLASSICAL_BREAKOUT, make_classical(quality=0.9)
        ) == pytest.approx(0.9)

    def test_classical_failure_speed_factor(self) -> None:
        """«Failure speed»: جودة 0.9 باسترجاع فوري ⇒ 0.9؛ وبتأخير شمعتين
        ⇒ 0.9/3 = 0.3."""
        instant = make_classical(event_type=FAILED, quality=0.9, failure_speed=0.0)
        assert extract_raw_strength(FAILED, instant) == pytest.approx(0.9)
        slow = make_classical(event_type=FAILED, quality=0.9, failure_speed=2.0)
        assert extract_raw_strength(FAILED, slow) == pytest.approx(0.3)

    def test_unknown_payload_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="بلا مستخلص قوة"):
            extract_raw_strength(EventType.POC_REJECTION, object())
