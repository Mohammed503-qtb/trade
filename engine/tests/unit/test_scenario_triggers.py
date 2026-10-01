"""اختبارات المشغلات الخمسة (7.3) — آلات حالة شريطية بقيم محسوبة يدويًا.

كل مشغل بثوابت اختبار: اشتعال بشمعة محسوبة، ولا اشتعال بنقيضها المانع،
والحالة التشغيلية (عدادات/لمس) تتقدم حتميًا عبر الأشرطة.
"""

from __future__ import annotations

import pytest
from _scenario_fixtures import ATR, make_candle
from scenarios.triggers import (
    SUPPORTED_CONDITION_TYPES,
    StructureEventRef,
    TriggerRuntime,
    TriggerSpecError,
    advance,
)
from schemas import BreakDirection, EventType, TriggerDefinition

# ───────────────────────── DISPLACEMENT_CONFIRM ─────────────────────────


class TestDisplacementConfirm:
    """إزاحة إطار التنفيذ باتجاه السيناريو — من أحداث البنية المرصودة."""

    def test_fires_on_aligned_displacement(self) -> None:
        definition = TriggerDefinition(
            condition_type="DISPLACEMENT_CONFIRM",
            params={"direction": "LONG", "timeframe": "1m"},
        )
        refs = (StructureEventRef(EventType.DISPLACEMENT_UP, "1m", BreakDirection.UP),)
        assert advance(definition, TriggerRuntime(), candle=make_candle(1), structure_events=refs)

    def test_not_fires_on_opposed(self) -> None:
        definition = TriggerDefinition(
            condition_type="DISPLACEMENT_CONFIRM",
            params={"direction": "LONG", "timeframe": "1m"},
        )
        refs = (StructureEventRef(EventType.DISPLACEMENT_DOWN, "1m", BreakDirection.DOWN),)
        assert not advance(
            definition, TriggerRuntime(), candle=make_candle(1), structure_events=refs
        )

    def test_not_fires_on_foreign_timeframe(self) -> None:
        definition = TriggerDefinition(
            condition_type="DISPLACEMENT_CONFIRM",
            params={"direction": "SHORT", "timeframe": "1m"},
        )
        refs = (StructureEventRef(EventType.DISPLACEMENT_DOWN, "15m", BreakDirection.DOWN),)
        assert not advance(
            definition, TriggerRuntime(), candle=make_candle(1), structure_events=refs
        )


# ───────────────────────── INTERNAL_BOS ─────────────────────────


class TestInternalBos:
    """كسر بنية داخلية باتجاه السيناريو — مشغل الاستمرار §21.2."""

    def test_fires_on_aligned_internal_bos(self) -> None:
        definition = TriggerDefinition(
            condition_type="INTERNAL_BOS", params={"direction": "LONG", "timeframe": "1m"}
        )
        refs = (StructureEventRef(EventType.INTERNAL_BOS, "1m", BreakDirection.UP),)
        assert advance(definition, TriggerRuntime(), candle=make_candle(1), structure_events=refs)

    def test_external_bos_is_not_internal(self) -> None:
        definition = TriggerDefinition(
            condition_type="INTERNAL_BOS", params={"direction": "LONG", "timeframe": "1m"}
        )
        refs = (StructureEventRef(EventType.EXTERNAL_BOS, "1m", BreakDirection.UP),)
        assert not advance(
            definition, TriggerRuntime(), candle=make_candle(1), structure_events=refs
        )


# ───────────────────────── ACCEPTANCE_BEYOND ─────────────────────────


class TestAcceptanceBeyond:
    """قبول عدّ إغلاقات لا فتيل — نافذة متتالية تُصفَّر عند الكسر."""

    def test_three_consecutive_closes_fire(self) -> None:
        definition = TriggerDefinition(
            condition_type="ACCEPTANCE_BEYOND",
            params={"level": 59_600.0, "direction": "SHORT", "window": 3},
        )
        runtime = TriggerRuntime()
        below = make_candle(1, close=59_500.0, low=59_480.0, high=59_650.0, open_=59_600.0)
        assert not advance(definition, runtime, candle=below)  # 1
        assert not advance(definition, runtime, candle=below)  # 2
        assert advance(definition, runtime, candle=below)  # 3 — النافذة اكتملت

    def test_reset_on_breach_breaks_window(self) -> None:
        definition = TriggerDefinition(
            condition_type="ACCEPTANCE_BEYOND",
            params={"level": 59_600.0, "direction": "SHORT", "window": 2},
        )
        runtime = TriggerRuntime()
        below = make_candle(1, close=59_500.0, low=59_480.0, high=59_650.0, open_=59_600.0)
        above = make_candle(2, close=59_700.0, low=59_640.0, high=59_750.0, open_=59_680.0)
        assert not advance(definition, runtime, candle=below)  # عداد 1
        assert not advance(definition, runtime, candle=above)  # صُفِّر
        assert not advance(definition, runtime, candle=below)  # عداد 1 من جديد

    def test_long_side_level(self) -> None:
        definition = TriggerDefinition(
            condition_type="ACCEPTANCE_BEYOND",
            params={"level": 60_000.0, "direction": "LONG", "window": 1},
        )
        runtime = TriggerRuntime()
        up = make_candle(1, close=60_050.0, low=60_000.0, high=60_080.0, open_=60_010.0)
        assert advance(definition, runtime, candle=up)


# ───────────────────────── RETEST_HOLD ─────────────────────────


class TestRetestHold:
    """لمس نطاق الحافة ثم إغلاق صامد في جهة الاختراق — §21.2 «retest»."""

    def _definition(
        self, boundary: float = 59_800.0, direction: str = "SHORT"
    ) -> TriggerDefinition:
        return TriggerDefinition(
            condition_type="RETEST_HOLD",
            params={"boundary": boundary, "direction": direction, "band_atr": 0.25},
        )

    def test_touch_then_holding_close_fires(self) -> None:
        definition = self._definition()
        runtime = TriggerRuntime()
        # لمس بلا صمود: عودة إلى نطاق الحافة (band = 0.25×200 = 50 حول
        # 59_800) لكن الإغلاق فوق الحافة بعد — ليس صمودًا هابطًا بعد.
        touch = make_candle(1, open_=59_600.0, high=59_830.0, low=59_580.0, close=59_810.0)
        assert not advance(definition, runtime, candle=touch, atr=ATR)  # لمس فقط
        assert runtime.touched is True
        # إغلاق صامد دون الحافة (جهة الاختراق الهابط)
        holding = make_candle(2, open_=59_810.0, high=59_840.0, low=59_600.0, close=59_650.0)
        assert advance(definition, runtime, candle=holding, atr=ATR)

    def test_touch_and_hold_same_bar_fires(self) -> None:
        """لمس وصمود في الشمعة نفسها — إعادة اختبار مكتملة بشمعة واحدة."""
        definition = self._definition()
        runtime = TriggerRuntime()
        one_bar = make_candle(1, open_=59_600.0, high=59_830.0, low=59_580.0, close=59_620.0)
        assert advance(definition, runtime, candle=one_bar, atr=ATR)

    def test_no_touch_no_fire(self) -> None:
        definition = self._definition()
        runtime = TriggerRuntime()
        # بعيد عن النطاق كليًا وصامد — بلا لمس لا اشتعال
        far = make_candle(1, open_=59_500.0, high=59_550.0, low=59_450.0, close=59_500.0)
        assert not advance(definition, runtime, candle=far, atr=ATR)

    def test_no_atr_no_fire(self) -> None:
        """النطاق من بنية التقلب — بلا ATR لا لمس موثق (لا افتراض صامت)."""
        definition = self._definition()
        runtime = TriggerRuntime()
        touch = make_candle(1, open_=59_600.0, high=59_830.0, low=59_580.0, close=59_620.0)
        assert not advance(definition, runtime, candle=touch, atr=None)
        assert runtime.touched is False

    def test_close_back_above_boundary_does_not_fire_short(self) -> None:
        definition = self._definition()
        runtime = TriggerRuntime()
        touch = make_candle(1, open_=59_600.0, high=59_830.0, low=59_580.0, close=59_620.0)
        advance(definition, runtime, candle=touch, atr=ATR)
        # إغلاق فوق الحافة — ليس صمودًا في جهة الاختراق الهابط
        failing = make_candle(2, open_=59_620.0, high=59_900.0, low=59_600.0, close=59_870.0)
        assert not advance(definition, runtime, candle=failing, atr=ATR)


# ───────────────────────── ZONE_RECLAIM ─────────────────────────


class TestZoneReclaim:
    """إغلاق كامل خلف المستوى — فشل القبول حدث إغلاق لا فتيل."""

    def test_close_beyond_level_fires(self) -> None:
        definition = TriggerDefinition(
            condition_type="ZONE_RECLAIM", params={"level": 59_900.0, "direction": "LONG"}
        )
        reclaimed = make_candle(1, open_=59_850.0, high=59_950.0, low=59_820.0, close=59_930.0)
        assert advance(definition, TriggerRuntime(), candle=reclaimed)

    def test_wick_beyond_does_not_fire(self) -> None:
        definition = TriggerDefinition(
            condition_type="ZONE_RECLAIM", params={"level": 59_900.0, "direction": "LONG"}
        )
        wick_only = make_candle(1, open_=59_850.0, high=59_950.0, low=59_820.0, close=59_880.0)
        assert not advance(definition, TriggerRuntime(), candle=wick_only)


# ───────────────────────── الحرس ─────────────────────────


class TestTriggerSpecGuards:
    """التعريف الفاسد يُرفض صاخبًا — لا افتراضات صامتة."""

    def test_unknown_condition_type(self) -> None:
        definition = TriggerDefinition(
            condition_type="MAGIC_INTUITION", params={"direction": "LONG"}
        )
        with pytest.raises(TriggerSpecError, match="نوع مشغل غير مدعوم"):
            advance(definition, TriggerRuntime(), candle=make_candle(1))

    def test_missing_direction(self) -> None:
        definition = TriggerDefinition(condition_type="ZONE_RECLAIM", params={"level": 100.0})
        with pytest.raises(TriggerSpecError, match="بلا اتجاه قانوني"):
            advance(definition, TriggerRuntime(), candle=make_candle(1))

    def test_flat_direction_rejected(self) -> None:
        definition = TriggerDefinition(
            condition_type="ZONE_RECLAIM", params={"level": 100.0, "direction": "FLAT"}
        )
        with pytest.raises(TriggerSpecError, match="باتجاه غير اتجاهي"):
            advance(definition, TriggerRuntime(), candle=make_candle(1))

    def test_missing_numeric_param(self) -> None:
        definition = TriggerDefinition(condition_type="ZONE_RECLAIM", params={"direction": "LONG"})
        with pytest.raises(TriggerSpecError, match="بلا معامل 'level'"):
            advance(definition, TriggerRuntime(), candle=make_candle(1))

    def test_five_types_supported(self) -> None:
        assert (
            frozenset(
                {
                    "DISPLACEMENT_CONFIRM",
                    "INTERNAL_BOS",
                    "ACCEPTANCE_BEYOND",
                    "RETEST_HOLD",
                    "ZONE_RECLAIM",
                }
            )
            == SUPPORTED_CONDITION_TYPES
        )
