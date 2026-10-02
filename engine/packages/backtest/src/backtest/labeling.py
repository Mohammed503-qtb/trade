"""محرك الوسم (§30) — الحالات الخمس بعد انقضاء الأفق حصرًا.

«Each candidate scenario receives a label only after its defined
evaluation horizon ends» — الترجمة من ميكانيكا المخرج إلى الدلالة:

====================  =====================================
مخرج المحاكي          الوسم §30
====================  =====================================
UNFILLED              NOT_EXECUTABLE (لم تقم صفقة أصلاً)
TARGET                TARGET_FIRST (الهدف قبل الإبطال)
STOP                  INVALIDATION_FIRST (الإبطال قبل الهدف)
TIMEOUT / ENTRY_EXPIRY
                      net > 0 ⇒ TIMEOUT_WITH_PROFIT
                      net ≤ 0 ⇒ TIMEOUT_WITH_LOSS
بلا مخرج (بيانات أقصر)
                      بلا وسم — «الوسم بعد انقضاء الأفق» فلا
                      يُختلق حكم لم يقع (يُحصى في التقرير)
====================  =====================================

«Net target evaluation includes realistic costs» — عتبة الربح/الخسارة
عند المهلة هي الصافي المحقق بعد تكاليف REALISTIC لا الإجمالي.
"""

from __future__ import annotations

from schemas import ExitReason, LabelState

__all__ = ["label_for"]


def label_for(
    *, exit_reason: ExitReason | None, net_realized_edge: float | None
) -> LabelState | None:
    """وسم §30 من مخرج المحاكي وصافيه المحقق.

    :param exit_reason: مخرج المحاكي — ``None`` يعني بقاء النية غير
        محسومة حتى نهاية البيانات (لا وسم — §30).
    :param net_realized_edge: الصافي المحقق بعد تكاليف REALISTIC لوحدة
        أصل (مطلوب عند TIMEOUT/ENTRY_EXPIRY لعتبة الربح).
    """
    if exit_reason is None:
        return None
    if exit_reason is ExitReason.UNFILLED:
        return LabelState.NOT_EXECUTABLE
    if exit_reason is ExitReason.TARGET:
        return LabelState.TARGET_FIRST
    if exit_reason is ExitReason.STOP:
        return LabelState.INVALIDATION_FIRST
    # TIMEOUT / ENTRY_EXPIRY — عتبة الربح صافيةً بعد التكاليف
    if net_realized_edge is None:
        raise ValueError(
            f"وسم المهلة {exit_reason} يتطلب الصافي المحقق — لا عتبة ربح بلا تكاليف (§30)"
        )
    if net_realized_edge > 0.0:
        return LabelState.TIMEOUT_WITH_PROFIT
    return LabelState.TIMEOUT_WITH_LOSS
