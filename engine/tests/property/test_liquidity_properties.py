"""اختبارات خصائص محرك السيولة الكامل (المهمة 3-d) — §26.3 والحتمية والتحجيم.

تُفرض الخصائص على :class:`liquidity.LiquidityEngine` بمكوناتها (خريطة
المناطق + كاشف الاجتياح + الأهداف) مع محرك التقلب الموازي يغذي الحالة
عند كل شمعة (نمط verify_phase2 — عقد الواجهة) والمتطرفات تصل كقيم
``schemas.Swing`` مُشتقة حتميًا من الشمعة نفسها (confirmed-as-supplied —
عقد الكاشف المستقل §47):

- **لا نظرة مستقبلية (§26.3)**: أحداث البادئة [0..k] ولقطات مناطقها لا
  تتغير بتمديد الذيل أبدًا — لكل قطع k (لا رفرفة §27): الاجتياح تسلسل
  نافذته تقييمية، وحدود النافذة عند الشريط t مغلقة على الماضي حصرًا.

- **الحتمية الصرفة**: نفس السلسلة مرتين ⇒ نفس الأحداث والمناطق بالتطابق
  التام (بما فيه ``zone_id`` — مفاتيح uuid5 بلا أسعار).

- **لا تغيّر بالتحجيم (قوى الأساسين)**: ‎λ = 2^k‎ يحجّم أسعار الشموع
  والمتطرفات معًا (والحالة التقلبية تُعاد اشتقاقها من المحجّم فيتحجّج
  ATR) — فتتطابق أنواع الأحداث وحمولاتها **بالكامل** (كل حقول
  ``SweepEventPayload``/``BreakAcceptEventPayload`` عديمة البُعد أو عدّية
  أو زمنية) ومعرفات المناطق وحالاتها ودرجاتها الثلاث (نِسب)، بينما
  تتحجّج أسعار المناطق بـλ بالضبط — والقراءة الحية ``targets`` كذلك:
  مسافاتها المعيارية وصلاتها متطابقة وفواصلها المحجّجة بـλ.

- **حدود الدرجات**: ``reaction_score``/``unmitigated_score``/
  ``importance_score`` ∈ [0, 1] دائمًا (§10.3 — ليست احتمالات).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from liquidity import EmittedEvent, LiquidityEngine
from market_state.volatility import VolatilityConfig, VolatilityEngine
from schemas import (
    BreakAcceptEventPayload,
    Candle,
    DataQuality,
    LiquidityZone,
    SweepEventPayload,
    Swing,
    SwingDirection,
    SwingScope,
)

_BASE = datetime(2026, 1, 5, tzinfo=UTC)

# إعداد تقلب مصغر سريع الدافئ (نمط tests/property/test_features_properties.py).
_TINY = VolatilityConfig(
    atr_period=2,
    pct_window=3,
    rv_window=2,
    vov_window=2,
    range_window=3,
    holding_horizons=(3,),
)

legs = st.tuples(
    st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)


def _mk_candle(
    index: int,
    o: float,
    c: float,
    up_wick: float,
    down_wick: float,
    v: float,
    lam: float = 1.0,
) -> Candle:
    """شمعة من أطراف (open, close, فتيلان، حجم) بمعامل تحجيم ‎λ‎ سعري.

    ``λ`` قوة أساسين فالتحجيم دقيق بتّيًا: كل النسب المشتقة لاحقًا لا
    تتغير إلا بطاقة الرقم نفسها.
    """
    o, c = lam * o, lam * c
    high = max(o, c) + lam * up_wick
    low = min(o, c) - lam * down_wick
    span = high - low
    body = abs(c - o)
    if span > 0.0:
        body_fraction = body / span
        close_location = (c - low) / span
    else:
        body_fraction = 0.0
        close_location = 0.5
    return Candle(
        instrument_id="BINANCE_USDM:BTCUSDT",
        timeframe="1m",
        bar_time=_BASE + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=o,
        high=high,
        low=low,
        close=c,
        volume=v,
        range=span,
        body_size=body,
        upper_wick=high - max(o, c),
        lower_wick=min(o, c) - low,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=span,
        realized_volatility=abs(math.log(c / o)) if o > 0.0 else 0.0,
    )


def _bar_swings(index: int, candle: Candle) -> list[Swing]:
    """متطرفات مشتقة حتميًا من الشمعة — كل ثالث شريط، بالتناوب قمة/قاع.

    المشتق من الشمعة نفسها **كما وصلت**: في المسار المحجّج تصل الشمعة
    محجّجة فيتحجّج المتطرف معها تلقائيًا (لا معامل λ هنا إطلاقًا —
    ضربه هنا كان سيعطّل التحجيم مرتين)؛ والمعرفات فهرسية بلا أسعار؛
    و``confirmation_time = bar_time`` (confirmed-as-supplied — عقد التغذية
    §47: الكاشف المستقل يستهلك المتطرفات كما وصلت، التأخير مسؤولية
    منشئها في المسار الحي).
    """
    if index % 3 != 0:
        return []
    bar_time = _BASE + timedelta(minutes=index)
    if index % 2 == 0:
        swing = Swing(
            swing_id=f"sw-h-{index}",
            price=candle.high,
            timeframe=candle.timeframe,
            direction=SwingDirection.HIGH,
            strength=0.6,
            confirmation_time=bar_time,
            external_or_internal=SwingScope.EXTERNAL,
            bar_time=bar_time,
        )
    else:
        swing = Swing(
            swing_id=f"sw-l-{index}",
            price=candle.low,
            timeframe=candle.timeframe,
            direction=SwingDirection.LOW,
            strength=0.6,
            confirmation_time=bar_time,
            external_or_internal=SwingScope.INTERNAL,
            bar_time=bar_time,
        )
    return [swing]


@st.composite
def candle_runs(draw: st.DrawFn) -> tuple[list[Candle], list[Candle], float]:
    """شموع سليمة حتمية الترتيب + نسختها المحجّجة ومعامل التحجيم."""
    rows = draw(st.lists(legs, min_size=8, max_size=30))
    exponent = draw(st.integers(min_value=-2, max_value=4))
    lam = 2.0**exponent
    original = [_mk_candle(i, o, c, uw, dw, v) for i, (o, c, uw, dw, v) in enumerate(rows)]
    scaled = [_mk_candle(i, o, c, uw, dw, v, lam=lam) for i, (o, c, uw, dw, v) in enumerate(rows)]
    return original, scaled, lam


def _run(
    candles: list[Candle],
) -> tuple[list[list[EmittedEvent]], list[tuple[LiquidityZone, ...]]]:
    """تشغيل الواجهة الكاملة مع محرك تقلب موازٍ — أحداث ولقطات مناطق لكل شمعة."""
    vol_engine = VolatilityEngine(config=_TINY)
    engine = LiquidityEngine()
    events_per_bar: list[list[EmittedEvent]] = []
    zones_per_bar: list[tuple[LiquidityZone, ...]] = []
    for index, candle in enumerate(candles):
        # أول شمعة تعيد None من محرك التقلب (لا حالة من شمعة واحدة) —
        # يمر كما هو: عقد التغذية الاختياري الموحد للكاشفين (غياب ATR).
        state = vol_engine.update(candle)
        events_per_bar.append(list(engine.update(candle, state, _bar_swings(index, candle))))
        zones_per_bar.append(tuple(engine.zones()))
    return events_per_bar, zones_per_bar


# ═══════════ §26.3: لا نظرة مستقبلية — البادئة مستقلة عن الذيل ═══════════


class TestLiquidityNoLookahead:
    """أحداث البادئة [0..k] ومناطقها لا تتغير بتمديد الذيل — لكل قطع k."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_prefix_events_and_zones_independent_of_tail(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        candles = run[0]
        full_events, full_zones = _run(candles)
        for k in range(1, len(candles) + 1):
            prefix_events, prefix_zones = _run(candles[:k])
            assert prefix_events == full_events[:k], f"أحداث البادئة تغيرت بالذيل عند k={k}"
            assert prefix_zones == full_zones[:k], f"مناطق البادئة تغيرت بالذيل عند k={k}"


# ═══════════ الحتمية الصرفة ═══════════


class TestLiquidityDeterminism:
    """نفس السلسلة مرتين ⇒ نفس الأحداث والمناطق بالتطابق التام."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_same_sequence_twice_identical(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        candles = run[0]
        assert _run(candles) == _run(candles)


# ═══════════ التحجيم السعري — قوى الأساسين تبقي عديمات البُعد ═══════════


def _assert_scaled_zone(original: LiquidityZone, scaled: LiquidityZone, lam: float) -> None:
    """زوج مناطق بنفس الشمعة: الهوية والحالة والدرجات متطابقة والسعر محجّم."""
    assert scaled.zone_id == original.zone_id  # مفاتيح uuid5 بلا أسعار (عقد zones)
    assert scaled.side is original.side
    assert scaled.price_low == lam * original.price_low
    assert scaled.price_high == lam * original.price_high
    assert scaled.origin_time == original.origin_time
    assert scaled.age == original.age
    assert scaled.source_type is original.source_type
    assert scaled.test_count == original.test_count
    assert scaled.last_test_time == original.last_test_time
    assert scaled.sweep_status is original.sweep_status
    assert scaled.reaction_score == original.reaction_score  # نِسب — لا تتغير
    assert scaled.unmitigated_score == original.unmitigated_score
    assert scaled.importance_score == original.importance_score
    assert scaled.instrument == original.instrument
    assert scaled.timeframe == original.timeframe
    assert scaled.state is original.state


def _assert_scaled_event(original: EmittedEvent, scaled: EmittedEvent) -> None:
    """زوج أحداث: النوع والزمن والحمولة متطابقون بالكامل.

    حمولتا §20 السيوليتان (اجتياح/كسر-وقبول) كل حقولهما عديمة البُعد
    (``excursion_atr``/``acceptance_ratio``) أو عدّية (``reclaim_bars``/
    ``test_count_at_event``/``window_bars``) أو معرفية-زمنية — لا سعر مطلق
    واحد، فتتطابقان بالتساوي الصرف تحت التحجيم.
    """
    assert scaled.event_type is original.event_type
    assert scaled.event_time == original.event_time
    if isinstance(original.payload, SweepEventPayload):
        assert isinstance(scaled.payload, SweepEventPayload)
        assert scaled.payload == original.payload
        return
    assert isinstance(original.payload, BreakAcceptEventPayload)
    assert isinstance(scaled.payload, BreakAcceptEventPayload)
    assert scaled.payload == original.payload


class TestLiquidityScaleInvariance:
    """λ=2^k يحجّم الأسعار وATR معًا — التصنيفات والدرجات والقراءة الحية لا تتغير."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_power_of_two_scaling_preserves_dimensionless_state(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        original, scaled, lam = run
        events_orig, zones_orig = _run(original)
        events_scaled, zones_scaled = _run(scaled)
        for bar_orig, bar_scaled in zip(events_orig, events_scaled, strict=True):
            assert len(bar_scaled) == len(bar_orig)
            for ev_orig, ev_scaled in zip(bar_orig, bar_scaled, strict=True):
                _assert_scaled_event(ev_orig, ev_scaled)
        for snap_orig, snap_scaled in zip(zones_orig, zones_scaled, strict=True):
            assert len(snap_scaled) == len(snap_orig)
            for z_orig, z_scaled in zip(snap_orig, snap_scaled, strict=True):
                _assert_scaled_zone(z_orig, z_scaled, lam)

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_targets_reading_scale_invariant(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        """القراءة الحية: المسافات المعيارية والصلة محفوظة والفواصل محجّجة بـλ."""
        original, scaled, lam = run
        vol_engine = VolatilityEngine(config=_TINY)
        engine_a = LiquidityEngine()
        for index, candle in enumerate(original):
            state = vol_engine.update(candle)
            engine_a.update(candle, state, _bar_swings(index, candle))
        vol_engine_b = VolatilityEngine(config=_TINY)
        engine_b = LiquidityEngine()
        for index, candle in enumerate(scaled):
            state = vol_engine_b.update(candle)
            engine_b.update(candle, state, _bar_swings(index, candle))
        price_orig = original[-1].close
        price_scaled = scaled[-1].close
        state_a = vol_engine.state
        state_b = vol_engine_b.state
        assert state_a is not None and state_b is not None  # بعد ≥ شمعتين
        targets_a = engine_a.targets(price_orig, state_a, limit_per_side=5)
        targets_b = engine_b.targets(price_scaled, state_b, limit_per_side=5)
        assert len(targets_b.above) == len(targets_a.above)
        assert len(targets_b.below) == len(targets_a.below)
        for entry_a, entry_b in zip(targets_a.above, targets_b.above, strict=True):
            assert entry_b.zone.zone_id == entry_a.zone.zone_id
            assert entry_b.distance_atr == entry_a.distance_atr  # نسبة — محفوظة
            assert entry_b.relevance == entry_a.relevance  # importance × إشباع — نسب
            assert entry_b.zone_low == lam * entry_a.zone_low  # سعر ± atr×نصف — يتحجّج
            assert entry_b.zone_high == lam * entry_a.zone_high
        for entry_a, entry_b in zip(targets_a.below, targets_b.below, strict=True):
            assert entry_b.zone.zone_id == entry_a.zone.zone_id
            assert entry_b.distance_atr == entry_a.distance_atr
            assert entry_b.relevance == entry_a.relevance
            assert entry_b.zone_low == lam * entry_a.zone_low
            assert entry_b.zone_high == lam * entry_a.zone_high


# ═══════════ حدود الدرجات الثلاث (§10.3 — ليست احتمالات) ═══════════


class TestZoneScoreBounds:
    """الدرجات الموثقة الثلاث تبقى في [0, 1] عبر التشغيل الكامل دائمًا."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_all_scores_within_unit_interval(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        _events, zones_per_bar = _run(run[0])
        for snapshot in zones_per_bar:
            for zone in snapshot:
                assert 0.0 <= zone.reaction_score <= 1.0, zone
                assert 0.0 <= zone.unmitigated_score <= 1.0, zone
                assert 0.0 <= zone.importance_score <= 1.0, zone
