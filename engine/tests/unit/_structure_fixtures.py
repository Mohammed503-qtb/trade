"""مساعدات مشتركة لاختبارات البنية (المهمة 3-b) — بناة شموع وحالات تقلب.

النمط نفسه المستقل في tests/unit/test_swings.py (الوكيل السابق) بعد إثبات
أن بناةه المحلية تنتج شموعًا فاسدة عند خلط الأطراف: الباني هنا يشتق كل
الحقول العشرين من OHLC خام متسق (``high ≥ max(open, close)`` و
``low ≤ min(open, close)``) فلا يُبنى مدخل مرفوض أبدًا — والدقة العشرية
للقيم المختارة تجعل النسب المشتقة قابلة للحساب اليدوي في التوكعات.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from market_state.volatility import VolatilityState
from schemas import Candle, DataQuality

__all__ = [
    "BASE_TIME",
    "INSTRUMENT",
    "TIMEFRAME",
    "make_candle",
    "make_vol_state",
]

#: طابع الشمعة الأولى — الدقائق ترقّم الأشرطة (إطار الدقيقة).
BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def make_candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    """شمعة مغلقة كاملة الحقول العشرين — كل المشتقات من OHLC الخام.

    :raises ValueError: إذا خرقت الأطراف مدى الشمعة (high/low لا يحتويان
        open/close) — فساد المدخل يُرفض عند البناء لا عند الاستهلاك.
    """
    if high < max(open_, close) or low > min(open_, close):
        raise ValueError(
            f"أطراف خارج المدى: OHLC=({open_}, {high}, {low}, {close}) — "
            "يجب أن يحتوي [low, high] الافتتاحَ والإغلاقَ (عقد §8.1)"
        )
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span if span > 0.0 else 0.0,
        close_location_value=(close - low) / span if span > 0.0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def make_vol_state(
    atr: float | None,
    *,
    expansion: float | None = 0.5,
    bar_time: datetime | None = None,
) -> VolatilityState:
    """حالة تقلب مصنوعة يدويًا — ما يقرؤه كاشف البنية منها حصرًا:
    ``atr`` و``range_expansion_percentile`` وطابع الحارس.
    """
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=0.001,
        range_expansion_percentile=expansion,
        vol_of_vol=0.1,
        gap_shock=0.0,
        spread_to_range=0.5,
        expected_holding_vol_1h=0.001,
        bar_time=bar_time,
    )
