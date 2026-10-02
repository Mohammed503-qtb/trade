"""أدوات اختبارات الإعادة — شموع ومواصفات دخول حتمية قابلة لإعادة الاستخدام.

نمط ``_risk_fixtures`` نفسه: بناة صرفون بلا حالة، وكل القيم موثقة المصدر
(أسعار رمزية بمقياس واضح — الحقائق تُختبر بالعلاقات لا بالأرقام الكونية).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from schemas import Candle, DataQuality, Direction, EntrySpec

__all__ = [
    "ATR_TEST",
    "LONG_SPEC_DEFAULTS",
    "SHORT_SPEC_DEFAULTS",
    "T0",
    "candle_at",
    "entry_spec",
]

#: لحظة الصفر لكل الاختبارات — UTC ثابتة.
T0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

#: وحدة R الاختبارية (مسافة الوقف) — 1.0 ليس كل شيء.
ATR_TEST = 1.0


def candle_at(
    minute: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    *,
    timeframe: str = "1m",
    quality: DataQuality = DataQuality.HEALTHY,
) -> Candle:
    """شمعة دقيقة عند ``T0 + minute`` بقيم معلنة (مشتقات متسقة)."""
    rng = h - lo
    if rng < 0:
        raise ValueError(f"شمعة معكوسة: high={h} < low={lo}")
    return Candle(
        instrument_id="BTCUSDT",
        timeframe=timeframe,
        bar_time=T0 + timedelta(minutes=minute),
        session_id="sess-test",
        quality=quality,
        is_closed=True,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=100.0,
        range=rng,
        body_size=abs(c - o),
        upper_wick=h - max(o, c),
        lower_wick=min(o, c) - lo,
        body_fraction=(abs(c - o) / rng) if rng > 0 else 0.0,
        close_location_value=((c - lo) / rng) if rng > 0 else 0.5,
        true_range=rng,
        realized_volatility=(rng / c) if c > 0 else 0.0,
    )


#: قيم مواصفة الشراء الافتراضية — منطقة [100.0, 100.5] ووقف 99.5 وهدف 102.
LONG_SPEC_DEFAULTS: dict[str, float | str] = {
    "trade_intent_id": "ti-long-1",
    "scenario_id": "sc-long-1",
    "decision_id": "dc-long-1",
    "symbol": "BTCUSDT",
    "entry_price": 100.5,
    "zone_opposite_price": 100.0,
    "stop_price": 99.5,
    "target_price": 102.0,
}

#: مواصفة البيع — منطقة [99.5, 100.0] ووقف 100.5 وهدف 98.
SHORT_SPEC_DEFAULTS: dict[str, float | str] = {
    "trade_intent_id": "ti-short-1",
    "scenario_id": "sc-short-1",
    "decision_id": "dc-short-1",
    "symbol": "BTCUSDT",
    "entry_price": 99.5,
    "zone_opposite_price": 100.0,
    "stop_price": 100.5,
    "target_price": 98.0,
}


def entry_spec(
    *,
    side: Direction = Direction.LONG,
    decision_minute: int = 0,
    horizon_minutes: int = 240,
    planned_quantity: float = 10.0,
    regime: str = "TREND",
    **overrides: object,
) -> EntrySpec:
    """مواصفة دخول معلنة — الشراء أو البيع بقيم افتراضية متسقة هندسيًا."""
    base = dict(LONG_SPEC_DEFAULTS if side is Direction.LONG else SHORT_SPEC_DEFAULTS)
    base.update(overrides)  # type: ignore[arg-type]
    return EntrySpec(
        side=side,
        decision_time=T0 + timedelta(minutes=decision_minute),
        expiry=T0 + timedelta(minutes=decision_minute + horizon_minutes),
        planned_quantity=planned_quantity,
        regime=regime,
        **base,  # type: ignore[arg-type]
    )
