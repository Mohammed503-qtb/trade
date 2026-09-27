"""اختبارات المخزن السوقي الحية (المهمة 1.6) — ضد PG الفعلي.

علامة integration: تتطلب بنية حية (postgres على 5543 بعد هجرة 0002).

التغطية:
- كتابة أحداث منقّاة idempotent (الكتابة الثانية لا تضيف صفوفاً).
- upsert شموع: متطورة ثم مقفلة بنفس المفتاح تُحدَّث لا تُستنسخ.
- قراءة الشموع مرتبة زمنياً وتطابق القيم المكتوبة.
- معرف الأداة الحتمي: نفس (venue, symbol) ⇒ نفس UUID دائماً.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ingestion.market_store import MarketStore, event_quality, instrument_uuid
from schemas import Candle, DataQuality, TradeEvent

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
_VENUE = "binance-usdm-futures"
_SYMBOL = "TESTVERIFY"


def _event(seq: int, t_ms: int) -> TradeEvent:
    return TradeEvent(
        event_time_utc=_T0 + timedelta(milliseconds=t_ms),
        receive_time_utc=_T0 + timedelta(milliseconds=t_ms + 5),
        source_timeframe="1t",
        venue=_VENUE,
        symbol=_SYMBOL,
        feed_id="binance-usdm-aggtrades",
        sequence_id=f"tv-{seq}",
        source_latency_ms=5.0,
        price=100.0 + seq,
        quantity=1.0,
        buyer_is_maker=False,
    )


def _candle(bar_time: datetime, *, is_closed: bool, close: float) -> Candle:
    return Candle(
        instrument_id=f"{_VENUE}:{_SYMBOL}",
        timeframe="1m",
        bar_time=bar_time,
        session_id=bar_time.date().isoformat(),
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=100.0,
        high=max(100.0, close),
        low=min(100.0, close),
        close=close,
        volume=3.0,
        range=abs(close - 100.0) if close != 100.0 else 0.0,
        body_size=abs(close - 100.0),
        upper_wick=0.0,
        lower_wick=min(100.0, close) - 100.0 if close < 100.0 else 0.0,
        body_fraction=1.0 if close != 100.0 else 0.0,
        close_location_value=1.0 if close > 100.0 else (0.0 if close < 100.0 else 0.5),
        true_range=abs(close - 100.0),
        realized_volatility=abs(__import__("math").log(close / 100.0)) if close != 100.0 else 0.0,
    )


async def test_events_idempotent_write() -> None:
    events = [_event(i, i * 100) for i in range(1, 6)]
    qualities = [event_quality(()) for _ in events]
    async with MarketStore() as store:
        # تنظيف أثر أي تشغيل سابق لنفس الاختبار (الرمز الخاص بنا)
        pool = await store._pg()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM market_events WHERE symbol = $1", _SYMBOL)
            await conn.execute(
                "DELETE FROM candles WHERE instrument_id = $1", f"{_VENUE}:{_SYMBOL}"
            )

        first = await store.write_events(events, qualities)
        second = await store.write_events(events, qualities)
        total = await store.count_events(_SYMBOL)
        assert first == 5
        assert second == 0
        assert total == 5

        # upsert: متطورة ثم مقفلة بنفس المفتاح — تحديث لا استنساخ
        evolving = _candle(_T0, is_closed=False, close=101.0)
        closed = _candle(_T0, is_closed=True, close=103.0)
        await store.upsert_candles([evolving])
        await store.upsert_candles([closed])
        read_back = await store.read_candles(f"{_VENUE}:{_SYMBOL}", "1m", closed_only=False)
        assert len(read_back) == 1
        assert read_back[0].is_closed is True
        assert float(read_back[0].close) == 103.0
        assert read_back[0].quality is DataQuality.HEALTHY

        # تنظيف ختامي — لا نترك أثراً للرمز التجريبي
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM market_events WHERE symbol = $1", _SYMBOL)
            await conn.execute(
                "DELETE FROM candles WHERE instrument_id = $1", f"{_VENUE}:{_SYMBOL}"
            )


def test_instrument_uuid_deterministic() -> None:
    """نفس الهوية المصدرية ⇒ نفس UUID — عبر الاستدعاءات وبين العمليات."""
    a = instrument_uuid(_VENUE, _SYMBOL)
    b = instrument_uuid(_VENUE, _SYMBOL)
    assert a == b
    assert instrument_uuid(_VENUE, "OTHER") != a
    assert a.version == 5  # uuid5 قوامه SHA-1 — تحديد لا عشوائية
