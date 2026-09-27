"""أدوات داخلية مشتركة — ليست جزءًا من الواجهة العلنية للحزمة.

عقد الحزمة (§16 و§47): تعمل quantmath على مصفوفات numpy وfloat64 حصرًا،
ولا تستورد أي حزمة مشروع أخرى (عقد "quantmath is a foundation" في import-linter).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

__all__ = ["as_f64_1d", "check_window"]

#: مصفوفة أحادية البعد بدقة float64 — عقد كل دوال الحزمة (دقة معلنة).
type FloatArray = NDArray[np.float64]


def as_f64_1d(values: FloatArray, name: str) -> FloatArray:
    """إجبار المدخل إلى متجه float64 أحادي البعد (عقد الدقة المعلنة).

    يقبل أي شيء يقبله ‎np.asarray‎. لا نُغيّر شيئًا في المدخل أبدًا؛
    والمصفوفة المطابقة أصلًا لا تُنسخ (لا نطفّئ فيها شيئًا).

    :raises ValueError: إذا لم يكن الناتج أحادي البعد.
    """
    arr: FloatArray = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"{name} يجب أن تكون متجهًا أحادي البعد؛ بُعدها {arr.ndim}")
    return arr


def check_window(window: int, minimum: int, name: str = "window") -> None:
    """التحقق من صلاحية حجم نافذة/دورة: ≥ minimum وإلا ValueError.

    :raises ValueError: إذا كان window أصغر من minimum.
    """
    if window < minimum:
        raise ValueError(f"{name} يجب أن يكون ≥ {minimum}؛ وُجد {window}")
