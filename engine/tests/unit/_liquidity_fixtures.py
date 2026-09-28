"""عدة اختبارات السيولة (المهمة 3-d) — بناة مشتركة لملفات الاختبار الثلاثة.

بناة صرفة بلا حالة: شمعة قانونية قيمها المشتقة محسوبة صحيحة من OHLC (عقد
§8.1 — القيم السالبة/الخارجة عن [0,1] ترفضها pydantic فصحة الحساب جزء من
الاختبار نفسه)، وحالة تقلب مصنوعة يدويًا بما يقرؤه محرك السيولة منها حصرًا
(‏ATR + معاملات العتبات)، ومتطرف مؤكد يصل كقيمة §11.1 (المحرك لا يتحقق من
المتطرف — التوصيل structure→liquidity مسؤولية المستدعي)، ونطاق أسماء معرفات
المناطق الموثق في :mod:`liquidity.zones` (uuid5 بنطاق ثابت — روح D-07).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from market_state.volatility import VolatilityState
from schemas import (
    Candle,
    DataQuality,
    Swing,
    SwingDirection,
    SwingScope,
)

#: الاثنين 2026-01-05 — أول شموع أسبوع ISO 2026-W02 (الانقلابات تُختبر بأزمنة صريحة).
BASE = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
SESSION_ID = "2026-01-05"

#: نطاق أسماء معرفات المناطق — نفس الثابت الموثق في liquidity.zones.
ZONE_NAMESPACE = uuid5(NAMESPACE_URL, "engine.liquidity.zone.v1")


def zone_uuid(key: str) -> str:
    """معرف منطقة حسب الصيغة الموثقة — ``uuid5(ZONE_NAMESPACE, key)``."""
    return str(uuid5(ZONE_NAMESPACE, key))


def minutes(index: int) -> datetime:
    """زمن شمعة بالدليل — ``BASE + index`` دقائق (ترتيب صاعد صارم بالبناء)."""
    return BASE + timedelta(minutes=index)


def candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    bar_time: datetime | None = None,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    volume: float = 10.0,
) -> Candle:
    """شمعة مغلقة بقيم مشتقة صحيحة من OHLC (§8.1) — مدى منحل يُقبل بحدوده."""
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else minutes(index),
        session_id=SESSION_ID,
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span if span > 0.0 else 0.0,
        close_location_value=(close - low) / span if span > 0.0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def vol(atr: float | None, *, bar_time: datetime | None = None) -> VolatilityState:
    """حالة تقلب مصنوعة يدويًا — ما يقرؤه محرك السيولة منها هو ATR والعتبات حصرًا."""
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=0.001,
        range_expansion_percentile=0.5,
        vol_of_vol=0.1,
        gap_shock=0.0,
        spread_to_range=0.5,
        expected_holding_vol_1h=0.001,
        bar_time=bar_time,
    )


def swing(
    swing_id: str,
    price: float,
    direction: SwingDirection,
    *,
    bar_time: datetime,
    scope: SwingScope = SwingScope.INTERNAL,
    strength: float = 0.8,
    timeframe: str = TIMEFRAME,
    confirm_delay: timedelta = timedelta(minutes=3),
) -> Swing:
    """متطرف مؤكد كقيمة (§11.1) — ``confirmation_time = bar_time + التأخير``."""
    return Swing(
        swing_id=swing_id,
        price=price,
        timeframe=timeframe,
        direction=direction,
        strength=strength,
        confirmation_time=bar_time + confirm_delay,
        external_or_internal=scope,
        bar_time=bar_time,
    )
