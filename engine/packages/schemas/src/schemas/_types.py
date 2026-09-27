"""أنواع مشروطة مشتركة داخل حزمة schemas (خاصة بالحزمة — لا تُصدَّر علنيًا).

كل قيد هنا مطابق لحدود الخطة (مثل §19.1 للنطاقات) ويُستخدم عبر النماذج
لضمان اتساق JSON Schema المُصدَّر مع العقود المكتوبة.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, Field


def _ensure_utc(value: datetime) -> datetime:
    """فرض عقد الوقت (§7.1): رفض الزمن الساذج وتطبيع الواعي إلى UTC.

    لا يُستخدم أبدًا زمن الساعة المحلية كزمن حدث سوقي.
    """
    if value.tzinfo is None:
        raise ValueError("naive datetime rejected: market event times must be tz-aware (§7.1)")
    return value.astimezone(UTC)


# زمن حدث بمنطقة UTC مضمونة — يُبث وفقًا لعقد §7.1/§32.
UTCDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]

# نطاق مغلق [0.0, 1.0] — جودة/قوة/طراوة/خصم استقلالية (§19.1) وحصص ونِسَب.
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]

# نطاق مغلق [-1.0, +1.0] — درجة الاتجاه (§19.1).
SignedUnit = Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]

# سعر موجب صارم — أسعار الأدوات المتداولة (D-02: عقود مستمرة مشفرة).
PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]

# الاسم الدلالي للسعر — نفس قيد الموجب الصارم أعلاه.
Price = PositiveFloat

# كمية/حجم/مسافة غير سالبة.
NonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]

# أي عدد عشري منتهٍ (أرباح/انزلاق قد تكون سالبة — الانزلاق الملائم سالب).
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]

# مئين مغلق [0.0, 100.0] — مثل مئين التقلب (مثال §32).
Percentile = Annotated[float, Field(ge=0.0, le=100.0, allow_inf_nan=False)]

# عدد صحيح غير سالب — تعدادات الصفوف والاختلالات (§8.2).
NonNegativeInt = Annotated[int, Field(ge=0)]
