"""مجموعات معاملات الدمج المصدرة — «كلها في parameter_sets مُصدَّرة» (D-03).

كل ثابت يدخل حساب الدمج يعيش هنا: حصص المجموعات الست (§19.3 — «starting
priors» تُعاد اختبارها في دفتر التجارب وتُدار إصداريًا)، ومعامل خصم
الاستقلالية الهندسي (§19.4)، وعمر الطراوة بوحدات أشرطة الإطار (§19.1)،
والقيم المحايدة الافتراضية للجودة ومعدّل السياق.

الإعداد مجمّد ويمنع الحقول الغريبة؛ ``fingerprint`` بصمة حتمية للمجموعة
كاملة تُختم بها اللقطات والسجلات فتعرف أي إصدار من الرياضيات أنتجها.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator
from schemas import DEFAULT_GROUP_SHARES, EvidenceGroup

__all__ = ["FusionConfig", "default_fusion_config"]


class FusionConfig(BaseModel):
    """إعداد محرك الدمج — المصدر الوحيد لكل ثوابت الحساب (D-03).

    الحقول الأربعة الأولى تحكم رياضيات الدمج مباشرة؛ تغيير أي منها بعد
    الأرشفة يغيّر هوية النتائج (البصمة) — لذلك تُدار إصداريًا وتوثق في
    سجل الترقية مع كل لقطة مؤرشفة.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: حصص المجموعات الست §19.3 — سقوف tanh لكل مجموعة (D-03-أ) وأساس
    #: إعادة التوزيع التناسبي عند الخلو (D-03-ب). مجموعها 1.0.
    group_shares: dict[EvidenceGroup, float] = Field(
        default_factory=lambda: dict(DEFAULT_GROUP_SHARES)
    )

    #: معامل الخصم الهندسي للاستقلالية γ (§19.4): داخل مجموعة الارتباط
    #: نفسها يبقى الأول كامل القيمة ويُخصم كل تالٍ بـ γ^k — «دفعة واحدة
    #: تنتج 4 أحداث» لا تعد أربع تأكيدات مستقلة.
    independence_decay: float = Field(default=0.5, gt=0.0, le=1.0)

    #: عمر الطراوة بالأشرطة (§19.1 freshness): الدليل يبقى كامل الطراوة
    #: عند شمعة تأكيده ويضمحل خطيًا حتى صفر بعد هذا العدد من أشرطة إطاره
    #: — قياس زمني بمقياس الحدث نفسه لا عتبة كونية.
    freshness_ttl_bars: float = Field(default=60.0, gt=0.0)

    #: معدّل السياق الافتراضي (§19.2 context_modifier): محايد 1.0 — تعديله
    #: بالحالة النظامية موطن القرار 6-2 الموثق في ADR-024، لا رقمًا كونيًا
    #: مختلقًا.
    default_context_modifier: float = Field(default=1.0, gt=0.0)

    #: جودة الدليل الافتراضية (§19.1 quality): 1.0 — بوابات التنقيح
    #: أعلى المجرى (المرحلة 1) تمنع الشموع الرديئة من الوصول إلى الكواشف
    #: أصلًا فكل حدث منتَج من مدخل اجتاز الجودة.
    default_quality: float = Field(default=1.0, gt=0.0, le=1.0)

    @field_validator("group_shares")
    @classmethod
    def _shares_complete_and_normalized(
        cls, value: dict[EvidenceGroup, float]
    ) -> dict[EvidenceGroup, float]:
        """الحصص كاملة المجموعات الست وموجبة ومجموعها 1.0 ضمن تعويم معلن.

        حصص ناقصة أو مجموع منحرف تكسر سقوف tanh وإعادة التوزيع معًا —
        تُرفض صاخبة لا تُطبَّع صامتة.
        """
        expected = set(EvidenceGroup)
        if set(value) != expected:
            raise ValueError(
                f"حصص المجموعات ناقصة أو زائدة: {sorted(m.name for m in set(value) ^ expected)} — "
                "الست جميعها إلزامية (§19.3)"
            )
        total = sum(value.values())
        if any(share <= 0.0 for share in value.values()):
            raise ValueError("كل حصة موجبة صارمة — حصة صفرية تلغي سقف مجموعتها")
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"مجموع الحصص {total} ≠ 1.0 (بتسامح 1e-9) — §19.3 حرفيًا")
        return value

    @property
    def fingerprint(self) -> str:
        """بصمة المجموعة الكاملة — sha256 لتسلسل قانوني حتمي.

        ترتيب الحقول ثابت (sort_keys) وتمثيل الأعداد بـ repr الكامل فلا
        يتغير الشيف إلا بتغير فعلي في قيمة تدخل الحساب.
        """
        canonical = json.dumps(
            {
                "group_shares": {group.value: share for group, share in self.group_shares.items()},
                "independence_decay": self.independence_decay,
                "freshness_ttl_bars": self.freshness_ttl_bars,
                "default_context_modifier": self.default_context_modifier,
                "default_quality": self.default_quality,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_fusion_config() -> FusionConfig:
    """الإعداد الافتراضي — حصص §19.3 حرفيًا وخصم 0.5 وعمر 60 شمعة."""
    return FusionConfig()
