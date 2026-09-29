"""سجل الحدث التدفقي المبثوث من كواشف التدفق — قبل تجميع المغلف (§32).

نفس عقد ``structure.events``: الكواشف تخرج سجلات مُصنَّفة الأنواع
(``event_type`` + الحمولة الموثقة من أسس 4-a)؛ **تجميع المغلف** —
``event_id``/``trace_id``/``receive_time`` — مسؤولية الناشر اللاحق حصرًا
ولا يُبنى هنا إطلاقًا (فصل البناء عن النقل بعقد §32).

العقود:

- **الحتمية الصرفة**: سجل مجمّد بلا طابع استقبال ولا هوية رسالة — محتوى
  الكاشف عند الشريط t يحدد السجل بالكامل.

- **لا-نظرة-مستقبلية (§26.3)**: ``event_time`` هو ``bar_time`` الشريط
  الذي **أكد** الحدث — البث بعدها حصرًا (§27 فصل المتطور عن المؤكد).

- **نوع الحمولة محتكر**: ``payload`` اتحاد حمولات التدفق الموثقة في 4-a
  حصرًا — لا ``dict`` يدوي ولا ``BaseModel`` مبهم.

- **المرشحية**: أحداث الامتصاص والإنهاك تخرج ``confirmed=False`` في
  حمولتها (فرضيات قابلة للتأكيد §12.2/§12.3) — التأكيد اللاحق يرفع
  درجة المرشح نفسه ولا يخترع حدثًا موازيًا.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from schemas import (
    AbsorptionEventPayload,
    EventType,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    ImbalanceClusterEventPayload,
)

__all__ = ["EmittedEvent"]


@dataclass(frozen=True)
class EmittedEvent:
    """حدث تدفقي مؤكد عند إقفال شريط فوتبرنت — خرج الكواشف ومدخل الناشر.

    - ``event_type``: نوع §20 الموثق (التمييز بين الجهتين في النوع لا في
      الحمولة — ABSORPTION_BUY مقابل ABSORPTION_SELL مثلًا).
    - ``event_time``: ``bar_time`` الشريط المؤكِد (لا-نظرة-مستقبلية §26.3).
    - ``payload``: حمولة 4-a الموثقة — مجمّدة تمنع الحقول الغريبة.
    """

    event_type: EventType
    event_time: datetime
    payload: (
        AbsorptionEventPayload
        | FlowContinuationEventPayload
        | ExhaustionEventPayload
        | ImbalanceClusterEventPayload
    )
