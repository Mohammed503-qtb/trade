"""سمات الشموع الست (§13.1) — عائلات الأنماط مستعارات لتركيباتها.

كل شمعة تُصنَّف بالسمات الست الحرفية من §13.1: ``body fraction`` و
``wick asymmetry`` و``close location`` و``range percentile`` و
``gap relationship`` و``volume relationship`` — والأنماط المسماة
(الابتلاع/الدبوس/الدوجي...) **مستعارات لتركيبات هذه السمات** لا
كيانات مستقلة (§13.1: "Named patterns are aliases for feature
combinations").

كل دالة هنا: ‎(list[Candle], معاملات نافذة) → FeatureSeries‎ — صرفة
بلا حالة، لا ترى إلا شموع مدخلاتها (لا نظرة مستقبلية §26.3 — النوافذ
خلفية شاملة للقيمة الحالية بعقد quantmath نفسه)، وتفوّض الرياضيات إلى
حزمة quantmath حصرًا (عقد A-02).

عقود مشتركة موروثة (لا تُكرر في كل docstring):

- **الدافئ الموضعي nan**: السمات الفورية الثلاث بلا دافئ (قيمة عند كل
  شمعة من أولها)، وذوات النوافذ/السابق nan حتى اكتمال نافذتها الخلفية.
- **القائمة الفارغة** ⇒ مصفوفة فارغة (بعد تحقق الاتساق في windows).
- التحقق من الاتساق (أداة/إطار/ترتيب) في كل استدعاء عبر :mod:`features.windows`.

قرارات موثقة للقسمة على مدى منعدم (high == low — شمعة مسطحة):

- ``body_fraction`` ⇒ 0.0 (جسم منعدم بحكم التعريف).
- ``wick_asymmetry`` ⇒ 0.0 (لا ظلال أصلًا فلا عدم تناظر).
- ``close_location`` ⇒ 0.5 (الإغلاق في منتصف مدى منعدم — القرار
  المحايد الموثق؛ يلي 0.0 و1.0 لا معنى لهما لشمعة بلا مدى).
"""

from __future__ import annotations

import numpy as np
from quantmath import rolling_mean, rolling_percentile
from schemas import Candle

from .windows import (
    FeatureSeries,
    closes,
    highs,
    lows,
    opens,
    ranges,
    volumes,
)

__all__ = [
    "body_fraction_series",
    "close_location_series",
    "gap_relationship_series",
    "range_percentile_series",
    "volume_relationship_series",
    "wick_asymmetry_series",
]


def body_fraction_series(candles: list[Candle]) -> FeatureSeries:
    """حصة الجسم من المدى (§13.1 ``body fraction``): |close−open| / range.

    [0, 1] — 0 جسم منعدم (دوجي مطلق) و1 شمعة بكامل مداها جسم (ماروبوزو).
    المدى المنعدم ⇒ 0.0 (قرار الوحدة الموثق في رأس الموديول).
    """
    open_arr = opens(candles)
    close_arr = closes(candles)
    range_arr = ranges(candles)
    out = np.zeros(len(candles), dtype=np.float64)
    nonzero = range_arr > 0.0
    out[nonzero] = np.abs(close_arr[nonzero] - open_arr[nonzero]) / range_arr[nonzero]
    return out


def wick_asymmetry_series(candles: list[Candle]) -> FeatureSeries:
    """عدم تناظر الظلال (§13.1 ``wick asymmetry``): (علوي − سفلي) / range.

    [-1, +1] — موجب: ظل علوي أطول (رفض صاعد عند القمة)، سالب: ظل سفلي
    أطول (رفض هابط عند القاع — إشارة الشراء الشموعية الكلاسيكية)، صفر:
    تناظر تام. المدى المنعدم ⇒ 0.0.
    """
    open_arr = opens(candles)
    close_arr = closes(candles)
    high_arr = highs(candles)
    low_arr = lows(candles)
    range_arr = ranges(candles)
    upper = high_arr - np.maximum(open_arr, close_arr)
    lower = np.minimum(open_arr, close_arr) - low_arr
    out = np.zeros(len(candles), dtype=np.float64)
    nonzero = range_arr > 0.0
    out[nonzero] = (upper[nonzero] - lower[nonzero]) / range_arr[nonzero]
    return out


def close_location_series(candles: list[Candle]) -> FeatureSeries:
    """موقع الإغلاق في المدى (§13.1 ``close location``): (close−low)/range.

    [0, 1] — 1 إغلاق عند القمة (قوة شرائية)، 0 إغلاق عند القاع، 0.5
    منتصف. المدى المنعدم ⇒ 0.5 (قرار الوحدة الموثق أعلاه).
    """
    close_arr = closes(candles)
    low_arr = lows(candles)
    range_arr = ranges(candles)
    out = np.full(len(candles), 0.5, dtype=np.float64)
    nonzero = range_arr > 0.0
    out[nonzero] = (close_arr[nonzero] - low_arr[nonzero]) / range_arr[nonzero]
    return out


def range_percentile_series(candles: list[Candle], window: int) -> FeatureSeries:
    """مئيني المدى (§13.1 ``range percentile``) ضمن نافذة خلفية شاملة.

    [0, 1] عبر :func:`quantmath.rolling_percentile` بعقدها الحرفي: نسبة
    أعضاء النافذة الأصغر قطعيًا؛ الدافئ ‎i < window−1‎ ⇒ nan.
    """
    return rolling_percentile(ranges(candles), window)


def gap_relationship_series(candles: list[Candle], window: int) -> FeatureSeries:
    """علاقة الفجوة (§13.1 ``gap relationship``): (open − close السابقة) /
    متوسط مدى النافذة الخلفية.

    بلا وحدات نسبةً للمدى المتوسط: 0 فجوة منعدمة (إغلاق سابق = فتح
    حالي)، موجب فجوة صاعدة، سالب فجوة هابطة، و1.0 فجوة بمقدار مدى
    شمعة كاملة. الموضع الأول nan (لا سابق) والنافذة nan حتى اكتمالها؛
    متوسط مدى منعدم ⇒ nan (لا معنى لنسبة على صفر — حارس قسمة quantmath
    نفسه).
    """
    if len(candles) == 0:
        return ranges(candles)  # مصفوفة فارغة بلا حساب
    open_arr = opens(candles)
    close_arr = closes(candles)
    mean_range = rolling_mean(ranges(candles), window)
    gap = np.full(len(candles), np.nan, dtype=np.float64)
    gap[1:] = open_arr[1:] - close_arr[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = gap / mean_range
    out[mean_range == 0.0] = np.nan
    return out


def volume_relationship_series(candles: list[Candle], window: int) -> FeatureSeries:
    """علاقة الحجم (§13.1 ``volume relationship``): volume / متوسط حجم
    النافذة الخلفية.

    بلا وحدات نسبةً للحجم المتوسط: 1.0 حجم مطابق للمتوسط، >1 توسع
    حجمي (مشاركة غير معتادة)، <1 انكماش. الدافئ nan حتى اكتمال
    النافذة؛ متوسط حجم منعدم ⇒ nan.
    """
    volume_arr = volumes(candles)
    mean_volume = rolling_mean(volume_arr, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = volume_arr / mean_volume
    out[mean_volume == 0.0] = np.nan
    return out
