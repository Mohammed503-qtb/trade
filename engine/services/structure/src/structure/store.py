"""مخزن أحداث البنية والأنماط — كتابة/قراءة structure_events وpattern_events
(§31.3، المهمة 3-f).

نفس روح ``market_state.store`` (2-f): asyncpg مباشر على اتصال المستدعي،
كتابة idempotent عبر ON CONFLICT على المفتاح الحتمي، والحمولة بالترميز
القانوني ``model_dump_json()``/``model_dump()`` — نفس بايتات البث عبر
NATS (مصدر حقيقة موحد للمسارين §32).

القرارات الموثقة:

- **الجدولان من هيكل 0004**: ``structure_events`` يحمل أحداث §20 البنيوية
  (INTERNAL_BOS/EXTERNAL_BOS/CHOCH/DISPLACEMENT_*) **وسجل المتطرفات §11.1**
  («BOS/CHoCH/swing/displacement» حرفيًا في §31.3) بنوع معرف موثق
  ``SWING_CONFIRMED`` — لا بث NATS له (قاموس §20 لا يعرف متطرفًا) لكن
  التخزين قانوني بصريح القائمة. ``pattern_events`` يحمل FVG/OB/premium-
  discount من كواشف §11 (قرار ADR-021: الجدول موطن أنماط طور المرحلة 3
  والمرحلة 5ا توسعه على الجدول نفسه).

- **event_id حتمي (روح D-07)**: ``uuid5(namespace, f"{event_type}|{instrument}
  |{timeframe}|{event_time.isoformat()}")`` — نفس الحدث من الإعادة الحتمية
  يحمل المعرف نفسه فإعادة الإرسال (at-least-once §32) تحدّث ولا تكرر؛
  وتصادم حدثين مختلفين بنفس الطابع مستحيل لأن الكاشف الواحد لا يبث النوع
  نفسه مرتين في الشمعة الواحدة (عقود الكواشف).

- **الأداة صريحة دائمًا**: ``schemas.Swing`` (§11.1) لا يحمل أداة (حرفية
  الخطة) — ``upsert_swing`` يستقبل الأداة صراحة من المستدعي الذي يملك
  هوية المسار؛ لا عالميات خفية ولا اشتقاق تخميني من المعرفات.

- **قراءة الأحداث**: ``recent_events`` يبني المغلفات من الصفوف — الحمولة
  تتحقق عبر pydantic بنموذجها الموثق من ``payload_model_for`` (الأسس 3-a)
  فلا dict خام يعبر الحدود.
"""

from __future__ import annotations

import json
import uuid as uuid_module

import asyncpg
from schemas import (
    SCHEMA_VERSION,
    EventEnvelope,
    EventType,
    Swing,
    payload_digest,
    payload_model_for,
)

__all__ = [
    "PATTERN_EVENT_TYPES",
    "STRUCTURE_EVENT_TYPES",
    "SWING_CONFIRMED_EVENT_TYPE",
    "AnalysisEventStore",
    "AnalysisEventStoreError",
    "analysis_instrument_uuid",
    "deterministic_event_id",
]

#: نوع سجل المتطرفات الموثق — ليس نوع §20 (لا بث له) لكن §31.3 يذكر
#: «swing» صراحة ضمن structure_events فيُخزن بهذا الاسم المعرف.
SWING_CONFIRMED_EVENT_TYPE = "SWING_CONFIRMED"

#: أنواع §20 الموطنة في structure_events (كسور وإزاحات §11.2-4).
STRUCTURE_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.INTERNAL_BOS,
        EventType.EXTERNAL_BOS,
        EventType.CHOCH,
        EventType.DISPLACEMENT_UP,
        EventType.DISPLACEMENT_DOWN,
    }
)

#: أنواع §20 الموطنة في pattern_events — طور المرحلة 3 (§11.5-7) وطور
#: المرحلة 5a (§13: أربعة شموعية واثنان كلاسيكيان — توسعة مشروعة موثقة).
PATTERN_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.FVG_BULLISH,
        EventType.FVG_BEARISH,
        EventType.ORDER_BLOCK_BULLISH,
        EventType.ORDER_BLOCK_BEARISH,
        EventType.PREMIUM_LOCATION,
        EventType.DISCOUNT_LOCATION,
        EventType.BULLISH_ENGULFING,
        EventType.BEARISH_ENGULFING,
        EventType.REJECTION_CANDLE,
        EventType.INSIDE_BAR_BREAK,
        EventType.CLASSICAL_BREAKOUT,
        EventType.CLASSICAL_FAILED_BREAKOUT,
    }
)

#: الجداول الثلاثة القانونية للقراءة/العد — قائمة بيضاء لا مدخل خارجي.
_KNOWN_TABLES: frozenset[str] = frozenset({"structure_events", "pattern_events", "liquidity_zones"})

#: مساحة اسم معرف الحدث الحتمي — uuid5 فوق NAMESPACE_URL بمفتاح نطاق
#: معلن (نمط _ZONE_NAMESPACE/_FVG_NAMESPACE نفسه): تحديد لا عشوائية.
_EVENT_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/analysis-event"
)

#: مساحة اسم معرف الأداة — نفس ترميز ingestion/market_state الحتمي.
_INSTRUMENT_NAMESPACE = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
)


class AnalysisEventStoreError(RuntimeError):
    """خلل في كتابة/قراءة أحداث التحليل — خطأ تشغيلي صريح."""


def analysis_instrument_uuid(instrument: str) -> uuid_module.UUID:
    """معرف أداة حتمي من المفتاح المركب ``venue:symbol`` — اصطلاح 1.6 نفسه."""
    if not instrument:
        raise AnalysisEventStoreError("مفتاح أداة فارغ — المتوقع «venue:symbol»")
    return uuid_module.uuid5(_INSTRUMENT_NAMESPACE, instrument)


def deterministic_event_id(
    event_type: str, instrument: str, timeframe: str, event_time: object, digest: str
) -> uuid_module.UUID:
    """معرف حدث حتمي — ``uuid5(namespace, type|instrument|timeframe|time|digest)``.

    الحتمية تجعل إعادة الإرسال نفسها تحدّث صفها (idempotent) وتسمح
    للمستهلكين اشتقاق المعرف نفسه من الحدث المكافئ (روح D-07). المكوّن
    الخامس بصمة الحمولة القانونية (``schemas.payload_digest``): الأحداث
    المتعددة المناطق عند الشمعة نفسها متميزة بحمولاتها — مكتشف بوابة
    المرحلة 6 (ADR-024)؛ الرباعي السابق كان يصدمها تصادم كتابة صامتة.
    """
    key = f"{event_type}|{instrument}|{timeframe}|{event_time.isoformat()}|{digest}"  # type: ignore[attr-defined]
    return uuid_module.uuid5(_EVENT_NAMESPACE, key)


def _table_for(event_type: EventType) -> str:
    """جدول §31.3 الموطن للنوع — بنيوي أو نمطي (رفض صاخب لغيرهما)."""
    if event_type in STRUCTURE_EVENT_TYPES:
        return "structure_events"
    if event_type in PATTERN_EVENT_TYPES:
        return "pattern_events"
    raise AnalysisEventStoreError(
        f"نوع حدث بلا موطن تخزين في طور المرحلة 3: {event_type.value!r} — "
        "جداول §31.3 الحالية تغطي البنيوي والنمطي حصرًا"
    )


def _check_table(table: str) -> str:
    """تحقق الجدول ضد القائمة البيضاء — لا تركيب مداخل خارجية."""
    if table not in _KNOWN_TABLES:
        raise AnalysisEventStoreError(
            f"جدول غير معروف: {table!r} — المسموح: {sorted(_KNOWN_TABLES)}"
        )
    return table


class AnalysisEventStore:
    """كتابة/قراءة أحداث البنية والأنماط — عمليات صغيرة على اتصال المستدعي."""

    async def upsert_event(self, conn: asyncpg.Connection, envelope: EventEnvelope) -> None:
        """كتابة حدث idempotent على event_id الحتمي (DO UPDATE).

        الجدول من نوع الحدث (بنية/نمط §31.3)؛ الحمولة تمر عبر نموذجها
        الموثق (``payload_model_for``) ثم ``model_dump_json()`` — ترميز
        قانوني مفاتيحه مرتبة يحوم التواريخ ISO (وتحقق pydantic صاخب عند
        الكتابة: الحدث المخالف لا يخزن أصلًا).
        """
        table = _table_for(envelope.event_type)
        instrument = str(envelope.payload["instrument"])
        timeframe = str(envelope.payload["timeframe"])
        model = payload_model_for(envelope.event_type)
        if model is None:  # pragma: no cover — الأنواع المخزنة موثقة الحمولات
            raise AnalysisEventStoreError(
                f"نوع بلا نموذج حمولة: {envelope.event_type.value} — لا تخزين بلا مخطط"
            )
        payload_json = model.model_validate(envelope.payload).model_dump_json()
        await conn.execute(
            f"""
            INSERT INTO {table} (
                event_id, event_type, instrument_id, timeframe, event_time, payload
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (event_id) DO UPDATE SET
                payload = EXCLUDED.payload
            """,  # noqa: S608 — القائمة البيضاء أعلاه تضمن الاسم
            uuid_module.UUID(str(envelope.event_id)),
            envelope.event_type.value,
            analysis_instrument_uuid(instrument),
            timeframe,
            envelope.event_time,
            payload_json,
        )

    async def upsert_swing(self, conn: asyncpg.Connection, swing: Swing, instrument: str) -> None:
        """كتابة متطرف مؤكد في structure_events («swing» §31.3).

        النوع الموثق SWING_CONFIRMED والحمولة نموذج Swing الكامل بالترميز
        القانوني؛ المعرف الحتمي من (النوع، الأداة، الإطار، طابع التأكيد) —
        إعادة تسليم المتطرف نفسه تحدّث ولا تكرر.
        """
        # المفتاح يشمل معرف المتطرف: القطبان قد يؤكدان بشمعة واحدة فلطابع
        # التأكيد وحده لا يفصل بينهما (تصادم كان يُسقط أحدهما في upsert)
        event_id = deterministic_event_id(
            f"{SWING_CONFIRMED_EVENT_TYPE}|{swing.swing_id}",
            instrument,
            swing.timeframe,
            swing.confirmation_time,
            payload_digest(swing),
        )
        await conn.execute(
            """
            INSERT INTO structure_events (
                event_id, event_type, instrument_id, timeframe, event_time, payload
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (event_id) DO UPDATE SET
                payload = EXCLUDED.payload
            """,
            event_id,
            SWING_CONFIRMED_EVENT_TYPE,
            analysis_instrument_uuid(instrument),
            swing.timeframe,
            swing.confirmation_time,
            swing.model_dump_json(),
        )

    async def recent_events(
        self,
        conn: asyncpg.Connection,
        instrument: str,
        timeframe: str,
        *,
        limit: int = 50,
        table: str = "structure_events",
    ) -> list[EventEnvelope]:
        """أحدث الأحداث لأداة/إطار — مغلفات كاملة محققة عبر pydantic.

        سجلات SWING_CONFIRMED مستثناة (ليست مغلفات §20 — تُقرأ بمسار
        ``recent_swings``)؛ الترتيب زمني تصاعدي (الأقدم أولًا) لسلسلة
        استهلاك الدمج (المرحلة 6).
        """
        _check_table(table)
        if table == "liquidity_zones":
            raise AnalysisEventStoreError("liquidity_zones ليس جدول أحداث — استخدم مخزن السيولة")
        rows = await conn.fetch(
            f"""
            SELECT event_id, event_type, event_time, payload
            FROM {table}
            WHERE instrument_id = $1 AND timeframe = $2 AND event_type <> $3
            ORDER BY event_time DESC
            LIMIT $4
            """,  # noqa: S608 — القائمة البيضاء أعلاه تضمن الاسم
            analysis_instrument_uuid(instrument),
            timeframe,
            SWING_CONFIRMED_EVENT_TYPE,
            limit,
        )
        envelopes: list[EventEnvelope] = []
        for row in reversed(rows):
            event_type = EventType(row["event_type"])
            payload_dict = row["payload"]
            if isinstance(payload_dict, (str, bytes, bytearray)):
                payload_dict = json.loads(payload_dict)
            model = payload_model_for(event_type)
            if model is None:  # pragma: no cover — الأنواع المخزنة موثقة الحمولات
                raise AnalysisEventStoreError(f"نوع بلا نموذج حمولة: {event_type.value}")
            envelopes.append(
                EventEnvelope(
                    event_id=uuid_module.UUID(str(row["event_id"])),
                    schema_version=SCHEMA_VERSION,
                    event_type=event_type,
                    event_time=row["event_time"],
                    receive_time=row["event_time"],
                    source=f"store.{table}",
                    trace_id="",
                    correlation_id=None,
                    payload=model.model_validate(payload_dict).model_dump(),
                )
            )
        return envelopes

    async def recent_swings(
        self,
        conn: asyncpg.Connection,
        instrument: str,
        timeframe: str,
        *,
        limit: int = 100,
    ) -> list[Swing]:
        """أحدث المتطرفات المؤكدة (سجل §11.1 في structure_events) تصاعديًا."""
        rows = await conn.fetch(
            """
            SELECT payload FROM structure_events
            WHERE instrument_id = $1 AND timeframe = $2 AND event_type = $3
            ORDER BY event_time DESC
            LIMIT $4
            """,
            analysis_instrument_uuid(instrument),
            timeframe,
            SWING_CONFIRMED_EVENT_TYPE,
            limit,
        )
        swings: list[Swing] = []
        for row in reversed(rows):
            payload = row["payload"]
            if isinstance(payload, (str, bytes, bytearray)):
                payload = json.loads(payload)
            swings.append(Swing.model_validate(payload))
        return swings

    async def count_events(
        self,
        conn: asyncpg.Connection,
        instrument: str | None = None,
        *,
        table: str = "structure_events",
    ) -> int:
        """عدد الأحداث (لكل الأدوات أو لأداة) — للاختبارات والرصد."""
        _check_table(table)
        if table == "liquidity_zones":
            raise AnalysisEventStoreError("liquidity_zones ليس جدول أحداث — استخدم مخزن السيولة")
        if instrument is None:
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")  # noqa: S608
        else:
            count = await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE instrument_id = $1",  # noqa: S608
                analysis_instrument_uuid(instrument),
            )
        return int(count or 0)
