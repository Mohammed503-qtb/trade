"""مجموعات معاملات السيناريوهات المصدرة — كل ثابت تشغيلي في مكان واحد.

نمط ``fusion.parameter_sets`` نفسه (D-03/D-04): كل ثابت يدخل تشغيل
السيناريوهات يعيش هنا مُدارًا إصداريًا ببصمة حتمية — فتعرف أي إصدار من
الهندسة أنتج أي مقترح.

حدود ما لا يعيش هنا عمدًا:

- **عدد المجموعات الداعمة للترقية = 2** — ثابت مواصفة لا معامل إعدادي
  («at least two independent evidence groups» §18.4 حرفيًا)؛ جعله قابلًا
  للضبط دعوةٌ لتخريب البوابة.
- **أوزان الأحداث وحصص المجموعات** — ملك ``fusion.parameter_sets``
  (D-03) تستهلكها السيناريوهات كما هي لا تنسخها.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field
from schemas import ScenarioTemplate

__all__ = ["ScenarioConfig", "default_scenario_config"]


class ScenarioConfig(BaseModel):
    """إعداد محرك السيناريوهات — المصدر الوحيد لثوابته التشغيلية.

    الحقول قيم أولية (priors) هندسية موثقة المصدر، لا أرقامًا كونية
    مختلقة: كلها مقاسة بوحدات ATR أو بأشرطة إطار التنفيذ — قياس نسبي
    بالمقياس نفسه الذي تقيس به الكواشف (§16 التطبيع).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: الزعنفة الزمنية لكل قالب (D-04) — عمر المقترح بأشرطة إطار
    #: التنفيذ (1m افتراضيًا D-05) قبل أن ينقضي بلا مشغل: الانعكاس
    #: ينتظر إزاحة تأكيد سريعة بعد الاجتياح، والاستمرار يتحمل ارتدادًا
    #: أطول، والاختراق ينتظر إعادة اختبار لا تتأخر كثيرًا بعد القبول.
    expiry_bars: dict[ScenarioTemplate, int] = Field(
        default_factory=lambda: {
            ScenarioTemplate.REVERSAL: 60,
            ScenarioTemplate.CONTINUATION: 120,
            ScenarioTemplate.BREAKOUT: 60,
        }
    )

    #: مضاعف عازلة التقلب للإبطال (§23.4): العازلة = المضاعف × ATR
    #: لحظة الإنشاء فوق/تحت المستوى البنيوي — من بنية التقلب لا رقم
    #: نقاط كوني.
    invalidation_buffer_atr: float = Field(default=0.5, gt=0.0)

    #: حارس انجراف الدخول §18.4 («moved too far from the planned
    #: entry»): المسافة القصوى من إغلاق شمعة المشغل إلى حدود منطقة
    #: الدخول مقاسة بـATR — تجاوزها يعني ظروف تنفيذ مختلفة بنيويًا
    #: (شرط 6 §18.5) فيُبطَل المشغل الفاشل لا أن يرخَّص دخول رديء.
    #: الجزء «المكلف» من الفحص (reward/risk بعد التكاليف §25.2)
    #: مسؤولية المرحلة 8 — موثق مؤجل لا صمت.
    max_entry_drift_atr: float = Field(default=2.0, gt=0.0)

    #: نافذة القبول لمشغل ACCEPTANCE_BEYOND — عدد الإغلاقات المتتالية
    #: خلف المستوى التي تُعد «قبولًا» (§10.4 روح window_bars في حمولة
    #: الكسر-القبول نفسها).
    acceptance_window_bars: int = Field(default=3, ge=1)

    #: نصف عرض نطاق إعادة الاختبار لمشغل RETEST_HOLD — بـATR: الشمعة
    #: تلمس النطاق حول الحافة ثم الإغلاق صامدًا في جهة الاختراق
    #: (§21.2 «retest/continuation»).
    retest_band_atr: float = Field(default=0.25, gt=0.0)

    @property
    def fingerprint(self) -> str:
        """بصمة حتمية للمجموعة كاملة — تُختم بها المقترحات والانتقالات."""
        payload = json.dumps(
            {
                "expiry_bars": {t.value: b for t, b in sorted(self.expiry_bars.items())},
                "invalidation_buffer_atr": self.invalidation_buffer_atr,
                "max_entry_drift_atr": self.max_entry_drift_atr,
                "acceptance_window_bars": self.acceptance_window_bars,
                "retest_band_atr": self.retest_band_atr,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_scenario_config() -> ScenarioConfig:
    """الإعداد الافتراضي — قيم أولية موثقة قابلة للاستبدال إصداريًا."""
    return ScenarioConfig()
