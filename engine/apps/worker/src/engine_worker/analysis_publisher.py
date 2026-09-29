"""ناشر أحداث التحليل عبر NATS — تجميع مغلفات §32 (3-f، توسعة 4-e للتدفق).

مسؤوليتان منفصلتان بعقد صارم:

- **مصنع المغلف** :func:`build_envelope` — تجميع ``EmittedEvent`` المكشوفة
  (بلا هوية رسالة — عقود 3-b/3-d) في ``EventEnvelope`` القانوني: معرف
  ``event_id`` حتمي (روح D-07 — الحتمية شرط الإعادة)، و``receive_time``
  من المستدعي (المسار الحي يمرر طابع الاستقبال الفعلي؛ الإعادة التاريخية
  تمرر ``event_time`` نفسها فتثبت الحتمية)، و``source``/``trace_id``
  صريحان. لا ساعة داخلية ولا عشوائية — المصنع نقي قابل للإعادة بتّيًا.
  **توسعة 4-e**: التوقيع بروتوكول هيكلي :class:`EmittedEventLike` فيقبل
  سجلات البنية/السيولة (3-b/3-d) وسجلات التدفق (4-c/4-d) على السواء —
  الشكل واحد (نوع §20 + وقت التأكيد + حمولة pydantic موثقة) والبقية
  شأن الكاشف صاحب السجل.

- **الناشر** :class:`AnalysisEventPublisher` — رفيع عمدًا كناشر اللقطات
  (2-f): يقبل عميل NATS محضّرًا (متصلًا)، يبث بالترميز القانوني للمخطط
  المصدَّر مع رؤوس ``schema_version``/``event_type`` ثم flush؛ إعادة
  الاتصال والتراجع مسؤولية المنصة/worker لا الناشر.

الموضوع: ``{prefix}.event.{instrument}.{timeframe}.{event_type}`` — الأداة
تُنظف بنفس دالة 2-f، و``event_type`` lowercase ليكون رمز موضوع NATS
قانونيًا قابلًا للاشتراك الجالب (نمط ``market.state.…updated`` نفسه).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import schemas
from pydantic import BaseModel
from schemas import EventEnvelope, EventType
from structure.store import deterministic_event_id

from engine_worker.publisher import normalize_instrument

__all__ = [
    "ANALYSIS_EVENT_SUBJECT_PREFIX",
    "AnalysisEventPublisher",
    "EmittedEventLike",
    "NATSPublishClient",
    "build_envelope",
    "subject_for",
]

#: بادئة موضوع أحداث التحليل — نمط §32 الجالب.
ANALYSIS_EVENT_SUBJECT_PREFIX = "market.event"


class EmittedEventLike(Protocol):
    """الشكل الهيكلي لسجل حدث مكشوف — البنية (3-b/3-d) والتدفق (4-c/4-d).

    سجلات ``EmittedEvent`` في الحزمتين dataclasses مجمّدة بهذه الحقول
    الثلاثة نفسها؛ البروتوكول يقبلهما معًا بلا استيراد أي منهما (الناشر
    طبقة تركيب محايدة تجاه الكواشف). الحقول خصائص قراءة فقط (تغايرية)
    فاتحاد حمولات كل حزمة يحقق ``BaseModel`` دون تثبيت تغاير السمات.
    """

    @property
    def event_type(self) -> EventType: ...

    @property
    def event_time(self) -> datetime: ...

    @property
    def payload(self) -> BaseModel: ...


class NATSPublishClient(Protocol):
    """الحد الأدنى من عميل NATS — نفس عقد ناشر اللقطات (2-f) حرفيًا.

    التوقيع مطابق لعميل nats-py فيما يستدعيه الناشر فيحققه أي عميل حقيقي
    بلا لصق، ويحققه العميل الوهمي في الاختبارات حرفيًا.
    """

    async def publish(
        self,
        subject: str,
        payload: bytes = b"",
        reply: str = "",
        headers: dict[str, str] | None = None,
    ) -> None: ...

    async def flush(self) -> None: ...


def subject_for(event_type: EventType, instrument: str, timeframe: str) -> str:
    """الموضوع القانوني: ``market.event.{instrument}.{timeframe}.{type}``."""
    return (
        f"{ANALYSIS_EVENT_SUBJECT_PREFIX}.{normalize_instrument(instrument)}"
        f".{timeframe}.{event_type.value.lower()}"
    )


def build_envelope(
    event: EmittedEventLike,
    instrument: str,
    *,
    source: str,
    trace_id: str,
    receive_time: datetime,
    correlation_id: str | None = None,
) -> EventEnvelope:
    """تجميع مغلف §32 القانوني من حدث مكشوف — نقي حتمي بلا ساعة.

    ``receive_time`` إلزامي صريح من المستدعي (مسار حي: طابع الاستقبال؛
    إعادة تاريخية: ``event_time`` نفسها — حتمية الإعادة شرط البوابة)؛
    و``event_id`` حتمي من هوية الحدث الكاملة (روح D-07) فإعادة الإرسال
    (at-least-once §32) تحمل المعرف نفسه.
    """
    payload = event.payload.model_dump()
    timeframe = str(payload["timeframe"])
    event_id = deterministic_event_id(
        event.event_type.value, instrument, timeframe, event.event_time
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version=schemas.SCHEMA_VERSION,
        event_type=event.event_type,
        event_time=event.event_time,
        receive_time=receive_time,
        source=source,
        trace_id=trace_id,
        correlation_id=correlation_id,
        payload=payload,
    )


class AnalysisEventPublisher:
    """ناشر رفيع لأحداث التحليل — بث وflush، لا إعادة اتصال ولا تراجع."""

    def __init__(
        self,
        nc: NATSPublishClient,
        subject_prefix: str = ANALYSIS_EVENT_SUBJECT_PREFIX,
    ) -> None:
        self._nc = nc
        self._subject_prefix = subject_prefix

    def subject(self, event_type: EventType, instrument: str, timeframe: str) -> str:
        """موضوع الحدث بالبادئة القابلة للحقن (اختبارات/بيئات)."""
        return (
            f"{self._subject_prefix}.{normalize_instrument(instrument)}"
            f".{timeframe}.{event_type.value.lower()}"
        )

    async def publish(self, envelope: EventEnvelope) -> None:
        """بث المغلف بالترميز القانوني + رؤوس §32 ثم flush.

        الحمولة ``model_dump_json()`` كما هي (بايتات UTF-8) — والتحقق ضد
        المخطط المصدَّر مسؤولية المستهلك (نفس عقد 2-f).
        """
        instrument = str(envelope.payload["instrument"])
        timeframe = str(envelope.payload["timeframe"])
        headers = {
            "schema_version": schemas.SCHEMA_VERSION,
            "event_type": envelope.event_type.value,
        }
        await self._nc.publish(
            self.subject(envelope.event_type, instrument, timeframe),
            envelope.model_dump_json().encode("utf-8"),
            headers=headers,
        )
        await self._nc.flush()
