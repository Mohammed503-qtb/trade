"""اختبارات مصفوفة الجهد مقابل النتيجة — بوابة المهمة 4.4 الحرفية (§12.2).

منهاج البوابة: «مصفوفة الحالات الأربع (§12.2)» بالحالات الأربع المولدة
يدويًا (جهد كبير/صغير × استجابة قوية/ضعيفة عبر صناعة delta_share و
close−open وatr وهمية) + «INSUFFICIENT_VOLATILITY» + «اختبار خاصية اكتمال
التغطية» (كل مدخل صالح ∈ الحالات الخمس حصرًا وتقسيم حصري — hypothesis
بذر مثبت) + «خطية العتبة» (مضاعفة atr×2 مع مضاعفة close−open×2 ⇒ نفس
التصنيف — عتبة تطبيعية §16).

هندسة المصغّرات: atr=1.0 افتراضيًا فالعتبة الافتراضية
``FLOW_RESPONSE_MIN = atr × 0.5 = 0.5`` سعرًا، و``EFFORT_MIN_SHARE = 0.4``؛
القيم العشرية المختارة (buy=80/sell=20 ⇒ share=0.6 بالضبط) تجعل كل خلية
قابلة للحساب اليدوي، والحدود المغلقة (≥) تُختبر عند الحد بالضبط.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from market_state.volatility import VolatilityState
from orderflow.effort import (
    EFFORT_MIN_SHARE,
    EffortResultState,
    FlowGuards,
    bar_delta_share,
    check_flow_inputs,
    classify_effort_vs_result,
    directional_response,
    efficiency,
    usable_atr,
)
from orderflow.rows import METHODOLOGY_AGGTRADE_TAKER
from schemas import Candle, DataQuality, FootprintBar

# ═══════════ المصغّرات ═══════════

BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def make_candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    """شمعة مكتملة كاملة الحقول — كل المشتقات من OHLC الخام المتسق."""
    if high < max(open_, close) or low > min(open_, close):
        raise ValueError(
            f"أطراف خارج المدى: OHLC=({open_}, {high}, {low}, {close}) — "
            "يجب أن يحتوي [low, high] الافتتاحَ والإغلاقَ (عقد §8.1)"
        )
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span if span > 0.0 else 0.0,
        close_location_value=(close - low) / span if span > 0.0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def make_fp_bar(
    index: int,
    buy: float,
    sell: float,
    *,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> FootprintBar:
    """شريط فوتبرنت متسق: delta = buy−sell وtotal = buy+sell (عقد البنّاء).

    حقول poc/vah/val الشكلية لا يقرؤها المصنف — قياسه delta/total حصرًا.
    """
    total = buy + sell
    return FootprintBar(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        source_feed="binance-aggTrades",
        methodology=METHODOLOGY_AGGTRADE_TAKER,
        buy_volume=buy,
        sell_volume=sell,
        total_volume=total,
        delta=buy - sell,
        buy_share=buy / total if total > 0.0 else 0.0,
        sell_share=sell / total if total > 0.0 else 0.0,
        poc=100.0,
        vah=101.0,
        val=99.0,
        row_count=3,
        buy_imbalance_count=0,
        sell_imbalance_count=0,
    )


def make_vol(atr: float | None, *, bar_time: datetime | None = None) -> VolatilityState:
    """حالة تقلب مصنوعة — ما يقرؤه المصنف منها حصرًا: atr والطابع والعتبات."""
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=0.001,
        range_expansion_percentile=0.5,
        vol_of_vol=0.1,
        gap_shock=0.0,
        spread_to_range=0.5,
        expected_holding_vol_1h=0.001,
        bar_time=bar_time,
    )


#: أشرطة المصفوفة: جهد كبير (share=±0.6) وصغير (share=±0.2) بالاتجاهين.
_EFFORT_LARGE = (80.0, 20.0)  # share = +0.6
_EFFORT_SMALL = (60.0, 40.0)  # share = +0.2
_EFFORT_LARGE_SELL = (20.0, 80.0)  # share = -0.6
_EFFORT_SMALL_SELL = (40.0, 60.0)  # share = -0.2

# ═══════════ المصفوفة الأربع §12.2 — الحالات الأربع مولّدة يدويًا ═══════════


class TestEffortResultMatrix:
    """الخلايا الأربع بالاتجاهين + الدلتا المعدومة والشريط الفارغ."""

    @pytest.mark.parametrize(
        ("buy", "sell", "body", "expected"),
        [
            # جهد كبير × استجابة قوية ⇒ توافق
            (80.0, 20.0, 0.8, EffortResultState.AGREE_EFFORT_RESULT),
            # جهد كبير × استجابة ضعيفة ⇒ «امتصاص محتمل/شراء عالق» (فرضية §12.2)
            (80.0, 20.0, 0.2, EffortResultState.EFFORT_NO_RESULT),
            # جهد صغير × استجابة قوية ⇒ حركة بلا عدوانية
            (60.0, 40.0, 0.8, EffortResultState.RESULT_NO_EFFORT),
            # كلاهما ضعيف
            (60.0, 40.0, 0.2, EffortResultState.LOW_EFFORT_LOW_RESULT),
        ],
        ids=["agree", "effort-no-result", "result-no-effort", "low-low"],
    )
    def test_buy_side_matrix_cells(
        self, buy: float, sell: float, body: float, expected: EffortResultState
    ) -> None:
        """الجهة الشرائية: body موجب = استجابة صاعدة close−open."""
        bar = make_fp_bar(0, buy, sell)
        candle = make_candle(0, 100.0, 100.0 + max(body, 0.0), 100.0, 100.0 + body)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is expected

    @pytest.mark.parametrize(
        ("buy", "sell", "body", "expected"),
        [
            (20.0, 80.0, -0.8, EffortResultState.AGREE_EFFORT_RESULT),
            (20.0, 80.0, -0.2, EffortResultState.EFFORT_NO_RESULT),
            (40.0, 60.0, -0.8, EffortResultState.RESULT_NO_EFFORT),
            (40.0, 60.0, -0.2, EffortResultState.LOW_EFFORT_LOW_RESULT),
        ],
        ids=["agree-sell", "effort-no-result-sell", "result-no-effort-sell", "low-low-sell"],
    )
    def test_sell_side_mirror_matrix_cells(
        self, buy: float, sell: float, body: float, expected: EffortResultState
    ) -> None:
        """المرآة البيعية: الاستجابة باتجاه الدلتا = open−close."""
        bar = make_fp_bar(0, buy, sell)
        candle = make_candle(0, 100.0, 100.0, 100.0 + min(body, 0.0), 100.0 + body)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is expected

    def test_buy_aggression_with_adverse_close_is_effort_no_result(self) -> None:
        """إيجابية دلتا بإغلاق هابط: الاستجابة باتجاه الجهد سالبة ⇒ ضعيفة دومًا."""
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.5, 98.0, 98.5)  # هبوط معاكس للجهد الشرائي
        assert (
            classify_effort_vs_result(bar, candle, make_vol(1.0))
            is EffortResultState.EFFORT_NO_RESULT
        )

    def test_zero_delta_response_declared_zero(self) -> None:
        """الدلتا المعدومة لا اتجاه لجهدِها ⇒ استجابة صفر معلن — ولو ضخم الجسم.

        جهد صغير (0) × استجابة ضعيفة (0) ⇒ LOW_EFFORT_LOW_RESULT بعقد التعريف.
        """
        bar = make_fp_bar(0, 50.0, 50.0)
        candle = make_candle(0, 100.0, 102.0, 100.0, 102.0)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.LOW_EFFORT_LOW_RESULT
        )

    def test_empty_bar_zero_effort_declared(self) -> None:
        """شريط بلا صفقات (total=0, delta=0): جهد صفر معلن — لا عدوانية تُقاس."""
        bar = make_fp_bar(0, 0.0, 0.0)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.LOW_EFFORT_LOW_RESULT
        )


# ═══════════ بوابة §16: لا قرار بلا تقلب ═══════════


class TestInsufficientVolatility:
    """vol غائب أو ATR غائب/منحل ⇒ INSUFFICIENT_VOLATILITY — لا قيمة مزيفة."""

    def test_vol_none(self) -> None:
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        assert classify_effort_vs_result(bar, candle, None) is (
            EffortResultState.INSUFFICIENT_VOLATILITY
        )

    def test_atr_none_warmup(self) -> None:
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        assert classify_effort_vs_result(bar, candle, make_vol(None)) is (
            EffortResultState.INSUFFICIENT_VOLATILITY
        )

    @pytest.mark.parametrize(
        "atr", [0.0, -1.0, float("nan"), float("inf")], ids=["zero", "neg", "nan", "inf"]
    )
    def test_degenerate_atr_is_absence(self, atr: float) -> None:
        """ATR منحل = غياب (الرفض لا القسمة) — حتى المعامِلات لا تُطبَّق."""
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        assert classify_effort_vs_result(bar, candle, make_vol(atr)) is (
            EffortResultState.INSUFFICIENT_VOLATILITY
        )


# ═══════════ الحدود المغلقة (≥) — بلوغ الحد بالضبط يمر ═══════════


class TestInclusiveBoundaries:
    """المقارنات مغلقة: الجهد عند 0.4 كبير والاستجابة عند العتبة قوية."""

    def test_effort_exactly_at_min_is_large(self) -> None:
        """buy=70/sell=30 ⇒ share=0.4 بالضبط = EFFORT_MIN_SHARE."""
        bar = make_fp_bar(0, 70.0, 30.0)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.AGREE_EFFORT_RESULT
        )

    def test_response_exactly_at_threshold_is_strong(self) -> None:
        """استجابة 0.5 = atr×0.5 بالضبط — حد مغلق."""
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.5, 100.0, 100.5)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.AGREE_EFFORT_RESULT
        )

    def test_response_exactly_at_threshold_small_effort(self) -> None:
        bar = make_fp_bar(0, *_EFFORT_SMALL)
        candle = make_candle(0, 100.0, 100.5, 100.0, 100.5)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.RESULT_NO_EFFORT
        )

    def test_just_below_both_boundaries_is_low_low(self) -> None:
        """0.399 دون حد الجهد و0.499 دون العتبة (عند atr=1.0) — كلاهما ضعيف."""
        bar = make_fp_bar(0, 69.9, 30.1)  # share ≈ 0.398
        candle = make_candle(0, 100.0, 100.499, 100.0, 100.499)
        assert classify_effort_vs_result(bar, candle, make_vol(1.0)) is (
            EffortResultState.LOW_EFFORT_LOW_RESULT
        )


# ═══════════ تجاوز معامل العتبة (response_min_mult) ═══════════


class TestResponseMultiplierOverride:
    """التجاوز يفوز على الافتراضي 0.5 — والفاسد يُرفض صاخبًا دائمًا."""

    def test_raised_threshold_flips_strong_to_weak(self) -> None:
        """عتبة 2.0×atr: استجابة 0.8 كانت قوية صارت ضعيفة."""
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        result = classify_effort_vs_result(bar, candle, make_vol(1.0), response_min_mult=2.0)
        assert result is EffortResultState.EFFORT_NO_RESULT

    def test_lowered_threshold_flips_weak_to_strong(self) -> None:
        """عتبة 0.1×atr: استجابة 0.2 كانت ضعيفة صارت قوية."""
        bar = make_fp_bar(0, *_EFFORT_SMALL)
        candle = make_candle(0, 100.0, 100.2, 100.0, 100.2)
        result = classify_effort_vs_result(bar, candle, make_vol(1.0), response_min_mult=0.1)
        assert result is EffortResultState.RESULT_NO_EFFORT

    @pytest.mark.parametrize(
        "bad", [0.0, -1.0, float("nan"), float("inf")], ids=["zero", "neg", "nan", "inf"]
    )
    def test_invalid_override_rejected_even_without_vol(self, bad: float) -> None:
        """المدخل الفاسد يُرفض حتى عند غياب التقلب — لا يُبتلع صمتًا."""
        bar = make_fp_bar(0, *_EFFORT_LARGE)
        candle = make_candle(0, 100.0, 100.8, 100.0, 100.8)
        with pytest.raises(ValueError, match="معامل تجاوز غير صالح"):
            classify_effort_vs_result(bar, candle, None, response_min_mult=bad)


# ═══════════ دالة الكفاءة §20 (Delta efficiency) ═══════════


class TestEfficiencyFunction:
    """``response_atr / |delta_share|`` — صرفة، والجهد الصفري يُرفض صاخبًا."""

    @pytest.mark.parametrize(
        ("response_atr", "share_abs", "expected"),
        [(1.0, 0.5, 2.0), (0.0, 0.5, 0.0), (-1.0, 0.5, -2.0), (0.3, 0.1, 3.0)],
    )
    def test_ratio_values(self, response_atr: float, share_abs: float, expected: float) -> None:
        assert efficiency(response_atr, share_abs) == pytest.approx(expected)

    def test_negative_response_negative_efficiency(self) -> None:
        """الاستجابة المعاكسة ⇒ كفاءة سالبة — القيمة الصرفة صادقة الإشارة."""
        assert efficiency(-0.7, 0.7) == pytest.approx(-1.0)

    @pytest.mark.parametrize(
        ("response_atr", "share_abs"),
        [
            (1.0, 0.0),
            (1.0, -0.5),
            (1.0, float("nan")),
            (float("nan"), 0.5),
            (float("inf"), 0.5),
        ],
        ids=["zero-effort", "neg-effort", "nan-effort", "nan-response", "inf-response"],
    )
    def test_invalid_inputs_rejected(self, response_atr: float, share_abs: float) -> None:
        with pytest.raises(ValueError, match=r"كفاءة|غير محدودة"):
            efficiency(response_atr, share_abs)


# ═══════════ بدائل القياس: usable_atr / bar_delta_share / directional_response ═══════════


class TestMeasurementPrimitives:
    """العقود الصغيرة: الانحلال غياب، والاتساق شرط، والاتجاه ±1 حصرًا."""

    @pytest.mark.parametrize(
        ("atr", "expected"),
        [
            (None, None),
            (2.0, 2.0),
            (0.0, None),
            (-1.0, None),
            (float("nan"), None),
            (float("inf"), None),
        ],
        ids=["none", "valid", "zero", "neg", "nan", "inf"],
    )
    def test_usable_atr(self, atr: float | None, expected: float | None) -> None:
        assert usable_atr(make_vol(atr)) == expected

    def test_usable_atr_none_vol(self) -> None:
        assert usable_atr(None) is None

    def test_bar_delta_share_values(self) -> None:
        assert bar_delta_share(make_fp_bar(0, 80.0, 20.0)) == pytest.approx(0.6)
        assert bar_delta_share(make_fp_bar(0, 20.0, 80.0)) == pytest.approx(-0.6)
        assert bar_delta_share(make_fp_bar(0, 0.0, 0.0)) == 0.0

    def test_inconsistent_bar_rejected(self) -> None:
        """|delta| > الحجم الكلي تناقض قانوني — لا تصحيح صامت."""
        bar = make_fp_bar(0, 30.0, 10.0)
        broken = bar.model_copy(update={"delta": 100.0})
        with pytest.raises(ValueError, match="غير متسق"):
            bar_delta_share(broken)

    def test_nan_delta_rejected(self) -> None:
        bar = make_fp_bar(0, 30.0, 10.0)
        broken = bar.model_copy(update={"delta": float("nan")})
        with pytest.raises(ValueError, match="غير محدودة"):
            bar_delta_share(broken)

    def test_directional_response_values(self) -> None:
        candle = make_candle(0, 100.0, 101.0, 99.0, 100.5)
        assert directional_response(candle, 1) == pytest.approx(0.5)
        assert directional_response(candle, -1) == pytest.approx(-0.5)

    @pytest.mark.parametrize("bad", [0, 2, -2], ids=["zero", "two", "neg-two"])
    def test_directional_response_rejects_bad_direction(self, bad: int) -> None:
        candle = make_candle(0, 100.0, 101.0, 99.0, 100.5)
        with pytest.raises(ValueError, match="اتجاه غير صالح"):
            directional_response(candle, bad)


# ═══════════ الحارس الصرف: الثنائية والإغلاق ولا-نظرة §26.3 ═══════════


class TestPureInputGuards:
    """check_flow_inputs عبر classify: كل خرق ValueError صاخب."""

    def _pair(self) -> tuple[FootprintBar, Candle]:
        return make_fp_bar(0, 80.0, 20.0), make_candle(0, 100.0, 100.8, 100.0, 100.8)

    def test_evolving_bar_rejected(self) -> None:
        _, candle = self._pair()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            classify_effort_vs_result(
                make_fp_bar(0, 80.0, 20.0, is_closed=False), candle, make_vol(1.0)
            )

    def test_evolving_candle_rejected(self) -> None:
        bar, _ = self._pair()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            classify_effort_vs_result(
                bar, make_candle(0, 100.0, 100.8, 100.0, 100.8, is_closed=False), make_vol(1.0)
            )

    def test_mismatched_bar_time_rejected(self) -> None:
        bar, _ = self._pair()
        late_candle = make_candle(1, 100.0, 100.8, 100.0, 100.8)
        with pytest.raises(ValueError, match="طابع لا يطابق"):
            classify_effort_vs_result(bar, late_candle, make_vol(1.0))

    def test_mismatched_instrument_rejected(self) -> None:
        bar, _ = self._pair()
        foreign = make_candle(0, 100.0, 100.8, 100.0, 100.8, instrument_id="OTHER:XYZ")
        with pytest.raises(ValueError, match="تغذية غير متسقة"):
            classify_effort_vs_result(bar, foreign, make_vol(1.0))

    def test_mismatched_timeframe_rejected(self) -> None:
        bar, _ = self._pair()
        foreign = make_candle(0, 100.0, 100.8, 100.0, 100.8, timeframe="5m")
        with pytest.raises(ValueError, match="تغذية غير متسقة"):
            classify_effort_vs_result(bar, foreign, make_vol(1.0))

    def test_future_volatility_rejected(self) -> None:
        bar, candle = self._pair()
        future = make_vol(1.0, bar_time=BASE_TIME + timedelta(minutes=3))
        with pytest.raises(ValueError, match="من المستقبل"):
            classify_effort_vs_result(bar, candle, future)

    def test_older_volatility_allowed(self) -> None:
        """الحالة الأقدم مسموحة — قيمها الدافئة تعلن نفسها (عقد الحارس)."""
        bar, candle = self._pair()
        older = make_vol(1.0, bar_time=BASE_TIME - timedelta(minutes=5))
        assert (
            classify_effort_vs_result(bar, candle, older) is EffortResultState.AGREE_EFFORT_RESULT
        )

    def test_direct_check_flow_inputs_contract(self) -> None:
        bar, candle = self._pair()
        check_flow_inputs(bar, candle, make_vol(1.0))  # الثلاثية السليمة تمر
        with pytest.raises(ValueError, match="طابع لا يطابق"):
            check_flow_inputs(bar, make_candle(2, 100.0, 100.8, 100.0, 100.8), None)


# ═══════════ حارس التدفق الموضعي: الهوية والترتيب ═══════════


class TestFlowGuardsStateful:
    """FlowGuards: هوية واحدة وترتيب تصاعدي قطعي — الرفض القانوني الصاخب."""

    def _steps(self) -> list[tuple[FootprintBar, Candle, VolatilityState]]:
        return [
            (make_fp_bar(i, 60.0, 40.0), make_candle(i, 100.0, 100.3, 99.9, 100.1), make_vol(1.0))
            for i in range(3)
        ]

    def test_ascending_stream_passes(self) -> None:
        guards = FlowGuards()
        for bar, candle, vol in self._steps():
            guards.check(bar, candle, vol)
        assert guards.instrument_id == INSTRUMENT
        assert guards.timeframe == TIMEFRAME

    def test_identity_captured_from_first_bar(self) -> None:
        guards = FlowGuards()
        bar, candle, vol = self._steps()[0]
        guards.check(bar, candle, vol)
        assert guards.instrument_id == INSTRUMENT

    def test_duplicate_bar_time_rejected(self) -> None:
        guards = FlowGuards()
        bar, candle, vol = self._steps()[0]
        guards.check(bar, candle, vol)
        with pytest.raises(ValueError, match="تكرار bar_time"):
            guards.check(bar, candle, vol)

    def test_late_bar_rejected(self) -> None:
        guards = FlowGuards()
        steps = self._steps()
        for bar, candle, vol in steps[:2]:
            guards.check(bar, candle, vol)
        with pytest.raises(ValueError, match="متأخر"):
            guards.check(steps[0][0], steps[0][1], steps[0][2])

    def test_mixed_instrument_rejected(self) -> None:
        guards = FlowGuards()
        steps = self._steps()
        guards.check(*steps[0])
        # ثنائية أجنبية متسقة (شريط وشمعة معًا) — يصل حارس الهوية لا حارس الثنائية.
        foreign_bar = make_fp_bar(1, 60.0, 40.0, instrument_id="OTHER:XYZ")
        foreign_candle = make_candle(1, 100.0, 100.3, 99.9, 100.1, instrument_id="OTHER:XYZ")
        with pytest.raises(ValueError, match="خلط أدوات"):
            guards.check(foreign_bar, foreign_candle, steps[1][2])

    def test_mixed_timeframe_rejected(self) -> None:
        guards = FlowGuards()
        steps = self._steps()
        guards.check(*steps[0])
        foreign_bar = make_fp_bar(1, 60.0, 40.0, timeframe="5m")
        foreign_candle = make_candle(1, 100.0, 100.3, 99.9, 100.1, timeframe="5m")
        with pytest.raises(ValueError, match="خلط أطر"):
            guards.check(foreign_bar, foreign_candle, steps[1][2])


# ═══════════ خاصية اكتمال التغطية — بوابة المرحلة نصًا ═══════════


def _matrix_cell(buy: float, sell: float, candle: Candle, atr: float) -> EffortResultState:
    """الخلية المشتقة مستقلة في الاختبار — نفس الحساب الحرفي للمصنِّف.

    الجهد من حقول الشريط ذاتها والاستجابة من حقول الشمعة ذاتها (بترتيب
    العمليات نفسه) فتطابق الخلية المتوقعة مع خرج المصنف بتّي.
    """
    share = bar_delta_share(make_fp_bar(0, buy, sell))
    effort_large = abs(share) >= EFFORT_MIN_SHARE
    if share > 0.0:
        response = candle.close - candle.open
    elif share < 0.0:
        response = candle.open - candle.close
    else:
        response = 0.0
    response_strong = response >= atr * 0.5  # DEFAULT_MULTIPLIERS[FLOW_RESPONSE_MIN] = 0.5
    if effort_large:
        if response_strong:
            return EffortResultState.AGREE_EFFORT_RESULT
        return EffortResultState.EFFORT_NO_RESULT
    if response_strong:
        return EffortResultState.RESULT_NO_EFFORT
    return EffortResultState.LOW_EFFORT_LOW_RESULT


flow_triples = st.fixed_dictionaries(
    {
        "buy": st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        "sell": st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        "body": st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        "up_wick": st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        "down_wick": st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        "atr": st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False),
    }
)


class TestCoverageCompletenessProperty:
    """«اكتمال التغطية»: كل ثلاثية صالحة ∈ حالة واحدة من الخمس حصرًا.

    الخصية تثبت أن التصنيف دالة كاملة على المدخلات الصالحة تطابق خلية
    المصفوفة المشتقة مستقلة (جهد كبير؟ × استجابة قوية؟) — تقسيم حصري
    كامل؛ واختبار الوصول المنفصل يبني مدخلًا لكل حالة من الخمس فيثبت أن
    كل حالة موصولة (لا حالة ميتة). البذر مثبت (derandomize).
    """

    @given(triple=flow_triples)
    @hyp_settings(max_examples=50, deadline=None, derandomize=True)
    def test_every_valid_input_matches_its_matrix_cell(self, triple: dict[str, float]) -> None:
        buy = triple["buy"]
        sell = triple["sell"]
        body = triple["body"]
        open_, close = 100.0, 100.0 + body
        high = max(open_, close) + triple["up_wick"]
        low = min(open_, close) - triple["down_wick"]
        atr = triple["atr"]
        bar = make_fp_bar(0, buy, sell)
        candle = make_candle(0, open_, high, low, close)
        result = classify_effort_vs_result(bar, candle, make_vol(atr))
        # العضوية الحصرية: النتيجة واحدة من الخمس حصرًا وتطابق الخلية المستقلة.
        assert isinstance(result, EffortResultState)
        assert result is _matrix_cell(buy, sell, candle, atr)

    @pytest.mark.parametrize(
        ("state", "triple"),
        [
            (EffortResultState.AGREE_EFFORT_RESULT, (80.0, 20.0, 0.8, 1.0)),
            (EffortResultState.EFFORT_NO_RESULT, (80.0, 20.0, 0.2, 1.0)),
            (EffortResultState.RESULT_NO_EFFORT, (60.0, 40.0, 0.8, 1.0)),
            (EffortResultState.LOW_EFFORT_LOW_RESULT, (60.0, 40.0, 0.2, 1.0)),
            (EffortResultState.INSUFFICIENT_VOLATILITY, (80.0, 20.0, 0.8, None)),
        ],
        ids=["agree", "effort-no-result", "result-no-effort", "low-low", "no-vol"],
    )
    def test_every_state_is_reachable(
        self, state: EffortResultState, triple: tuple[float, float, float, float | None]
    ) -> None:
        """اكتمال التغطية بالاتجاه الآخر: كل حالة من الخمس يبلغها مدخل صالح."""
        buy, sell, body, atr = triple
        bar = make_fp_bar(0, buy, sell)
        candle = make_candle(0, 100.0, 100.0 + max(body, 0.0), 100.0 + min(body, 0.0), 100.0 + body)
        vol = make_vol(atr) if atr is not None else None
        assert classify_effort_vs_result(bar, candle, vol) is state


# ═══════════ خطية العتبة التطبيعية §16 — قوى الأساسين ═══════════


class TestThresholdLinearityProperty:
    """مضاعفة atr×2^k مع تحجيم الشمعة كاملةً بنفس القوة ⇒ نفس التصنيف.

    عتبة §16 تطبيعية خطية صرفة: ``threshold = atr × multiplier`` — تحجيم
    ATR والأسعار معًا بقوة أساسين (‎λ = 2^k‎ عمليات float الدقيقة) يحفظ
    نتيجة المقارنة «سعر بسعر» بتّيًا، فالخلية لا تتغير أبدًا.
    """

    @given(
        buy=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        sell=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        body=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        up_wick=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        down_wick=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        atr=st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False),
        exponent=st.integers(min_value=-3, max_value=3),
    )
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_scaling_atr_and_prices_preserves_classification(
        self,
        buy: float,
        sell: float,
        body: float,
        up_wick: float,
        down_wick: float,
        atr: float,
        exponent: int,
    ) -> None:
        lam = 2.0**exponent
        bar = make_fp_bar(0, buy, sell)  # الحجوم لا تُحجّم — الحصة عديمة البُعد
        base = classify_effort_vs_result(
            bar,
            make_candle(
                0,
                100.0,
                100.0 + max(body, 0.0) + up_wick,
                100.0 + min(body, 0.0) - down_wick,
                100.0 + body,
            ),
            make_vol(atr),
        )
        scaled = classify_effort_vs_result(
            bar,
            make_candle(
                0,
                100.0 * lam,
                (100.0 + max(body, 0.0) + up_wick) * lam,
                (100.0 + min(body, 0.0) - down_wick) * lam,
                (100.0 + body) * lam,
            ),
            make_vol(atr * lam),
        )
        assert scaled is base
