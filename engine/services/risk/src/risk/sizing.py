"""التحجيم (§23.2) — الأساس والمعدلات الستة والسقوف المطلقة.

«position_size = allowed_risk_money / stop_distance_value» ثم المعدلات
الستة بترتيب الخطة (تقلب/سيولة/جودة تنفيذ/ارتباط/تدهور يومي/جودة
سيناريو بعد المعايرة) ثم السقوف المطلقة (أداة/محفظة).

الحصانة المعمارية (بوابة الخروج 8): كل معدل ∈ (0, 1] — لا معدل يرفع
الأحجام أبدًا — و``SizingResult`` يرفض بنيويًا أي نتيجة يتجاوز خطرها
ميزانيتها. سقف مخاطرة الأحداث (§23.3) يقلص الميزانية عند تواجد أي
نافذة كلي (غير عالية الأثر — العالية تحجب الحجب الصلب رقم 10).
"""

from __future__ import annotations

from datetime import datetime

from schemas import (
    EvaluationContext,
    MarketStateSnapshot,
    Scenario,
    SizingCapBasis,
    SizingModifier,
    SizingModifierName,
    SizingResult,
    StructuralStop,
)

from .no_trade import location_quality
from .parameter_sets import SCENARIO_QUALITY_DEFERRAL, RiskConfig

__all__ = ["compute_sizing"]

#: أرضية صارمة تمنع انعدام المضاعف — قيمة صغرى موجبة تحفظ عقد (0, 1].
_EPSILON: float = 1e-6


def _volatility_modifier(
    market_state: MarketStateSnapshot | None, config: RiskConfig
) -> SizingModifier:
    """معدل التقلب — خارج النطاق يخفض تناسبيًا (ADR-015: قياس مئيني)."""
    if market_state is None:
        return SizingModifier(
            name=SizingModifierName.VOLATILITY,
            multiplier=1.0,
            rationale="بلا لقطة حالة معتمدة — المعدل محايد بتوثيق (لا قراءة بلا مقياس)",
        )
    percentile = float(market_state.volatility_percentile)
    if percentile < config.vol_percentile_min:
        multiplier = max(_EPSILON, percentile / config.vol_percentile_min)
        rationale = (
            f"مئين التقلب {percentile:.1f} دون الأدنى {config.vol_percentile_min:.1f} — "
            f"تخفيض تناسبي إلى {multiplier:.3f}"
        )
    elif percentile > config.vol_percentile_max:
        multiplier = max(_EPSILON, config.vol_percentile_max / percentile)
        rationale = (
            f"مئين التقلب {percentile:.1f} فوق الأقصى {config.vol_percentile_max:.1f} — "
            f"تخفيض تناسبي إلى {multiplier:.3f}"
        )
    else:
        multiplier = 1.0
        rationale = (
            f"مئين التقلب {percentile:.1f} داخل النطاق "
            f"[{config.vol_percentile_min:.1f}, {config.vol_percentile_max:.1f}] — معدل كامل"
        )
    return SizingModifier(
        name=SizingModifierName.VOLATILITY, multiplier=multiplier, rationale=rationale
    )


def _liquidity_modifier(scenario: Scenario, config: RiskConfig) -> SizingModifier:
    """معدل السيولة — من جودة موقع منطقة الاستناد (درجات §10.3)."""
    quality = location_quality(scenario)
    multiplier = (
        config.liquidity_multiplier_floor + (1.0 - config.liquidity_multiplier_floor) * quality
    )
    return SizingModifier(
        name=SizingModifierName.LIQUIDITY,
        multiplier=multiplier,
        rationale=(
            f"جودة الموقع {quality:.3f} (متوسط درجات §10.3) — المضاعف "
            f"{multiplier:.3f} بين الأرضية {config.liquidity_multiplier_floor:.2f} والكامل"
        ),
    )


def _execution_quality_modifier(context: EvaluationContext, config: RiskConfig) -> SizingModifier:
    """معدل جودة التنفيذ — أسوأ نسبة استهلاك (كمون/انزلاق) من الميزانية."""
    latency_ratio = (
        context.latency_ms / config.max_latency_ms if config.max_latency_ms > 0.0 else 1.0
    )
    slippage_ratio = (
        context.slippage_estimate / config.max_slippage_budget
        if config.max_slippage_budget > 0.0
        else 1.0
    )
    worst = max(latency_ratio, slippage_ratio)
    if worst <= config.exec_quality_full_below:
        multiplier = 1.0
        rationale = (
            f"أسوأ استهلاك {worst:.2f} من الميزانية دون "
            f"{config.exec_quality_full_below:.2f} — جودة كاملة"
        )
    else:
        span = max(_EPSILON, 1.0 - config.exec_quality_full_below)
        fraction = min(1.0, (worst - config.exec_quality_full_below) / span)
        multiplier = 1.0 - fraction * (1.0 - config.exec_quality_floor)
        rationale = (
            f"أسوأ استهلاك {worst:.2f} من الميزانية — تخفيض خطي إلى "
            f"{multiplier:.3f} (أرضية {config.exec_quality_floor:.2f})"
        )
    return SizingModifier(
        name=SizingModifierName.EXECUTION_QUALITY,
        multiplier=multiplier,
        rationale=rationale,
    )


def _correlation_modifier(context: EvaluationContext, config: RiskConfig) -> SizingModifier:
    """معدل الارتباط — عقوبة لكل تعرض مترابط مفتوح."""
    exposure = context.correlated_exposure
    multiplier = max(_EPSILON, 1.0 - config.correlation_penalty * exposure)
    return SizingModifier(
        name=SizingModifierName.CORRELATION,
        multiplier=multiplier,
        rationale=(
            f"التعرض المترابط المفتوح {exposure} بعقوبة "
            f"{config.correlation_penalty:.2f} لكل تعرض — المضاعف {multiplier:.3f}"
        ),
    )


def _daily_drawdown_modifier(context: EvaluationContext, config: RiskConfig) -> SizingModifier:
    """معدل التدهور اليومي — تخفيض خطي حتى السقف (عنده يشتعل الحاجب 7)."""
    fraction = (
        context.risk_used_today / config.daily_loss_cap if config.daily_loss_cap > 0.0 else 1.0
    )
    multiplier = max(_EPSILON, 1.0 - config.drawdown_slope * fraction)
    return SizingModifier(
        name=SizingModifierName.DAILY_DRAWDOWN,
        multiplier=multiplier,
        rationale=(
            f"المستهلك اليوم {fraction:.1%} من السقف — المضاعف الخطي "
            f"{multiplier:.3f} (المضاعف صفر عند السقف حيث يسبقه الحاجب الصلب 7)"
        ),
    )


def _scenario_quality_modifier() -> SizingModifier:
    """معدل جودة السيناريو — محايد بتأجيل معايرة معلن (§23.2/§19.6)."""
    return SizingModifier(
        name=SizingModifierName.SCENARIO_QUALITY,
        multiplier=1.0,
        rationale=SCENARIO_QUALITY_DEFERRAL,
    )


def risk_budget_for(
    config: RiskConfig,
    context: EvaluationContext,
    decision_time: datetime,
) -> float:
    """الميزانية النقدية للصفقة — سقف الصفقة مقلصًا بسقف الأحداث.

    سقف مخاطرة الأحداث (§23.3) يقلص الميزانية عند وقوع لحظة القرار
    داخل أي نافذة كلي (بأي أهمية — العالية الأثر تحجب الدخول حظرًا
    صلبًا أصلًا برقم 10 فلا تبلغ التحجيم).
    """
    budget = config.per_trade_risk_cap
    moment = decision_time.timestamp()
    in_event_window = any(
        window.event_time.timestamp() - window.pre_event_window_s
        <= moment
        <= window.event_time.timestamp() + window.post_event_window_s
        for window in context.embargo_windows
    )
    if in_event_window:
        budget = min(budget, config.event_risk_cap)
    return budget


def compute_sizing(
    scenario: Scenario,
    stop: StructuralStop,
    *,
    config: RiskConfig,
    context: EvaluationContext,
    market_state: MarketStateSnapshot | None,
    decision_time: datetime,
    portfolio_cap_remaining: float | None = None,
) -> SizingResult:
    """التحجيم الكامل — الأساس فالمعدلات الستة فالسقوف المطلقة.

    :param portfolio_cap_remaining: سعة المحفظة المتبقية (بوحدات الأصل) —
        افتراضيًا كامل سقف المحفظة (أول سياق MVP أحادي الأداة).
    """
    budget = risk_budget_for(config, context, decision_time)
    stop_distance_value = stop.stop_distance
    base_position_size = budget / stop_distance_value

    modifiers = (
        _volatility_modifier(market_state, config),
        _liquidity_modifier(scenario, config),
        _execution_quality_modifier(context, config),
        _correlation_modifier(context, config),
        _daily_drawdown_modifier(context, config),
        _scenario_quality_modifier(),
    )
    final_multiplier = 1.0
    for modifier in modifiers:
        final_multiplier *= modifier.multiplier

    adjusted = base_position_size * final_multiplier
    portfolio_remaining = (
        config.portfolio_position_cap
        if portfolio_cap_remaining is None
        else portfolio_cap_remaining
    )
    hard_cap = min(config.instrument_position_cap, portfolio_remaining)
    if adjusted > config.instrument_position_cap and adjusted > portfolio_remaining:
        capped_by = (
            SizingCapBasis.INSTRUMENT
            if config.instrument_position_cap <= portfolio_remaining
            else SizingCapBasis.PORTFOLIO
        )
    elif adjusted > config.instrument_position_cap:
        capped_by = SizingCapBasis.INSTRUMENT
    elif adjusted > portfolio_remaining:
        capped_by = SizingCapBasis.PORTFOLIO
    else:
        capped_by = SizingCapBasis.NONE
    position_size = min(adjusted, hard_cap)
    resulting_risk_money = position_size * stop_distance_value

    return SizingResult(
        risk_budget=budget,
        stop_distance_value=stop_distance_value,
        base_position_size=base_position_size,
        modifiers=modifiers,
        final_multiplier=final_multiplier,
        instrument_cap=config.instrument_position_cap,
        portfolio_cap_remaining=portfolio_remaining,
        capped_by=capped_by,
        position_size=position_size,
        resulting_risk_money=resulting_risk_money,
    )
