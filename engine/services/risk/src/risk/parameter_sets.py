"""مجموعات معاملات المخاطرة المصدرة — كل ثابت تشغيلي في مكان واحد.

نمط ``scenarios.parameter_sets`` و``fusion.parameter_sets`` نفسه (D-03/
D-04): كل ثابت يدخل قرار المخاطرة يعيش هنا مُدارًا إصداريًا ببصمة
حتمية sha256 — فتعرف أي إصدار من الهندسة أنتج أي قرار، و«كل خرق مخاطرة
= رفض صلب موثق بكود» يُقاس على إصدار معلن لا على ثوابت مشتتة.

حدود ما لا يعيش هنا عمدًا:

- **أكواد §22.1 الخمسة عشر وأسماء الكتمات §22.2** — عقود مواصفة في
  ``schemas.enums`` لا معاملات قابلة للضبط (تعطيل حاجب دعوة لتخريب
  البوابة).
- **قيم ATR والتقلب** — مقاييس لحظة تمرر للمحرك من الشمعة، لا ثوابت.
- كل القيم الافتراضية أدناه «قيم أولية هندسية» موثقة المصدر — قابلة
  للاستبدال إصداريًا بتغيير الضبط وإعادة ختم البصمة، لا أرقام كونية
  مختلقة: العتبات المكانية كلها مضاعِفات ATR (ADR-015) والنقدية
  بعملة التسعير.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator
from schemas import (
    CostMode,
    OrderPolicy,
    SessionType,
    SoftSuppressionReason,
)

__all__ = ["RiskConfig", "default_risk_config"]

#: المعدل الافتراضي كاملًا — «scenario quality modifier after
#: calibration» (§23.2): المعايرة مؤجلة حتى المرحلة 9 (CalibrationReport
#: eligible=False) فالمعدل محايد بتأجيل معلن لا بصمت.
SCENARIO_QUALITY_DEFERRAL = (
    "معدل جودة السيناريو §23.2 «after calibration» — المعايرة مؤجلة "
    "حتى المرحلة 9 (CalibrationReport eligible=False) فالمعدل محايد 1.0 "
    "بتوثيق صريح لا صمت"
)


class RiskConfig(BaseModel):
    """إعداد وحدة المخاطرة — المصدر الوحيد لثوابته التشغيلية.

    القيود العشرة §23.3 («The configuration must contain») حرفيًا ثم
    عتبات الحواجب §22.1 وأوزان الكتم §22.2 ومعاملات المعدلات الستة
    §23.2 ونمط التكلفة §25.1-2.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── قيود المخاطرة العشرة (§23.3 «must contain» حرفيًا) ──

    #: 1. سقف مخاطرة الصفقة الواحدة (نقدي بعملة التسعير).
    per_trade_risk_cap: float = Field(default=100.0, gt=0.0)
    #: 2. سقف الخسارة اليومي (نقدي).
    daily_loss_cap: float = Field(default=300.0, gt=0.0)
    #: 3. سقف الخسارة على نافذة متدحرجة (نقدي).
    rolling_loss_cap: float = Field(default=900.0, gt=0.0)
    #: عرض نافذة السقف المتدحرج بالثواني (3 أيام افتراضيًا).
    rolling_loss_window_s: float = Field(default=259_200.0, gt=0.0)
    #: 4. سقف المراكز المتزامنة.
    simultaneous_position_cap: int = Field(default=3, ge=1)
    #: 5. سقف التعرض المترابط (عدد المراكز في أدوات مترابطة — MVP: الأداة نفسها).
    correlated_exposure_cap: int = Field(default=2, ge=1)
    #: 6. سقف مخاطرة الأحداث (نقدي) — يقلص الميزانية عند تواجد نافذة كلي
    #:    (غير عالية الأثر — العالية تحجب حظرًا صلبًا §22.1 رقم 10).
    event_risk_cap: float = Field(default=50.0, gt=0.0)
    #: 7. أقصى ميزانية انزلاق (بوحدات السعر — ذهاب وإياب). يتسق مع
    #:    التقدير الواقعي الافتراضي أدناه (24 دون السقف 30) — سياق سليم
    #:    لا يشعل الحاجب الخامس بنيويًا.
    max_slippage_budget: float = Field(default=30.0, gt=0.0)
    #: 8. أقصى مسافة وقف بمضاعف ATR (مطبَّع — ADR-015).
    max_stop_distance_atr: float = Field(default=5.0, gt=0.0)
    #: 9. أقصى زمن تملك لاستراتيجية السكالب (ثوانٍ).
    max_holding_time_s: float = Field(default=14_400.0, gt=0.0)

    # ── عتبات الحجب الصلب (§22.1 — كل حاجب عتبته الموثقة) ──

    #: رقم 1: أقصى عمر بيانات مقبول بالثواني — الركود وراءه حاجب.
    max_data_staleness_s: float = Field(default=90.0, gt=0.0)
    #: رقم 4: أقصى نسبة فاتحة من الحافة المتوقعة (كسر 0-1).
    max_spread_pct_of_edge: float = Field(default=0.10, gt=0.0, le=1.0)
    #: رقم 4: أو من مسافة الوقف — أيّ الحدين يكفي مقارنةً.
    max_spread_pct_of_stop: float = Field(default=0.05, gt=0.0, le=1.0)
    #: رقم 6: أقصى كمون تنفيذ مسموح (مللي ثانية) لأفق الاستراتيجية.
    max_latency_ms: float = Field(default=750.0, gt=0.0)

    # ── الكتم اللين (§22.2 «بأوزان إعدادية») ──

    #: أوزان الكتمات العشر — الوزن يسهم في المجموع الذي يقارن بالعتبة.
    soft_weights: dict[SoftSuppressionReason, float] = Field(
        default_factory=lambda: {
            SoftSuppressionReason.POOR_LOCATION: 0.3,
            SoftSuppressionReason.WEAK_OR_CORRELATED_EVIDENCE: 0.4,
            SoftSuppressionReason.VOLATILITY_TOO_LOW: 0.2,
            SoftSuppressionReason.VOLATILITY_TOO_EXTREME: 0.4,
            SoftSuppressionReason.REGIME_TRANSITION: 0.3,
            SoftSuppressionReason.TARGET_TOO_CLOSE: 0.4,
            SoftSuppressionReason.STOP_TOO_WIDE: 0.3,
            SoftSuppressionReason.SESSION_CONFLICT: 0.4,
            SoftSuppressionReason.CHASING_EXPANDED_MOVE: 0.4,
            SoftSuppressionReason.HORIZON_EXCEEDED: 0.3,
        }
    )
    #: عتبة الكتم: مجموع أوزان المشتعلة ≥ العتبة ⇒ رفض لين موثق.
    soft_threshold: float = Field(default=1.0, gt=0.0)

    #: عتبات الكتمات الفردية (معايير اشتعال كل كتمة):
    #: 1 POOR_LOCATION — أدنى جودة موقع مقبولة (متوسط درجات §10.3 الثلاث
    #: للمنطقة المرسبة: رد الفعل/عدم التخفيف/الأهمية).
    min_location_quality: float = Field(default=0.35, ge=0.0, le=1.0)
    #: 2 WEAK — أدنى درجة دليل خام مقبولة (|raw_evidence_score|).
    min_evidence_score: float = Field(default=0.15, ge=0.0, le=1.0)
    #: 2 CORRELATED — أقصى تركّز مجموعة واحدة من الحصة الفعلية.
    max_group_concentration: float = Field(default=0.60, ge=0.0, le=1.0)
    #: 3 VOLATILITY_TOO_LOW — أدنى مئين تقلب مقبول لحركة الهدف.
    vol_percentile_min: float = Field(default=15.0, ge=0.0, le=100.0)
    #: 4 VOLATILITY_TOO_EXTREME — أقصى مئين تقلب مقبول لوقف آمن.
    vol_percentile_max: float = Field(default=90.0, ge=0.0, le=100.0)
    #: 6 TARGET_TOO_CLOSE — أدنى R إجمالية مقبولة (المسافة ÷ الوقف).
    min_target_r: float = Field(default=1.5, gt=0.0)
    #: 7 STOP_TOO_WIDE — عتبة عرض الوقف اللينة بمضاعف ATR (دون السقف الصلب 8).
    soft_stop_wideness_atr: float = Field(default=3.0, gt=0.0)
    #: 8 SESSION_CONFLICT — الجلسات المسودة (سلوكها يتنافر مع السكالب).
    session_blacklist: frozenset[SessionType] = Field(
        default_factory=lambda: frozenset({SessionType.MAINTENANCE})
    )
    #: 9 CHASING — أقصى انجراف مقبول عن مرجع الدخول بمضاعف ATR (اللين
    #:    دون حارس الانجراف البنيوي في السيناريوهات — عتبتان غايتان).
    chase_drift_atr: float = Field(default=1.5, gt=0.0)

    # ── التحجيم (§23.2 — السقوف المطلقة ومعاملات المعدلات الستة) ──

    #: السقف المطلق لحجم الأداة (بوحدات الأصل).
    instrument_position_cap: float = Field(default=1.0, gt=0.0)
    #: السقف المطلق لإجمالي أحجام المحفظة (بوحدات الأصل).
    portfolio_position_cap: float = Field(default=2.0, gt=0.0)
    #: معدل السيولة — أرضية المضاعف عند انعدام جودة الموقع.
    liquidity_multiplier_floor: float = Field(default=0.5, gt=0.0, le=1.0)
    #: معدل جودة التنفيذ — نسبة الميزانية التي دونها يبقى المضاعف كاملًا.
    exec_quality_full_below: float = Field(default=0.50, gt=0.0, le=1.0)
    #: معدل جودة التنفيذ — أرضية المضاعف عند استنفاد الميزانية كاملة.
    exec_quality_floor: float = Field(default=0.50, gt=0.0, le=1.0)
    #: معدل الارتباط — عقوبة لكل تعرض مترابط مفتوح.
    correlation_penalty: float = Field(default=0.25, gt=0.0, le=1.0)
    #: معدل التدهور اليومي — خطي: المضاعف = 1 − المستهلك/السقف (عند
    #: السقف يصبح صفرًا ويشتعل الحاجب الصلب رقم 7 قبله).
    drawdown_slope: float = Field(default=1.0, ge=0.0)

    # ── الإبطال البنيوي (§23.4 — عدم يقين التنفيذ) ──

    #: مضاعف عدم اليقين: (كمون ثانية) × (ATR/ثانية الشمعة) × المضاعف.
    execution_uncertainty_multiplier: float = Field(default=0.50, gt=0.0)
    #: مدة شمعة إطار التنفيذ بالثواني (1m افتراضيًا — D-05).
    execution_bar_seconds: float = Field(default=60.0, gt=0.0)

    # ── التكاليف (§25.1-2 + §23.5) ──

    #: نمط القبول («A strategy cannot pass production gates based only
    #: on optimistic costs» — REALISTIC وحده).
    acceptance_cost_mode: CostMode = CostMode.REALISTIC
    #: الحد الأدنى المقبول لـR الصافية المقدرة (§23.5 رفض الحافة).
    min_net_r: float = Field(default=0.50, gt=0.0)
    #: الحد الأدنى للمكافأة المتبقية بعد التكاليف (§22.1 رقم 12 — بوحدات R).
    min_remaining_r: float = Field(default=0.30, gt=0.0)
    #: العمولة ذهابًا وإيابًا لكل وحدة أصل (عملة التسعير).
    commission_per_unit: float = Field(default=4.80, ge=0.0)
    #: تقدير الفاتحة ذهابًا وإيابًا (وحدات سعر).
    spread_estimate: float = Field(default=12.00, ge=0.0)
    #: تقدير الانزلاق ذهابًا وإيابًا بالواقعي (وحدات سعر) — يُضرب
    #: بمضاعف النمط.
    slippage_estimate: float = Field(default=24.00, ge=0.0)
    #: تقدير التمويل/التمويل لفترة التملك المتوقعة.
    funding_estimate: float = Field(default=3.20, ge=0.0)
    #: تقدير الاختيار السلبي المتوقع.
    adverse_selection_estimate: float = Field(default=5.00, ge=0.0)
    #: تقدير أثر التعبئة الجزئية.
    partial_fill_estimate: float = Field(default=3.00, ge=0.0)
    #: مضاعفات الأنماط الثلاثة (§25.1) على الانزلاق والفاتحة معًا —
    #: OPTIMISTIC تشخيصي فقط.
    mode_multipliers: dict[CostMode, float] = Field(
        default_factory=lambda: {
            CostMode.OPTIMISTIC: 0.50,
            CostMode.REALISTIC: 1.00,
            CostMode.STRESS: 2.00,
        }
    )
    #: سياسة الدخول المخططة للنوايا المعتمدة (§24.1/§24.2).
    entry_policy: OrderPolicy = OrderPolicy.LIMIT_AT_ZONE

    @field_validator("soft_weights")
    @classmethod
    def _soft_weights_complete(
        cls, value: dict[SoftSuppressionReason, float]
    ) -> dict[SoftSuppressionReason, float]:
        """الأوزان العشر كاملة موجبة — كتمة بلا وزن إعدادي تعطيل مقنّع."""
        expected = set(SoftSuppressionReason)
        missing = expected - set(value)
        if missing:
            raise ValueError(
                f"أوزان الكتم ناقصة: {sorted(r.value for r in missing)} — "
                "§22.2 «بأوزان إعدادية»: كل الكتمات العشر موزونة"
            )
        extra = set(value) - expected
        if extra:
            raise ValueError(f"أوزان لكتمات مجهولة: {sorted(r.value for r in extra)}")
        for reason, weight in value.items():
            if weight <= 0.0:
                raise ValueError(
                    f"وزن الكتمة {reason.value} = {weight} — الوزن موجب أو إزالة موثقة"
                )
        return value

    @field_validator("mode_multipliers")
    @classmethod
    def _mode_multipliers_complete(cls, value: dict[CostMode, float]) -> dict[CostMode, float]:
        """الأنماط الثلاثة كاملة — نمط بلا مضاعف تكلفة بلا تعريف."""
        expected = set(CostMode)
        if set(value) != expected:
            raise ValueError(
                f"مضاعفات الأنماط يجب أن تكون الثلاثة كاملة {sorted(m.value for m in expected)}"
            )
        return value

    @property
    def fingerprint(self) -> str:
        """بصمة حتمية للمجموعة كاملة — تختم كل قرار تنتجه."""
        payload = json.dumps(
            {
                "per_trade_risk_cap": self.per_trade_risk_cap,
                "daily_loss_cap": self.daily_loss_cap,
                "rolling_loss_cap": self.rolling_loss_cap,
                "rolling_loss_window_s": self.rolling_loss_window_s,
                "simultaneous_position_cap": self.simultaneous_position_cap,
                "correlated_exposure_cap": self.correlated_exposure_cap,
                "event_risk_cap": self.event_risk_cap,
                "max_slippage_budget": self.max_slippage_budget,
                "max_stop_distance_atr": self.max_stop_distance_atr,
                "max_holding_time_s": self.max_holding_time_s,
                "max_data_staleness_s": self.max_data_staleness_s,
                "max_spread_pct_of_edge": self.max_spread_pct_of_edge,
                "max_spread_pct_of_stop": self.max_spread_pct_of_stop,
                "max_latency_ms": self.max_latency_ms,
                "soft_weights": {r.value: w for r, w in sorted(self.soft_weights.items())},
                "soft_threshold": self.soft_threshold,
                "min_location_quality": self.min_location_quality,
                "min_evidence_score": self.min_evidence_score,
                "max_group_concentration": self.max_group_concentration,
                "vol_percentile_min": self.vol_percentile_min,
                "vol_percentile_max": self.vol_percentile_max,
                "min_target_r": self.min_target_r,
                "soft_stop_wideness_atr": self.soft_stop_wideness_atr,
                "session_blacklist": sorted(s.value for s in self.session_blacklist),
                "chase_drift_atr": self.chase_drift_atr,
                "instrument_position_cap": self.instrument_position_cap,
                "portfolio_position_cap": self.portfolio_position_cap,
                "liquidity_multiplier_floor": self.liquidity_multiplier_floor,
                "exec_quality_full_below": self.exec_quality_full_below,
                "exec_quality_floor": self.exec_quality_floor,
                "correlation_penalty": self.correlation_penalty,
                "drawdown_slope": self.drawdown_slope,
                "execution_uncertainty_multiplier": self.execution_uncertainty_multiplier,
                "execution_bar_seconds": self.execution_bar_seconds,
                "acceptance_cost_mode": self.acceptance_cost_mode.value,
                "min_net_r": self.min_net_r,
                "min_remaining_r": self.min_remaining_r,
                "commission_per_unit": self.commission_per_unit,
                "spread_estimate": self.spread_estimate,
                "slippage_estimate": self.slippage_estimate,
                "funding_estimate": self.funding_estimate,
                "adverse_selection_estimate": self.adverse_selection_estimate,
                "partial_fill_estimate": self.partial_fill_estimate,
                "mode_multipliers": {m.value: v for m, v in sorted(self.mode_multipliers.items())},
                "entry_policy": self.entry_policy.value,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_risk_config() -> RiskConfig:
    """الإعداد الافتراضي — قيم أولية موثقة قابلة للاستبدال إصداريًا."""
    return RiskConfig()
