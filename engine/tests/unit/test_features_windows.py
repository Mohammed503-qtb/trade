"""اختبارات استخراج المصفوفات — بوابة السمات الموحدة (المهمة 2-c، A-02).

يُثبت: القيم الخام من OHLCV حصرًا (استقلال تام عن الحقول المشتقة المخزنة)،
الرفض الصارم لخلط الأدوات/الأطر وكسر الترتيب، وقانونية الفارغة والمفردة
والتساوي الزمني، وحساب العوائد اللوغاريتمية يدويًا.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from features import (
    bodies,
    closes,
    highs,
    log_returns,
    lows,
    opens,
    ranges,
    volumes,
)
from features.windows import FeatureSeries
from numpy.testing import assert_array_equal
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)


def _candle(
    index: int,
    *,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10.0,
    instrument_id: str = "BINANCE_USDM:BTCUSDT",
    timeframe: str = "1m",
    stored_range: float | None = None,
    stored_body: float | None = None,
) -> Candle:
    """شمعة اصطناعية — الحقول المشتقة تُملأ متسقة إلا إن كُذِبت عمدًا.

    ``stored_range``/``stored_body`` يسمحان بحقن قيم مخزنة كاذبة لإثبات أن
    طبقة السمات تقرأ OHLCV الخام وحده ولا تثق بالحقول المخزنة أبدًا.
    """
    span = high - low
    body = abs(close - open_)
    if span > 0.0:
        body_fraction = body / span
        close_location = (close - low) / span
    else:
        body_fraction = 0.0
        close_location = 0.5
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=_BASE + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=stored_range if stored_range is not None else span,
        body_size=stored_body if stored_body is not None else body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def _simple_three() -> list[Candle]:
    """ثلاث شموع بقيم مميزة معروفة لكل الحقول."""
    return [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0, volume=10.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0, volume=20.0),
        _candle(2, open_=102.0, high=106.0, low=101.0, close=105.0, volume=30.0),
    ]


# كل المستخرجات الثمانية — تُعلمم عليها اختبارات الرفض لقفل التحقق في كل واحدة.
EXTRACTORS: list[tuple[str, Callable[[list[Candle]], FeatureSeries]]] = [
    ("highs", highs),
    ("lows", lows),
    ("closes", closes),
    ("opens", opens),
    ("volumes", volumes),
    ("ranges", ranges),
    ("bodies", bodies),
    ("log_returns", log_returns),
]


# ─── القيم الخام ───


def test_extract_simple_values() -> None:
    """الثلاث البسيطة: كل مصفوفة بقيمها الحرفية."""
    candles = _simple_three()
    assert_array_equal(highs(candles), [102.0, 103.0, 106.0])
    assert_array_equal(lows(candles), [99.0, 100.0, 101.0])
    assert_array_equal(closes(candles), [101.0, 102.0, 105.0])
    assert_array_equal(opens(candles), [100.0, 101.0, 102.0])
    assert_array_equal(volumes(candles), [10.0, 20.0, 30.0])
    assert_array_equal(ranges(candles), [3.0, 3.0, 5.0])
    assert_array_equal(bodies(candles), [1.0, 1.0, 3.0])


def test_ranges_from_raw_ohlc_not_stored_field() -> None:
    """المدى يُحسب من high−low الخام — حقل range المخزن الكاذب لا يُقرأ."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0, stored_range=999.0),
        _candle(1, open_=101.0, high=103.0, low=100.0, close=102.0, stored_range=777.0),
    ]
    assert_array_equal(ranges(candles), [3.0, 3.0])


def test_bodies_signed() -> None:
    """الجسم موقّع: سالب للهابطة، موجب للصاعدة — الإشارة معلومة لا ضجيج."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=98.0, close=101.0),
        _candle(1, open_=101.0, high=102.0, low=98.0, close=99.0),
    ]
    assert_array_equal(bodies(candles), [1.0, -2.0])


def test_bodies_ignore_stored_body_size() -> None:
    """الجسم من close−open الخام — حقل body_size المخزن الكاذب لا يُقرأ."""
    candles = [
        _candle(0, open_=100.0, high=102.0, low=99.0, close=101.0, stored_body=999.0),
    ]
    assert_array_equal(bodies(candles), [1.0])


def test_float64_dtype_everywhere() -> None:
    """عقد الدقة: كل المصفوفات float64 حصرًا."""
    candles = _simple_three()
    for _, extractor in EXTRACTORS:
        assert extractor(candles).dtype == np.float64


# ─── القائمة الفارغة والمفردة ───


@pytest.mark.parametrize(("name", "extractor"), EXTRACTORS, ids=[n for n, _ in EXTRACTORS])
def test_empty_list_returns_empty_array(
    name: str, extractor: Callable[[list[Candle]], FeatureSeries]
) -> None:
    """الفارغة قانونية: مصفوفة فارغة بلا أخطاء (عقد الموديول)."""
    assert name  # التسمية تظهر في تقرير المعلمة
    out = extractor([])
    assert out.shape == (0,)
    assert out.dtype == np.float64


def test_single_candle() -> None:
    """المفردة قانونية: طول 1 والعوائد [nan] (لا سابق)."""
    candles = [_candle(0, open_=100.0, high=102.0, low=99.0, close=101.0)]
    assert_array_equal(highs(candles), [102.0])
    assert_array_equal(log_returns(candles), [np.nan])


# ─── العوائد اللوغاريتمية يدويًا ───


def test_log_returns_manual() -> None:
    """‎ln(c_t/c_{t−1})‎ بقيم يدوية — الأول nan دومًا.

    المدى الصريح [99, 107] يحتضن كل الإغلاقات حتى تكون كل شمعة صالحة
    بذاتها (الخرق المختبر هو منطق العوائد لا صلاحية OHLC).
    """
    candles = [
        _candle(0, close=101.0, high=107.0, low=99.0),
        _candle(1, close=102.0, high=107.0, low=99.0),
        _candle(2, close=105.0, high=107.0, low=99.0),
        _candle(3, close=106.0, high=107.0, low=99.0),
    ]
    expected = [np.nan, math.log(102.0 / 101.0), math.log(105.0 / 102.0), math.log(106.0 / 105.0)]
    out = log_returns(candles)
    assert np.isnan(out[0])
    # نفس التعبير اليدوي ضمن أولب واحد على الأكثر (np.log مقابل math.log)
    np.testing.assert_allclose(out[1:], expected[1:], rtol=1e-14)


def test_log_returns_constant_closes_zero() -> None:
    """إغلاقات ثابتة ⇒ أصفار تامة بعد الأول."""
    candles = [_candle(i, close=100.0) for i in range(4)]
    out = log_returns(candles)
    assert np.isnan(out[0])
    assert_array_equal(out[1:], [0.0, 0.0, 0.0])


# ─── التساوي الزمني والترتيب ───


def test_equal_bar_times_allowed() -> None:
    """غير متناقص يسمح بالتساوي — رفض التكرار مسؤولية المحركات لا الاستخراج."""
    candles = [
        _candle(0, close=100.0),
        _candle(0, close=101.0),
    ]
    assert_array_equal(closes(candles), [100.0, 101.0])


def test_equal_then_greater_allowed() -> None:
    """تساوٍ ثم صعود: قانوني بالكامل."""
    candles = [
        _candle(0, close=100.0),
        _candle(0, close=100.5),
        _candle(1, close=101.0),
    ]
    assert closes(candles).shape == (3,)


# ─── الرفض الصارم ───


@pytest.mark.parametrize(("name", "extractor"), EXTRACTORS, ids=[n for n, _ in EXTRACTORS])
def test_mixed_instruments_rejected_everywhere(
    name: str, extractor: Callable[[list[Candle]], FeatureSeries]
) -> None:
    """خلط أدوات ⇒ ValueError في كل مستخرج بلا استثناء."""
    assert name  # التسمية تظهر في تقرير المعلمة
    candles = [
        _candle(0, instrument_id="BINANCE_USDM:BTCUSDT"),
        _candle(1, instrument_id="BINANCE_USDM:ETHUSDT"),
    ]
    with pytest.raises(ValueError, match="خلط أدوات"):
        extractor(candles)


@pytest.mark.parametrize(("name", "extractor"), EXTRACTORS, ids=[n for n, _ in EXTRACTORS])
def test_descending_bar_time_rejected_everywhere(
    name: str, extractor: Callable[[list[Candle]], FeatureSeries]
) -> None:
    """الترتيب المعكوس ⇒ ValueError في كل مستخرج."""
    assert name  # التسمية تظهر في تقرير المعلمة
    candles = [
        _candle(1, close=100.0),
        _candle(0, close=101.0),
    ]
    with pytest.raises(ValueError, match="غير تصاعدي"):
        extractor(candles)


def test_mixed_timeframes_rejected() -> None:
    """خلط أطر ⇒ ValueError برسالة تسمّي الإطارين."""
    candles = [
        _candle(0, timeframe="1m"),
        _candle(1, timeframe="5m"),
    ]
    with pytest.raises(ValueError, match="خلط أطر"):
        closes(candles)


def test_error_messages_name_the_offenders() -> None:
    """الرسائل عربية وتسمّي المخطئين: الأداتين، والإطارين، والموضع."""
    mixed = [
        _candle(0, instrument_id="BINANCE_USDM:BTCUSDT"),
        _candle(1, instrument_id="BINANCE_USDM:ETHUSDT"),
    ]
    with pytest.raises(ValueError) as exc_info:
        closes(mixed)
    message = str(exc_info.value)
    assert "BINANCE_USDM:BTCUSDT" in message
    assert "BINANCE_USDM:ETHUSDT" in message
    assert "الموضع 1" in message

    descending = [_candle(5), _candle(3)]
    with pytest.raises(ValueError) as exc_info:
        closes(descending)
    assert "تصاعدي" in str(exc_info.value)


def test_first_violation_reported_not_last() -> None:
    """أول خرق يوقف الحساب — رسالة الموضع 2 لا 3.

    الإغلاقات داخل النطاق الافتراضي [low, high] حصرًا حتى يكون الخرق
    الوحيد المختبر هو تراجع bar_time عند الموضع 2 (لا صلاحية OHLC).
    """
    candles = [
        _candle(0, close=100.1),
        _candle(1, close=100.2),
        _candle(0, close=100.3),  # تراجع عند الموضع 2
        _candle(0, close=100.4),  # تراجع لاحق لا يصل إليه الفحص
    ]
    with pytest.raises(ValueError, match="الموضع 2"):
        closes(candles)
