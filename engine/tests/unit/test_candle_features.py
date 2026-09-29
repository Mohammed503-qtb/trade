"""اختبارات سمات الشموع الست (§13.1) — المهمة 5-a.

يُقفل: القيم اليدوية الهندسية المحسوبة، عقود nan الدافئ (الفورية الثلاث
بلا دافئ، وذوات النوافذ حتى اكتمالها)، قرارات المدى المنعدم الموثقة
(0.0 / 0.0 / 0.5)، القائمة الفارغة، حوارس القسمة (متوسط منعدم ⇒ nan)،
الحدود [0,1] و[-1,+1]، والتسجيل في السجل المركزي (compute_feature
بالمسار الوحيد A-02).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from features import (
    body_fraction_series,
    close_location_series,
    compute_feature,
    gap_relationship_series,
    range_percentile_series,
    volume_relationship_series,
    wick_asymmetry_series,
)
from numpy.typing import NDArray
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)
_INSTRUMENT = "BINANCE_USDM:BTCUSDT"


def _make_candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
) -> Candle:
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=_INSTRUMENT,
        timeframe="1m",
        bar_time=_BASE + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=(body / span) if span > 0 else 0.0,
        close_location_value=((close - low) / span) if span > 0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0 else 0.0,
    )


# ─── بناة هندسية مصطنعة بسيطة ───


def _flat_series(n: int, *, high: float = 110.0, low: float = 90.0) -> list[Candle]:
    """شموع متطابقة تمامًا: فتح 100 إغلاق 100 بظلَّي 10/10 — تناظر تام."""
    return [_make_candle(i, open_=100.0, high=high, low=low, close=100.0) for i in range(n)]


def _varied_series(n: int = 130) -> list[Candle]:
    """سلسلة حتمية مضطربة كافية لاكتمال دافئ النوافذ (window=100)."""
    candles: list[Candle] = []
    for i in range(n):
        drift = math.sin(i / 7.0) * 8.0
        open_ = 100.0 + drift
        close = 100.0 + math.cos(i / 5.0) * 6.0 + drift * 0.5
        high = max(open_, close) + 1.0 + (i % 5)
        low = min(open_, close) - 1.0 - (i % 3)
        candles.append(
            _make_candle(
                i, open_=open_, high=high, low=low, close=close, volume=80.0 + (i * 31) % 90
            )
        )
    return candles


# ─── body_fraction ───


class TestBodyFraction:
    def test_manual_values(self) -> None:
        # شمعة: open=100 close=110 high=112 low=98 ⇒ |110-100|/14 = 10/14
        candle = _make_candle(0, open_=100.0, high=112.0, low=98.0, close=110.0)
        out = body_fraction_series([candle])
        assert out[0] == pytest.approx(10.0 / 14.0)

    def test_doji_zero_and_full_body(self) -> None:
        doji = _make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.0)
        marubozu = _make_candle(1, open_=100.0, high=110.0, low=100.0, close=110.0)
        out = body_fraction_series([doji, marubozu])
        assert out[0] == pytest.approx(0.0)
        assert out[1] == pytest.approx(1.0)

    def test_flat_candle_yields_zero(self) -> None:
        flat = _make_candle(0, open_=100.0, high=100.0, low=100.0, close=100.0)
        assert body_fraction_series([flat])[0] == 0.0

    def test_bounds_property(self) -> None:
        out = body_fraction_series(_varied_series())
        assert np.all((out >= 0.0) & (out <= 1.0))


# ─── wick_asymmetry ───


class TestWickAsymmetry:
    def test_manual_lower_wick_dominant(self) -> None:
        # open=close=100, high=101, low=95 ⇒ upper=1, lower=5, asym=(1-5)/6
        candle = _make_candle(0, open_=100.0, high=101.0, low=95.0, close=100.0)
        assert wick_asymmetry_series([candle])[0] == pytest.approx((1.0 - 5.0) / 6.0)

    def test_upper_wick_dominant_positive(self) -> None:
        candle = _make_candle(0, open_=100.0, high=105.0, low=99.0, close=100.0)
        assert wick_asymmetry_series([candle])[0] == pytest.approx((5.0 - 1.0) / 6.0)

    def test_symmetric_zero(self) -> None:
        out = wick_asymmetry_series(_flat_series(3))
        assert np.all(out == 0.0)

    def test_flat_candle_yields_zero(self) -> None:
        flat = _make_candle(0, open_=100.0, high=100.0, low=100.0, close=100.0)
        assert wick_asymmetry_series([flat])[0] == 0.0

    def test_signed_bounds_property(self) -> None:
        out = wick_asymmetry_series(_varied_series())
        assert np.all((out >= -1.0) & (out <= 1.0))


# ─── close_location ───


class TestCloseLocation:
    def test_manual_values(self) -> None:
        # close=low ⇒ 0؛ close=high ⇒ 1؛ close=منتصف ⇒ 0.5
        at_low = _make_candle(0, open_=100.0, high=110.0, low=90.0, close=90.0)
        at_high = _make_candle(1, open_=100.0, high=110.0, low=90.0, close=110.0)
        mid = _make_candle(2, open_=100.0, high=110.0, low=90.0, close=100.0)
        out = close_location_series([at_low, at_high, mid])
        assert out[0] == pytest.approx(0.0)
        assert out[1] == pytest.approx(1.0)
        assert out[2] == pytest.approx(0.5)

    def test_flat_candle_yields_half(self) -> None:
        flat = _make_candle(0, open_=100.0, high=100.0, low=100.0, close=100.0)
        assert close_location_series([flat])[0] == 0.5

    def test_bounds_property(self) -> None:
        out = close_location_series(_varied_series())
        assert np.all((out >= 0.0) & (out <= 1.0))


# ─── range_percentile ───


class TestRangePercentile:
    def test_warmup_nan_then_values(self) -> None:
        window = 5
        out = range_percentile_series(_varied_series(12), window)
        assert np.all(np.isnan(out[: window - 1]))
        assert np.all(~np.isnan(out[window - 1 :]))
        assert np.all((out[window - 1 :] >= 0.0) & (out[window - 1 :] <= 1.0))

    def test_highest_range_top_percentile(self) -> None:
        candles = _varied_series(10)
        ranges = [c.range for c in candles]
        window = 10
        out = range_percentile_series(candles, window)
        # آخر شمعة بمدى الأعلى قطعيًا في نافذتها ⇒ 1.0
        top_index = int(np.argmax(ranges))
        if top_index >= window - 1:
            assert out[top_index] == 1.0

    def test_constant_series_zero(self) -> None:
        # عقد rolling_percentile: سلسلة ثابتة ⇒ 0.0 (لا توسع فوق سابق)
        out = range_percentile_series(_flat_series(8), 4)
        assert np.all(out[3:] == 0.0)

    def test_empty_list(self) -> None:
        out = range_percentile_series([], 5)
        assert out.shape == (0,)


# ─── gap_relationship ───


class TestGapRelationship:
    def test_first_nan_manual_values(self) -> None:
        # شمعتان: الأولى close=90؛ الثانية open=95 ⇒ gap=+5 على متوسط مدى نافذة 2
        first = _make_candle(0, open_=100.0, high=101.0, low=89.0, close=90.0)
        second = _make_candle(1, open_=95.0, high=105.0, low=94.0, close=104.0)
        out = gap_relationship_series([first, second], 2)
        assert np.isnan(out[0])
        # متوسط مدى النافذة الخلفية الشاملة عند الموضع 1: (12+11)/2 = 11.5
        assert out[1] == pytest.approx(5.0 / 11.5)

    def test_no_gap_zero(self) -> None:
        # افحص مواضع لا فجوة فيها: أعد بناء سلسلة بفتح = إغلاق السابق
        chained: list[Candle] = []
        prev_close = 100.0
        for i in range(6):
            close = prev_close + (1.0 if i % 2 == 0 else -1.0)
            chained.append(
                _make_candle(
                    i,
                    open_=prev_close,
                    high=max(prev_close, close) + 1,
                    low=min(prev_close, close) - 1,
                    close=close,
                )
            )
            prev_close = close
        out = gap_relationship_series(chained, 3)
        assert np.all(out[2:] == 0.0)

    def test_warmup_respects_window(self) -> None:
        window = 20
        out = gap_relationship_series(_varied_series(40), window)
        assert np.all(np.isnan(out[: window - 1]))

    def test_empty_list(self) -> None:
        out = gap_relationship_series([], 5)
        assert out.shape == (0,)

    def test_zero_mean_range_is_nan(self) -> None:
        # شموع مسطحة كاملة (مدى منعدم) ⇒ متوسط منعدم ⇒ nan لا inf
        flats = [_make_candle(i, open_=100.0, high=100.0, low=100.0, close=100.0) for i in range(6)]
        out = gap_relationship_series(flats, 3)
        assert np.all(np.isnan(out))


# ─── volume_relationship ───


class TestVolumeRelationship:
    def test_manual_ratio(self) -> None:
        candles = _varied_series(4)
        candles = [c.model_copy(update={"volume": 100.0}) for c in candles]
        out = volume_relationship_series(candles, 4)
        # متوسط نافذة شاملة 4 قيم متطابقة = 100 ⇒ النسبة 1.0
        assert np.all(out[3:] == 1.0)

    def test_expansion_above_one(self) -> None:
        candles = _varied_series(5)
        candles = [c.model_copy(update={"volume": 100.0}) for c in candles[:-1]] + [
            candles[-1].model_copy(update={"volume": 300.0})
        ]
        out = volume_relationship_series(candles, 5)
        # النافذة الخلفية شاملة للقيمة الحالية: (4×100+300)/5 = 140
        assert out[-1] == pytest.approx(300.0 / 140.0)

    def test_warmup_nan(self) -> None:
        out = volume_relationship_series(_varied_series(25), 20)
        assert np.all(np.isnan(out[:19]))

    def test_empty_list(self) -> None:
        out = volume_relationship_series([], 5)
        assert out.shape == (0,)


# ─── التسجيل في السجل المركزي (عقد A-02) ───


class TestRegistryWiring:
    @pytest.mark.parametrize(
        ("name", "factory"),
        [
            ("body_fraction", lambda cs: body_fraction_series(cs)),
            ("wick_asymmetry", lambda cs: wick_asymmetry_series(cs)),
            ("close_location", lambda cs: close_location_series(cs)),
            ("range_percentile_100", lambda cs: range_percentile_series(cs, 100)),
            ("gap_relationship_20", lambda cs: gap_relationship_series(cs, 20)),
            ("volume_relationship_20", lambda cs: volume_relationship_series(cs, 20)),
        ],
    )
    def test_compute_feature_matches_direct_call(
        self, name: str, factory: Callable[[list[Candle]], NDArray[np.float64]]
    ) -> None:
        candles = _varied_series()
        assert compute_feature(name, candles).tobytes() == factory(candles).tobytes()

    def test_override_window_wins(self) -> None:
        candles = _varied_series(60)
        overridden = compute_feature("volume_relationship_20", candles, window=5)
        assert overridden.tobytes() == volume_relationship_series(candles, 5).tobytes()

    def test_series_length_contract(self) -> None:
        candles = _varied_series(50)
        for name in (
            "body_fraction",
            "wick_asymmetry",
            "close_location",
            "range_percentile_100",
            "gap_relationship_20",
            "volume_relationship_20",
        ):
            assert len(compute_feature(name, candles)) == len(candles), name
