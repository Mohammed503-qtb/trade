"""المدى الحقيقي (TR) وعائلة ATR — عمود تطبيع العتبات في §16.

«التقلب يستخدم لتطبيع كل عتبة تقريبًا»: كل مسافة سعرية يُفضَّل أن تأخذ
صيغة ``threshold = local_volatility × multiplier`` بدل ثابت ticks/pips واحد.
"""

from __future__ import annotations

import numpy as np

from ._internal import FloatArray, as_f64_1d, check_window
from .rolling import rolling_percentile

__all__ = ["atr_percentile", "true_range", "wilder_atr"]


def true_range(highs: FloatArray, lows: FloatArray, closes: FloatArray) -> FloatArray:
    """المدى الحقيقي الكلاسيكي (يشمل فجوات الإغلاق السابق).

    - ``tr[0] = highs[0] − lows[0]`` (لا إغلاق سابق لأول شمعة).
    - ``tr[i] = max(H−L, |H−C_prev|, |L−C_prev|)``.

    nan/inf تمر كما هي (‎np.maximum‎ ينشر nan). لا نظرة مستقبلية:
    خرج الموضع ``i`` يعتمد على ``i`` و``i−1`` حصرًا.

    :raises ValueError: إذا اختلفت أطوال المصفوفات الثلاث.
    """
    h = as_f64_1d(highs, "highs")
    low = as_f64_1d(lows, "lows")
    c = as_f64_1d(closes, "closes")
    n = h.shape[0]
    if not (low.shape[0] == n and c.shape[0] == n):
        raise ValueError(
            f"أطوال المصفوفات يجب أن تتطابق: highs={n}, lows={low.shape[0]}, closes={c.shape[0]}"
        )
    out: FloatArray = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    with np.errstate(invalid="ignore", over="ignore"):
        out[0] = h[0] - low[0]
        if n > 1:
            prev_c = c[:-1]
            body = h[1:] - low[1:]
            gap_high = np.abs(h[1:] - prev_c)
            gap_low = np.abs(low[1:] - prev_c)
            out[1:] = np.maximum(np.maximum(body, gap_high), gap_low)
    return out


def wilder_atr(tr: FloatArray, period: int) -> FloatArray:
    """تمهيد وايلدر RMA لسلسلة المدى الحقيقي.

    - أول قيمة عند الفهرس ``period−1`` = متوسط TR لأول ``period`` عناصر.
    - بعدها استدعاء ذاتي: ``atr[i] = (atr[i−1]×(period−1) + tr[i]) / period``.
    - الدافئ قبل ``period−1`` = ``np.nan``.
    - ``period = 1`` حالة حدية: ATR ≡ TR عنصرًا بعنصر (قيم محدودة).
    - nan في TR تمر كما هي وتنتشر عبر الاستدعاء الذاتي بعد موضعها
      (تمرير بلا انفجار) — المُستدعي مسؤول عن نظافة مدخلاته.

    :raises ValueError: إذا كانت period < 1.
    """
    check_window(period, minimum=1, name="period")
    arr = as_f64_1d(tr, "tr")
    n = arr.shape[0]
    out: FloatArray = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return out
    start = period - 1
    with np.errstate(invalid="ignore", over="ignore"):
        out[start] = float(np.mean(arr[:period]))
        for i in range(start + 1, n):
            out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return out


def atr_percentile(atr_values: FloatArray, window: int) -> FloatArray:
    """مئيني قيمة ATR الحالية ضمن نافذتها الخلفية (§16: "ATR percentile").

    تفويض مباشر إلى :func:`rolling_percentile` بعقوده كاملة (نافذة شاملة
    للقيمة الحالية، دافئ موضعي، استبعاد عناصر nan داخل النافذة). الدافئ
    المزدوج — نمو ATR نفسه ثم اكتمال النافذة — يظهر كنان حتى يتوفر
    عضوان محدودان على الأقل داخل النافذة.

    :raises ValueError: إذا كانت window < 2.
    """
    return rolling_percentile(atr_values, window)
