"""سمات التقلب والمدى والكفاءة والحجم (§16 + §9.3 تحضيرًا لـ2-d).

كل دالة هنا: ‎(list[Candle], معاملات نافذة) → FeatureSeries‎ — صرفة بلا حالة،
لا ترى إلا شموع مدخلاتها (لا نظرة مستقبلية §26.3)، وتفوّض كل الرياضيات إلى
حزمة quantmath حصرًا (عقد A-02: مسار شيفرة واحد للحي والإعادة؛ هذه الطبقة
جسر منظم لا تحسب بنفسها إلا ما لا يوفره quantmath).

عقود مشتركة موروثة من quantmath (لا تُكرر في كل docstring):

- **الدافئ الموضعي nan**: المواضع التي لم تكتمل نافذتها بنيويًا ⇒ nan.
- **استبعاد nan داخل النافذة** من البسط والمقام معًا (يؤخر القيمة الأولى
  لسلاسل ذات دافئ مزدوج لكنه لا يعطلها) — عقد rolling_* الموثق.
- **القائمة الفارغة** ⇒ مصفوفة فارغة (بعد تحقق الاتساق).
- التحقق من الاتساق (أداة/إطار/ترتيب) في كل استدعاء عبر :mod:`features.windows`.
"""

from __future__ import annotations

import numpy as np
from quantmath import (
    atr_percentile,
    expected_holding_vol,
    gap_shock,
    range_expansion_percentile,
    realized_volatility,
    rolling_mean,
    spread_to_range,
    true_range,
    vol_of_vol,
    wilder_atr,
)
from schemas import Candle

from .windows import (
    FeatureSeries,
    bodies,
    closes,
    highs,
    log_returns,
    lows,
    opens,
    ranges,
    volumes,
)

__all__ = [
    "atr_pct_series",
    "atr_series",
    "directional_efficiency_series",
    "expected_holding_vol_series",
    "gap_shock_series",
    "normalized_range_series",
    "range_expansion_series",
    "realized_vol_series",
    "spread_to_range_series",
    "vol_of_vol_series",
    "volume_concentration_series",
]


def atr_series(candles: list[Candle], period: int = 14) -> FeatureSeries:
    """سلسلة ATR (وايلدر RMA) من المدى الحقيقي TR بفجوات الإغلاق السابق.

    جسر مباشر: ‎wilder_atr(true_range(...))‎ — أول قيمة عند الفهرس ``period−1``
    (بذرة متوسط)، الدافئ قبلها nan.
    """
    return wilder_atr(true_range(highs(candles), lows(candles), closes(candles)), period)


def atr_pct_series(
    candles: list[Candle], atr_period: int = 14, pct_window: int = 100
) -> FeatureSeries:
    """مئيني ATR الحالي ضمن نافذته الخلفية (§16: "ATR percentile") ∈ [0, 1].

    سلسلة ATR ثم :func:`quantmath.atr_percentile` — الدافئ المزدوج (نمو ATR
    ثم اكتمال نافذة المئيني) يُحل بعقد الاستبعاد: أول قيمة عند أول فهرس
    تكتمل فيه شروط المئيني بشرط أن القيمة الحالية نفسها محدودة.
    """
    return atr_percentile(atr_series(candles, atr_period), pct_window)


def realized_vol_series(candles: list[Candle], window: int = 20) -> FeatureSeries:
    """التقلب المحقق: انحراف معياري متدحرج (عينة ddof=1) للعوائد اللوغاريتمية.

    النسبة لكل شمعة بلا تحجيم زمني — التحجيم مسؤولية
    :func:`expected_holding_vol_series`.
    """
    return realized_volatility(log_returns(candles), window)


def range_expansion_series(candles: list[Candle], window: int = 100) -> FeatureSeries:
    """مئيني توسع المدى: موقع مدى الشمعة الحالية ضمن نافذته الخلفية ∈ [0, 1].

    ``1.0`` توسع كامل (المدى يعلو كل نافذته)؛ ``0.0`` انكماش أو تساوٍ.
    """
    return range_expansion_percentile(ranges(candles), window)


def vol_of_vol_series(
    candles: list[Candle], rv_window: int = 20, vov_window: int = 50
) -> FeatureSeries:
    """تقلب-التقلب: معامل تباين سلسلة التقلب المحقق على نافذة خلفية.

    سلسلتان متتاليتان: realized_vol ثم :func:`quantmath.vol_of_vol` — أول قيمة
    عند اكتمال دافئ السلسلتين معًا.
    """
    return vol_of_vol(realized_vol_series(candles, rv_window), vov_window)


def gap_shock_series(candles: list[Candle], atr_period: int = 14) -> FeatureSeries:
    """حجم الفجوة/الصدمة الأخيرة معياريةً بالـATR (§16: "recent gap/shock size").

    ‎gap[i] = |open[i] − close[i−1]| / atr[i]‎ — أول عنصر nan دائمًا (لا سابق)،
    وعقود الحواف (atr=0 مع فجوة ⇒ inf) كما في quantmath.
    """
    return gap_shock(opens(candles), closes(candles), atr_series(candles, atr_period))


def spread_to_range_series(candles: list[Candle]) -> FeatureSeries:
    """نسبة |جسم الشمعة| إلى مداها الكلي ∈ [0, 1] لشمعة سليمة.

    جسر مباشر إلى :func:`quantmath.spread_to_range` بعقده (مدى صفري ⇒ 0.0).
    """
    return spread_to_range(bodies(candles), ranges(candles))


def expected_holding_vol_series(
    candles: list[Candle], horizon_bars: int, rv_window: int = 20
) -> FeatureSeries:
    """تقلب زمن الاحتفاظ المتوقع عند كل موضع: تحجيم جذر الزمن للعوائد.

    ‎ehv[i] = realized_vol[i] × sqrt(horizon_bars)‎ عنصرًا بعنصر عبر
    :func:`quantmath.expected_holding_vol` (السكالر) — نفس العقد حرفيًا
    (horizon صحيح ≥ 1 وإلا ValueError؛ nan/inf تمر كما هي).
    """
    rv = realized_vol_series(candles, rv_window)
    out = np.empty(rv.shape[0], dtype=np.float64)
    for i in range(rv.shape[0]):
        out[i] = expected_holding_vol(float(rv[i]), horizon_bars)
    return out


def normalized_range_series(candles: list[Candle], atr_period: int = 14) -> FeatureSeries:
    """المدى معياريًا بالـATR: ‎range[i] / atr[i]‎ (سمة نظام §9.3 تحضيرًا لـ2-d).

    قيم تُقارن عبر الزمن والأدوات بلا وحدات؛ الحواف موروثة من القسمة:
    ‎atr == 0‎ مع مدى موجب ⇒ inf؛ ومدى صفري مع atr صفري ⇒ nan (تمرير بلا انفجار).
    """
    atr = atr_series(candles, atr_period)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        return ranges(candles) / atr


def directional_efficiency_series(candles: list[Candle], window: int = 20) -> FeatureSeries:
    """كفاءة كوفمان الاتجاهية ER ضمن النافذة الخلفية ∈ [0, 1] (§9.3 لـ2-d).

    ‎ER[i] = |close[i] − close[i−window]| / Σ_{j=i−window+1..i} |close[j] − close[j−1]|‎

    - البسط صافي الإزاحة على window تزايد؛ المقام إجمالي المسافة المقطوعة —
      فـ1.0 حركة اتجاهية نقية و0.0 ذهابٌ وإياب تام (عدم مساواة المثلث يضمن ≤ 1).
    - **الدافئ**: يحتاج window **تزايدات** أي window+1 إغلاقًا ⇒ المواضع
      ``i < window`` كلها nan.
    - **حارس القسمة**: مقام صفري (نافذة بلا أي حركة) ⇒ nan — كفاءة حركة
      معدومة غير معرفة.
    """
    if window < 1:
        raise ValueError(f"window يجب أن يكون ≥ 1؛ وُجد {window}")
    c = closes(candles)
    n = c.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(window, n):
        segment = c[i - window : i + 1]
        denominator = float(np.abs(np.diff(segment)).sum())
        if denominator == 0.0:
            continue
        out[i] = abs(float(c[i] - c[i - window])) / denominator
    return out


def volume_concentration_series(candles: list[Candle], window: int = 20) -> FeatureSeries:
    """تركيز الحجم: حجم الشمعة الحادية ÷ متوسط حجم نافذتها الخلفية (§9.3 لـ2-d).

    ``1.0`` حجم عادي؛ ‎> 1`` تركيز فوق المألوف النافذي؛ ``0.0`` شمعة صامتة
    ضمن نافذة ناطقة. **حارس القسمة**: نافذة صامتة كليًا (متوسط صفري) ⇒ nan.
    """
    if window < 1:
        raise ValueError(f"window يجب أن يكون ≥ 1؛ وُجد {window}")
    v = volumes(candles)
    means = rolling_mean(v, window)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out = v / means
    out[means == 0.0] = np.nan
    return out
