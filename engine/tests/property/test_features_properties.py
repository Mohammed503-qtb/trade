"""اختبارات خصائص حزمة السمات ومحرك التقلب (المهمة 2-c) — §26.3.

الخصائص المفروضة:

- **لا نظرة مستقبلية**: خرج السمة/الحالة على البادئة [0..k] لا يتغير أبدًا
  بتمديد الذيل — جوهر §26.3 وعقد الإعادة (A-02).
- **الحتمية الصرفة**: نداءان متطابقان ⇒ نفس البايتات (nan بنمط البتات
  نفسه)، ومحركان متطابقان ⇒ نفس الحالات بالكامل.

على نمط tests/property/test_schemas_bounds.py وtest_math_properties.py
مع derandomize=True (بذرة حتمية).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
from features import (
    atr_pct_series,
    directional_efficiency_series,
    gap_shock_series,
    vol_of_vol_series,
    volume_concentration_series,
)
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from market_state.volatility import VolatilityConfig, VolatilityEngine, VolatilityState
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)

# إعداد مصغر سريع الدافئ للخصائص الموضعية — يقلب كل العقود بلا كلفة.
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
    index: int, o: float, c: float, up_wick: float, down_wick: float, v: float
) -> Candle:
    high = max(o, c) + up_wick
    low = min(o, c) - down_wick
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
def candle_lists(draw: st.DrawFn) -> list[Candle]:
    """شموع سليمة حتمية الترتيب (bar_time من الدليل) بأطراف عشوائية."""
    rows = draw(st.lists(legs, min_size=6, max_size=36))
    return [_mk_candle(i, o, c, uw, dw, v) for i, (o, c, uw, dw, v) in enumerate(rows)]


def _prefix_stable(
    name: str,
    full: np.ndarray,
    prefix_out: np.ndarray,
    k: int,
) -> None:
    """خرج البادئة [0..k] من مكالمة مقصوصة == نفس مقاطع المكالمة الكاملة."""
    assert np.array_equal(prefix_out, full[:k], equal_nan=True), (
        f"{name} نظرت المستقبل: خرج البادئة تغيّر بتمديد الذيل"
    )


def _run_engine(config: VolatilityConfig, candles: list[Candle]) -> list[VolatilityState | None]:
    engine = VolatilityEngine(config=config)
    return [engine.update(candle) for candle in candles]


# ═══════════ §26.3: لا نظرة مستقبلية — السمات ═══════════


class TestFeaturesNoLookahead:
    """خرج البادئة لا يتغير بتمديد الذيل — لكل قطع k."""

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_atr_pct_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = atr_pct_series(candles, atr_period=3, pct_window=5)
        for k in range(1, len(candles) + 1):
            _prefix_stable("atr_pct", full, atr_pct_series(candles[:k], 3, 5), k)

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_vol_of_vol_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = vol_of_vol_series(candles, rv_window=3, vov_window=4)
        for k in range(1, len(candles) + 1):
            _prefix_stable("vol_of_vol", full, vol_of_vol_series(candles[:k], 3, 4), k)

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_gap_shock_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = gap_shock_series(candles, atr_period=3)
        for k in range(1, len(candles) + 1):
            _prefix_stable("gap_shock", full, gap_shock_series(candles[:k], 3), k)

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_directional_efficiency_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = directional_efficiency_series(candles, window=4)
        for k in range(1, len(candles) + 1):
            _prefix_stable(
                "directional_efficiency",
                full,
                directional_efficiency_series(candles[:k], 4),
                k,
            )

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_volume_concentration_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = volume_concentration_series(candles, window=3)
        for k in range(1, len(candles) + 1):
            _prefix_stable(
                "volume_concentration",
                full,
                volume_concentration_series(candles[:k], 3),
                k,
            )


# ═══════════ الحتمية — السمات ═══════════


class TestFeaturesDeterminism:
    """نفس المدخلات مرتين ⇒ نفس البايتات."""

    @given(candles=candle_lists())
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_features_byte_identical_across_calls(self, candles: list[Candle]) -> None:
        calls: list[tuple[str, Callable[[list[Candle]], object]]] = [
            ("atr_pct", lambda cs: atr_pct_series(cs, 3, 5)),
            ("vov", lambda cs: vol_of_vol_series(cs, 3, 4)),
            ("gap", lambda cs: gap_shock_series(cs, 3)),
            ("dir_eff", lambda cs: directional_efficiency_series(cs, 4)),
            ("vol_conc", lambda cs: volume_concentration_series(cs, 3)),
        ]
        for name, call in calls:
            left, right = call(candles), call(candles)
            assert np.asarray(left).tobytes() == np.asarray(right).tobytes(), name


# ═══════════ §26.3 + A-02: المحرك الموضعي ═══════════


class TestEngineProperties:
    """حالات المحرك: بادئة مستقلة عن الذيل، وحتمية كاملة بين محركين."""

    @given(candles=candle_lists())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_engine_states_prefix_independent_of_tail(self, candles: list[Candle]) -> None:
        full = _run_engine(_TINY, candles)
        for k in range(1, len(candles) + 1):
            prefix = _run_engine(_TINY, candles[:k])
            assert prefix == full[:k], "حالة المحرك تأثرت بشموع لم تصل بعد"

    @given(candles=candle_lists())
    @hyp_settings(max_examples=20, deadline=None, derandomize=True)
    def test_two_engines_identical_states(self, candles: list[Candle]) -> None:
        first = _run_engine(_TINY, candles)
        second = _run_engine(_TINY, candles)
        assert first == second
