"""اختبارات مِحور الاستئصال (المهمة 2-e، §43) — جدول فارغ الوظائف مكتمل التوصيل.

يُقفل: بنية الجدول (base ثم plus_* ثم minus_* بلا صفوف مكررة)، الرفض
العربي للأسماء المجهولة وللاستئصال الغائب، جمود كل البنى، placeholder
الافتراضي، التوصيل الحقيقي عبر compute_feature (بما فيه دافئ nan للنوافذ
الأوسع من البيانات)، والحتمية البايتية الكاملة مع الساعة المحقونة.
"""

from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from engine_replay import (
    AblationSpec,
    Dataset,
    FeatureSet,
    VariantKind,
    placeholder_evaluator,
    run_ablation,
)
from engine_replay import ablation as ablation_module
from features import compute_feature, feature_names
from numpy.typing import NDArray
from schemas import Candle, DataQuality

_BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
_FIXED_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _candle(index: int, close: float) -> Candle:
    """شمعة اصطناعية صالحة بنمط اختبارات السجل — لا fixtures هنا (عقد المهمة)."""
    open_ = 100.0 + index * 0.1
    high = max(open_, close) + 0.5
    low = min(open_, close) - 0.5
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id="BINANCE_USDM:BTCUSDT",
        timeframe="1m",
        bar_time=_BASE_TIME + timedelta(minutes=index),
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


def _candles(n: int) -> list[Candle]:
    """سلسلة حتمية مضطربة — نوافذ أوسع من n تعيد nan كاملة (عقد quantmath)."""
    return [_candle(i, 100.0 + math.sin(i / 3.0) * 4.0 + (i % 5) * 0.2) for i in range(n)]


def _dataset(n: int = 8, label: str = "synthetic") -> Dataset:
    return Dataset(label=label, candles=tuple(_candles(n)))


_SPEC = AblationSpec(
    base_features=("spread_to_range", "normalized_range_14", "directional_efficiency_20"),
    ablated=("atr_14", "gap_shock_14"),
    dataset_label="synthetic",
)

# ─── FeatureSet: مصدر السمات الوحيد هو السجل ───


def test_featureset_accepts_every_registered_name() -> None:
    """كل أسماء السجل الفعلية قانونية — التحقق ضد السجل الحي لا قائمة مثبتة."""
    fs = FeatureSet(name="all", features=feature_names())
    assert fs.features == feature_names()


def test_featureset_preserves_order_and_name() -> None:
    """الترتيب المعطى محفوظ كما هو (حتمية الجدول تعتمده)."""
    fs = FeatureSet(name="m", features=("atr_14", "spread_to_range"))
    assert fs.name == "m"
    assert fs.features == ("atr_14", "spread_to_range")


def test_featureset_rejects_unknown_name() -> None:
    """السمة المجهولة مرفوضة برسالة عربية تسرد الأسماء القانونية."""
    with pytest.raises(ValueError, match="غير مسجلة"):
        FeatureSet(name="bad", features=("atr_14", "not_a_feature"))


def test_featureset_rejects_duplicate_names() -> None:
    """التكرار داخل المجموعة مرفوض — لا معنى لعضو مزدوج في جدول استئصال."""
    with pytest.raises(ValueError, match="مكررة"):
        FeatureSet(name="dup", features=("atr_14", "atr_14"))


def test_featureset_is_frozen() -> None:
    fs = FeatureSet(name="m", features=("atr_14",))
    with pytest.raises(FrozenInstanceError):
        fs.name = "other"  # type: ignore[misc]


def test_dataset_is_frozen() -> None:
    ds = _dataset(3)
    with pytest.raises(FrozenInstanceError):
        ds.label = "other"  # type: ignore[misc]


# ─── AblationSpec: التحقق المبكر ───


def test_spec_rejects_unknown_in_base() -> None:
    with pytest.raises(ValueError, match="غير مسجلة"):
        AblationSpec(base_features=("nope",), ablated=("atr_14",), dataset_label="d")


def test_spec_rejects_unknown_in_ablated() -> None:
    with pytest.raises(ValueError, match="غير مسجلة"):
        AblationSpec(base_features=("atr_14",), ablated=("nope",), dataset_label="d")


def test_spec_rejects_duplicates_in_base() -> None:
    with pytest.raises(ValueError, match="مكررة"):
        AblationSpec(
            base_features=("atr_14", "atr_14"), ablated=("spread_to_range",), dataset_label="d"
        )


def test_spec_rejects_duplicates_in_ablated() -> None:
    with pytest.raises(ValueError, match="مكررة"):
        AblationSpec(
            base_features=("atr_14",),
            ablated=("spread_to_range", "spread_to_range"),
            dataset_label="d",
        )


def test_spec_name_deterministic_and_unambiguous() -> None:
    """اسم المواصفة حتمي ويكشف المجموعتين معًا (يظهر في التقارير)."""
    spec = AblationSpec(base_features=("atr_14",), ablated=("spread_to_range",), dataset_label="d")
    assert spec.name == "base(atr_14);ablate(spread_to_range)"


# ─── بناء المتغيرات: plus/minus والدلالة الموثقة ───


def test_plus_variant_appends_feature() -> None:
    spec = AblationSpec(
        base_features=("atr_14", "spread_to_range"), ablated=("gap_shock_14",), dataset_label="d"
    )
    variant = spec.plus_variant("gap_shock_14")
    assert variant.label == "plus_gap_shock_14"
    assert variant.kind is VariantKind.PLUS
    assert variant.feature_set.features == ("atr_14", "spread_to_range", "gap_shock_14")


def test_plus_variant_rejects_member_of_base() -> None:
    """قرار موثق: base+X لعضو حاضر يكرر القاعدة بلا معلومة — رفض عربي."""
    spec = AblationSpec(base_features=("atr_14",), ablated=("spread_to_range",), dataset_label="d")
    with pytest.raises(ValueError, match="يكرر القاعدة"):
        spec.plus_variant("atr_14")


def test_minus_variant_removes_feature_preserving_order() -> None:
    spec = AblationSpec(
        base_features=("atr_14", "spread_to_range", "gap_shock_14"),
        ablated=("spread_to_range",),
        dataset_label="d",
    )
    variant = spec.minus_variant("spread_to_range")
    assert variant.label == "minus_spread_to_range"
    assert variant.kind is VariantKind.MINUS
    assert variant.feature_set.features == ("atr_14", "gap_shock_14")


def test_minus_variant_rejects_non_member() -> None:
    """استئصال غائب عن القاعدة مرفوض برسالة عربية (اختيبر plus بدلًا منها)."""
    spec = AblationSpec(base_features=("atr_14",), ablated=("spread_to_range",), dataset_label="d")
    with pytest.raises(ValueError, match="ليست في القاعدة"):
        spec.minus_variant("spread_to_range")


def test_build_variants_disjoint_all_plus() -> None:
    """القاعدة + N خارجها ⇒ 1 + N متغيرات: base ثم plus_* بترتيب ablated."""
    spec = AblationSpec(
        base_features=("spread_to_range",),
        ablated=("atr_14", "gap_shock_14", "realized_vol_20"),
        dataset_label="d",
    )
    variants = spec.build_variants()
    assert [v.label for v in variants] == [
        "base",
        "plus_atr_14",
        "plus_gap_shock_14",
        "plus_realized_vol_20",
    ]
    assert [v.kind for v in variants] == [
        VariantKind.BASE,
        VariantKind.PLUS,
        VariantKind.PLUS,
        VariantKind.PLUS,
    ]


def test_build_variants_all_in_base_all_minus() -> None:
    """كل المستأصلة داخل القاعدة ⇒ 1 + N صفوف minus_* (لا plus مكرر)."""
    spec = AblationSpec(
        base_features=("atr_14", "spread_to_range", "gap_shock_14"),
        ablated=("gap_shock_14", "atr_14"),
        dataset_label="d",
    )
    variants = spec.build_variants()
    assert [v.label for v in variants] == [
        "base",
        "minus_gap_shock_14",
        "minus_atr_14",
    ]
    assert variants[1].feature_set.features == ("atr_14", "spread_to_range")
    assert variants[2].feature_set.features == ("spread_to_range", "gap_shock_14")


def test_build_variants_mixed_grouped_plus_then_minus() -> None:
    """المختلطة: كتلة plus (الخارج، بترتيب ablated) ثم كتلة minus (الداخل)."""
    spec = AblationSpec(
        base_features=("spread_to_range", "normalized_range_14"),
        ablated=("atr_14", "normalized_range_14", "realized_vol_20"),
        dataset_label="d",
    )
    variants = spec.build_variants()
    assert [v.label for v in variants] == [
        "base",
        "plus_atr_14",
        "plus_realized_vol_20",
        "minus_normalized_range_14",
    ]


def test_build_variants_deterministic() -> None:
    """نفس المواصفة تبني نفس الجدول بالضبط مرتين (ترتيبًا ومحتوى)."""
    assert _SPEC.build_variants() == _SPEC.build_variants()


def test_base_variant_feature_set_named_base() -> None:
    variant = _SPEC.base_variant()
    assert variant.label == "base"
    assert variant.feature_set.name == "base"
    assert variant.feature_set.features == _SPEC.base_features


# ─── placeholder_evaluator: الـstub الموثق ───


def test_placeholder_evaluator_returns_feature_count() -> None:
    """المقياس الوحيد المسموح بهذه المرحلة: عدد السمات — لا مقاييس وهمية."""
    fs2 = FeatureSet(name="x", features=("atr_14", "spread_to_range"))
    assert placeholder_evaluator(fs2, _dataset(1)) == {"placeholder": 2.0}
    fs1 = FeatureSet(name="y", features=("atr_14",))
    assert placeholder_evaluator(fs1, _dataset(3)) == {"placeholder": 1.0}
    # البيانات لا تؤثر في placeholder (المقيم الحقيقي 5a.3/9 سيستهلكها)
    fs_empty = FeatureSet(name="z", features=())
    assert placeholder_evaluator(fs_empty, Dataset(label="e", candles=())) == {"placeholder": 0.0}


# ─── run_ablation: التنفيذ والتقارير على شموع اصطناعية ───


def test_run_report_contains_every_variant() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    assert [r.variant_label for r in report.variants] == [
        "base",
        "plus_atr_14",
        "plus_gap_shock_14",
    ]
    assert [r.kind for r in report.variants] == [
        VariantKind.BASE,
        VariantKind.PLUS,
        VariantKind.PLUS,
    ]
    assert report.spec_name == _SPEC.name
    assert report.dataset_label == "synthetic"


def test_run_metrics_placeholder_match_feature_counts() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    by_label = {r.variant_label: r.metrics for r in report.variants}
    assert by_label["base"] == {"placeholder": 3.0}
    assert by_label["plus_atr_14"] == {"placeholder": 4.0}
    assert by_label["plus_gap_shock_14"] == {"placeholder": 4.0}


def test_run_features_used_match_variant_sets() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    by_label = {r.variant_label: r.features_used for r in report.variants}
    assert by_label["base"] == _SPEC.base_features
    assert by_label["plus_atr_14"] == (*_SPEC.base_features, "atr_14")


def test_run_deterministic_bytes_with_injected_clock() -> None:
    """الحتمية الكاملة: نفس المدخلات + ساعة محقونة ⇒ نفس بايتات JSON مرتين."""
    dataset = _dataset()
    report_a = run_ablation(_SPEC, dataset, now=lambda: _FIXED_CLOCK)
    report_b = run_ablation(_SPEC, dataset, now=lambda: _FIXED_CLOCK)
    assert report_a.to_json() == report_b.to_json()
    assert report_a == report_b


def test_run_created_at_from_injected_clock() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    assert report.created_at_utc == _FIXED_CLOCK


def test_run_elapsed_zero_with_fixed_clock_and_nonnegative_without() -> None:
    """ساعة ثابتة ⇒ قياس 0.0 بالضبط؛ بلا حقن ⇒ قياس جداري ≥ 0 (الاستثناءان الموثقان)."""
    fixed = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    assert all(r.elapsed_ms == 0.0 for r in fixed.variants)
    real = run_ablation(_SPEC, _dataset())
    assert all(r.elapsed_ms >= 0.0 for r in real.variants)


def test_to_json_structure_and_roundtrip() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    data = json.loads(report.to_json())
    assert data["spec_name"] == _SPEC.name
    assert data["dataset_label"] == "synthetic"
    assert data["created_at_utc"] == _FIXED_CLOCK.isoformat()
    assert len(data["variants"]) == 3
    first = data["variants"][0]
    assert first["variant_label"] == "base"
    assert first["kind"] == "BASE"
    assert first["metrics"] == {"placeholder": 3.0}
    assert first["features_used"] == list(_SPEC.base_features)
    assert any("placeholder" in note for note in data["notes"])
    assert any("5a" in note for note in data["notes"])


def test_to_json_coerces_int_metrics_to_float() -> None:
    """تسوية المقاييس إلى float — قيم int من مقيم محقون تتسلسل كانتظام موحد."""

    def _int_evaluator(feature_set: FeatureSet, dataset: Dataset) -> dict[str, int]:
        return {"count": len(feature_set.features)}

    report = run_ablation(_SPEC, _dataset(), _int_evaluator, now=lambda: _FIXED_CLOCK)
    assert report.variants[0].metrics == {"count": 3.0}
    assert '"count": 3.0' in report.to_json()


def test_injected_evaluator_overrides_metrics() -> None:
    """نقطة الحقن الوحيدة تعمل: مقيم مخصص يستبدل placeholder بالكامل."""

    def _custom(feature_set: FeatureSet, dataset: Dataset) -> dict[str, float]:
        return {
            "n_candles": float(len(dataset.candles)),
            "n_features": float(len(feature_set.features)),
        }

    report = run_ablation(_SPEC, _dataset(), _custom, now=lambda: _FIXED_CLOCK)
    assert report.variants[0].metrics == {"n_candles": 8.0, "n_features": 3.0}
    assert report.variants[1].metrics == {"n_candles": 8.0, "n_features": 4.0}


def test_to_markdown_valid_table_with_all_variants() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    markdown = report.to_markdown()
    lines = markdown.splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("| المتغير"))
    assert lines[header_idx + 1].startswith("| ---")
    rows = [line for line in lines[header_idx + 2 :] if line.startswith("|")]
    assert len(rows) == len(report.variants)
    for result in report.variants:
        assert any(f"`{result.variant_label}`" in row for row in rows)
    assert "placeholder=3.0" in markdown


def test_to_markdown_includes_notes_and_dataset() -> None:
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    markdown = report.to_markdown()
    assert "## ملاحظات" in markdown
    assert markdown.count("- ") >= len(report.notes)
    assert "synthetic" in markdown
    assert markdown.startswith("# تقرير الاستئصال")


# ─── التوصيل الحقيقي: السمات تُحسب فعلًا — وnan لا يفجر المحور ───


def test_nan_warmup_feature_does_not_explode() -> None:
    """نافذة أوسع من البيانات ⇒ سلسلة nan كاملة (عقد quantmath) لا استثناء.

    المحور ينفذ المتغير كاملًا ويقيّمه — الدافئ nan سلوك موثق لا فشل.
    """
    dataset = _dataset(6)
    spec = AblationSpec(
        base_features=("spread_to_range",),
        ablated=("range_expansion_100",),  # نافذة 100 > 6 شموع
        dataset_label="synthetic",
    )
    report = run_ablation(spec, dataset, now=lambda: _FIXED_CLOCK)
    assert [r.variant_label for r in report.variants] == ["base", "plus_range_expansion_100"]
    assert report.variants[1].metrics == {"placeholder": 2.0}


def test_compute_feature_wider_than_data_all_nan() -> None:
    """توثيق مباشر للعقد المستهلك: window=100 على 6 شموع ⇒ 6 قيم nan كاملة."""
    series = compute_feature("range_expansion_100", _candles(6))
    assert len(series) == 6
    assert bool(np.all(np.isnan(series)))


def test_broken_wiring_length_mismatch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """حارس التوصيل: سمة أعادت سلسلة بطول مخالف ⇒ ValueError عربية (لا صمت)."""

    def _broken(name: str, candles: list[Candle], **overrides: int) -> NDArray[np.float64]:
        _ = name, overrides
        return np.zeros(len(candles) + 1)

    monkeypatch.setattr(ablation_module, "compute_feature", _broken)
    with pytest.raises(ValueError, match="عقد التوصيل"):
        run_ablation(_SPEC, _dataset(4), now=lambda: _FIXED_CLOCK)


def test_dataset_label_mismatch_appends_note() -> None:
    """مخالفة تسمية البيانات تُوثق كملاحظة — لا كسر صامت ولا فشل."""
    spec = AblationSpec(
        base_features=("spread_to_range",),
        ablated=("atr_14",),
        dataset_label="declared",
    )
    report = run_ablation(spec, _dataset(label="actual"), now=lambda: _FIXED_CLOCK)
    assert report.dataset_label == "declared"
    assert any("تحذير مطابقة" in note for note in report.notes)
    clean = run_ablation(spec, _dataset(label="declared"), now=lambda: _FIXED_CLOCK)
    assert not any("تحذير مطابقة" in note for note in clean.notes)


def test_notes_document_placeholder_and_method() -> None:
    """كل تقرير يحمل الملاحظات الموثقة الثابت (منهج §43 + placeholder + التوصيل)."""
    report = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    joined = "\n".join(report.notes)
    assert "§43" in joined
    assert "placeholder" in joined
    assert "compute_feature" in joined
    # الملاحظات حتمية: نفس التسلسل في كل تشغيل
    again = run_ablation(_SPEC, _dataset(), now=lambda: _FIXED_CLOCK)
    assert report.notes == again.notes


def test_run_ablation_full_mixed_table_end_to_end() -> None:
    """تجربة مختلطة كاملة: base + خارج (plus) + داخل (minus) بتقرير صالح."""
    spec = AblationSpec(
        base_features=("spread_to_range", "normalized_range_14"),
        ablated=("normalized_range_14", "atr_14", "directional_efficiency_20"),
        dataset_label="synthetic",
    )
    report = run_ablation(spec, _dataset(10), now=lambda: _FIXED_CLOCK)
    assert [r.variant_label for r in report.variants] == [
        "base",
        "plus_atr_14",
        "plus_directional_efficiency_20",
        "minus_normalized_range_14",
    ]
    payload: dict[str, Any] = json.loads(report.to_json())
    assert len(payload["variants"]) == 4
    assert payload["variants"][3]["features_used"] == ["spread_to_range"]
