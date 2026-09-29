"""اختبارات كائنات البنية والسيولة (§10/§11) — round-trip وحدود وجمود
وسجل الحمولات (EVENT_PAYLOAD_MODELS) والتحقق ضد المخططات المُصدَّرة.

كل نموذج جديد: بناء مثال صالح → model_dump_json → model_validate_json →
== الأصل، ورفض القيم خارج الحدود، ورفض التعديل (frozen) ورفض الحقول
الغريبة (extra="forbid")، والفواصل السعرية المعكوسة تُرفض (تحقق صاخب).
قيم التعدادات منسوخة هنا كثوابت مرجعية مستقلة عن الوحدة المختبرة.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from jsonschema import validate as jsonschema_validate
from pydantic import BaseModel, ValidationError
from schemas import (
    EVENT_PAYLOAD_MODELS,
    BreakAcceptEventPayload,
    BreakDirection,
    DisplacementEventPayload,
    EventType,
    FvgDirection,
    FvgEventPayload,
    FvgState,
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    StructureBreakPayload,
    StructureConsequence,
    SweepClassification,
    SweepEventPayload,
    Swing,
    SwingDirection,
    SwingScope,
    ZoneState,
    payload_model_for,
)
from schemas.export import ALL_MODELS, GENERATED_DIR, check

UTC = UTC


def _dt(minute: int = 0, second: int = 0) -> datetime:
    """زمن حدث قياسي بمنطقة UTC — عقد §7.1."""
    return datetime(2026, 9, 27, 2, minute, second, tzinfo=UTC)


# ─── مصانع أمثلة صالحة لكل نموذج (overrides لاختبار الحدود) ───


def make_swing(**overrides: Any) -> Swing:
    kwargs: dict[str, Any] = {
        "swing_id": "sw-0001",
        "price": 60_180.0,
        "timeframe": "15m",
        "direction": SwingDirection.HIGH,
        "strength": 0.82,
        # §11.1: التأكيد بعد قاعدة النظر الخلفي — confirmation = bar + تأخير
        "confirmation_time": _dt(minute=45),
        "external_or_internal": SwingScope.EXTERNAL,
        "bar_time": _dt(minute=30),  # الامتداد الموثق: شمعة القمة نفسها
    }
    kwargs.update(overrides)
    return Swing(**kwargs)


def make_structure_break(**overrides: Any) -> StructureBreakPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "swing_id": "sw-0001",  # المتطرف المكسور (§11.1)
        "swing_scope": SwingScope.EXTERNAL,
        "break_direction": BreakDirection.UP,
        "breach_distance_atr": 0.62,  # مسافة الكسر/ATR (مقياس §11.2)
        "closing_acceptance": 0.91,  # قبول الإغلاق (§11.2)
        "follow_through": 0.77,
        "choch_prior_direction": None,  # BOS لا CHOCH
    }
    kwargs.update(overrides)
    return StructureBreakPayload(**kwargs)


def make_displacement(**overrides: Any) -> DisplacementEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "direction": BreakDirection.UP,
        "range_zscore": 2.9,  # السمات الست الحرفية §11.4
        "body_fraction": 0.88,
        "close_location": 0.95,
        "atr_multiple": 2.4,
        "velocity": 1.8,  # مدى/شمعة
        "follow_through": 0.7,
    }
    kwargs.update(overrides)
    return DisplacementEventPayload(**kwargs)


def make_fvg(**overrides: Any) -> FvgEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "direction": FvgDirection.BULLISH,  # الفجوة الصاعدة (§11.5)
        "gap_low": 60_120.0,  # قمة الشمعة قبل-pre
        "gap_high": 60_310.0,  # قاع الشمعة الحالية — الفاصل موجب العرض
        "size_atr": 1.1,  # الحجم/ATR المحلي (§11.5)
        "state": FvgState.CREATED,  # البث هو التكوين حصرًا
    }
    kwargs.update(overrides)
    return FvgEventPayload(**kwargs)


def make_order_block(**overrides: Any) -> OrderBlockEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "direction": FvgDirection.BULLISH,  # منطقة مصدرية صاعدة
        "zone_low": 59_910.0,  # الشمعة/العنقود المعاكس المصدر (§11.6 خطوة 2)
        "zone_high": 60_060.0,
        "origin_time": _dt(minute=0),
        "displacement_id": "disp-0007",  # الإزاحة المولِّدة (§11.6 خطوة 1)
        "structure_consequence": StructureConsequence.BOS,  # خطوة 3
        "size_atr": 0.9,
    }
    kwargs.update(overrides)
    return OrderBlockEventPayload(**kwargs)


def make_premium_discount(**overrides: Any) -> PremiumDiscountEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "range_name": "dealing-15m-sw-0001",  # §11.7: النطاق يُسمّى صراحةً
        "range_low": 59_400.0,
        "range_high": 60_600.0,
        "equilibrium": 60_000.0,  # (high+low)/2 حرفيًا (§11.7)
        "location": PremiumDiscountSide.PREMIUM,
        "normalized_distance": 0.42,  # (price−eq)/(range/2) — قد يتجاوز ±1
        "price": 60_420.0,
    }
    kwargs.update(overrides)
    return PremiumDiscountEventPayload(**kwargs)


def make_liquidity_zone(**overrides: Any) -> LiquidityZone:
    kwargs: dict[str, Any] = {
        # §10.2 حرفيًا
        "zone_id": "lz-0001",
        "side": LiquiditySide.SELL_SIDE,  # سيولة بيعية عند القاع (§10.1)
        "price_low": 59_400.0,
        "price_high": 59_480.0,
        "origin_time": _dt(minute=0),
        "age": 34,  # شموع عند آخر تحديث — لقطة لا قيمة حية
        "source_type": LiquiditySourceType.PRIOR_SWING,
        "test_count": 2,
        "last_test_time": _dt(minute=15),
        "sweep_status": SweepClassification.UNKNOWN,  # لم يكتمل تسلسل §10.4
        "reaction_score": 0.8,
        "unmitigated_score": 0.9,
        "importance_score": 0.75,  # §10.3: الدرجة ليست احتمالًا
        # الامتدادات التشغيلية الموثقة
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "state": ZoneState.ACTIVE,
    }
    kwargs.update(overrides)
    return LiquidityZone(**kwargs)


def make_sweep(**overrides: Any) -> SweepEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=30),
        "zone_id": "lz-0001",  # الربط الإلزامي بالمنطقة (§10.4 شرط 5)
        "zone_side": LiquiditySide.SELL_SIDE,
        "classification": SweepClassification.CONFIRMED_SWEEP,  # عند البث دائمًا
        "excursion_atr": 0.31,  # أقصى تجاوز/ATR (§10.4)
        "penetration_reached": True,  # الشرط 3 §10.4
        "reclaim_bars": 2,  # سرعة الاسترجاع (§20 «reclaim speed»)
        "test_count_at_event": 3,
    }
    kwargs.update(overrides)
    return SweepEventPayload(**kwargs)


def make_break_accept(**overrides: Any) -> BreakAcceptEventPayload:
    kwargs: dict[str, Any] = {
        "instrument": "BINANCE_USDM:BTCUSDT",
        "timeframe": "15m",
        "bar_time": _dt(minute=45),
        "zone_id": "lz-0002",
        "zone_side": LiquiditySide.BUY_SIDE,
        "excursion_atr": 0.55,
        "acceptance_ratio": 0.83,  # §20 «Acceptance ratio»
        "window_bars": 6,
    }
    kwargs.update(overrides)
    return BreakAcceptEventPayload(**kwargs)


_NEW_MODELS: list[tuple[str, BaseModel]] = [
    ("Swing", make_swing()),
    ("StructureBreakPayload", make_structure_break()),
    ("DisplacementEventPayload", make_displacement()),
    ("FvgEventPayload", make_fvg()),
    ("OrderBlockEventPayload", make_order_block()),
    ("PremiumDiscountEventPayload", make_premium_discount()),
    ("LiquidityZone", make_liquidity_zone()),
    ("SweepEventPayload", make_sweep()),
    ("BreakAcceptEventPayload", make_break_accept()),
]

_NEW_MODEL_NAMES = [name for name, _ in _NEW_MODELS]

# ─── Round-trip ───


class TestRoundTrip:
    """JSON round-trip لكل نموذج جديد — العقد يبقى مطابقًا لنفسه عبر السلك."""

    @pytest.mark.parametrize(
        ("name", "instance"),
        _NEW_MODELS,
        ids=_NEW_MODEL_NAMES,
    )
    def test_json_round_trip(self, name: str, instance: BaseModel) -> None:
        text = instance.model_dump_json()
        restored = type(instance).model_validate_json(text)
        assert restored == instance, f"round-trip فشل لـ{name}"

    def test_python_round_trip_liquidity_zone(self) -> None:
        zone = make_liquidity_zone()
        assert LiquidityZone.model_validate(zone.model_dump()) == zone

    def test_str_enum_serializes_to_plain_value(self) -> None:
        assert make_swing().model_dump()["direction"] == "HIGH"
        assert make_liquidity_zone().model_dump()["side"] == "SELL_SIDE"
        assert make_fvg().model_dump()["state"] == "CREATED"
        assert make_sweep().model_dump()["classification"] == "CONFIRMED_SWEEP"

    def test_time_contract_normalizes_to_utc(self) -> None:
        from datetime import timezone

        plus3 = timezone(timedelta(hours=3))
        swing = make_swing(bar_time=datetime(2026, 9, 27, 5, 30, tzinfo=plus3))
        assert swing.bar_time.utcoffset() == timedelta(0)
        assert swing.bar_time == _dt(minute=30)

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="bar_time"):
            make_premium_discount(bar_time=datetime(2026, 9, 27, 2, 30))


# ─── عقد §11.1: Swing ───


class TestSwingContract:
    """حقول §11.1 الحرفية + الامتداد الموثق الوحيد bar_time."""

    def test_fields_are_section_11_1_literal_plus_one_extension(self) -> None:
        assert set(Swing.model_fields) == {
            # السبعة الحرفية من نص §11.1
            "swing_id",
            "price",
            "timeframe",
            "direction",
            "strength",
            "confirmation_time",
            "external_or_internal",
            # الامتداد التشغيلي الموثق (وقت شمعة القمة/القاع نفسها)
            "bar_time",
        }

    def test_swing_direction_values_literal(self) -> None:
        assert {member.value for member in SwingDirection} == {"HIGH", "LOW"}
        assert SwingDirection.HIGH == "HIGH"
        assert SwingDirection.LOW == "LOW"

    def test_swing_scope_values_literal(self) -> None:
        assert {member.value for member in SwingScope} == {"EXTERNAL", "INTERNAL"}

    def test_strength_is_unit_interval(self) -> None:
        for bad in (-0.01, 1.01, 2.0):
            with pytest.raises(ValidationError, match="strength"):
                make_swing(strength=bad)


# ─── عقد §10.2: LiquidityZone ───


class TestLiquidityZoneContract:
    """الحقول الاثنا عشر الحرفية من §10.2 + الامتدادات الثلاثة الموثقة."""

    def test_fields_are_section_10_2_literal_plus_extensions(self) -> None:
        literal = {
            "zone_id",
            "side",
            "price_low",
            "price_high",
            "origin_time",
            "age",
            "source_type",
            "test_count",
            "last_test_time",
            "sweep_status",
            "reaction_score",
            "unmitigated_score",
            "importance_score",
        }
        extensions = {"instrument", "timeframe", "state"}
        assert set(LiquidityZone.model_fields) == literal | extensions

    def test_inverted_price_band_raises(self) -> None:
        with pytest.raises(ValidationError, match="فاصل المنطقة معكوس"):
            make_liquidity_zone(price_low=60_100.0, price_high=60_050.0)

    def test_degenerate_single_price_band_allowed(self) -> None:
        zone = make_liquidity_zone(price_low=59_400.0, price_high=59_400.0)
        assert zone.price_low == zone.price_high

    @pytest.mark.parametrize("bad", [-0.1, -0.0001, 1.0001, 1.1, 2.0])
    def test_unit_interval_fields_out_of_range(self, bad: float) -> None:
        for field in ("reaction_score", "unmitigated_score", "importance_score"):
            with pytest.raises(ValidationError, match=field):
                make_liquidity_zone(**{field: bad})

    @pytest.mark.parametrize("bad", [-1, -5])
    def test_counts_reject_negative(self, bad: int) -> None:
        for field in ("age", "test_count"):
            with pytest.raises(ValidationError, match=field):
                make_liquidity_zone(**{field: bad})

    def test_last_test_time_nullable_required(self) -> None:
        zone = make_liquidity_zone(last_test_time=None, test_count=0)
        assert zone.last_test_time is None
        assert "last_test_time" in zone.model_dump()  # حاضرًا دومًا كحقول §10.2

    def test_side_values_literal(self) -> None:
        assert {member.value for member in LiquiditySide} == {"BUY_SIDE", "SELL_SIDE"}

    def test_source_type_values_literal(self) -> None:
        assert {member.value for member in LiquiditySourceType} == {
            "PRIOR_SWING",
            "EQUAL_LEVEL",
            "SESSION_EXTREME",
            "PREV_DAY_EXTREME",
            "PREV_WEEK_EXTREME",
            "RANGE_BOUNDARY",
        }

    def test_zone_state_values_literal(self) -> None:
        assert {member.value for member in ZoneState} == {
            "ACTIVE",
            "SWEPT",
            "CONSUMED",
            "INVALIDATED",
        }


# ─── حدود الحمولات ───


class TestPayloadBounds:
    """القيم خارج حدود الخطة تُرفض — تحقق صاخب لا تصحيح صامت."""

    @pytest.mark.parametrize("bad", [0.0, -0.5])
    def test_positive_atr_fields_reject_non_positive(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="breach_distance_atr"):
            make_structure_break(breach_distance_atr=bad)
        with pytest.raises(ValidationError, match="atr_multiple"):
            make_displacement(atr_multiple=bad)
        with pytest.raises(ValidationError, match="velocity"):
            make_displacement(velocity=bad)
        with pytest.raises(ValidationError, match="size_atr"):
            make_fvg(size_atr=bad)
        with pytest.raises(ValidationError, match="size_atr"):
            make_order_block(size_atr=bad)
        with pytest.raises(ValidationError, match="excursion_atr"):
            make_sweep(excursion_atr=bad)
        with pytest.raises(ValidationError, match="excursion_atr"):
            make_break_accept(excursion_atr=bad)

    @pytest.mark.parametrize("bad", [-0.1, 1.0001, 1.5])
    def test_unit_interval_fields_out_of_range(self, bad: float) -> None:
        for field in ("closing_acceptance", "follow_through"):
            with pytest.raises(ValidationError, match=field):
                make_structure_break(**{field: bad})
        for field in ("body_fraction", "close_location", "follow_through"):
            with pytest.raises(ValidationError, match=field):
                make_displacement(**{field: bad})
        with pytest.raises(ValidationError, match="acceptance_ratio"):
            make_break_accept(acceptance_ratio=bad)

    @pytest.mark.parametrize("bad", [-1, -3])
    def test_non_negative_int_fields_reject_negative(self, bad: int) -> None:
        with pytest.raises(ValidationError, match="reclaim_bars"):
            make_sweep(reclaim_bars=bad)
        with pytest.raises(ValidationError, match="test_count_at_event"):
            make_sweep(test_count_at_event=bad)
        with pytest.raises(ValidationError, match="window_bars"):
            make_break_accept(window_bars=bad)

    def test_inverted_fvg_gap_raises(self) -> None:
        with pytest.raises(ValidationError, match="فاصل الفجوة معكوس"):
            make_fvg(gap_low=60_310.0, gap_high=60_120.0)

    def test_inverted_order_block_zone_raises(self) -> None:
        with pytest.raises(ValidationError, match="فاصل المنطقة معكوس"):
            make_order_block(zone_low=60_060.0, zone_high=59_910.0)

    def test_dealing_range_must_be_well_defined(self) -> None:
        # منحل (عرض صفري) — يبطل normalized_distance (قسمة على صفر)
        with pytest.raises(ValidationError, match="نطاق معالجة"):
            make_premium_discount(range_low=60_000.0, range_high=60_000.0)
        # معكوس
        with pytest.raises(ValidationError, match="نطاق معالجة"):
            make_premium_discount(range_low=61_000.0, range_high=60_000.0)

    def test_normalized_distance_may_exceed_unit_outside_range(self) -> None:
        # §11.7 موثق: الإقصاء المطبَّع قد يتجاوز ±1 خارج النطاق — معلومة لا خطأ
        payload = make_premium_discount(normalized_distance=1.42)
        assert payload.normalized_distance == 1.42
        payload = make_premium_discount(normalized_distance=-1.42)
        assert payload.normalized_distance == -1.42

    def test_choch_prior_direction_none_for_bos(self) -> None:
        assert make_structure_break().choch_prior_direction is None
        choch = make_structure_break(choch_prior_direction=BreakDirection.DOWN)
        assert choch.choch_prior_direction == BreakDirection.DOWN  # CHOCH فقط


# ─── الجمود والحقول الغريبة ───


class TestFrozenAndExtra:
    """كل نموذج جديد مجمّد (لا تعديل) ويمنع الحقول الغريبة (عقد مغلق)."""

    @pytest.mark.parametrize(
        ("name", "instance"),
        _NEW_MODELS,
        ids=_NEW_MODEL_NAMES,
    )
    def test_frozen_rejects_mutation(self, name: str, instance: BaseModel) -> None:
        first_field = next(iter(type(instance).model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, first_field, None)

    @pytest.mark.parametrize(
        ("name", "instance"),
        _NEW_MODELS,
        ids=_NEW_MODEL_NAMES,
    )
    def test_extra_fields_forbidden(self, name: str, instance: BaseModel) -> None:
        data = instance.model_dump()
        poisoned = {**data, "sorcerer_field": 42}
        with pytest.raises(ValidationError, match=r"[Ee]xtra"):
            type(instance).model_validate(poisoned)


# ─── سجل الحمولات: EVENT_PAYLOAD_MODELS ───

# الأنواع البنيوية/السيولية الخمسة عشر (§20) — ثابت مرجعي مستقل
STRUCTURAL_EVENT_TYPES: set[EventType] = {
    EventType.INTERNAL_BOS,
    EventType.EXTERNAL_BOS,
    EventType.CHOCH,
    EventType.DISPLACEMENT_UP,
    EventType.DISPLACEMENT_DOWN,
    EventType.LIQUIDITY_SWEEP_HIGH,
    EventType.LIQUIDITY_SWEEP_LOW,
    EventType.BREAK_AND_ACCEPT_HIGH,
    EventType.BREAK_AND_ACCEPT_LOW,
    EventType.FVG_BULLISH,
    EventType.FVG_BEARISH,
    EventType.ORDER_BLOCK_BULLISH,
    EventType.ORDER_BLOCK_BEARISH,
    EventType.PREMIUM_LOCATION,
    EventType.DISCOUNT_LOCATION,
}


#: أحداث التدفق الثمانية الموثقة في المرحلة 4 (§12 + §20) — توسعة مشروعة
#: لخريطة الحمولات فوق الخمسة عشر البنيوية/السيولية.
FLOW_EVENT_TYPES = {
    EventType.ABSORPTION_BUY,
    EventType.ABSORPTION_SELL,
    EventType.FLOW_CONTINUATION_UP,
    EventType.FLOW_CONTINUATION_DOWN,
    EventType.EXHAUSTION_UP,
    EventType.EXHAUSTION_DOWN,
    EventType.BUY_IMBALANCE_CLUSTER,
    EventType.SELL_IMBALANCE_CLUSTER,
}


#: أحداث الأنماط الستة الموثقة في المرحلة 5a (§13 + §20) — أربعة شموعية
#: واثنان كلاسيكيان فوق الخمسة عشر البنيوية والثمانية التدفقية.
PATTERN_EVENT_TYPES = {
    EventType.BULLISH_ENGULFING,
    EventType.BEARISH_ENGULFING,
    EventType.REJECTION_CANDLE,
    EventType.INSIDE_BAR_BREAK,
    EventType.CLASSICAL_BREAKOUT,
    EventType.CLASSICAL_FAILED_BREAKOUT,
}


class TestPayloadRegistry:
    """الخريطة: 15 بنيويًا/سيوليًا (المرحلة 3) + 8 تدفقية (المرحلة 4)
    + 6 أنماطية (المرحلة 5a)."""

    def test_registry_covers_structural_types_exactly(self) -> None:
        assert set(EVENT_PAYLOAD_MODELS) >= STRUCTURAL_EVENT_TYPES
        assert (set(EVENT_PAYLOAD_MODELS) - STRUCTURAL_EVENT_TYPES) == (
            FLOW_EVENT_TYPES | PATTERN_EVENT_TYPES
        )
        assert len(EVENT_PAYLOAD_MODELS) == 29

    def test_every_mapped_model_is_pydantic_base_model(self) -> None:
        for model in EVENT_PAYLOAD_MODELS.values():
            assert issubclass(model, BaseModel), model

    def test_break_payload_serves_all_three_break_types(self) -> None:
        for event_type in (EventType.INTERNAL_BOS, EventType.EXTERNAL_BOS, EventType.CHOCH):
            assert payload_model_for(event_type) is StructureBreakPayload

    def test_expected_model_per_event_family(self) -> None:
        assert payload_model_for(EventType.DISPLACEMENT_UP) is DisplacementEventPayload
        assert payload_model_for(EventType.DISPLACEMENT_DOWN) is DisplacementEventPayload
        assert payload_model_for(EventType.LIQUIDITY_SWEEP_HIGH) is SweepEventPayload
        assert payload_model_for(EventType.LIQUIDITY_SWEEP_LOW) is SweepEventPayload
        assert payload_model_for(EventType.BREAK_AND_ACCEPT_HIGH) is BreakAcceptEventPayload
        assert payload_model_for(EventType.BREAK_AND_ACCEPT_LOW) is BreakAcceptEventPayload
        assert payload_model_for(EventType.FVG_BULLISH) is FvgEventPayload
        assert payload_model_for(EventType.FVG_BEARISH) is FvgEventPayload
        assert payload_model_for(EventType.ORDER_BLOCK_BULLISH) is OrderBlockEventPayload
        assert payload_model_for(EventType.ORDER_BLOCK_BEARISH) is OrderBlockEventPayload
        assert payload_model_for(EventType.PREMIUM_LOCATION) is PremiumDiscountEventPayload
        assert payload_model_for(EventType.DISCOUNT_LOCATION) is PremiumDiscountEventPayload

    def test_payload_model_for_none_outside_documented_map(self) -> None:
        # الأنماط والجلسات وHTF بلا حمولة موثقة بعد (طور لاحق) —
        # الأحداث التدفقية موثقة منذ المرحلة 4 (§12)
        assert payload_model_for(EventType.HTF_BULLISH) is None
        assert payload_model_for(EventType.HTF_BEARISH) is None

    def test_every_payload_is_self_contained(self) -> None:
        """التمركز الذاتي (§32): instrument/timeframe/bar_time في كل حمولة."""
        for model in EVENT_PAYLOAD_MODELS.values():
            fields = set(model.model_fields)
            assert {"instrument", "timeframe", "bar_time"} <= fields, model


# ─── التصدير: كل نموذج جديد بمخططه ───


class TestExportRegistration:
    """«لا رسالة بلا مخطط مُصدَّر»: كل نموذج جديد في ALL_MODELS وgenerated/."""

    def test_all_new_models_registered(self) -> None:
        for name in _NEW_MODEL_NAMES:
            assert name in ALL_MODELS, f"{name} غير مسجل في ALL_MODELS"

    def test_generated_dir_check_passes(self) -> None:
        assert check(GENERATED_DIR) == 0

    def test_schema_files_exist_on_disk(self) -> None:
        for name in _NEW_MODEL_NAMES:
            assert (GENERATED_DIR / f"{name}.schema.json").is_file(), name

    def test_index_json_lists_new_models(self) -> None:
        index = json.loads((GENERATED_DIR / "index.json").read_text(encoding="utf-8"))
        assert set(index) == set(ALL_MODELS)
        for name in _NEW_MODEL_NAMES:
            assert name in index

    @pytest.mark.parametrize(
        ("name", "instance"),
        _NEW_MODELS,
        ids=_NEW_MODEL_NAMES,
    )
    def test_example_validates_against_exported_schema(
        self, name: str, instance: BaseModel
    ) -> None:
        schema = json.loads((GENERATED_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        jsonschema_validate(instance.model_dump(mode="json"), schema)
