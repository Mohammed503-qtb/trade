"""رياضيات التقلب النقية: ATR وعائلته، مئينيات متدحرجة، z-scores، تشبع (§16).

عقد الحزمة (§47 و§26.3 و§16):

- **عقد أساس نقي** (import-linter: "quantmath is a foundation"): لا تستورد
  هذه الحزمة أي حزمة مشروع أخرى — تعمل على مصفوفات numpy وقيم أولية حصرًا.
- **لا نظرة مستقبلية**: كل دالة تنتج عند الفهرس i قيمًا تعتمد على
  المدخلات [0..i] فقط؛ النوافذ خلفية شاملة للقيمة الحالية.
- **float64 حصرًا** مع تمرير القيم غير المحدودة (nan/inf) دون انفجار.
- **حتمية صرفة**: لا عشوائية إطلاقًا؛ نفس المصفوفة ⇒ نفس المخرجات بايت-بايت.
"""

from __future__ import annotations

from .atr import atr_percentile, true_range, wilder_atr
from .rolling import rolling_mean, rolling_percentile, rolling_std, rolling_zscore
from .saturation import is_saturated, saturation_run
from .volatility import (
    expected_holding_vol,
    gap_shock,
    range_expansion_percentile,
    realized_volatility,
    spread_to_range,
    vol_of_vol,
)

__version__ = "0.1.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022)
__all__ = [
    "atr_percentile",
    "expected_holding_vol",
    "gap_shock",
    "is_saturated",
    "range_expansion_percentile",
    "realized_volatility",
    "rolling_mean",
    "rolling_percentile",
    "rolling_std",
    "rolling_zscore",
    "saturation_run",
    "spread_to_range",
    "true_range",
    "vol_of_vol",
    "wilder_atr",
]
