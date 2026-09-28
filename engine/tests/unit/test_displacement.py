"""اختبارات كاشف الإزاحة — بوابة المهمة 3-b الحرفية (§11.4).

منهاج §38.1 الإلزامي بالاسم: «true displacement» و«weak expansion» —
وبوابات §11.4 الست كل بوابة مستقلة (اختبار كل شرط على حدة)، والحمولة
بصيغ الموديول محسوبة يدويًا، وقاعدة التكرار الموثقة («بث لكل شمعة
مستوفية») مقفلة بتركض متتالٍ كامل.

هندسة المصغّرات: الخلفية أربع شموع هادئة بمدى 1.0 بالضبط (متناوبة
الاتجاه فلا يمتد الاندفاع) وحالة تقلب حقنها يدويًا — ``expansion=0.5``
دون العتبة فتُسكَت، وشمعة الاندفاع مداها 5.0 وحالتها ``expansion=0.95``
فتمر مئيني التوسع؛ نوافذ الإحصاء مصغّرة (``zscore_window=5``) ليكتمل
z-score على خمس شموع — القيم العشرية للقيم المختارة تجعل النسب قابلة
للحساب اليدوي بالضبط.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import timedelta

import pytest
from _structure_fixtures import BASE_TIME, INSTRUMENT, TIMEFRAME, make_candle, make_vol_state
from market_state.volatility import VolatilityState
from schemas import BreakDirection, DisplacementEventPayload, EventType
from structure import DisplacementConfig, DisplacementDetector
from structure.events import EmittedEvent

# ═══════════ المصغّرات ═══════════

#: إعداد الاختبارات: نافذة z-score خماسية (البوابات الأخرى بافتراضياتها).
_CFG = DisplacementConfig(zscore_window=5)

_QUIET_UP = (100.0, 100.5, 99.5, 100.25)  # مدى 1.0 صاعد
_QUIET_DOWN = (100.25, 100.75, 99.75, 100.0)  # مدى 1.0 هابط

#: خلفية قياسية: أربع هادئة متناوبة — الاندفاع الصاعد لا يمتد (سابقه هابط).
_BACKGROUND_UP = [_QUIET_UP, _QUIET_DOWN, _QUIET_UP, _QUIET_DOWN]

#: الخلفية قبل اندفاع هابط: سابقه صاعدة فلا يمتد الركض.
_BACKGROUND_DOWN = [_QUIET_UP, _QUIET_DOWN, _QUIET_UP, _QUIET_UP]

#: شمعة الإزاحة الحقيقية (§38.1): مدى 5.0 اتجاهية، جسم 0.9، إغلاق عند التطرف.
_IMPULSE_UP = (100.0, 105.0, 100.0, 104.5)
_IMPULSE_DOWN = (104.5, 105.0, 100.0, 100.5)


def _feed(
    detector: DisplacementDetector, rows: Sequence[tuple[float, float, float, float]]
) -> list[list[EmittedEvent]]:
    """تغذية الصفوف بحالات تقلب هادئة (expansion=0.5 دون العتبة)."""
    out: list[list[EmittedEvent]] = []
    for i, row in enumerate(rows):
        out.append(detector.update(make_candle(i, *row), make_vol_state(1.0, expansion=0.5)))
    return out


def _feed_impulse(
    detector: DisplacementDetector,
    background: list[tuple[float, float, float, float]],
    impulse: tuple[float, float, float, float],
    *,
    vol: VolatilityState | None,
) -> list[EmittedEvent]:
    """خلفية هادئة ثم شمعة الحكم بحالتها — يعيد خرج شمعة الحكم وحدها."""
    _feed(detector, background)
    return detector.update(make_candle(len(background), *impulse), vol)


def _payload_of(events: list[EmittedEvent]) -> DisplacementEventPayload:
    """تضييق الاتحاد — حمولة الإزاحة DisplacementEventPayload حصرًا."""
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, DisplacementEventPayload)
    return payload


# ═══════════ §38.1 «true displacement» — الإزاحة الحقيقية ═══════════


class TestTrueDisplacement:
    """شمعة موسعة اتجاهية بإغلاق متطرف فوق المئين — الحمولة محسوبة يدويًا."""

    def test_true_displacement_up_payload_hand_computed(self) -> None:
        """§38.1: المدى 5.0 وسط نوافذ مدى 1.0 — كل قيمة بالصيغة الموثقة."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector, _BACKGROUND_UP, _IMPULSE_UP, vol=make_vol_state(1.0, expansion=0.95)
        )
        event = events[0]
        assert event.event_type is EventType.DISPLACEMENT_UP
        assert event.event_time == BASE_TIME + timedelta(minutes=4)
        payload = _payload_of(events)
        assert payload.instrument == INSTRUMENT
        assert payload.timeframe == TIMEFRAME
        assert payload.bar_time == BASE_TIME + timedelta(minutes=4)
        assert payload.direction is BreakDirection.UP
        # z-score المدى [1,1,1,1,5] على نافذته الشاملة: (5−1.8)/sqrt(3.2) = sqrt(3.2)
        assert payload.range_zscore == pytest.approx(3.2 / math.sqrt(3.2))
        assert payload.body_fraction == pytest.approx(4.5 / 5.0)  # |104.5−100|/5
        assert payload.close_location == pytest.approx(4.5 / 5.0)  # (104.5−100)/5
        assert payload.atr_multiple == pytest.approx(5.0 / 1.0)  # (high−low)/atr
        assert payload.velocity == pytest.approx(5.0)  # ركض أحادي الشمعة (سابقه هابط)
        assert payload.follow_through == 0.0  # صفر شموع منقضية (§26.3)

    def test_true_displacement_down_mirror(self) -> None:
        """المرآة الهابطة: الجسم 0.8 والإغلاق عند القاع (0.1 ≤ 1−0.8)."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector, _BACKGROUND_DOWN, _IMPULSE_DOWN, vol=make_vol_state(1.0, expansion=0.95)
        )
        assert events[0].event_type is EventType.DISPLACEMENT_DOWN
        payload = _payload_of(events)
        assert payload.direction is BreakDirection.DOWN
        assert payload.range_zscore == pytest.approx(3.2 / math.sqrt(3.2))
        assert payload.body_fraction == pytest.approx(4.0 / 5.0)  # |100.5−104.5|/5
        assert payload.close_location == pytest.approx(0.5 / 5.0)  # (100.5−100)/5
        assert payload.atr_multiple == pytest.approx(5.0)
        assert payload.velocity == pytest.approx(5.0)  # سابقه صاعدة — ركض أحادي


# ═══════════ §38.1 «weak expansion» — التوسع الضعيف ═══════════


class TestWeakExpansion:
    """فتيل طويل بجسم ضعيف وإغلاق وسطي، ومئيني دون العتبة — لا حدث أبدًا."""

    def test_long_wick_small_body_mid_close_no_event(self) -> None:
        """شمعة واسعة بلا كفاءة إغلاق: جسم 0.1 وإغلاق عند 0.1 — ليست إزاحة."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector,
            _BACKGROUND_UP,
            (100.0, 105.0, 100.0, 100.5),
            vol=make_vol_state(1.0, expansion=0.95),
        )
        assert events == []

    def test_low_percentile_no_event(self) -> None:
        """الشمعة قوية بذاتها لكن موقعها الإحصائي دون العتبة (0.5 < 0.90)."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector, _BACKGROUND_UP, _IMPULSE_UP, vol=make_vol_state(1.0, expansion=0.5)
        )
        assert events == []

    def test_percentile_none_warmup_no_event(self) -> None:
        """مئيني التوسع غائب (دافئ محرك التقلب) ⇒ بوابة مغلقة لا قيمة مزيفة."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector, _BACKGROUND_UP, _IMPULSE_UP, vol=make_vol_state(1.0, expansion=None)
        )
        assert events == []


# ═══════════ البوابات الست المستقلة — كل شرط لازم بذاته ═══════════


#: صفّا خلفية بمدى 0.5 (لاستيفاء مضاعف ATR عند حده بالضبط دون انحلال إحصائي).
_QUIET_HALF_UP = (100.0, 100.25, 99.75, 100.1)
_QUIET_HALF_DOWN = (100.1, 100.35, 99.85, 100.0)


def _gate_fixture(
    case: str,
) -> tuple[
    list[tuple[float, float, float, float]],
    tuple[float, float, float, float],
    VolatilityState | None,
]:
    """خلفية وشمعة حكم وحالة تقلب لكل حالة عزل — بوابة واحدة تفشل وحدها."""
    passing_vol = make_vol_state(1.0, expansion=0.95)
    if case == "direction_doji":  # البوابة 5: تساوٍ تام بلا اتجاه
        return _BACKGROUND_UP, (100.0, 105.0, 100.0, 100.0), passing_vol
    if case == "percentile_below_min":  # البوابة 1: 0.89 < 0.90
        return _BACKGROUND_UP, _IMPULSE_UP, make_vol_state(1.0, expansion=0.89)
    if case == "atr_none_warmup":  # البوابة 4: العتبة أصل الحكم
        return _BACKGROUND_UP, _IMPULSE_UP, make_vol_state(None, expansion=0.95)
    if case == "atr_zero_degenerate":  # البوابة 4: تقلب منحل — الرفض لا القسمة
        return _BACKGROUND_UP, _IMPULSE_UP, make_vol_state(0.0, expansion=0.95)
    if case == "atr_multiple_below_threshold":  # البوابة 4: 0.9/1.0 < 1.0
        return _BACKGROUND_UP, (100.0, 100.9, 100.0, 100.85), passing_vol
    if case == "body_below_min":  # البوابة 2: جسم 0.55 < 0.6 (الإغلاق 0.9 يجوز)
        return _BACKGROUND_UP, (101.75, 105.0, 100.0, 104.5), passing_vol
    if case == "close_location_below_min_up":  # البوابة 3 صاعدًا: 0.7 < 0.8
        return _BACKGROUND_UP, (100.0, 105.0, 100.0, 103.5), passing_vol
    if case == "close_location_above_max_down":  # البوابة 3 هابطًا: 0.227 > 1−0.8
        return _BACKGROUND_UP, (104.0, 104.4, 100.0, 101.0), passing_vol
    if case == "zscore_window_incomplete":  # البوابة 6: نافذة ناقصة ⇒ None
        return _BACKGROUND_UP[:3], _IMPULSE_UP, passing_vol
    if case == "zscore_flat_nan":  # البوابة 6: انحراف صفري ⇒ nan ⇒ None
        flat_up = (100.0, 101.0, 99.0, 100.4)  # مدى 2.0
        flat_down = (100.4, 101.4, 99.4, 100.0)  # مدى 2.0
        return (
            [flat_up, flat_down, flat_up, flat_down],
            (100.0, 102.0, 100.0, 101.8),  # مؤهلة كاملةً سوى الإحصاء المنحل
            passing_vol,
        )
    raise AssertionError(f"حالة عزل غير معروفة: {case}")


class TestIndependentGates:
    """كل بوابة من بوابات §11.4 الست شرط لازم — عزل فشل كل واحدة وحدها."""

    @pytest.mark.parametrize(
        "case",
        [
            "direction_doji",
            "percentile_below_min",
            "atr_none_warmup",
            "atr_zero_degenerate",
            "atr_multiple_below_threshold",
            "body_below_min",
            "close_location_below_min_up",
            "close_location_above_max_down",
            "zscore_window_incomplete",
            "zscore_flat_nan",
        ],
    )
    def test_single_failing_gate_blocks_the_event(self, case: str) -> None:
        background, impulse, vol = _gate_fixture(case)
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(detector, background, impulse, vol=vol)
        assert events == [], case


class TestInclusiveBoundaries:
    """المقارنات الموثقة مغلقة (≥): بلوغ الحد بالضبط يمر — لا عتبة صارمة."""

    def test_percentile_exactly_at_min_passes(self) -> None:
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector, _BACKGROUND_UP, _IMPULSE_UP, vol=make_vol_state(1.0, expansion=0.90)
        )
        assert _payload_of(events).range_zscore == pytest.approx(3.2 / math.sqrt(3.2))

    def test_atr_multiple_exactly_at_threshold_passes(self) -> None:
        """مدى 1.0 = atr×1.0 بالضبط (خلفية مداها 0.5 فلا انحلال إحصائي)."""
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector,
            [_QUIET_HALF_UP, _QUIET_HALF_DOWN] * 2,
            (100.0, 101.0, 100.0, 100.9),
            vol=make_vol_state(1.0, expansion=0.95),
        )
        assert _payload_of(events).atr_multiple == pytest.approx(1.0)

    def test_body_exactly_at_min_passes(self) -> None:
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector,
            _BACKGROUND_UP,
            (101.5, 105.0, 100.0, 104.5),
            vol=make_vol_state(1.0, expansion=0.95),
        )
        assert _payload_of(events).body_fraction == pytest.approx(0.6)

    def test_close_location_exactly_at_min_passes(self) -> None:
        detector = DisplacementDetector(_CFG)
        events = _feed_impulse(
            detector,
            _BACKGROUND_UP,
            (100.0, 105.0, 100.0, 104.0),
            vol=make_vol_state(1.0, expansion=0.95),
        )
        assert _payload_of(events).close_location == pytest.approx(0.8)


# ═══════════ قاعدة التكرار الموثقة: بث لكل شمعة مستوفية ═══════════


class TestEmitEveryQualifyingBar:
    """«بث لكل شمعة مستوفية» — كاشف خام لا يُسقط قياسًا، والسرعة تمدّ الركض."""

    ROWS = (
        *_BACKGROUND_UP,
        (100.0, 105.0, 100.0, 104.5),  # 4: الاندفاع الأول (سابقه هابط) — ركض 1
        (104.5, 109.5, 104.5, 109.0),  # 5: مواصلة صاعدة — ركض 2
        (109.0, 114.0, 109.0, 113.5),  # 6: مواصلة ثالثة — ركض 3 (سقف النافذة)
    )

    def _feed_run(self, config: DisplacementConfig) -> list[list[EmittedEvent]]:
        detector = DisplacementDetector(config)
        out: list[list[EmittedEvent]] = []
        for i, row in enumerate(self.ROWS):
            vol = make_vol_state(1.0, expansion=0.95) if i >= 4 else make_vol_state(1.0)
            out.append(detector.update(make_candle(i, *row), vol))
        return out

    def test_consecutive_qualifying_bars_each_emit(self) -> None:
        """ثلاث شموع متتالية مستوفية ⇒ ثلاثة أحداث — حدث واحد كأقصى في الشمعة."""
        per_bar = self._feed_run(_CFG)
        assert [len(events) for events in per_bar[4:]] == [1, 1, 1]
        flat = [event for events in per_bar for event in events]
        assert [e.event_type for e in flat] == [EventType.DISPLACEMENT_UP] * 3
        assert [e.event_time for e in flat] == [BASE_TIME + timedelta(minutes=i) for i in (4, 5, 6)]

    def test_velocity_extends_over_run_and_caps_at_window(self) -> None:
        """السرعة: مدى الركض ÷ شموعه — يمتد بالموالاة ويُقص عند velocity_window."""
        per_bar = self._feed_run(_CFG)
        first = _payload_of(per_bar[4])
        second = _payload_of(per_bar[5])
        third = _payload_of(per_bar[6])
        assert first.velocity == pytest.approx(5.0)  # (105−100)/1 — سابقه هابط
        assert second.velocity == pytest.approx((109.5 - 100.0) / 2)  # ركض شمعتين
        assert third.velocity == pytest.approx((114.0 - 100.0) / 3)  # قص النافذة (3)

    def test_velocity_window_one_counts_current_bar_only(self) -> None:
        """velocity_window=1: السرعة مدى الشمعة الحالية وحدها رغم مواصلة السابق."""
        per_bar = self._feed_run(DisplacementConfig(zscore_window=5, velocity_window=1))
        assert _payload_of(per_bar[4]).velocity == pytest.approx(5.0)
        assert _payload_of(per_bar[5]).velocity == pytest.approx(5.0)  # مداها 109.5−104.5

    def test_buffer_evicts_oldest_beyond_zscore_window(self) -> None:
        """المخزن بطول نافذة الإحصاء: bars_seen يتشبع ويزلق الأقدم."""
        detector = DisplacementDetector(_CFG)
        for i, row in enumerate(self.ROWS):
            detector.update(make_candle(i, *row), make_vol_state(1.0))
        assert detector.bars_seen == 5  # سبع شموع — المخزن خماسي


# ═══════════ الإعداد والحوارس ═══════════


class TestDisplacementConfig:
    """تحقق الإعداد الصاخب — لا إعداد نصف شرعي، والحدود الجائزة تُبنى."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"percentile_min": 0.0},
            {"percentile_min": 1.5},
            {"percentile_min": float("nan")},
            {"body_min": 0.0},
            {"body_min": 1.5},
            {"close_extreme_min": 0.5},
            {"close_extreme_min": 0.0},
            {"zscore_window": 1},
            {"velocity_window": 0},
        ],
        ids=[
            "pct-zero",
            "pct-above-one",
            "pct-nan",
            "body-zero",
            "body-above-one",
            "close-half",
            "close-below-half",
            "zwindow-one",
            "vwindow-zero",
        ],
    )
    def test_invalid_config_rejected(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            DisplacementConfig(**kwargs)  # type: ignore[arg-type]

    def test_closed_interval_bounds_construct(self) -> None:
        """الحدود الجائزة: (0,1] للكمّ والنسبة و(0.5,1] للتطرف — تُبنى فعلًا."""
        config = DisplacementConfig(
            percentile_min=1.0,
            body_min=1.0,
            close_extreme_min=1.0,
            zscore_window=2,
            velocity_window=1,
        )
        assert config.percentile_min == 1.0
        assert config.zscore_window == 2


class TestDisplacementGuards:
    """حوارس التدفق المشتركة (_guards) على كاشف الإزاحة — رفض صاخب."""

    def test_evolving_candle_rejected(self) -> None:
        detector = DisplacementDetector(_CFG)
        with pytest.raises(ValueError, match="المغلقة فقط"):
            detector.update(
                make_candle(0, 100.0, 101.0, 99.0, 100.5, is_closed=False),
                make_vol_state(1.0),
            )

    def test_duplicate_bar_time_rejected(self) -> None:
        detector = DisplacementDetector(_CFG)
        detector.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), make_vol_state(1.0))
        with pytest.raises(ValueError, match="تكرار bar_time"):
            detector.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), make_vol_state(1.0))

    def test_future_volatility_state_rejected(self) -> None:
        detector = DisplacementDetector(_CFG)
        detector.update(make_candle(0, 100.0, 101.0, 99.0, 100.5), make_vol_state(1.0))
        future = BASE_TIME + timedelta(minutes=3)
        with pytest.raises(ValueError, match="من المستقبل"):
            detector.update(
                make_candle(1, 100.0, 101.0, 99.0, 100.5),
                make_vol_state(1.0, bar_time=future),
            )
