"""اختبارات وحدة مقاييس التقلب (المهمة 2.1 — §16).

قيم محسوبة يدويًا:
- realized_volatility يطابق np.std(ddof=1) على كل نافذة حرفيًا.
- gap_shock بـATR معروف (الفجوة معياريةً): |110−99|/2 = 5.5.
- expected_holding_vol بتحجيم جذر الزمن: 4 أشرطة ⇒ ×2، و9 ⇒ ×3.
- spread_to_range: 0 عند range=0 (عقد الشمعة المسطحة) وبقاء القيم في [0,1].
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from quantmath import (
    expected_holding_vol,
    gap_shock,
    range_expansion_percentile,
    realized_volatility,
    spread_to_range,
    vol_of_vol,
)


def arr(*xs: float) -> NDArray[np.float64]:
    """متجه float64 — عقد الدقة المعلنة للحزمة."""
    out: NDArray[np.float64] = np.asarray(xs, dtype=np.float64)
    return out


class TestRealizedVolatility:
    """التقلب المحقق — انحراف معياري متدحرج (عينة) للعوائد اللوغاريتمية."""

    def test_matches_np_std_per_window(self) -> None:
        rets = arr(0.01, -0.02, 0.03, 0.005)
        rv = realized_volatility(rets, window=3)
        assert np.isnan(rv[:2]).all()
        assert rv[2] == float(np.std(rets[:3], ddof=1))
        assert rv[3] == float(np.std(rets[1:4], ddof=1))

    def test_leading_nan_return_excluded(self) -> None:
        # أول عائد nan (لا إغلاق سابق) يُستبعد: نافذة [nan, .01, −.02]
        rets = arr(np.nan, 0.01, -0.02)
        rv = realized_volatility(rets, window=3)
        assert rv[2] == float(np.std(arr(0.01, -0.02), ddof=1))

    def test_window_validation(self) -> None:
        with pytest.raises(ValueError, match="window"):
            realized_volatility(arr(1.0, 2.0), window=1)


class TestRangeExpansionPercentile:
    """مئيني توسع المدى — توسع كامل 1.0 وانكماش 0.0."""

    def test_full_expansion_is_one(self) -> None:
        rep = range_expansion_percentile(arr(1.0, 1.0, 1.0, 3.0), window=3)
        assert np.isnan(rep[:2]).all()
        assert rep[3] == 1.0

    def test_contraction_is_zero(self) -> None:
        rep = range_expansion_percentile(arr(3.0, 2.0, 1.0, 0.5), window=3)
        assert rep[3] == 0.0

    def test_warmup_nan(self) -> None:
        rep = range_expansion_percentile(arr(1.0, 2.0), window=3)
        assert np.isnan(rep).all()


class TestVolOfVol:
    """معامل تباين سلسلة التقلب: std/|mean| مع حارس متوسط-الصفر."""

    def test_manual(self) -> None:
        # [0.01, 0.02, 0.03]: std=0.01، |mean|=0.02 ⇒ 0.5
        vov = vol_of_vol(arr(0.01, 0.02, 0.03), window=3)
        assert np.isnan(vov[:2]).all()
        assert vov[2] == pytest.approx(0.5)

    def test_near_zero_mean_guard(self) -> None:
        # |mean| = 1e-13/3 < 1e-12 ⇒ nan بدل قيمة عملاقة
        vov = vol_of_vol(arr(1e-13, -1e-13, 1e-13), window=3)
        assert np.isnan(vov[2])

    def test_exact_zero_mean_guard(self) -> None:
        vov = vol_of_vol(arr(0.0, 0.0, 0.0), window=3)
        assert np.isnan(vov[2])

    def test_constant_series_is_zero(self) -> None:
        # std=0 على متوسط موجب ⇒ 0.0 (لا nan — القسمة سليمة)
        vov = vol_of_vol(arr(0.02, 0.02, 0.02), window=3)
        assert vov[2] == 0.0

    def test_warmup_nan(self) -> None:
        vov = vol_of_vol(arr(0.01, 0.02), window=3)
        assert np.isnan(vov).all()


class TestGapShock:
    """الفجوة معياريةً بالـATR — أول عنصر nan دائمًا."""

    def test_manual_with_known_atr(self) -> None:
        gs = gap_shock(arr(100.0, 110.0, 105.0), arr(99.0, 108.0, 107.0), arr(1.0, 2.0, 1.0))
        assert np.isnan(gs[0])
        assert gs[1] == 5.5  # |110−99|/2
        assert gs[2] == 3.0  # |105−108|/1

    def test_single_element_is_nan(self) -> None:
        gs = gap_shock(arr(100.0), arr(99.0), arr(1.0))
        assert gs.shape == (1,)
        assert np.isnan(gs[0])

    def test_zero_atr_with_gap_is_inf(self) -> None:
        gs = gap_shock(arr(100.0, 110.0), arr(100.0, 100.0), arr(1.0, 0.0))
        assert gs[1] == np.inf

    def test_zero_atr_zero_gap_is_nan(self) -> None:
        gs = gap_shock(arr(100.0, 100.0), arr(100.0, 100.0), arr(1.0, 0.0))
        assert np.isnan(gs[1])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="أطوال"):
            gap_shock(arr(1.0, 2.0), arr(1.0), arr(1.0, 2.0))


class TestExpectedHoldingVol:
    """تحجيم جذر الزمن — horizon صحيح موجب وإلا ValueError."""

    def test_four_bars_double(self) -> None:
        assert expected_holding_vol(0.01, 4) == 0.02

    def test_nine_bars_triple(self) -> None:
        assert expected_holding_vol(0.01, 9) == pytest.approx(0.03)

    def test_one_bar_is_identity(self) -> None:
        assert expected_holding_vol(0.013, 1) == 0.013

    def test_non_positive_horizon_raises(self) -> None:
        for bad in (0, -1, -100):
            with pytest.raises(ValueError, match="horizon"):
                expected_holding_vol(0.01, bad)

    def test_non_integer_horizon_raises(self) -> None:
        with pytest.raises(ValueError, match="horizon"):
            expected_holding_vol(0.01, 2.5)  # type: ignore[arg-type]

    def test_nonfinite_passes_through(self) -> None:
        assert np.isnan(expected_holding_vol(float("nan"), 4))
        assert expected_holding_vol(float("inf"), 4) == float("inf")


class TestSpreadToRange:
    """نسبة |الجسم|/المدى — 0 عند range=0 وبقاء [0,1] لشموع سليمة."""

    def test_manual(self) -> None:
        s = spread_to_range(arr(1.0, 2.0), arr(2.0, 4.0))
        assert s[0] == 0.5
        assert s[1] == 0.5

    def test_zero_range_gives_zero_even_with_body(self) -> None:
        s = spread_to_range(arr(5.0, 0.0), arr(0.0, 4.0))
        assert s[0] == 0.0  # عقد الشمعة المسطحة
        assert s[1] == 0.0

    def test_negative_body_uses_absolute(self) -> None:
        s = spread_to_range(arr(-2.0), arr(4.0))
        assert s[0] == 0.5

    def test_full_body_and_doji_bounds(self) -> None:
        s = spread_to_range(arr(4.0, 0.0), arr(4.0, 4.0))
        assert s[0] == 1.0
        assert s[1] == 0.0

    def test_nan_range_propagates(self) -> None:
        s = spread_to_range(arr(1.0), arr(np.nan))
        assert np.isnan(s[0])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="أطوال"):
            spread_to_range(arr(1.0, 2.0), arr(1.0))
