"""التشبع: عدّ الركض المتتالي فوق/تحت عتبة — «القيمة فوق عتبة لمدة كافية».

§26.3: العد عند الفهرس ``i`` يعتمد على ``[0..i]`` حصرًا (ركض خلفي متتالٍ).
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from ._internal import FloatArray, as_f64_1d

__all__ = ["is_saturated", "saturation_run"]

#: القيم المقبولة لمعامل direction (تحقق زمني — غير المدرجة يُرفض).
_DIRECTIONS: Final[tuple[str, ...]] = ("above", "below")


def saturation_run(values: FloatArray, bound: float, direction: str) -> FloatArray:
    """عدد العناصر المتتالية حتى الموضع الحالي (شاملةً) المحققة للشرط.

    ``direction="above"``: القيمة ≥ bound؛ و``"below"``: القيمة ≤ bound.
    الموضع غير المحقق ⇒ ``0.0``. ``inf``/``−inf`` تُعامل قيمًا عادية
    تقارن طبيعيًا.

    **عقد nan**: الموضع nan ⇒ خرجه nan **ويقطع الركض** — يعود العد من
    صفر بعد الموضع.

    :raises ValueError: إذا لم يكن direction أحد "above"/"below".
    """
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction يجب أن يكون 'above' أو 'below'؛ وُجد {direction!r}")
    arr = as_f64_1d(values, "values")
    out: FloatArray = np.empty(arr.shape[0], dtype=np.float64)
    above = direction == "above"
    run = 0
    for i in range(arr.shape[0]):
        value = arr[i]
        if np.isnan(value):
            out[i] = np.nan
            run = 0
            continue
        qualifies = value >= bound if above else value <= bound
        run = run + 1 if qualifies else 0
        out[i] = float(run)
    return out


def is_saturated(
    values: FloatArray, bound: float, direction: str, min_run: int
) -> NDArray[np.bool_]:
    """هل بلغ العد المتتالي الحد الأدنى؟ boolean لكل موضع.

    مواضع nan ⇒ ``False`` (عدّها غير معروف — الحذر الافتراضي).
    بقية العقود كما في :func:`saturation_run`.

    :raises ValueError: كما في saturation_run، أو إذا كان min_run < 1.
    """
    if min_run < 1:
        raise ValueError(f"min_run يجب أن يكون ≥ 1؛ وُجد {min_run}")
    runs = saturation_run(values, bound, direction)
    return runs >= min_run
