"""مغلف الأحداث الموحد (§32) — عقد كل رسالة داخلية على الناقل.

كل الرسائل الداخلية تستخدم عقودًا مُدارة إصداريًا؛ «عقد الإنتاج الفعلي يجب
أن يولَّد/يُتحقق منه من مخططات مطبوعة لا سلاسل يدوية» (§32).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ._types import UTCDatetime
from .enums import EventType


class EventEnvelope(BaseModel):
    """المغلف القياسي ذو الحقول التسعة (§32 حرفيًا).

    مجمّد ويمنع الحقول الغريبة: الرسالة عقد غير قابل للعبث بعد البثّ.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    schema_version: str
    event_type: EventType
    event_time: UTCDatetime
    receive_time: UTCDatetime
    source: str
    trace_id: str
    correlation_id: str | None
    payload: dict[str, Any]
