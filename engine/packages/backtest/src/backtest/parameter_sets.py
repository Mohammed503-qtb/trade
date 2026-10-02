"""مجموعات معاملات الإعادة المصدرة — كل ثابت تشغيلي في مكان واحد.

نمط ``risk.parameter_sets`` و``scenarios.parameter_sets`` نفسه: كل ثابت
يدخل عالم المحاكاة يعيش هنا مُدارًا إصداريًا ببصمة حتمية sha256 — فتعرف
أي إصدار من المحاكاة أنتج أي تقرير («نفس البيانات/الإصدار ⇒ نفس
النتائج» §26.2)، و«إصدارات المعاملات جامدة» (§26.1).

حدود ما لا يعيش هنا عمدًا:

- **سياسة الترتيب داخل الشمعة** — عقد مواصفة (IntrabarPolicy في
  schemas.enums) لا معامل قابل للضبط: CONSERVATIVE حصرًا في MVP
  («يجب ألا يختار المخرج المحابي أبدًا» §30).
- **بروتوكول WFO** — له عقد مواصفة مستقل (WFOProtocolConfig) لأن
  §39.3 يجعل الأعداد بروتوكولًا معلنًا لا ضبطًا حرًا.
- كل القيم الافتراضية «قيم أولية هندسية» موثقة المصدر — قابلة
  للاستبدال الإصداري بإعادة ختم البصمة.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator
from schemas import CostMode, IntrabarPolicy

__all__ = [
    "DEFAULT_SAMPLE_WFO_PROTOCOL",
    "BacktestConfig",
    "CostSchedule",
    "default_backtest_config",
]


class CostSchedule(BaseModel):
    """جدول تكلفة إعدادي لأنمط واحد — بوحدات السعر لكل وحدة أصل لكل جهة.

    العمولة بالنقاط الأساسية (bps) من القيمة الاسمية للجهة الواحدة؛
    البقية مطلقة بعملة التسعير.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: نصف الفاتحة لكل جهة (الدخول والإخراج كلٌّ جهة).
    spread_per_side: float = Field(default=0.5, ge=0.0)
    #: العمولة بالنقاط الأساسية من الاسمية لكل جهة (10 bps = 0.1%).
    commission_bps_per_side: float = Field(default=2.0, ge=0.0)
    #: الانزلاق النمذجي لكل جهة (المحاكي يعبئ عند المستويات النظيفة
    #: والانزلاق يسجل كتكلفة محققة — لا ازدواج حساب).
    slippage_per_side: float = Field(default=0.3, ge=0.0)
    #: التمويل — صفر موثق في MVP (سبوت بلا تمويل).
    funding_per_holding_h: float = Field(default=0.0, ge=0.0)


class BacktestConfig(BaseModel):
    """إعداد عالم المحاكاة — المصدر الوحيد لثوابته التشغيلية.

    التعبئة الجزئية (§26.1 «Partial fills modeled»): نسبة إعدادية من
    الكمية المخططة تُعبأ عند كل شمعة لمس للمنطقة؛ 1.0 = تعبئة كاملة
    من أول لمس (أبسط العالمين)، والقيم الأدق تحتاج بيانات حجم أعمق
    (بعد MVP).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: سياسة الترتيب داخل الشمعة — CONSERVATIVE حصرًا في MVP.
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.CONSERVATIVE
    #: الكمون النمذجي المسجل (مللي ثانية) — يُوثق في كل تعبئة (§24.5).
    latency_ms: float = Field(default=250.0, ge=0.0)
    #: نسبة التعبئة لكل شمعة لمس من الكمية المخططة (0, 1].
    fill_fraction_per_bar: float = Field(default=1.0, gt=0.0, le=1.0)
    #: جداول التكلفة الثلاثة (§25.1) — REALISTIC وحده نمط القبول.
    cost_schedules: dict[CostMode, CostSchedule] = Field(
        default_factory=lambda: {
            CostMode.OPTIMISTIC: CostSchedule(
                spread_per_side=0.25,
                commission_bps_per_side=1.0,
                slippage_per_side=0.15,
            ),
            CostMode.REALISTIC: CostSchedule(
                spread_per_side=0.5,
                commission_bps_per_side=2.0,
                slippage_per_side=0.3,
            ),
            CostMode.STRESS: CostSchedule(
                spread_per_side=1.5,
                commission_bps_per_side=3.0,
                slippage_per_side=1.2,
            ),
        }
    )

    @field_validator("cost_schedules")
    @classmethod
    def _three_modes_complete(
        cls, value: dict[CostMode, CostSchedule]
    ) -> dict[CostMode, CostSchedule]:
        """الأنماط الثلاثة كاملة — لا إعداد بلا نمط (بوابة القبول REALISTIC)."""
        missing = [mode for mode in CostMode if mode not in value]
        if missing:
            raise ValueError(
                f"جداول التكلفة ناقصة الأنماط: {missing} — الثلاثة كاملة إلزامًا (§25.1)"
            )
        return value

    @field_validator("intrabar_policy")
    @classmethod
    def _conservative_only_mvp(cls, value: IntrabarPolicy) -> IntrabarPolicy:
        """CONSERVATIVE حصرًا — HIGHER_RESOLUTION مؤجل موثق (§30)."""
        if value is not IntrabarPolicy.CONSERVATIVE:
            raise ValueError(
                f"سياسة الترتيب داخل الشمعة {value} غير متاحة في MVP — "
                "CONSERVATIVE حصرًا (بيانات أعلى دقة من الإطار بعد MVP، "
                "«يجب ألا يختار المخرج المحابي أبدًا» §30)"
            )
        return value

    def schedule_for(self, mode: CostMode) -> CostSchedule:
        """جدول تكلفة نمط — KeyError مستحيل بنيويًا (مدقق الاكتمال)."""
        return self.cost_schedules[mode]

    def fingerprint(self) -> str:
        """بصمة sha256 حتمية — مرتبة المفاتيح فلا يتغير الختم بترتيب قاموس."""
        payload = {
            "intrabar_policy": self.intrabar_policy.value,
            "latency_ms": self.latency_ms,
            "fill_fraction_per_bar": self.fill_fraction_per_bar,
            "cost_schedules": {
                mode.value: schedule.model_dump()
                for mode, schedule in sorted(
                    self.cost_schedules.items(), key=lambda kv: kv[0].value
                )
            },
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()


def default_backtest_config() -> BacktestConfig:
    """الإعداد الافتراضي — قيم أولية هندسية موثقة (بصمة تعيش مع التقرير)."""
    return BacktestConfig()


#: بروتوكول بنية العينة (ليس بروتوكول بحث §39.3 — معلن الاسم صراحة):
#: يثبت بنية التدحرج والحجز الزمني على مرشحي العينة الحقيقيين (103
#: قرارات عبر 24 ساعة) — حجز 4 ساعات بين كل طيتين يستهلك أكثر من
#: نصف النهار فلا تتسع أعداد أكبر. «الأعداد لا تُقلص لمجرد عبور
#: بوابة» فبروتوكول البحث (2000/500/500 خطوة 500) يبقى الافتراضي
#: ويتطلب تاريخًا أطول (موثق في تقاريره).
DEFAULT_SAMPLE_WFO_PROTOCOL: dict[str, float | int | str] = {
    "protocol_name": "SAMPLE_STRUCTURE",
    "train_candidates": 20,
    "validation_candidates": 10,
    "oos_candidates": 10,
    "step_candidates": 5,
    "embargo_s": 14_400.0,
}
