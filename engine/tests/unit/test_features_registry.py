"""اختبارات سجل السمات المركزي (المهمة 2-c) — الدليل الحصري للاستئصال 2-e.

يُقفل: الأسماء الحرفية الثابتة، فريديتها، الفئات، الافتراضات المثبتة،
جمود المواصفات والخريطات، ومطابقة compute_feature للنداء المباشر (السجل
لا يستنسخ حسابًا — المسار الوحيد A-02).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from features import (
    FeatureCategory,
    atr_pct_series,
    atr_series,
    body_fraction_series,
    close_location_series,
    compute_feature,
    directional_efficiency_series,
    expected_holding_vol_series,
    feature_names,
    gap_relationship_series,
    gap_shock_series,
    get_feature_spec,
    list_features,
    normalized_range_series,
    range_expansion_series,
    range_percentile_series,
    realized_vol_series,
    spread_to_range_series,
    vol_of_vol_series,
    volume_concentration_series,
    volume_relationship_series,
    wick_asymmetry_series,
)
from numpy.typing import NDArray
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)

# ─── الأسماء والفئات والافتراضات المثبتة (مرجع مستقل داخل الاختبار) ───

PINNED: dict[str, tuple[FeatureCategory, dict[str, int]]] = {
    "atr_14": (FeatureCategory.VOLATILITY, {"period": 14}),
    "atr_pct_14_100": (FeatureCategory.VOLATILITY, {"atr_period": 14, "pct_window": 100}),
    "realized_vol_20": (FeatureCategory.VOLATILITY, {"window": 20}),
    "vol_of_vol_20_50": (FeatureCategory.VOLATILITY, {"rv_window": 20, "vov_window": 50}),
    "gap_shock_14": (FeatureCategory.VOLATILITY, {"atr_period": 14}),
    "expected_holding_vol_60_20": (
        FeatureCategory.VOLATILITY,
        {"horizon_bars": 60, "rv_window": 20},
    ),
    "range_expansion_100": (FeatureCategory.RANGE, {"window": 100}),
    "spread_to_range": (FeatureCategory.RANGE, {}),
    "normalized_range_14": (FeatureCategory.RANGE, {"atr_period": 14}),
    "directional_efficiency_20": (FeatureCategory.EFFICIENCY, {"window": 20}),
    "volume_concentration_20": (FeatureCategory.VOLUME, {"window": 20}),
    # سمات الشموع الست (§13.1) — المرحلة 5a
    "body_fraction": (FeatureCategory.CANDLE, {}),
    "wick_asymmetry": (FeatureCategory.CANDLE, {}),
    "close_location": (FeatureCategory.CANDLE, {}),
    "range_percentile_100": (FeatureCategory.CANDLE, {"window": 100}),
    "gap_relationship_20": (FeatureCategory.CANDLE, {"window": 20}),
    "volume_relationship_20": (FeatureCategory.CANDLE, {"window": 20}),
}


def _candle(index: int, close: float) -> Candle:
    open_ = 100.0 + index * 0.1
    high = max(open_, close) + 0.5
    low = min(open_, close) - 0.5
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id="BINANCE_USDM:BTCUSDT",
        timeframe="1m",
        bar_time=_BASE + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0 + (index * 37) % 50,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span,
        close_location_value=(close - low) / span,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)),
    )


def _candles(n: int = 160) -> list[Candle]:
    """سلسلة حتمية مضطربة كافية لاكتمال دافئ كل السمات المسجلة."""
    return [_candle(i, 100.0 + math.sin(i / 5.0) * 5.0 + (i % 7) * 0.05) for i in range(n)]


def test_registry_contains_exactly_pinned_names() -> None:
    """السجل يطابق المرجع المثبت بالضبط — لا زيادة ولا نقصان."""
    assert feature_names() == tuple(sorted(PINNED))
    assert len(list_features()) == len(PINNED)


def test_names_unique() -> None:
    """الأسماء فريدة قطعيًا (شرط قفل السجل)."""
    names = [spec.name for spec in list_features()]
    assert len(names) == len(set(names))


def test_categories_and_defaults_pinned() -> None:
    """كل سمة بفئتها وافتراضاتها المثبتة حرفيًا."""
    for spec in list_features():
        pinned_category, pinned_params = PINNED[spec.name]
        assert spec.category is pinned_category, spec.name
        assert dict(spec.default_params) == pinned_params, spec.name


def test_default_params_empty_for_paramless_feature() -> None:
    """السمة بلا معاملات (spread_to_range) لها خريطة فارغة محفوظة."""
    spec = get_feature_spec("spread_to_range")
    assert dict(spec.default_params) == {}
    assert len(spec.default_params) == 0


def test_default_params_mapping_is_immutable() -> None:
    """الافتراضات خريطة محفوظة — أي تعديل يرفض بTypeError (لا تلاعب بالاستئصال)."""
    spec = get_feature_spec("atr_14")
    with pytest.raises(TypeError):
        spec.default_params["period"] = 99  # type: ignore[index]


def test_feature_spec_frozen() -> None:
    """المواصفة مجمّدة — إسناد أي حقل يرفض بFrozenInstanceError."""
    spec = get_feature_spec("atr_14")
    with pytest.raises(FrozenInstanceError):
        spec.name = "hacked"  # type: ignore[misc]


def test_list_features_sorted_deterministically() -> None:
    """القائمة مرتبة أبجديًا وت返ع نفس المحتوى عند كل نداء."""
    first = list_features()
    second = list_features()
    assert [spec.name for spec in first] == sorted(spec.name for spec in first)
    assert first == second


def test_get_feature_spec_unknown_name_raises_with_options() -> None:
    """اسم مجهول ⇒ ValueError عربية تسرد الأسماء القانونية."""
    with pytest.raises(ValueError, match="سمة غير مسجلة") as exc_info:
        get_feature_spec("not_a_feature")
    assert "atr_14" in str(exc_info.value)


def test_category_enum_values() -> None:
    """الفئات الخمس بقيمها الحرفية — StrEnum قابل للتسلسل في التقارير."""
    assert FeatureCategory.VOLATILITY == "VOLATILITY"
    assert FeatureCategory.RANGE == "RANGE"
    assert FeatureCategory.EFFICIENCY == "EFFICIENCY"
    assert FeatureCategory.VOLUME == "VOLUME"
    assert FeatureCategory.CANDLE == "CANDLE"
    assert len(FeatureCategory) == 5


def test_every_category_represented() -> None:
    """كل فئة لها سمة واحدة على الأقل — لا فئة عائمة بلا عائلة."""
    categories = {spec.category for spec in list_features()}
    assert categories == set(FeatureCategory)


# ─── compute_feature — المسار الوحيد عبر الاسم ───

SeriesFactory = Callable[[list[Candle]], NDArray[np.float64]]
DIRECT_CALLS: dict[str, SeriesFactory] = {
    "atr_14": lambda cs: atr_series(cs, period=14),
    "atr_pct_14_100": lambda cs: atr_pct_series(cs, atr_period=14, pct_window=100),
    "realized_vol_20": lambda cs: realized_vol_series(cs, window=20),
    "vol_of_vol_20_50": lambda cs: vol_of_vol_series(cs, rv_window=20, vov_window=50),
    "gap_shock_14": lambda cs: gap_shock_series(cs, atr_period=14),
    "expected_holding_vol_60_20": lambda cs: expected_holding_vol_series(
        cs, horizon_bars=60, rv_window=20
    ),
    "range_expansion_100": lambda cs: range_expansion_series(cs, window=100),
    "spread_to_range": lambda cs: spread_to_range_series(cs),
    "normalized_range_14": lambda cs: normalized_range_series(cs, atr_period=14),
    "directional_efficiency_20": lambda cs: directional_efficiency_series(cs, window=20),
    "volume_concentration_20": lambda cs: volume_concentration_series(cs, window=20),
    "body_fraction": lambda cs: body_fraction_series(cs),
    "wick_asymmetry": lambda cs: wick_asymmetry_series(cs),
    "close_location": lambda cs: close_location_series(cs),
    "range_percentile_100": lambda cs: range_percentile_series(cs, window=100),
    "gap_relationship_20": lambda cs: gap_relationship_series(cs, window=20),
    "volume_relationship_20": lambda cs: volume_relationship_series(cs, window=20),
}


@pytest.mark.parametrize("name", sorted(DIRECT_CALLS), ids=sorted(DIRECT_CALLS))
def test_compute_feature_matches_direct_call(name: str) -> None:
    """السجل لا يشوه: بالاسم == بالنداء المباشر، بتّية (nan بنمط البتات نفسه)."""
    candles = _candles()
    assert compute_feature(name, candles).tobytes() == DIRECT_CALLS[name](candles).tobytes()


def test_compute_feature_override_wins() -> None:
    """تجاوز معامل يغير النتيجة إلى قيمة النداء المباشر بذلك المعامل."""
    candles = _candles()
    overridden = compute_feature("realized_vol_20", candles, window=5)
    assert overridden.tobytes() == realized_vol_series(candles, window=5).tobytes()
    # والافتراضي بلا تجاوز يبقى كما هو
    assert compute_feature("realized_vol_20", candles).tobytes() != overridden.tobytes()


def test_compute_feature_unknown_param_raises() -> None:
    """معامل مجهول ⇒ ValueError تسمّي المعاملات القانونية."""
    candles = _candles(30)
    with pytest.raises(ValueError, match="معامل مجهول"):
        compute_feature("atr_14", candles, window=7)


def test_compute_feature_unknown_name_raises() -> None:
    """اسم مجهول ⇒ ValueError (نفس عقد get_feature_spec)."""
    with pytest.raises(ValueError, match="سمة غير مسجلة"):
        compute_feature("nope", _candles(5))


def test_compute_feature_validates_consistency() -> None:
    """تحقق الاتساق يعبر السجل — خلط أدوات يرفض حتى عبر compute_feature."""
    candles = _candles(30)
    intruder = candles[-1].model_copy(update={"instrument_id": "BINANCE_USDM:ETHUSDT"})
    with pytest.raises(ValueError, match="خلط أدوات"):
        compute_feature("atr_14", [*candles, intruder])


def test_compute_feature_empty_candles() -> None:
    """القائمة الفارغة عبر السجل: مصفوفة فارغة (لا استثناء من المسار)."""
    out = compute_feature("atr_pct_14_100", [])
    assert out.shape == (0,)
