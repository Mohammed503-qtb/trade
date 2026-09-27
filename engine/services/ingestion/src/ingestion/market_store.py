"""المخزن السوقي — كتابة الأحداث المنقّاة والشموع إلى PG (المهمة 1.6).

جدولان من هجرة 0002 (§31.2):
- ``market_events``: الأحداث الخام المطبّعة المحتجزة — كتابة idempotent عبر
  الفهرس الفريد الجزئي (symbol, sequence_id): إعادة الإعادة لا تكرر الصفوف.
- ``candles``: الشموع القانونية — upsert على المفتاح (instrument_id,
  timeframe, bar_time): المتطورة تُحدَّث حتى قفلها، والمقفلة تثبت قيمها
  (إعادة كتابتها بنفس القيم لا تغير شيئاً — الحتمية محفوظة).

قرارات موثقة:
- ``event_id`` يولد UUID4 وقت الكتابة (هوية صف قاعدة بيانات لا هوية حدث
  مصدري — هوية المصدر هي (symbol, sequence_id) وهي أساس idempotency).
- كتابة الشمعة المقفلة فوق متطورة بنفس المفتاح تُحدَّث قيمها — هذا هو
  الانتقال الطبيعي متطور→مقفول في §27، لا كسر له.
- كل الدفعات تستخدم executemany على اتصال من RawStore نفسه؟ لا — مستقل:
  هذه الوحدة تفتح مجمّعها الخاص (صغر النطاق: عملية واحدة لكل استدعاء).
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Sequence

import asyncpg
from common.config import Settings, load_settings
from schemas import Candle, DataQuality, TradeEvent

# هوية أداة حتمية من (venue, symbol) — uuid5 برمز نطاق ثابت:
# نفس الأداة ⇒ نفس المعرف دائماً (عبر الجلسات والإعادات) إلى حين حلقة
# seed المرجعية (جدول instruments) التي تستبدلها بهوية موزونة موثقة.
# قرار موثق: uuid5(namespace, "venue:symbol") — تحديد لا عشوائية، لأن
# market_events.instrument_id عمود Uuid إلزامي في هجرة 0002.
_INSTRUMENT_NAMESPACE = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
)


def instrument_uuid(venue: str, symbol: str) -> uuid_module.UUID:
    """معرف أداة حتمي من هويتها المصدريّة — ثابت عبر كل الجلسات."""
    return uuid_module.uuid5(_INSTRUMENT_NAMESPACE, f"{venue}:{symbol}")


class MarketStoreError(RuntimeError):
    """خلل في كتابة/قراءة المخزن السوقي — خطأ تشغيلي صريح."""


def event_quality(signals: Sequence[DataQuality]) -> DataQuality:
    """جودة الحدث من إشارات خط التنقيح — أسوأ إشارة، لا إشارات = HEALTHY.

    قرار موثق: جودة الحدث المخزن مستمدة من إشاراته الخاصة (حدثية بحتة)
    لا من حالات المصنف الكسولة المعتمدة على الساعة (STALE/UNAVAILABLE) —
    تلك حالات شريحة لحظية تخص المسار الحي، وأرشفة الحدث بها تشوه الحتمية.
    """
    if not signals:
        return DataQuality.HEALTHY
    from .quality import worst_quality

    return worst_quality(*signals)


class MarketStore:
    """كتابة/قراءة الأحداث المنقّاة والشموع — عمليات صغيرة مستقلة."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or load_settings()
        self._pool: asyncpg.Pool | None = None

    async def _pg(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._settings.database_url, min_size=1, max_size=4
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> MarketStore:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def write_events(
        self, events: Sequence[TradeEvent], qualities: Sequence[DataQuality]
    ) -> int:
        """كتابة أحداث منقّاة — يعيد عدد الصفوف المدرجة حديثاً (idempotent).

        الصفوف المكررة (نفس symbol+sequence_id موجود مسبقاً) تُتخطى بقاعدة
        البيانات نفسها؛ العدّ عبر فرق الجدول قبل/بعد — سياق كاتب واحد
        موثق (خط الأنابيب/الإعادة)، لا كتابة متزامنة على الجدول نفسه.
        """
        if len(events) != len(qualities):
            raise MarketStoreError(
                f"أطوال غير متطابقة: {len(events)} حدث مقابل {len(qualities)} جودة"
            )
        if not events:
            return 0
        symbol = events[0].symbol
        before = await self.count_events(symbol)
        rows = [
            (
                uuid_module.uuid4(),
                instrument_uuid(e.venue, e.symbol),
                e.venue,
                e.symbol,
                e.event_time_utc,
                e.receive_time_utc,
                e.sequence_id,
                float(e.price),
                float(e.quantity),
                e.buyer_is_maker,
                q.value,
                e.source_timeframe,
                e.feed_id,
                e.source_latency_ms,
            )
            for e, q in zip(events, qualities, strict=True)
        ]
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO market_events (
                    event_id, instrument_id, venue, symbol, event_time,
                    receive_time, sequence_id, price, quantity, buyer_is_maker,
                    quality, source_timeframe, feed_id, source_latency_ms
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14
                )
                ON CONFLICT (symbol, sequence_id) WHERE sequence_id IS NOT NULL
                DO NOTHING
                """,
                rows,
            )
        after = await self.count_events(symbol)
        return after - before

    async def count_events(self, symbol: str) -> int:
        pool = await self._pg()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM market_events WHERE symbol = $1", symbol
            )
            return int(count or 0)

    async def upsert_candles(self, candles: Sequence[Candle]) -> None:
        """upsert شموع على (instrument_id, timeframe, bar_time).

        المتطورة تُحدَّث عند كل إصدار حتى قفلها؛ المقفلة تكتب قيمها النهائية.
        """
        if not candles:
            return
        rows = [
            (
                c.instrument_id,
                c.timeframe,
                c.bar_time,
                c.session_id,
                c.quality.value,
                c.is_closed,
                float(c.open),
                float(c.high),
                float(c.low),
                float(c.close),
                float(c.volume),
                float(c.range),
                float(c.body_size),
                float(c.upper_wick),
                float(c.lower_wick),
                float(c.body_fraction),
                float(c.close_location_value),
                float(c.true_range),
                float(c.realized_volatility),
            )
            for c in candles
        ]
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO candles (
                    instrument_id, timeframe, bar_time, session_id, quality,
                    is_closed, open, high, low, close, volume,
                    range_, body_size, upper_wick, lower_wick,
                    body_fraction, close_location_value, true_range,
                    realized_volatility
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                    $12,$13,$14,$15,$16,$17,$18,$19
                )
                ON CONFLICT (instrument_id, timeframe, bar_time) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    quality = EXCLUDED.quality,
                    is_closed = EXCLUDED.is_closed,
                    open = EXCLUDED.open, high = EXCLUDED.high,
                    low = EXCLUDED.low, close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    range_ = EXCLUDED.range_,
                    body_size = EXCLUDED.body_size,
                    upper_wick = EXCLUDED.upper_wick,
                    lower_wick = EXCLUDED.lower_wick,
                    body_fraction = EXCLUDED.body_fraction,
                    close_location_value = EXCLUDED.close_location_value,
                    true_range = EXCLUDED.true_range,
                    realized_volatility = EXCLUDED.realized_volatility
                """,
                rows,
            )

    async def read_candles(
        self, instrument_id: str, timeframe: str, *, closed_only: bool = True
    ) -> list[Candle]:
        """قراءة الشموع مرتبة زمنياً — مرجع المقارنة الحتمي للإعادة."""
        pool = await self._pg()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM candles
                WHERE instrument_id = $1 AND timeframe = $2
                  AND ($3::bool OR is_closed)
                ORDER BY bar_time
                """,
                instrument_id,
                timeframe,
                not closed_only,
            )
        return [
            Candle(
                instrument_id=r["instrument_id"],
                timeframe=r["timeframe"],
                bar_time=r["bar_time"],
                session_id=r["session_id"],
                quality=DataQuality(r["quality"]),
                is_closed=r["is_closed"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                range=r["range_"],
                body_size=r["body_size"],
                upper_wick=r["upper_wick"],
                lower_wick=r["lower_wick"],
                body_fraction=float(r["body_fraction"]),
                close_location_value=float(r["close_location_value"]),
                true_range=r["true_range"],
                realized_volatility=r["realized_volatility"],
            )
            for r in rows
        ]
