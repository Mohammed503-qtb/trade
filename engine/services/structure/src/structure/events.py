"""سجل الحدث المبثوث من كواشف البنية — قبل تجميع المغلف (§32)، المهمة 3-b.

الكواشف تُخرج سجلات مُصنَّفة الأنواع (``event_type`` + الحمولة الموثقة من
أسس 3-a)؛ **تجميع المغلف** — ``event_id``/``trace_id``/``receive_time`` —
مسؤولية مهمة لاحقة (الناشر 3-f) حصرًا ولا يُبنى هنا إطلاقًا (فصل البناء
عن النقل بعقد §32).

العقود:

- **الحتمية الصرفة**: سجل مجمّد بلا طابع استقبال ولا هوية رسالة — محتوى
  الكاشف عند الشمعة t يحدد السجل بالكامل.

- **لا-نظرة-مستقبلية (§26.3)**: ``event_time`` هو ``bar_time`` الشمعة التي
  **أكدت** الحدث — البث بعدها حصرًا (§27 فصل المتطور عن المؤكد).

- **نوع الحمولة محتكر**: ``payload`` اتحاد الحمولتين البنيويتين الموثقتين
  في 3-a حصرًا (``StructureBreakPayload`` لـINTERNAL_BOS/EXTERNAL_BOS/CHOCH
  و``DisplacementEventPayload`` لـDISPLACEMENT_UP/DOWN) — لا ``dict`` يدوي
  ولا ``BaseModel`` مبهم؛ الطور اللاحق من المرحلة 3 (FVG/OB/premium)
  يوسع الاتحاد بإضافة موثقة على هذا الملف وحده.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from schemas import DisplacementEventPayload, EventType, StructureBreakPayload

__all__ = ["EmittedEvent"]


@dataclass(frozen=True)
class EmittedEvent:
    """حدث بنيوي مؤكد عند إقفال شمعة — خرج الكواشف ومدخل مجمّع المغلف (3-f).

    - ``event_type``: نوع §20 الموثق (التمييز بين كسري BOS في النوع لا في
      الحمولة — الحمولة مشتركة بالعقد 3-a).
    - ``event_time``: ``bar_time`` الشمعة المؤكِدة (لا-نظرة-مستقبلية §26.3).
    - ``payload``: حمولة 3-a الموثقة — مجمّدة تمنع الحقول الغريبة.
    """

    event_type: EventType
    event_time: datetime
    payload: StructureBreakPayload | DisplacementEventPayload
