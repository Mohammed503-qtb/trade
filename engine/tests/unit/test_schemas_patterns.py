"""اختبارات حمولتا أحداث الأنماط — المرحلة 5-a (§13 + §20 + §32).

العقود المفحوصة:

- round-trip JSON كامل لكل نموذج (CandlePatternEventPayload و
  ClassicalPatternEventPayload وAnchorPoint)؛
- رفض القيم خارج حدودها (strength/quality خارج [0,1] وأسعار غير موجبة
  وbars_in_pattern صفري)؛
- الجمود (frozen) ومنع الحقول الغريبة (extra="forbid")؛
- عقد مفاتيح السمات الست حصرًا (§13.1): feature_readings تقبل
  CANDLE_FEATURE_KEYS فقط وترفض الخواء؛
- عقد زوج الفشل (§20 CLASSICAL_FAILED_BREAKOUT): reclaim_level
  وfailure_speed يحضران معًا أو يغيبان معًا؛
- عقد الأنكورات: 2..8 نقاط إرساء (§13.2) وrole غير فارغ؛
- التسجيل في EVENT_PAYLOAD_MODELS: أنواع الأنماط الستة الست تخدم
  حمولتيها (4 شموعية + 2 كلاسيكية) — الخريطة الآن 29 نوعًا.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from schemas import (
    CANDLE_FEATURE_KEYS,
    AnchorPoint,
    BreakDirection,
    CandlePatternEventPayload,
    CandlePatternFamily,
    ClassicalPatternEventPayload,
    ClassicalPatternType,
    PatternDirection,
    PatternStatus,
)
from schemas.enums import EventType
from schemas.envelope import EVENT_PAYLOAD_MODELS, payload_model_for


def _dt(minute: int = 0) -> datetime:
    return datetime(2026, 9, 29, 12, minute, tzinfo=UTC)


# ─── مصانع أمثلة صالحة ───


def make_anchor(minute: int, price: float, role: str) -> AnchorPoint:
    return AnchorPoint(time=_dt(minute), price=price, role=role)


def make_candle_pattern(**overrides: Any) -> CandlePatternEventPayload:
    """ابتلاع صاعد (BULLISH_ENGULFING) — جسم يبتلع جسم سابقه بإغلاق قوي."""
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(5),
        "family": CandlePatternFamily.ENGULFING,
        "direction": PatternDirection.BULLISH,
        "feature_readings": {
            "body_fraction": 0.82,
            "close_location": 0.95,
            "volume_relationship": 1.9,
        },
        "strength": 0.74,
        "bars_in_pattern": 2,
    }
    kwargs.update(overrides)
    return CandlePatternEventPayload(**kwargs)


def make_classical(**overrides: Any) -> ClassicalPatternEventPayload:
    """قمة مزدوجة كسرت رقبتها هبوطًا (CLASSICAL_BREAKOUT) — هندسة مؤكدة."""
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(40),
        "pattern_type": ClassicalPatternType.DOUBLE_TOP,
        "geometry": {"height_atr": 4.2, "width_bars": 55.0, "slope_per_bar": -0.001},
        "anchor_points": (
            make_anchor(1, 100.0, "P1_LEFT_PEAK"),
            make_anchor(20, 90.0, "P2_NECKLINE"),
            make_anchor(35, 100.4, "P3_RIGHT_PEAK"),
        ),
        "completion_time": _dt(40),
        "breakout_level": 90.0,
        "invalidation_level": 100.4,
        "measured_move": 79.6,
        "quality": 0.88,
        "break_direction": BreakDirection.DOWN,
        "status": PatternStatus.CONFIRMED,
        "reclaim_level": None,
        "failure_speed": None,
    }
    kwargs.update(overrides)
    return ClassicalPatternEventPayload(**kwargs)


# ─── تعدادات §13 ───


class TestEnums:
    def test_candle_families_eight(self) -> None:
        """العائلات الثماني §13.1 حرفيًا بقيم UPPERCASE."""
        assert len(CandlePatternFamily) == 8
        assert {f.value for f in CandlePatternFamily} == {
            "ENGULFING",
            "PIN_REJECTION",
            "HAMMER_SHOOTING_STAR",
            "INSIDE_BAR",
            "DOJI",
            "MORNING_EVENING_STAR",
            "STRONG_CLOSING",
            "EXPANSION",
        }

    def test_classical_types_eight_families_split_directions(self) -> None:
        """10 قيم لثماني عائلات §13.2 (الجهات المفصولة موثقة في العد)."""
        assert len(ClassicalPatternType) == 10
        assert ClassicalPatternType.DOUBLE_TOP == "DOUBLE_TOP"
        assert ClassicalPatternType.INVERSE_HEAD_AND_SHOULDERS == "INVERSE_HEAD_AND_SHOULDERS"
        assert ClassicalPatternType.FAILED_BREAKOUT == "FAILED_BREAKOUT"

    def test_pattern_status_candidate_confirmed(self) -> None:
        assert PatternStatus.CANDIDATE == "CANDIDATE"
        assert PatternStatus.CONFIRMED == "CONFIRMED"

    def test_candle_feature_keys_six(self) -> None:
        """مفاتيح السمات الست §13.1 حرفيًا."""
        assert (
            frozenset(
                {
                    "body_fraction",
                    "wick_asymmetry",
                    "close_location",
                    "range_percentile",
                    "gap_relationship",
                    "volume_relationship",
                }
            )
            == CANDLE_FEATURE_KEYS
        )


# ─── AnchorPoint ───


class TestAnchorPoint:
    def test_round_trip(self) -> None:
        anchor = make_anchor(3, 105.5, "NECKLINE")
        restored = AnchorPoint.model_validate_json(anchor.model_dump_json())
        assert restored == anchor

    def test_role_empty_rejected(self) -> None:
        with pytest.raises(ValidationError, match="role"):
            AnchorPoint(time=_dt(1), price=100.0, role="   ")

    def test_price_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            AnchorPoint(time=_dt(1), price=0.0, role="P1")

    def test_frozen_and_extra_forbid(self) -> None:
        anchor = make_anchor(1, 100.0, "P1")
        with pytest.raises(ValidationError):
            AnchorPoint.model_validate({"time": _dt(1), "price": 100.0, "role": "P1", "extra": 1})
        with pytest.raises(Exception):  # noqa: B017 — التخصيص على نموذج مجمّد
            anchor.role = "P9"  # type: ignore[misc]


# ─── CandlePatternEventPayload ───


class TestCandlePatternPayload:
    def test_round_trip(self) -> None:
        payload = make_candle_pattern()
        restored = CandlePatternEventPayload.model_validate_json(payload.model_dump_json())
        assert restored == payload

    def test_strength_bounds(self) -> None:
        with pytest.raises(ValidationError):
            make_candle_pattern(strength=1.5)
        with pytest.raises(ValidationError):
            make_candle_pattern(strength=-0.01)

    def test_bars_in_pattern_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_candle_pattern(bars_in_pattern=0)

    def test_feature_keys_restricted_to_six(self) -> None:
        with pytest.raises(ValidationError, match="غير قانونية"):
            make_candle_pattern(
                feature_readings={"body_fraction": 0.5, "rsi": 71.0},
            )

    def test_feature_readings_empty_rejected(self) -> None:
        with pytest.raises(ValidationError, match="فارغة"):
            make_candle_pattern(feature_readings={})

    def test_frozen_and_extra_forbid(self) -> None:
        payload = make_candle_pattern()
        with pytest.raises(ValidationError):
            CandlePatternEventPayload.model_validate({**payload.model_dump(), "magic": True})
        with pytest.raises(Exception):  # noqa: B017
            payload.strength = 0.9  # type: ignore[misc]

    def test_neutral_direction_legal_for_context(self) -> None:
        """NEUTRAL قانونية في العقد (للتصنيف السياقي غير المبثوث)."""
        payload = make_candle_pattern(
            family=CandlePatternFamily.DOJI,
            direction=PatternDirection.NEUTRAL,
            feature_readings={"body_fraction": 0.03},
            bars_in_pattern=1,
        )
        assert payload.direction == PatternDirection.NEUTRAL


# ─── ClassicalPatternEventPayload ───


class TestClassicalPatternPayload:
    def test_round_trip(self) -> None:
        payload = make_classical()
        restored = ClassicalPatternEventPayload.model_validate_json(payload.model_dump_json())
        assert restored == payload

    def test_outputs_eight_present(self) -> None:
        """مخرجات §13.2 الثمانية حاضرة بالأسماء الحرفية."""
        for field in (
            "pattern_type",
            "geometry",
            "anchor_points",
            "completion_time",
            "breakout_level",
            "invalidation_level",
            "measured_move",
            "quality",
        ):
            assert field in ClassicalPatternEventPayload.model_fields, field

    def test_quality_bounds(self) -> None:
        with pytest.raises(ValidationError):
            make_classical(quality=1.2)
        with pytest.raises(ValidationError):
            make_classical(quality=-0.1)

    def test_anchors_bounds(self) -> None:
        one = (make_anchor(1, 100.0, "P1"),)
        with pytest.raises(ValidationError, match=r"2\.\.8"):
            make_classical(anchor_points=one)
        nine = tuple(make_anchor(m, 100.0 + m, f"P{m}") for m in range(1, 10))
        with pytest.raises(ValidationError, match=r"2\.\.8"):
            make_classical(anchor_points=nine)

    def test_geometry_empty_rejected(self) -> None:
        with pytest.raises(ValidationError, match="geometry"):
            make_classical(geometry={})

    def test_failure_pair_contract(self) -> None:
        """زوج الفشل (§20) يحضر معًا أو يغيب معًا."""
        with pytest.raises(ValidationError, match="زوج الفشل"):
            make_classical(reclaim_level=91.0, failure_speed=None)
        with pytest.raises(ValidationError, match="زوج الفشل"):
            make_classical(reclaim_level=None, failure_speed=3.0)
        failed = make_classical(
            pattern_type=ClassicalPatternType.RANGE_BREAKOUT,
            status=PatternStatus.CANDIDATE,
            reclaim_level=91.0,
            failure_speed=2.5,
        )
        assert failed.reclaim_level is not None
        assert failed.failure_speed is not None

    def test_levels_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_classical(breakout_level=0.0)
        with pytest.raises(ValidationError):
            make_classical(invalidation_level=-5.0)
        with pytest.raises(ValidationError):
            make_classical(measured_move=0.0)

    def test_frozen_and_extra_forbid(self) -> None:
        payload = make_classical()
        with pytest.raises(ValidationError):
            ClassicalPatternEventPayload.model_validate(
                {**payload.model_dump(), "harmonic_ratio": 0.618}
            )
        with pytest.raises(Exception):  # noqa: B017
            payload.quality = 0.5  # type: ignore[misc]

    def test_ambiguous_geometry_stays_candidate(self) -> None:
        """«الغامض مرشح» (§13.2): القبول بقيمة status=CANDIDATE وجودة منخفضة."""
        payload = make_classical(
            status=PatternStatus.CANDIDATE,
            quality=0.18,
            geometry={"height_atr": 0.9, "width_bars": 8.0},
        )
        assert payload.status == PatternStatus.CANDIDATE


# ─── سجل الحمولات §32 ───


class TestPayloadRegistry:
    """المرحلة 5a تضيف أنواع الأنماط الستة إلى خريطة 23 (بنيوية/سيولية/
    تدفقية) — المجموع 29."""

    def test_pattern_types_mapped(self) -> None:
        for event_type in (
            EventType.BULLISH_ENGULFING,
            EventType.BEARISH_ENGULFING,
            EventType.REJECTION_CANDLE,
            EventType.INSIDE_BAR_BREAK,
        ):
            assert payload_model_for(event_type) is CandlePatternEventPayload
        for event_type in (EventType.CLASSICAL_BREAKOUT, EventType.CLASSICAL_FAILED_BREAKOUT):
            assert payload_model_for(event_type) is ClassicalPatternEventPayload

    def test_registry_size(self) -> None:
        assert len(EVENT_PAYLOAD_MODELS) == 29

    def test_mapped_models_are_pydantic(self) -> None:
        for model in (
            CandlePatternEventPayload,
            ClassicalPatternEventPayload,
            AnchorPoint,
        ):
            assert issubclass(model, BaseModel)
