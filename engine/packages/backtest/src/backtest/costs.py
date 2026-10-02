"""التكاليف المحققة (§25.2 على تعبئات وقعت) — التحلل السداسي بلا ازدواج.

عقود المرحلة 8 (``schemas.risk.CostBreakdown``) تقدّر التكلفة **قبل**
الصفقة لقرار القبول (§23.5)؛ هذا الموديول يحقق التحلل نفسه **بعد**
التنفيذ المحاكى: من مستويات الدخول/المخرج الفعلية وجدول التكلفة
الإعدادي للنمط — بوحدات السعر لكل وحدة أصل، ذهابًا وإيابًا.

قواعد العد الموثقة (ADR-027):

- **التعبئة عند مستويات نظيفة** (حافة المنطقة/الوقف/الهدف/إغلاق
  الشمعة) — والانزلاق والفاتحة والعمولة **تكلفة محققة** تُحتسب مرة
  واحدة هنا (لا انزلاق مضاعف داخل أسعار التعبئة).
- ``funding_financing`` صفر موثق في MVP (سبوت بلا تمويل — الجدول
  يحمل المعامل ليومض حسابه عند تفعيله).
- ``other_execution_costs`` صفر موثق (الاختيار السلبي المحقق قياسه
  بعد MVP؛ التقديري يعيش في §23.5) — لا اختلاق قياس لم يقع.
- REALISTIC وحده نمط القبول (§25.1) — OPTIMISTIC تشخيص وSTRESS متانة.
"""

from __future__ import annotations

from schemas import CostMode, Direction, RealizedCosts

from .parameter_sets import BacktestConfig

__all__ = ["realize_costs"]


def realize_costs(
    *,
    side: Direction,
    entry_price: float,
    exit_price: float | None,
    config: BacktestConfig,
    holding_s: float = 0.0,
    mode: CostMode = CostMode.REALISTIC,
) -> RealizedCosts:
    """تحلل §25.2 المحقق لذهاب-وإياب لوحدة أصل واحدة.

    :param exit_price: ``None`` غير قانوني هنا — التكاليف المحققة
        تحتاج مخرجًا وقع (المفتوح عند نهاية البيانات بلا تكاليف).
    """
    if exit_price is None:
        raise ValueError("تحلل التكلفة المحقق يتطلب مخرجًا وقع — لا تكاليف لغير منتهٍ")
    schedule = config.schedule_for(mode)

    direction_sign = 1.0 if side is Direction.LONG else -1.0
    gross_realized_edge = (exit_price - entry_price) * direction_sign

    spread = 2.0 * schedule.spread_per_side
    slippage = 2.0 * schedule.slippage_per_side
    commission = schedule.commission_bps_per_side * 1e-4 * (entry_price + exit_price)
    funding = schedule.funding_per_holding_h * max(0.0, holding_s) / 3600.0
    other = 0.0  # موثق صفر MVP (انظر وثقة الموديول)

    total = spread + commission + slippage + funding + other
    return RealizedCosts(
        cost_mode=mode,
        gross_realized_edge=gross_realized_edge,
        spread=spread,
        commission=commission,
        slippage=slippage,
        funding_financing=funding,
        other_execution_costs=other,
        net_realized_edge=gross_realized_edge - total,
    )
