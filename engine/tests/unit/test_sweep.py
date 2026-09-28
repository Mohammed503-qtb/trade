"""اختبارات كاشف الاجتياح — بوابة المهمة 3-d (§10.4 + §38.1 + §26.3).

يُقفل بثوابت §38.1 المسمات: الاجتياح التام (اختراق بالعتبة الموثقة ثم
استرجاع داخل النافذة) والفاشل القارب (تغلغل دون العتبة ثم مغادرة)، ثم
الكسر بالقبول والاجتياح الجزئي والمجهول، وضرورة الشروط الخمسة شرطًا
شرطًا (سقوط أيّ منها ⇒ لا بث)، والتناظر السعري (LIQUIDITY_SWEEP_LOW)،
ووحدة التقييم لكل منطقة، والعبور القافز الحاسم، وسلوك ما قبل توفر ATR.
التغذية عبر الواجهة :class:`liquidity.engine.LiquidityEngine` حصرًا —
ترتيب «كشف قبل تحديث الخريطة» هو جوهر شرط 1 ويُختبر عبرها.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest
from _liquidity_fixtures import (
    INSTRUMENT,
    TIMEFRAME,
    candle,
    minutes,
    swing,
    vol,
    zone_uuid,
)
from liquidity import LiquidityEngine, SweepConfig
from liquidity.sweep import EmittedEvent
from schemas import (
    BreakAcceptEventPayload,
    EventType,
    LiquiditySide,
    SweepClassification,
    SweepEventPayload,
    SwingDirection,
    ZoneState,
)

_ATR = 2.0
#: العتبة المطلوبة لمنطقة صفرية العرض: max(atr×SWEEP_TOLERANCE, عرض×0.5) = 0.5.
_REQUIRED = 0.5


def _prior_key(swing_id: str) -> str:
    return f"{INSTRUMENT}|{TIMEFRAME}|PRIOR_SWING|{swing_id}"


def _engine_with_zone(
    *,
    atr: float | None = _ATR,
    level: float = 100.0,
    direction: SwingDirection = SwingDirection.HIGH,
    swing_id: str = "s1",
) -> tuple[LiquidityEngine, str]:
    """واجهة بمنطقة PRIOR_SWING صفرية العرض عند ``level`` (قمة أو قاع).

    الشمعة الأولى واسعة (95..105) فتستقر مناطق الجلسة بعيدًا عن مسار
    التسلسلات كلها (95 < low ≤ high < 105) — عزل الحمولة لمنطقة الاختبار
    وحدها. المنطقة تؤسس بالشمعة الثانية (الكاشف يقيّم قبلها) فلا تُجتاح
    بشمعة تأسيسها أبدًا (شرط 1 §10.4).
    """
    engine = LiquidityEngine()
    assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(atr)) == []
    assert (
        engine.update(
            candle(1, 100.0, 100.5, 99.5, 99.8),
            vol(atr),
            [swing(swing_id, level, direction, bar_time=minutes(1))],
        )
        == []
    )
    return engine, zone_uuid(_prior_key(swing_id))


def _engine_with_cluster(*, atr: float | None = _ATR) -> tuple[LiquidityEngine, str]:
    """واجهة بعنقود EQUAL_LEVEL بالمدى [100.0, 100.4] (تسامح 0.5).

    المتطرفان داخليان فلا تتأسس حدود نطاق — العرض 0.4 يجعل العتبة المطلوبة
    max(0.5, 0.2) = 0.5 (جزء التقلب هو الحاكم).
    """
    engine = LiquidityEngine()
    assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(atr)) == []
    for index, (sid, price) in enumerate((("A", 100.0), ("B", 100.4)), start=1):
        assert (
            engine.update(
                candle(index, 99.8, 99.9, 99.5, 99.8),  # دون مدى العنقود — لا لمس
                vol(atr),
                [swing(sid, price, SwingDirection.HIGH, bar_time=minutes(index))],
            )
            == []
        )
    return engine, zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|A,B")


def _feed(
    engine: LiquidityEngine,
    rows: Sequence[tuple[float, float, float, float]],
    *,
    atr: float | None = _ATR,
    start: int = 2,
) -> list[list[EmittedEvent]]:
    """تغذية صفوف (O, H, L, C) من الدليل ``start`` وجمع أحداث كل شريط."""
    per_bar: list[list[EmittedEvent]] = []
    for offset, (o, h, low, c) in enumerate(rows):
        index = start + offset
        per_bar.append(engine.update(candle(index, o, h, low, c), vol(atr)))
    return per_bar


# ═══════════ §38.1: ثابت الاجتياح التام (BUY_SIDE) ═══════════


class TestExactSweepFixture:
    """اقتراب ← اختراق بالعتبة ← استرجاع داخل النافذة ⇒ LIQUIDITY_SWEEP_HIGH."""

    ROWS = (
        (99.5, 100.0, 99.0, 100.0),  # 2: الاقتراب — لمس المستوى وإغلاق عليه
        (100.0, 101.4, 99.9, 101.0),  # 3: الاختراق — تجاوز 1.4 ≥ 0.5 وإغلاق وراءه
        (100.5, 100.6, 98.8, 99.0),  # 4: الاسترجاع — إغلاق دون الحافة القريبة
    )

    def test_exact_sweep_fixture_buy_side(self) -> None:
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(engine, self.ROWS)
        assert per_bar[:2] == [[], []]
        events = per_bar[2]
        assert len(events) == 1
        event = events[0]
        assert event.event_type is EventType.LIQUIDITY_SWEEP_HIGH
        assert event.event_time == minutes(4)  # شمعة الحسم (شرط 5)
        payload = event.payload
        assert isinstance(payload, SweepEventPayload)
        assert payload.bar_time == minutes(4)
        assert payload.zone_id == zone_id  # الربط الإلزامي
        assert payload.zone_side is LiquiditySide.BUY_SIDE
        assert payload.classification is SweepClassification.CONFIRMED_SWEEP
        assert payload.excursion_atr == pytest.approx(1.4 / _ATR)  # 0.7
        assert payload.penetration_reached is True  # الشرط 3 موثقًا في الحمولة
        assert payload.reclaim_bars == 2  # من أول تغلغل (الاقتراب) حتى الاسترجاع
        assert payload.test_count_at_event == 1  # حلقة التفاعل الحالية وحدها
        assert payload.instrument == INSTRUMENT
        assert payload.timeframe == TIMEFRAME

    def test_exact_sweep_finalizes_zone_state_and_scores(self) -> None:
        engine, zone_id = _engine_with_zone()
        _feed(engine, self.ROWS)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.SWEPT  # ACTIVE → SWEPT
        assert zone.sweep_status is SweepClassification.CONFIRMED_SWEEP
        assert zone.test_count == 1
        assert zone.last_test_time == minutes(2)  # حصيلة حلقة التفاعل
        # رفض الاسترجاع سُجل: عمق (100 - 99.0)/2 = 0.5 ATR
        assert zone.reaction_score == pytest.approx(math.tanh(0.5))
        assert zone.unmitigated_score == 0.0  # تجاوز صريح لمستوى صفري العرض
        assert zone.importance_score == 0.0  # المستهلَكة تُصفَّر

    def test_swept_zone_never_retested(self) -> None:
        engine, zone_id = _engine_with_zone()
        _feed(engine, self.ROWS)
        _feed(engine, [(99.5, 100.2, 99.2, 99.6)], start=5)  # لمس جديدة بعد الموت
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 1  # الميتة ليست هدفًا للتفاعل
        assert zone.state is ZoneState.SWEPT


# ═══════════ §38.1: ثابت الاجتياح الفاشل القارب (near-miss) ═══════════


class TestNearMissSweepFixture:
    """تغلغل دون العتبة ثم مغادرة جهة القرب ⇒ FAILED_SWEEP بلا بث البتة."""

    ROWS = (
        (99.5, 100.0, 99.0, 100.0),  # 2: الاقتراب
        (100.0, 100.4, 99.5, 99.6),  # 3: تجاوز 0.4 < 0.5 ثم إغلاق دون المستوى
    )

    def test_near_miss_sweep_fixture(self) -> None:
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(engine, self.ROWS)
        assert per_bar == [[], []]  # لا حدث ولا شمعة مؤهلة
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.ACTIVE  # الفشل لا يُنهي المنطقة
        assert zone.sweep_status is SweepClassification.FAILED_SWEEP
        assert zone.test_count == 1  # الاختبار حُصِّل مع بدء التفاعل
        # رفض المغادرة سُجل أيضًا: عمق (100 - 99.6)/2 = 0.2 ATR
        assert zone.reaction_score == pytest.approx(math.tanh(0.2))
        assert zone.unmitigated_score == 0.0  # تجاوز 100.4 واضح خلف المستوى


# ═══════════ §10.4: الكسر بالقبول (BREAK_AND_ACCEPT) ═══════════


class TestBreakAndAcceptFixture:
    """إغلاقات قبول كافية وراء الحافة البعيدة ⇒ BREAK_AND_ACCEPT_HIGH."""

    ROWS = (
        (99.5, 100.0, 99.0, 100.0),  # 2: الاقتراب — نافذة التقييم تفتح هنا
        (100.0, 101.4, 99.9, 100.8),  # 3: اختراق بالعتبة + إغلاق مؤهل (1)
        (100.8, 101.0, 100.2, 100.9),  # 4: إغلاق مؤهل (2) ⇒ القبول
    )

    def test_break_and_accept_fixture(self) -> None:
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(engine, self.ROWS)
        assert per_bar[:2] == [[], []]
        events = per_bar[2]
        assert len(events) == 1
        event = events[0]
        assert event.event_type is EventType.BREAK_AND_ACCEPT_HIGH
        assert event.event_time == minutes(4)
        payload = event.payload
        assert isinstance(payload, BreakAcceptEventPayload)
        assert payload.zone_id == zone_id
        assert payload.bar_time == minutes(4)
        assert payload.excursion_atr == pytest.approx(1.4 / _ATR)
        assert payload.acceptance_ratio == pytest.approx(2.0 / 3.0)  # مؤهلة ÷ نافذة
        assert payload.window_bars == 3
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.CONSUMED  # ACTIVE → CONSUMED
        assert zone.sweep_status is SweepClassification.BREAK_AND_ACCEPT

    def test_acceptance_short_of_minimum_is_not_accept(self) -> None:
        """إغلاق مؤهل وحيد داخل النافذة دون بلوغ accept_min_closes لا يقبل."""
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.0, 99.0, 100.0),
                (100.0, 101.4, 99.9, 100.8),  # مؤهل 1
                (100.8, 101.0, 99.9, 100.0),  # إغلاق على المستوى — غير مؤهل
            ],
        )
        assert per_bar == [[], [], []]  # انقضت النافذة (3 شموع) بلا حسم
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.ACTIVE
        assert zone.sweep_status is SweepClassification.PARTIAL_SWEEP


# ═══════════ §10.4: الجزئي والمجهول — تصنيفات بلا بث ═══════════


class TestPartialAndUnknown:
    """انقضاء النافذة بلا حسم: داخل المنطقة PARTIAL وخلف الحافة UNKNOWN."""

    def test_partial_sweep_fixture(self) -> None:
        """اختراق بالعتبة ثم إغلاقات مترددة داخل النطاق حتى الانقضاء."""
        engine, cluster_id = _engine_with_cluster()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.3, 99.2, 100.1),  # 3: اقتراب داخل النطاق بلا اختراق
                (100.1, 101.1, 100.0, 100.2),  # 4: تجاوز 0.7 ≥ 0.5 — النافذة تفتح
                (100.2, 100.9, 100.1, 100.3),  # 5: إغلاق متردد داخل النطاق
                (100.3, 100.6, 100.05, 100.15),  # 6: الثالثة — انقضاء النافذة
            ],
            start=3,
        )
        assert per_bar == [[], [], [], []]
        zone = engine.zone(cluster_id)
        assert zone is not None
        assert zone.sweep_status is SweepClassification.PARTIAL_SWEEP
        assert zone.state is ZoneState.ACTIVE  # تبقى بحصيلة اختبارها
        assert zone.test_count == 1

    def test_unknown_fixture(self) -> None:
        """إغلاق وراء الحافة البعيدة بقبول ناقص عند الانقضاء ⇒ UNKNOWN."""
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.0, 99.0, 100.0),  # 2: الاقتراب
                (100.0, 100.4, 99.9, 100.0),  # 3: تجاوز 0.4 دون العتبة
                (100.0, 100.45, 99.95, 100.3),  # 4: إغلاق وراء الحافة (غير كافٍ)
            ],
        )
        assert per_bar == [[], [], []]
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.sweep_status is SweepClassification.UNKNOWN
        assert zone.state is ZoneState.ACTIVE
        assert zone.test_count == 1


# ═══════════ §10.4: التناظر السعري (SELL_SIDE → *_LOW) ═══════════


class TestSellSideSymmetry:
    """منطقة القاع تُجتاح هبوطًا وتبث LIQUIDITY_SWEEP_LOW — الحساب واحد."""

    def test_exact_sweep_fixture_sell_side_low(self) -> None:
        engine, zone_id = _engine_with_zone(direction=SwingDirection.LOW)
        per_bar = _feed(
            engine,
            [
                (100.5, 100.8, 100.0, 100.0),  # 2: الاقتراب — لمس القاع وإغلاق عليه
                (99.8, 100.1, 98.6, 99.0),  # 3: اختراق 1.4 ≥ 0.5 هبوطًا + إغلاق دونه
                (100.0, 101.2, 99.5, 101.0),  # 4: الاسترجاع — إغلاق فوق الحافة القريبة
            ],
        )
        assert per_bar[:2] == [[], []]
        events = per_bar[2]
        assert len(events) == 1
        event = events[0]
        assert event.event_type is EventType.LIQUIDITY_SWEEP_LOW
        payload = event.payload
        assert isinstance(payload, SweepEventPayload)
        assert payload.zone_side is LiquiditySide.SELL_SIDE
        assert payload.excursion_atr == pytest.approx(1.4 / _ATR)
        assert payload.reclaim_bars == 2
        assert payload.test_count_at_event == 1
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.SWEPT
        # عمق الرفض السعري: (101.0 - 100.0)/2 = 0.5 ATR
        assert zone.reaction_score == pytest.approx(math.tanh(0.5))

    def test_break_and_accept_fixture_sell_side_low(self) -> None:
        engine, zone_id = _engine_with_zone(direction=SwingDirection.LOW)
        per_bar = _feed(
            engine,
            [
                (100.5, 100.8, 100.0, 100.0),
                (99.8, 100.1, 98.6, 99.2),  # مؤهل 1
                (99.2, 99.9, 99.0, 99.4),  # مؤهل 2 ⇒ القبول
            ],
        )
        events = per_bar[2]
        assert len(events) == 1
        assert events[0].event_type is EventType.BREAK_AND_ACCEPT_LOW
        payload = events[0].payload
        assert isinstance(payload, BreakAcceptEventPayload)
        assert payload.acceptance_ratio == pytest.approx(2.0 / 3.0)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.CONSUMED


# ═══════════ §10.4: اجتياح المستوى الصفري بفتيل شمعة واحدة ═══════════


class TestOneCandleWickSweep:
    """لمس واختراق واسترجاع في شمعة واحدة ⇒ reclaim_bars = 0 (فتيل واحد)."""

    def test_zero_width_prior_sweep_in_single_candle(self) -> None:
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(engine, [(99.5, 101.4, 99.2, 99.6)])
        events = per_bar[0]
        assert len(events) == 1
        event = events[0]
        assert event.event_type is EventType.LIQUIDITY_SWEEP_HIGH
        payload = event.payload
        assert isinstance(payload, SweepEventPayload)
        assert payload.reclaim_bars == 0  # «صفر = اجتياح بفتيل شمعة واحدة»
        assert payload.excursion_atr == pytest.approx(1.4 / _ATR)
        assert payload.test_count_at_event == 1
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.SWEPT


# ═══════════ §10.4 شرط 3: صيغة العتبة المطلوبة الموثقة ═══════════


class TestRequiredExcursionFormula:
    """‏required = max(atr×SWEEP_TOLERANCE, عرض×width_fraction) — الفرعان معًا."""

    @staticmethod
    def _wide_cluster_engine() -> tuple[LiquidityEngine, str]:
        """عنقود متسلسل بالمدى [100.0, 102.2] — عرض 2.2 يحكم العتبة (1.1)."""
        engine = LiquidityEngine()
        assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR)) == []
        chain = [100.0, 100.4, 100.9, 101.3, 101.8, 102.2]
        for index, price in enumerate(chain, start=1):
            assert (
                engine.update(
                    candle(index, 99.0, 99.8, 98.5, 99.2),  # دون العنقود — لا لمس
                    vol(_ATR),
                    [swing(f"w{index}", price, SwingDirection.HIGH, bar_time=minutes(index))],
                )
                == []
            )
        members = ",".join(f"w{i}" for i in range(1, 7))
        cluster_id = zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|{members}")
        return engine, cluster_id

    def test_width_branch_demands_proportional_excursion(self) -> None:
        """تجاوز 0.8 يكفي منطقة صفرية العرض (0.5) ولا يكفي العريضة (1.1)."""
        wide_engine, wide_id = self._wide_cluster_engine()
        per_bar = _feed(
            wide_engine,
            [
                (101.0, 102.0, 100.5, 101.5),  # 7: اقتراب داخل النطاق
                (101.5, 103.0, 101.2, 102.6),  # 8: تجاوز 0.8 < 1.1 + إغلاق مؤهل
                (102.0, 102.3, 99.5, 99.6),  # 9: مغادرة جهة القرب دون العتبة
            ],
            start=7,
        )
        assert per_bar == [[], [], []]  # العرض يحكم ⇒ لا بث
        wide_zone = wide_engine.zone(wide_id)
        assert wide_zone is not None
        assert wide_zone.sweep_status is SweepClassification.FAILED_SWEEP
        assert wide_zone.state is ZoneState.ACTIVE
        narrow_engine, narrow_id = _engine_with_zone()
        per_bar_narrow = _feed(
            narrow_engine,
            [
                (99.5, 100.0, 99.0, 100.0),  # 2: اقتراب
                (100.0, 100.8, 99.8, 100.0),  # 3: التجاوز نفسه 0.8 ≥ 0.5
                (99.9, 100.1, 99.2, 99.5),  # 4: استرجاع
            ],
        )
        events = per_bar_narrow[2]
        assert len(events) == 1
        assert events[0].event_type is EventType.LIQUIDITY_SWEEP_HIGH
        payload = events[0].payload
        assert isinstance(payload, SweepEventPayload)
        assert payload.excursion_atr == pytest.approx(0.8 / _ATR)
        assert narrow_id == payload.zone_id


# ═══════════ §10.4: الشروط الخمسة — كل شرط ضروري مستقلًا ═══════════


class TestFiveConditionsNecessary:
    """إسقاط أي شرط من الخمسة ⇒ لا بث — مختبرًا شرطًا شرطًا."""

    def test_condition1_no_preexisting_zone(self) -> None:
        """بلا منطقة قائمة لا اجتياح — الحركة نفسها فوق الفراغ لا تبث."""
        engine = LiquidityEngine()
        per_bar = _feed(
            engine,
            [
                (99.0, 105.0, 95.0, 100.0),  # 0: التأسيس الواسع
                (100.0, 101.4, 99.9, 101.0),  # 1: اختراق فوق فراغ
                (100.5, 100.6, 98.8, 99.0),  # 2: استرجاع
            ],
            start=0,
        )
        assert per_bar == [[], [], []]

    def test_condition2_no_through_trade_beyond_far_edge(self) -> None:
        """لمس دون اختراق الحافة البعيدة ثم مغادرة ⇒ فشل لا اجتياح."""
        engine, cluster_id = _engine_with_cluster()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.3, 99.2, 100.1),  # 3: اقتراب داخل النطاق
                (100.1, 100.35, 99.0, 99.2),  # 4: مغادرة دون اختراق 100.4
            ],
            start=3,
        )
        assert per_bar == [[], []]
        zone = engine.zone(cluster_id)
        assert zone is not None
        assert zone.sweep_status is SweepClassification.FAILED_SWEEP
        assert zone.state is ZoneState.ACTIVE

    def test_condition3_insufficient_excursion(self) -> None:
        """التجاوز دون العتبة لا يكتمل به الشرط 3 — والعتبة ذاتها كافية فوقها."""
        engine, zone_id = _engine_with_zone()
        under = _feed(engine, [(99.5, 100.0, 99.0, 100.0), (100.0, 100.4, 99.5, 99.6)])
        assert under == [[], []]  # تجاوز 0.4 دون 0.5
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.sweep_status is SweepClassification.FAILED_SWEEP
        engine2, zone2_id = _engine_with_zone()
        over = _feed(engine2, [(99.5, 100.0, 99.0, 100.0), (100.0, 100.6, 99.5, 99.6)])
        assert len(over[1]) == 1  # تجاوز 0.6 ≥ 0.5 ⇒ الشرط اكتمل والبث وقع
        assert over[1][0].event_type is EventType.LIQUIDITY_SWEEP_HIGH
        assert zone2_id == over[1][0].payload.zone_id

    def test_condition4_no_reclaim_or_accept_response(self) -> None:
        """الشرط 4: لا استرجاع ولا قبول كافٍ داخل النافذة ⇒ لا بث."""
        engine, cluster_id = _engine_with_cluster()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.3, 99.2, 100.1),  # 3: اقتراب
                (100.1, 101.1, 100.0, 100.2),  # 4: اختراق بالعتبة — النافذة تفتح
                (100.2, 100.9, 100.1, 100.3),  # 5: لا استجابة
                (100.3, 100.6, 100.05, 100.15),  # 6: لا استجابة — انقضاء
            ],
            start=3,
        )
        assert per_bar == [[], [], [], []]
        zone = engine.zone(cluster_id)
        assert zone is not None
        assert zone.sweep_status is SweepClassification.PARTIAL_SWEEP

    def test_condition5_payload_completeness_and_linkage(self) -> None:
        """كل بث موقوت بشمعة الحسم ومربوط بمنطقته — الحمولات معتمدة جاهزة."""
        collected: list[tuple[int, EmittedEvent]] = []
        runs = (
            (_engine_with_zone(), 2),
            (_engine_with_zone(direction=SwingDirection.LOW), 2),
            (_engine_with_cluster(), 3),  # عنقود استهلك الشرائط 0..2 ببرولوجه
        )
        for (engine, _zone_id), start in runs:
            rows = [
                (99.5, 100.0, 99.0, 100.0),
                (100.0, 101.4, 99.9, 101.0),
                (100.5, 100.6, 98.8, 99.0),
            ]
            for offset, row in enumerate(rows):
                index = start + offset
                for event in engine.update(candle(index, *row), vol(_ATR)):
                    collected.append((index, event))
        assert collected  # أحداث فعلية فُحصت
        known_types = {
            EventType.LIQUIDITY_SWEEP_HIGH,
            EventType.LIQUIDITY_SWEEP_LOW,
            EventType.BREAK_AND_ACCEPT_HIGH,
            EventType.BREAK_AND_ACCEPT_LOW,
        }
        for index, event in collected:
            assert event.event_type in known_types  # قاموس §20 السيولي حصرًا
            assert event.event_time == minutes(index)  # لا بث قبل إقفال شمعة الحسم
            payload = event.payload
            assert isinstance(payload, SweepEventPayload | BreakAcceptEventPayload)
            assert payload.bar_time == event.event_time  # شرط 5: توثيق موحد
            assert payload.zone_id  # الربط الإلزامي بمنطقة مستهلَكة
            assert payload.instrument == INSTRUMENT
            assert payload.timeframe == TIMEFRAME


# ═══════════ قواعد آلة التفاعل ═══════════


class TestInteractionRules:
    """تقييم واحد في كل مرة، وحصيلة اختبار لكل حلقة، والموت يطوي المعلق."""

    def test_one_evaluation_at_a_time_per_zone(self) -> None:
        """المنطقة في تفاعل لا تبدأ ثانيًا — الاختبار يُحصى مرة لكل حلقة."""
        engine, zone_id = _engine_with_zone()
        _feed(
            engine,
            [
                (99.5, 100.0, 99.0, 100.0),  # 2: الحلقة الأولى تبدأ (نافذة تفتح)
                (100.0, 100.2, 99.5, 100.0),  # 3: لمس جديد والحلقة قائمة
                (100.0, 100.3, 99.8, 100.0),  # 4: الثالثة — انقضاء بلا حسم
            ],
        )
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 1  # لمسة الشريطين 3 و4 داخل الحلقة نفسها
        assert zone.sweep_status is SweepClassification.PARTIAL_SWEEP
        _feed(engine, [(99.5, 100.1, 99.3, 99.8)], start=5)  # 5: لمسة جديدة بعد الطي
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 2  # حلقة جديدة ⇒ حصيلة جديدة

    def test_founding_candle_never_sweeps_its_own_zone(self) -> None:
        """شرط 1 عبر الواجهة: شمعة التأسيس تخترق وتسترجع ولا تبث شيئًا."""
        engine = LiquidityEngine()
        assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR)) == []
        founding = engine.update(
            candle(1, 99.5, 101.4, 99.2, 99.6),  # فتيل اجتياح كامل
            vol(_ATR),
            [swing("s1", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        assert founding == []  # الكاشف سبق تأسيس المنطقة
        events = engine.update(candle(2, 99.6, 101.0, 99.0, 99.4), vol(_ATR))
        assert len(events) == 1  # الشمعة التالية تجتاحها فعلًا
        assert events[0].event_type is EventType.LIQUIDITY_SWEEP_HIGH
        payload = events[0].payload
        assert isinstance(payload, SweepEventPayload)
        assert payload.reclaim_bars == 0

    def test_zone_death_folds_pending_interaction(self) -> None:
        """موت المنطقة (إحلال دمج المتساويات) يطوي تفاعلها بلا حسم."""
        engine, _ = _engine_with_zone()
        _feed(engine, [(99.5, 100.0, 99.0, 100.0)])  # 2: حلقة مفتوحة على s1
        # الشريط 3: الكاشف يقيّم قبل الخريطة (الحلقة قائمة) ثم الدمج يُميت s1
        events = engine.update(
            candle(3, 100.0, 100.2, 99.8, 100.0),
            vol(_ATR),
            [swing("B", 100.3, SwingDirection.HIGH, bar_time=minutes(3))],
        )
        assert events == []
        # الشريط 4: الاسترجاع يقع على منطقة ميتة — لا حدث ولا تصنيف متأخر
        after = engine.update(candle(4, 100.0, 100.1, 98.9, 99.0), vol(_ATR))
        assert after == []
        s1 = engine.zone(zone_uuid(_prior_key("s1")))
        assert s1 is not None
        assert s1.state is ZoneState.INVALIDATED  # إحلال الدمج (جدول (ب))
        assert s1.sweep_status is SweepClassification.UNKNOWN  # لم يُحسم قط
        assert s1.test_count == 1  # حلقة الشريط 2 حُصِّلت قبل الموت
        cluster = engine.zone(zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|B,s1"))
        assert cluster is not None
        assert cluster.state is ZoneState.ACTIVE
        assert cluster.test_count == 1  # حلقة جديدة على العنقود باللمسة الأخيرة
        assert cluster.sweep_status is SweepClassification.FAILED_SWEEP  # طويت بالمغادرة

    def test_decisive_traversal_invalidates_untouched_zone(self) -> None:
        """عبور قافز بهامش بنوي: مدى الشمعة كله وراء الحافة وإغلاق بهامش."""
        engine, zone_id = _engine_with_zone()
        events = _feed(engine, [(101.0, 101.5, 100.2, 101.3)])[0]
        assert events == []  # عبور بلا تسلسل — لا بث (§20)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.INVALIDATED
        assert zone.test_count == 0  # لم تُلمس قط

    def test_decisive_traversal_buffer_boundary(self) -> None:
        """هامش STRUCTURAL_LEVEL_BUFFER (atr×0.5): الحد مغلق والناقص لا يبطل."""
        engine, zone_id = _engine_with_zone()
        _feed(engine, [(101.0, 101.5, 100.2, 101.0)])  # close−high = 1.0 == الهامش
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.INVALIDATED  # >= حواف مغلقة
        engine2, zone2_id = _engine_with_zone()
        _feed(engine2, [(101.0, 101.5, 100.2, 100.9)])  # 0.9 دون الهامش
        zone2 = engine2.zone(zone2_id)
        assert zone2 is not None
        assert zone2.state is ZoneState.ACTIVE  # لا لمس ولا إبطال — صمت كامل

    def test_decisive_traversal_requires_scale(self) -> None:
        """قبل توفر ATR لا عبور قافزًا — العتبة التطبيعية شرط الإبطال أيضًا."""
        engine, zone_id = _engine_with_zone(atr=None)
        _feed(engine, [(101.0, 103.0, 100.2, 102.5)], atr=None)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.ACTIVE

    def test_touched_zone_takes_interaction_precedence(self) -> None:
        """المنطقة الملموسة تحسم بالنافذة لا بالعبور القافز — التفاعل أسبق."""
        engine, zone_id = _engine_with_zone()
        per_bar = _feed(
            engine,
            [
                (99.5, 100.0, 99.0, 100.0),  # 2: الحلقة تبدأ باللمس
                (100.5, 101.4, 100.2, 100.8),  # 3: مدى الشمعة وراء الحافة كلها
                (100.8, 101.2, 100.5, 101.0),  # 4: إغلاق مؤهل ثانٍ ⇒ قبول
            ],
        )
        assert [len(bar) for bar in per_bar] == [0, 0, 1]
        assert per_bar[2][0].event_type is EventType.BREAK_AND_ACCEPT_HIGH
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.CONSUMED  # لا INVALIDATED قط

    def test_multiple_zones_interact_in_creation_order(self) -> None:
        """منطقتان على الجانب نفسه تتفاعلان بشمعة واحدة بترتيب إنشائهما."""
        engine = LiquidityEngine()
        assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR)) == []
        assert (
            engine.update(
                candle(1, 99.0, 99.8, 98.5, 99.0),
                vol(_ATR),
                [swing("z1", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
            )
            == []
        )
        assert (
            engine.update(
                candle(2, 99.0, 99.8, 98.5, 99.0),
                vol(_ATR),
                [swing("z2", 101.6, SwingDirection.HIGH, bar_time=minutes(2))],
            )
            == []
        )
        events = engine.update(candle(3, 100.0, 102.4, 98.8, 99.0), vol(_ATR))
        assert len(events) == 2  # كلاهما اجتِيح بفتيل الشمعة نفسها
        assert events[0].payload.zone_id == zone_uuid(_prior_key("z1"))  # الأقدم أولًا
        assert events[1].payload.zone_id == zone_uuid(_prior_key("z2"))
        first, second = events
        assert isinstance(first.payload, SweepEventPayload)
        assert isinstance(second.payload, SweepEventPayload)
        assert first.payload.excursion_atr == pytest.approx(2.4 / _ATR)
        assert second.payload.excursion_atr == pytest.approx(0.8 / _ATR)

    def test_no_atr_counts_tests_and_tracks_penetration_only(self) -> None:
        """قبل توفر المقياس: اختبارات وتغلغل بلا نوافذ ولا تصنيف ولا بث."""
        engine, zone_id = _engine_with_zone(atr=None)
        per_bar = _feed(
            engine,
            [
                (99.5, 100.0, 99.0, 99.5),  # 2: لمس وإغلاق دون المستوى — طي بلا تصنيف
                (99.5, 100.5, 99.3, 100.2),  # 3: لمس جديد وتجاوز سعري متابَع
                (100.0, 100.4, 99.0, 99.0),  # 4: مغادرة — طي ثانٍ بلا تصنيف
            ],
            atr=None,
        )
        assert per_bar == [[], [], []]
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.ACTIVE
        assert zone.test_count == 2  # حلقتان حُصِّلتا
        assert zone.sweep_status is SweepClassification.UNKNOWN  # لم تُصنف قط
        assert zone.unmitigated_score == 0.0  # تجاوز 100.5 خلف المستوى الصفري


# ═══════════ الإعداد وخرج الكاشف ═══════════


class TestSweepConfigAndOutput:
    """تحقق الإعداد الصاخب وجمود خرج الكاشف (حمولات معتمدة جاهزة لـ3-f)."""

    def test_config_validation(self) -> None:
        with pytest.raises(ValueError, match="eval_window"):
            SweepConfig(eval_window=0)
        with pytest.raises(ValueError, match="accept_min_closes"):
            SweepConfig(accept_min_closes=0)
        with pytest.raises(ValueError, match="width_fraction"):
            SweepConfig(width_fraction=0.0)
        config = SweepConfig()
        assert (config.eval_window, config.accept_min_closes, config.width_fraction) == (3, 2, 0.5)

    def test_emitted_event_is_frozen(self) -> None:
        engine, _ = _engine_with_zone()
        events = _feed(engine, [(99.5, 101.4, 99.2, 99.6)])[0]
        assert len(events) == 1
        with pytest.raises(FrozenInstanceError):
            events[0].event_type = EventType.LIQUIDITY_SWEEP_LOW  # type: ignore[misc]
