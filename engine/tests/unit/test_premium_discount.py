"""اختبارات محرك الموقع premium/discount — بوابة المهمة 3-c (§11.7).

يُقفل حرفيًا بعقود :mod:`structure.premium_discount`:
- النطاق معرّى الاسم صراحةً (external_range وحده) من المتطرفات الخارجية
  المؤكدة — الرفض الملتبس: لا نطاق (غياب أحد الطرفين أو انحلاله) ⇒ لا
  حساب ولا بث، والمتطرفات الداخلية تُهمل للنطاق.
- المتساويات الصارمة حرفيًا: فوق المنصف PREMIUM وتحته DISCOUNT وعليه
  بالضبط NEUTRAL (حالة معلنة لا تُبث).
- البث عند الانتقالات حصرًا: أول تحديد بعد اكتمال النطاق يُبث (من
  UNKNOWN)، والعبور بين الجانبين يُبث، والبقاء والمرور بالمحايد لا.
- لا إعادة تعريف صامتة: النطاق يمتد وحده (السقف لا ينقص والأرضية لا
  ترتفع) وامتداد الشمعة نفسها يُعيد التقييم بحدود النطاق الجاري.
- normalized_distance = (close − eq)/(range/2) — يجوز تجاوز ±1 خارج النطاق.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import pytest
from _structure_fixtures import BASE_TIME, make_candle
from schemas import (
    EventType,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    Swing,
    SwingDirection,
    SwingScope,
)
from structure.events import EmittedEvent
from structure.premium_discount import (
    RANGE_NAME,
    PremiumDiscountEngine,
    PremiumDiscountLocation,
)

_ATR = 2.0


def _swing(
    index: int,
    price: float,
    direction: SwingDirection,
    *,
    scope: SwingScope = SwingScope.EXTERNAL,
) -> Swing:
    """متطرف مؤكد مصنوع يدويًا بطابع شمعة ``index``."""
    bar_time = BASE_TIME + timedelta(minutes=index)
    return Swing(
        swing_id=f"sw-{'h' if direction is SwingDirection.HIGH else 'l'}-{index}",
        price=price,
        timeframe="1m",
        direction=direction,
        strength=0.6,
        confirmation_time=bar_time,
        external_or_internal=scope,
        bar_time=bar_time,
    )


def _payload_of(events: Sequence[EmittedEvent]) -> PremiumDiscountEventPayload:
    """تضييق الحمولة الوحيدة — حمولة premium/discount الموثقة حصرًا."""
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, PremiumDiscountEventPayload)
    return payload


# ═══════════ النطاق معرّى الاسم: الرفض الملتبس ═══════════


class TestNamedRange:
    """‏external_range وحده — من الخارجية المؤكدة، والانحلال غياب معلن."""

    def test_no_range_no_events_no_crash(self) -> None:
        """بلا متطرفات خارجية: لا نطاق ولا حساب ولا بث — UNKNOWN معلنة."""
        engine = PremiumDiscountEngine()
        for i in range(5):
            assert engine.update(make_candle(i, 100.0, 101.0, 99.0, 100.5), ()) == []
        state = engine.state
        assert state.location is PremiumDiscountLocation.UNKNOWN
        assert state.range_low is None and state.range_high is None
        assert state.equilibrium is None
        assert state.range_name == RANGE_NAME == "external_range"

    def test_single_sided_range_pending(self) -> None:
        """قمة خارجية دون قاع أدنى منها سعرًا: التعريف يبقى معلقًا."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 101.0, 99.0, 100.5), [_swing(0, 101.0, SwingDirection.HIGH)]
        )
        assert engine.state.location is PremiumDiscountLocation.UNKNOWN
        # الطرف يُتتبع (الامتداد الأحادي يراكم الأطراف) والحساب وحده المعلق:
        # range_low غائب فلا منصف ولا موقع — «كله أو لا شيء» عناء الحساب
        assert engine.state.range_high == pytest.approx(101.0)
        assert engine.state.range_low is None
        assert engine.state.equilibrium is None

    def test_internal_swings_ignored_for_range(self) -> None:
        """المتطرفات الداخلية تُقبل في التغذية وتُهمل للنطاق (حركة داخلية)."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 101.0, 99.0, 100.5),
            [
                _swing(0, 110.0, SwingDirection.HIGH, scope=SwingScope.INTERNAL),
                _swing(0, 90.0, SwingDirection.LOW, scope=SwingScope.INTERNAL),
            ],
        )
        assert engine.state.location is PremiumDiscountLocation.UNKNOWN

    def test_both_sides_define_range(self) -> None:
        """قمة خارجية وقاع خارجي أدنى منها ⇒ النطاق معرف ومنصفه صحيح."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 101.0, 99.0, 100.5),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        # الإغلاق 100.5 فوق المنصف 100.0 ⇒ PREMIUM وأول تحديد يُبث
        state = engine.state
        assert state.range_low == pytest.approx(98.0)
        assert state.range_high == pytest.approx(102.0)
        assert state.equilibrium == pytest.approx(100.0)
        assert state.location is PremiumDiscountLocation.PREMIUM


# ═══════════ المتساويات الصارمة وجدول الانتقالات ═══════════


class TestLocationAndTransitions:
    """فوق المنصف PREMIUM وتحته DISCOUNT وعليه NEUTRAL — البث للانتقال حصرًا."""

    def _engine_with_range(self) -> PremiumDiscountEngine:
        """نطاق [98, 102] بمنصف 100 — أول موقع DISCOUNT عند الشمعة 0."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 100.5, 99.5, 99.5),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        assert engine.state.location is PremiumDiscountLocation.DISCOUNT
        return engine

    def test_first_definition_broadcasts_from_unknown(self) -> None:
        """أول تحديد بعد اكتمال النطاق يُبث (انتقال من غير المعرف)."""
        engine = PremiumDiscountEngine()
        events = engine.update(
            make_candle(0, 100.0, 100.5, 99.5, 99.5),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        assert [e.event_type for e in events] == [EventType.DISCOUNT_LOCATION]
        payload = _payload_of(events)
        assert payload.location is PremiumDiscountSide.DISCOUNT
        assert payload.range_name == "external_range"
        assert payload.range_low == pytest.approx(98.0)
        assert payload.range_high == pytest.approx(102.0)
        assert payload.equilibrium == pytest.approx(100.0)
        assert payload.normalized_distance == pytest.approx((99.5 - 100.0) / 2.0)

    def test_staying_in_side_no_broadcast(self) -> None:
        """البقاء في الجانب نفسه لا يُبث — انتقال فقط."""
        engine = self._engine_with_range()
        for i, close in enumerate((99.2, 99.8, 99.0), start=1):
            assert engine.update(make_candle(i, 100.0, 100.5, 98.5, close), ()) == []
        assert engine.state.location is PremiumDiscountLocation.DISCOUNT

    def test_crossing_broadcasts(self) -> None:
        """العبور بين الجانبين يُبث في الشمعة العابرة حصرًا."""
        engine = self._engine_with_range()
        events = engine.update(make_candle(1, 100.0, 101.0, 99.0, 100.8), ())
        assert [e.event_type for e in events] == [EventType.PREMIUM_LOCATION]
        # والعودة
        events = engine.update(make_candle(2, 100.5, 100.8, 98.5, 99.2), ())
        assert [e.event_type for e in events] == [EventType.DISCOUNT_LOCATION]

    def test_close_exactly_at_equilibrium_is_neutral_no_broadcast(self) -> None:
        """الإغلاق على المنصف بالضبط NEUTRAL — حالة تُقرأ لا تُبث."""
        engine = self._engine_with_range()
        assert engine.update(make_candle(1, 100.0, 101.0, 99.0, 100.0), ()) == []
        assert engine.state.location is PremiumDiscountLocation.NEUTRAL

    def test_return_to_same_side_via_neutral_no_broadcast(self) -> None:
        """DISCOUNT→NEUTRAL→DISCOUNT: لا عبور بين الجانبين فلا بث."""
        engine = self._engine_with_range()
        engine.update(make_candle(1, 100.0, 101.0, 99.0, 100.0), ())  # NEUTRAL
        assert engine.update(make_candle(2, 100.0, 100.5, 98.5, 99.4), ()) == []
        assert engine.state.location is PremiumDiscountLocation.DISCOUNT

    def test_normalized_distance_beyond_one_outside_range(self) -> None:
        """خارج النطاق معلومة لا خطأ — الإقصاء يتجاوز ±1 (موثق في 3-a)."""
        engine = self._engine_with_range()
        # رفع الموقع إلى PREMIUM أولًا ثم إغلاق دون أرضية النطاق (98):
        # انتقال فعلي يُبث والإقصاء (96 − 100)/2 = −2 يتجاوز −1
        engine.update(make_candle(1, 100.5, 101.0, 99.5, 100.8), ())  # PREMIUM
        assert engine.state.location is PremiumDiscountLocation.PREMIUM
        events = engine.update(make_candle(2, 97.5, 98.0, 95.0, 96.0), ())
        assert [e.event_type for e in events] == [EventType.DISCOUNT_LOCATION]
        payload = _payload_of(events)
        assert payload.normalized_distance == pytest.approx(-2.0)


# ═══════════ لا إعادة تعريف صامتة: الامتداد الأحادي ═══════════


class TestRangeExtension:
    """النطاق يمتد وحده — السقف لا ينقص والأرضية لا ترتفع أبدًا."""

    def test_new_external_high_extends_same_bar(self) -> None:
        """قمة خارجية فوق السقف ترفعه والموقع يُعاد تقييمه بحدود النطاق الجاري."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 100.5, 99.5, 99.5),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        assert engine.state.location is PremiumDiscountLocation.DISCOUNT
        # قمة خارجية جديدة 108: النطاق [98, 108] والمنصف 103 — الإغلاق 101
        # صار تحت المنصف الجديد (DISCOUNT ما زال) ولا بث لتغير حدود النطاق
        # وحدها... لكن الإغلاق 100.5: نغذي شمعة جديدة بإغلاق 101.0
        events = engine.update(
            make_candle(1, 100.5, 101.5, 100.0, 101.0),
            [_swing(1, 108.0, SwingDirection.HIGH)],
        )
        state = engine.state
        assert state.range_high == pytest.approx(108.0)
        assert state.equilibrium == pytest.approx(103.0)
        assert state.location is PremiumDiscountLocation.DISCOUNT
        assert events == []  # DISCOUNT → DISCOUNT: لا انتقال

    def test_range_never_shrinks(self) -> None:
        """قمة خارجية أدنى من السقف لا تحركه، وقاع أعلى من الأرضية كذلك."""
        engine = PremiumDiscountEngine()
        engine.update(
            make_candle(0, 100.0, 100.5, 99.5, 100.5),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        engine.update(
            make_candle(1, 100.5, 101.0, 100.0, 100.8),
            [
                _swing(1, 101.0, SwingDirection.HIGH),  # دون السقف 102
                _swing(1, 99.0, SwingDirection.LOW),  # فوق الأرضية 98
            ],
        )
        state = engine.state
        assert state.range_high == pytest.approx(102.0)  # لم ينقص
        assert state.range_low == pytest.approx(98.0)  # لم يرتفع

    def test_extension_reassessment_same_bar_can_broadcast(self) -> None:
        """امتداد الشمعة نفسها يعيد التقييم: PREMIUM صار DISCOUNT بالسقف الجديد."""
        engine = PremiumDiscountEngine()
        # النطاق [98, 102] منصف 100 والإغلاق 100.8 ⇒ PREMIUM (بث أول)
        events = engine.update(
            make_candle(0, 100.0, 101.0, 99.5, 100.8),
            [
                _swing(0, 102.0, SwingDirection.HIGH),
                _swing(0, 98.0, SwingDirection.LOW),
            ],
        )
        assert [e.event_type for e in events] == [EventType.PREMIUM_LOCATION]
        # قمة خارجية 104 ترفع السقف: المنصف 101 والإغلاق 100.8 صار تحته
        events = engine.update(
            make_candle(1, 100.8, 101.5, 100.4, 100.8),
            [_swing(1, 104.0, SwingDirection.HIGH)],
        )
        assert [e.event_type for e in events] == [EventType.DISCOUNT_LOCATION]
        assert engine.state.range_high == pytest.approx(104.0)


# ═══════════ الحتمية ═══════════


class TestDeterminism:
    """نفس الشموع والمتطرفات ⇒ نفس الأحداث والحالة بالتطابق التام."""

    ROWS = (
        (100.0, 100.5, 99.5, 99.5),
        (100.0, 101.0, 99.0, 100.8),
        (100.5, 100.8, 98.5, 99.2),
        (99.5, 100.5, 99.0, 100.2),
    )

    def test_same_sequence_identical(self) -> None:
        def run() -> tuple[tuple[tuple[str, dict[str, object]], ...], object]:
            engine = PremiumDiscountEngine()
            events: list[EmittedEvent] = []
            swings: tuple[list[Swing], ...] = (
                [_swing(0, 102.0, SwingDirection.HIGH), _swing(0, 98.0, SwingDirection.LOW)],
                [],
                [_swing(2, 104.0, SwingDirection.HIGH)],
                [],
            )
            for i, row in enumerate(self.ROWS):
                events.extend(engine.update(make_candle(i, *row), swings[i]))
            return tuple(
                (e.event_type.value, dict(e.payload.model_dump())) for e in events
            ), engine.state

        assert run() == run()


# ═══════════ الحوارس الصاخبة ═══════════


class TestGuards:
    """عقود الشمعة الموحدة — نفس رفض بقية كواشف §11."""

    def test_developing_candle_rejected(self) -> None:
        engine = PremiumDiscountEngine()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            engine.update(make_candle(0, 100.0, 101.0, 99.0, 100.5, is_closed=False), ())

    def test_identity_mix_rejected(self) -> None:
        engine = PremiumDiscountEngine()
        engine.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), ())
        with pytest.raises(ValueError, match="خلط أطر زمنية"):
            engine.update(make_candle(1, 100.0, 101.0, 99.0, 100.5, timeframe="5m"), ())
