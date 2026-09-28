"""اختبارات متعقّب كتل الأوامر — بوابة المهمة 3-c (§11.6).

يُقفل حرفيًا بعقود :mod:`structure.order_blocks`:
- خط الأنابيب الخمسي عند كل إزاحة مؤكدة: التتبع الخلفي للشمعة/العنقيد
  المعاكس المتراص (تسامح EQUAL_LEVEL_TOLERANCE)، والبث **المؤجل** حتى
  تحقق كسر موافق الاتجاه ضمن النافذة (خطوة 3 قبل البث — لا بث ثم إبطال).
- التسمية: قطبية المنطقة تتبع قطبية الإزاحة المولِّدة (UP→BULLISH).
- تتبع الاختبارات من الشريط التالي للبث: حلقات متتالية قاطعة للمنطقة
  ودرجة رد الفعل clamp01(tanh(الرفض/ATR)).
- الجودة متوسط موزون في [0, 1] ببعد تدفق غير متاح بعد (وزن صفر موثق).
- الصخب: أحداث بنوع غريب أو طابع لا يطابق الشمعة أو تغذية غير متسقة
  (حدث مع ATR غائب) — كلها ValueError.

الأحداث تُصنع يدويًا بنفس عقود الواجهة (event_time == bar_time الشمعة
الجارية وهويتها من بناة المثبتات المشتركة).
"""

from __future__ import annotations

import math
from datetime import timedelta

import pytest
from _structure_fixtures import BASE_TIME, INSTRUMENT, TIMEFRAME, make_candle, make_vol_state
from schemas import (
    BreakDirection,
    DisplacementEventPayload,
    EventType,
    FvgDirection,
    OrderBlockEventPayload,
    StructureBreakPayload,
    SwingScope,
)
from structure.events import EmittedEvent
from structure.order_blocks import OrderBlockTracker

#: ATR ثابت — التسامح = 2.0 × 0.25 = 0.5 (مسافة التراص).
_ATR = 2.0


def _displacement(
    bar_index: int,
    direction: BreakDirection,
    *,
    atr_multiple: float = 2.0,
) -> EmittedEvent:
    """حدث إزاحة مؤكد مصنوع يدويًا بطابع شمعة ``bar_index``."""
    event_type = (
        EventType.DISPLACEMENT_UP if direction is BreakDirection.UP else EventType.DISPLACEMENT_DOWN
    )
    bar_time = BASE_TIME + timedelta(minutes=bar_index)
    return EmittedEvent(
        event_type=event_type,
        event_time=bar_time,
        payload=DisplacementEventPayload(
            instrument=INSTRUMENT,
            timeframe=TIMEFRAME,
            bar_time=bar_time,
            direction=direction,
            range_zscore=1.5,
            body_fraction=0.9,
            close_location=0.95 if direction is BreakDirection.UP else 0.05,
            atr_multiple=atr_multiple,
            velocity=3.0,
            follow_through=0.0,
        ),
    )


def _bos(
    bar_index: int,
    direction: BreakDirection,
    *,
    event_type: EventType = EventType.INTERNAL_BOS,
) -> EmittedEvent:
    """حدث كسر بنية مؤكد مصنوع يدويًا بطابع شمعة ``bar_index``."""
    bar_time = BASE_TIME + timedelta(minutes=bar_index)
    return EmittedEvent(
        event_type=event_type,
        event_time=bar_time,
        payload=StructureBreakPayload(
            instrument=INSTRUMENT,
            timeframe=TIMEFRAME,
            bar_time=bar_time,
            swing_id="sw-test",
            swing_scope=SwingScope.INTERNAL,
            break_direction=direction,
            breach_distance_atr=1.5,
            closing_acceptance=0.8,
            follow_through=0.0,
            choch_prior_direction=None,
        ),
    )


def _ob_payload(events: list[EmittedEvent]) -> OrderBlockEventPayload:
    """تضييق حدث الكتلة الوحيد — الحمولة OrderBlockEventPayload حصرًا."""
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, OrderBlockEventPayload)
    return payload


# ═══════════ خطوتا 2 و4: التتبع الخلفي وتحديد المنطقة المصدرية ═══════════


class TestSourceTracing:
    """الشمعة المعاكسة الأخيرة أو العنقود المتراص قبل الاندفاع."""

    def test_single_opposing_candle_source(self) -> None:
        """شمعة معاكسة منفردة: المنطقة [low, high] وطابعها أصلها."""
        tracker = OrderBlockTracker()
        # شمعة 0: هابطة معاكسة [99.5, 101.5]؛ 1: اندفاع صاعد؛ 2: إزاحة صاعدة
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.2, 103.0, 100.0, 102.8), make_vol_state(_ATR))
        assert (
            tracker.update(
                make_candle(2, 103.0, 106.0, 102.8, 105.5),
                make_vol_state(_ATR),
                [_displacement(2, BreakDirection.UP)],
            )
            == []
        )  # مرشحة بلا بث — البث المؤجل
        assert tracker.order_blocks() == ()
        # شمعة 3: كسر موافق ⇒ البث بمنطقة الشمعة المعاكسة
        events = tracker.update(
            make_candle(3, 105.5, 107.0, 105.0, 106.5),
            make_vol_state(_ATR),
            (),
            [_bos(3, BreakDirection.UP)],
        )
        payload = _ob_payload(events)
        assert events[0].event_type is EventType.ORDER_BLOCK_BULLISH
        assert payload.zone_low == pytest.approx(99.5)
        assert payload.zone_high == pytest.approx(101.5)
        assert payload.direction is FvgDirection.BULLISH
        assert payload.structure_consequence.value == "BOS"

    def test_compact_cluster_merged(self) -> None:
        """عنقود معاكس متراص: مناطق الأعضاء متحدة وطابع الأقدم أصلاً."""
        tracker = OrderBlockTracker()
        # شمعتا 0-1 هابطتان متتراصتان (انفصال 0.3 ≤ تسامح 0.5)
        tracker.update(make_candle(0, 100.0, 100.2, 99.0, 99.4), make_vol_state(_ATR))
        tracker.update(make_candle(1, 99.7, 100.5, 98.8, 99.2), make_vol_state(_ATR))
        tracker.update(make_candle(2, 99.5, 102.5, 99.3, 102.2), make_vol_state(_ATR))
        tracker.update(
            make_candle(3, 102.2, 105.0, 102.0, 104.6),
            make_vol_state(_ATR),
            [_displacement(3, BreakDirection.UP)],
        )
        events = tracker.update(
            make_candle(4, 104.6, 106.0, 104.0, 105.5),
            make_vol_state(_ATR),
            (),
            [_bos(4, BreakDirection.UP)],
        )
        payload = _ob_payload(events)
        assert payload.zone_low == pytest.approx(98.8)  # أدنى قاع العنقود
        assert payload.zone_high == pytest.approx(100.5)  # أعلى قمته
        assert payload.origin_time == BASE_TIME  # طابع أقدم عضو (الشمعة 0)

    def test_separated_opposite_candle_not_clustered(self) -> None:
        """معاكسة بعد معاكسة بفاصل يتجاوز التسامح ⇒ المصدر الأخيرة وحدها."""
        tracker = OrderBlockTracker()
        # الشمعة 0 بعيدة (فاصل مدى 2.0 > 0.5) — لا تنضم للعنقود
        tracker.update(make_candle(0, 103.0, 103.5, 101.5, 102.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.0, 100.4, 99.0, 99.3), make_vol_state(_ATR))
        tracker.update(make_candle(2, 99.5, 102.5, 99.3, 102.2), make_vol_state(_ATR))
        tracker.update(
            make_candle(3, 102.2, 105.0, 102.0, 104.6),
            make_vol_state(_ATR),
            [_displacement(3, BreakDirection.UP)],
        )
        events = tracker.update(
            make_candle(4, 104.6, 106.0, 104.0, 105.5),
            make_vol_state(_ATR),
            (),
            [_bos(4, BreakDirection.UP)],
        )
        payload = _ob_payload(events)
        assert payload.zone_low == pytest.approx(99.0)  # الشمعة 1 وحدها
        assert payload.zone_high == pytest.approx(100.4)

    def test_no_opposing_candle_no_candidate(self) -> None:
        """كل السجل أجسام صاعدة (اندفاع) ⇒ لا مصدر ⇒ لا مرشحة ولا بث."""
        tracker = OrderBlockTracker()
        for i in range(3):
            tracker.update(
                make_candle(i, 100.0 + i, 101.5 + i, 99.8 + i, 101.2 + i),
                make_vol_state(_ATR),
                [_displacement(i, BreakDirection.UP)] if i == 2 else (),
            )
        assert (
            tracker.update(
                make_candle(3, 103.2, 105.0, 103.0, 104.6),
                make_vol_state(_ATR),
                (),
                [_bos(3, BreakDirection.UP)],
            )
            == []
        )
        assert tracker.order_blocks() == ()

    def test_doji_stops_trace(self) -> None:
        """الديدجة ليست معاكسة ولا اندفاعية — توقف التتبع فلا مصدر."""
        tracker = OrderBlockTracker()
        # شمعة 0 معاكسة هابطة، شمعة 1 ديدجة (close == open)، ثم الاندفاع
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.0, 101.0, 99.0, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(2, 100.5, 103.5, 100.3, 103.2), make_vol_state(_ATR))
        tracker.update(
            make_candle(3, 103.2, 105.0, 103.0, 104.6),
            make_vol_state(_ATR),
            [_displacement(3, BreakDirection.UP)],
        )
        assert (
            tracker.update(
                make_candle(4, 104.6, 106.0, 104.0, 105.5),
                make_vol_state(_ATR),
                (),
                [_bos(4, BreakDirection.UP)],
            )
            == []
        )


# ═══════════ خطوة 3: البث المؤجل بتحقق النتيجة البنيوية ═══════════


class TestDeferredEmission:
    """المرشحة تُبنى عند الإزاحة وتبث عند الكسر الموافق حصرًا."""

    def _candidate_ready(self) -> tuple[OrderBlockTracker, int]:
        """متعقّب بمرشحة معلقة من إزاحة صاعدة عند الشمعة 3."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.2, 103.0, 100.0, 102.8), make_vol_state(_ATR))
        tracker.update(make_candle(2, 103.0, 103.5, 102.5, 103.2), make_vol_state(_ATR))
        tracker.update(
            make_candle(3, 103.2, 106.0, 103.0, 105.6),
            make_vol_state(_ATR),
            [_displacement(3, BreakDirection.UP)],
        )
        return tracker, 4

    def test_opposite_direction_break_does_not_verify(self) -> None:
        """كسر معاكس الاتجاه لا يحقق المرشحة الصاعدة — تبقى معلقة."""
        tracker, bar = self._candidate_ready()
        assert (
            tracker.update(
                make_candle(bar, 105.0, 105.5, 102.0, 102.5),
                make_vol_state(_ATR),
                (),
                [_bos(bar, BreakDirection.DOWN)],
            )
            == []
        )
        assert tracker.order_blocks() == ()

    def test_stale_candidate_discarded_after_window(self) -> None:
        """انقضاء نافذة التحقق يدرد المرشحة نهائيًا — لا بث بعدها أبدًا."""
        tracker, bar = self._candidate_ready()
        # النافذة الافتراضية 5 — نتجاوزها بست شموع محايدة
        for i in range(bar, bar + 6):
            tracker.update(make_candle(i, 105.0, 105.5, 104.5, 105.2), make_vol_state(_ATR))
        assert (
            tracker.update(
                make_candle(bar + 6, 105.2, 107.0, 105.0, 106.6),
                make_vol_state(_ATR),
                (),
                [_bos(bar + 6, BreakDirection.UP)],
            )
            == []
        )
        assert tracker.order_blocks() == ()

    def test_bos_at_displacement_bar_verifies_same_bar(self) -> None:
        """نافذة صفرية صريحة: الكسر بشمعة الإزاحة نفسها يحقق فورًا."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.2, 103.0, 100.0, 102.8), make_vol_state(_ATR))
        events = tracker.update(
            make_candle(2, 103.0, 106.0, 102.8, 105.5),
            make_vol_state(_ATR),
            [_displacement(2, BreakDirection.UP)],
            [_bos(2, BreakDirection.UP)],
        )
        assert [e.event_type for e in events] == [EventType.ORDER_BLOCK_BULLISH]

    def test_bearish_naming_follows_displacement(self) -> None:
        """قطبية المنطقة تتبع الإزاحة: هابطة بعد معاكسة صاعدة ⇒ BEARISH."""
        tracker = OrderBlockTracker()
        # شمعة 0 معاكسة صاعدة [99.5, 101.5] قبل اندفاع هابط
        tracker.update(make_candle(0, 100.0, 101.5, 99.5, 101.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.8, 101.0, 98.0, 98.5), make_vol_state(_ATR))
        tracker.update(
            make_candle(2, 98.5, 99.0, 95.5, 96.0),
            make_vol_state(_ATR),
            [_displacement(2, BreakDirection.DOWN)],
        )
        events = tracker.update(
            make_candle(3, 96.0, 96.5, 94.0, 94.5),
            make_vol_state(_ATR),
            (),
            [_bos(3, BreakDirection.DOWN)],
        )
        payload = _ob_payload(events)
        assert events[0].event_type is EventType.ORDER_BLOCK_BEARISH
        assert payload.direction is FvgDirection.BEARISH
        assert payload.zone_low == pytest.approx(99.5)
        assert payload.zone_high == pytest.approx(101.5)


# ═══════════ خطوة 5: تتبع الاختبارات وردود الأفعال ═══════════


class TestRetestTracking:
    """حلقات التفاعل من الشريط التالي للبث — والرفض tanh مطبعًا."""

    def _live_block(self) -> OrderBlockTracker:
        """متعقّب بمنطقة حية منبعثة [99.5, 101.5] عند الشمعة 3."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.2, 103.0, 100.0, 102.8), make_vol_state(_ATR))
        tracker.update(make_candle(2, 103.0, 103.5, 102.5, 103.2), make_vol_state(_ATR))
        tracker.update(
            make_candle(3, 103.2, 106.0, 103.0, 105.6),
            make_vol_state(_ATR),
            [_displacement(3, BreakDirection.UP)],
            [_bos(3, BreakDirection.UP)],
        )
        assert tracker.order_blocks()
        return tracker

    def test_emission_bar_not_a_retest(self) -> None:
        """شمعة البث نفسها ليست اختبارًا (عقد الترويسة)."""
        tracker = self._live_block()
        (block,) = tracker.order_blocks()
        assert block.retest_count == 0
        assert block.last_reaction_score == 0.0  # غياب معلن لا دليل

    def test_consecutive_overlaps_one_loop(self) -> None:
        """شموع متتالية قاطعة للمنطقة = حلقة واحدة لا عدّة."""
        tracker = self._live_block()
        for i, close in enumerate((101.5, 102.2, 101.8), start=4):
            tracker.update(make_candle(i, 102.0, 103.0, 100.8, close), make_vol_state(_ATR))
        (block,) = tracker.order_blocks()
        assert block.retest_count == 1

    def test_gap_then_overlap_counts_new_loop(self) -> None:
        """شريط غير قاطع يغلق الحلقة — العودة حلقة ثانية."""
        tracker = self._live_block()
        tracker.update(make_candle(4, 102.0, 103.0, 100.8, 102.5), make_vol_state(_ATR))
        tracker.update(make_candle(5, 105.0, 106.0, 104.5, 105.5), make_vol_state(_ATR))  # بعيدة
        tracker.update(make_candle(6, 102.0, 103.0, 100.8, 102.4), make_vol_state(_ATR))
        (block,) = tracker.order_blocks()
        assert block.retest_count == 2

    def test_reaction_score_formula(self) -> None:
        """‏clamp01(tanh((close − zone_low)/atr)) للصاعدة — القيمة اليدوية."""
        tracker = self._live_block()
        close = 103.5
        tracker.update(make_candle(4, 103.0, 104.0, 100.8, close), make_vol_state(_ATR))
        (block,) = tracker.order_blocks()
        expected = max(0.0, min(1.0, math.tanh((close - 99.5) / _ATR)))
        assert block.last_reaction_score == pytest.approx(expected)

    def test_negative_rejection_clamped_to_zero(self) -> None:
        """إغلاق وراء الحافة البعيدة رفض منفي يُقص إلى 0.0."""
        tracker = self._live_block()
        tracker.update(make_candle(4, 100.5, 101.0, 99.0, 99.2), make_vol_state(_ATR))
        (block,) = tracker.order_blocks()
        assert block.last_reaction_score == 0.0

    def test_quality_within_unit_interval(self) -> None:
        """المتوسط الموزون المطبَّع ∈ [0, 1] دائمًا — مع اختبارات فعلية."""
        tracker = self._live_block()
        tracker.update(make_candle(4, 102.0, 103.0, 100.8, 102.5), make_vol_state(_ATR))
        for i in range(5, 12):
            tracker.update(
                make_candle(i, 102.5 + (i % 2), 103.5, 100.6, 102.0 + (i % 2)),
                make_vol_state(_ATR),
            )
        (block,) = tracker.order_blocks()
        assert 0.0 <= block.quality <= 1.0


# ═══════════ الحتمية والمعرفات ═══════════


class TestDeterminism:
    """‏ob_id وdisplacement_id مفاتيح uuid5 خالية من الأسعار."""

    ROWS = (
        (101.0, 101.5, 99.5, 100.0),
        (100.2, 103.0, 100.0, 102.8),
        (103.0, 103.5, 102.5, 103.2),
    )

    def test_same_sequence_identical(self) -> None:
        def run() -> tuple[tuple[tuple[str, dict[str, object]], ...], object]:
            tracker = OrderBlockTracker()
            events: list[EmittedEvent] = []
            for i, row in enumerate(self.ROWS):
                tracker.update(make_candle(i, *row), make_vol_state(_ATR))
            events.extend(
                tracker.update(
                    make_candle(3, 103.2, 106.0, 103.0, 105.6),
                    make_vol_state(_ATR),
                    [_displacement(3, BreakDirection.UP)],
                )
            )
            events.extend(
                tracker.update(
                    make_candle(4, 105.6, 107.0, 105.0, 106.5),
                    make_vol_state(_ATR),
                    (),
                    [_bos(4, BreakDirection.UP)],
                )
            )
            return tuple(
                (e.event_type, e.payload.model_dump()) for e in events
            ), tracker.order_blocks()

        assert run() == run()


# ═══════════ الصخب في التحقق (عقود التغذية) ═══════════


class TestNoisyValidation:
    """الرفض الصاخب عند المصدر — لا تجاهل ولا قص صامت."""

    def test_inconsistent_feed_atr_missing_rejected(self) -> None:
        """حدث إزاحة مع حالة تقلب بلا ATR — تناقض صريح يُرفض."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.2, 103.0, 100.0, 102.8), make_vol_state(_ATR))
        with pytest.raises(ValueError, match="غير متسقة"):
            tracker.update(
                make_candle(2, 103.0, 106.0, 102.8, 105.5),
                make_vol_state(None),
                [_displacement(2, BreakDirection.UP)],
            )

    def test_foreign_event_type_rejected(self) -> None:
        """حدث بنوع خارج الموضع (فجوة في موضع الإزاحة) — ValueError."""
        tracker = OrderBlockTracker()
        bar_time = BASE_TIME
        fvg_event = EmittedEvent(
            event_type=EventType.FVG_BULLISH,
            event_time=bar_time,
            payload=_displacement(0, BreakDirection.UP).payload,  # الحمولة لا تُفحص قبل النوع
        )
        with pytest.raises(ValueError, match="غير متوقع"):
            tracker.update(
                make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR), [fvg_event]
            )

    def test_mismatched_event_time_rejected(self) -> None:
        """حدث بطابع لا يطابق الشمعة الجارية — تسريب §26.3 يُرفض."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        with pytest.raises(ValueError, match="لا يطابق شمعة"):
            tracker.update(
                make_candle(1, 100.2, 103.0, 100.0, 102.8),
                make_vol_state(_ATR),
                [_displacement(0, BreakDirection.UP)],  # طابع الشمعة 0
            )

    def test_foreign_identity_rejected(self) -> None:
        """حمولة بهوية غريبة عن المتعقّب — ValueError صاخبة."""
        tracker = OrderBlockTracker()
        tracker.update(make_candle(0, 101.0, 101.5, 99.5, 100.0), make_vol_state(_ATR))
        displaced = _displacement(1, BreakDirection.UP)
        payload = displaced.payload.model_copy(update={"instrument": "OTHER:XYZ"})
        with pytest.raises(ValueError, match="هوية غريبة"):
            tracker.update(
                make_candle(1, 100.2, 103.0, 100.0, 102.8),
                make_vol_state(_ATR),
                [
                    EmittedEvent(
                        event_type=displaced.event_type,
                        event_time=displaced.event_time,
                        payload=payload,
                    )
                ],
            )
