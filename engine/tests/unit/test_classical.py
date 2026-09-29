"""اختبارات البُنى الكلاسيكية الثماني (§13.2) — المهمة 5-c.

بوابة المهمة نصًّا: «هندسات مثالية + غامضة تبقى مرشحة ضعيفة» — لكل بنية
من الثماني هندسة مثالية محسوبة يدويًا القيم (breakout/invalidation/
measured_move بمعادلات §13.2 الحرفية) ومراياها، وهندسة غامضة تبقى
CANDIDATE بجودة منخفضة (§13.2: «تبقى مرشحة وتساهم قليلًا أو لا تساهم»)،
والكسر الفاشل بزوجه (§20)، وغير المكسور لا يُبث أبدًا.

الباني ``zigzag`` يصنع سلاسل تمر بمستويات قمم/قيعان صريحة (كل انعطاف
بذيل أعرض 1.5× لضمان القطع المحلي بفرادير k=2) — القطوع الفعلية
بأسعار المستوى ± الذيل، والحسابات اليدوية أدناه تعتمد أسعار القطوع
الفعلية لا مستويات المدخل.
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime, timedelta

import pytest
from patterns.classical import (
    ClassicalConfig,
    ClassicalPatternDetector,
    EmittedEvent,
    PivotKind,
    find_pivots,
)
from schemas import (
    Candle,
    ClassicalPatternType,
    DataQuality,
    EventType,
    PatternStatus,
)

_BASE = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
_INSTRUMENT = "BINANCE_USDM:BTCUSDT"


def make_candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    is_closed: bool = True,
    instrument: str = _INSTRUMENT,
) -> Candle:
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument,
        timeframe="1m",
        bar_time=_BASE + timedelta(minutes=index),
        session_id="2026-09-29",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=(body / span) if span > 0 else 0.0,
        close_location_value=((close - low) / span) if span > 0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0 else 0.0,
    )


def zigzag(levels: list[float], legs: int = 3, wick: float = 0.4, start: int = 0) -> list[Candle]:
    """سلسلة تمر بالمستويات صراحةً — كل انعطاف بذيل أعرض لضمان القطع.

    ``start`` فهرس البداية (لبناء أذيال بترتيب زمني لاحق)."""
    out: list[Candle] = []
    idx = start
    for a, b in itertools.pairwise(levels):
        for s in range(legs):
            t = (s + 1) / legs
            close = a + (b - a) * t
            open_ = a + (b - a) * (s / legs)
            w = wick * 1.5 if s == legs - 1 else wick
            out.append(
                make_candle(
                    idx,
                    open_=open_,
                    high=max(open_, close) + w,
                    low=min(open_, close) - w,
                    close=close,
                )
            )
            idx += 1
    return out


def flag_series() -> list[Candle]:
    """سلسلة العلم: هادئة رتيبة (بلا قطوع) فعمود قوي فتجميع ضيق فكسر."""
    out: list[Candle] = []
    for i in range(8):
        o = 100.0 + i * 0.3
        c = o + 0.3
        out.append(make_candle(i, open_=o, high=c + 0.15, low=o - 0.15, close=c))
    out.append(make_candle(8, open_=102.4, high=106.55, low=102.25, close=106.4))
    out.append(make_candle(9, open_=106.4, high=110.55, low=106.25, close=110.4))
    prev = 110.4
    for i in range(10, 14):
        c = prev - 0.3
        out.append(
            make_candle(i, open_=prev, high=max(prev, c) + 0.1, low=min(prev, c) - 0.1, close=c)
        )
        prev = c
    out.append(make_candle(14, open_=109.2, high=111.6, low=109.1, close=111.5))
    return out


FLAG_CFG = ClassicalConfig(
    reference_window=8,
    pole_min_bars=2,
    flag_max_bars=4,
    pole_min_range_ratio=2.0,
)


def events_of(candles: list[Candle], cfg: ClassicalConfig | None = None) -> list[EmittedEvent]:
    detector = ClassicalPatternDetector(cfg) if cfg else ClassicalPatternDetector()
    return list(detector.on_candles(candles))


def single_break(candles: list[Candle], cfg: ClassicalConfig | None = None) -> EmittedEvent:
    events = events_of(candles, cfg)
    breaks = [e for e in events if e.event_type is EventType.CLASSICAL_BREAKOUT]
    assert len(breaks) == 1, [e.event_type.value for e in events]
    assert len(events) == 1
    return breaks[0]


# ═══════════════════════ القطوع المحلية ═══════════════════════


class TestFindPivots:
    def test_alternation_and_backwards_confirmation(self) -> None:
        candles = zigzag([100.0, 110.0, 95.0, 108.0, 90.0])
        pivots = find_pivots(candles, 2)
        kinds = [p.kind for p in pivots]
        # تعاقب صارم HIGH/LOW بالترتيب — والقاع الأخير عند آخر شمعة
        # (11) غير مؤكد بعد (يحتاج شمعتين بعده) فلا يظهر
        assert kinds == [PivotKind.HIGH, PivotKind.LOW, PivotKind.HIGH]
        # أسعار القطوع بالذيل الأعرض عند الانعطاف
        assert pivots[0].price == pytest.approx(110.6)
        assert pivots[1].price == pytest.approx(94.4)
        # تأكيد خلفي فقط: كل قطع مؤكد يسبق آخر شمعتين على الأقل
        assert all(p.index <= len(candles) - 3 for p in pivots)
        # وعند مدّ السلسلة شمعتين هادئتين يؤكد القاع الرابع
        extended = [
            *candles,
            make_candle(12, open_=90.0, high=90.6, low=89.6, close=90.4),
            make_candle(13, open_=90.4, high=90.8, low=90.0, close=90.6),
        ]
        extended_pivots = find_pivots(extended, 2)
        assert [p.kind for p in extended_pivots][-1] is PivotKind.LOW
        assert extended_pivots[-1].price == pytest.approx(89.4)

    def test_no_pivots_in_monotone_series(self) -> None:
        candles = [
            make_candle(i, open_=100.0 + i, high=101.0 + i, low=99.0 + i, close=100.5 + i)
            for i in range(8)
        ]
        assert find_pivots(candles, 2) == []

    def test_strict_inequality_required(self) -> None:
        # تساوي الذروة مع جار لا يقطع (مقارنة صارمة)
        candles = [
            make_candle(0, open_=100.0, high=110.0, low=99.0, close=105.0),
            make_candle(1, open_=105.0, high=110.0, low=100.0, close=101.0),
            make_candle(2, open_=101.0, high=104.0, low=100.0, close=103.0),
            make_candle(3, open_=103.0, high=104.0, low=100.0, close=101.0),
            make_candle(4, open_=101.0, high=103.0, low=100.0, close=102.0),
        ]
        assert find_pivots(candles, 2) == []


# ═══════════════════════ الإعداد ═══════════════════════


class TestConfig:
    def test_strict_unit_intervals_rejected(self) -> None:
        with pytest.raises(ValueError, match="double_tolerance"):
            ClassicalConfig(double_tolerance=1.0)
        with pytest.raises(ValueError, match="confirmed_quality_min"):
            ClassicalConfig(confirmed_quality_min=0.0)

    def test_numeric_bounds(self) -> None:
        with pytest.raises(ValueError, match="pivot_strength"):
            ClassicalConfig(pivot_strength=0)
        with pytest.raises(ValueError, match="pole_min_range_ratio"):
            ClassicalConfig(pole_min_range_ratio=1.0)
        with pytest.raises(ValueError, match="failure_max_bars"):
            ClassicalConfig(failure_max_bars=0)

    def test_frozen(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            ClassicalConfig().window = 50  # type: ignore[misc]


# ═══════════════════ القمة/القاع المزدوج §13.2 ═══════════════════


class TestDoubleTopBottom:
    def test_double_top_manual_values(self) -> None:
        # القطوع: H(110.6) L(94.4) H(110.8) — الرقبة 94.4 والارتفاع 16.2
        event = single_break(zigzag([100.0, 110.0, 95.0, 110.2, 93.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.DOUBLE_TOP
        assert p.break_direction.value == "DOWN"
        assert p.breakout_level == pytest.approx(94.4)
        assert p.invalidation_level == pytest.approx(110.8)
        # measured = الرقبة − (القمة − الرقبة)
        assert p.measured_move == pytest.approx(94.4 - (110.8 - 94.4))
        assert p.quality == pytest.approx(0.723, abs=0.005)
        assert p.status is PatternStatus.CONFIRMED
        assert len(p.anchor_points) == 3
        roles = {a.role for a in p.anchor_points}
        assert roles == {"P1_PEAK", "P2_NECKLINE", "P3_PEAK"}

    def test_double_bottom_mirror(self) -> None:
        event = single_break(zigzag([100.0, 90.0, 105.0, 89.8, 107.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.DOUBLE_BOTTOM
        assert p.break_direction.value == "UP"
        assert p.breakout_level == pytest.approx(105.6)
        assert p.invalidation_level == pytest.approx(89.2)
        assert p.measured_move == pytest.approx(105.6 + (105.6 - 89.2))

    def test_mismatched_peaks_rejected(self) -> None:
        # تفاوت القمتين يتجاوز double_tolerance (10% من الارتفاع)
        candles = zigzag([100.0, 110.0, 95.0, 105.0, 93.0])
        assert events_of(candles) == []

    def test_unbroken_never_broadcasts(self) -> None:
        assert events_of(zigzag([100.0, 110.0, 95.0, 110.2, 100.0])) == []


# ═══════════════════ الرأس والكتفان §13.2 ═══════════════════


class TestHeadAndShoulders:
    def test_hs_manual_values(self) -> None:
        # القطوع: H(105.6) L(95.4) H(110.6) L(95.9) H(105.8)
        event = single_break(zigzag([100.0, 105.0, 96.0, 110.0, 96.5, 105.2, 93.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.HEAD_AND_SHOULDERS
        assert p.break_direction.value == "DOWN"
        # الرقبة المتحفظة: أدنى نقطتيها
        assert p.breakout_level == pytest.approx(95.4)
        assert p.invalidation_level == pytest.approx(110.6)
        assert p.measured_move == pytest.approx(95.4 - (110.6 - 95.4))
        assert p.quality == pytest.approx(0.982, abs=0.005)
        assert p.status is PatternStatus.CONFIRMED
        assert len(p.anchor_points) == 5
        assert {a.role for a in p.anchor_points} == {
            "LEFT_SHOULDER",
            "NECKLINE_LEFT",
            "HEAD",
            "NECKLINE_RIGHT",
            "RIGHT_SHOULDER",
        }

    def test_inverse_hs_mirror(self) -> None:
        event = single_break(zigzag([100.0, 95.0, 104.0, 90.0, 103.5, 94.8, 107.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.INVERSE_HEAD_AND_SHOULDERS
        assert p.break_direction.value == "UP"
        assert p.breakout_level == pytest.approx(104.6)
        assert p.invalidation_level == pytest.approx(89.4)
        assert p.measured_move == pytest.approx(104.6 + (104.6 - 89.4))

    def test_flat_head_rejected(self) -> None:
        # رأس لا يبرز فوق الكتفين (بروز ≈ 0.05 < 0.10) — لا رأس وكتفين
        candles = zigzag([100.0, 105.5, 96.0, 106.0, 96.5, 103.0, 93.0])
        events = events_of(candles)
        assert not any(
            e.payload.pattern_type is ClassicalPatternType.HEAD_AND_SHOULDERS for e in events
        )


# ═══════════════════ البُنى الخطية (مثلث/إسفين/قناة/نطاق) ═══════════════════


class TestLineStructures:
    def test_triangle_breakout_up(self) -> None:
        # خطا القمم هابط والقيعان صاعد — تقارب مختلف الإشارة
        event = single_break(zigzag([90.0, 100.0, 92.0, 97.0, 94.0, 99.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.TRIANGLE
        assert p.break_direction.value == "UP"
        # الكسر عبر امتداد خط القمم عند الشمعة الكاسرة
        assert p.breakout_level == pytest.approx(97.1)
        assert p.invalidation_level == pytest.approx(93.733, abs=0.005)
        assert p.measured_move == pytest.approx(100.467, abs=0.005)
        assert len(p.anchor_points) == 4

    def test_wedge_breakout_down(self) -> None:
        # خطان هابطان متقاربان — الإسفين، كسر تحت امتداد خط القيعان
        event = single_break(zigzag([90.0, 100.0, 95.0, 98.0, 92.0, 93.5, 86.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.WEDGE
        assert p.break_direction.value == "DOWN"
        assert p.breakout_level == pytest.approx(89.9)
        assert p.invalidation_level == pytest.approx(97.6)
        assert p.measured_move == pytest.approx(82.2)

    def test_channel_breakout_up(self) -> None:
        # خطان صاعدان متوازيان — قناة، كسر فوق امتداد خط القمم
        event = single_break(zigzag([80.0, 90.0, 85.0, 96.0, 91.0, 102.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.CHANNEL
        assert p.break_direction.value == "UP"
        assert p.breakout_level == pytest.approx(96.6)
        assert p.invalidation_level == pytest.approx(90.4)
        assert p.quality == pytest.approx(1.0)

    def test_range_breakout_up(self) -> None:
        # حافتان شبه أفقيتين بتفاوت يرفض المزدوج (ضمن عتبتي السطحية والرفض)
        event = single_break(zigzag([95.0, 100.0, 90.0, 98.6, 91.6, 103.5], legs=5))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.RANGE_BREAKOUT
        assert p.break_direction.value == "UP"
        assert p.breakout_level == pytest.approx(98.92, abs=0.01)
        assert p.invalidation_level == pytest.approx(91.32, abs=0.01)
        assert p.measured_move == pytest.approx(106.52, abs=0.01)


# ═══════════════════ العلم §13.2 ═══════════════════


class TestFlag:
    def test_flag_breakout_up(self) -> None:
        event = single_break(flag_series(), FLAG_CFG)
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.FLAG
        assert p.break_direction.value == "UP"
        assert p.breakout_level == pytest.approx(110.5)
        assert p.invalidation_level == pytest.approx(109.1)
        # الهدف = قمة التجميع + ارتفاع العمود (8.3)
        assert p.measured_move == pytest.approx(118.8, abs=0.05)
        assert p.quality == pytest.approx(0.831, abs=0.005)
        assert len(p.anchor_points) == 4
        assert {a.role for a in p.anchor_points} == {
            "POLE_BASE",
            "POLE_TOP",
            "FLAG_HIGH",
            "FLAG_LOW",
        }

    def test_weak_pole_rejected(self) -> None:
        # عمود هزيل: امتداد شمعتيه دون ضعفَي المدى المرجعي — لا علم
        candles: list[Candle] = []
        for i in range(8):
            o = 100.0 + i * 0.3
            c = o + 0.3
            candles.append(make_candle(i, open_=o, high=c + 0.15, low=o - 0.15, close=c))
        candles.append(make_candle(8, open_=102.4, high=102.85, low=102.25, close=102.7))
        candles.append(make_candle(9, open_=102.7, high=103.15, low=102.55, close=103.0))
        prev = 103.0
        for i in range(10, 14):
            c = prev - 0.1
            candles.append(
                make_candle(
                    i, open_=prev, high=max(prev, c) + 0.05, low=min(prev, c) - 0.05, close=c
                )
            )
            prev = c
        candles.append(make_candle(14, open_=102.6, high=103.5, low=102.5, close=103.4))
        events = events_of(candles, FLAG_CFG)
        assert not any(e.payload.pattern_type is ClassicalPatternType.FLAG for e in events)

    def test_wide_consolidation_rejected(self) -> None:
        # تجميع أوسع من نصف ارتفاع العمود — ليس علمًا
        candles = flag_series()
        wide = [
            make_candle(10, open_=110.4, high=110.5, low=107.9, close=108.0),
            make_candle(11, open_=108.0, high=108.1, low=106.4, close=106.5),
            make_candle(12, open_=106.5, high=107.6, low=106.4, close=107.5),
            make_candle(13, open_=107.5, high=107.6, low=105.4, close=105.5),
        ]
        merged = [*candles[:10], *wide, candles[-1]]
        events = events_of(merged, FLAG_CFG)
        assert not any(e.payload.pattern_type is ClassicalPatternType.FLAG for e in events)


# ═══════════════════ الغامض مرشح ضعيف (§13.2 حرفيًا) ═══════════════════


class TestAmbiguousGeometry:
    def test_ambiguous_double_top_stays_candidate(self) -> None:
        # تفاوت 9% من الارتفاع — قمة مزدوجة غامضة تبقى مرشحة ضعيفة
        event = single_break(zigzag([100.0, 110.0, 95.0, 108.65, 93.0]))
        p = event.payload
        assert p.pattern_type is ClassicalPatternType.DOUBLE_TOP
        assert p.status is PatternStatus.CANDIDATE
        assert p.quality < 0.5
        assert p.break_direction.value == "DOWN"

    def test_candidate_still_broadcasts_on_break(self) -> None:
        """الغامض يُبث إن انكسر — الوزن مسؤولية الدمج (§19) لا الكاشف."""
        events = events_of(zigzag([100.0, 110.0, 95.0, 108.65, 93.0]))
        assert any(e.event_type is EventType.CLASSICAL_BREAKOUT for e in events)


# ═══════════════════ الكسر الفاشل (§20) ═══════════════════


class TestFailedBreakout:
    def test_break_then_reclaim_emits_failure(self) -> None:
        events = events_of(zigzag([100.0, 110.0, 95.0, 110.2, 94.0, 96.5]))
        assert [e.event_type for e in events] == [
            EventType.CLASSICAL_BREAKOUT,
            EventType.CLASSICAL_FAILED_BREAKOUT,
        ]
        failure = events[1].payload
        assert failure.pattern_type is ClassicalPatternType.DOUBLE_TOP
        assert failure.reclaim_level is not None
        assert failure.reclaim_level == pytest.approx(94.833, abs=0.01)
        # الكسر في شمعة والاسترجاع في التالية ⇒ سرعة فشل 1
        assert failure.failure_speed == 1.0

    def test_failure_window_expiry(self) -> None:
        # كسر ثم بقاء دونه طوال نافذة الفشل ثم استرجاع متأخر — الكسر ناجح
        candles = zigzag([100.0, 110.0, 95.0, 110.2, 94.0])
        # 8 شموع هادئة تحت الرقبة (94.4) — نافذة الفشل كاملة
        tail = [make_candle(12 + i, open_=93.9, high=94.2, low=93.5, close=93.8) for i in range(8)]
        # استرجاع متأخر بعد انقضاء النافذة
        late = make_candle(20, open_=93.8, high=95.6, low=93.6, close=95.2)
        events = events_of([*candles, *tail, late])
        assert [e.event_type for e in events] == [EventType.CLASSICAL_BREAKOUT]

    def test_no_rebroadcast_after_failure(self) -> None:
        candles = zigzag([100.0, 110.0, 95.0, 110.2, 94.0, 96.5])
        more = [
            make_candle(18, open_=96.5, high=97.0, low=95.8, close=96.2),
            make_candle(19, open_=96.2, high=96.8, low=95.9, close=96.0),
        ]
        events = events_of([*candles, *more])
        assert len(events) == 2  # الكسر وفشله فقط — لا إعادة


# ═══════════════════ العقود العابرة ═══════════════════


class TestCrossCuttingContracts:
    def test_determinism_two_runs(self) -> None:
        candles = zigzag([100.0, 110.0, 95.0, 110.2, 93.0, 88.0, 91.0])
        first = events_of(candles)
        second = events_of(candles)
        assert first == second

    def test_no_lookahead_prefix_independence(self) -> None:
        """أحداث البادئة مستقلة عن الذيل — لا نظرة مستقبلية §26.3."""
        base = zigzag([100.0, 110.0, 95.0, 110.2, 93.0])
        # ذيل لاحق بترتيب زمني صحيح: استرجاع فوق الرقبة المكسورة
        tail = zigzag([93.0, 96.5], start=len(base))
        prefix_events = events_of(base)
        full_events = events_of([*base, *tail])
        assert prefix_events, "البادئة تحمل حدث الكسر"
        prefix_pairs = {(e.event_type, e.event_time) for e in prefix_events}
        full_pairs = {(e.event_type, e.event_time) for e in full_events}
        assert prefix_pairs <= full_pairs

    def test_batch_equals_candle_by_candle(self) -> None:
        candles = zigzag([100.0, 110.0, 95.0, 110.2, 93.0, 96.0])
        batch = events_of(candles)
        stepwise: list[EmittedEvent] = []
        detector = ClassicalPatternDetector()
        for candle in candles:
            stepwise.extend(detector.on_candle(candle))
        assert stepwise == batch

    def test_outputs_eight_present(self) -> None:
        event = single_break(zigzag([100.0, 110.0, 95.0, 110.2, 93.0]))
        payload = event.payload
        for field_name in (
            "pattern_type",
            "geometry",
            "anchor_points",
            "completion_time",
            "breakout_level",
            "invalidation_level",
            "measured_move",
            "quality",
        ):
            assert field_name in type(payload).model_fields, field_name

    def test_geometry_is_numeric_only(self) -> None:
        event = single_break(zigzag([100.0, 110.0, 95.0, 110.2, 93.0]))
        assert event.payload.geometry
        assert all(isinstance(v, float) for v in event.payload.geometry.values())

    def test_completion_time_is_break_candle(self) -> None:
        candles = zigzag([100.0, 110.0, 95.0, 110.2, 93.0])
        event = single_break(candles)
        assert event.payload.completion_time == candles[-1].bar_time
        assert event.payload.bar_time == candles[-1].bar_time
        assert event.event_time == candles[-1].bar_time

    def test_payload_carry_identity(self) -> None:
        event = single_break(zigzag([100.0, 110.0, 95.0, 110.2, 93.0]))
        assert event.payload.instrument == _INSTRUMENT
        assert event.payload.timeframe == "1m"


# ═══════════════════ الحارس ═══════════════════


class TestGuard:
    def test_open_candle_rejected(self) -> None:
        detector = ClassicalPatternDetector()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            detector.on_candle(
                make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.5, is_closed=False)
            )

    def test_instrument_mix_rejected(self) -> None:
        detector = ClassicalPatternDetector()
        detector.on_candle(make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.5))
        with pytest.raises(ValueError, match="خلط أدوات"):
            detector.on_candle(
                make_candle(1, open_=100.0, high=101.0, low=99.0, close=100.5, instrument="ETH")
            )

    def test_duplicate_rejected(self) -> None:
        detector = ClassicalPatternDetector()
        candle = make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.5)
        detector.on_candle(candle)
        with pytest.raises(ValueError, match="تكرار"):
            detector.on_candle(candle)

    def test_late_candle_rejected(self) -> None:
        detector = ClassicalPatternDetector()
        detector.on_candle(make_candle(1, open_=100.0, high=101.0, low=99.0, close=100.5))
        with pytest.raises(ValueError, match="متأخرة"):
            detector.on_candle(make_candle(0, open_=100.0, high=101.0, low=99.0, close=100.5))

    def test_half_identity_rejected(self) -> None:
        with pytest.raises(ValueError, match="الهوية"):
            ClassicalPatternDetector(instrument_id=_INSTRUMENT)

    def test_explicit_identity_accepted(self) -> None:
        detector = ClassicalPatternDetector(instrument_id=_INSTRUMENT, timeframe="1m")
        assert detector.instrument_id == _INSTRUMENT
        assert detector.config.pivot_strength == 2
