"""اختبارات كاشف عناقيد الاختلال الصفّي — بوابة المهمة 4-c (§12.6 + §20).

يُقفل حرفيًا بعقود :mod:`orderflow.imbalance`:

- تصنيف الشريط من عداداته (الجهة الغالبة عند الحد؛ التعادل محايد).
- آلة السلسلة: امتداد/كسر/تصفير، والبث عند اكتمال ``min_cluster_bars``
  حصرًا عند آخر شريط في العنقيد (لا-نظرة-مستقبلية §26.3).
- النمو المتواصل: العنقيد المبث ينتهي عند إعلانه وسلسلة جديدة تبدأ —
  لا إعادة بث لنفس الأشرطة (لا رفرفة §27).
- درجات ``max_row_ratio`` الثلاث والتشبّع الموثق للصف الأحادي الجانب.
- حقن ``displacement_aligner`` (لا استيراد structure — عقد الاستقلال).
- الحتمية الصرفة والحوارس الصاخبة وحدود الحمولة (4-a).

هندسة التسلسلات: صفوف مختارة يدويًا بنسب قابلة للحساب الذهني
(30/10 = 3.0 بالضبط عند ``IMBALANCE_RATIO``) — بوابة المرحلة:
«fixtures هندسية مبنية يدويًا».
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import pytest
from _orderflow_fixtures import (
    BASE_TIME,
    INSTRUMENT,
    TIMEFRAME,
    make_bar_rows,
    make_footprint_bar,
)
from orderflow.events import EmittedEvent
from orderflow.imbalance import (
    SATURATED_ROW_RATIO,
    ImbalanceClusterConfig,
    ImbalanceClusterDetector,
)
from orderflow.rows import IMBALANCE_RATIO
from schemas import EventType, FootprintBar, ImbalanceClusterEventPayload, ImbalanceSide

# ═══════════ صفوف هندسية مبنية يدويًا (§38.1) ═══════════

#: صفوف شرائية قياسية: عدادات (2, 0) — النسب 3.0 بالضبط.
_BUY_ROWS = ((100.0, 30.0, 10.0), (101.0, 12.0, 4.0))
#: مرآة بيعية: عدادات (0, 2) — الجهة الغالبة SELL.
_SELL_ROWS = ((100.0, 10.0, 30.0), (101.0, 4.0, 12.0))
#: محايد: نسب 1.0 لا اختلال فيها — عدادات (0, 0).
_NEUTRAL_ROWS = ((100.0, 10.0, 10.0), (101.0, 5.0, 5.0))
#: تعادل العدّادين عند الحد: (2, 2) — لا جهة حاسمة (محايد يكسر السلسلة).
_TIE_ROWS = (
    (100.0, 30.0, 10.0),
    (101.0, 12.0, 4.0),
    (102.0, 10.0, 30.0),
    (103.0, 4.0, 12.0),
)
#: غالبة دون الحد: عدادات (1, 0) عند min_imbalance_count=2.
_BELOW_MIN_ROWS = ((100.0, 30.0, 10.0),)

#: عنقيد شرائي متنامٍ — أربعة أشرطة بعدادات شرائية متزايدة (2، 3، 4، 5):
#: الشريط الثاني يحمل صفًّا بيعيًا نسبته 50 (فخ الجهة المعاكسة — يجب
#: ألا يهيمن على ``max_row_ratio``)، وأقصى نسبة شرائية مصنّفة 6.0.
_INCREASING_ROWS: tuple[tuple[tuple[float, float, float], ...], ...] = (
    ((100.0, 30.0, 10.0), (101.0, 12.0, 4.0), (102.0, 5.0, 5.0)),
    (
        (100.0, 40.0, 10.0),
        (101.0, 30.0, 10.0),
        (102.0, 21.0, 7.0),
        (103.0, 2.0, 100.0),
    ),
    (
        (100.0, 50.0, 10.0),
        (101.0, 40.0, 10.0),
        (102.0, 30.0, 10.0),
        (103.0, 24.0, 8.0),
    ),
    (
        (100.0, 60.0, 10.0),
        (101.0, 50.0, 10.0),
        (102.0, 40.0, 10.0),
        (103.0, 30.0, 10.0),
        (104.0, 3.0, 1.0),
    ),
)


def _run(
    detector: ImbalanceClusterDetector,
    rows_specs: Sequence[tuple[tuple[float, float, float], ...]],
) -> list[EmittedEvent]:
    """تغذية الكاشف بمتتالية صفوف مرقّمة — الأحداث بترتيب البث."""
    events: list[EmittedEvent] = []
    for index, spec in enumerate(rows_specs):
        events.extend(detector.update(make_bar_rows(index, spec)))
    return events


def _payloads(events: list[EmittedEvent]) -> list[ImbalanceClusterEventPayload]:
    """حمولات العناقيد من الأحداث — الاختبار يفهم الحمولة ذاتيًا."""
    payloads = []
    for event in events:
        assert isinstance(event.payload, ImbalanceClusterEventPayload)
        payloads.append(event.payload)
    return payloads


# ═══════════ صلاحية البنّاء اليدوي (بوابة fixtures) ═══════════


class TestBarFixture:
    """البنّاء يبني ``FootprintBar`` صالحًا + صفوفه بالبناء الفعلي."""

    def test_builder_produces_valid_model(self) -> None:
        """البناء الفعلي يتحقق (pydantic صاخب) والعدادات تشتق من الصفوف."""
        bar_rows = make_bar_rows(0, _BUY_ROWS)
        assert bar_rows.bar.row_count == 2
        assert bar_rows.bar.buy_imbalance_count == 2
        assert bar_rows.bar.sell_imbalance_count == 0
        assert bar_rows.bar.buy_volume == pytest.approx(42.0)
        assert bar_rows.bar.sell_volume == pytest.approx(14.0)
        assert bar_rows.bar.poc == pytest.approx(100.0)  # أثقل صف (40 ضد 16)
        assert len(bar_rows.rows) == 2

    def test_poc_tie_breaks_to_lowest_price(self) -> None:
        """تعادل أثقل صفين ⇒ الأدنى سعرًا (قاعدة البنّاء الموثقة)."""
        bar_rows = make_bar_rows(0, ((100.0, 10.0, 10.0), (200.0, 15.0, 5.0)))
        assert bar_rows.bar.poc == pytest.approx(100.0)  # كلاهما 20

    def test_rows_must_be_strictly_ascending(self) -> None:
        with pytest.raises(ValueError, match="تصاعدية"):
            make_bar_rows(0, ((200.0, 10.0, 10.0), (100.0, 5.0, 5.0)))

    def test_bar_rows_rejects_zero_volume_bar(self) -> None:
        """عقد rows.py: الشريط بلا صفقات لا يُبنى."""
        with pytest.raises(ValueError, match="بلا صفقات"):
            make_bar_rows(0, ((100.0, 0.0, 0.0),))

    def test_counter_override_builds_pathological_case(self) -> None:
        """تجاوز العدادات صريح — لبناء المدخلات المرضية المقصودة."""
        bar_rows = make_bar_rows(
            0,
            ((100.0, 1.0, 100.0), (101.0, 1.0, 3.0)),
            buy_imbalance_count=2,
        )
        assert bar_rows.bar.buy_imbalance_count == 2  # المتجاوز — لا المشتق 0
        assert bar_rows.bar.sell_imbalance_count == 2  # المشتق: صفان بيعيان

    def test_bar_level_allows_zero_volume(self) -> None:
        """الشريط (بلا صفوف) صفر التداول جائز في طبقة البار — حصص 0.0 معلنة
        (حالة بيانات غير كافية)؛ المنع في طبقة BarRows وحدها."""
        bar = make_footprint_bar(0, ((100.0, 0.0, 0.0),))
        assert bar.total_volume == 0.0
        assert bar.buy_share == 0.0 and bar.sell_share == 0.0
        assert bar.poc == pytest.approx(100.0)


# ═══════════ §12.6: اكتمال العنقيد وبثّه ═══════════


class TestClusterEmission:
    """البث عند اكتمال ``min_cluster_bars`` حصرًا — حدث واحد للعنقيد."""

    def test_full_buy_cluster_four_bars(self) -> None:
        """أربعة أشرطة بعدادات متزايدة (2،3،4،5) وحد 4 ⇒ حدث واحد كامل.

        ``bar_count=4`` و``total_imbalances=14`` (2+3+4+5) و
        ``max_row_ratio=6.0`` محسوبة من الصفوف اليدوية — والفخ البيعي
        (نسبة 50) مستبعد بجهته.
        """
        detector = ImbalanceClusterDetector(ImbalanceClusterConfig(min_cluster_bars=4))
        events = _run(detector, _INCREASING_ROWS)
        assert [e.event_type for e in events] == [EventType.BUY_IMBALANCE_CLUSTER]
        (payload,) = _payloads(events)
        assert payload.side is ImbalanceSide.BUY
        assert payload.bar_count == 4
        assert payload.total_imbalances == 14
        assert payload.max_row_ratio == pytest.approx(6.0)
        assert payload.aligned_with_displacement is False
        assert payload.instrument == INSTRUMENT
        assert payload.timeframe == TIMEFRAME
        # الحدث عند آخر شريط في العنقيد (الرابع — BASE+3 دقائق).
        assert events[0].event_time == BASE_TIME + timedelta(minutes=3)
        assert payload.bar_time == BASE_TIME + timedelta(minutes=3)

    def test_default_threshold_emits_at_completion_bar_only(self) -> None:
        """الحد الافتراضي 3: البث عند الشريط الثالث حصرًا — الشريط الرابع
        سلسلة جديدة (لا إعادة بث ولا نمو لأثر رجعي §27)."""
        events = _run(ImbalanceClusterDetector(), _INCREASING_ROWS)
        assert [e.event_type for e in events] == [EventType.BUY_IMBALANCE_CLUSTER]
        (payload,) = _payloads(events)
        assert payload.bar_count == 3
        assert payload.total_imbalances == 9  # أشرطة 1-3 فقط (2+3+4)
        assert payload.max_row_ratio == pytest.approx(5.0)  # أقصى شرائي في 1-3
        assert payload.bar_time == BASE_TIME + timedelta(minutes=2)

    def test_continuation_forms_independent_new_cluster(self) -> None:
        """ستة أشرطة شرائية متتالية والحد 3 ⇒ عنقيدان مستقلان (3+3)."""
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS,) * 6,
        )
        assert [e.event_type for e in events] == [
            EventType.BUY_IMBALANCE_CLUSTER,
            EventType.BUY_IMBALANCE_CLUSTER,
        ]
        first, second = _payloads(events)
        assert first.bar_count == 3 and second.bar_count == 3
        assert first.bar_time == BASE_TIME + timedelta(minutes=2)
        assert second.bar_time == BASE_TIME + timedelta(minutes=5)  # سلسلة جديدة 4-6
        assert first.total_imbalances == 6 and second.total_imbalances == 6

    def test_below_threshold_then_restart_from_zero(self) -> None:
        """شريطان ثم انقطاع محايد ⇒ لا بث؛ السلسلة اللاحقة تعدّ من الصفر."""
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS, _BUY_ROWS, _NEUTRAL_ROWS, _BUY_ROWS, _BUY_ROWS, _BUY_ROWS),
        )
        (payload,) = _payloads(events)
        assert payload.bar_count == 3  # أشرطة 4-6 فقط — الشريطان الأولان سقطا
        assert payload.total_imbalances == 6
        assert payload.bar_time == BASE_TIME + timedelta(minutes=5)

    def test_opposite_bar_breaks_buy_chain(self) -> None:
        """شريط بيعي بين شرائيين يكسر الامتداد — لا عنقيد شرائي إطلاقًا."""
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS, _BUY_ROWS, _SELL_ROWS, _BUY_ROWS, _BUY_ROWS),
        )
        assert events == []

    def test_opposite_bar_starts_opposite_chain(self) -> None:
        """الكاسر البيعي أول سلسلة معاكسة — تكتمل هي الأخرى عند حدّها."""
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS, _BUY_ROWS, _SELL_ROWS, _SELL_ROWS, _SELL_ROWS),
        )
        assert [e.event_type for e in events] == [EventType.SELL_IMBALANCE_CLUSTER]
        (payload,) = _payloads(events)
        assert payload.side is ImbalanceSide.SELL
        assert payload.bar_count == 3  # أشرطة 3-5
        assert payload.total_imbalances == 6
        assert payload.max_row_ratio == pytest.approx(3.0)

    def test_tie_counters_is_neutral_break(self) -> None:
        """تعادل العدّادين (2، 2) لا جهة حاسمة — يكسر السلسلة."""
        bar_rows = make_bar_rows(0, _TIE_ROWS)
        assert (bar_rows.bar.buy_imbalance_count, bar_rows.bar.sell_imbalance_count) == (2, 2)
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS, _BUY_ROWS, _TIE_ROWS, _BUY_ROWS, _BUY_ROWS, _BUY_ROWS),
        )
        (payload,) = _payloads(events)
        assert payload.bar_count == 3
        assert payload.bar_time == BASE_TIME + timedelta(minutes=5)

    def test_dominant_below_min_is_neutral(self) -> None:
        """عدّاد غالب دون الحد (1 < 2) ⇒ الشريط محايد يكسر السلسلة."""
        events = _run(
            ImbalanceClusterDetector(),
            (_BUY_ROWS, _BELOW_MIN_ROWS, _BUY_ROWS, _BUY_ROWS, _BUY_ROWS),
        )
        (payload,) = _payloads(events)
        assert payload.bar_count == 3  # أشرطة 3-5 — الشريط الثاني كسر الأول
        assert payload.bar_time == BASE_TIME + timedelta(minutes=4)

    def test_min_one_counts_every_imbalanced_bar(self) -> None:
        """حد 1/1: كل شريط اختلالي عنقيد قائم بذاته (حدود bar_count ≥ 1)."""
        events = _run(
            ImbalanceClusterDetector(
                ImbalanceClusterConfig(min_imbalance_count=1, min_cluster_bars=1)
            ),
            (_BUY_ROWS, _NEUTRAL_ROWS, _SELL_ROWS),
        )
        assert [e.event_type for e in events] == [
            EventType.BUY_IMBALANCE_CLUSTER,
            EventType.SELL_IMBALANCE_CLUSTER,
        ]
        first, second = _payloads(events)
        assert first.bar_count == 1 and second.bar_count == 1
        assert first.total_imbalances == 2 and second.total_imbalances == 2


# ═══════════ درجات max_row_ratio الثلاث والتشبّع ═══════════


class TestMaxRowRatio:
    """القياس الصفّي الأمين: تصنيف بالجهة، واحتياط، وحيادي معلن."""

    def test_one_sided_row_saturates(self) -> None:
        """صف أحادي الجانب (شراء فقط) نسبته inf ⇒ تشبّع معلن لا انهيار."""
        rows = ((100.0, 50.0, 0.0), (101.0, 12.0, 4.0))  # عدادات (2, 0)
        events = _run(ImbalanceClusterDetector(), (rows,) * 3)
        (payload,) = _payloads(events)
        assert payload.max_row_ratio == SATURATED_ROW_RATIO

    def test_threshold_mismatch_falls_back_to_dominant(self) -> None:
        """حد كاشف 100 أعلى من نسب الصفوف ⇒ الاحتياط: أقصى صف شرائي خام."""
        detector = ImbalanceClusterDetector(
            ImbalanceClusterConfig(min_cluster_bars=4, ratio_min=100.0)
        )
        events = _run(detector, _INCREASING_ROWS)
        (payload,) = _payloads(events)
        assert payload.max_row_ratio == pytest.approx(6.0)  # أقصى مهيمن شرائي

    def test_neutral_floor_when_no_dominant_row(self) -> None:
        """لا صف مهيمن بالجهة أصلًا (مدخل متناقض) ⇒ الحيادي 1.0 معلنًا."""
        rows = ((100.0, 1.0, 100.0), (101.0, 1.0, 3.0))  # كلاهما بيعي الهيمنة
        detector = ImbalanceClusterDetector()
        events: list[EmittedEvent] = []
        for index in range(3):
            # عدادات متجاوزة تدّعي شرائية لا تصنعها الصفوف — الحالة المرضية.
            events.extend(
                detector.update(
                    make_bar_rows(index, rows, buy_imbalance_count=2, sell_imbalance_count=0)
                )
            )
        (payload,) = _payloads(events)
        assert payload.max_row_ratio == pytest.approx(1.0)


# ═══════════ حقن توائم الإزاحة (§12.6 «aligned with displacement») ═══════════


class TestDisplacementAligner:
    """المحقِن يقرر التوائم — الكاشف لا يستورد structure أبدًا."""

    def test_no_aligner_reports_false(self) -> None:
        """بلا محقِن: قيمة صادقة غير مدركة — False دائمًا."""
        events = _run(ImbalanceClusterDetector(), (_BUY_ROWS,) * 3)
        assert _payloads(events)[0].aligned_with_displacement is False

    def test_injected_true_aligner(self) -> None:
        detector = ImbalanceClusterDetector(displacement_aligner=lambda bars: True)
        events = _run(detector, (_BUY_ROWS,) * 3)
        assert _payloads(events)[0].aligned_with_displacement is True

    def test_aligner_decides_from_cluster_content(self) -> None:
        """محقِن يقرأ أشرطة العنقيد: دلتات موجبة ⇒ True؛ سالبة ⇒ False."""

        def all_positive(bars: Sequence[FootprintBar]) -> bool:
            return all(bar.delta > 0.0 for bar in bars)

        events = _run(
            ImbalanceClusterDetector(displacement_aligner=all_positive),
            (_BUY_ROWS,) * 3,
        )
        assert _payloads(events)[0].aligned_with_displacement is True  # دلتات +28
        # العنقيد المتنامي: شريطه الثاني دلتاه سالبة (−34) ⇒ لا توائم.
        detector = ImbalanceClusterDetector(
            ImbalanceClusterConfig(min_cluster_bars=4), displacement_aligner=all_positive
        )
        events = _run(detector, _INCREASING_ROWS)
        assert _payloads(events)[0].aligned_with_displacement is False

    def test_aligner_receives_exactly_cluster_bars(self) -> None:
        """المحقِن يرى أشرطة العنقيد وحدها بترتيبها — لا السلسلة المقفلة."""
        seen: list[tuple[int, ...]] = []

        def capture(bars: Sequence[FootprintBar]) -> bool:
            seen.append(tuple(int(b.bar_time.minute) for b in bars))
            return False

        _run(
            ImbalanceClusterDetector(displacement_aligner=capture),
            (_BUY_ROWS,) * 4,
        )
        assert seen == [(0, 1, 2)]  # العنقيد الأول فقط (3 أشرطة) — الرابع سلسلة جديدة


# ═══════════ لا-نظرة-مستقبلية (§26.3) ═══════════


class TestNoLookahead:
    """الإعلان عند الشريط الأخير في العنقيد حصرًا — لا تسريب من الذيل."""

    @staticmethod
    def _prefix_events(k: int) -> list[EmittedEvent]:
        detector = ImbalanceClusterDetector(ImbalanceClusterConfig(min_cluster_bars=4))
        return _run(detector, _INCREASING_ROWS[:k])

    def test_prefix_before_completion_emits_nothing(self) -> None:
        for k in (1, 2, 3):
            assert self._prefix_events(k) == [], f"بادئة {k} أشرطة يجب ألا تبث"

    def test_event_appears_exactly_at_completion(self) -> None:
        """عند k = الاكتمال (4) الحدث موجود — لا قبله ولا انتظارًا للكسر."""
        events = self._prefix_events(4)
        assert [e.event_type for e in events] == [EventType.BUY_IMBALANCE_CLUSTER]
        assert _payloads(events)[0].bar_time == BASE_TIME + timedelta(minutes=3)

    def test_event_stable_under_future_extension(self) -> None:
        """تمديد الذيل لا يغير الحدث المكتمل — لا رفرفة (§27)."""
        completed = self._prefix_events(4)
        digest = [(e.event_type.value, e.payload.model_dump_json()) for e in completed]
        detector = ImbalanceClusterDetector(ImbalanceClusterConfig(min_cluster_bars=4))
        extended = _run(detector, (*_INCREASING_ROWS, _NEUTRAL_ROWS, _NEUTRAL_ROWS))
        assert [(e.event_type.value, e.payload.model_dump_json()) for e in extended] == digest


# ═══════════ الحتمية الصرفة ═══════════


class TestDeterminism:
    """نفس التسلسل مرتين ⇒ نفس الأحداث (هاش) — بلا طوابع ولا عشوائية."""

    SEQUENCE: tuple[tuple[tuple[float, float, float], ...], ...] = (
        _BUY_ROWS,
        _BUY_ROWS,
        _BUY_ROWS,
        _SELL_ROWS,
        _SELL_ROWS,
        _SELL_ROWS,
        _NEUTRAL_ROWS,
        _BUY_ROWS,
        _BUY_ROWS,
        _BUY_ROWS,
    )

    def test_same_sequence_same_events_hash(self) -> None:
        def digest() -> tuple[tuple[str, str], ...]:
            events = _run(ImbalanceClusterDetector(), self.SEQUENCE)
            return tuple((e.event_type.value, e.payload.model_dump_json()) for e in events)

        first, second = digest(), digest()
        assert first == second
        assert hash(first) == hash(second)
        # ثلاثة عناقيد بترتيب البث: شرائي، بيعي، شرائي — بعد كل اكتمال.
        assert [t for t, _ in first] == [
            EventType.BUY_IMBALANCE_CLUSTER.value,
            EventType.SELL_IMBALANCE_CLUSTER.value,
            EventType.BUY_IMBALANCE_CLUSTER.value,
        ]


# ═══════════ حدود الحمولة (4-a) والتوثيق ═══════════


class TestPayloadContract:
    """bar_count ≥ 1 والعدادات غير سالبة — عبر بناء صالح فقط."""

    def test_bounds_hold_across_scenarios(self) -> None:
        scenarios: list[list[EmittedEvent]] = [
            _run(ImbalanceClusterDetector(), (_BUY_ROWS,) * 3),
            _run(ImbalanceClusterDetector(), (_SELL_ROWS,) * 5),
            _run(
                ImbalanceClusterDetector(ImbalanceClusterConfig(min_cluster_bars=1)),
                (_BUY_ROWS, _NEUTRAL_ROWS, _SELL_ROWS),
            ),
            _run(
                ImbalanceClusterDetector(ImbalanceClusterConfig(min_cluster_bars=4)),
                _INCREASING_ROWS,
            ),
        ]
        for events in scenarios:
            for payload in _payloads(events):
                assert payload.bar_count >= 1
                assert payload.total_imbalances >= 0
                assert payload.max_row_ratio > 0.0

    def test_identity_captured_from_first_bar(self) -> None:
        detector = ImbalanceClusterDetector()

        def identity() -> tuple[str | None, str | None]:
            """قراءة الهوية عبر دالة — يبطل تضييق mypy للخصائص (درس 3-b)."""
            return detector.instrument_id, detector.timeframe

        assert identity() == (None, None)
        detector.update(make_bar_rows(0, _BUY_ROWS))
        assert identity() == (INSTRUMENT, TIMEFRAME)

    def test_explicit_identity_preserved(self) -> None:
        detector = ImbalanceClusterDetector(instrument_id=INSTRUMENT, timeframe=TIMEFRAME)
        events = _run(detector, (_BUY_ROWS,) * 3)
        assert _payloads(events)[0].instrument == INSTRUMENT


# ═══════════ الحوارس الصاخبة (§27 + الهوية + الترتيب) ═══════════


class TestGuards:
    """الرفض الصاخب عند المصدر — لا تجاهل محسوب."""

    def test_developing_bar_rejected(self) -> None:
        detector = ImbalanceClusterDetector()
        detector.update(make_bar_rows(0, _BUY_ROWS))
        with pytest.raises(ValueError, match="المغلقة فقط"):
            detector.update(make_bar_rows(1, _BUY_ROWS, is_closed=False))

    def test_instrument_mix_rejected(self) -> None:
        detector = ImbalanceClusterDetector()
        detector.update(make_bar_rows(0, _BUY_ROWS))
        with pytest.raises(ValueError, match="خلط أدوات"):
            detector.update(make_bar_rows(1, _BUY_ROWS, instrument_id="BINANCE_USDM:ETHUSDT"))

    def test_timeframe_mix_rejected(self) -> None:
        detector = ImbalanceClusterDetector()
        detector.update(make_bar_rows(0, _BUY_ROWS))
        with pytest.raises(ValueError, match="خلط أطر"):
            detector.update(make_bar_rows(1, _BUY_ROWS, timeframe="5m"))

    def test_duplicate_bar_time_rejected(self) -> None:
        detector = ImbalanceClusterDetector()
        detector.update(make_bar_rows(1, _BUY_ROWS))
        with pytest.raises(ValueError, match="تكرار bar_time"):
            detector.update(make_bar_rows(1, _BUY_ROWS))

    def test_late_bar_time_rejected(self) -> None:
        detector = ImbalanceClusterDetector()
        detector.update(make_bar_rows(2, _BUY_ROWS))
        with pytest.raises(ValueError, match="متأخر"):
            detector.update(make_bar_rows(1, _BUY_ROWS))

    def test_partial_identity_rejected(self) -> None:
        with pytest.raises(ValueError, match="الهوية تُمرَّر كاملة"):
            ImbalanceClusterDetector(instrument_id=INSTRUMENT)


# ═══════════ الإعداد (الصخب في التحقق) ═══════════


class TestConfigValidation:
    """الإعداد الفاسد يُرفض عند البناء — لا قيم مزيفة."""

    def test_defaults(self) -> None:
        config = ImbalanceClusterConfig()
        assert config.min_imbalance_count == 2
        assert config.min_cluster_bars == 3
        assert config.ratio_min == IMBALANCE_RATIO

    def test_invalid_min_imbalance_count(self) -> None:
        with pytest.raises(ValueError, match="min_imbalance_count"):
            ImbalanceClusterConfig(min_imbalance_count=0)

    def test_invalid_min_cluster_bars(self) -> None:
        with pytest.raises(ValueError, match="min_cluster_bars"):
            ImbalanceClusterConfig(min_cluster_bars=0)

    @pytest.mark.parametrize("bad", [1.0, 0.5, float("inf"), float("nan")])
    def test_invalid_ratio_min(self, bad: float) -> None:
        with pytest.raises(ValueError, match="ratio_min"):
            ImbalanceClusterConfig(ratio_min=bad)

    def test_valid_custom_config(self) -> None:
        config = ImbalanceClusterConfig(min_imbalance_count=1, min_cluster_bars=2, ratio_min=4.0)
        assert (config.min_imbalance_count, config.min_cluster_bars, config.ratio_min) == (
            1,
            2,
            4.0,
        )
