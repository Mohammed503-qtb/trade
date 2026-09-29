"""اختبارات حمولات أحداث التدفق — المرحلة 4-a (§12 + §20 + §32).

العقود المفحوصة لكل حمولة من الخمسة (AbsorptionConditions و
AbsorptionEventPayload وFlowContinuationEventPayload و
ExhaustionEventPayload وImbalanceClusterEventPayload):

- round-trip JSON كامل (model_dump_json → model_validate_json → ==)؛
- رفض القيم خارج حدودها (حصص خارج [-1,1] وكفاءات غير موجبة ونسب سالبة
  وعدّادات سالبة)؛
- الجمود (frozen) ومنع الحقول الغريبة (extra="forbid")؛
- التطابق الاتجاهي: ABSORPTION_BUY ⇒ absorbed_pressure=SELL (§20 حرفيًا:
  «الضغط البيعي امتُص») — الحمولة متمركزة ذاتيًا؛
- المرشحية: الامتصاص يصدر confirmed=False حصرًا عند الإنشاء (فرضيات
  قابلة للتأكيد §12.2) — confirmed=True صنعة تأكيد لاحق لا إنشاء.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from schemas import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    FlowDirection,
    ImbalanceClusterEventPayload,
    ImbalanceSide,
)
from schemas.enums import EventType

UTC = UTC


def _dt(minute: int = 0) -> datetime:
    return datetime(2026, 9, 28, 3, minute, tzinfo=UTC)


# ─── مصانع أمثلة صالحة ───


def make_conditions(**overrides: Any) -> AbsorptionConditions:
    kwargs: dict[str, Any] = {
        "elevated_delta": True,
        "limited_extension": True,
        "repeated_response": True,
        "opposite_displacement": None,
    }
    kwargs.update(overrides)
    return AbsorptionConditions(**kwargs)


def make_absorption(**overrides: Any) -> AbsorptionEventPayload:
    """مرشح امتصاص شرائي (ABSORPTION_BUY): عدوانية بيعية كبيرة ردّ محدود."""
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(5),
        "absorbed_pressure": AbsorbedPressure.SELL,
        "delta": -412.5,
        "delta_share": -0.62,
        "excursion_atr": 0.31,
        "conditions": make_conditions(),
        "zone_id": None,
        "confirmed": False,
    }
    kwargs.update(overrides)
    return AbsorptionEventPayload(**kwargs)


def make_continuation(**overrides: Any) -> FlowContinuationEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(6),
        "direction": FlowDirection.UP,
        "delta": 318.2,
        "delta_share": 0.71,
        "response_atr": 1.42,
        "efficiency": 2.0,
    }
    kwargs.update(overrides)
    return FlowContinuationEventPayload(**kwargs)


def make_exhaustion(**overrides: Any) -> ExhaustionEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(7),
        "direction": FlowDirection.UP,
        "efficiency": 0.8,
        "efficiency_prev": 1.9,
        "decay_ratio": 0.42,
        "failed_extremes": 3,
        "follow_through": 0.15,
    }
    kwargs.update(overrides)
    return ExhaustionEventPayload(**kwargs)


def make_cluster(**overrides: Any) -> ImbalanceClusterEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(8),
        "side": ImbalanceSide.BUY,
        "bar_count": 4,
        "total_imbalances": 11,
        "max_row_ratio": 6.2,
        "aligned_with_displacement": True,
    }
    kwargs.update(overrides)
    return ImbalanceClusterEventPayload(**kwargs)


ALL_VALID: list[tuple[str, BaseModel]] = [
    ("conditions", make_conditions()),
    ("absorption", make_absorption()),
    ("continuation", make_continuation()),
    ("exhaustion", make_exhaustion()),
    ("cluster", make_cluster()),
]


# ─── round-trip وجمود وحقول غريبة ───


class TestOrderFlowPayloadContracts:
    @pytest.mark.parametrize(
        ("name", "instance"),
        ALL_VALID,
        ids=[name for name, _ in ALL_VALID],
    )
    def test_json_round_trip(self, name: str, instance: BaseModel) -> None:
        decoded = type(instance).model_validate_json(instance.model_dump_json())
        assert decoded == instance

    @pytest.mark.parametrize(
        ("name", "instance"),
        ALL_VALID,
        ids=[name for name, _ in ALL_VALID],
    )
    def test_frozen(self, name: str, instance: BaseModel) -> None:
        """الجمود عبر setattr مباشرة — model_copy(update=) يتجاوز التحقق بالتصميم."""
        field = "bar_time" if hasattr(instance, "bar_time") else "elevated_delta"
        with pytest.raises(ValidationError, match=r"frozen|Instance is frozen"):
            setattr(instance, field, None)

    @pytest.mark.parametrize(
        ("name", "instance"),
        ALL_VALID,
        ids=[name for name, _ in ALL_VALID],
    )
    def test_extra_forbidden(self, name: str, instance: BaseModel) -> None:
        data = instance.model_dump()
        data["ghost_field"] = 1
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            type(instance).model_validate(data)


# ─── الحدود §12 ───


class TestAbsorptionBounds:
    def test_buy_event_absorbs_sell_pressure(self) -> None:
        """ABSORPTION_BUY = الضغط البيعي امتُص (§20) — الحمولة تطابق النوع."""
        payload = make_absorption()
        assert payload.absorbed_pressure is AbsorbedPressure.SELL
        assert payload.delta < 0  # عدوانية بيعية
        assert payload.confirmed is False  # مرشح دائمًا عند الإنشاء (§12.2)

    def test_confirmed_true_requires_later_confirmation_not_creation(self) -> None:
        """confirmed=True حالة تأكيد لاحق مشروعة في العقد (لا يخلقها الكاشف)."""
        payload = make_absorption(confirmed=True)
        assert payload.confirmed is True  # البوابة تقبل التأكيد اللاحق — البث يوثقه

    def test_delta_share_bounded(self) -> None:
        with pytest.raises(ValidationError):
            make_absorption(delta_share=1.5)
        with pytest.raises(ValidationError):
            make_absorption(delta_share=-1.01)

    def test_excursion_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_absorption(excursion_atr=0.0)
        with pytest.raises(ValidationError):
            make_absorption(excursion_atr=-0.1)

    def test_conditions_fourth_optional_none_or_bool(self) -> None:
        cond = make_conditions(opposite_displacement=True)
        assert cond.opposite_displacement is True
        with pytest.raises(ValidationError):
            make_conditions(opposite_displacement="maybe")

    def test_zone_id_optional(self) -> None:
        assert make_absorption().zone_id is None
        zoned = make_absorption(zone_id="f108eb9a-1234")
        assert zoned.zone_id == "f108eb9a-1234"


class TestContinuationBounds:
    def test_response_and_efficiency_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_continuation(response_atr=0.0)
        with pytest.raises(ValidationError):
            make_continuation(efficiency=-1.0)

    def test_delta_share_signed_unit(self) -> None:
        with pytest.raises(ValidationError):
            make_continuation(delta_share=-1.2)
        ok = make_continuation(delta_share=-1.0)
        assert ok.delta_share == -1.0

    def test_direction_enum(self) -> None:
        assert make_continuation().direction is FlowDirection.UP
        with pytest.raises(ValidationError):
            make_continuation(direction="SIDEWAYS")


class TestExhaustionBounds:
    def test_efficiencies_and_decay_positive(self) -> None:
        for field in ("efficiency", "efficiency_prev", "decay_ratio"):
            with pytest.raises(ValidationError):
                make_exhaustion(**{field: 0.0})

    def test_failed_extremes_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            make_exhaustion(failed_extremes=-1)
        assert make_exhaustion(failed_extremes=0).failed_extremes == 0

    def test_follow_through_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            make_exhaustion(follow_through=1.01)
        assert make_exhaustion(follow_through=0.0).follow_through == 0.0


class TestClusterBounds:
    def test_bar_count_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            make_cluster(bar_count=0)
        assert make_cluster(bar_count=1).bar_count == 1

    def test_total_imbalances_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            make_cluster(total_imbalances=-3)

    def test_max_row_ratio_positive(self) -> None:
        with pytest.raises(ValidationError):
            make_cluster(max_row_ratio=0.0)


# ─── التسجيل في EVENT_PAYLOAD_MODELS (§20+§32) ───


class TestPayloadRegistry:
    @pytest.mark.parametrize(
        ("event_type", "model"),
        [
            (EventType.ABSORPTION_BUY, AbsorptionEventPayload),
            (EventType.ABSORPTION_SELL, AbsorptionEventPayload),
            (EventType.FLOW_CONTINUATION_UP, FlowContinuationEventPayload),
            (EventType.FLOW_CONTINUATION_DOWN, FlowContinuationEventPayload),
            (EventType.EXHAUSTION_UP, ExhaustionEventPayload),
            (EventType.EXHAUSTION_DOWN, ExhaustionEventPayload),
            (EventType.BUY_IMBALANCE_CLUSTER, ImbalanceClusterEventPayload),
            (EventType.SELL_IMBALANCE_CLUSTER, ImbalanceClusterEventPayload),
        ],
    )
    def test_flow_events_registered(self, event_type: EventType, model: type[BaseModel]) -> None:
        from schemas import payload_model_for

        assert payload_model_for(event_type) is model
