"""مخزن مناطق السيولة — كتابة/قراءة جدول liquidity_zones (§31.3، المهمة 3-f).

«Stores every detected liquidity zone and lifecycle state» حرفيًا: كل منطقة
§10.2 بحالتها التتبعية الكاملة — الكتابة upsert على ``zone_id`` الحتمي
(uuid5 خالٍ من الأسعار — عقد zones) فدورة حياة المنطقة المتقدمة تُحدّث
صفها الواحد ولا تتكرر أبدًا (المنطقة كائن متغير الحالة لا حدث متعدد).

نفس روح ``market_state.store``: asyncpg على اتصال المستدعي، الأعمدة
المسطحة للفهرسة والاستعلام و``payload`` JSONB بالترميز القانوني
``model_dump_json()`` مصدر الحقيقة الكامل.

القراءة تُعيد بناء ``schemas.LiquidityZone`` عبر pydantic — لا dict خام.
"""

from __future__ import annotations

import json
import uuid as uuid_module

import asyncpg
from schemas import LiquidityZone

__all__ = [
    "LiquidityZoneStore",
    "LiquidityZoneStoreError",
]

#: مساحة اسم معرف الأداة — نفس ترميز ingestion/market_state/structure.
_INSTRUMENT_NAMESPACE = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
)


class LiquidityZoneStoreError(RuntimeError):
    """خلل في كتابة/قراءة مناطق السيولة — خطأ تشغيلي صريح."""


def _instrument_uuid(instrument: str) -> uuid_module.UUID:
    """معرف أداة حتمي من المفتاح المركب — اصطلاح 1.6 نفسه."""
    if not instrument:
        raise LiquidityZoneStoreError("مفتاح أداة فارغ — المتوقع «venue:symbol»")
    return uuid_module.uuid5(_INSTRUMENT_NAMESPACE, instrument)


class LiquidityZoneStore:
    """كتابة/قراءة مناطق السيولة ودورة حياتها — على اتصال المستدعي."""

    async def upsert_zone(self, conn: asyncpg.Connection, zone: LiquidityZone) -> None:
        """كتابة لقطة منطقة idempotent على zone_id (DO UPDATE).

        كل تقدم في دورة الحياة (اختبار/تغلغل/اجتياح/استهلاك/بطلان) يعيد
        كتابة الصف الواحد بحالته الجارية — «lifecycle state» §31.3 صفٌّ
        متغير لا سجل تراكمي.
        """
        await conn.execute(
            """
            INSERT INTO liquidity_zones (
                zone_id, instrument_id, timeframe, side, price_low, price_high,
                origin_time, source_type, state, sweep_status, test_count,
                importance_score, payload
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
            ON CONFLICT (zone_id) DO UPDATE SET
                side = EXCLUDED.side,
                price_low = EXCLUDED.price_low,
                price_high = EXCLUDED.price_high,
                source_type = EXCLUDED.source_type,
                state = EXCLUDED.state,
                sweep_status = EXCLUDED.sweep_status,
                test_count = EXCLUDED.test_count,
                importance_score = EXCLUDED.importance_score,
                payload = EXCLUDED.payload
            """,
            uuid_module.UUID(zone.zone_id),
            _instrument_uuid(zone.instrument),
            zone.timeframe,
            zone.side.value,
            float(zone.price_low),
            float(zone.price_high),
            zone.origin_time,
            zone.source_type.value,
            zone.state.value,
            zone.sweep_status.value,
            int(zone.test_count),
            float(zone.importance_score),
            zone.model_dump_json(),
        )

    async def upsert_zones(self, conn: asyncpg.Connection, zones: list[LiquidityZone]) -> None:
        """كتابة دفعة لقطات (ترتيب حتمي بترتيب الإدخال) — معاملة المستدعي."""
        for zone in zones:
            await self.upsert_zone(conn, zone)

    async def read_zone(self, conn: asyncpg.Connection, zone_id: str) -> LiquidityZone | None:
        """قراءة منطقة بمعرفها — إعادة بناء عبر pydantic من الحمولة."""
        row = await conn.fetchrow(
            "SELECT payload FROM liquidity_zones WHERE zone_id = $1",
            uuid_module.UUID(zone_id),
        )
        if row is None:
            return None
        payload = row["payload"]
        if isinstance(payload, (str, bytes, bytearray)):
            payload = json.loads(payload)
        return LiquidityZone.model_validate(payload)

    async def read_zones(
        self,
        conn: asyncpg.Connection,
        instrument: str,
        timeframe: str,
        *,
        state: str | None = None,
    ) -> list[LiquidityZone]:
        """كل مناطق أداة/إطار (مرشحة اختياريًا بحالة) بترتيب الإنشاء."""
        if state is None:
            rows = await conn.fetch(
                """
                SELECT payload FROM liquidity_zones
                WHERE instrument_id = $1 AND timeframe = $2
                ORDER BY origin_time, zone_id
                """,
                _instrument_uuid(instrument),
                timeframe,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT payload FROM liquidity_zones
                WHERE instrument_id = $1 AND timeframe = $2 AND state = $3
                ORDER BY origin_time, zone_id
                """,
                _instrument_uuid(instrument),
                timeframe,
                state,
            )
        zones: list[LiquidityZone] = []
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, (str, bytes, bytearray)):
                payload = json.loads(payload)
            zones.append(LiquidityZone.model_validate(payload))
        return zones

    async def count_zones(
        self,
        conn: asyncpg.Connection,
        instrument: str | None = None,
        *,
        state: str | None = None,
    ) -> int:
        """عدد المناطق (لكل الأدوات أو لأداة، مرشحة اختياريًا بحالة)."""
        if instrument is None:
            if state is None:
                count = await conn.fetchval("SELECT count(*) FROM liquidity_zones")
            else:
                count = await conn.fetchval(
                    "SELECT count(*) FROM liquidity_zones WHERE state = $1", state
                )
        elif state is None:
            count = await conn.fetchval(
                "SELECT count(*) FROM liquidity_zones WHERE instrument_id = $1",
                _instrument_uuid(instrument),
            )
        else:
            count = await conn.fetchval(
                "SELECT count(*) FROM liquidity_zones WHERE instrument_id = $1 AND state = $2",
                _instrument_uuid(instrument),
                state,
            )
        return int(count or 0)
