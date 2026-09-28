"""اختبارات متعقّب فجوات القيمة العادلة — بوابة المهمة 3-c (§11.5).

يُقفل حرفيًا بعقود :mod:`structure.fvg`:
- الكشف الثلاثي القطعي (المساواة ليست فجوة) والفاصلان الصحيحان
  والاستحالة البرهانية للاجتماع.
- البث مرة واحدة عند التكوين بحمولة CREATED (الملء/الإبطال تتبعيان
  لا يُبثان — قاموس §20 لا يعرف «فجوة مملوءة»).
- آلة الحالة CREATED→MITIGATED→FILLED/INVALIDATED بقفز INVALIDATED
  المباشر من أي حالة، ورتابة fill_fraction غير المتناقصة المقصوصة.
- «لا يُفترض أن كل فجوة يجب أن تُملأ» (§11.5 حرفيًا): بقاء أبدي بلا
  انتهاء صلاحية ولا تقليم.
- غياب ATR يمنع التكوين كله والفجوة المتعذرة لا تُلتقط لاحقًا.
- الحوارس الصاخبة (§27 والهوية والترتيب وحالة تقلب مستقبلية).

هندسة التسلسلات: كل شمعة لاحقة محقوبة ضد قاعدة «الشمعة قبل السابقة»
(لا تصنع فجوات عرضية غير مقصودة) — الشمعة الوسطى عريضة المدى عمدًا
لتعزل فجوة الاختبار الوحيدة في السجل.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from _structure_fixtures import BASE_TIME, make_candle, make_vol_state
from schemas import EventType, FvgDirection, FvgEventPayload, FvgState
from structure.events import EmittedEvent
from structure.fvg import FvgLifecycle, FvgTracker

#: ATR ثابت — كل المقاييس قابلة للحساب اليدوي.
_ATR = 2.0

#: شموع التأسيس الثلاث (i, open, high, low, close) — فجوة صاعدة [100, 102]
#: عند الشمعة 2: الوسطى عريضة (98.5–106) فتحجب أي فجوة عرضية لاحقة
#: ضد قاعدة الشمعة-قبل-السابقة، وقاعها دون الفاصل لا يمس الفجوة.
_SETUP_ROWS = (
    (0, 99.0, 100.0, 98.0, 99.5),
    (1, 99.0, 106.0, 98.5, 100.0),
    (2, 102.0, 104.0, 102.0, 103.5),
)


def _form_bullish_gap(tracker: FvgTracker) -> FvgEventPayload:
    """تأسيس فجوة صاعدة واحدة بفاصل [100, 102] عند الشمعة 2 — حمولتها."""
    payload: FvgEventPayload | None = None
    for i, o, h, low, c in _SETUP_ROWS:
        events = tracker.update(make_candle(i, o, h, low, c), make_vol_state(_ATR))
        if events:
            (event,) = events
            assert event.event_type is EventType.FVG_BULLISH
            assert isinstance(event.payload, FvgEventPayload)
            payload = event.payload
    assert payload is not None, "التأسيس يجب أن يبث فجوة واحدة"
    return payload


def _feed(
    tracker: FvgTracker,
    rows: tuple[tuple[float, float, float, float], ...],
    *,
    start: int = 3,
) -> None:
    """تغذية صفوف (open, high, low, close) اعتبارًا من الشريط ``start``."""
    for i, row in enumerate(rows, start=start):
        tracker.update(make_candle(i, *row), make_vol_state(_ATR))


# ═══════════ §11.5: الكشف الثلاثي القطعي ═══════════


class TestDetection:
    """‏low[i] > high[i-2] صاعدة وhigh[i] < low[i-2] هابطة — قطعيًا."""

    def test_bullish_three_bar_gap(self) -> None:
        """فجوة صاعدة: فاصلها [high[i-2], low[i]] وحدثها عند شمعة i بالضبط."""
        tracker = FvgTracker()
        payload = _form_bullish_gap(tracker)
        assert payload.gap_low == pytest.approx(100.0)  # high[i-2]
        assert payload.gap_high == pytest.approx(102.0)  # low[i]
        assert payload.size_atr == pytest.approx(2.0 / _ATR)
        assert payload.direction is FvgDirection.BULLISH
        assert payload.state is FvgState.CREATED

    def test_bearish_three_bar_gap(self) -> None:
        """فجوة هابطة: فاصلها [high[i], low[i-2]] — المرآة الكاملة."""
        tracker = FvgTracker()
        tracker.update(make_candle(0, 101.0, 102.0, 100.0, 100.5), make_vol_state(_ATR))
        tracker.update(make_candle(1, 100.0, 101.5, 94.0, 100.0), make_vol_state(_ATR))
        events = tracker.update(make_candle(2, 96.5, 98.0, 96.0, 96.5), make_vol_state(_ATR))
        assert [e.event_type for e in events] == [EventType.FVG_BEARISH]
        payload = events[0].payload
        assert isinstance(payload, FvgEventPayload)
        assert payload.gap_low == pytest.approx(98.0)  # high[i]
        assert payload.gap_high == pytest.approx(100.0)  # low[i-2]
        assert payload.direction is FvgDirection.BEARISH

    def test_equality_is_not_a_gap(self) -> None:
        """‏low[i] == high[i-2] بالضبط ليست فجوة (نص §11.5 قاطع)."""
        tracker = FvgTracker()
        tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR))
        tracker.update(make_candle(1, 99.5, 106.0, 99.0, 100.2), make_vol_state(_ATR))
        # قاع [2] = 100.0 يساوي قمة [0] = 100.0 بالضبط — لا فجوة
        assert (
            tracker.update(make_candle(2, 100.5, 104.0, 100.0, 103.5), make_vol_state(_ATR)) == []
        )
        assert tracker.gaps() == ()

    def test_first_two_bars_never_detect(self) -> None:
        """لا شمعة i-2 قبل الشريط الثاني — أول شمعتين بلا كشف أصلًا."""
        tracker = FvgTracker()
        assert tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR)) == []
        assert (
            tracker.update(make_candle(1, 100.5, 106.0, 100.0, 105.0), make_vol_state(_ATR)) == []
        )
        assert tracker.gaps() == ()

    def test_at_most_one_event_per_bar(self) -> None:
        """برهان الترويسة: اجتماع القطبيتين تناقض — حدث واحد كأقصى دائمًا."""
        tracker = FvgTracker()
        for i, o, h, low, c in _SETUP_ROWS:
            assert len(tracker.update(make_candle(i, o, h, low, c), make_vol_state(_ATR))) <= 1


# ═══════════ آلة الحالة التتبعية (§11.5 «invalidation/consumption state») ═══════════


class TestFillLifecycle:
    """‏CREATED→MITIGATED→FILLED/INVALIDATED — الملء قياس مستمر صحيح."""

    def test_untouched_gap_stays_created_forever(self) -> None:
        """«لا يُفترض أن كل فجوة يجب أن تُملأ» — بقاء أبدي بلا تقليم."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        # شموع فوق الفاصل كليًا (قاعها 102.5 > 102) وبلا فجوات عرضية
        _feed(tracker, tuple((103.0, 105.0, 102.5, 104.0) for _ in range(9)))
        (gap,) = tracker.gaps()
        assert gap.state is FvgLifecycle.CREATED
        assert gap.fill_fraction == 0.0
        assert gap.first_mitigation_time is None

    def test_partial_fill_mitigates_with_first_time(self) -> None:
        """أول تغلغل جزئي: MITIGATED + first_mitigation_time بطابع شمعته."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        # تغلغل حتى 101 (نصف الفاصل) وإغلاق فوق الحافة القريبة
        _feed(tracker, ((103.5, 103.8, 101.0, 103.2),))
        (gap,) = tracker.gaps()
        assert gap.state is FvgLifecycle.MITIGATED
        assert gap.fill_fraction == pytest.approx(0.5)  # (102 − 101) / 2
        assert gap.first_mitigation_time == BASE_TIME + timedelta(minutes=3)

    def test_full_traversal_without_close_beyond_fills(self) -> None:
        """اجتياح كامل بالفتيل دون إغلاق وراء الحافة البعيدة ⇒ FILLED."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        _feed(tracker, ((101.5, 103.0, 99.5, 101.5),))
        (gap,) = tracker.gaps()
        assert gap.state is FvgLifecycle.FILLED
        assert gap.fill_fraction == 1.0

    def test_close_beyond_far_edge_invalidates_from_created(self) -> None:
        """إغلاق دون gap_low صراحة ⇒ INVALIDATED مباشرة من CREATED."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        _feed(tracker, ((101.0, 101.5, 99.0, 99.4),))
        (gap,) = tracker.gaps()
        assert gap.state is FvgLifecycle.INVALIDATED
        assert gap.fill_fraction == 1.0  # القياس مستمر حتى بعد الإبطال

    def test_invalidation_from_mitigated(self) -> None:
        """القفز إلى INVALIDATED من أي حالة — هنا من MITIGATED."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        _feed(tracker, ((103.5, 103.8, 101.0, 103.2),))
        assert tracker.gaps()[0].state is FvgLifecycle.MITIGATED
        _feed(tracker, ((101.5, 102.5, 99.0, 99.4),), start=4)
        assert tracker.gaps()[0].state is FvgLifecycle.INVALIDATED

    def test_fill_fraction_monotone_and_clipped(self) -> None:
        """رتابة غير متناقصة مقصوصة إلى [0, 1] مهما تعمق التغلغل."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        fractions: list[float] = []
        rows = (
            (102.8, 103.5, 101.5, 102.8),
            (102.8, 103.5, 100.5, 102.8),
            (102.8, 103.2, 98.0, 102.8),
            (102.8, 103.2, 97.0, 102.8),
        )
        for j, row in enumerate(rows):
            _feed(tracker, (row,), start=3 + j)
            fractions.append(tracker.gaps()[0].fill_fraction)
        assert fractions == sorted(fractions)  # رتيبة
        assert fractions[-1] == 1.0  # مقصوصة — لا 1.5 رغم القاع 97
        assert all(0.0 <= f <= 1.0 for f in fractions)

    def test_broadcast_once_no_rebroadcast_on_state_changes(self) -> None:
        """حدث واحد عند التكوين حصرًا — الملء والإبطال لا يُبثان أبدًا."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        emitted = 1  # حدث التكوين من المساعد
        for i, row in enumerate(
            (
                (103.2, 103.8, 101.0, 103.2),  # ملء جزئي
                (99.4, 102.5, 99.0, 99.4),  # إبطال بإغلاق دون الحافة
                (100.2, 102.0, 99.0, 100.0),  # ما بعد الإبطال
            ),
            start=3,
        ):
            emitted += len(tracker.update(make_candle(i, *row), make_vol_state(_ATR)))
        assert emitted == 1


# ═══════════ العتبات التطبيعية (§16): التطبيع أصل التكوين ═══════════


class TestAtrNormalization:
    """‏size_atr قسمة على ATR حالي — غيابه يمنع التكوين كله."""

    def test_no_detection_without_atr(self) -> None:
        """‏vol=None أو ATR غائب/منحل ⇒ لا تكوين ولا بث (لا حجم بلا أصل)."""
        for vol in (None, make_vol_state(None), make_vol_state(0.0)):
            tracker = FvgTracker()
            tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR))
            tracker.update(make_candle(1, 99.0, 106.0, 98.5, 100.0), make_vol_state(_ATR))
            assert tracker.update(make_candle(2, 102.0, 104.0, 102.0, 103.5), vol) == [], (
                f"التكوين يجب أن يُمنع عند {vol!r}"
            )
            assert tracker.gaps() == ()

    def test_warmup_gap_not_captured_retroactively(self) -> None:
        """الفجوة المتعذرة (دافئ) لا تُلتقط لاحقًا — الكشف لا يتأخر."""
        tracker = FvgTracker()
        for i, o, h, low, c in _SETUP_ROWS:
            tracker.update(make_candle(i, o, h, low, c), make_vol_state(None))
        assert tracker.gaps() == ()
        # ATR يتوفر لاحقًا — الفجوة الضائعة لا تعود (قاع هذه دون قمة الوسطى)
        assert tracker.update(make_candle(3, 100.0, 103.5, 99.0, 100.2), make_vol_state(_ATR)) == []
        assert tracker.gaps() == ()

    def test_fill_tracking_continues_without_atr(self) -> None:
        """غياب ATR يمنع التكوين الجديد ويستمر تتبع الملء للقائم."""
        tracker = FvgTracker()
        _form_bullish_gap(tracker)
        assert tracker.update(make_candle(3, 103.5, 103.8, 101.0, 103.2), None) == []
        (gap,) = tracker.gaps()
        assert gap.state is FvgLifecycle.MITIGATED
        assert gap.fill_fraction == pytest.approx(0.5)


# ═══════════ الحتمية والمعرفات ═══════════


class TestDeterminism:
    """‏gap_id مفتاح uuid5 خالٍ من الأسعار — نفس المدخلات ⇒ نفس كل شيء."""

    ROWS = (
        (99.0, 100.0, 98.0, 99.5),
        (99.0, 106.0, 98.5, 100.0),
        (102.0, 104.0, 102.0, 103.5),
        (103.5, 103.8, 101.0, 103.2),
        (102.8, 103.5, 100.5, 102.8),
    )

    def test_same_sequence_identical_snapshots(self) -> None:
        def run() -> tuple[tuple[tuple[str, dict[str, object]], ...], object]:
            tracker = FvgTracker()
            events: list[EmittedEvent] = []
            for i, row in enumerate(self.ROWS):
                events.extend(tracker.update(make_candle(i, *row), make_vol_state(_ATR)))
            return tuple(
                (e.event_type.value, dict(e.payload.model_dump())) for e in events
            ), tracker.gaps()

        assert run() == run()

    def test_gap_id_stable_across_instantiations(self) -> None:
        """المعرف دالة في (الوقت، الاتجاه) وحسب — لا الأسعار."""
        ids = []
        for _ in range(2):
            tracker = FvgTracker()
            _form_bullish_gap(tracker)
            ids.append(tracker.gaps()[0].gap_id)
        assert ids[0] == ids[1]


# ═══════════ الحوارس الصاخبة (§27 + الهوية + §26.3) ═══════════


class TestGuards:
    """الرفض الصاخب عند المصدر — لا تجاهل محسوب."""

    def test_developing_candle_rejected(self) -> None:
        tracker = FvgTracker()
        tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR))
        with pytest.raises(ValueError, match="المغلقة فقط"):
            tracker.update(
                make_candle(1, 99.5, 100.5, 99.0, 100.2, is_closed=False),
                make_vol_state(_ATR),
            )

    def test_identity_mix_rejected(self) -> None:
        tracker = FvgTracker()
        tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR))
        with pytest.raises(ValueError, match="خلط أطر زمنية"):
            tracker.update(
                make_candle(1, 99.5, 100.5, 99.0, 100.2, timeframe="5m"),
                make_vol_state(_ATR),
            )

    def test_late_or_duplicate_bar_rejected(self) -> None:
        tracker = FvgTracker()
        tracker.update(make_candle(1, 99.5, 100.5, 99.0, 100.2), make_vol_state(_ATR))
        with pytest.raises(ValueError, match="تكرار bar_time"):
            tracker.update(make_candle(1, 99.6, 100.6, 99.1, 100.3), make_vol_state(_ATR))

    def test_future_vol_state_rejected(self) -> None:
        """حالة تقلب بطابع أحدث من الشمعة — تسريب §26.3 يُرفض صاخبًا."""
        from datetime import UTC, datetime

        tracker = FvgTracker()
        tracker.update(make_candle(0, 99.0, 100.0, 98.0, 99.5), make_vol_state(_ATR))
        future_vol = make_vol_state(_ATR, bar_time=datetime(2026, 1, 5, 0, 5, tzinfo=UTC))
        with pytest.raises(ValueError, match="المستقبل"):
            tracker.update(make_candle(1, 99.5, 100.5, 99.0, 100.2), future_vol)
