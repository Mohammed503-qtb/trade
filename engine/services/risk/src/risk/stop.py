"""الوقف البنيوي (§23.4) — «بنية + عازلة تقلب + عدم يقين تنفيذ».

«Stops are defined from market structure and volatility, not from a
universal number of points» — المستوى البنيوي وعازلة التقلب تحملهما
قاعدة إبطال السيناريو (§18.5، بناها المُقترِح من مضاعف ATR)، وعدم
اليقين التنفيذي يُشتق هنا من كمون التنفيذ المتوقع ومعدل التقلب
الزمني (ADR-026): (الكمون بالثواني) × (ATR / ثواني الشمعة) × مضاعف.

مرجع الدخول المخطط: الحافة المحافظة لمنطقة الدخول — أبعد حافة عن
الوقف — فتكون 1R المحسوبة أسوأ حالة تعبئة (التحجيم لا يتفاءل).
"""

from __future__ import annotations

from schemas import Direction, Scenario, StructuralStop

from .parameter_sets import RiskConfig

__all__ = ["compute_structural_stop"]


def compute_structural_stop(
    scenario: Scenario,
    *,
    atr: float,
    config: RiskConfig,
    latency_ms: float,
) -> StructuralStop | None:
    """حساب الوقف البنيوي الثلاثي — None عند استحالة الهندسة الصالحة.

    :param scenario: السيناريو بقاعدة إبطاله (المستوى والعازلة).
    :param atr: ATR شمعة القرار — مقياس عدم اليقين والعتبات.
    :param config: إصدار معاملات المخاطرة.
    :param latency_ms: كمون التنفيذ المتوقع (مللي ثانية) — مدخل عدم
        اليقين؛ غياب تقدير (صفر) يعني عدم يقين صفريًا بتوثيق صريح.
    :returns: الوقف كامل القياس، أو None حين تفقد الهندسة صلاحيتها
        (مستوى غير موجب أو وقف غير موجب أو مسافة غير موجبة) —
        والحاجب الصلب رقم 8 يلتقط اللاشيء.
    """
    if atr <= 0.0:
        return None
    rule = scenario.invalidation
    if rule.structural_level <= 0.0:
        return None

    latency_seconds = max(0.0, latency_ms) / 1000.0
    volatility_rate = atr / config.execution_bar_seconds  # سعر/ثانية
    execution_uncertainty = (
        latency_seconds * volatility_rate * config.execution_uncertainty_multiplier
    )

    zone = scenario.entry_zone
    if scenario.direction is Direction.LONG:
        # إبطاد LONG تحت البنية؛ المرجع المحافظ = الحافة العليا للمنطقة.
        stop_price = rule.structural_level - (rule.volatility_buffer + execution_uncertainty)
        entry_reference = zone.price_high
        if stop_price <= 0.0 or entry_reference <= stop_price:
            return None
    else:
        # إبطال SHORT فوق البنية؛ المرجع المحافظ = الحافة الدنيا.
        stop_price = rule.structural_level + (rule.volatility_buffer + execution_uncertainty)
        entry_reference = zone.price_low
        if stop_price <= 0.0 or entry_reference >= stop_price:
            return None

    stop_distance = abs(entry_reference - stop_price)
    if stop_distance <= 0.0:
        return None

    return StructuralStop(
        structural_level=rule.structural_level,
        volatility_buffer=rule.volatility_buffer,
        execution_uncertainty=execution_uncertainty,
        stop_price=stop_price,
        entry_reference=entry_reference,
        stop_distance=stop_distance,
        accept_through=rule.accept_through,
        atr=atr,
        stop_distance_atr=stop_distance / atr,
    )
