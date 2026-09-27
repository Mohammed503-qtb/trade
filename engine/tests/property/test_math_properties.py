"""اختبارات خصائص حزمة quantmath (المهمة 2.1) — §16 و§26.3 و§38.

الخصائص المفروضة على كل العائلة:
- **لا نظرة مستقبلية**: خرج البادئة [0..k] لا يتغير أبدًا عند تعديل ذيل
  المدخلات (جوهر §26.3 — سيُعاد استخدامها في كل كواشف المراحل 2 و3).
- **الحتمية الصرفة**: استدعاءان متطابقان ⇒ نفس البايتات (nan بنمط
  البتات نفسه) — لا عشوائية في الحزمة إطلاقًا.
- **النطاقات**: ATR ≥ 0 وnan في الدافئ فقط؛ المئينيات ∈ [0,1]؛
  ‎|z| ≤ √(window−1)‏؛ spread_to_range ∈ [0,1] لشموع سليمة.
- **الرتابة**: قيمة حالية أكبر ⇒ مئيني لا يصغر.
- **saturation_run/is_saturated** يطابقان مرجعًا يدويًا مستقلًا (oracle).

على نمط tests/property/test_schemas_bounds.py مع derandomize=True
(بذرة حتمية — ثقافة test_candles.py للخصائص الحسابية).
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from numpy.typing import NDArray
from quantmath import (
    atr_percentile,
    expected_holding_vol,
    gap_shock,
    is_saturated,
    range_expansion_percentile,
    realized_volatility,
    rolling_mean,
    rolling_percentile,
    rolling_std,
    rolling_zscore,
    saturation_run,
    spread_to_range,
    true_range,
    vol_of_vol,
    wilder_atr,
)

# ─── استراتيجيات ───

finite = st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)
nonneg = st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False)
positive = st.floats(min_value=1e-6, max_value=1e4, allow_nan=False, allow_infinity=False)
maybe_nonfinite = st.one_of(
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    st.just(float("nan")),
    st.just(float("inf")),
    st.just(float("-inf")),
)
series = st.lists(finite, min_size=12, max_size=24)
small_window = st.integers(min_value=2, max_value=6)
k_offset = st.integers(min_value=0, max_value=30)


# ─── مساعدات ───


def to_np(values: list[float]) -> NDArray[np.float64]:
    """متجه float64 — عقد الدقة المعلنة."""
    out: NDArray[np.float64] = np.asarray(values, dtype=np.float64)
    return out


def to_ohlc(
    closes: list[float], spreads: list[float]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """شموع سليمة: high = close+spread، low = close−spread (spread ≥ 0)."""
    c = to_np(closes)
    s = to_np(spreads)
    return c + s, c - s, c


def mutated_tail(values: list[float], k: int) -> list[float]:
    """نسخة يتغير ذيلها جذريًا بعد k — أي تأثير للذيل يكسر اللا-نظرة-المستقبلية."""
    tail = [v * -1.7 + 3.3 for v in reversed(values[k + 1 :])]
    return values[: k + 1] + tail


def assert_prefix_stable[Arr: (NDArray[np.float64], NDArray[np.bool_])](
    name: str, left: Arr, right: Arr, k: int
) -> None:
    """البادئة [0..k] من مخرجين على مدخلين متطابقي الرأس يجب أن تتطابق."""
    assert np.array_equal(left[: k + 1], right[: k + 1], equal_nan=True), (
        f"{name} نظرت المستقبل: خرج البادئة تغيّر بتعديل الذيل"
    )


# ─── §26.3: لا نظرة مستقبلية ───


class TestNoLookahead:
    """خرج البادئة [0..k] لا يتغير عند تعديل الذيل (k+1..)."""

    @given(values=series, window=small_window, k_raw=k_offset)
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_rolling_family(self, values: list[float], window: int, k_raw: int) -> None:
        n = len(values)
        k = min(max(k_raw, window - 1), n - 2)
        x, y = to_np(values), to_np(mutated_tail(values, k))
        assert_prefix_stable("rolling_mean", rolling_mean(x, window), rolling_mean(y, window), k)
        assert_prefix_stable(
            "rolling_percentile", rolling_percentile(x, window), rolling_percentile(y, window), k
        )
        assert_prefix_stable(
            "rolling_zscore", rolling_zscore(x, window), rolling_zscore(y, window), k
        )
        assert_prefix_stable("rolling_std", rolling_std(x, window), rolling_std(y, window), k)

    @given(
        closes=series,
        spreads=st.lists(nonneg, min_size=12, max_size=24),
        period=st.integers(min_value=1, max_value=6),
        window=small_window,
        k_raw=k_offset,
    )
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_atr_family(
        self,
        closes: list[float],
        spreads: list[float],
        period: int,
        window: int,
        k_raw: int,
    ) -> None:
        n = min(len(closes), len(spreads))
        k = min(max(k_raw, max(period, window - 1)), n - 2)
        h1, l1, c1 = to_ohlc(closes[:n], spreads[:n])
        h2, l2, c2 = to_ohlc(mutated_tail(closes, k)[:n], mutated_tail(spreads, k)[:n])
        tr1, tr2 = true_range(h1, l1, c1), true_range(h2, l2, c2)
        assert_prefix_stable("true_range", tr1, tr2, k)
        a1, a2 = wilder_atr(tr1, period), wilder_atr(tr2, period)
        assert_prefix_stable("wilder_atr", a1, a2, k)
        assert_prefix_stable(
            "atr_percentile", atr_percentile(a1, window), atr_percentile(a2, window), k
        )

    @given(
        returns_=series,
        ranges_=series,
        vols_=series,
        opens_=series,
        atrs_=series,
        window=small_window,
        k_raw=k_offset,
    )
    @hyp_settings(max_examples=25, deadline=None, derandomize=True)
    def test_volatility_family(
        self,
        returns_: list[float],
        ranges_: list[float],
        vols_: list[float],
        opens_: list[float],
        atrs_: list[float],
        window: int,
        k_raw: int,
    ) -> None:
        n = min(len(returns_), len(ranges_), len(vols_), len(opens_), len(atrs_))
        k = min(max(k_raw, window - 1), n - 2)
        r1, r2 = to_np(returns_[:n]), to_np(mutated_tail(returns_, k)[:n])
        g1, g2 = to_np(ranges_[:n]), to_np(mutated_tail(ranges_, k)[:n])
        v1, v2 = to_np(vols_[:n]), to_np(mutated_tail(vols_, k)[:n])
        o1, o2 = to_np(opens_[:n]), to_np(mutated_tail(opens_, k)[:n])
        a1, a2 = to_np(atrs_[:n]), to_np(mutated_tail(atrs_, k)[:n])
        assert_prefix_stable(
            "realized_volatility",
            realized_volatility(r1, window),
            realized_volatility(r2, window),
            k,
        )
        assert_prefix_stable(
            "range_expansion_percentile",
            range_expansion_percentile(g1, window),
            range_expansion_percentile(g2, window),
            k,
        )
        assert_prefix_stable("vol_of_vol", vol_of_vol(v1, window), vol_of_vol(v2, window), k)
        assert_prefix_stable("spread_to_range", spread_to_range(r1, g1), spread_to_range(r2, g2), k)
        assert_prefix_stable("gap_shock", gap_shock(o1, r1, a1), gap_shock(o2, r2, a2), k)

    @given(
        values=st.lists(maybe_nonfinite, min_size=12, max_size=24),
        bound=finite,
        direction=st.sampled_from(["above", "below"]),
        min_run=st.integers(min_value=1, max_value=5),
        k_raw=k_offset,
    )
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_saturation_family(
        self,
        values: list[float],
        bound: float,
        direction: str,
        min_run: int,
        k_raw: int,
    ) -> None:
        n = len(values)
        k = min(k_raw, n - 2)
        x, y = to_np(values), to_np(mutated_tail(values, k))
        assert_prefix_stable(
            "saturation_run",
            saturation_run(x, bound, direction),
            saturation_run(y, bound, direction),
            k,
        )
        assert_prefix_stable(
            "is_saturated",
            is_saturated(x, bound, direction, min_run),
            is_saturated(y, bound, direction, min_run),
            k,
        )


# ─── الحتمية الصرفة ───


class TestDeterminism:
    """نفس المصفوفة ⇒ نفس المخرجات بايت-بايت (nan بنمط البتات نفسه)."""

    @given(
        values=st.lists(maybe_nonfinite, min_size=8, max_size=16),
        window=small_window,
        period=st.integers(min_value=1, max_value=6),
        bound=finite,
        min_run=st.integers(min_value=1, max_value=4),
    )
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_all_functions_byte_identical(
        self,
        values: list[float],
        window: int,
        period: int,
        bound: float,
        min_run: int,
    ) -> None:
        x, y = to_np(values), to_np(values).copy()
        pairs = [
            (rolling_mean(x, window), rolling_mean(y, window)),
            (rolling_percentile(x, window), rolling_percentile(y, window)),
            (rolling_zscore(x, window), rolling_zscore(y, window)),
            (rolling_std(x, window), rolling_std(y, window)),
            (wilder_atr(x, period), wilder_atr(y, period)),
            (atr_percentile(x, window), atr_percentile(y, window)),
            (realized_volatility(x, window), realized_volatility(y, window)),
            (
                range_expansion_percentile(x, window),
                range_expansion_percentile(y, window),
            ),
            (vol_of_vol(x, window), vol_of_vol(y, window)),
            (spread_to_range(x, x), spread_to_range(y, y)),
            (gap_shock(x, y, x), gap_shock(y, x, y)),
            (saturation_run(x, bound, "above"), saturation_run(y, bound, "above")),
        ]
        for left, right in pairs:
            assert left.tobytes() == right.tobytes()
        sat_l = is_saturated(x, bound, "below", min_run)
        sat_r = is_saturated(y, bound, "below", min_run)
        assert sat_l.tobytes() == sat_r.tobytes()
        assert expected_holding_vol(0.0125, 16) == expected_holding_vol(0.0125, 16)


# ─── النطاقات والمراجع المستقلة ───


class TestTrueRangeProperties:
    """TR يطابق الصيغة الحرفية لـ§16 ويظل غير سالب لشموع سليمة."""

    @given(closes=series, spreads=st.lists(nonneg, min_size=2, max_size=24))
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_matches_oracle_and_non_negative(
        self, closes: list[float], spreads: list[float]
    ) -> None:
        n = min(len(closes), len(spreads))
        h, low, c = to_ohlc(closes[:n], spreads[:n])
        tr = true_range(h, low, c)
        assert tr.shape == (n,)
        assert (tr >= 0).all()
        assert tr[0] == h[0] - low[0]
        expected = [h[0] - low[0]]
        for i in range(1, n):
            expected.append(max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1])))
        np.testing.assert_array_equal(tr, to_np(expected))


class TestWilderAtrProperties:
    """ATR: nan في الدافئ حصرًا، ≥ 0، بذرة = متوسط، والاستدعاء الذاتي حرفي."""

    @given(tr_values=st.lists(nonneg, min_size=12, max_size=24), period=st.integers(1, 8))
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_warmup_bounds_and_recurrence(self, tr_values: list[float], period: int) -> None:
        tr = to_np(tr_values)
        n = len(tr_values)
        atr = wilder_atr(tr, period)
        assert np.isnan(atr[: period - 1]).all()  # الدافئ فقط
        assert np.isfinite(atr[period - 1 :]).all()  # بعده محدود دائمًا
        assert (atr[~np.isnan(atr)] >= 0).all()  # ATR ≥ 0
        assert atr[period - 1] == float(np.mean(tr[:period]))  # البذرة
        for i in range(period, n):  # الاستدعاء الذاتي حرفيًا
            expected = (atr[i - 1] * (period - 1) + tr[i]) / period
            assert atr[i] == expected


class TestPercentileProperties:
    """المئيني ∈ [0,1] وnan في الدافئ، ورتاببته في القيمة الحالية."""

    @given(values=series, window=small_window)
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_bounds_and_warmup(self, values: list[float], window: int) -> None:
        p = rolling_percentile(to_np(values), window)
        assert np.isnan(p[: window - 1]).all()
        body = p[window - 1 :]
        assert np.isfinite(body).all()
        assert ((body >= 0.0) & (body <= 1.0)).all()

    @given(
        base=st.lists(finite, min_size=1, max_size=10),
        x1=finite,
        x2=finite,
    )
    @hyp_settings(max_examples=50, deadline=None, derandomize=True)
    def test_monotone_in_current_value(self, base: list[float], x1: float, x2: float) -> None:
        lo, hi = min(x1, x2), max(x1, x2)
        window = len(base) + 1
        p_lo = rolling_percentile(to_np([*base, lo]), window)[-1]
        p_hi = rolling_percentile(to_np([*base, hi]), window)[-1]
        assert 0.0 <= p_lo <= p_hi <= 1.0


class TestZscoreProperties:
    """z محدود دائمًا: ‎|z| ≤ √(window−1)‏ — الانحراف الشامل يحتوي انحراف الذات."""

    @given(values=series, window=small_window)
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_finite_and_bounded_by_sqrt(self, values: list[float], window: int) -> None:
        z = rolling_zscore(to_np(values), window)
        assert np.isnan(z[: window - 1]).all()
        body = z[window - 1 :]
        assert (np.isfinite(body) | np.isnan(body)).all()  # لا inf أبدًا
        limit = math.sqrt(window - 1) * (1.0 + 1e-9)
        assert (np.abs(body[np.isfinite(body)]) <= limit).all()


class TestSpreadToRangeProperties:
    """نسبة السبر إلى المدى ∈ [0,1] لشموع سليمة (‎|body| ≤ range‎)."""

    @given(
        ranges_=st.lists(nonneg, min_size=1, max_size=24),
        fraction=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=24,
        ),
        flip=st.lists(st.booleans(), min_size=1, max_size=24),
    )
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_within_unit_for_valid_candles(
        self,
        ranges_: list[float],
        fraction: list[float],
        flip: list[bool],
    ) -> None:
        n = min(len(ranges_), len(fraction), len(flip))
        bodies = [(-1.0 if flip[i] else 1.0) * fraction[i] * ranges_[i] for i in range(n)]
        s = spread_to_range(to_np(bodies), to_np(ranges_[:n]))
        for i in range(n):
            if ranges_[i] == 0.0:
                assert s[i] == 0.0
            else:
                assert 0.0 <= s[i] <= 1.0


class TestSaturationOracle:
    """saturation_run/is_saturated يطابقان مرجعًا يدويًا مستقلًا (بما فيه nan)."""

    @given(
        values=st.lists(maybe_nonfinite, min_size=1, max_size=24),
        bound=finite,
        direction=st.sampled_from(["above", "below"]),
    )
    @hyp_settings(max_examples=50, deadline=None, derandomize=True)
    def test_saturation_run_matches_manual_reference(
        self, values: list[float], bound: float, direction: str
    ) -> None:
        runs = saturation_run(to_np(values), bound, direction)
        expected: list[float] = []
        run = 0
        for v in values:
            if math.isnan(v):
                expected.append(math.nan)
                run = 0
                continue
            qualifies = v >= bound if direction == "above" else v <= bound
            run = run + 1 if qualifies else 0
            expected.append(float(run))
        assert np.array_equal(runs, to_np(expected), equal_nan=True)

    @given(
        values=st.lists(maybe_nonfinite, min_size=1, max_size=24),
        bound=finite,
        direction=st.sampled_from(["above", "below"]),
        min_run=st.integers(min_value=1, max_value=5),
    )
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_is_saturated_matches_reference(
        self,
        values: list[float],
        bound: float,
        direction: str,
        min_run: int,
    ) -> None:
        sat = is_saturated(to_np(values), bound, direction, min_run)
        runs = saturation_run(to_np(values), bound, direction).tolist()
        expected = [(not math.isnan(r)) and r >= min_run for r in runs]
        assert sat.tolist() == expected


class TestNonNegativity:
    """المقاييس المعيارية غير سالبة أو nan (لا قيم سالبة مهما كان المدخل)."""

    @given(returns_=series, window=small_window)
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_realized_volatility_non_negative_or_nan(
        self, returns_: list[float], window: int
    ) -> None:
        rv = realized_volatility(to_np(returns_), window)
        assert (np.isnan(rv) | (rv >= 0)).all()

    @given(vols_=st.lists(nonneg, min_size=12, max_size=24), window=small_window)
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_vol_of_vol_non_negative_or_nan(self, vols_: list[float], window: int) -> None:
        vov = vol_of_vol(to_np(vols_), window)
        assert (np.isnan(vov) | (vov >= 0)).all()

    @given(
        opens_=series,
        closes_=series,
        atrs_=st.lists(positive, min_size=12, max_size=24),
    )
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_gap_shock_non_negative_or_nan_with_positive_atr(
        self,
        opens_: list[float],
        closes_: list[float],
        atrs_: list[float],
    ) -> None:
        n = min(len(opens_), len(closes_), len(atrs_))
        gs = gap_shock(to_np(opens_[:n]), to_np(closes_[:n]), to_np(atrs_[:n]))
        assert gs.shape == (n,)
        assert np.isnan(gs[0])
        assert (np.isnan(gs) | (gs >= 0)).all()


class TestExpectedHoldingVolProperties:
    """تحجيم جذر الزمن: تركّب √(a·b) = √a·√b، وهوية شريط واحد، والرتابة."""

    @given(per_bar=nonneg, a=st.integers(min_value=1, max_value=50), b=st.integers(1, 50))
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_sqrt_time_composition_and_identity(self, per_bar: float, a: int, b: int) -> None:
        assert expected_holding_vol(per_bar, 1) == per_bar
        direct = expected_holding_vol(per_bar, a * b)
        composed = expected_holding_vol(expected_holding_vol(per_bar, a), b)
        assert math.isclose(direct, composed, rel_tol=1e-12)

    @given(per_bar=nonneg, a=st.integers(1, 50), b=st.integers(1, 50))
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_monotone_in_horizon(self, per_bar: float, a: int, b: int) -> None:
        lo, hi = min(a, b), max(a, b)
        assert expected_holding_vol(per_bar, lo) <= expected_holding_vol(per_bar, hi)
