"""مخزن التدفق — كتابة/قراءة أحداث التدفق وأشرطة وصفوف الفوتبرنت
(§31.2 + §31.3، المهمة 4-e).

نفس روح ``structure.store``/``liquidity.store`` (المخزن المحلي لا يستوردهما
— عقود import-linter تمنع الاستيراد داخل طبقة الكواشف الواحدة؛ التطابق
الهيكلي مقصود والمساحة الاسمية للمعرفات الحتمية نفسها):

- ``orderflow_events`` (§31.3): الأحداث الثمانية الموثقة في 4-a — كتابة
  upsert على ``event_id`` الحتمي (uuid5 من نوع الحدث والأداة والإطار
  ووقت التأكيد — روح D-07: إعادة الإرسال تحت عقيدة at-least-once §32
  تُحدّث ولا تكرر أبدًا).

- ``footprint_bars`` (§31.2): الشريط كائن متغير الحالة — المتطور يُحدَّث
  لا يُستنسخ (عقيدة الشموع نفسها)؛ الكتابة upsert على المفتاح الطبيعي
  (instrument_id, timeframe, bar_time) و``payload`` JSONB بالترميز
  القانوني ``model_dump_json()`` مصدر الحقيقة الكامل.

- ``footprint_rows`` (§31.2): «الاحتفاظ عند الحاجة للبحث أو حدث مكتشف
  حصرًا» — **لا كتابة تلقائية للصفوف مع كل شريط** (لا تخزين غير محدود
  للمحاكاة البصرية §8.2): الكاتب (بوابة المرحلة/المسار الحي) يقرر أي
  الأشرطة تستحق صفوفها؛ الاستبدال لكل شريط ``replace_rows`` حذف-ثم-إدراج
  داخل معاملة المستدعي فإعادة الإرسال idempotent تمامًا.

القراءة تُعيد بناء نماذج schemas عبر pydantic — لا dict خام.
"""

from __future__ import annotations

import json
import uuid as uuid_module
from datetime import datetime

import asyncpg
from schemas import (
    AbsorptionEventPayload,
    EventType,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    FootprintBar,
    ImbalanceClusterEventPayload,
    payload_digest,
)

from .events import EmittedEvent
from .rows import FootprintRow

__all__ = [
    "FLOW_EVENT_TYPES",
    "FootprintStore",
    "OrderflowStoreError",
    "flow_event_id",
    "orderflow_instrument_uuid",
]

#: مساحة اسم معرف الحدث الحتمي — نفس ترميز structure.store (uuid5 فوق
#: NAMESPACE_URL بمفتاح نطاق معلن): معرفات الأحداث متسقة عبر الحزم.
_EVENT_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/analysis-event"
)

#: مساحة اسم معرف الأداة — نفس ترميز ingestion/market_state/structure.
_INSTRUMENT_NAMESPACE = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
)

#: أنواع أحداث التدفق الثمانية الموطنة في orderflow_events (§31.3: «امتصاص،
#: إنهاك، دلتا/اختلال» — الاستمرار دلتا-توافق وال عناقيد اختلال).
FLOW_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.ABSORPTION_BUY,
        EventType.ABSORPTION_SELL,
        EventType.FLOW_CONTINUATION_UP,
        EventType.FLOW_CONTINUATION_DOWN,
        EventType.EXHAUSTION_UP,
        EventType.EXHAUSTION_DOWN,
        EventType.BUY_IMBALANCE_CLUSTER,
        EventType.SELL_IMBALANCE_CLUSTER,
    }
)


class OrderflowStoreError(RuntimeError):
    """خلل في كتابة/قراءة بيانات التدفق — خطأ تشغيلي صريح."""


def orderflow_instrument_uuid(instrument: str) -> uuid_module.UUID:
    """معرف أداة حتمي من المفتاح المركب ``venue:symbol`` — اصطلاح 1.6 نفسه."""
    if not instrument:
        raise OrderflowStoreError("مفتاح أداة فارغ — المتوقع «venue:symbol»")
    return uuid_module.uuid5(_INSTRUMENT_NAMESPACE, instrument)


def flow_event_id(
    event_type: str, instrument: str, timeframe: str, event_time: object, digest: str
) -> uuid_module.UUID:
    """معرف حدث تدفق حتمي — ``uuid5(namespace, type|instrument|timeframe|time|digest)``.

    نفس عقد ``structure.store.deterministic_event_id`` الموسع ببصمة الحمولة
    (المعرّف محلي هنا لأن عقود الطبقات تمنع الاستيراد من حزمة البنية —
    انظر وثائق الموديول؛ البصمة من ``schemas.payload_digest`` — ADR-024).
    """
    key = f"{event_type}|{instrument}|{timeframe}|{event_time.isoformat()}|{digest}"  # type: ignore[attr-defined]
    return uuid_module.uuid5(_EVENT_NAMESPACE, key)


class FootprintStore:
    """كتابة/قراءة أشرطة الفوتبرنت وصفوفها المقيدة — على اتصال المستدعي.

    الأشرطة upsert على المفتاح الطبيعي؛ الصفوف استبدال صريح لكل شريط
    (الاحتفاظ قرار الكاتب — §31.2)؛ الأحداث upsert على ``event_id``.
    """

    async def upsert_bar(self, conn: asyncpg.Connection, bar: FootprintBar) -> None:
        """كتابة شريط فوتبرنت idempotent على المفتاح الطبيعي (DO UPDATE).

        المتطور يُحدَّث في صفه نفسه حتى إقفاله (عقيدة «يُحدَّث لا
        يُستنسخ»)؛ الإرسال المكرر لا يكرر صفًا أبدًا.
        """
        try:
            await conn.execute(
                """
                INSERT INTO footprint_bars (
                    instrument_id, timeframe, bar_time, quality, is_closed,
                    source_feed, methodology,
                    buy_volume, sell_volume, total_volume, delta,
                    poc, vah, val, row_count,
                    buy_imbalance_count, sell_imbalance_count, payload
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11,
                    $12, $13, $14, $15,
                    $16, $17, $18::jsonb
                )
                ON CONFLICT (instrument_id, timeframe, bar_time) DO UPDATE SET
                    quality = EXCLUDED.quality,
                    is_closed = EXCLUDED.is_closed,
                    source_feed = EXCLUDED.source_feed,
                    methodology = EXCLUDED.methodology,
                    buy_volume = EXCLUDED.buy_volume,
                    sell_volume = EXCLUDED.sell_volume,
                    total_volume = EXCLUDED.total_volume,
                    delta = EXCLUDED.delta,
                    poc = EXCLUDED.poc,
                    vah = EXCLUDED.vah,
                    val = EXCLUDED.val,
                    row_count = EXCLUDED.row_count,
                    buy_imbalance_count = EXCLUDED.buy_imbalance_count,
                    sell_imbalance_count = EXCLUDED.sell_imbalance_count,
                    payload = EXCLUDED.payload
                """,
                orderflow_instrument_uuid(bar.instrument_id),
                bar.timeframe,
                bar.bar_time,
                bar.quality.value,
                bar.is_closed,
                bar.source_feed,
                bar.methodology,
                bar.buy_volume,
                bar.sell_volume,
                bar.total_volume,
                bar.delta,
                bar.poc,
                bar.vah,
                bar.val,
                bar.row_count,
                bar.buy_imbalance_count,
                bar.sell_imbalance_count,
                bar.model_dump_json(),
            )
        except Exception as exc:
            raise OrderflowStoreError(f"فشل upsert شريط الفوتبرنت {bar.bar_time}: {exc}") from exc

    async def replace_rows(
        self,
        conn: asyncpg.Connection,
        bar: FootprintBar,
        rows: tuple[FootprintRow, ...],
    ) -> None:
        """استبدال صفوف شريط بعينه idempotent — حذف ثم إدراج (معاملة المستدعي).

        «الاحتفاظ عند الحاجة للبحث أو حدث مكتشف حصرًا» (§31.2): هذه الدالة
        لا تُستدعى آليًا مع كل شريط — الكاتب يقرر أي الأشرطة تستحق صفوفها.
        """
        instrument_uuid = orderflow_instrument_uuid(bar.instrument_id)
        try:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM footprint_rows "
                    "WHERE instrument_id = $1 AND timeframe = $2 AND bar_time = $3",
                    instrument_uuid,
                    bar.timeframe,
                    bar.bar_time,
                )
                if rows:
                    await conn.executemany(
                        """
                        INSERT INTO footprint_rows (
                            instrument_id, timeframe, bar_time, price, buy_volume, sell_volume
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        [
                            (
                                instrument_uuid,
                                bar.timeframe,
                                bar.bar_time,
                                row.price,
                                row.buy_volume,
                                row.sell_volume,
                            )
                            for row in rows
                        ],
                    )
        except Exception as exc:
            raise OrderflowStoreError(
                f"فشل استبدال صفوف الفوتبرنت عند {bar.bar_time}: {exc}"
            ) from exc

    async def upsert_event(self, conn: asyncpg.Connection, event: EmittedEvent) -> None:
        """كتابة حدث تدفق idempotent على ``event_id`` الحتمي (DO UPDATE).

        التحقق من النوع موطن orderflow_events حصرًا — الأنواع غير التدفقية
        خطأ صاخب (لا كتابة صامتة لجدول غير موطن).
        """
        if event.event_type not in FLOW_EVENT_TYPES:
            raise OrderflowStoreError(
                f"نوع حدث ليس من تدفق المرحلة 4: {event.event_type.value!r} — "
                "orderflow_events موطن الأنواع الثمانية التدفقية حصرًا"
            )
        payload = event.payload
        instrument = payload.instrument
        timeframe = payload.timeframe
        event_id = flow_event_id(
            event.event_type.value,
            instrument,
            timeframe,
            event.event_time,
            payload_digest(payload),
        )
        try:
            await conn.execute(
                """
                INSERT INTO orderflow_events (
                    event_id, event_type, instrument_id, timeframe, event_time, payload
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (event_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    payload = EXCLUDED.payload
                """,
                event_id,
                event.event_type.value,
                orderflow_instrument_uuid(instrument),
                timeframe,
                event.event_time,
                payload.model_dump_json(),
            )
        except Exception as exc:
            raise OrderflowStoreError(
                f"فشل upsert حدث التدفق {event.event_type.value}: {exc}"
            ) from exc

    async def read_bars(
        self,
        conn: asyncpg.Connection,
        instrument_id: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[FootprintBar]:
        """قراءة أحدث الأشرطة (الأحدث أولًا) وإعادة بناء النموذج عبر pydantic."""
        try:
            rows = await conn.fetch(
                "SELECT payload FROM footprint_bars "
                "WHERE instrument_id = $1 AND timeframe = $2 "
                "ORDER BY bar_time DESC LIMIT $3",
                orderflow_instrument_uuid(instrument_id),
                timeframe,
                limit,
            )
        except Exception as exc:
            raise OrderflowStoreError(f"فشل قراءة أشرطة الفوتبرنت: {exc}") from exc
        return [FootprintBar.model_validate_json(r["payload"]) for r in rows]

    async def read_events(
        self,
        conn: asyncpg.Connection,
        instrument_id: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[EmittedEvent]:
        """قراءة أحدث أحداث التدفق (الأحدث أولًا) بإعادة بناء الحمولة الموثقة."""
        try:
            rows = await conn.fetch(
                "SELECT event_type, event_time, payload FROM orderflow_events "
                "WHERE instrument_id = $1 AND timeframe = $2 "
                "ORDER BY event_time DESC LIMIT $3",
                orderflow_instrument_uuid(instrument_id),
                timeframe,
                limit,
            )
        except Exception as exc:
            raise OrderflowStoreError(f"فشل قراءة أحداث التدفق: {exc}") from exc
        out: list[EmittedEvent] = []
        for r in rows:
            event_type = EventType(r["event_type"])
            payload_model: type[object]
            if event_type in (EventType.ABSORPTION_BUY, EventType.ABSORPTION_SELL):
                payload_model = AbsorptionEventPayload
            elif event_type in (
                EventType.FLOW_CONTINUATION_UP,
                EventType.FLOW_CONTINUATION_DOWN,
            ):
                payload_model = FlowContinuationEventPayload
            elif event_type in (EventType.EXHAUSTION_UP, EventType.EXHAUSTION_DOWN):
                payload_model = ExhaustionEventPayload
            else:
                payload_model = ImbalanceClusterEventPayload
            payload_json = r["payload"]
            # JSONB يعود str من asyncpg — فك الترميز القانوني ثم البناء
            data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
            payload = payload_model.model_validate(data)
            out.append(
                EmittedEvent(
                    event_type=event_type,
                    event_time=r["event_time"],
                    payload=payload,
                )
            )
        return out

    async def read_rows(
        self,
        conn: asyncpg.Connection,
        instrument_id: str,
        timeframe: str,
        bar_time: datetime,
    ) -> list[FootprintRow]:
        """قراءة صفوف شريط بعينه (المرتبة تصاعديًا بالسعر — عقد rows.py)."""
        try:
            rows = await conn.fetch(
                "SELECT price, buy_volume, sell_volume FROM footprint_rows "
                "WHERE instrument_id = $1 AND timeframe = $2 AND bar_time = $3 "
                "ORDER BY price ASC",
                orderflow_instrument_uuid(instrument_id),
                timeframe,
                bar_time,
            )
        except Exception as exc:
            raise OrderflowStoreError(f"فشل قراءة صفوف الفوتبرنت: {exc}") from exc
        return [
            FootprintRow(price=r["price"], buy_volume=r["buy_volume"], sell_volume=r["sell_volume"])
            for r in rows
        ]
