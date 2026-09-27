"""اختبارات وحدة ATR وعائلته (المهمة 2.1 — §16).

كل القيم محسوبة يدويًا:
- TR بفجوة إغلاق سابق صاعدة/هابطة (تفوّق |H−C_prev| أو |L−C_prev| على H−L).
- وايلدر بخطوتين محسوبتين يدويًا — كل القيم ثنائية التمثيل تمامًا
  فالمقارنة الحرفية ``==`` مشروعة.
- الدافئ nan وفق العقد الموضعي، وperiod=1 حالة حدية (ATR ≡ TR).
- atr_percentile عبر rolling_percentile مع استبعاد عناصر nan.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from quantmath import atr_percentile, true_range, wilder_atr


def arr(*xs: float) -> NDArray[np.float64]:
    """متجه float64 — عقد الدقة المعلنة للحزمة."""
    out: NDArray[np.float64] = np.asarray(xs, dtype=np.float64)
    return out


class TestTrueRange:
    """TR الكلاسيكي: العنصر الأول H−L بلا سابق، والفجوات تدخل بالقيمة القصوى."""

    def test_first_element_is_high_minus_low(self) -> None:
        tr = true_range(arr(10.0, 12.0), arr(9.0, 10.0), arr(9.5, 11.0))
        assert tr[0] == 1.0

    def test_gap_up_previous_close_dominates(self) -> None:
        # |H−C_prev| = |12−9.5| = 2.5 يتفوق على H−L = 2 و|L−C_prev| = 0.5
        tr = true_range(arr(10.0, 12.0), arr(9.0, 10.0), arr(9.5, 11.0))
        assert tr[1] == 2.5

    def test_gap_down_previous_close_dominates(self) -> None:
        # شمعة 1: H=11, L=10, C_prev=14.5 ⇒ |L−C_prev| = 4.5 يتفوق على 3.5 و1.0
        tr = true_range(arr(15.0, 11.0), arr(14.0, 10.0), arr(14.5, 10.5))
        assert tr[1] == 4.5

    def test_flat_candles_give_zero(self) -> None:
        tr = true_range(arr(5.0, 5.0), arr(5.0, 5.0), arr(5.0, 5.0))
        assert tr[0] == 0.0
        assert tr[1] == 0.0

    def test_nan_inputs_propagate_without_explosion(self) -> None:
        tr = true_range(arr(10.0, 12.0), arr(9.0, 10.0), arr(np.nan, 11.0))
        assert tr[0] == 1.0
        assert np.isnan(tr[1])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="أطوال"):
            true_range(arr(10.0, 12.0), arr(9.0), arr(9.5, 11.0))

    def test_empty_input_gives_empty_output(self) -> None:
        tr = true_range(arr(), arr(), arr())
        assert tr.shape == (0,)


class TestWilderAtr:
    """تمهيد وايلدر RMA: بذرة المتوسط عند period−1 ثم الاستدعاء الذاتي."""

    def test_two_manual_steps(self) -> None:
        # tr = [1, 2.5, 2, 3]، period=2:
        # atr[1] = mean(1, 2.5) = 1.75
        # atr[2] = (1.75×1 + 2)/2 = 1.875
        # atr[3] = (1.875×1 + 3)/2 = 2.4375
        atr = wilder_atr(arr(1.0, 2.5, 2.0, 3.0), period=2)
        assert np.isnan(atr[0])
        assert atr[1] == 1.75
        assert atr[2] == 1.875
        assert atr[3] == 2.4375

    def test_warmup_nan_then_seed_is_mean(self) -> None:
        tr = arr(3.0, 1.0, 4.0, 1.0, 5.0)
        atr = wilder_atr(tr, period=3)
        assert np.isnan(atr[:2]).all()
        assert atr[2] == float(np.mean(tr[:3]))  # (3+1+4)/3

    def test_period_one_equals_tr(self) -> None:
        tr = arr(4.0, 1.0, 7.0, 2.0)
        atr = wilder_atr(tr, period=1)
        assert np.array_equal(atr, tr)

    def test_shorter_than_period_all_nan(self) -> None:
        atr = wilder_atr(arr(1.0, 2.0), period=5)
        assert np.isnan(atr).all()

    def test_classic_period_fourteen(self) -> None:
        tr = arr(*[float(i) for i in range(1, 16)])  # 1..15
        atr = wilder_atr(tr, period=14)
        assert np.isnan(atr[:13]).all()
        assert atr[13] == 7.5  # متوسط 1..14
        assert atr[14] == (7.5 * 13 + 15.0) / 14

    def test_nan_tr_propagates_through_recurrence(self) -> None:
        # nan في البذرة ينتشر عبر الاستدعاء الذاتي (تمرير بلا انفجار)
        atr = wilder_atr(arr(np.nan, 2.0, 3.0), period=2)
        assert np.isnan(atr).all()

    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="period"):
            wilder_atr(arr(1.0, 2.0), period=0)


class TestAtrPercentile:
    """مئيني ATR — دافئ موضعي + استبعاد عناصر nan (عقد rolling_percentile)."""

    def test_manual_with_nan_warmup_exclusion(self) -> None:
        # atr = [nan, 3, 1, 2, 3]، window=3:
        # i=2: نافذة [nan,3,1] ⇒ finite=[3,1]، القيمة 1 لا تعلو شيئًا ⇒ 0.0
        # i=3: نافذة [3,1,2] ⇒ تعلو 1 فقط من عضويْن ⇒ 0.5
        # i=4: نافذة [1,2,3] ⇒ تعلو الاثنين ⇒ 1.0
        pct = atr_percentile(arr(np.nan, 3.0, 1.0, 2.0, 3.0), window=3)
        assert np.isnan(pct[:2]).all()
        assert pct[2] == 0.0
        assert pct[3] == 0.5
        assert pct[4] == 1.0

    def test_window_below_two_raises(self) -> None:
        with pytest.raises(ValueError, match="window"):
            atr_percentile(arr(1.0, 2.0), window=1)
