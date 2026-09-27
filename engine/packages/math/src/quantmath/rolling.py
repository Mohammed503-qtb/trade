"""إحصاءات النوافذ الخلفية: مئيني متدحرج، z-score، متوسط، انحراف معياري.

العقد المشترك لكل دوال هذا الموديول (§16 و§26.3):

- **لا نظرة مستقبلية إطلاقًا**: القيمة عند الفهرس ``i`` تُحتسب من
  المدخلات ``[0..i]`` حصرًا؛ كل النوافذ خلفية **شاملة للقيمة الحالية**.
- **الدافئ الموضعي**: المواضع ``i < window - 1`` ⇒ ``np.nan``
  (لم تكتمل النافذة بنيويًا بعدُ)، بمعزل عن محتوى القيم.
- **عقد nan**: القيمة الحالية nan ⇒ الخرج عند موضعها nan. عناصر nan
  الأخرى داخل النافذة تُستبعد من الإحصاء (من البسط والمقام معًا)
  لتظل الدوال صالحة لسلاسل ذات دافئ (كعوائد لوغاريتمية أو ATR غير
  مكتمل). أما ``inf`` فلا تُستبعد — تمر عبر الحساب كما هي دون انفجار.
- **float64 حصرًا** و**حتمية صرفة**: نفس المصفوفة ⇒ نفس المخرجات
  بايت-بايت؛ كل إحصاء يُحتسب لكل نافذة على حدة (بدون مجاميع جارية)
  ليطابق مرجع ``np.mean``/``np.std`` حرفيًا.
"""

from __future__ import annotations

import numpy as np

from ._internal import FloatArray, as_f64_1d, check_window

__all__ = ["rolling_mean", "rolling_percentile", "rolling_std", "rolling_zscore"]


def rolling_mean(values: FloatArray, window: int) -> FloatArray:
    """المتوسط المتدحرج على نافذة خلفية شاملة للقيمة الحالية.

    عناصر nan داخل النافذة تُستبعد (انظر عقد الموديول)؛ ولا يبقى خرج
    nan بعد الدافئ إلا إذا كانت القيمة الحالية نفسها nan.

    :raises ValueError: إذا كانت window < 1.
    """
    check_window(window, minimum=1)
    arr = as_f64_1d(values, "values")
    n = arr.shape[0]
    out: FloatArray = np.full(n, np.nan, dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        for i in range(window - 1, n):
            if np.isnan(arr[i]):
                continue
            chunk = arr[i - window + 1 : i + 1]
            finite = chunk[~np.isnan(chunk)]
            out[i] = float(np.mean(finite))
    return out


def rolling_std(values: FloatArray, window: int, ddof: int = 1) -> FloatArray:
    """الانحراف المعياري المتدحرج (عينة ``ddof=1`` افتراضيًا) لكل نافذة خلفية.

    درجات الحرية تُحسب على عدد الأعضاء غير الـnan في النافذة:
    إن كان ``عدد الأعضاء المحدودين − ddof < 1`` فالخرج nan.

    :raises ValueError: إذا كان ddof < 0 أو window < 1 + ddof.
    """
    if ddof < 0:
        raise ValueError(f"ddof يجب أن يكون ≥ 0؛ وُجد {ddof}")
    check_window(window, minimum=1 + ddof)
    arr = as_f64_1d(values, "values")
    n = arr.shape[0]
    out: FloatArray = np.full(n, np.nan, dtype=np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        for i in range(window - 1, n):
            if np.isnan(arr[i]):
                continue
            chunk = arr[i - window + 1 : i + 1]
            finite = chunk[~np.isnan(chunk)]
            if finite.shape[0] - ddof < 1:
                continue
            out[i] = float(np.std(finite, ddof=ddof))
    return out


def rolling_zscore(values: FloatArray, window: int) -> FloatArray:
    """z-score القيمة الحالية مقابل متوسط/انحراف النافذة الخلفية الشاملة لها.

    حارس القسمة: أي انحراف محسوب يساوي صفرًا — تساوٍ تام، أو انهدام
    تحت-عادي لمربعات الانحرافات — ⇒ nan لا inf. رياضيًا
    ``|z| ≤ √(window−1)`` لأن انحراف النافذة الشاملة يحتوي انحراف
    القيمة الحالية نفسها.

    :raises ValueError: إذا كانت window < 2.
    """
    check_window(window, minimum=2)
    arr = as_f64_1d(values, "values")
    means = rolling_mean(arr, window)
    stds = rolling_std(arr, window, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out = (arr - means) / stds
    out[stds == 0.0] = np.nan
    return out


def rolling_percentile(values: FloatArray, window: int) -> FloatArray:
    """مئيني القيمة الحالية ضمن النافذة الخلفية **الشاملة لها**.

    **العقد الموثق صراحة**: النافذة تنتهي عند القيمة الحالية وتشملها،
    والمئيني هو نسبة أعضاء النافذة الأصغر منها قطعيًا:

    ``p_i = #{v ∈ W_i : v < x_i} / (|F_i| − 1)``

    حيث ``W_i`` آخر ``window`` قيمة منتهية بالقيمة الحالية ``x_i``،
    و``F_i`` أعضاؤها غير الـnan.

    - أفضل حالة: القيمة تعلو كل نافذتها قطعيًا ⇒ ``1.0``.
    - أسوأ حالة: لا تعلو شيئًا ⇒ ``0.0`` (يشمل التساوي التام:
      سلسلة ثابتة ⇒ 0.0 — لا توسع فوق أي سابق).
    - الدافئ ``i < window−1`` ⇒ nan؛ وأقل من عضويين محدودين ⇒ nan.

    :raises ValueError: إذا كانت window < 2.
    """
    check_window(window, minimum=2)
    arr = as_f64_1d(values, "values")
    n = arr.shape[0]
    out: FloatArray = np.full(n, np.nan, dtype=np.float64)
    for i in range(window - 1, n):
        current = arr[i]
        if np.isnan(current):
            continue
        chunk = arr[i - window + 1 : i + 1]
        finite = chunk[~np.isnan(chunk)]
        denominator = finite.shape[0] - 1
        if denominator < 1:
            continue
        out[i] = np.count_nonzero(finite < current) / denominator
    return out
