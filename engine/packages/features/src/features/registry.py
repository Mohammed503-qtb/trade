"""سجل السمات المركزي — الدليل الحصري لمِحور الاستئصال (2-e) ومحرك النظام (2-d).

كل سمة تدخل السجل باسم حرفي ثابت + دالة استخراج + معاملاتها الافتراضية،
مع فئة تُميّز عائلتها الحسابية. هذا السجل وحده كافٍ لتشغيل جدول الاستئصال
(base/±feature) وتغذية محرك النظام: يُعدّد السمات بأسمائها الثابتة، ويعيد
مواصفاتها (الفئة والافتراضات)، ويحسب أياً منها بالاسم مع تجاوزات معاملية —
بلا أي استيراد مباشر لدوال السمات من قبل المستهلكين.

عقود السجل:

- **الأسماء حرفية ثابتة**: ترمّز معاملاتها الافتراضية للقراءة البشرية
  (مثل ``atr_pct_14_100``) لكنها **ليست** مصدر الحقيقة للمعاملات —
  ``default_params`` هي المصدر؛ الاسم للعرض والاستئصال والتقارير.
- **التسجيل حتمي عند الاستيراد**: القائمة مبنية صراحةً في هذا الموديول —
  لا تسجيل ديناميكي ولا اكتشاف تلقائي؛ أي إضافة سمة = تعديل موضع واحد هنا.
- **المواصفات مجمّدة والافتراضات خريطة محفوظة** (‎MappingProxyType‎): لا
  تعديل عرضي لسلوك الاستئصال بعد النشر.
- **compute_feature** يدمج الافتراضات مع التجاوزات (التجاوز يفوز)، ويرفض
  أسماء السمات ومفاتيح المعاملات المجهولة بـValueError عربية — النداء
  النهائي يمر عبر دوال :mod:`features.vol_features` نفسها (لا مسار موازٍ).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from schemas import Candle

from .candle_features import (
    body_fraction_series,
    close_location_series,
    gap_relationship_series,
    range_percentile_series,
    volume_relationship_series,
    wick_asymmetry_series,
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
from .windows import FeatureSeries

__all__ = [
    "FeatureCategory",
    "FeatureSpec",
    "compute_feature",
    "feature_names",
    "get_feature_spec",
    "list_features",
]


class FeatureCategory(StrEnum):
    """عائلة السمة الحسابية — تجميع الاستئصال والعرض حسب الطبيعة لا الاسم."""

    VOLATILITY = "VOLATILITY"
    RANGE = "RANGE"
    EFFICIENCY = "EFFICIENCY"
    VOLUME = "VOLUME"
    CANDLE = "CANDLE"


@dataclass(frozen=True)
class FeatureSpec:
    """مواصفة سمة مسجلة: هوية + عائلة + معاملات افتراضية محفوظة."""

    name: str
    category: FeatureCategory
    #: المعاملات الافتراضية — خريطة محفوظة (قراءة فقط) يمررها السجل لدالة الاستخراج.
    default_params: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))


#: نوع دالة الاستخراج: (candles, **params) → سلسلة سمات.
type FeatureExtractor = Callable[..., FeatureSeries]

# ───────────────────────── بناء السجل ─────────────────────────
#: التسجيل الصريح الحتمي — (الاسم، الفئة، الدالة، الافتراضات).
_FEATURES: tuple[tuple[str, FeatureCategory, FeatureExtractor, dict[str, int]], ...] = (
    (
        "atr_14",
        FeatureCategory.VOLATILITY,
        atr_series,
        {"period": 14},
    ),
    (
        "atr_pct_14_100",
        FeatureCategory.VOLATILITY,
        atr_pct_series,
        {"atr_period": 14, "pct_window": 100},
    ),
    (
        "realized_vol_20",
        FeatureCategory.VOLATILITY,
        realized_vol_series,
        {"window": 20},
    ),
    (
        "vol_of_vol_20_50",
        FeatureCategory.VOLATILITY,
        vol_of_vol_series,
        {"rv_window": 20, "vov_window": 50},
    ),
    (
        "gap_shock_14",
        FeatureCategory.VOLATILITY,
        gap_shock_series,
        {"atr_period": 14},
    ),
    (
        "expected_holding_vol_60_20",
        FeatureCategory.VOLATILITY,
        expected_holding_vol_series,
        {"horizon_bars": 60, "rv_window": 20},
    ),
    (
        "range_expansion_100",
        FeatureCategory.RANGE,
        range_expansion_series,
        {"window": 100},
    ),
    (
        "spread_to_range",
        FeatureCategory.RANGE,
        spread_to_range_series,
        {},
    ),
    (
        "normalized_range_14",
        FeatureCategory.RANGE,
        normalized_range_series,
        {"atr_period": 14},
    ),
    (
        "directional_efficiency_20",
        FeatureCategory.EFFICIENCY,
        directional_efficiency_series,
        {"window": 20},
    ),
    (
        "volume_concentration_20",
        FeatureCategory.VOLUME,
        volume_concentration_series,
        {"window": 20},
    ),
    # سمات الشموع الست (§13.1) — عائلات الأنماط مستعارات لتركيباتها
    # (المرحلة 5a): الثلاث الفورية بلا معاملات والثلاث ذات النوافذ الخلفية.
    (
        "body_fraction",
        FeatureCategory.CANDLE,
        body_fraction_series,
        {},
    ),
    (
        "wick_asymmetry",
        FeatureCategory.CANDLE,
        wick_asymmetry_series,
        {},
    ),
    (
        "close_location",
        FeatureCategory.CANDLE,
        close_location_series,
        {},
    ),
    (
        "range_percentile_100",
        FeatureCategory.CANDLE,
        range_percentile_series,
        {"window": 100},
    ),
    (
        "gap_relationship_20",
        FeatureCategory.CANDLE,
        gap_relationship_series,
        {"window": 20},
    ),
    (
        "volume_relationship_20",
        FeatureCategory.CANDLE,
        volume_relationship_series,
        {"window": 20},
    ),
)

#: السجل الداخلي: الاسم → (المواصفة، دالة الاستخراج) — يُبنى مرة واحدة عند الاستيراد.
_REGISTRY: Mapping[str, tuple[FeatureSpec, FeatureExtractor]] = MappingProxyType(
    {
        name: (
            FeatureSpec(
                name=name,
                category=category,
                default_params=MappingProxyType(dict(params)),
            ),
            extractor,
        )
        for name, category, extractor, params in _FEATURES
    }
)


def list_features() -> tuple[FeatureSpec, ...]:
    """كل السمات المسجلة بترتيب حتمي (أبجدي بالاسم) — نسخة طازجة عند كل نداء."""
    return tuple(
        sorted(
            (spec for spec, _extractor in _REGISTRY.values()),
            key=lambda spec: spec.name,
        )
    )


def feature_names() -> tuple[str, ...]:
    """أسماء السمات المسجلة بترتيب حتمي (أبجدي)."""
    return tuple(sorted(_REGISTRY))


def get_feature_spec(name: str) -> FeatureSpec:
    """مواصفة سمة باسمها المسجل.

    :raises ValueError: اسم غير مسجل (تُسرد الأسماء القانونية في الرسالة).
    """
    try:
        return _REGISTRY[name][0]
    except KeyError:
        raise ValueError(
            f"سمة غير مسجلة في السجل: {name!r} — الأسماء القانونية: {feature_names()}"
        ) from None


def compute_feature(name: str, candles: list[Candle], **overrides: int) -> FeatureSeries:
    """حساب سمة مسجلة بالاسم، مع تجاوزات معاملية تفوز على الافتراضات.

    النداء يمر عبر دالة السمة نفسها في :mod:`features.vol_features` (المسار
    الوحيد A-02) — السجل لا يستنسخ حسابًا أبدًا.

    :raises ValueError: اسم غير مسجل، أو مفتاح معامل مجهول، أو معامل غير صالح
        (يُمرر لQuantmath لتحقق النوافذ).
    """
    try:
        spec, extractor = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"سمة غير مسجلة في السجل: {name!r} — الأسماء القانونية: {feature_names()}"
        ) from None
    params: dict[str, int] = dict(spec.default_params)
    for key, value in overrides.items():
        if key not in params:
            raise ValueError(
                f"معامل مجهول {key!r} للسمة {name!r} — المعاملات القانونية: "
                f"{tuple(spec.default_params)}"
            )
        params[key] = value
    return extractor(candles, **params)
