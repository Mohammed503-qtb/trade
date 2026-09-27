"""السمات الحسابية — مسار واحد للحي والإعادة (قرار A-02).

حزمة صرفة بلا حالة: دوال ‎list[Candle] → FeatureSeries‎ تُحسب من OHLCV الخام
حصرًا عبر quantmath، ويستدعيها المحرك الحي (worker) ومحرك الإعادة (replay)
بالتطابق — لا ازدواجية شيفرة إطلاقًا (§26.1 مشدَّدًا في plan_review A-02).

- :mod:`features.windows` — استخراج المصفوفات بتحقق صارم (أداة/إطار/ترتيب).
- :mod:`features.vol_features` — سمات التقلب (§16) والمدى والكفاءة والحجم (§9.3).
- :mod:`features.registry` — السجل المركزي المغذي لمِحور الاستئصال (2-e).
"""

from __future__ import annotations

from .registry import (
    FeatureCategory,
    FeatureSpec,
    compute_feature,
    feature_names,
    get_feature_spec,
    list_features,
)
from .vol_features import (
    atr_pct_series,
    atr_series,
    directional_efficiency_series,
    expected_holding_vol_series,
    gap_shock_series,
    normalized_range_series,
    range_expansion_series,
    realized_vol_series,
    spread_to_range_series,
    vol_of_vol_series,
    volume_concentration_series,
)
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

__version__ = "0.1.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022)
__all__ = [
    "FeatureCategory",
    "FeatureSeries",
    "FeatureSpec",
    "__version__",
    "atr_pct_series",
    "atr_series",
    "bodies",
    "closes",
    "compute_feature",
    "directional_efficiency_series",
    "expected_holding_vol_series",
    "feature_names",
    "gap_shock_series",
    "get_feature_spec",
    "highs",
    "list_features",
    "log_returns",
    "lows",
    "normalized_range_series",
    "opens",
    "range_expansion_series",
    "ranges",
    "realized_vol_series",
    "spread_to_range_series",
    "vol_of_vol_series",
    "volume_concentration_series",
    "volumes",
]
