"""اختبارات خصائص محرك البنية الكامل (المهمة 3-b) — §26.3 والحتمية والتحجيم.

تُفرض الخصائص على :class:`structure.StructureEngine` بأ_componentاتها
الثلاثة (متطرفات/كسور/إزاحة) مع محرك التقلب الموازي يغذي الحالة عند كل
شمعة (نمط verify_phase2 — عقد الواجهة):

- **لا نظرة مستقبلية (§26.3)**: أحداث ومتطرفات البادئة [0..k] لا تتغير
  بتمديد الذيل أبدًا — لكل قطع k (لا رفرفة §27).
- **الحتمية الصرفة**: نفس السلسلة مرتين ⇒ نفس الأحداث والمتطرفات بالتطابق
  التام (بما فيها ``swing_id``).
- **لا تغيّر بالتحجيم (قوى الأساسين)**: ‎λ = 2^k‎ يحجّم الأسعار كلها —
  الحالة التقلبية تُعاد اشتقاقها من الشموع المحجّمة فيتحجّج ATR معها —
  فتبقى كل المقاييس عديمة البُعد (``breach_distance_atr`` و
  ``closing_acceptance`` و``strength`` و``body_fraction`` و``range_zscore``
  و``atr_multiple``) والتصنيفات (أنواع الأحداث والاتجاهات والنطاقات)
  ومعرفات المتطرفات متطابقة **بالتساوي الصرف** (قوى الأساسين تُبقيها
  عمليات float الدقيقة)، بينما تتحجّج الأسعار و``velocity`` (سعر/شمعة)
  بـλ بالضبط.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from market_state.volatility import VolatilityConfig, VolatilityEngine
from schemas import Candle, DataQuality, DisplacementEventPayload, StructureBreakPayload, Swing
from structure import DisplacementConfig, StructureConfig, StructureEngine, SwingConfig
from structure.events import EmittedEvent

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

# بنية مصغّرة النوافذ: تأكيد متطرفات بثلاث شموع، وإحصاء إزاحة خماسي —
# لتشتغل المسارات الثلاثة على التسلسلات القصيرة.
_STRUCT = StructureConfig(
    swings=SwingConfig(confirm_bars=2),
    displacement=DisplacementConfig(zscore_window=5),
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

    ``λ`` قوة أساسين فالتحجيم دقيق بتّيًا: كل النسب المشتقة لاحقًا
    (جسم/موقع/مضاعف/تطبيع ATR) لا تتغير إلا بطاقة الرقم نفسها.
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


@st.composite
def candle_runs(draw: st.DrawFn) -> tuple[list[Candle], list[Candle], float]:
    """شموع سليمة حتمية الترتيب + نسأختها المحجّمة ومعامل التحجيم."""
    rows = draw(st.lists(legs, min_size=8, max_size=30))
    exponent = draw(st.integers(min_value=-2, max_value=4))
    lam = 2.0**exponent
    original = [_mk_candle(i, o, c, uw, dw, v) for i, (o, c, uw, dw, v) in enumerate(rows)]
    scaled = [_mk_candle(i, o, c, uw, dw, v, lam=lam) for i, (o, c, uw, dw, v) in enumerate(rows)]
    return original, scaled, lam


def _run(
    candles: list[Candle],
) -> tuple[list[list[EmittedEvent]], list[tuple[Swing, ...]]]:
    """تشغيل الواجهة الكاملة مع محرك التقلب الموازي — أحداث وسجل متطرفات لكل شمعة."""
    vol_engine = VolatilityEngine(config=_TINY)
    engine = StructureEngine(config=_STRUCT)
    events_per_bar: list[list[EmittedEvent]] = []
    swings_per_bar: list[tuple[Swing, ...]] = []
    for candle in candles:
        state = vol_engine.update(candle)
        events_per_bar.append(list(engine.update(candle, state)))
        swings_per_bar.append(engine.swings)
    return events_per_bar, swings_per_bar


# ═══════════ §26.3: لا نظرة مستقبلية — البادئة مستقلة عن الذيل ═══════════


class TestStructureNoLookahead:
    """أحداث ومتطرفات البادئة [0..k] لا تتغير بتمديد الذيل — لكل قطع k."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_prefix_events_and_swings_independent_of_tail(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        candles = run[0]
        full_events, full_swings = _run(candles)
        for k in range(1, len(candles) + 1):
            prefix_events, prefix_swings = _run(candles[:k])
            assert prefix_events == full_events[:k], f"أحداث البادئة تغيرت بالذيل عند k={k}"
            assert prefix_swings == full_swings[:k], f"متطرفات البادئة تغيرت بالذيل عند k={k}"


# ═══════════ الحتمية الصرفة ═══════════


class TestStructureDeterminism:
    """نفس السلسلة مرتين ⇒ نفس الأحداث والمتطرفات بالتطابق التام."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_same_sequence_twice_identical(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        candles = run[0]
        assert _run(candles) == _run(candles)


# ═══════════ التحجيم السعري — قوى الأساسين تبقي عديمات البُعد ═══════════


def _assert_scaled_event(original: EmittedEvent, scaled: EmittedEvent, lam: float) -> None:
    """زوج أحداث بنفس الشمعة: النوع والزمن متطابقان والمقاييس عديمة البُعد."""
    assert scaled.event_type is original.event_type
    assert scaled.event_time == original.event_time
    if isinstance(original.payload, StructureBreakPayload):
        assert isinstance(scaled.payload, StructureBreakPayload)
        # كل حقول حمولة الكسر عديمة البُعد — تتطابق بالتساوي الصرف.
        assert scaled.payload == original.payload
        return
    assert isinstance(original.payload, DisplacementEventPayload)
    assert isinstance(scaled.payload, DisplacementEventPayload)
    left = original.payload.model_dump()
    right = scaled.payload.model_dump()
    assert right.pop("velocity") == lam * left.pop("velocity")  # سعر/شمعة — يتحجّم بـλ
    assert right == left  # zscore/جسم/موقع/مضاعف ATR — عديمة البُعد بالضبط


def _assert_scaled_swing(original: Swing, scaled: Swing, lam: float) -> None:
    """زوج متطرفين: المعرف والتصنيف والقوة متطابقة، والسعر محجّم بـλ."""
    assert scaled.swing_id == original.swing_id  # مفتاح uuid5 لا يدخل الأسعار
    assert scaled.price == lam * original.price
    assert scaled.timeframe == original.timeframe
    assert scaled.direction is original.direction
    assert scaled.strength == original.strength  # tanh(excess/atr) — نسبة
    assert scaled.confirmation_time == original.confirmation_time
    assert scaled.external_or_internal is original.external_or_internal
    assert scaled.bar_time == original.bar_time


class TestStructureScaleInvariance:
    """λ=2^k يحجّم الأسعار وATR معًا — التصنيفات والمقاييس النسبية لا تتغير."""

    @given(run=candle_runs())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_power_of_two_scaling_preserves_dimensionless_measures(
        self, run: tuple[list[Candle], list[Candle], float]
    ) -> None:
        original, scaled, lam = run
        events_orig, swings_orig = _run(original)
        events_scaled, swings_scaled = _run(scaled)
        for bar_orig, bar_scaled in zip(events_orig, events_scaled, strict=True):
            assert len(bar_scaled) == len(bar_orig)
            for ev_orig, ev_scaled in zip(bar_orig, bar_scaled, strict=True):
                _assert_scaled_event(ev_orig, ev_scaled, lam)
        for snap_orig, snap_scaled in zip(swings_orig, swings_scaled, strict=True):
            assert len(snap_scaled) == len(snap_orig)
            for sw_orig, sw_scaled in zip(snap_orig, snap_scaled, strict=True):
                _assert_scaled_swing(sw_orig, sw_scaled, lam)
