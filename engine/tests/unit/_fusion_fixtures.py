"""مساعدات مشتركة لاختبارات الدمج (المرحلة 6) — بناة حمولات أحداث §20
لكل عائلة كاشف (نمط ``_orderflow_fixtures``).

الحمولات قانونية كاملة الحقول بقيم قابلة للحساب اليدوي، وكل حقل قابل
للتجاوز لبناء الحالات المقصودة. معاملات التعداد تقبل العضو أو قيمته
النصية (إجبار صريح داخل الباني) فتبقى أسطر الاختبار قصيرة مقروءة.
القيم الافتراضية محايدة القوة (لا صفر موت ولا حد أقصى) حتى تكون فروق
الاختبارات من التغيير المقصود وحده.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from schemas import (
    BreakDirection,
    CandlePatternEventPayload,
    ClassicalPatternEventPayload,
    DisplacementEventPayload,
    EventType,
    FvgDirection,
    FvgEventPayload,
    FvgState,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    StructureBreakPayload,
    StructureConsequence,
    SweepClassification,
    SwingScope,
)
from schemas.liquidity import (
    BreakAcceptEventPayload,
    LiquiditySide,
    SweepEventPayload,
)
from schemas.orderflow import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    FlowDirection,
    ImbalanceClusterEventPayload,
    ImbalanceSide,
)
from schemas.patterns import (
    AnchorPoint,
    CandlePatternFamily,
    ClassicalPatternType,
    PatternDirection,
    PatternStatus,
)

__all__ = [
    "BASE_TIME",
    "INSTRUMENT",
    "TIMEFRAME",
    "make_absorption",
    "make_break_accept",
    "make_candle_pattern",
    "make_classical",
    "make_displacement",
    "make_exhaustion",
    "make_flow_continuation",
    "make_fvg",
    "make_imbalance_cluster",
    "make_order_block",
    "make_premium_discount",
    "make_structure_break",
    "make_sweep",
]

#: طابع الشريط الأولى — الدقائق ترقّم الأحداث (إطار الدقيقة).
BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def _bar_time(index: int) -> datetime:
    return BASE_TIME + timedelta(minutes=index)


def make_structure_break(
    index: int = 0,
    *,
    break_direction: BreakDirection | str = BreakDirection.UP,
    breach_distance_atr: float = 1.0,
    closing_acceptance: float = 0.8,
    follow_through: float = 0.5,
    swing_scope: SwingScope = SwingScope.EXTERNAL,
) -> StructureBreakPayload:
    """كسر بنية §11.2-3 — يخدم INTERNAL_BOS/EXTERNAL_BOS/CHOCH."""
    return StructureBreakPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        swing_id=f"swing-{index}",
        swing_scope=swing_scope,
        break_direction=BreakDirection(break_direction),
        breach_distance_atr=breach_distance_atr,
        closing_acceptance=closing_acceptance,
        follow_through=follow_through,
    )


def make_displacement(
    index: int = 0,
    *,
    direction: BreakDirection | str = BreakDirection.UP,
    range_zscore: float = 2.0,
) -> DisplacementEventPayload:
    """إزاحة §11.4 — السمات الست بقيم متوسطة قابلة للتوقع."""
    return DisplacementEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        direction=BreakDirection(direction),
        range_zscore=range_zscore,
        body_fraction=0.8,
        close_location=0.9,
        atr_multiple=2.0,
        velocity=1.5,
        follow_through=0.6,
    )


def make_fvg(
    index: int = 0,
    *,
    direction: FvgDirection | str = FvgDirection.BULLISH,
    size_atr: float = 1.0,
) -> FvgEventPayload:
    """فجوة قيمة §11.5 عند التكوين."""
    return FvgEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        direction=FvgDirection(direction),
        gap_low=100.0,
        gap_high=100.0 + size_atr,
        size_atr=size_atr,
        state=FvgState.CREATED,
    )


def make_order_block(
    index: int = 0,
    *,
    direction: FvgDirection | str = FvgDirection.BULLISH,
    consequence: StructureConsequence = StructureConsequence.BOS,
) -> OrderBlockEventPayload:
    """منطقة مصدرية §11.6 — النتيجة البنيوية قابلة للتوجيه."""
    return OrderBlockEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        direction=FvgDirection(direction),
        zone_low=99.0,
        zone_high=100.0,
        origin_time=_bar_time(index) - timedelta(minutes=3),
        displacement_id=f"disp-{index}",
        structure_consequence=consequence,
        size_atr=1.0,
    )


def make_premium_discount(
    index: int = 0,
    *,
    location: PremiumDiscountSide | str = PremiumDiscountSide.DISCOUNT,
    normalized_distance: float = 0.6,
) -> PremiumDiscountEventPayload:
    """موقع نطاق المعالجة §11.7."""
    side = PremiumDiscountSide(location)
    price = (
        100.0 + normalized_distance
        if side is PremiumDiscountSide.PREMIUM
        else 100.0 - normalized_distance
    )
    return PremiumDiscountEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        range_name="dealing-range-1",
        range_low=90.0,
        range_high=110.0,
        equilibrium=100.0,
        location=side,
        normalized_distance=normalized_distance,
        price=price,
    )


def make_sweep(
    index: int = 0,
    *,
    zone_side: LiquiditySide | str = LiquiditySide.SELL_SIDE,
    excursion_atr: float = 1.0,
    reclaim_bars: int = 0,
) -> SweepEventPayload:
    """اجتياح سيولة §10.4 مؤكد (البث نفسه التأكيد)."""
    return SweepEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        zone_id=f"zone-{index}",
        zone_side=LiquiditySide(zone_side),
        classification=SweepClassification.CONFIRMED_SWEEP,
        excursion_atr=excursion_atr,
        penetration_reached=True,
        reclaim_bars=reclaim_bars,
        test_count_at_event=2,
    )


def make_break_accept(
    index: int = 0,
    *,
    zone_side: LiquiditySide | str = LiquiditySide.BUY_SIDE,
    acceptance_ratio: float = 0.8,
) -> BreakAcceptEventPayload:
    """كسر بقبول §10.4 — الطرف المقابل للاجتياح."""
    return BreakAcceptEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        zone_id=f"zone-{index}",
        zone_side=LiquiditySide(zone_side),
        excursion_atr=0.5,
        acceptance_ratio=acceptance_ratio,
        window_bars=3,
    )


def make_absorption(
    index: int = 0,
    *,
    absorbed_pressure: AbsorbedPressure | str = AbsorbedPressure.SELL,
    delta_share: float = -0.4,
) -> AbsorptionEventPayload:
    """امتصاص §12.3 — مرشح غير مؤكد افتراضيًا (عقد الحمولة)."""
    return AbsorptionEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        absorbed_pressure=AbsorbedPressure(absorbed_pressure),
        delta=-40.0 if delta_share < 0 else 40.0,
        delta_share=delta_share,
        excursion_atr=0.2,
        conditions=AbsorptionConditions(
            elevated_delta=True,
            limited_extension=True,
            repeated_response=False,
            opposite_displacement=None,
        ),
    )


def make_flow_continuation(
    index: int = 0,
    *,
    direction: FlowDirection | str = FlowDirection.UP,
    efficiency: float = 2.0,
) -> FlowContinuationEventPayload:
    """توافق التدفق §12.2."""
    return FlowContinuationEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        direction=FlowDirection(direction),
        delta=50.0,
        delta_share=0.5,
        response_atr=1.0,
        efficiency=efficiency,
    )


def make_exhaustion(
    index: int = 0,
    *,
    direction: FlowDirection | str = FlowDirection.UP,
    decay_ratio: float = 0.25,
) -> ExhaustionEventPayload:
    """إنهاك §12.4 — تراجع كفاءة بمرجع سابق."""
    efficiency = 1.0
    return ExhaustionEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        direction=FlowDirection(direction),
        efficiency=efficiency,
        efficiency_prev=efficiency / decay_ratio if decay_ratio > 0 else efficiency,
        decay_ratio=decay_ratio,
        failed_extremes=2,
        follow_through=0.3,
    )


def make_imbalance_cluster(
    index: int = 0,
    *,
    side: ImbalanceSide | str = ImbalanceSide.BUY,
    bar_count: int = 3,
    total_imbalances: int = 6,
) -> ImbalanceClusterEventPayload:
    """عنقيد اختلالات §12.6 — الكثافة لكل شريط قابلة للتوقع."""
    return ImbalanceClusterEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        side=ImbalanceSide(side),
        bar_count=bar_count,
        total_imbalances=total_imbalances,
        max_row_ratio=4.0,
        aligned_with_displacement=True,
    )


def make_candle_pattern(
    index: int = 0,
    *,
    direction: PatternDirection | str = PatternDirection.BULLISH,
    strength: float = 0.7,
) -> CandlePatternEventPayload:
    """نمط شموعي §13.1 — قراءات السمات الست كاملة بعقد الخريطة."""
    return CandlePatternEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        family=CandlePatternFamily.ENGULFING,
        direction=PatternDirection(direction),
        feature_readings={
            "body_fraction": 0.6,
            "wick_asymmetry": -0.4,
            "close_location": 0.8,
            "range_percentile": 0.7,
            "gap_relationship": 0.5,
            "volume_relationship": 0.6,
        },
        strength=strength,
        bars_in_pattern=2,
    )


def make_classical(
    index: int = 0,
    *,
    event_type: EventType | str = EventType.CLASSICAL_BREAKOUT,
    break_direction: BreakDirection | str = BreakDirection.UP,
    quality: float = 0.9,
    failure_speed: float | None = None,
) -> ClassicalPatternEventPayload:
    """بنية كلاسيكية §13.2 — مخرجات الثمانية كاملة؛ زوج الفشل اختياري."""
    resolved_type = EventType(event_type)
    failed = resolved_type is EventType.CLASSICAL_FAILED_BREAKOUT
    reclaim = 105.0 if failed else None
    speed = failure_speed if failed else None
    if failed and speed is None:
        speed = 2.0
    return ClassicalPatternEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=_bar_time(index),
        pattern_type=ClassicalPatternType.DOUBLE_BOTTOM,
        geometry={"height_atr": 2.0, "width_bars": 20.0, "slope_per_bar": -0.05},
        anchor_points=(
            AnchorPoint(time=_bar_time(index) - timedelta(minutes=30), price=100.0, role="P1"),
            AnchorPoint(time=_bar_time(index) - timedelta(minutes=20), price=95.0, role="P2"),
            AnchorPoint(time=_bar_time(index) - timedelta(minutes=10), price=100.0, role="P3"),
        ),
        completion_time=_bar_time(index) - timedelta(minutes=5),
        breakout_level=100.0,
        invalidation_level=94.0,
        measured_move=110.0,
        quality=quality,
        break_direction=BreakDirection(break_direction),
        status=PatternStatus.CONFIRMED,
        reclaim_level=reclaim,
        failure_speed=speed,
    )
