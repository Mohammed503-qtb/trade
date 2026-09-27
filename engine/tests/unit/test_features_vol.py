"""اختبارات سمات التقلب — مرجعية مزدوجة (المهمة 2-c، §16).

(1) **قيم يدوية**: كل سمة على شموع 3-5 بسيطة بقيم محسوبة باليد حرفيًا
    (خطوات ثنائية التمثيل حيث أمكن تُقارن بالمطابقة التامة).
(2) **اختبار الجسر**: نفس المدخلات تُمرر لquantmath مباشرة == خرج السمة
    بالتطابق البايتي — الجسر لا يشوه (A-02: لا مسار موازٍ للرياضيات).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from features import (
    atr_pct_series,
    atr_series,
    directional_efficiency_series,
    expected_holding_vol_series,
    gap_shock_series,
    normalized_range_series,
    range_expansion_series,
    realized_vol_series,
    spread_to_range_series,
    vol_of_vol_series,
    volume_concentration_series,
)
from features.windows import (
    FeatureSeries,
    bodies,
    closes,
    highs,
    log_returns,
    lows,
    opens,
    ranges,
    volumes,
)
from numpy.testing import assert_array_equal
from quantmath import (
    atr_percentile,
    expected_holding_vol,
    gap_shock,
    range_expansion_percentile,
    realized_volatility,
    rolling_mean,
    spread_to_range,
    true_range,
    vol_of_vol,
    wilder_atr,
)
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)


def _candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
) -> Candle:
    """شمعة اصطناعية بقيم مشتقة متسقة — الحقول المشتقة لا تُقرأ أصلًا هنا."""
    span = high - low
    body = abs(close - open_)
    if span > 0.0:
        body_fraction = body / span
        close_location = (close - low) / span
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
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)),
    )


def _by_closes(closes: list[float], *, volume: float = 10.0) -> list[Candle]:
    """شموع بمسارات محكومة: open = إغلاق السابق، قمم/قيعان تحيط بالجسم."""
    out: list[Candle] = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i > 0 else close
        high = max(open_, close) + 0.5
        low = min(open_, close) - 0.5
        out.append(_candle(i, open_=open_, high=high, low=low, close=close, volume=volume))
    return out


def _synth(n: int) -> list[Candle]:
    """سلسلة حتمية مضطربة (150 شمعة) — غذاء اختبارات الجسر والدافئ."""
    out: list[Candle] = []
    for i in range(n):
        open_ = 100.0 + math.sin(i / 5.0) * 5.0 + ((i % 3) - 1) * 0.25
        close = 100.0 + math.sin((i + 1) / 5.0) * 5.0
        high = max(open_, close) + abs(math.sin(i / 3.0)) * 2.0 + 0.5
        low = min(open_, close) - abs(math.cos(i / 4.0)) * 2.0 - 0.5
        out.append(
            _candle(i, open_=open_, high=high, low=low, close=close, volume=100.0 + (i * 37) % 90)
        )
    return out


def _ohlc(
    candles: list[Candle],
) -> tuple[FeatureSeries, FeatureSeries, FeatureSeries, FeatureSeries]:
    return opens(candles), highs(candles), lows(candles), closes(candles)


# ═══════════ (1) المرجع اليدوي ═══════════


def test_atr_manual_wilder_period2() -> None:
    """TR = [3,3,5,3] باليد ⇒ ATR(2) = [nan, 3.0, 4.0, 3.5] (خطوات ثنائية التمثيل)."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0),
        _candle(3, open_=105.0, high=107.0, low=104.0, close=106.0),
    ]
    out = atr_series(candles, period=2)
    assert np.isnan(out[0])
    assert out[1] == 3.0  # بذرة: متوسط TR[0:2]
    assert out[2] == 4.0  # (3.0×1 + 5)/2
    assert out[3] == 3.5  # (4.0×1 + 3)/2


def test_atr_manual_warmup_period3() -> None:
    """period=3: أول قيمتان nan والثالثة بذرة متوسط أول ثلاثة TR."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),  # TR=3
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0),  # TR=3
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0),  # TR=5
        _candle(3, open_=105.0, high=107.0, low=104.0, close=106.0),  # TR=3
    ]
    out = atr_series(candles, period=3)
    assert np.isnan(out[:2]).all()
    assert out[2] == (3.0 + 3.0 + 5.0) / 3.0
    assert out[3] == (((3.0 + 3.0 + 5.0) / 3.0) * 2.0 + 3.0) / 3.0


def test_atr_pct_manual() -> None:
    """ATR(2)=[nan,3,4,3.5] والمئيني(3) = [nan,nan,1.0,0.5] باليد (نافذة شاملة)."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0),
        _candle(3, open_=105.0, high=107.0, low=104.0, close=106.0),
    ]
    out = atr_pct_series(candles, atr_period=2, pct_window=3)
    assert np.isnan(out[:2]).all()
    # عند i=2: النافذة [nan,3,4] والقيمة 4 تعلو 3 قطعيًا: 1/(2−1)=1.0
    assert out[2] == 1.0
    # عند i=3: النافذة [3,4,3.5] والقيمة 3.5 تعلو 3 فقط: 1/(3−1)=0.5
    assert out[3] == 0.5


def test_realized_vol_manual() -> None:
    """rv(2) عند i=2: انحراف عينة [ln(102/101), ln(105/102)] بحساب يدوي صريح."""
    candles = _by_closes([101.0, 102.0, 105.0, 106.0])
    r1 = math.log(102.0 / 101.0)
    r2 = math.log(105.0 / 102.0)
    mean = (r1 + r2) / 2.0
    variance = ((r1 - mean) ** 2 + (r2 - mean) ** 2) / (2.0 - 1.0)
    expected = math.sqrt(variance)
    out = realized_vol_series(candles, window=2)
    assert np.isnan(out[:2]).all()
    assert out[2] == pytest.approx(expected, rel=1e-12)
    assert np.isnan(out[0])


def test_range_expansion_manual() -> None:
    """مدىات [3,3,5,3]: توسع كامل 1.0 عند 5 ثم 0.0 عند العودة إلى 3."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0),
        _candle(3, open_=105.0, high=107.0, low=104.0, close=106.0),
    ]
    out = range_expansion_series(candles, window=3)
    assert np.isnan(out[:2]).all()
    assert out[2] == 1.0  # 5 يعلو [3,3] قطعيًا: 2/(3−1)
    assert out[3] == 0.0  # 3 لا يعلو شيئًا من [3,5,3]


def test_vol_of_vol_manual() -> None:
    """vov = انحراف نافذة rv ÷ |متوسطها| — حساب يدوي صريح لسلسلتين متتاليتين."""
    candles = _by_closes([101.0, 102.0, 105.0, 106.0, 109.0])
    r = [math.log(candles[i].close / candles[i - 1].close) for i in range(1, 5)]

    # rv(2) بالفهارس البشرية: rv_1 = std(r1,r2), rv_2 = std(r2,r3), rv_3 = std(r3,r4)
    def _std2(a: float, b: float) -> float:
        m = (a + b) / 2.0
        return math.sqrt(((a - m) ** 2 + (b - m) ** 2) / 1.0)

    rv2, rv3 = _std2(r[0], r[1]), _std2(r[1], r[2])
    mean = (rv2 + rv3) / 2.0
    expected = _std2(rv2, rv3) / mean
    out = vol_of_vol_series(candles, rv_window=2, vov_window=2)
    assert np.isnan(out[:3]).all()
    assert out[3] == pytest.approx(expected, rel=1e-12)


def test_gap_shock_manual() -> None:
    """فجوة 3 نقاط مع ATR=4 (period=1 ⇒ ATR≡TR) ⇒ 0.75 بالضبط؛ ولا فجوة ⇒ 0."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),  # TR=3
        _candle(1, open_=104.0, high=105.0, low=103.0, close=104.0),  # TR=4 (يفصل الإغلاق السابق)
        _candle(2, open_=104.0, high=104.5, low=103.5, close=104.0),  # TR=1
    ]
    out = gap_shock_series(candles, atr_period=1)
    assert np.isnan(out[0])
    assert out[1] == 3.0 / 4.0
    assert out[2] == 0.0


def test_spread_to_range_manual() -> None:
    """جسم 4 من مدى 6 ⇒ 4/6؛ والشمعة المسطحة ⇒ 0.0 (عقد الحارس)."""
    candles = [
        _candle(0, open_=100.0, high=105.0, low=99.0, close=104.0),
        _candle(1, open_=100.0, high=100.0, low=100.0, close=100.0),
    ]
    out = spread_to_range_series(candles)
    assert out[0] == 4.0 / 6.0
    assert out[1] == 0.0


def test_expected_holding_vol_manual() -> None:
    """horizon=4 ⇒ ×2.0 بالضبط — عنصريًا لكل rv مكتمل النافذة (العقد الموثق).

    الدافئ: ret[0]=nan ⇒ الموضعان 0 و1 فقط nan (نافذة 2 عند الموضع 1
    تختزل إلى عنصر واحد بddof=1 ⇒ nan)؛ الموضعان 2 و3 محسوبان يدويًا.
    """
    candles = _by_closes([101.0, 102.0, 105.0, 106.0])
    r1 = math.log(102.0 / 101.0)
    r2 = math.log(105.0 / 102.0)
    r3 = math.log(106.0 / 105.0)

    def _rv_pair(a: float, b: float) -> float:
        m = (a + b) / 2.0
        return math.sqrt(((a - m) ** 2 + (b - m) ** 2) / 1.0)

    out = expected_holding_vol_series(candles, horizon_bars=4, rv_window=2)
    assert np.isnan(out[:2]).all()
    assert out[2] == pytest.approx(_rv_pair(r1, r2) * 2.0, rel=1e-12)
    assert out[3] == pytest.approx(_rv_pair(r2, r3) * 2.0, rel=1e-12)


def test_expected_holding_vol_rejects_bad_horizon() -> None:
    """horizon صحيح ≥ 1 وإلا ValueError (عقد quantmath يمر عبر الجسر)."""
    candles = _by_closes([101.0, 102.0, 105.0, 106.0])
    with pytest.raises(ValueError, match="horizon_bars"):
        expected_holding_vol_series(candles, horizon_bars=0, rv_window=2)


def test_normalized_range_manual() -> None:
    """range/ATR باليد: [nan, 3/3, 5/4, 3/3.5]."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0),
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0),
        _candle(3, open_=105.0, high=107.0, low=104.0, close=106.0),
    ]
    out = normalized_range_series(candles, atr_period=2)
    assert np.isnan(out[0])
    assert out[1] == 1.0
    assert out[2] == 5.0 / 4.0
    assert out[3] == 3.0 / 3.5


def test_directional_efficiency_manual() -> None:
    """كوفمان ER: [100,102,101,103] w=3 ⇒ 3/5؛ والاتجاه النقي ⇒ 1.0؛ والذهاب والإياب ⇒ 0."""
    out = directional_efficiency_series(_by_closes([100.0, 102.0, 101.0, 103.0]), window=3)
    assert np.isnan(out[:3]).all()
    assert out[3] == 3.0 / 5.0  # |103−100| / (2+1+2)

    pure = directional_efficiency_series(_by_closes([100.0, 101.0, 102.0, 103.0]), window=3)
    assert pure[3] == 1.0

    round_trip = directional_efficiency_series(_by_closes([100.0, 103.0, 100.0]), window=2)
    assert round_trip[2] == 0.0  # صافي صفر مسافة كلية 6


def test_directional_efficiency_flat_window_nan() -> None:
    """نافذة بلا أي حركة ⇒ مقام صفري ⇒ nan (الكفاءة غير معرفة)."""
    out = directional_efficiency_series(_by_closes([100.0, 100.0, 100.0, 100.0]), window=3)
    assert np.isnan(out).all()


def test_volume_concentration_manual() -> None:
    """حجم 30 مقابل متوسط نافذة (10+10+30)/3 ⇒ 1.8؛ والصامتة الكاملة ⇒ nan."""
    candles = [
        _candle(0, open_=100.0, high=101.0, low=99.0, close=100.0, volume=10.0),
        _candle(1, open_=100.0, high=101.0, low=99.0, close=100.0, volume=10.0),
        _candle(2, open_=100.0, high=101.0, low=99.0, close=100.0, volume=10.0),
        _candle(3, open_=100.0, high=101.0, low=99.0, close=100.0, volume=30.0),
    ]
    out = volume_concentration_series(candles, window=3)
    assert np.isnan(out[:2]).all()
    assert out[2] == pytest.approx(1.0, rel=1e-12)
    assert out[3] == pytest.approx(30.0 / ((10.0 + 10.0 + 30.0) / 3.0), rel=1e-12)

    silent = [
        _candle(i, open_=100.0, high=101.0, low=99.0, close=100.0, volume=0.0) for i in range(4)
    ]
    assert np.isnan(volume_concentration_series(silent, window=3)).all()


@pytest.mark.parametrize(
    ("factory", "kwargs", "match"),
    [
        (atr_series, {"period": 0}, "period"),
        (atr_pct_series, {"atr_period": 0}, "period"),
        (atr_pct_series, {"pct_window": 1}, "window"),
        (realized_vol_series, {"window": 1}, "window"),
        (range_expansion_series, {"window": 1}, "window"),
        (vol_of_vol_series, {"rv_window": 1}, "window"),
        (vol_of_vol_series, {"vov_window": 1}, "window"),
        (gap_shock_series, {"atr_period": 0}, "period"),
        (directional_efficiency_series, {"window": 0}, "window"),
        (volume_concentration_series, {"window": 0}, "window"),
    ],
    ids=[
        "atr-period0",
        "atrpct-atrperiod0",
        "atrpct-window1",
        "rv-window1",
        "rangeexp-window1",
        "vov-rvwindow1",
        "vov-vovwindow1",
        "gap-atrperiod0",
        "direff-window0",
        "volconc-window0",
    ],
)
def test_window_validation_rejected(
    factory: Callable[..., FeatureSeries], kwargs: dict[str, int], match: str
) -> None:
    """النوافذ غير الصالحة ترفض بValueError — عقود quantmath تمر عبر الجسر كاملة."""
    candles = _by_closes([100.0, 101.0, 102.0, 103.0, 101.0])
    with pytest.raises(ValueError, match=match):
        factory(candles, **kwargs)


# ═══════════ (2) اختبار الجسر — quantmath مباشرة == السمة ═══════════


def test_bridge_atr() -> None:
    candles = _synth(150)
    _o, h, low, c = _ohlc(candles)
    direct = wilder_atr(true_range(h, low, c), 14)
    assert_array_equal(atr_series(candles, period=14), direct)


def test_bridge_atr_pct() -> None:
    candles = _synth(150)
    _, h, low, c = _ohlc(candles)
    direct = atr_percentile(wilder_atr(true_range(h, low, c), 14), 100)
    assert_array_equal(atr_pct_series(candles, atr_period=14, pct_window=100), direct)


def test_bridge_realized_vol() -> None:
    candles = _synth(150)
    direct = realized_volatility(log_returns(candles), 20)
    assert_array_equal(realized_vol_series(candles, window=20), direct)


def test_bridge_range_expansion() -> None:
    candles = _synth(150)
    direct = range_expansion_percentile(ranges(candles), 100)
    assert_array_equal(range_expansion_series(candles, window=100), direct)


def test_bridge_vol_of_vol() -> None:
    candles = _synth(150)
    direct = vol_of_vol(realized_volatility(log_returns(candles), 20), 50)
    assert_array_equal(vol_of_vol_series(candles, rv_window=20, vov_window=50), direct)


def test_bridge_gap_shock() -> None:
    candles = _synth(150)
    o, h, low, c = _ohlc(candles)
    atr = wilder_atr(true_range(h, low, c), 14)
    direct = gap_shock(o, c, atr)
    assert_array_equal(gap_shock_series(candles, atr_period=14), direct)


def test_bridge_spread_to_range() -> None:
    candles = _synth(150)
    direct = spread_to_range(bodies(candles), ranges(candles))
    assert_array_equal(spread_to_range_series(candles), direct)


def test_bridge_expected_holding_vol() -> None:
    candles = _synth(150)
    series = expected_holding_vol_series(candles, horizon_bars=25, rv_window=20)
    rv = realized_volatility(log_returns(candles), 20)
    for i in range(rv.shape[0]):
        expected = expected_holding_vol(float(rv[i]), 25)
        if math.isnan(expected):
            assert np.isnan(series[i])
        else:
            assert series[i] == expected  # نفس التعبير — تطابق تام


def test_bridge_normalized_range() -> None:
    candles = _synth(150)
    _, h, low, c = _ohlc(candles)
    atr = wilder_atr(true_range(h, low, c), 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        direct = ranges(candles) / atr
    assert_array_equal(normalized_range_series(candles, atr_period=14), direct)


def test_bridge_volume_concentration() -> None:
    candles = _synth(150)
    v = volumes(candles)
    means = rolling_mean(v, 20)
    with np.errstate(divide="ignore", invalid="ignore"):
        direct = v / means
    direct[means == 0.0] = np.nan
    assert_array_equal(volume_concentration_series(candles, window=20), direct)


# ═══════════ الدافئ: مواضع أول قيمة غير nan ═══════════


@pytest.mark.parametrize(
    ("factory", "kwargs", "expected_index"),
    [
        (atr_series, {"period": 14}, 13),
        (atr_pct_series, {"atr_period": 14, "pct_window": 100}, 99),
        (realized_vol_series, {"window": 20}, 19),
        (range_expansion_series, {"window": 100}, 99),
        (vol_of_vol_series, {"rv_window": 20, "vov_window": 50}, 49),
        (gap_shock_series, {"atr_period": 14}, 13),
        (spread_to_range_series, {}, 0),
        (normalized_range_series, {"atr_period": 14}, 13),
        (directional_efficiency_series, {"window": 20}, 20),
        (volume_concentration_series, {"window": 20}, 19),
        (expected_holding_vol_series, {"horizon_bars": 60, "rv_window": 20}, 19),
    ],
    ids=[
        "atr14",
        "atrpct-14-100",
        "rv20",
        "rangeexp100",
        "vov-20-50",
        "gap14",
        "spread",
        "normrange14",
        "direff20",
        "volconc20",
        "ehv-60-20",
    ],
)
def test_first_non_nan_position(
    factory: Callable[..., FeatureSeries], kwargs: dict[str, int], expected_index: int
) -> None:
    """مواضع الدافئ الافتراضية مقفلة حرفيًا (اشتقاق موثق في VolatilityConfig.warmup_bars)."""
    candles = _synth(150)
    out = factory(candles, **kwargs)
    assert np.isnan(out[:expected_index]).all(), "الدافئ أقصر من الموثق"
    assert not np.isnan(out[expected_index]), "الدافئ أطول من الموثق"


@pytest.mark.parametrize(
    "factory",
    [
        atr_series,
        atr_pct_series,
        realized_vol_series,
        range_expansion_series,
        vol_of_vol_series,
        gap_shock_series,
        spread_to_range_series,
        normalized_range_series,
        directional_efficiency_series,
        volume_concentration_series,
    ],
    ids=[
        "atr",
        "atrpct",
        "rv",
        "rangeexp",
        "vov",
        "gap",
        "spread",
        "normrange",
        "direff",
        "volconc",
    ],
)
def test_empty_candles_returns_empty(factory: Callable[..., FeatureSeries]) -> None:
    """القائمة الفارغة قانونية لكل السمات: مصفوفة فارغة بعد تحقق الاتساق."""
    out = factory([])
    assert out.shape == (0,)
    assert out.dtype == np.float64


def test_single_candle_spread_defined_rest_nan() -> None:
    """من شمعة واحدة: السبر معرف والباقي nan — لا انفجار ولا استنتاج مزيف."""
    candles = [_candle(0, open_=100.0, high=102.0, low=99.0, close=101.0)]
    assert spread_to_range_series(candles).shape == (1,)
    assert spread_to_range_series(candles)[0] == 1.0 / 3.0
    assert np.isnan(atr_series(candles, period=14))[0]
    assert np.isnan(realized_vol_series(candles, window=20))[0]
    assert np.isnan(gap_shock_series(candles, atr_period=14))[0]
