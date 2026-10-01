"""عقود المخاطرة — لا-تداول (§22) ووحدة R والتحجيم (§23) والتكاليف (§25.2).

الحد الفاصل بين الاستدلال والقرار: هذه العقود تحمل ما تنتجه وحدة
المخاطرة من سيناريو TRIGGERED (خرج من محرك المرحلة 7 بمشغله وإبطاله
المعرّفين) — لا تحليلًا فنيًا («The Risk Engine receives an approved
trade intent candidate, not raw technical analysis» §23).

المصادر الحرفية:
- §22.3 كائن تفسير الرفض السداسي (no_trade_code/severity/triggering_
  conditions/offsetting_evidence/whether_retry_is_allowed/retry_condition).
- §23.2 التحجيم (أساس + المعدلات الستة + السقوف المطلقة).
- §23.4 الإبطال البنيوي الثلاثي (بنية + عازلة تقلب + عدم يقين تنفيذ).
- §23.5 المكافأة/المخاطرة السباعية و«estimated net R».
- §25.2 تحلل التكلفة السداسي (Gross Price Edge − Spread − Commission −
  Slippage − Funding/Financing − Other Execution Costs = Net Trading Edge).
- §31.3 جدول decisions («Final decision object and all gates»).

جميع النماذج مجمّدة تمنع الحقول الغريبة — عقود القرار لا تُطفّر صامتة.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._types import (
    FiniteFloat,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    Price,
    UTCDatetime,
)
from .enums import (
    CostMode,
    DataQuality,
    Direction,
    HardBlockReason,
    NoTradeSeverity,
    RejectionBasis,
    SessionType,
    SizingCapBasis,
    SizingModifierName,
    SoftSuppressionReason,
)
from .evidence import ExplanationObject
from .execution import OrderIntent


class _RiskModel(BaseModel):
    """أساس موحد لعقود المخاطرة: مجمّدة وتمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ───────────────────────── نافذة الخطر الكلي (§17.3) ─────────────────────────


class MacroEventWindow(_RiskModel):
    """نافذة حدث كلي مجدول (§17.3) — مدخل حاجب الحظر (§22.1 رقم 10).

    «A high-impact event near a scalp entry can cause a hard block even
    when technical evidence is strong» — النافذة تحمل الحدث وأثره
    الزمني (قبل/بعد) ونطاق أصوله؛ محرك الكلي مطوي في market_state
    (انحراف موثق في build_plan §B) فالمصدر سياق القرار لا جدول كلي.
    """

    #: لحظة الإصدار المجدول (§17.3 event_time).
    event_time: UTCDatetime
    #: نطاق الأصول المتأثرة — رمز الأداة أو «*» للسوق كله.
    asset_scope: str
    #: الأهمية (§17.3 importance) — «HIGH» وحدها عالية الأثر لحاجب §22.1.
    importance: str
    #: عنوان الحدث — توثيق بشري للنافذة (بيان تضخم/قرار مصرف/...).
    title: str
    #: عرض نافذة الحظر قبل الإصدار بالثواني (§17.3 pre_event_window).
    pre_event_window_s: NonNegativeFloat
    #: عرض نافذة الحظر بعد الإصدار بالثواني (§17.3 post_event_window).
    post_event_window_s: NonNegativeFloat

    @property
    def high_impact(self) -> bool:
        """هل الحدث عالي الأثر؟ — أهمية HIGH حصرًا (قاعدة موثقة)."""
        return self.importance.strip().upper() == "HIGH"

    def blocks(self, moment: datetime) -> bool:
        """هل اللحظة داخل نافذة الحظر؟ — قياس زمني صرف حتمي.

        الحدث غير عالي الأثر لا يحجب أبدًا (§22.1 رقم 10 «high-impact
        scheduled event» حصرًا) والنافذة [event_time − pre, event_time +
        post] مغلقة الطرفين.
        """
        if not self.high_impact:
            return False
        start = self.event_time.timestamp() - self.pre_event_window_s
        end = self.event_time.timestamp() + self.post_event_window_s
        return start <= moment.timestamp() <= end


# ───────────────────────── سياق التقييم (حقن الحواجب) ─────────────────────────


class EvaluationContext(_RiskModel):
    """وقائع التشغيل لحظة القرار — الحقائق التي تحكم الحواجب والكتمات.

    مبدأ التصميم (ADR-026): كل حقل افتراضيه «سليم» — فبناء السياق
    الفارغ يعني سوقًا صالحًا تمامًا للتقييم، وكل اختبار حقن فشل مستقل
    (بوابة الخروج 8: «كلٌّ باختبار حقن فشل مستقل») يطفئ حقيقة واحدة
    فيشتعل حاجبها وحده — لا سبيل آخر لاشتعال حاجب من غير حقنه.

    الحقول الزمنية أعمار وقيم مقاسة لحظة القرار (لا طوابع — الزمن
    يمرر للمحرك من شمعة القرار نفسها: لا ساعة داخلية §26.2).
    """

    #: جودة البيانات الحية (§7.4) — غير الآمنة تحجب (§22.1 رقم 1).
    data_quality: DataQuality = DataQuality.HEALTHY
    #: عمر آخر بيانات مؤكدة بالثواني — الركود حقن مستقل للرقم 1.
    data_age_seconds: NonNegativeFloat = 0.0
    #: هل الأداة قابلة للتداول؟ (موقوفة/غير متاحة/خارج ساعات القبول — رقم 2)
    instrument_tradable: bool = True
    #: توثيق لماذا الأداة غير قابلة — إلزامي عند التعطيل (لا صمت).
    instrument_status_note: str = ""
    #: صحة اتصال وجهة التنفيذ (رقم 3).
    venue_healthy: bool = True
    #: تقدير الفاتحة بوحدات السعر (رقم 4) — ذهاب وإياب.
    spread_estimate: NonNegativeFloat = 0.0
    #: تقدير الانزلاق المتوقع بوحدات السعر (رقم 5) — ذهاب وإياب واقعي.
    slippage_estimate: NonNegativeFloat = 0.0
    #: كمون التنفيذ المتوقع بالمللي ثانية (رقم 6).
    latency_ms: NonNegativeFloat = 0.0
    #: المراكز المفتوحة الآن (رقم 7 — سقف المراكز المتزامنة §23.3).
    positions_open: NonNegativeInt = 0
    #: التعرض المفتوح في أدوات مترابطة (رقم 7 — سقف التعرض المترابط §23.3).
    correlated_exposure: NonNegativeInt = 0
    #: المخاطرة النقدية المستهلكة اليوم (رقم 7 — سقف الخسارة اليومي).
    risk_used_today: NonNegativeFloat = 0.0
    #: المخاطرة المستهلكة على النافذة المتدحرجة (رقم 7 — السقف المتدحرج).
    risk_used_rolling: NonNegativeFloat = 0.0
    #: هل يمكن وضع الوقف ومطابقته موثوقًا عند الوجهة؟ (رقم 8 — خارجي)
    stop_reliable: bool = True
    #: هل الوسيط/البورصة تقبل الأداة ونوع الأمر؟ (رقم 9)
    broker_accepts_order: bool = True
    #: نوافذ الأحداث الكلية عالية الأثر (رقم 10 — §17.3).
    embargo_windows: tuple[MacroEventWindow, ...] = ()
    #: سيناريوهات معاكسة ذات أسبقية أعلى غير محسومة (رقم 13 — خطر ثنائي).
    conflicting_scenario_ids: tuple[str, ...] = ()
    #: معرفات الأحداث المراسِمة المستهلكة سلفًا (رقم 14 — لا معلومة بنيوية جديدة).
    consumed_anchor_event_ids: tuple[str, ...] = ()
    #: حالة الطوارئ/مفتاح الإيقاف (رقم 15).
    kill_switch: bool = False
    #: الجلسة الحالية (§9.4) — لكتم تعارض السلوك الجزئي (§22.2 رقم 8).
    session: SessionType = SessionType.UTC_DAY


# ───────────────────────── كائن تفسير الرفض (§22.3) ─────────────────────────


class NoTradeExplanation(_RiskModel):
    """تفسير عدم التداول (§22.3 حرفيًا — الحقول الستة بأسماء الخطة).

    «Every rejection has: no_trade_code, severity, triggering_conditions,
    offsetting_evidence, whether_retry_is_allowed, retry_condition» —
    رفض بلا تفسير مكتمل مستحيل معماريًا: الشرط يفحص آليًا في البوابة.
    """

    #: رمز عدم التداول — حاجب صلب (§22.1) أو كتمة لينة (§22.2).
    no_trade_code: HardBlockReason | SoftSuppressionReason
    #: الشدة — صلب يقاطع أو لين يكتم موزونًا.
    severity: NoTradeSeverity
    #: الشروط المشعِّلة — نص يوثق الحقائق المقاسة التي أشعلت الرمز.
    triggering_conditions: str
    #: الدليل المقابل — ما كان يؤيد الدخول رغم الرفض (محاسبة صادقة).
    offsetting_evidence: tuple[str, ...]
    #: هل تسمح إعادة المحاولة؟ (اللين كله يسمح؛ الصلب حسب رمزه)
    whether_retry_is_allowed: bool
    #: شرط إعادة المحاولة — إلزامي عند السماح وممنوع عند المنع.
    retry_condition: str | None

    @model_validator(mode="after")
    def _retry_contract(self) -> Self:
        """شرط الإعادة إلزامي مع السماح ومحظور مع المنع — لا غموض."""
        if self.whether_retry_is_allowed and (
            self.retry_condition is None or not self.retry_condition.strip()
        ):
            raise ValueError(
                "retry_condition إلزامي عند السماح بإعادة المحاولة (§22.3) — "
                "السماح بلا شرط موثق وعدٌ معلّق لا عقد"
            )
        if not self.whether_retry_is_allowed and self.retry_condition is not None:
            raise ValueError("retry_condition حاضر مع منع الإعادة (§22.3) — المنع لا يعلّق شرطًا")
        if not self.triggering_conditions.strip():
            raise ValueError(
                "triggering_conditions فارغة — «Every rejection has ...» (§22.3): "
                "لا رفض بلا شروط مشعِّلة موثقة"
            )
        return self


# ───────────────────────── الإبطال البنيوي (§23.4) ─────────────────────────


class StructuralStop(_RiskModel):
    """حساب الوقف البنيوي (§23.4 حرفيًا) — «بنية + عازلة تقلب + عدم
    يقين تنفيذ» لا رقم نقاط كوني.

    مرجع الدخول المخطط (ADR-026): الحافة المحافظة لمنطقة الدخول — أبعد
    حافة عن الوقف — فتكون 1R المحسوبة أسوأ حالة للتعبئة (التحجيم لا
    يتفاءل بتعبة أفضل).
    """

    #: المستوى البنيوي المُبطِل (من قاعدة السيناريو §18.5).
    structural_level: Price
    #: عازلة التقلب فوق/تحت المستوى (من قاعدة السيناريو — مضاعف ATR).
    volatility_buffer: NonNegativeFloat
    #: عدم يقين التنفيذ المضاف (كمون × معدل التقلب الزمني — ADR-026).
    execution_uncertainty: NonNegativeFloat
    #: سعر الوقف النهائي — المستوى ± (العازلة + عدم اليقين) بجهة الإبطال.
    stop_price: Price
    #: مرجع الدخول المخطط (الحافة المحافظة).
    entry_reference: Price
    #: مسافة الوقف بوحدات السعر (|المرجع − الوقف|) — مقام وحدة R.
    stop_distance: PositiveFloat
    #: هل الإبطال يتطلب قبولًا عبر المستوى (إغلاقًا) لا فتيلًا؟
    accept_through: bool
    #: ATR الشمعة المرجعية — سجل المقياس الذي بُني عليه الوقف.
    atr: PositiveFloat
    #: مسافة الوقف مطبَّعة بـATR — للمقارنة المعيارية (ADR-015).
    stop_distance_atr: PositiveFloat


# ───────────────────────── التحجيم (§23.2) ─────────────────────────


class SizingModifier(_RiskModel):
    """معدل تحجيم واحد — اسمه وقيمته وتوثيق سببه.

    المعدل ∈ (0, 1]: لا معدل يرفع الحجم أبدًا — «الخطر الناتج ≤
    السقف دائمًا» (بوابة الخروج 8) تُبنى على هذا الحصر.
    """

    name: SizingModifierName
    #: المضاعف (0, 1] — يضرب الحجم الأساسي.
    multiplier: float
    #: توثيق السبب — لماذا هذا المعدل بهذه القيمة هنا (لا أرقام صامتة).
    rationale: str

    @model_validator(mode="after")
    def _multiplier_band(self) -> Self:
        """المعدل لا يرفع الأحجام أبدًا — نطاق (0, 1] حصرًا."""
        if not (0.0 < self.multiplier <= 1.0):
            raise ValueError(
                f"معدل التحجيم {self.name.value} خارج (0, 1]: {self.multiplier} — "
                "لا معدل يرفع الحجم (§23.2 + بوابة الخروج 8)"
            )
        if not self.rationale.strip():
            raise ValueError(f"معدل التحجيم {self.name.value} بلا توثيق سبب — لا أرقام صامتة")
        return self


class SizingResult(_RiskModel):
    """نتيجة التحجيم الكاملة (§23.2) — الشفافية الرقمية لكل خطوة.

    الحساب الحرفي: ``position_size = allowed_risk_money /
    stop_distance_value`` ثم المعدلات الستة مضاعفةً ثم السقوف المطلقة
    (أداة ومحفظة) — و«resulting_risk_money = position_size ×
    stop_distance_value ≤ risk_budget دائمًا» شرط يُحقق في النموذج ذاته.
    """

    #: المخاطرة النقدية المسموحة (بعد أي خفض إعدادي للميزانية).
    risk_budget: PositiveFloat
    #: مسافة الوقف بوحدات السعر لكل وحدة أصل — مقام المعادلة.
    stop_distance_value: PositiveFloat
    #: الحجم الأساسي قبل المعدلات (= risk_budget / stop_distance_value).
    base_position_size: PositiveFloat
    #: المعدلات الستة بترتيب §23.2 الحرفي.
    modifiers: tuple[SizingModifier, ...]
    #: حاصل ضرب المعدلات ∈ (0, 1].
    final_multiplier: float
    #: السقف المطلق لحجم الأداة (بوحدات الأصل).
    instrument_cap: PositiveFloat
    #: السعة المتبقية من سقف المحفظة (بوحدات الأصل).
    portfolio_cap_remaining: PositiveFloat
    #: أي السقوف قيّد الحجم النهائي (NONE إن لم يقيّد سقف).
    capped_by: SizingCapBasis
    #: الحجم النهائي بعد المعدلات والسقوف.
    position_size: PositiveFloat
    #: المخاطرة النقدية الناتجة — ≤ الميزانية دائمًا (خاصية البوابة).
    resulting_risk_money: NonNegativeFloat

    @model_validator(mode="after")
    def _risk_never_exceeds_budget(self) -> Self:
        """الخاصية المركزية: الخطر الناتج ≤ الميزانية دائمًا.

        «تحقق: خاصية الخطر الناتج ≤ السقف دائمًا» (build_plan 8.3) —
        يُحقق هنا بنيويًا فوق إثبات hypothesis: أي نتيجة تحجيم تتجاوز
        ميزانيتها مرفوضة صاخبة عند البناء نفسه.
        """
        tolerance = 1e-9 * max(1.0, self.risk_budget)
        if self.resulting_risk_money > self.risk_budget + tolerance:
            raise ValueError(
                f"الخطر الناتج {self.resulting_risk_money} يتجاوز الميزانية "
                f"{self.risk_budget} — مستحيل بنيويًا (§23.2 + بوابة الخروج 8)"
            )
        if self.position_size > self.instrument_cap * (1.0 + 1e-12):
            raise ValueError(f"الحجم {self.position_size} يتجاوز سقف الأداة {self.instrument_cap}")
        if self.position_size > self.portfolio_cap_remaining * (1.0 + 1e-12):
            raise ValueError(
                f"الحجم {self.position_size} يتجاوز سعة المحفظة {self.portfolio_cap_remaining}"
            )
        if not (0.0 < self.final_multiplier <= 1.0):
            raise ValueError(f"حاصل المعدلات {self.final_multiplier} خارج (0, 1] — لا رفع للتحجيم")
        return self


# ───────────────────────── التكاليف (§25.2 + §23.5) ─────────────────────────


class CostBreakdown(_RiskModel):
    """تحلل التكلفة (§25.2 حرفيًا) — «Post-trade P&L must be decomposed
    into» والتحلل هنا التقديري قبلها بوحدات السعر لكل وحدة أصل، ذهابًا
    وإيابًا، بنمط تكلفة معلن (§25.1).

    المتطابقة محقاة في النموذج: net_trading_edge = gross − مجموع
    المكونات الخمسة — أي انحراف رفض صاخب لا تقريب صامت.
    """

    #: نمط التكلفة (§25.1) — REALISTIC وحده نمط القبول.
    cost_mode: CostMode
    #: Gross Price Edge — المسافة الإجمالية نحو الهدف.
    gross_price_edge: NonNegativeFloat
    #: Spread — تكلفة الفاتحة.
    spread: NonNegativeFloat
    #: Commission — العمولة/الرسوم.
    commission: NonNegativeFloat
    #: Slippage — الانزلاق المتوقع.
    slippage: NonNegativeFloat
    #: Funding/Financing — التمويل حيث ينطبق.
    funding_financing: NonNegativeFloat
    #: Other Execution Costs — الاختيار السلبي المتوقع وأثر التعبئة الجزئية.
    other_execution_costs: NonNegativeFloat
    #: Net Trading Edge — الحافة الصافية (= gross − المكونات، محقاة أدناه).
    net_trading_edge: FiniteFloat

    @model_validator(mode="after")
    def _decomposition_identity(self) -> Self:
        """متطابقة §25.2: الصافي = الإجمالي − مجموع المكونات الخمسة."""
        total_costs = (
            self.spread
            + self.commission
            + self.slippage
            + self.funding_financing
            + self.other_execution_costs
        )
        expected = self.gross_price_edge - total_costs
        tolerance = 1e-9 * max(1.0, self.gross_price_edge)
        if abs(self.net_trading_edge - expected) > tolerance:
            raise ValueError(
                f"تحلل التكلفة غير متطابق: net_trading_edge={self.net_trading_edge} "
                f"والصافي المحسوب {expected} (§25.2: الإجمالي ناقص المكونات الخمسة)"
            )
        return self


class RewardRiskEstimate(_RiskModel):
    """تقدير المكافأة/المخاطرة (§23.5 حرفيًا) — المكونات السبعة وR الصافية.

    «The engine computes: gross target distance; expected slippage;
    commission/fee; spread cost; expected adverse selection; partial-
    fill risk; estimated net R» — و«A setup can be rejected because the
    gross target is large but cost-adjusted edge is insufficient»:
    الرفض قرار كمي على estimated_net_r مقابل الحد الأدنى الإعدادي.
    """

    #: نمط التكلفة المعتمد في التقدير (§25.1) — القبول بـREALISTIC.
    cost_mode: CostMode
    #: مستوى الهدف المعتمد (أقرب هدف §10.5 من السيناريو).
    target_level: Price
    #: مرجع الدخول المخطط (الحافة المحافظة — نفسه في الوقف).
    entry_reference: Price
    #: مسافة الوقف (وحدة R السعرية — من §23.4).
    stop_distance: PositiveFloat
    #: 1. gross target distance — |الهدف − الدخول|.
    gross_target_distance: NonNegativeFloat
    #: 2. expected slippage — ذهابًا وإيابًا.
    expected_slippage: NonNegativeFloat
    #: 3. commission/fee — ذهابًا وإيابًا.
    commission_fee: NonNegativeFloat
    #: 4. spread cost — ذهابًا وإيابًا.
    spread_cost: NonNegativeFloat
    #: 5. expected adverse selection — الاختيار السلبي المتوقع.
    expected_adverse_selection: NonNegativeFloat
    #: 6. partial-fill risk — أثر التعبئة الجزئية المتوقع.
    partial_fill_risk: NonNegativeFloat
    #: 7. estimated net R — الحافة الصافية ÷ مسافة الوقف (قد تكون سالبة).
    estimated_net_r: FiniteFloat
    #: R الإجمالية قبل التكاليف (المسافة ÷ الوقف) — شفافية القياس.
    gross_r: NonNegativeFloat
    #: التحلل الكامل §25.2 (بوحدات السعر لكل وحدة أصل).
    breakdown: CostBreakdown

    @model_validator(mode="after")
    def _component_consistency(self) -> Self:
        """المكونات السبعة = تحلل §25.2 نفسه — لا حسابين منفصلين."""
        b = self.breakdown
        if (
            abs(b.gross_price_edge - self.gross_target_distance) > 1e-9
            or abs(b.slippage - self.expected_slippage) > 1e-9
            or abs(b.commission - self.commission_fee) > 1e-9
            or abs(b.spread - self.spread_cost) > 1e-9
        ):
            raise ValueError("مكونات §23.5 لا تطابق تحلل §25.2 — حساب واحد لا حسابان")
        return self


# ───────────────────────── كائن القرار (§31.3 decisions) ─────────────────────────


class RiskDecision(_RiskModel):
    """القرار النهائي وكل بواباته (§31.3 «Final decision object and all
    gates») — مخرج وحدة المخاطرة الوحيد لكل سيناريو TRIGGERED.

    القرار إما ترخيص (مع نية أمر §24.1 كاملة) وإما رفض موثق الأساس
    بتفسير §22.3 لكل سبب — لا حالة بين بين. التفسير §2.8 مرافق إلزامي
    بتقدير تكاليف مسدد (وعد المرحلة 6) وسبب رفض عند الرفض حصرًا.
    """

    #: معرف حتمي (uuid5 فوق السيناريو — قرار ترخيص واحد لكل سيناريو).
    decision_id: str
    scenario_id: str
    symbol: str
    direction: Direction
    #: لحظة القرار (زمن شمعة القرار — لا ساعة داخلية).
    decided_at: UTCDatetime
    #: هل رُخص الدخول؟
    approved: bool
    #: أساس الرفض — إلزامي عند الرفض وممنوع عند الترخيص.
    rejection_basis: RejectionBasis | None
    #: الحواجب الصلبة المشتعلة (§22.1) — فارغة عند الترخيص.
    hard_blocks: tuple[NoTradeExplanation, ...]
    #: الكتمات اللينة المشتعلة (§22.2) — موثقة حتى عند الترخيص تحت العتبة.
    soft_suppressions: tuple[NoTradeExplanation, ...]
    #: مجموع أوزان الكتمات المشتعلة مقابل العتبة الإعدادية.
    soft_total: NonNegativeFloat
    #: الوقف البنيوي (§23.4) — محسوب قبل البوابات (بوابات 4/8 تحتاجه).
    stop: StructuralStop | None
    #: التحجيم (§23.2) — عند بلوغ مرحلته فقط.
    sizing: SizingResult | None
    #: المكافأة/المخاطرة (§23.5) — عند بلوغ مرحلتها فقط.
    reward_risk: RewardRiskEstimate | None
    #: نية الأمر المعتمدة (§24.1) — عند الترخيص حصرًا.
    order_intent: OrderIntent | None
    #: كائن التفسير §2.8 — بتكلفة مسددة وسبب رفض عند الرفض.
    explanation: ExplanationObject
    #: بصمة مجموعة معاملات المخاطرة التي أنتجت القرار (إصداري).
    parameter_fingerprint: str

    @model_validator(mode="after")
    def _decision_contract(self) -> Self:
        """عقد القرار: ترخيص = اكتمال، رفض = أساس موثق ولا نية أمر."""
        if self.approved:
            if self.rejection_basis is not None:
                raise ValueError("قرار مرخِّص يحمل أساس رفض — تناقض جوهري")
            if self.hard_blocks:
                raise ValueError(
                    "قرار مرخِّص مع حواجب صلبة مشتعلة — «refuse new entries when "
                    "any of the following holds» (§22.1)"
                )
            missing = [
                name
                for name, part in (
                    ("stop", self.stop),
                    ("sizing", self.sizing),
                    ("reward_risk", self.reward_risk),
                    ("order_intent", self.order_intent),
                )
                if part is None
            ]
            if missing:
                raise ValueError(f"قرار مرخِّص ناقص الأجزاء {missing} — الترخيص اكتمال لا وعد")
        else:
            if self.rejection_basis is None:
                raise ValueError(
                    "قرار رفض بلا أساس — HARD_BLOCK/SOFT_SUPPRESSED/NET_EDGE_INSUFFICIENT"
                )
            if self.order_intent is not None:
                raise ValueError("قرار رفض يحمل نية أمر — لا تنفيذ لما رُفض (§22)")
        return self
