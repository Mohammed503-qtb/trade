"""مقاييس التقلب المرجعية لـ§16.

التقلب المحقق، مئيني توسع المدى، تقلب-التقلب، حجم الفجوة/الصدمة
المعيار بالـATR، تقلب زمن الاحتفاظ المتوقع، ونسبة السبر إلى المدى.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from ._internal import FloatArray, as_f64_1d
from .rolling import rolling_mean, rolling_percentile, rolling_std

__all__ = [
    "expected_holding_vol",
    "gap_shock",
    "range_expansion_percentile",
    "realized_volatility",
    "spread_to_range",
    "vol_of_vol",
]

#: عتبة حارس القسمة في vol_of_vol: |mean| دونها يُعد صفرًا (nan بدل inf).
ZERO_MEAN_EPS: Final[float] = 1e-12


def realized_volatility(log_returns: FloatArray, window: int) -> FloatArray:
    """التقلب المحقق: الانحراف المعياري المتدحرج (عينة ``ddof=1``)
    للعوائد اللوغاريتمية.

    النسبة «لكل شمعة» — لا تحجيم زمني هنا إطلاقًا؛ التحجيم مسؤولية
    :func:`expected_holding_vol`. عقد الدافئ وnan كما في :func:`rolling_std`.

    :raises ValueError: إذا كانت window < 2.
    """
    return rolling_std(log_returns, window, ddof=1)


def range_expansion_percentile(ranges: FloatArray, window: int) -> FloatArray:
    """مئيني المدى الحالي ضمن نوافذه الخلفية (توسع/انكماش المدى).

    ``1.0`` = المدى الحالي يعلو كل نافذته قطعيًا (توسع كامل)؛
    ``0.0`` = لا يعلو شيئًا (انكماش أو تساوٍ). تفويض كامل إلى
    :func:`rolling_percentile` بعقوده الموثقة.

    :raises ValueError: إذا كانت window < 2.
    """
    return rolling_percentile(ranges, window)


def vol_of_vol(vol_series: FloatArray, window: int) -> FloatArray:
    """معامل تباين سلسلة التقلب: ``std / |mean|`` على النافذة الخلفية الشاملة.

    حارس القسمة: متوسط النافذة شبه صفري (``|mean| < 1e-12``) ⇒ nan
    بدل inf. الدافئ nan حتى اكتمال النافذة (متوسط وانحراف معًا)؛
    وسلسلة ثابتة تمامًا ⇒ 0.0.

    :raises ValueError: إذا كانت window < 2 (عبر rolling_std).
    """
    means = rolling_mean(vol_series, window)
    stds = rolling_std(vol_series, window, ddof=1)
    abs_means = np.abs(means)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = stds / abs_means
    out[abs_means < ZERO_MEAN_EPS] = np.nan
    return out


def gap_shock(opens: FloatArray, prev_closes: FloatArray, atr: FloatArray) -> FloatArray:
    """حجم الفجوة/الصدمة الأخيرة معياريةً بالـATR (§16: "recent gap/shock size").

    ``gap[i] = |open[i] − close[i−1]| / atr[i]`` — و``prev_closes`` هي
    سلسلة الإغلاقات المحاذية للشموع (الدالة تنظر بنفسها إلى ``i−1``).
    أول عنصر nan دائمًا (لا سابق). عقد الحواف: ``atr[i] == 0`` مع فجوة
    موجبة ⇒ inf؛ مع فجوة صفرية ⇒ nan (تمرير بلا انفجار). nan/inf تمر
    كما هي.

    :raises ValueError: إذا اختلفت أطوال المصفوفات الثلاث.
    """
    o = as_f64_1d(opens, "opens")
    c = as_f64_1d(prev_closes, "prev_closes")
    a = as_f64_1d(atr, "atr")
    n = o.shape[0]
    if not (c.shape[0] == n and a.shape[0] == n):
        raise ValueError(
            f"أطوال المصفوفات يجب أن تتطابق: opens={n}, prev_closes={c.shape[0]}, atr={a.shape[0]}"
        )
    out: FloatArray = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return out
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        gaps = np.abs(o[1:] - c[:-1])
        out[1:] = gaps / a[1:]
    return out


def expected_holding_vol(per_bar_vol: float, horizon_bars: int) -> float:
    """تقلب زمن الاحتفاظ المتوقع: تحجيم جذر الزمن (§16).

    ``per_bar_vol × sqrt(horizon_bars)`` حيث horizon عدد الأشرطة المتوقع
    للاحتفاظ بالوضعية. ``horizon_bars`` عدد صحيح موجب (≥ 1) وإلا
    ValueError. القيم غير المحدودة تمر كما هي (nan ⇒ nan، inf ⇒ inf).

    :raises ValueError: إذا لم يكن horizon_bars عددًا صحيحًا موجبًا.
    """
    if horizon_bars < 1 or horizon_bars != int(horizon_bars):
        raise ValueError(f"horizon_bars يجب أن يكون عددًا صحيحًا موجبًا (≥ 1)؛ وُجد {horizon_bars!r}")
    return float(per_bar_vol * math.sqrt(horizon_bars))


def spread_to_range(bodies: FloatArray, ranges: FloatArray) -> FloatArray:
    """نسبة |جسم الشمعة| إلى مداها الكلي (§16: "spread-to-range ratio").

    ``|body[i]| / range[i]`` — لشمعة سليمة (‎|body| ≤ range‎) القيمة
    ∈ [0, 1]: ``1.0`` جسم كامل، ``0.0`` دوجي.

    **العقد الموثق**: ``range == 0`` (شمعة مسطحة) ⇒ ``0.0`` دائمًا —
    حتى لو كان الجسم nan (لا مدى يتسع لأي سبر). nan في المدى ⇒ nan؛
    والمدخلات غير المتسقة (‎|body| > range‎ أو مدى سالب) تمر كما هي
    بلا قصّ ولا تقييد.

    :raises ValueError: إذا اختلف طول المصفوفتين.
    """
    b = as_f64_1d(bodies, "bodies")
    r = as_f64_1d(ranges, "ranges")
    if b.shape[0] != r.shape[0]:
        raise ValueError(f"أطوال المصفوفات يجب أن تتطابق: bodies={b.shape[0]}, ranges={r.shape[0]}")
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out = np.abs(b) / r
    out[r == 0.0] = 0.0
    return out
