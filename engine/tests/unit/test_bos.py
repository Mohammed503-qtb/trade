"""اختبارات محرك كسر البنية BOS/CHoCH — بوابة المهمة 3-b الحرفية (§11.2-3).

منهاج §38.1 الإلزامي («BOS with wick-only break») بالاسم، وعقود bos.py
الموثقة كلها تُقفل هنا بمصغّرات محسومة يدويًا:

- عتبة ``DISPLACEMENT_MIN`` (‎atr×1.0‎ افتراضيًا): الكسر عند بلوغها بالضبط
  (حد مغلق) والإخفاق القريب دونها لا يستهلك المستوى (§27: السكوت ليس حالة).
- الخرق الفتيلي ليس كسرًا افتراضيًا («not merely an isolated wick») — وبسياسة
  ``wick_breaks_valid`` يُقبل بعتبة الإزاحة نفسها مقاسةً بامتداد الفتيل.
- التصنيف بالنطاق (داخلي/خارجي) وآلة الإطار الاتجاهية: التأسيس الأول
  EXTERNAL_BOS، أول مخالفة خارجية CHOCH تحمل ``choch_prior_direction``،
  وما تلاها من نفس الاتجاه استمرار EXTERNAL_BOS — والداخلية لا تمس الإطار.
- المقاييس (§11.2): ``breach_distance_atr`` و``closing_acceptance``
  بصيغتيهما الموثقتين محسوبتين يدويًا، و``follow_through=0.0`` معلنة (§26.3).
- استهلاك المستويات الأضعف وراء امتداد الشمعة الكاسرة، وحدث واحد لكل اتجاه
  بترتيب حتمي UP ثم DOWN.
- الدافئ (‎atr=None‎) والتقلب المنحل (‎atr≤0‎) لا تقييم فيهما إطلاقًا —
  والمستوى القديم يُكسر عند أول شمعة تُقيَّم فعلًا (بث بعد العلم لا رفرفة).
- حوارس ``on_swing`` الحصرية وحوارس التدفق المشتركة — رفض صاخب.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from _structure_fixtures import BASE_TIME, INSTRUMENT, TIMEFRAME, make_candle, make_vol_state
from schemas import (
    BreakDirection,
    EventType,
    StructureBreakPayload,
    Swing,
    SwingDirection,
    SwingScope,
)
from structure import BosConfig, EmittedEvent, StructureBreakEngine

#: ATR الثابت للمصغّرات — عتبة DISPLACEMENT_MIN = 2.0×1.0 = 2.0.
_ATR = 2.0


def _swing(
    swing_id: str,
    price: float,
    *,
    direction: SwingDirection,
    scope: SwingScope,
    bar_index: int,
    confirm_index: int,
    timeframe: str = TIMEFRAME,
) -> Swing:
    """متطرف مصنوع يدويًا — العلاقة القانونية (bar ≤ confirmation) محفوظة."""
    return Swing(
        swing_id=swing_id,
        price=price,
        timeframe=timeframe,
        direction=direction,
        strength=0.5,
        confirmation_time=BASE_TIME + timedelta(minutes=confirm_index),
        external_or_internal=scope,
        bar_time=BASE_TIME + timedelta(minutes=bar_index),
    )


def _engine_with_high_level(
    *,
    swing_id: str = "sw-h-100",
    price: float = 100.0,
    scope: SwingScope = SwingScope.EXTERNAL,
    wick_breaks_valid: bool = False,
) -> StructureBreakEngine:
    """محرك بهوية مثبتة (شمعة 0 دون المستوى) ومستوى قمة واحد مسجل قبل التقييم."""
    engine = StructureBreakEngine(BosConfig(wick_breaks_valid=wick_breaks_valid))
    engine.update(make_candle(0, 99.0, 99.5, 98.5, 99.2), make_vol_state(_ATR))
    engine.on_swing(
        _swing(
            swing_id,
            price,
            direction=SwingDirection.HIGH,
            scope=scope,
            bar_index=0,
            confirm_index=1,
        )
    )
    return engine


def _payload_of(events: list[EmittedEvent]) -> StructureBreakPayload:
    """تضييق اتحاد الحمولتين — حمولة محرك الكسور StructureBreakPayload حصرًا."""
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, StructureBreakPayload)
    return payload


def _direction(engine: StructureBreakEngine) -> BreakDirection | None:
    """قراءة اتجاه الإطار عبر دالة — لا تعبير عضو يُضيّقه mypy ويثبته.

    mypy يضيّق تعبيرات الأعضاء (الخصائص) عند ``is``/``len`` ويثبّت التضييق
    عبر استدعاءات المحرك اللاحقة (الخاصية لا تُبطل) فتنقض القراءات
    التالية زورًا — القراءة عبر استدعاء دالة تعيد النوع المعلن المفتوح
    في كل مرة (نتائج الاستدعاءات لا تُضيّق أصلًا).
    """
    return engine.framework_direction


def _highs(engine: StructureBreakEngine) -> tuple[Swing, ...]:
    """قراءة القمم الحية عبر دالة — نفس عقد :func:`_direction` بعينه."""
    return engine.unbroken_highs


def _break_payloads(events: list[EmittedEvent]) -> list[StructureBreakPayload]:
    """تضييق دفعة أحداث إلى حمولات الكسر — isinstance عنصرًا بعنصر فلا union-attr."""
    narrowed: list[StructureBreakPayload] = []
    for event in events:
        payload = event.payload
        if isinstance(payload, StructureBreakPayload):
            narrowed.append(payload)
    return narrowed


# ═══════════ §38.1 «BOS with wick-only break» — الخرق الفتيلي ═══════════


class TestWickOnlyBreak:
    """الفتيل يخرق المستوى والإغلاق يرتد داخله — ليس كسرًا إلا بسياسة صريحة."""

    def test_wick_pierce_close_back_inside_no_event_by_default(self) -> None:
        """الخرق الفتيلي (فائض 2.5 ≥ العتبة) مع إغلاق مرتد: لا حدث افتراضيًا."""
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 100.0, 102.5, 99.0, 99.5), make_vol_state(_ATR))
        assert events == []
        assert len(_highs(engine)) == 1  # لا استهلاك صامتًا — المستوى مسلَّح

    def test_wick_pierce_with_wick_breaks_valid_emits_event(self) -> None:
        """بسياسة الخرق الفتيلي: حدث بعتبة الإزاحة نفسها مقاسةً بامتداد الفتيل."""
        engine = _engine_with_high_level(wick_breaks_valid=True)
        events = engine.update(make_candle(1, 100.0, 102.5, 99.0, 99.5), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert events[0].event_type is EventType.EXTERNAL_BOS  # أول كسر خارجي = تأسيس
        assert events[0].event_time == BASE_TIME + timedelta(minutes=1)
        assert payload.instrument == INSTRUMENT
        assert payload.timeframe == TIMEFRAME
        assert payload.bar_time == BASE_TIME + timedelta(minutes=1)
        assert payload.swing_id == "sw-h-100"
        assert payload.break_direction is BreakDirection.UP
        assert payload.breach_distance_atr == pytest.approx(2.5 / _ATR)  # امتداد الفتيل
        assert payload.closing_acceptance == 0.0  # الإغلاق ارتد داخل النطاق — غياب القبول معلن
        assert payload.follow_through == 0.0
        assert payload.choch_prior_direction is None
        assert _direction(engine) is BreakDirection.UP

    def test_wick_pierce_does_not_consume_level_then_close_breaks_later(self) -> None:
        """المستوى الناجي من الفتيل يُكسر لاحقًا بالإغلاق — لا رفرفة ولا فقدان."""
        engine = _engine_with_high_level()
        engine.update(make_candle(1, 100.0, 102.5, 99.0, 99.5), make_vol_state(_ATR))
        events = engine.update(make_candle(2, 99.5, 102.3, 99.0, 102.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.swing_id == "sw-h-100"
        assert payload.breach_distance_atr == pytest.approx(1.0)  # (102-100)/2
        assert _highs(engine) == ()

    def test_wick_excursion_under_threshold_not_break_even_with_policy(self) -> None:
        """تحت سياسة الفتيل نفسها: امتداد الفتيل دون العتبة ليس خرقًا صالحًا."""
        engine = _engine_with_high_level(wick_breaks_valid=True)
        events = engine.update(make_candle(1, 100.0, 101.95, 99.5, 101.9), make_vol_state(_ATR))
        assert events == []
        assert len(_highs(engine)) == 1

    def test_close_crosses_under_threshold_wick_carries_the_break(self) -> None:
        """إغلاق عابر دون عتبة الإزاحة وفتيل فوقها: المسار الفتيلي يحمل الكسر."""
        engine = _engine_with_high_level(wick_breaks_valid=True)
        events = engine.update(make_candle(1, 100.0, 103.0, 99.0, 101.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.breach_distance_atr == pytest.approx(3.0 / _ATR)  # امتداد الفتيل 3.0
        assert payload.closing_acceptance == pytest.approx(1.0 / 3.0)  # (101-100)/(103-100)


# ═══════════ عتبة DISPLACEMENT_MIN: الحد المغلق والإخفاق القريب ═══════════


class TestCloseBreakThreshold:
    """عتبة الكسر = atr×مضاعف DISPLACEMENT_MIN (§16) — بلوغها كسر ودونها سكوت."""

    def test_close_exactly_at_threshold_emits_boundary_event(self) -> None:
        """إغلاق يتجاوز المستوى بمقدار العتبة بالضبط (2.0 = atr×1.0) ⇒ حدث."""
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 100.0, 102.5, 99.0, 102.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.breach_distance_atr == pytest.approx(1.0)  # 2.0/atr
        assert payload.closing_acceptance == pytest.approx(0.8)  # (102-100)/(102.5-100)

    def test_close_beyond_but_under_threshold_near_miss_keeps_level_armed(self) -> None:
        """الإخفاق القريب: عبور دون العتبة لا حدث فيه ولا استهلاك (§27) — ثم يُكسر."""
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 100.0, 101.95, 99.5, 101.9), make_vol_state(_ATR))
        assert events == []
        assert len(_highs(engine)) == 1
        events = engine.update(make_candle(2, 101.9, 102.4, 101.0, 102.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.swing_id == "sw-h-100"
        assert _highs(engine) == ()

    def test_close_exactly_at_level_is_not_a_crossing(self) -> None:
        """مساواة الإغلاق للمستوى ليست عبورًا (عقد _nearest_level) — لا حدث."""
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 99.5, 100.5, 99.0, 100.0), make_vol_state(_ATR))
        assert events == []
        assert len(_highs(engine)) == 1


# ═══════════ التصنيف بالنطاق (§11.2 «classify as internal or external») ═══════════


class TestScopeClassification:
    """نطاق المتطرف المكسور يحدد النوع — والداخلية لا تمس آلة الإطار أصلًا."""

    def test_external_level_break_is_external_bos(self) -> None:
        engine = _engine_with_high_level(scope=SwingScope.EXTERNAL)
        events = engine.update(make_candle(1, 99.0, 103.5, 98.5, 103.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert events[0].event_type is EventType.EXTERNAL_BOS
        assert payload.swing_scope is SwingScope.EXTERNAL
        assert _direction(engine) is BreakDirection.UP

    def test_internal_level_break_is_internal_bos_framework_untouched(self) -> None:
        engine = _engine_with_high_level(scope=SwingScope.INTERNAL)
        events = engine.update(make_candle(1, 99.0, 103.5, 98.5, 103.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert events[0].event_type is EventType.INTERNAL_BOS
        assert payload.swing_scope is SwingScope.INTERNAL
        assert _direction(engine) is None  # الداخلية حركة داخل الإطار

    def test_internal_break_against_framework_is_internal_bos_not_choch(self) -> None:
        """كسر داخلي معاكس لإطار قائم: INTERNAL_BOS — لا CHoCH ولا مساسًا للإطار."""
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 99.0, 99.5, 98.5, 99.2), make_vol_state(_ATR))
        engine.on_swing(
            _swing(
                "sw-h-100",
                100.0,
                direction=SwingDirection.HIGH,
                scope=SwingScope.EXTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        first = engine.update(make_candle(1, 99.0, 103.5, 98.5, 103.0), make_vol_state(_ATR))
        assert [e.event_type for e in first] == [EventType.EXTERNAL_BOS]
        engine.on_swing(
            _swing(
                "sw-l-95",
                95.0,
                direction=SwingDirection.LOW,
                scope=SwingScope.INTERNAL,
                bar_index=1,
                confirm_index=2,
            )
        )
        second = engine.update(make_candle(2, 103.0, 103.5, 92.5, 93.0), make_vol_state(_ATR))
        payload = _payload_of(second)
        assert second[0].event_type is EventType.INTERNAL_BOS
        assert payload.break_direction is BreakDirection.DOWN
        assert payload.choch_prior_direction is None
        assert _direction(engine) is BreakDirection.UP  # الإطار لم يتحرك


# ═══════════ آلة الإطار الاتجاهية: CHoCH (§11.3) ═══════════


class TestChochMachine:
    """التأسيس ثم أول مخالفة خارجية CHOCH ثم استمرار الإطار الجديد."""

    def test_choch_sequence_and_framework_transitions(self) -> None:
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 99.0, 99.5, 98.5, 99.2), make_vol_state(_ATR))
        assert _direction(engine) is None
        engine.on_swing(
            _swing(
                "sw-h-100",
                100.0,
                direction=SwingDirection.HIGH,
                scope=SwingScope.EXTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        # (1) أول كسر خارجي على الإطلاق: EXTERNAL_BOS تأسيسًا — لا نمط سابق ليُنتَهك.
        first = engine.update(make_candle(1, 99.0, 103.5, 98.5, 103.0), make_vol_state(_ATR))
        payload = _payload_of(first)
        assert first[0].event_type is EventType.EXTERNAL_BOS
        assert payload.choch_prior_direction is None
        assert _direction(engine) is BreakDirection.UP
        # شمعة هابطة تؤسس مرساة قاع خارجي @90 ثم تُغذى كسوق قبل تقييم الكاسرة.
        assert engine.update(make_candle(2, 103.0, 103.5, 90.0, 100.0), make_vol_state(_ATR)) == []
        engine.on_swing(
            _swing(
                "sw-l-90",
                90.0,
                direction=SwingDirection.LOW,
                scope=SwingScope.EXTERNAL,
                bar_index=2,
                confirm_index=3,
            )
        )
        # (2) أول كسر خارجي معاكس للإطار: CHOCH يحمل اتجاه الاستمرار المنتَهَك.
        second = engine.update(make_candle(3, 100.0, 100.5, 87.5, 88.0), make_vol_state(_ATR))
        payload = _payload_of(second)
        assert second[0].event_type is EventType.CHOCH
        assert payload.choch_prior_direction is BreakDirection.UP
        assert payload.break_direction is BreakDirection.DOWN
        assert payload.breach_distance_atr == pytest.approx(1.0)  # (90-88)/atr
        assert payload.closing_acceptance == pytest.approx(0.8)  # (90-88)/(90-87.5)
        assert _direction(engine) is BreakDirection.DOWN
        # شمعة عابرة ثم مرساة قاع خارجي ثانية @85.
        assert engine.update(make_candle(4, 88.0, 89.0, 87.0, 88.5), make_vol_state(_ATR)) == []
        engine.on_swing(
            _swing(
                "sw-l-85",
                85.0,
                direction=SwingDirection.LOW,
                scope=SwingScope.EXTERNAL,
                bar_index=4,
                confirm_index=5,
            )
        )
        # (3) كسر خارجي ثانٍ بنفس الاتجاه الجديد: استمرار EXTERNAL_BOS — لا CHoCH.
        third = engine.update(make_candle(5, 88.5, 89.0, 82.5, 83.0), make_vol_state(_ATR))
        payload = _payload_of(third)
        assert third[0].event_type is EventType.EXTERNAL_BOS
        assert payload.choch_prior_direction is None
        assert payload.break_direction is BreakDirection.DOWN
        assert _direction(engine) is BreakDirection.DOWN


# ═══════════ المقاييس (§11.2) — محسوبة يدويًا على مصغّر ═══════════


class TestMeasures:
    """breach_distance_atr وclosing_acceptance بصيغتيهما الموثقتين + follow_through."""

    def test_up_break_measures_hand_computed(self) -> None:
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 99.0, 104.0, 98.5, 103.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.breach_distance_atr == pytest.approx(1.5)  # (103-100)/2
        assert payload.closing_acceptance == pytest.approx(0.75)  # (103-100)/(104-100)
        assert payload.follow_through == 0.0  # صفر شموع منقضية بعد الكسر (§26.3)

    def test_down_break_measures_hand_computed(self) -> None:
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 100.5, 101.0, 100.0, 100.8), make_vol_state(_ATR))
        engine.on_swing(
            _swing(
                "sw-l-100",
                100.0,
                direction=SwingDirection.LOW,
                scope=SwingScope.EXTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        events = engine.update(make_candle(1, 101.0, 101.5, 96.0, 97.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.break_direction is BreakDirection.DOWN
        assert payload.breach_distance_atr == pytest.approx(1.5)  # (100-97)/2
        assert payload.closing_acceptance == pytest.approx(0.75)  # (100-97)/(100-96)
        assert payload.follow_through == 0.0


# ═══════════ استهلاك المستويات وترتيب الأحداث ═══════════


class TestConsumeSemantics:
    """الكسر المُبلَّغ يبتلع ما دونه — وحدث واحد لكل اتجاه بترتيب حتمي."""

    def test_break_consumes_weaker_levels_behind_extension(self) -> None:
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 99.0, 99.5, 98.5, 99.2), make_vol_state(_ATR))
        engine.on_swing(
            _swing(
                "sw-h-100",
                100.0,
                direction=SwingDirection.HIGH,
                scope=SwingScope.EXTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        engine.on_swing(
            _swing(
                "sw-h-101",
                101.0,
                direction=SwingDirection.HIGH,
                scope=SwingScope.INTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        assert len(_highs(engine)) == 2
        events = engine.update(make_candle(1, 99.0, 103.5, 98.5, 103.0), make_vol_state(_ATR))
        payload = _payload_of(events)
        # المرجع المُبلَّغ: أقرب سقف دون الإغلاق (@101) — والأضعف (@100) ابتُلع صامتًا.
        assert payload.swing_id == "sw-h-101"
        assert payload.swing_scope is SwingScope.INTERNAL
        assert _highs(engine) == ()
        assert len(engine.swings) == 2  # السجل الكامل لا يُمس

    def test_both_directions_same_bar_up_first(self) -> None:
        """تسلسل مرضوخ نادر: كسر صاعد وهابط في الشمعة نفسها — UP ثم DOWN حتمًا."""
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 100.0, 100.5, 99.5, 100.0), make_vol_state(_ATR))
        engine.on_swing(
            _swing(
                "sw-h-995",
                99.5,
                direction=SwingDirection.HIGH,
                scope=SwingScope.INTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        engine.on_swing(
            _swing(
                "sw-l-104",
                104.0,
                direction=SwingDirection.LOW,
                scope=SwingScope.INTERNAL,
                bar_index=0,
                confirm_index=1,
            )
        )
        events = engine.update(make_candle(1, 100.0, 102.0, 99.0, 101.5), make_vol_state(_ATR))
        assert [e.event_type for e in events] == [EventType.INTERNAL_BOS, EventType.INTERNAL_BOS]
        payloads = _break_payloads(events)
        assert len(payloads) == len(events)
        assert [p.break_direction for p in payloads] == [
            BreakDirection.UP,
            BreakDirection.DOWN,
        ]
        assert _direction(engine) is None  # داخليتان — الإطار لم يُمس


# ═══════════ الدافئ والتقلب المنحل: لا تقييم بلا أصل ═══════════


class TestWarmupAndDegenerateAtr:
    """atr غائب أو منحل (≤0) ⇒ لا تقييم ولا استهلاك — والمستوى يُكسر عند أول تقييم."""

    def test_warmup_atr_none_no_evaluation_no_consumption(self) -> None:
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 100.0, 103.5, 99.5, 103.0), make_vol_state(None))
        assert events == []
        assert len(_highs(engine)) == 1  # لا استهلاك أثناء الدافئ
        events = engine.update(make_candle(2, 103.0, 104.0, 102.0, 103.5), make_vol_state(_ATR))
        payload = _payload_of(events)
        assert payload.swing_id == "sw-h-100"  # كسر مستوى قديم عند أول شمعة تُقيَّم فعلًا

    def test_degenerate_zero_atr_rejected_without_division(self) -> None:
        """خلل مصدري أُصلح: atr=0.0 كان يقسم على صفر في التطبيع — الآن لا تقييم."""
        engine = _engine_with_high_level()
        events = engine.update(make_candle(1, 100.0, 103.5, 99.5, 103.0), make_vol_state(0.0))
        assert events == []
        assert len(_highs(engine)) == 1
        events = engine.update(make_candle(2, 103.0, 104.0, 102.0, 103.5), make_vol_state(_ATR))
        assert _payload_of(events).swing_id == "sw-h-100"


# ═══════════ الحوارس الصاخبة — عقود on_sway والحارس المشترك ═══════════


class TestBosGuards:
    """حوارس on_swing الحصرية + حوارس التدفق المشتركة (_guards)."""

    @staticmethod
    def _warm_engine() -> StructureBreakEngine:
        engine = StructureBreakEngine()
        engine.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), make_vol_state(_ATR))
        return engine

    def test_swing_before_any_candle_rejected(self) -> None:
        engine = StructureBreakEngine()
        with pytest.raises(ValueError, match="قبل أي شمعة"):
            engine.on_swing(
                _swing(
                    "sw-x",
                    100.0,
                    direction=SwingDirection.HIGH,
                    scope=SwingScope.EXTERNAL,
                    bar_index=0,
                    confirm_index=1,
                )
            )

    def test_swing_timeframe_mismatch_rejected(self) -> None:
        engine = self._warm_engine()
        with pytest.raises(ValueError, match="إطار مغاير"):
            engine.on_swing(
                _swing(
                    "sw-x",
                    100.0,
                    direction=SwingDirection.HIGH,
                    scope=SwingScope.EXTERNAL,
                    bar_index=0,
                    confirm_index=1,
                    timeframe="5m",
                )
            )

    def test_swing_bar_time_after_confirmation_rejected(self) -> None:
        engine = self._warm_engine()
        with pytest.raises(ValueError, match="علاقة قانونية"):
            engine.on_swing(
                _swing(
                    "sw-x",
                    100.0,
                    direction=SwingDirection.HIGH,
                    scope=SwingScope.EXTERNAL,
                    bar_index=3,
                    confirm_index=1,
                )
            )

    def test_duplicate_swing_id_rejected(self) -> None:
        engine = self._warm_engine()
        swing = _swing(
            "dup",
            100.0,
            direction=SwingDirection.HIGH,
            scope=SwingScope.EXTERNAL,
            bar_index=0,
            confirm_index=1,
        )
        engine.on_swing(swing)
        with pytest.raises(ValueError, match="مكرر المعرف"):
            engine.on_swing(swing)

    def test_decreasing_confirmation_time_rejected(self) -> None:
        engine = self._warm_engine()
        engine.on_swing(
            _swing(
                "sw-a",
                100.0,
                direction=SwingDirection.HIGH,
                scope=SwingScope.EXTERNAL,
                bar_index=1,
                confirm_index=2,
            )
        )
        with pytest.raises(ValueError, match="ترتيب تغذية متناقص"):
            engine.on_swing(
                _swing(
                    "sw-b",
                    99.0,
                    direction=SwingDirection.LOW,
                    scope=SwingScope.EXTERNAL,
                    bar_index=0,
                    confirm_index=1,
                )
            )

    def test_evolving_candle_rejected(self) -> None:
        engine = self._warm_engine()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            engine.update(
                make_candle(1, 100.0, 101.0, 99.0, 100.5, is_closed=False), make_vol_state(_ATR)
            )

    def test_duplicate_bar_time_rejected(self) -> None:
        engine = self._warm_engine()
        with pytest.raises(ValueError, match="تكرار bar_time"):
            engine.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), make_vol_state(_ATR))

    def test_future_volatility_state_rejected(self) -> None:
        engine = self._warm_engine()
        future = BASE_TIME + timedelta(minutes=3)
        with pytest.raises(ValueError, match="من المستقبل"):
            engine.update(
                make_candle(1, 100.0, 101.0, 99.0, 100.5),
                make_vol_state(_ATR, bar_time=future),
            )
