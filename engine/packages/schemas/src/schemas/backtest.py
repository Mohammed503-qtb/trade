"""عقود الإعادة والتنفيذ المحاكى والوسم والمقاييس (§26 + §30 + §29.2 + §39.3).

«الإعادة القانونية للقبول تعمل في محرك الإعادة الخارجي» (§28) — هذه
عقود ذلك المحرك: تعبئة محاكاة حتمية وتحلل تكلفة محقق على التعبئات
الفعلية ووسم §30 بعد انقضاء الأفق ومقاييس §29.2/§39.2 وهوية استنساخ
§26.2 وطيات §39.3.

حدود ما لا يعيش هنا عمدًا:

- **منطق المحاكاة نفسه** (الترتيب المتحفظ، التعبئة الجزئية، الحجز) —
  محرك ``backtest`` الحزمة، هذه عقوده فقط (نمط risk.py/risk).
- **تقدير التكاليف قبل الصفقة** (§23.5/§25.2 التقديري) — عقود risk.py
  من المرحلة 8؛ هنا التحلل **المحقق** على تعبئات وقعت فعلًا.
- **الوسم للمُرخَّصين حصرًا في MVP** — المرفوض قيمته الإسنادية في دفتر
  التجارب (§29.1 المرحلة 8)؛ وسم المرشحين كأهداف تعلم (§29.8) بعد MVP.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._types import (
    FiniteFloat,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    Price,
    UnitInterval,
    UTCDatetime,
)
from .enums import CostMode, Direction, ExitReason, IntrabarPolicy, LabelState, WFORole

__all__ = [
    "BacktestIdentity",
    "BacktestMetrics",
    "BacktestReport",
    "EntrySpec",
    "RDistribution",
    "RealizedCosts",
    "RegimeMetrics",
    "SimulatedFill",
    "SimulatedTrade",
    "WFOProtocolConfig",
    "WFOReport",
    "WFOSegment",
    "WFOWindow",
]


class _BacktestModel(BaseModel):
    """أساس موحد لعقود الإعادة: مجمّدة وتمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ───────────────────────── التعبئة والصفقة (§26.1) ─────────────────────────


class SimulatedFill(_BacktestModel):
    """تعبئة واحدة في العالم المحاكى — سعرًا وكمية ولحظة وكمونًا.

    لحظة التعبئة بدقة إطار البيانات (إغلاق شمعة اللمس) والكمون مسجل
    للفحص §24.5 — لا ساعة داخلية.
    """

    fill_time: UTCDatetime
    price: Price
    quantity: PositiveFloat
    #: كمون النمذجة المسجل (مللي ثانية) — ثابت إعدادي لا قياس.
    latency_ms: NonNegativeFloat


class RealizedCosts(_BacktestModel):
    """التحلل المحقق §25.2 على تعبئات وقعت — بوحدات السعر لكل وحدة أصل.

    المكونات الخمسة كما في التقديري (risk.CostBreakdown) لكن هنا من
    التعبئات الفعلية ذهابًا وإيابًا، والمتطابقة محقاة: الصافي المحقق =
    الحافة الإجمالية المحققة − مجموع المكونات.

    ``funding_financing`` صفر موثق في MVP (سبوت بلا تمويل) و
    ``other_execution_costs`` صفر موثق (الاختيار السلبي المحقق قياسه
    بعد MVP؛ التقديري يعيش في §23.5) — لا اختلاق قياس لم يقع.
    """

    cost_mode: CostMode
    #: الحافة الإجمالية المحققة — (مخرج − متوسط دخول) × جهة الصفقة.
    gross_realized_edge: FiniteFloat
    spread: NonNegativeFloat
    commission: NonNegativeFloat
    slippage: NonNegativeFloat
    funding_financing: NonNegativeFloat
    other_execution_costs: NonNegativeFloat
    #: الصافي المحقق بعد المكونات الخمسة (مححق أدناه).
    net_realized_edge: FiniteFloat

    @model_validator(mode="after")
    def _realized_decomposition_identity(self) -> Self:
        """متطابقة §25.2 المحققة: الصافي = الإجمالي − مجموع المكونات."""
        total = (
            self.spread
            + self.commission
            + self.slippage
            + self.funding_financing
            + self.other_execution_costs
        )
        expected = self.gross_realized_edge - total
        if abs(self.net_realized_edge - expected) > 1e-9 * max(1.0, abs(self.gross_realized_edge)):
            raise ValueError(
                f"تحلل التكلفة المحقق غير متطابق: net_realized_edge={self.net_realized_edge} "
                f"والصافي المحسوب {expected} (§25.2: الإجمالي ناقص المكونات الخمسة)"
            )
        return self


class SimulatedTrade(_BacktestModel):
    """الصفقة المحاكاة الكاملة لنية أمر واحدة — حتمية بذاتها.

    «Partial fills modeled» (§26.1): الدخول تعبئات متعددة بنسبة إعدادية
    لكل شمعة لمس؛ المخرج تعبئة واحدة (المخرج الأول فقط في MVP —
    التدريج §24.6 بعد MVP موثقًا).

    ``exit_reason=None`` تعني أن الصفقة بقيت مفتوحة حتى نهاية البيانات —
    «الوسم بعد انقضاء الأفق حصرًا» (§30) فلا وسم لها ولا تُعد في
    المقاييس؛ تُحصى في ملاحظات التقرير (انضباط موثق).
    """

    trade_intent_id: str
    scenario_id: str
    decision_id: str
    symbol: str
    side: Direction
    #: الكمية المخططة من النية (الميزانية ÷ مسافة الوقف — وحدة R §23.1).
    planned_quantity: PositiveFloat
    #: الكمية المعبأة فعليًا (صفر عند UNFILLED).
    filled_quantity: NonNegativeFloat
    entry_fills: tuple[SimulatedFill, ...]
    #: المخرج — غائب عند UNFILLED أو البقاء مفتوحًا حتى نهاية البيانات.
    exit_fill: SimulatedFill | None
    exit_reason: ExitReason | None
    #: مستوى الوقف المستخدم في المحاكاة (من النية).
    stop_price: Price
    #: مستوى الهدف المستخدم (الهدف الأول — MVP).
    target_price: Price
    #: هل حُسم غموضٌ داخل-شمعة بالترتيب المتحفظ؟ (وقف قبل هدف / دخول ثم وقف)
    ambiguity_resolved_conservatively: bool
    #: MFE/MAE بوحدات R من متوسط الدخول الفعلي عبر مسار ما بعد أول تعبئة
    #: («measured from the actual entry path» §29.2) — صفر عند UNFILLED.
    mfe_r: NonNegativeFloat
    mae_r: NonNegativeFloat
    #: وحدة R السعرية (|مرجع الدخول − الوقف|) — أساس كل مضاعفات R هنا.
    stop_distance: PositiveFloat
    #: التكاليف المحققة بنمط القبول REALISTIC حصرًا في جسم الصفقة
    #: (الأنماط الأخرى تشخيص تُحسب فوقها خارجًا).
    costs: RealizedCosts | None
    #: الوسم §30 — غائب حتى انقضاء الأفق (أو عند غير المنفذة: NOT_EXECUTABLE).
    label: LabelState | None
    #: نظام السوق لحظة القرار — أساس التجميع «حسب النظام» (§9/المقاييس).
    regime: str

    @model_validator(mode="after")
    def _trade_consistency(self) -> Self:
        if self.filled_quantity > 0.0 and not self.entry_fills:
            raise ValueError("كمية معبأة بلا تعبئات دخول — تناقض بنيوي")
        filled_sum = sum(f.quantity for f in self.entry_fills)
        if abs(filled_sum - self.filled_quantity) > 1e-9 * max(1.0, self.filled_quantity):
            raise ValueError(
                f"مجموع تعبئات الدخول {filled_sum} لا يطابق الكمية المعبأة {self.filled_quantity}"
            )
        if self.exit_reason is ExitReason.UNFILLED and self.filled_quantity != 0.0:
            raise ValueError("UNFILLED مع كمية معبأة — تناقض بنيوي")
        if self.filled_quantity == 0.0 and self.exit_reason not in (
            ExitReason.UNFILLED,
            ExitReason.ENTRY_EXPIRY,
            None,
        ):
            raise ValueError(
                f"لا مخرج بلا كمية: exit_reason={self.exit_reason} مع filled_quantity=0"
            )
        return self


# ───────────────────────── المقاييس (§29.2/§39.2) ─────────────────────────


class RDistribution(_BacktestModel):
    """توزيع R الصافية — إحصاءات رتبية حتمية (استيفاء خطي)."""

    mean_r: FiniteFloat
    std_r: NonNegativeFloat
    min_r: FiniteFloat
    p05_r: FiniteFloat
    p50_r: FiniteFloat
    p95_r: FiniteFloat
    max_r: FiniteFloat


class RegimeMetrics(_BacktestModel):
    """مقاييس نظام سوق واحد — «حسب النظام» (تقسيم أنظمة §43)."""

    regime: str
    trades_count: PositiveInt
    net_expectancy_r: FiniteFloat
    #: عامل الربح — None معلن عند انعدام الخاسرين (لا اختلاق ∞)،
    #: وصفر قانوني عند انعدام الرابحين (كلها خاسرة).
    profit_factor: NonNegativeFloat | None
    win_rate: UnitInterval
    total_net_r: FiniteFloat


class BacktestMetrics(_BacktestModel):
    """مقاييس الإعادة الكاملة — توقع صافٍ وعامل ربح وتوزيع R وMFE/MAE.

    كل قيمة None معلنة تعني «لا قياس ممكن» (لا صفقات مُوسومة): غياب
    معلن لا قيمة مختلقة — النمط نفسه في مقيّم الاستئصال (5a.3).
    """

    #: عدد الصفقات المُوسومة (المنتهية داخل البيانات) — أساس كل الإحصاءات.
    labeled_trades: PositiveInt
    #: الصفقات الباقية مفتوحة حتى نهاية البيانات (لا وسم لها — §30).
    open_at_data_end: NonNegativeInt
    #: الصفقات غير المنفذة أصلاً (دخول لم يعبأ) — NOT_EXECUTABLE.
    not_executable: NonNegativeInt
    label_counts: dict[str, PositiveInt]
    net_expectancy_r: FiniteFloat
    #: عامل الربح = مجموع الرابحة ÷ |مجموع الخاسرة| — None عند انعدام
    #: الخاسرين، وصفر قانوني عند انعدام الرابحين.
    profit_factor: NonNegativeFloat | None
    win_rate: UnitInterval
    total_gross_r: FiniteFloat
    total_net_r: FiniteFloat
    r_distribution: RDistribution
    mfe_mean_r: NonNegativeFloat
    mae_mean_r: NonNegativeFloat
    #: مقاييس كل نظام — مرتبة أبجديًا حتمًا (لا ترتيب وصول).
    by_regime: tuple[RegimeMetrics, ...]

    @model_validator(mode="after")
    def _metrics_consistency(self) -> Self:
        counted = sum(self.label_counts.values())
        if counted != self.labeled_trades:
            raise ValueError(
                f"مجموع عدّادات الوسم {counted} لا يطابق المُوسومة {self.labeled_trades}"
            )
        regimes_total = sum(r.trades_count for r in self.by_regime)
        if regimes_total > self.labeled_trades:
            raise ValueError(f"صفقات الأنظمة {regimes_total} تتجاوز المُوسومة {self.labeled_trades}")
        names = [r.regime for r in self.by_regime]
        if len(names) != len(set(names)):
            raise ValueError(f"أنظمة مكررة في التجميع: {names}")
        return self


# ───────────────────────── الهوية والاستنساخ (§26.2) ─────────────────────────


class BacktestIdentity(_BacktestModel):
    """هوية الإعادة التساعية (§26.2 حرفيًا) — «النتيجة الدقيقة قابلة
    للاستنساخ من هذه المعرّفات».

    المعرّفات التسعة بالنص: backtest_id، data_snapshot_id، code_version،
    model_version، parameter_set_version، cost_model_version، random_seed،
    start_time، end_time، instrument_set — تُختم uuid5 في
    ``backtest.identity`` (نمط decision_id_for).
    """

    backtest_id: str
    data_snapshot_id: str
    code_version: str
    model_version: str
    parameter_set_version: str
    cost_model_version: str
    random_seed: NonNegativeInt
    start_time: UTCDatetime
    end_time: UTCDatetime
    instrument_set: tuple[str, ...]

    @model_validator(mode="after")
    def _identity_sanity(self) -> Self:
        if not self.instrument_set:
            raise ValueError("مجموعة الأدوات فارغة — هوية بلا أدوات")
        if self.end_time < self.start_time:
            raise ValueError(f"نافذة الإعادة معكوسة: start={self.start_time} > end={self.end_time}")
        return self


# ───────────────────────── التدحرج الأمامي (§39.3) ─────────────────────────


class WFOProtocolConfig(_BacktestModel):
    """بروتوكول التدحرج الأمامي (§39.3 حرفيًا).

    الافتراض هو بروتوكول البحث: 2000 تدريب / 500 تحقق / 500 خارج-العينة
    تتدحرج 500 — «يمكن زيادة العدد عندما تتطلب الأنظمة ملاحظات أكثر؛
    ولا يُقلص أبدًا لمجرد عبور بوابة». ``protocol_name`` يوثق الاسم؛
    بروتوكول العينة البنيوي يعلن اسمه صراحة ولا يدّعي عبور بوابة بحث.
    """

    protocol_name: str
    train_candidates: PositiveInt
    validation_candidates: PositiveInt
    oos_candidates: PositiveInt
    step_candidates: PositiveInt
    #: الحجز الزمني بين الطيات المتجاورة — ≥ أقصى أفق تقييم للاستراتيجية.
    embargo_s: NonNegativeFloat

    @model_validator(mode="after")
    def _protocol_sanity(self) -> Self:
        if self.step_candidates > self.validation_candidates + self.oos_candidates:
            raise ValueError(
                f"خطوة التدحرج {self.step_candidates} تتجاوز تحقق+خارج "
                f"({self.validation_candidates + self.oos_candidates}) — تقفز مرشحين"
            )
        return self


class WFOSegment(_BacktestModel):
    """طية واحدة داخل نافذة: الدور وحدود المرشحين (شاملة الطرفين)."""

    role: WFORole
    first_index: NonNegativeInt
    last_index: NonNegativeInt

    @model_validator(mode="after")
    def _segment_sanity(self) -> Self:
        if self.last_index < self.first_index:
            raise ValueError(f"طية معكوسة: {self.first_index} > {self.last_index}")
        return self


class WFOWindow(_BacktestModel):
    """نافذة تدحرج واحدة: ثلاث طيات مفصولة بحجز زمني (لا تقاطع أبدًا)."""

    window_index: NonNegativeInt
    segments: tuple[WFOSegment, ...]
    #: أزمنة حدود الحجز الفعلية [بعد التدريب، بعد التحقق] — للتدقيق.
    embargo_boundaries_s: tuple[NonNegativeFloat, ...]

    @model_validator(mode="after")
    def _window_sanity(self) -> Self:
        roles = [s.role for s in self.segments]
        if len(roles) != len(set(roles)) or len(roles) != 3:
            raise ValueError(f"النافذة تحتاج الطيات الثلاث بلا تكرار: {roles}")
        ordered = [WFORole.TRAIN, WFORole.VALIDATION, WFORole.OUT_OF_SAMPLE]
        if roles != ordered:
            raise ValueError(f"الطيات غير مرتبة زمنيًا {roles} — القانوني {ordered}")
        return self


class WFOReport(_BacktestModel):
    """تقرير التدحرج الأمامي — قابل لإعادة الإنتاج بايت-بايت.

    لا مقاييس هنا (المحرك يقيّم فوق الطيات عبر حقن لاحق) — التقرير
    البنيوي: البروتوكول وعدد المرشحين والنوافذ وطيّاتها، ويوثق
    المرشحين المستهلكين بالحجز (المحذوفون لا يُقيَّمون في أي طية).
    """

    protocol: WFOProtocolConfig
    candidates_count: PositiveInt
    windows: tuple[WFOWindow, ...]
    #: عدد المرشحين الذين أكلهم الحجز (لا يتجسدون في أي طية).
    embargoed_count: NonNegativeInt
    notes: tuple[str, ...]

    @model_validator(mode="after")
    def _report_sanity(self) -> Self:
        for window in self.windows:
            for segment in window.segments:
                if segment.last_index >= self.candidates_count:
                    raise ValueError(
                        f"طية تتجاوز المرشحين: {segment.last_index} ≥ {self.candidates_count}"
                    )
        return self


# ───────────────────────── التقرير (§26.2 + بوابة 9) ─────────────────────────


class BacktestReport(_BacktestModel):
    """تقرير الإعادة الكامل — «إعادة كاملة آلية موثقة» (بوابة 9).

    الحتمية: نفس الهوية والمدخلات ⇒ نفس البايتات كلها ما عدا
    ``created_at_utc`` (الاستثناء الموثق الوحيد — نمط AblationReport)؛
    بنّاء التقرير يقبل ساعة محقونة فتصبح الحتمية كاملة.

    ``trades`` بترتيب حتمي (زمن أول تعبئة/قرار ثم معرف السيناريو) و
    ``unresolved_open`` إحصاء الباقيات مفتوحات حتى نهاية البيانات.
    """

    identity: BacktestIdentity
    #: نمط التكلفة المعتمد — REALISTIC حصرًا للقبول (§25.1).
    cost_mode: CostMode
    #: سياسة الترتيب داخل الشمعة — CONSERVATIVE حصرًا في MVP (§30).
    intrabar_policy: IntrabarPolicy
    #: بصمة إعداد المحاكاة (sha256 — backtest.parameter_sets).
    config_fingerprint: str
    trades: tuple[SimulatedTrade, ...]
    metrics: BacktestMetrics
    notes: tuple[str, ...]
    #: الاستثناء الحتمي الموثق الوحيد.
    created_at_utc: UTCDatetime

    @model_validator(mode="after")
    def _report_consistency(self) -> Self:
        if self.cost_mode is not CostMode.REALISTIC:
            raise ValueError(
                f"نمط التكلفة {self.cost_mode} لا يصلح للقبول — REALISTIC وحده نمط القبول (§25.1)"
            )
        if self.intrabar_policy is not IntrabarPolicy.CONSERVATIVE:
            raise ValueError(
                f"سياسة {self.intrabar_policy} غير متاحة في MVP — CONSERVATIVE "
                "حصرًا (بيانات أعلى دقة بعد MVP)"
            )
        return self


class EntrySpec(_BacktestModel):
    """مواصفة الدخول المستخرجة من النية — ما يراه المحاكي حصرًا.

    فصل النية الكاملة عن المحاكاة: المحاكي يستهلك الدخول والوقف والهدف
    والأفق والكمية المخططة — لا يرى تحليلًا ولا سياقًا (حدود الطبقات:
    backtest تحت القرار فلا يستورد risk/scenarios).
    """

    trade_intent_id: str
    scenario_id: str
    decision_id: str
    symbol: str
    side: Direction
    #: الحافة المعاكسة للمنطقة (أسوأ تعبئة قانونية — §30 تحفظًا).
    entry_price: Price
    #: الحد الآخر للمنطقة — التعبئة تتطلب لمس المنطقة.
    zone_opposite_price: Price
    stop_price: Price
    target_price: Price
    expiry: UTCDatetime
    #: لحظة القرار — التعبئة من الشمعة التالية حصرًا (لا-نظرة §26.3).
    decision_time: UTCDatetime
    planned_quantity: PositiveFloat
    #: نظام السوق لحظة القرار (تجميع المقاييس).
    regime: str

    @model_validator(mode="after")
    def _spec_sanity(self) -> Self:
        if self.expiry <= self.decision_time:
            raise ValueError(
                f"انقضاء النية {self.expiry} لا يتقدم لحظة القرار {self.decision_time}"
            )
        if self.side is Direction.LONG and self.stop_price >= self.entry_price:
            raise ValueError(
                f"وقف {self.stop_price} فوق دخول شراء {self.entry_price} — هندسة معكوسة"
            )
        if self.side is Direction.SHORT and self.stop_price <= self.entry_price:
            raise ValueError(
                f"وقف {self.stop_price} تحت دخول بيع {self.entry_price} — هندسة معكوسة"
            )
        return self
