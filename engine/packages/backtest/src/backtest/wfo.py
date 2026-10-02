"""أدوات التدحرج الأمامي (§39.3) — طيات مرتبة زمنيًا بحجز بين المتجاورات.

«2,000 eligible historical candidates → TRAIN / 500 → VALIDATION /
500 → OUT-OF-SAMPLE / roll forward by 500» — والقسمة مرتبة زمنيًا مع
«حجز ≥ أقصى أفق تقييم للاستراتيجية بين الطيات المتجاورة».

إنفاذ الحجز **زمنيًا لا عدديًا**: بعد آخر مرشح تدريب لا يدخل التحققَ
إلا أولُ مرشح لحظته ≥ لحظة آخر تدريب + الحجز (وبعده بين التحقق
والخارج) — فلا تتسرب أفقية التقييم بين الطيات مهما تزاحمت المرشحون
(«no calibration on the evaluation fold» §26.3-6).

«The exact sample count can be increased…; it is never reduced merely
to pass a gate» — البروتوكول الافتراضي هو بروتوكول البحث كاملًا؛
عند نقص المرشحين يرفض المقسّم بصوت عالٍ (خطأ عربي يسرد المتطلبات)
ولا يُختلق تقسيم أدعى أنه بحث.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from datetime import datetime, timedelta

from schemas import (
    WFOProtocolConfig,
    WFOReport,
    WFORole,
    WFOSegment,
    WFOWindow,
)

__all__ = [
    "WFOProtocolError",
    "research_protocol",
    "split_windows",
]


class WFOProtocolError(ValueError):
    """خطأ بروتوكول التدحرج — نقص مرشحين أو بروتوكول متهالك."""


def research_protocol(*, embargo_s: float) -> WFOProtocolConfig:
    """بروتوكول البحث الافتراضي (§39.3 حرفيًا) — 2000/500/500 خطوة 500.

    :param embargo_s: الحجز الزمني — ≥ أقصى أفق تقييم للاستراتيجية
        (مسؤولية المستدعي إعلانه؛ المقسّم لا يعرف أفق الاستراتيجية).
    """
    return WFOProtocolConfig(
        protocol_name="RESEARCH_2000_500_500",
        train_candidates=2000,
        validation_candidates=500,
        oos_candidates=500,
        step_candidates=500,
        embargo_s=embargo_s,
    )


def split_windows(times: Sequence[datetime], protocol: WFOProtocolConfig) -> WFOReport:
    """تقسيم المرشحين المرتبين زمنيًا إلى نوافذ تدحرج بطياتها الثلاث.

    :param times: لحظات المرشحين مرتبة تصاعديًا (يتحقق المقسّم).
    :raises WFOProtocolError: أزمنة غير مرتبة، أو مرشحون أقل من نافذة
        واحدة كاملة (المتطلبات تُسرد — لا تقسيم منقوص يدّعي البحث).
    """
    if len(times) < 2:
        raise WFOProtocolError("التدحرج يحتاج مرشحين اثنين على الأقل — قائمة أقصر")
    for previous, current in itertools.pairwise(times):
        if current < previous:
            raise WFOProtocolError(
                f"لحظات المرشحين غير مرتبة: {previous} ثم {current} — §39.3 زمنية-الترتيب حصرًا"
            )

    embargo = timedelta(seconds=protocol.embargo_s)
    windows: list[WFOWindow] = []
    embargoed_total = 0
    window_index = 0
    start = 0

    while True:
        train_start = start
        train_end = train_start + protocol.train_candidates
        if train_end > len(times):
            break
        val_start = _first_at_or_after(times, train_end, times[train_end - 1] + embargo)
        val_end = val_start + protocol.validation_candidates
        if val_end > len(times):
            break
        oos_start = _first_at_or_after(times, val_end, times[val_end - 1] + embargo)
        oos_end = oos_start + protocol.oos_candidates
        if oos_end > len(times):
            break

        embargo_after_train = (times[val_start] - times[train_end - 1]).total_seconds()
        embargo_after_validation = (times[oos_start] - times[val_end - 1]).total_seconds()
        embargoed_total += (val_start - train_end) + (oos_start - val_end)

        windows.append(
            WFOWindow(
                window_index=window_index,
                segments=(
                    WFOSegment(
                        role=WFORole.TRAIN, first_index=train_start, last_index=train_end - 1
                    ),
                    WFOSegment(
                        role=WFORole.VALIDATION, first_index=val_start, last_index=val_end - 1
                    ),
                    WFOSegment(
                        role=WFORole.OUT_OF_SAMPLE, first_index=oos_start, last_index=oos_end - 1
                    ),
                ),
                embargo_boundaries_s=(embargo_after_train, embargo_after_validation),
            )
        )
        window_index += 1
        start += protocol.step_candidates

    if not windows:
        needed = (
            protocol.train_candidates + protocol.validation_candidates + protocol.oos_candidates
        )
        raise WFOProtocolError(
            f"المرشحون ({len(times)}) لا يكملون نافذة تدحرج واحدة للبروتوكول "
            f"{protocol.protocol_name}: يتطلب {needed} مرشحًا للطيات وحجزًا زمنيًا "
            f"({protocol.embargo_s} ثانية) بينها — «لا تُقلص الأعداد لمجرد عبور "
            "بوابة» (§39.3)"
        )

    return WFOReport(
        protocol=protocol,
        candidates_count=len(times),
        windows=tuple(windows),
        embargoed_count=embargoed_total,
        notes=(
            "الحجز زمني لا عددي: لا يدخل التحققَ إلا ما تجاوز لحظة آخر تدريب "
            "بالحجز كاملًا (وبعده بين التحقق والخارج) — no calibration on the "
            "evaluation fold (§26.3-6).",
            "الطيات داخل النافذة متجاورة بلا تقاطع، والنوافذ تتدحرج بخطوة "
            f"{protocol.step_candidates} مرشحًا — الترتيب زمني صارم (§39.3).",
        ),
    )


def _first_at_or_after(times: Sequence[datetime], bound_index: int, earliest: datetime) -> int:
    """أول موضع ≥ ``bound_index`` تبلغ لحظته ``earliest`` (بحث خطي حتمي)."""
    index = bound_index
    while index < len(times) and times[index] < earliest:
        index += 1
    return index
