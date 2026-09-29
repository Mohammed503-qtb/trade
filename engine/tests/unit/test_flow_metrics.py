"""اختبارات المقاييس المتتالية لأشرطة الفوتبرنت — بوابة المهمة 4-c (§12.1).

يُقفل حرفيًا بعقود :mod:`orderflow.metrics`:

- ``delta_trend``: ميل المربعات الصغرى لدلت الأشرطة بترتيبها — موجب/
  سالب/صفر بأيدٍ محسوبة، و``None`` لأقل من شريطين، ورفض الدلتا غير
  المنتهية.
- ``volume_concentration`` (التعريف الزمني — معامل هيرفيندال المطبّع):
  ‏[0, 1] بأيدٍ محسوبة، و``None`` للنوافذ القصيرة/صفر التداول.
- ``volume_concentration_rows`` (التركّز السعري — حصة منطقة القيمة):
  ‏[0, 1] بأيدٍ محسوبة، والمساواة ``val == vah`` جائزة والمعكوس مرفوض.
- خاصية hypothesis بذر مثبت (derandomize): القياسات داخل حدودها
  الرياضية المعلنة لأي مدخلات صالحة، والحتمية الصرفة بالاستدعاء
  المزدوج.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

import pytest
from _orderflow_fixtures import make_bar_rows, make_footprint_bar
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from orderflow.metrics import delta_trend, volume_concentration, volume_concentration_rows
from orderflow.rows import BarRows, FootprintRow
from schemas import FootprintBar


def _bars_from_deltas(deltas: Sequence[float]) -> list[FootprintBar]:
    """أشرطة أحادية الصف بدلتات معلنة — الحجمان موجبان دائمًا.

    ``buy = 20 + max(delta, 0)`` و``sell = 20 + max(−delta, 0)`` ففرقهما
    الدلتة المطلوبة بالضبط والقيم قابلة للحساب الذهني.
    """
    return [
        make_footprint_bar(i, ((100.0, 20.0 + max(delta, 0.0), 20.0 + max(-delta, 0.0)),))
        for i, delta in enumerate(deltas)
    ]


def _bars_from_volumes(volumes: Sequence[float]) -> list[FootprintBar]:
    """أشرطة أحادية الصف بأحجام كلية معلنة (مناصفة شراء/بيع)."""
    return [make_footprint_bar(i, ((100.0, v / 2.0, v / 2.0),)) for i, v in enumerate(volumes)]


#: صفوف ثلاثة بأحجام كلية 20 و30 و10 عند أسعار 100/200/300 — أساس حساب
#: حصة منطقة القيمة يدويًا.
_MIX_ROWS = ((100.0, 10.0, 10.0), (200.0, 30.0, 0.0), (300.0, 0.0, 10.0))


# ═══════════ §12.1 «delta trend» ═══════════


class TestDeltaTrend:
    """ميل الدلتا لكل شريط عبر النافذة — انحدار خطي بسيط."""

    def test_none_below_two_bars(self) -> None:
        assert delta_trend([]) is None
        assert delta_trend(_bars_from_deltas((5.0,))) is None

    def test_positive_slope(self) -> None:
        """دلتات 10، 20، 30 ⇒ ميل +10 (دلتا لكل شريط)."""
        assert delta_trend(_bars_from_deltas((10.0, 20.0, 30.0))) == pytest.approx(10.0)

    def test_negative_slope(self) -> None:
        assert delta_trend(_bars_from_deltas((30.0, 20.0, 10.0))) == pytest.approx(-10.0)

    def test_flat_zero(self) -> None:
        assert delta_trend(_bars_from_deltas((5.0, 5.0, 5.0))) == pytest.approx(0.0)

    def test_two_bars_slope_is_exact_difference(self) -> None:
        """عند n = 2 الميل ``delta[1] − delta[0]`` بالضبط (عقد الدالة)."""
        assert delta_trend(_bars_from_deltas((5.0, 25.0))) == pytest.approx(20.0)

    def test_four_bars_hand_computed(self) -> None:
        """دلتات 0، 10، 5، 25 ⇒ ‏Σdx·dy/Σdx² = 35/5 = 7.0."""
        assert delta_trend(_bars_from_deltas((0.0, 10.0, 5.0, 25.0))) == pytest.approx(7.0)

    def test_non_finite_delta_rejected(self) -> None:
        bars = _bars_from_deltas((1.0, 2.0))
        corrupt = bars[1].model_copy(update={"delta": float("nan")})
        with pytest.raises(ValueError, match="غير منتهية"):
            delta_trend((bars[0], corrupt))


# ═══════════ §12.1 «volume concentration» — التعريف الزمني ═══════════


class TestVolumeConcentration:
    """معامل هيرفيندال المطبّع لحصص حجم الأشرطة ∈ [0, 1]."""

    def test_none_below_two_bars(self) -> None:
        assert volume_concentration([]) is None
        assert volume_concentration(_bars_from_volumes((50.0,))) is None

    def test_none_when_window_has_no_trades(self) -> None:
        """نافذة صفر التداول كليًا — لا مقارنة (نمط row_ratio)."""
        bars = _bars_from_volumes((0.0, 0.0))
        assert volume_concentration(bars) is None

    def test_equal_volumes_is_zero(self) -> None:
        """توزيع متساوٍ تمامًا (25×4) — أسهم القوى الثنائية دقيقة."""
        assert volume_concentration(_bars_from_volumes((25.0, 25.0, 25.0, 25.0))) == (
            pytest.approx(0.0)
        )

    def test_all_volume_in_one_bar_is_one(self) -> None:
        assert volume_concentration(_bars_from_volumes((30.0, 0.0, 0.0))) == pytest.approx(1.0)

    def test_zero_volume_bar_among_active_ones(self) -> None:
        """شريط صفر التداول بين نشطين لا يفسد القياس — (10، 0، 20) ⇒ 1/3."""
        assert volume_concentration(_bars_from_volumes((10.0, 0.0, 20.0))) == pytest.approx(
            1.0 / 3.0
        )

    def test_hand_computed_mixed_window(self) -> None:
        """حجوم 10، 10، 20: ‏H = 3/8 والتطبيع (3/8 − 1/3)/(2/3) = 1/16."""
        assert volume_concentration(_bars_from_volumes((10.0, 10.0, 20.0))) == pytest.approx(0.0625)

    def test_negative_total_volume_rejected(self) -> None:
        bars = _bars_from_volumes((10.0, 20.0))
        corrupt = bars[1].model_copy(update={"total_volume": -5.0})
        with pytest.raises(ValueError, match="غير صالح"):
            volume_concentration((bars[0], corrupt))

    def test_non_finite_total_volume_rejected(self) -> None:
        bars = _bars_from_volumes((10.0, 20.0))
        corrupt = bars[1].model_copy(update={"total_volume": float("inf")})
        with pytest.raises(ValueError, match="غير صالح"):
            volume_concentration((bars[0], corrupt))


# ═══════════ التركّز السعري — حصة منطقة القيمة (§12.5) ═══════════


class TestVolumeConcentrationRows:
    """مجموع أحجام الصفوف داخل [val, vah] ÷ الإجمالي ∈ [0, 1]."""

    def test_none_for_empty_window(self) -> None:
        assert volume_concentration_rows([]) is None

    def test_none_when_all_rows_have_no_trades(self) -> None:
        """كل الصفوف صفر التداول — لا مقارنة (بناء مباشر: BarRows عقد
        البنّاء يرفض الشريط صفر التداول، والمقياس يعلن غيابه بـNone)."""
        bar = make_footprint_bar(0, ((100.0, 0.0, 0.0),))
        empty_rows = BarRows(bar=bar, rows=(FootprintRow(100.0, 0.0, 0.0),))
        assert volume_concentration_rows((empty_rows,)) is None

    def test_full_range_value_area_is_one(self) -> None:
        """الافتراضي (مدى الصفوف كاملًا) ⇒ كل الحجم داخل المنطقة."""
        bar_rows = make_bar_rows(0, _MIX_ROWS)  # val=100, vah=300 تلقائيًا
        assert volume_concentration_rows((bar_rows,)) == pytest.approx(1.0)

    def test_degenerate_point_value_area_excludes_others(self) -> None:
        """‏val == vah جائزة (منطقة بمستوى معزول): عند 200 ⇒ 30/60 نصف؛
        وعند 150 (لا صف عنده) ⇒ صفر."""
        at_row = make_bar_rows(0, _MIX_ROWS, val=200.0, vah=200.0)
        assert volume_concentration_rows((at_row,)) == pytest.approx(0.5)
        between_rows = make_bar_rows(0, _MIX_ROWS, val=150.0, vah=150.0)
        assert volume_concentration_rows((between_rows,)) == pytest.approx(0.0)

    def test_hand_computed_partial_window(self) -> None:
        """شريطان: الأول منطقته كاملة (60/60) والثاني [150, 250] (30/60)
        ⇒ نافذة (60 + 30)/(60 + 60) = 0.75."""
        full = make_bar_rows(0, _MIX_ROWS)
        partial = make_bar_rows(1, _MIX_ROWS, val=150.0, vah=250.0)
        assert volume_concentration_rows((full, partial)) == pytest.approx(0.75)

    def test_single_price_window_share(self) -> None:
        """‏[150, 250] تلتقط الصف 200 وحده ⇒ 30/60 = 0.5."""
        bar_rows = make_bar_rows(0, _MIX_ROWS, val=150.0, vah=250.0)
        assert volume_concentration_rows((bar_rows,)) == pytest.approx(0.5)

    def test_inverted_value_area_rejected(self) -> None:
        bar = make_footprint_bar(0, _MIX_ROWS).model_copy(update={"val": 350.0})  # > vah=300
        bar_rows = BarRows(bar=bar, rows=tuple(FootprintRow(p, b, s) for p, b, s in _MIX_ROWS))
        with pytest.raises(ValueError, match="معكوسة"):
            volume_concentration_rows((bar_rows,))

    def test_non_finite_value_area_bound_rejected(self) -> None:
        bar = make_footprint_bar(0, _MIX_ROWS).model_copy(update={"val": float("nan")})
        bar_rows = BarRows(bar=bar, rows=tuple(FootprintRow(p, b, s) for p, b, s in _MIX_ROWS))
        with pytest.raises(ValueError, match="غير منتهيين"):
            volume_concentration_rows((bar_rows,))

    def test_negative_row_volume_rejected(self) -> None:
        bar_rows = make_bar_rows(0, _MIX_ROWS)
        corrupt = BarRows(bar=bar_rows.bar, rows=(FootprintRow(100.0, -5.0, 10.0),))
        with pytest.raises(ValueError, match="غير صالح"):
            volume_concentration_rows((corrupt,))

    def test_invalid_row_price_rejected(self) -> None:
        bar_rows = make_bar_rows(0, _MIX_ROWS)
        corrupt = BarRows(bar=bar_rows.bar, rows=(FootprintRow(float("nan"), 5.0, 10.0),))
        with pytest.raises(ValueError, match="سعر صف غير صالح"):
            volume_concentration_rows((corrupt,))


# ═══════════ خصائص hypothesis — بذر مثبت (derandomize) ═══════════

#: زوجا (شراء، بيع) موجبا الدائمًا — الشريط دائمًا ذو تداول (عقد BarRows).
_ROW_PAIR = st.tuples(
    st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
)
_BAR_SPEC = st.lists(_ROW_PAIR, min_size=1, max_size=4)
_WINDOW = st.lists(_BAR_SPEC, min_size=0, max_size=5)


def _to_rows_spec(pairs: Sequence[tuple[float, float]]) -> tuple[tuple[float, float, float], ...]:
    """سلم أسعار تصاعدي صارم (100 + 0.5·i) فوق أزواج الأحجام المولدة."""
    return tuple((100.0 + 0.5 * i, buy, sell) for i, (buy, sell) in enumerate(pairs))


class TestMetricProperties:
    """القياسات داخل حدودها الرياضية المعلنة لأي مدخلات صالحة."""

    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    @given(window=_WINDOW)
    def test_window_metrics_bounded(self, window: list[list[tuple[float, float]]]) -> None:
        """``delta_trend`` منتهٍ عند n ≥ 2 و``None`` دونها؛ والتركّز الزمني
        داخل [0, 1] — والحتمية بالاستدعاء المزدوج."""
        bars = [make_footprint_bar(i, _to_rows_spec(pairs)) for i, pairs in enumerate(window)]
        trend = delta_trend(bars)
        if len(bars) < 2:
            assert trend is None
        else:
            assert trend is not None and isfinite(trend)
        concentration = volume_concentration(bars)
        if len(bars) < 2:
            assert concentration is None
        else:
            assert concentration is not None and 0.0 <= concentration <= 1.0
        # الحتمية الصرفة — نفس المدخلات ⇒ نفس المخرجات.
        assert delta_trend(bars) == trend
        assert volume_concentration(bars) == concentration

    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    @given(window=_WINDOW)
    def test_rows_concentration_bounded(self, window: list[list[tuple[float, float]]]) -> None:
        """حصة منطقة القيمة داخل [0, 1] لأي نافذة صالحة — وحتمية."""
        bars_with_rows = [make_bar_rows(i, _to_rows_spec(pairs)) for i, pairs in enumerate(window)]
        concentration = volume_concentration_rows(bars_with_rows)
        if not bars_with_rows:
            assert concentration is None
        else:
            assert concentration is not None and 0.0 <= concentration <= 1.0
        assert volume_concentration_rows(bars_with_rows) == concentration
