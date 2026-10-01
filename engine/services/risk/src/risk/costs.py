"""نموذج التكاليف (§25.1-2) — التحلل السداسي وR الصافية المقدرة.

«Backtests and live analysis must include» التكاليف كلها — والتقدير هنا
قبل الصفقة بوحدات السعر لكل وحدة أصل ذهابًا وإيابًا، بتحلل §25.2
الحرفي:

    Gross Price Edge − Spread − Commission − Slippage − Funding/Financing
    − Other Execution Costs = Net Trading Edge

الأنماط الثلاثة (§25.1): مضاعف النمط يقيّس التكاليف السوقية (الفاتحة
والانزلاق والاختيار السلبي وأثر التعبئة الجزئية) ويترك الرسوم
التعاقدية (العمولة والتمويل) كما هي — الرسوم عقد لا ظرف سوق.
REALISTIC وحده نمط القبول: «A strategy cannot pass production gates
based only on optimistic costs».
"""

from __future__ import annotations

from schemas import (
    CostBreakdown,
    CostMode,
    Direction,
    RewardRiskEstimate,
    StructuralStop,
)

from .parameter_sets import RiskConfig

__all__ = [
    "estimate_reward_risk",
    "round_trip_cost",
]


def round_trip_cost(config: RiskConfig, cost_mode: CostMode) -> float:
    """إجمالي التكاليف المتوقعة ذهابًا وإيابًا لكل وحدة أصل (§25.2).

    مدخل الحاجب الصلب رقم 12 (المكافأة المتبقية بعد التكاليف) —
    بالمصطلحات الأربعة الخمسة مجمعة (الرسوم والتمويل وسواها).
    """
    multiplier = config.mode_multipliers[cost_mode]
    return (
        config.spread_estimate * multiplier
        + config.commission_per_unit
        + config.slippage_estimate * multiplier
        + config.funding_estimate
        + config.adverse_selection_estimate * multiplier
        + config.partial_fill_estimate * multiplier
    )


def estimate_reward_risk(
    stop: StructuralStop,
    *,
    target_level: float,
    direction: Direction,
    config: RiskConfig,
    cost_mode: CostMode,
) -> RewardRiskEstimate:
    """تقدير المكافأة/المخاطرة (§23.5) بتحلل §25.2 — حساب واحد لا حسابان.

    :param stop: الوقف المحسوب — مرجع الدخول ووحدة R.
    :param target_level: مستوى الهدف المعتمد (أقرب هدف §10.5).
    :param direction: اتجاه السيناريو — إشارة الحافة.
    :param cost_mode: نمط التكلفة — القبول بـREALISTIC وحده (§25.1).
    """
    multiplier = config.mode_multipliers[cost_mode]
    direction_sign = 1.0 if direction is Direction.LONG else -1.0

    gross_target_distance = max(0.0, (target_level - stop.entry_reference) * direction_sign)
    spread_cost = config.spread_estimate * multiplier
    slippage_cost = config.slippage_estimate * multiplier
    commission_fee = config.commission_per_unit
    funding = config.funding_estimate
    adverse_selection = config.adverse_selection_estimate * multiplier
    partial_fill = config.partial_fill_estimate * multiplier
    other_execution_costs = adverse_selection + partial_fill

    breakdown = CostBreakdown(
        cost_mode=cost_mode,
        gross_price_edge=gross_target_distance,
        spread=spread_cost,
        commission=commission_fee,
        slippage=slippage_cost,
        funding_financing=funding,
        other_execution_costs=other_execution_costs,
        net_trading_edge=(
            gross_target_distance
            - (spread_cost + commission_fee + slippage_cost + funding + other_execution_costs)
        ),
    )

    stop_distance = stop.stop_distance
    return RewardRiskEstimate(
        cost_mode=cost_mode,
        target_level=target_level,
        entry_reference=stop.entry_reference,
        stop_distance=stop_distance,
        gross_target_distance=gross_target_distance,
        expected_slippage=slippage_cost,
        commission_fee=commission_fee,
        spread_cost=spread_cost,
        expected_adverse_selection=adverse_selection,
        partial_fill_risk=partial_fill,
        estimated_net_r=breakdown.net_trading_edge / stop_distance,
        gross_r=gross_target_distance / stop_distance,
        breakdown=breakdown,
    )
