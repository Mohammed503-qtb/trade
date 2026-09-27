"""اختبارات وحدة النوافذ الخلفية (المهمة 2.1 — §16).

قيم محسوبة يدويًا:
- مئيني متدحرج: أفضل/أسوأ حالة = 1.0/0.0، وعقد التساوي التام (0.0)،
  واستبعاد عناصر nan من البسط والمقام.
- z-score يدويًا مع حارس القسمة (تباين صفري ⇒ nan لا inf).
- متوسط/انحراف يطابقان np.mean/np.std لكل نافذة حرفيًا.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray
from quantmath import rolling_mean, rolling_percentile, rolling_std, rolling_zscore


def arr(*xs: float) -> NDArray[np.float64]:
    """متجه float64 — عقد الدقة المعلنة للحزمة."""
    out: NDArray[np.float64] = np.asarray(xs, dtype=np.float64)
    return out


class TestRollingPercentile:
    """المئيني ضمن نافذة خلفية شاملة للقيمة الحالية — العقد الموثق حرفيًا."""

    def test_manual_values(self) -> None:
        # i=2: نافذة [5,1,3]، القيمة 3 تعلو 1 فقط من عضويْن ⇒ 0.5
        # i=3: نافذة [1,3,2]، القيمة 2 تعلو 1 فقط ⇒ 0.5
        pct = rolling_percentile(arr(5.0, 1.0, 3.0, 2.0), window=3)
        assert np.isnan(pct[:2]).all()
        assert pct[2] == 0.5
        assert pct[3] == 0.5

    def test_best_case_is_one(self) -> None:
        # القيمة تعلو كل نافذتها قطعيًا في الموضعين المحسوبين
        pct = rolling_percentile(arr(1.0, 2.0, 3.0, 4.0), window=3)
        assert pct[2] == 1.0
        assert pct[3] == 1.0

    def test_worst_case_is_zero(self) -> None:
        # القيمة لا تعلو أي سابق (انكماش كامل)
        pct = rolling_percentile(arr(4.0, 3.0, 2.0, 1.0), window=3)
        assert pct[2] == 0.0
        assert pct[3] == 0.0

    def test_all_equal_gives_zero(self) -> None:
        # عقد التساوي: سلسلة ثابتة ⇒ 0.0 (لا تعلو أي سابق قطعيًا)
        pct = rolling_percentile(arr(2.0, 2.0, 2.0, 2.0), window=3)
        assert np.isnan(pct[:2]).all()
        assert pct[2] == 0.0
        assert pct[3] == 0.0

    def test_warmup_all_nan_when_never_complete(self) -> None:
        pct = rolling_percentile(arr(1.0, 2.0, 3.0), window=4)
        assert np.isnan(pct).all()

    def test_nan_members_excluded(self) -> None:
        # نافذة [nan,1,2]: finite=[1,2] والقيمة 2 تعلو 1 من عضوٍ واحد ⇒ 1.0
        pct = rolling_percentile(arr(np.nan, 1.0, 2.0), window=3)
        assert pct[2] == 1.0

    def test_insufficient_finite_gives_nan(self) -> None:
        # نافذة [nan,nan,5]: عضو محدود واحد ⇒ المقام صفر ⇒ nan
        pct = rolling_percentile(arr(np.nan, np.nan, 5.0), window=3)
        assert np.isnan(pct[2])

    def test_window_validation(self) -> None:
        with pytest.raises(ValueError, match="window"):
            rolling_percentile(arr(1.0, 2.0), window=1)
        with pytest.raises(ValueError, match="window"):
            rolling_percentile(arr(1.0, 2.0), window=0)


class TestRollingZscore:
    """z-score مقابل النافذة الشاملة — مع حارس القسمة على تباين صفري."""

    def test_manual(self) -> None:
        # نافذة [1,2,3]: mean=2, std(ddof=1)=1 ⇒ z=(3−2)/1 = 1.0
        z = rolling_zscore(arr(1.0, 2.0, 3.0), window=3)
        assert np.isnan(z[:2]).all()
        assert z[2] == 1.0

    def test_manual_second_window(self) -> None:
        # i=3: نافذة [2,3,10]: mean=5, std=√19 ⇒ z=5/√19
        z = rolling_zscore(arr(1.0, 2.0, 3.0, 10.0), window=3)
        assert z[3] == 5.0 / float(np.std(arr(2.0, 3.0, 10.0), ddof=1))

    def test_zero_std_guard_gives_nan(self) -> None:
        # نافذة ثابتة تمامًا: 0/0 ⇒ nan (لا inf) — حارس القسمة
        z = rolling_zscore(arr(2.0, 2.0, 2.0), window=3)
        assert np.isnan(z[2])

    def test_warmup_nan(self) -> None:
        z = rolling_zscore(arr(1.0, 2.0), window=3)
        assert np.isnan(z).all()

    def test_window_validation(self) -> None:
        with pytest.raises(ValueError, match="window"):
            rolling_zscore(arr(1.0, 2.0), window=1)


class TestRollingMean:
    """المتوسط المتدحرج — مطابقة يدوية + استبعاد nan + هوية window=1."""

    def test_manual(self) -> None:
        m = rolling_mean(arr(1.0, 2.0, 3.0, 4.0), window=2)
        assert np.isnan(m[0])
        assert m[1] == 1.5
        assert m[2] == 2.5
        assert m[3] == 3.5

    def test_window_one_is_identity(self) -> None:
        values = arr(7.0, -3.0, 0.5)
        assert np.array_equal(rolling_mean(values, window=1), values)

    def test_nan_members_excluded(self) -> None:
        # نافذة [nan,4,2]: متوسط العضويْن المحدودين = 3.0
        m = rolling_mean(arr(np.nan, 4.0, 2.0), window=3)
        assert m[2] == 3.0

    def test_window_validation(self) -> None:
        with pytest.raises(ValueError, match="window"):
            rolling_mean(arr(1.0), window=0)


class TestRollingStd:
    """الانحراف المعياري المتدحرج — يطابق np.std لكل نافذة حرفيًا."""

    def test_matches_numpy_per_window(self) -> None:
        values = arr(1.0, 2.0, 3.0, 4.0)
        s = rolling_std(values, window=3)
        assert np.isnan(s[:2]).all()
        assert s[2] == float(np.std(values[:3], ddof=1))
        assert s[3] == float(np.std(values[1:4], ddof=1))

    def test_manual_two_elements(self) -> None:
        # نافذة [3,7]: std = √(((3−5)²+(7−5)²)/1) = √8
        s = rolling_std(arr(3.0, 7.0), window=2)
        assert s[1] == float(np.sqrt(8.0))

    def test_insufficient_finite_gives_nan(self) -> None:
        # نافذة [nan,nan,nan,5]: عضو محدود واحد وddof=1 ⇒ nan
        s = rolling_std(arr(np.nan, np.nan, np.nan, 5.0), window=4)
        assert np.isnan(s[3])

    def test_window_one_raises_with_default_ddof(self) -> None:
        with pytest.raises(ValueError, match="window"):
            rolling_std(arr(1.0, 2.0), window=1)

    def test_ddof_zero_single_element_is_zero(self) -> None:
        s = rolling_std(arr(5.0), window=1, ddof=0)
        assert s[0] == 0.0
