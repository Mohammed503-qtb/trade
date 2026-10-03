"""عقود جسر TradingView — حمولة التنبيه (§36) ومغلف الناقل ومآلات التسليم.

حدود الجسر (§6.4 + D-07 + D-09): TradingView يدفع POST/JSON إلى الحافة
العامة؛ الحمولة خالية من الأسرار حصرًا (§37.1)، ومفتاح الـidempotency
يشتقه الخادم من الحقول الخمسة الخام (D-07) — لا ثقة بأي مفتاح وافد.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ._types import PositiveFloat, UTCDatetime


class _TVModel(BaseModel):
    """أساس موحد لعقود الجسر: مجمّدة وتمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TVAlertPayload(_TVModel):
    """حمولة تنبيه Pine (§36 حرفيًا — الحقول الخام التي يرسلها المؤشر).

    ``bar_time_ms`` زمن شمعة المصدر (مللي ثانية عصر-يونكس — ما يرسله
    ``{{time}}``)، و``price`` سعر الإغلاق لحظة التنبيه (``{{close}}``).
    لا ``idempotency_key`` هنا عمدًا: D-07 يحسم أنه
    ``sha256(schema_version|source|alert_id|instrument|bar_time|event)``
    ويُشتق في الخادم حصرًا — المفتاح الوافد مدخل غير موثوق.
    لا أسرار ولا اعتماديات في الجسم إطلاقًا (§6.4/§37.1).
    """

    schema_version: str = Field(min_length=1)
    source: str = Field(min_length=1)
    alert_id: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    bar_time_ms: int = Field(gt=0)
    timeframe: str = Field(min_length=1)
    event: str = Field(min_length=1)
    price: PositiveFloat


class TVAlertEnvelope(_TVModel):
    """مغلف نشر التنبيه على NATS — روح §32 لعقود عابرة للناقل.

    الحمولة نموذج مُدار إصداريًا (لا سلاسل يدوية §32)، والمفتاح
    ``idempotency_key`` هو اشتقاق D-07 المحسوب خادميًا — المستهلك
    اللاحق (إعادة التحقق القانوني ثم المخاطرة/التنفيذ §36 خطوة 7-8)
    يراه جزء العقد لا مدخلًا خارجيًا.
    """

    event_id: UUID
    schema_version: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    source: str = Field(min_length=1)
    event_time: UTCDatetime
    receive_time: UTCDatetime
    payload: TVAlertPayload


class AlertDeliveryStatus(StrEnum):
    """حالة تسليم التنبيه (جدول alerts التشغيلي §31.6).

    ``RECEIVED``: قُبل وخُزن وأُقرّ ثم يُعالج خلفيًا.
    ``DUPLICATE``: مفتاح D-07 مكرر — إقرار بلا معالجة ثانية (§36 خطوة 3).
    ``REJECTED_AUTH``/``REJECTED_SCHEMA``: رفض صحيح عند البوابة (خطوتا 1-2).
    ``PROCESSED``: اكتملت إعادة التحقق القانوني ووثّق حكمها.
    ``REJECTED_CANONICAL``: أعاد المحرك القانوني التحقق فلم يطابق الحالة.
    """

    RECEIVED = "RECEIVED"
    DUPLICATE = "DUPLICATE"
    REJECTED_AUTH = "REJECTED_AUTH"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    PROCESSED = "PROCESSED"
    REJECTED_CANONICAL = "REJECTED_CANONICAL"


class AlertRevalidation(_TVModel):
    """نتيجة إعادة التحقق القانوني (§36 خطوة 7) — تُخزن مع التنبيه.

    ``matched``: هل الحدث المعلن موجود في الحالة القانونية للمحرك عند
    ``bar_time``؟ ``risk_outcome``: حكم المخاطرة الموثق إن وُجد سيناريو
    مرشح مطابق (لا أمر حي في MVP — التنفيذ مؤجل للمرحلة 11 معلنًا).
    """

    matched: bool
    canonical_event: str | None = None
    scenario_id: str | None = None
    risk_outcome: str | None = None
    detail: str


class WebhookAck(_TVModel):
    """إقرار البوابة الفوري (§6.4: أسرع من 3 ثوانٍ — العمل الثقيل خلفي).

    ``alert_key`` صدى لمفتاح D-07 المشتق خادميًا — للمراقبة والتتبع فقط.
    """

    status: AlertDeliveryStatus
    alert_key: str = Field(min_length=1)
    received_at: UTCDatetime
