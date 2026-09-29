"""اختبارات عائلات أنماط الشموع الثماني (§13.1) — المهمة 5-b.

بوابة المهمة نصًّا: «fixtures لكل عائلة» — لكل عائلة من الثماني هندسة
موجبة بقيم قوة محسوبة يدويًا + نواقص مانعة مستقلة، ثم الكاشف المبثوث
(الأنواع الثلاثة ذات الأحداث في §20) بحتميته ولا-نظرته وحراسه.

الإعداد في كل الاختبارات: نوافذ دافئ مصغّرة (مئيني 5 وفجوة/حجم 3)
لتقليل الحشو مع بقاء العقود نفسها — الإعداد الافتراضي يختبره فحص
الإعداد وحده.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from patterns.candle_patterns import (
    CandlePatternConfig,
    CandlePatternDetector,
    EmittedEvent,
    classify_doji,
    classify_engulfing,
    classify_expansion,
    classify_hammer_shooting_star,
    classify_inside_bar,
    classify_inside_bar_break,
    classify_last_candle,
    classify_morning_evening_star,
    classify_rejection,
    classify_strong_closing,
)
from schemas import (
    Candle,
    CandlePatternFamily,
    DataQuality,
    EventType,
    PatternDirection,
)

_BASE = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
_INSTRUMENT = "BINANCE_USDM:BTCUSDT"

CFG = CandlePatternConfig(
    range_percentile_window=5,
    gap_relationship_window=3,
    volume_relationship_window=3,
    trend_context_bars=5,
)


def make_candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
    instrument: str = _INSTRUMENT,
    timeframe: str = "1m",
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else _BASE + timedelta(minutes=index),
        session_id="2026-09-29",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=(body / span) if span > 0 else 0.0,
        close_location_value=((close - low) / span) if span > 0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0 else 0.0,
    )


def filler(index: int, level: float = 100.0) -> Candle:
    """شمعة سياق عادية: جسم متوسط، ظلال متوازنة، إغلاق منتصف — دافئ بلا أنماط عرضية."""
    drift = math.sin(index / 3.0) * 2.0
    open_ = level + drift
    close = level + drift * 0.4
    high = max(open_, close) + 0.6
    low = min(open_, close) - 0.6
    return make_candle(index, open_=open_, high=high, low=low, close=close, volume=120.0)


def warmed(n: int) -> list[Candle]:
    """سلسلة سياق كافية الدافئ لإعداد CFG (مئيني 5 ⇒ ≥ 6 شموع)."""
    return [filler(i) for i in range(n)]


# ═══════════════════ الإعداد ═══════════════════


class TestConfig:
    def test_defaults_are_documented_unit_intervals(self) -> None:
        config = CandlePatternConfig()
        assert config.engulfing_body_fraction_min == 0.55
        assert config.rejection_wick_asymmetry_min == 0.60
        assert config.doji_body_fraction_max == 0.10
        assert config.range_percentile_window == 100
        assert config.trend_context_bars == 5

    def test_rejects_out_of_unit_interval(self) -> None:
        with pytest.raises(ValueError, match="engulfing_body_fraction_min"):
            CandlePatternConfig(engulfing_body_fraction_min=1.5)

    def test_rejects_close_location_below_half(self) -> None:
        with pytest.raises(ValueError, match="engulfing_close_location_min"):
            CandlePatternConfig(engulfing_close_location_min=0.4)

    def test_rejects_bad_windows(self) -> None:
        with pytest.raises(ValueError, match="range_percentile_window"):
            CandlePatternConfig(range_percentile_window=1)
        with pytest.raises(ValueError, match="gap_relationship_window"):
            CandlePatternConfig(gap_relationship_window=0)
        with pytest.raises(ValueError, match="trend_context_bars"):
            CandlePatternConfig(trend_context_bars=1)

    def test_frozen(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            CandlePatternConfig().engulfing_body_fraction_min = 0.9  # type: ignore[misc]


# ═══════════════════ الابتلاع (حدثان §20) ═══════════════════


class TestEngulfing:
    def _bullish_pair(self) -> list[Candle]:
        # سابقة هابطة: open=105 close=100 (جسم 5) بمدى 6.5
        prev = make_candle(7, open_=105.0, high=106.0, low=99.5, close=100.0)
        # مبتلعة صاعدة: open=99 close=106 (جسم 7) بمدى 8.5 تغطي [99..106] ⊇ [100..105]
        last = make_candle(8, open_=99.0, high=107.0, low=98.5, close=106.0)
        return [prev, last]

    def test_bullish_positive_with_manual_strength(self) -> None:
        candles = warmed(7) + self._bullish_pair()
        result = classify_engulfing(candles, CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.ENGULFING
        assert result.direction is PatternDirection.BULLISH
        # strength = جسم المبتلعة/(الجسمين معًا) = 7/12
        assert result.strength == pytest.approx(7.0 / 12.0)
        assert result.bar_time == candles[-1].bar_time

    def test_bearish_mirror(self) -> None:
        prev = make_candle(7, open_=100.0, high=106.0, low=99.5, close=105.0)
        last = make_candle(8, open_=106.0, high=107.0, low=98.5, close=99.0)
        result = classify_engulfing([*warmed(7), prev, last], CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH

    def test_same_colors_rejected(self) -> None:
        prev = make_candle(7, open_=100.0, high=106.0, low=99.5, close=105.0)
        last = make_candle(8, open_=99.0, high=107.0, low=98.5, close=106.0)
        assert classify_engulfing([*warmed(7), prev, last], CFG) is None

    def test_doji_engulfed_rejected(self) -> None:
        prev = make_candle(7, open_=102.5, high=103.0, low=102.0, close=102.5)
        last = make_candle(8, open_=99.0, high=107.0, low=98.5, close=106.0)
        assert classify_engulfing([*warmed(7), prev, last], CFG) is None

    def test_weak_close_rejected(self) -> None:
        # مبتلعة صاعدة تغلق في منتصف مداها (إغلاق 0.5 < 0.70)
        prev = make_candle(7, open_=105.0, high=106.0, low=99.5, close=100.0)
        last = make_candle(8, open_=99.0, high=107.0, low=98.5, close=102.0)
        assert classify_engulfing([*warmed(7), prev, last], CFG) is None

    def test_body_not_covering_rejected(self) -> None:
        # جسم الحالية لا يغطي جسم السابقة (فتح أعلى قاع السابقة)
        prev = make_candle(7, open_=105.0, high=106.0, low=99.5, close=100.0)
        last = make_candle(8, open_=100.5, high=107.0, low=98.5, close=106.0)
        assert classify_engulfing([*warmed(7), prev, last], CFG) is None

    def test_weak_engulfing_body_rejected(self) -> None:
        # جسم المبتلعة نحيل: bf = 5/8.8 < 0.55
        prev = make_candle(7, open_=105.0, high=106.0, low=99.5, close=100.0)
        last = make_candle(8, open_=100.0, high=108.0, low=99.2, close=105.0)
        assert classify_engulfing([*warmed(7), prev, last], CFG) is None

    def test_warmup_incomplete_returns_none(self) -> None:
        result = classify_engulfing(self._bullish_pair(), CFG)  # دافئ مئيني 5 غير مكتمل
        assert result is None


# ═══════════════════ الرفض/الدبوس (حدث §20) ═══════════════════


class TestRejection:
    def _bullish_pin(self) -> Candle:
        # ذيل سفلي مهيمن: open=100 close=100.5 high=101 low=95 — bf=0.5/6≈0.083
        return make_candle(8, open_=100.0, high=101.0, low=95.0, close=100.5)

    def test_bullish_positive_with_manual_strength(self) -> None:
        candles = [*warmed(7), self._bullish_pin()]
        result = classify_rejection(candles, CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.PIN_REJECTION
        assert result.direction is PatternDirection.BULLISH
        # strength = الذيل المهيمن/المدى = 5/6
        assert result.strength == pytest.approx(5.0 / 6.0)

    def test_bearish_upper_wick(self) -> None:
        pin = make_candle(8, open_=100.0, high=105.5, low=99.5, close=100.5)
        result = classify_rejection([*warmed(7), pin], CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH
        assert result.strength == pytest.approx(5.0 / 6.0)

    def test_big_body_rejected(self) -> None:
        fat = make_candle(8, open_=95.0, high=101.0, low=94.5, close=100.5)
        assert classify_rejection([*warmed(7), fat], CFG) is None

    def test_balanced_wicks_rejected(self) -> None:
        balanced = make_candle(8, open_=100.0, high=103.0, low=97.0, close=100.5)
        assert classify_rejection([*warmed(7), balanced], CFG) is None


# ═══════════════════ المطرقة/الشهاب (سياقي) ═══════════════════


class TestHammerShootingStar:
    def _hammer_context(self, final_low: float) -> list[Candle]:
        # 4 شموع سياق متناقصة ثم شمعة القرار — قاع جديد فقط مع final_low
        candles = [
            make_candle(
                4 + i,
                open_=100.0 + (4 - i),
                high=101.0 + (4 - i),
                low=99.0 + (4 - i),
                close=99.5 + (4 - i),
            )
            for i in range(4)
        ]
        candles.append(
            make_candle(
                8,
                open_=100.0,
                high=100.6,
                low=final_low,
                close=100.3,
            )
        )
        return candles

    def test_hammer_at_new_low(self) -> None:
        candles = warmed(4) + self._hammer_context(final_low=95.0)
        result = classify_hammer_shooting_star(candles, CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.HAMMER_SHOOTING_STAR
        assert result.direction is PatternDirection.BULLISH
        # الذيل السفلي = 100.0-95.0 = 5؛ المدى = 100.6-95.0 = 5.6
        assert result.strength == pytest.approx(5.0 / 5.6)

    def test_no_new_low_rejected(self) -> None:
        # قاع شمعة القرار داخل قيعان السياق (أدنى قيعان السياق = 99.0)
        candles = warmed(4) + self._hammer_context(final_low=99.2)
        assert classify_hammer_shooting_star(candles, CFG) is None

    def test_shooting_star_at_new_high(self) -> None:
        context = [
            make_candle(
                4 + i,
                open_=100.0 - (4 - i),
                high=101.0 - (4 - i),
                low=99.0 - (4 - i),
                close=100.5 - (4 - i),
            )
            for i in range(4)
        ]
        star = make_candle(8, open_=100.0, high=104.6, low=99.4, close=100.2)
        result = classify_hammer_shooting_star(warmed(4) + context + [star], CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH


# ═══════════════════ الشمعة الداخلية (سياقي) ═══════════════════


class TestInsideBar:
    def test_inside_neutral_with_compression(self) -> None:
        mother = make_candle(7, open_=95.0, high=110.0, low=90.0, close=105.0)
        inside = make_candle(8, open_=100.0, high=104.0, low=96.0, close=101.0)
        result = classify_inside_bar([*warmed(7), mother, inside], CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.INSIDE_BAR
        assert result.direction is PatternDirection.NEUTRAL
        # انضغاط = 1 - مدى الداخلية/مدى الأم = 1 - 8/20 = 0.6
        assert result.strength == pytest.approx(0.6)

    def test_outside_bar_rejected(self) -> None:
        mother = make_candle(7, open_=95.0, high=110.0, low=90.0, close=105.0)
        outside = make_candle(8, open_=100.0, high=111.0, low=96.0, close=101.0)
        assert classify_inside_bar([*warmed(7), mother, outside], CFG) is None

    def test_full_compression_flat_mother(self) -> None:
        mother = make_candle(7, open_=100.0, high=100.0, low=100.0, close=100.0)
        inside = make_candle(8, open_=100.0, high=100.0, low=100.0, close=100.0)
        result = classify_inside_bar([*warmed(7), mother, inside], CFG)
        assert result is not None
        assert result.strength == pytest.approx(1.0)


# ═══════════════════ كسر الداخلية (حدث §20) ═══════════════════


class TestInsideBarBreak:
    def _sequence(self, breaker: Candle) -> list[Candle]:
        mother = make_candle(7, open_=95.0, high=110.0, low=90.0, close=105.0)
        inside = make_candle(8, open_=100.0, high=104.0, low=96.0, close=101.0)
        return [*warmed(7), mother, inside, breaker]

    def test_bullish_break(self) -> None:
        breaker = make_candle(9, open_=103.0, high=112.0, low=102.0, close=111.5)
        result = classify_inside_bar_break(self._sequence(breaker), CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.INSIDE_BAR
        assert result.direction is PatternDirection.BULLISH
        assert result.bar_time == breaker.bar_time
        assert 0.0 <= result.strength <= 1.0

    def test_bearish_break(self) -> None:
        breaker = make_candle(9, open_=98.0, high=99.0, low=88.0, close=89.0)
        result = classify_inside_bar_break(self._sequence(breaker), CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH

    def test_wick_probe_not_break(self) -> None:
        # ذيل فوق مدى الأم لكن الإغلاق داخلها — ليس كسرًا مؤكدًا
        probe = make_candle(9, open_=100.0, high=113.0, low=99.0, close=105.0)
        assert classify_inside_bar_break(self._sequence(probe), CFG) is None

    def test_no_inside_bar_no_break(self) -> None:
        mother = make_candle(7, open_=95.0, high=110.0, low=90.0, close=105.0)
        outside = make_candle(8, open_=100.0, high=112.0, low=89.0, close=101.0)
        breaker = make_candle(9, open_=101.0, high=114.0, low=100.0, close=113.0)
        assert classify_inside_bar_break([*warmed(7), mother, outside, breaker], CFG) is None


# ═══════════════════ الدوجي (سياقي) ═══════════════════


class TestDoji:
    def test_doji_positive(self) -> None:
        doji = make_candle(8, open_=100.0, high=103.0, low=97.0, close=100.15)
        result = classify_doji([*warmed(7), doji], CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.DOJI
        assert result.direction is PatternDirection.NEUTRAL
        # bf = 0.15/6 = 0.025 ⇒ strength = 1 - 0.025
        assert result.strength == pytest.approx(1.0 - 0.025)

    def test_fat_body_rejected(self) -> None:
        fat = make_candle(8, open_=97.0, high=103.0, low=96.5, close=102.5)
        assert classify_doji([*warmed(7), fat], CFG) is None


# ═══════════════════ النجمة الصباحية/المسائية (سياقي) ═══════════════════


class TestMorningEveningStar:
    def test_morning_star_with_manual_penetration(self) -> None:
        # أولى هابطة وافرة: open=106 close=100 (جسم 6)
        first = make_candle(7, open_=106.0, high=106.5, low=99.5, close=100.0)
        # نجمة صغيرة: جسم 0.2 بمدى 2.0 ⇒ bf=0.1 ≤ 0.30
        star = make_candle(8, open_=100.8, high=102.0, low=100.0, close=101.0)
        # ثالثة صاعدة تغلق 104.5: منتصف جسم الأولى = 103 ⇒ اختراق = 1.5/6 = 0.25
        third = make_candle(9, open_=101.0, high=105.0, low=100.5, close=104.5)
        result = classify_morning_evening_star([*warmed(7), first, star, third], CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.MORNING_EVENING_STAR
        assert result.direction is PatternDirection.BULLISH
        # strength = 0.5 + 0.25 = 0.75
        assert result.strength == pytest.approx(0.75)

    def test_evening_star_mirror(self) -> None:
        first = make_candle(7, open_=100.0, high=106.5, low=99.5, close=106.0)
        star = make_candle(8, open_=105.2, high=106.0, low=104.5, close=105.0)
        third = make_candle(9, open_=105.0, high=105.5, low=101.0, close=101.5)
        result = classify_morning_evening_star([*warmed(7), first, star, third], CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH

    def test_weak_penetration_rejected(self) -> None:
        first = make_candle(7, open_=106.0, high=106.5, low=99.5, close=100.0)
        star = make_candle(8, open_=100.5, high=101.5, low=100.0, close=101.0)
        # ثالثة تغلق عند 102.5 < منتصف 103 — اختراق ناقص
        third = make_candle(9, open_=101.0, high=103.0, low=100.5, close=102.5)
        assert classify_morning_evening_star([*warmed(7), first, star, third], CFG) is None

    def test_big_star_rejected(self) -> None:
        first = make_candle(7, open_=106.0, high=106.5, low=99.5, close=100.0)
        big_star = make_candle(8, open_=100.0, high=103.0, low=99.5, close=102.5)
        third = make_candle(9, open_=102.5, high=105.0, low=100.5, close=104.5)
        assert classify_morning_evening_star([*warmed(7), first, big_star, third], CFG) is None

    def test_aligned_flanks_rejected(self) -> None:
        # الطرفان هابطان معًا — ليست نجمة انعكاسية
        first = make_candle(7, open_=106.0, high=106.5, low=99.5, close=100.0)
        star = make_candle(8, open_=100.0, high=100.5, low=99.5, close=100.3)
        third_down = make_candle(9, open_=100.5, high=101.0, low=95.0, close=96.0)
        assert classify_morning_evening_star([*warmed(7), first, star, third_down], CFG) is None


# ═══════════════════ الإغلاق القوي (سياقي) ═══════════════════


class TestStrongClosing:
    def test_bullish_strong_close(self) -> None:
        # جسم 9/مدى 10 ⇒ bf=0.9 ≥ 0.60؛ close_location = 0.9 ≥ 0.80
        candle = make_candle(8, open_=100.0, high=110.0, low=100.0, close=109.0)
        result = classify_strong_closing([*warmed(7), candle], CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.STRONG_CLOSING
        assert result.direction is PatternDirection.BULLISH
        # strength = (0.9 + 0.9)/2 = 0.9
        assert result.strength == pytest.approx(0.9)

    def test_bearish_mirror(self) -> None:
        candle = make_candle(8, open_=110.0, high=110.0, low=100.0, close=101.0)
        result = classify_strong_closing([*warmed(7), candle], CFG)
        assert result is not None
        assert result.direction is PatternDirection.BEARISH

    def test_mid_close_rejected(self) -> None:
        candle = make_candle(8, open_=105.0, high=110.0, low=100.0, close=105.5)
        assert classify_strong_closing([*warmed(7), candle], CFG) is None


# ═══════════════════ التوسع (سياقي) ═══════════════════


class TestExpansion:
    def test_expansion_positive(self) -> None:
        # 5 شموع هادئة (مدى 1.2) ثم شمعة مداها الأعلى قطعيًا — مئيني 1.0
        quiet = [make_candle(i, open_=100.0, high=100.6, low=99.4, close=100.4) for i in range(5)]
        expanding = make_candle(5, open_=100.0, high=103.0, low=97.0, close=102.5)
        result = classify_expansion([*quiet, expanding], CFG)
        assert result is not None
        assert result.family is CandlePatternFamily.EXPANSION
        assert result.direction is PatternDirection.BULLISH
        assert result.strength == pytest.approx(1.0)

    def test_quiet_candle_rejected(self) -> None:
        quiet = [make_candle(i, open_=100.0, high=100.6, low=99.4, close=100.4) for i in range(6)]
        assert classify_expansion(quiet, CFG) is None

    def test_flat_body_expansion_is_neutral(self) -> None:
        quiet = [make_candle(i, open_=100.0, high=100.6, low=99.4, close=100.4) for i in range(5)]
        flat = make_candle(5, open_=100.0, high=103.0, low=97.0, close=100.0)
        result = classify_expansion([*quiet, flat], CFG)
        assert result is not None
        assert result.direction is PatternDirection.NEUTRAL


# ═══════════════════ classify_last_candle — الترتيب والتراكب ═══════════════════


class TestClassifyLastCandle:
    def test_empty_and_short(self) -> None:
        assert classify_last_candle([], CFG) == ()
        assert classify_last_candle([filler(0)], CFG) == ()

    def test_order_follows_section_13_1(self) -> None:
        # دوجي نقي في نهاية دافئ — عائلة واحدة على الأقل (الدوجي)
        candles = [*warmed(8), make_candle(99, open_=100.0, high=103.0, low=97.0, close=100.05)]
        families = [c.family for c in classify_last_candle(candles, CFG)]
        assert CandlePatternFamily.DOJI in families
        # الترتيب دائمًا بترتيب §13.1
        order = [c.family for c in classify_last_candle(candles, CFG)]
        section_order = [
            CandlePatternFamily.ENGULFING,
            CandlePatternFamily.PIN_REJECTION,
            CandlePatternFamily.HAMMER_SHOOTING_STAR,
            CandlePatternFamily.INSIDE_BAR,
            CandlePatternFamily.DOJI,
            CandlePatternFamily.MORNING_EVENING_STAR,
            CandlePatternFamily.STRONG_CLOSING,
            CandlePatternFamily.EXPANSION,
        ]
        ranks = [section_order.index(f) for f in order if f in section_order]
        assert ranks == sorted(ranks)

    def test_feature_readings_carry_all_six(self) -> None:
        candles = [*warmed(8), make_candle(99, open_=100.0, high=103.0, low=97.0, close=100.05)]
        for classification in classify_last_candle(candles, CFG):
            assert set(classification.feature_readings) == {
                "body_fraction",
                "wick_asymmetry",
                "close_location",
                "range_percentile",
                "gap_relationship",
                "volume_relationship",
            }


# ═══════════════════ الكاشف المبثوث (§20) ═══════════════════


def _detector_with_bullish_engulfing_end() -> tuple[CandlePatternDetector, list[Candle]]:
    detector = CandlePatternDetector(CFG)
    candles = [
        *warmed(7),
        make_candle(10, open_=105.0, high=106.0, low=99.5, close=100.0),
        make_candle(11, open_=99.0, high=107.0, low=98.5, close=106.0),
    ]
    return detector, candles


class TestDetector:
    def test_bullish_engulfing_event_broadcast(self) -> None:
        detector, candles = _detector_with_bullish_engulfing_end()
        events = detector.on_candles(candles)
        engulfing_events = [e for e in events if e.event_type is EventType.BULLISH_ENGULFING]
        assert len(engulfing_events) == 1
        event = engulfing_events[0]
        assert isinstance(event, EmittedEvent)
        assert event.event_time == candles[-1].bar_time
        payload = event.payload
        assert payload.family is CandlePatternFamily.ENGULFING
        assert payload.direction is PatternDirection.BULLISH
        assert payload.bars_in_pattern == 2
        assert payload.strength == pytest.approx(7.0 / 12.0)
        assert payload.instrument == _INSTRUMENT
        assert payload.timeframe == "1m"

    def test_rejection_event_broadcast(self) -> None:
        detector = CandlePatternDetector(CFG)
        pin = make_candle(99, open_=100.0, high=101.0, low=95.0, close=100.5)
        events = detector.on_candles([*warmed(8), pin])
        rejection_events = [e for e in events if e.event_type is EventType.REJECTION_CANDLE]
        assert len(rejection_events) == 1
        assert rejection_events[0].payload.strength == pytest.approx(5.0 / 6.0)

    def test_inside_bar_break_event_broadcast(self) -> None:
        detector = CandlePatternDetector(CFG)
        candles = [
            *warmed(7),
            make_candle(10, open_=95.0, high=110.0, low=90.0, close=105.0),
            make_candle(11, open_=100.0, high=104.0, low=96.0, close=101.0),
            make_candle(12, open_=103.0, high=112.0, low=102.0, close=111.5),
        ]
        events = detector.on_candles(candles)
        breaks = [e for e in events if e.event_type is EventType.INSIDE_BAR_BREAK]
        assert len(breaks) == 1
        assert breaks[0].event_time == candles[-1].bar_time
        assert breaks[0].payload.direction is PatternDirection.BULLISH

    def test_contextual_families_never_broadcast(self) -> None:
        """العائلات الخمس غير المبثوثة لا تنتج أحداثًا أبدًا."""
        detector = CandlePatternDetector(CFG)
        doji = make_candle(99, open_=100.0, high=103.0, low=97.0, close=100.05)
        events = detector.on_candles([*warmed(8), doji])
        assert events == ()

    def test_determinism_two_runs(self) -> None:
        candles = [
            *warmed(10),
            make_candle(20, open_=105.0, high=106.0, low=99.5, close=100.0),
            make_candle(21, open_=99.0, high=107.0, low=98.5, close=106.0),
            make_candle(22, open_=100.0, high=101.0, low=95.0, close=100.5),
        ]
        first = CandlePatternDetector(CFG).on_candles(candles)
        second = CandlePatternDetector(CFG).on_candles(candles)
        assert first == second

    def test_no_lookahead_prefix_independence(self) -> None:
        """أحداث البادئة مستقلة عن الذيل — بادئة أطول لا تغير ما بُث سابقًا."""
        candles = [
            *warmed(10),
            make_candle(20, open_=105.0, high=106.0, low=99.5, close=100.0),
            make_candle(21, open_=99.0, high=107.0, low=98.5, close=106.0),
        ]
        tail = [
            make_candle(22, open_=106.0, high=113.0, low=105.0, close=112.0),
            make_candle(23, open_=112.0, high=120.0, low=111.0, close=119.0),
        ]
        prefix_events = CandlePatternDetector(CFG).on_candles(candles)
        full_events = CandlePatternDetector(CFG).on_candles(candles + tail)
        prefix_times = {(e.event_type, e.event_time) for e in prefix_events}
        full_times = {(e.event_type, e.event_time) for e in full_events}
        assert prefix_times <= full_times

    def test_no_rebroadcast_same_candle(self) -> None:
        """كل شمعة تُستهلك مرة — لا إعادة بث لنمط الشمعة نفسها."""
        detector, candles = _detector_with_bullish_engulfing_end()
        events = detector.on_candles(candles)
        engulfing = [e for e in events if e.event_type is EventType.BULLISH_ENGULFING]
        # تغذية أطول لا تعيد بث حدث الشمعة المستهلكة
        more = detector.on_candles([filler(50), filler(51), filler(52)])
        assert not any(e.event_type is EventType.BULLISH_ENGULFING for e in more)
        assert len(engulfing) == 1

    def test_batch_equals_candle_by_candle(self) -> None:
        candles = [
            *warmed(10),
            make_candle(20, open_=105.0, high=106.0, low=99.5, close=100.0),
            make_candle(21, open_=99.0, high=107.0, low=98.5, close=106.0),
        ]
        batch = CandlePatternDetector(CFG).on_candles(candles)
        stepwise: list[EmittedEvent] = []
        detector = CandlePatternDetector(CFG)
        for candle in candles:
            stepwise.extend(detector.on_candle(candle))
        assert tuple(stepwise) == batch

    def test_identity_capture_from_first_candle(self) -> None:
        detector = CandlePatternDetector(CFG)
        assert detector.instrument_id is None
        detector.on_candle(filler(0))
        assert detector.instrument_id == _INSTRUMENT
        assert detector.timeframe == "1m"

    def test_explicit_identity_and_half_identity_rejected(self) -> None:
        detector = CandlePatternDetector(CFG, instrument_id=_INSTRUMENT, timeframe="1m")
        assert detector.instrument_id == _INSTRUMENT
        with pytest.raises(ValueError, match="الهوية"):
            CandlePatternDetector(CFG, instrument_id=_INSTRUMENT)

    def test_guard_open_candle_rejected(self) -> None:
        detector = CandlePatternDetector(CFG)
        with pytest.raises(ValueError, match="المغلقة فقط"):
            detector.on_candle(
                make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.5, is_closed=False)
            )

    def test_guard_instrument_mix_rejected(self) -> None:
        detector = CandlePatternDetector(CFG)
        detector.on_candle(filler(0))
        with pytest.raises(ValueError, match="خلط أدوات"):
            detector.on_candle(
                make_candle(1, open_=100.0, high=101.0, low=99.0, close=100.5, instrument="ETH")
            )

    def test_guard_duplicate_rejected(self) -> None:
        detector = CandlePatternDetector(CFG)
        candle = filler(0)
        detector.on_candle(candle)
        with pytest.raises(ValueError, match="تكرار"):
            detector.on_candle(candle)

    def test_guard_late_candle_rejected(self) -> None:
        detector = CandlePatternDetector(CFG)
        detector.on_candle(filler(1))
        with pytest.raises(ValueError, match="متأخرة"):
            detector.on_candle(filler(0))

    def test_events_order_within_candle(self) -> None:
        """ترتيب الأحداث داخل الشمعة الواحدة بترتيب عائلات §13.1."""
        # شمعة تبتلع (وإغلاقها قوي فتجمع العائلتين) — الابتلاع قبل بقية الأنواع
        detector, candles = _detector_with_bullish_engulfing_end()
        events = detector.on_candles(candles)
        types = [e.event_type for e in events]
        assert EventType.BULLISH_ENGULFING in types
        if len(types) > 1:
            assert types.index(EventType.BULLISH_ENGULFING) == 0
