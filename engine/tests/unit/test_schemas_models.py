"""اختبارات النماذج — round-trip وحدود وجمود ومنع الحقول الغريبة.

كل نموذج: بناء مثال صالح → model_dump_json → model_validate_json → == الأصل،
ورفض القيم خارج الحدود (§19.1 وغيرها)، ورفض التعديل (frozen) ورفض الحقول
الغريبة (extra="forbid").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError
from schemas import (
    Candle,
    CostBreakdown,
    CostMode,
    EvaluationContext,
    EventEnvelope,
    EvidenceRecord,
    ExperienceRecord,
    ExplanationObject,
    FootprintBar,
    HardBlockReason,
    InvalidationRule,
    LatencyRecord,
    MacroEventWindow,
    MarketRegime,
    MarketStateSnapshot,
    NoTradeExplanation,
    NoTradeSeverity,
    OrderIntent,
    PriceZone,
    RejectionBasis,
    RewardRiskEstimate,
    RiskDecision,
    Scenario,
    ScenarioTemplate,
    ScenarioTransition,
    SessionType,
    SizingCapBasis,
    SizingModifier,
    SizingModifierName,
    SizingResult,
    SlippageRecord,
    StructuralStop,
    TargetZone,
    TradeEvent,
    TriggerDefinition,
)
from schemas.enums import (
    DataQuality,
    Direction,
    EventType,
    EvidenceGroup,
    ScenarioState,
)

UTC = UTC


def _dt(minute: int = 0, second: int = 0) -> datetime:
    """زمن حدث قياسي بمنطقة UTC — عقد §7.1."""
    return datetime(2026, 9, 27, 2, minute, second, tzinfo=UTC)


# ─── مصانع أمثلة صالحة لكل نموذج (overrides لاختبار الحدود) ───


def make_market_state(**overrides: Any) -> MarketStateSnapshot:
    kwargs: dict[str, Any] = {
        "instrument": "BTCUSDT",
        "timeframe": "15m",
        "event_time": _dt(),
        "regime": MarketRegime.TREND_PULLBACK,
        "htf_bias": "BULLISH",
        "volatility_percentile": 62.4,  # مثال §32 حرفيًا
        "data_quality": DataQuality.HEALTHY,
    }
    kwargs.update(overrides)
    return MarketStateSnapshot(**kwargs)


def make_evidence(**overrides: Any) -> EvidenceRecord:
    kwargs: dict[str, Any] = {
        "evidence_id": "ev-0001",
        "group": EvidenceGroup.LIQUIDITY_LOCATION,
        "event_type": EventType.LIQUIDITY_SWEEP_LOW,
        "direction_score": 0.8,
        "raw_strength": 0.9,
        "quality": 0.85,
        "freshness": 1.0,
        "independence_discount": 0.7,
        "prior_weight": 0.95,  # وزن LIQUIDITY_SWEEP_LOW من §20
        "context_modifier": 1.0,
        "opposition": False,
        "source": "liquidity.detector",
        "correlation_group_id": "corr-impulse-42",
        # امتدادا سلسلة الجرد (المرحلة 6): مرساة الترتيب ووصلة الحدث
        "event_time": datetime(2026, 1, 5, tzinfo=UTC),
        "event_id": "0f8e2b6a-1c3d-5e4f-9a8b-7c6d5e4f3a2b",
    }
    kwargs.update(overrides)
    return EvidenceRecord(**kwargs)


def make_trigger() -> TriggerDefinition:
    return TriggerDefinition(
        condition_type="ZONE_RECLAIM",
        params={"zone_id": "lz-001", "timeframe": "1m", "min_displacement_atr": 0.5},
    )


def make_invalidation() -> InvalidationRule:
    return InvalidationRule(
        structural_level=59_400.0,
        volatility_buffer=120.0,  # عازلة من بنية التقلب لا رقم كوني (§23.4)
        accept_through=True,  # الإبطال بقبول عبر المستوى لا بمجرد فتيل (§18.5)
    )


def make_scenario(**overrides: Any) -> Scenario:
    kwargs: dict[str, Any] = {
        "scenario_id": "sc-0001",
        "symbol": "BTCUSDT",
        "direction": Direction.LONG,
        "regime": MarketRegime.TREND_PULLBACK,
        "context_snapshot": make_market_state(),
        "location_snapshot": {
            "zone_ids": ["lz-001"],
            "dealing_range": {"low": 59_000, "high": 61_000},
        },
        "thesis": "اجتياح سيولة بيعية ثم رفض وإزاحة صاعدة نحو سيولة شرائية",
        "supporting_evidence": ["ev-0001", "ev-0002"],
        "opposing_evidence": ["ev-0003"],
        "trigger_definition": make_trigger(),
        "entry_zone": PriceZone(price_low=59_800.0, price_high=60_050.0),
        "invalidation": make_invalidation(),
        "primary_targets": [TargetZone(price_level=60_900.0, zone_id="lz-high-001")],
        "secondary_targets": [TargetZone(price_level=61_500.0, zone_id="lz-high-002")],
        "expiry_time": _dt() + timedelta(hours=8),
        "state": ScenarioState.DRAFT,
        "scenario_score": 0.62,  # درجة خام لا احتمال (§2.6)
        "calibrated_probability": None,
        # امتدا المرحلة 7 (D-04): هوية القالب والحدث المرسي
        "template": ScenarioTemplate.REVERSAL,
        "proposed_from_event_id": "3f2a2c34-1111-4ddd-9a9e-000000000001",
    }
    kwargs.update(overrides)
    return Scenario(**kwargs)


def make_trade_event(**overrides: Any) -> TradeEvent:
    kwargs: dict[str, Any] = {
        "event_time_utc": _dt(second=15),
        "receive_time_utc": _dt(second=16),
        "source_timeframe": "1m",
        "venue": "BINANCE_USDM",
        "symbol": "BTCUSDT",
        "feed_id": "binance.aggTrades",
        "sequence_id": "741",
        "source_latency_ms": 12.5,
        "price": 60_120.5,
        "quantity": 0.004,
        "buyer_is_maker": False,
    }
    kwargs.update(overrides)
    return TradeEvent(**kwargs)


def make_candle(**overrides: Any) -> Candle:
    kwargs: dict[str, Any] = {
        "instrument_id": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(),
        "session_id": "20260927-UTC_DAY",
        "quality": DataQuality.HEALTHY,
        "is_closed": True,  # §27: المؤكد وحده مؤهل للقرار الحي
        "open": 60_000.0,
        "high": 60_150.0,
        "low": 59_990.0,
        "close": 60_120.5,
        "volume": 118.4,
        "range": 160.0,
        "body_size": 120.5,
        "upper_wick": 29.5,
        "lower_wick": 10.0,
        "body_fraction": 0.753,
        "close_location_value": 0.816,
        "true_range": 161.0,
        "realized_volatility": 0.0027,
    }
    kwargs.update(overrides)
    return Candle(**kwargs)


def make_footprint(**overrides: Any) -> FootprintBar:
    kwargs: dict[str, Any] = {
        "instrument_id": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": _dt(),
        "quality": DataQuality.HEALTHY,
        "is_closed": True,
        "source_feed": "binance.aggTrades",
        "methodology": "buyer_is_maker aggression v1 (§12.7)",  # المصدر والمنهجية إلزاميان
        "buy_volume": 70.2,
        "sell_volume": 48.2,
        "total_volume": 118.4,
        "delta": 22.0,
        "buy_share": 0.593,
        "sell_share": 0.407,
        "poc": 60_050.0,
        "vah": 60_110.0,
        "val": 60_010.0,
        "row_count": 12,
        "buy_imbalance_count": 2,
        "sell_imbalance_count": 1,
        "max_positive_delta_row": 60_050.0,
        "max_negative_delta_row": 60_020.0,
    }
    kwargs.update(overrides)
    return FootprintBar(**kwargs)


def make_envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        schema_version="1.0.0",
        event_type=EventType.CHOCH,
        event_time=_dt(),
        receive_time=_dt(second=1),
        source="structure.detector",
        trace_id="trace-0001",
        correlation_id=None,
        payload={"instrument": "BTCUSDT", "note": "choch"},
    )


def make_order_intent(**overrides: Any) -> OrderIntent:
    kwargs: dict[str, Any] = {
        "trade_intent_id": "ti-0001",
        "scenario_id": "sc-0001",
        "symbol": "BTCUSDT",
        "side": Direction.LONG,
        "entry_policy": "LIMIT_AT_ZONE",
        "entry_zone": PriceZone(price_low=59_800.0, price_high=60_050.0),
        "stop": 59_280.0,
        "targets": [TargetZone(price_level=60_900.0, zone_id="lz-high-001")],
        "max_slippage": 15.0,
        "max_latency": 250.0,
        "expiry": _dt() + timedelta(minutes=30),
        "risk_budget": 100.0,
        "client_order_id": "co-0001",
    }
    kwargs.update(overrides)
    return OrderIntent(**kwargs)


def make_slippage() -> SlippageRecord:
    return SlippageRecord(
        modeled_entry=60_000.0,
        actual_average_entry=60_008.5,
        modeled_exit=60_900.0,
        actual_average_exit=60_895.0,
        entry_slippage=8.5,
        exit_slippage=-5.0,  # سالب = انزلاق ملائم عند الخروج
    )


def make_latency() -> LatencyRecord:
    base = _dt()
    return LatencyRecord(
        signal_time=base,
        webhook_receive_time=base + timedelta(milliseconds=180),
        engine_decision_time=base + timedelta(milliseconds=410),
        broker_send_time=base + timedelta(milliseconds=415),
        exchange_ack_time=base + timedelta(milliseconds=590),
        fill_time=base + timedelta(milliseconds=730),
    )


def make_macro_window(**overrides: Any) -> MacroEventWindow:
    kwargs: dict[str, Any] = {
        "event_time": _dt(minute=30),
        "asset_scope": "*",
        "importance": "HIGH",
        "title": "بيان التضخم الأمريكي CPI",
        "pre_event_window_s": 900.0,
        "post_event_window_s": 600.0,
    }
    kwargs.update(overrides)
    return MacroEventWindow(**kwargs)


def make_no_trade_explanation(**overrides: Any) -> NoTradeExplanation:
    kwargs: dict[str, Any] = {
        "no_trade_code": HardBlockReason.KILL_SWITCH,
        "severity": NoTradeSeverity.HARD,
        "triggering_conditions": "مفتاح الإيقاف مفعّل — كل دخول جديد ممنوع",
        "offsetting_evidence": ("ev-0001", "ev-0002"),
        "whether_retry_is_allowed": False,
        "retry_condition": None,
    }
    kwargs.update(overrides)
    return NoTradeExplanation(**kwargs)


def make_stop(**overrides: Any) -> StructuralStop:
    kwargs: dict[str, Any] = {
        "structural_level": 59_400.0,
        "volatility_buffer": 120.0,
        "execution_uncertainty": 18.0,
        "stop_price": 59_262.0,  # 59400 − (120 + 18) — إبطال LONG تحت البنية
        "entry_reference": 60_050.0,  # الحافة المحافظة (أبعد عن الوقف)
        "stop_distance": 788.0,
        "accept_through": True,
        "atr": 240.0,
        "stop_distance_atr": 788.0 / 240.0,
    }
    kwargs.update(overrides)
    return StructuralStop(**kwargs)


def make_sizing_modifier(
    name: SizingModifierName = SizingModifierName.VOLATILITY,
    multiplier: float = 0.85,
) -> SizingModifier:
    return SizingModifier(
        name=name,
        multiplier=multiplier,
        rationale="تقلب داخل النطاق — تخفيض موثق §23.2",
    )


def make_sizing(**overrides: Any) -> SizingResult:
    modifiers = (
        make_sizing_modifier(SizingModifierName.VOLATILITY, 0.9),
        make_sizing_modifier(SizingModifierName.LIQUIDITY, 1.0),
        make_sizing_modifier(SizingModifierName.EXECUTION_QUALITY, 0.95),
        make_sizing_modifier(SizingModifierName.CORRELATION, 1.0),
        make_sizing_modifier(SizingModifierName.DAILY_DRAWDOWN, 0.8),
        make_sizing_modifier(SizingModifierName.SCENARIO_QUALITY, 1.0),
    )
    final_multiplier = 1.0
    for modifier in modifiers:
        final_multiplier *= modifier.multiplier
    kwargs: dict[str, Any] = {
        "risk_budget": 100.0,
        "stop_distance_value": 788.0,
        "base_position_size": 100.0 / 788.0,
        "modifiers": modifiers,
        "final_multiplier": final_multiplier,
        "instrument_cap": 2.0,
        "portfolio_cap_remaining": 5.0,
        "capped_by": SizingCapBasis.NONE,
        "position_size": 100.0 / 788.0 * final_multiplier,
        "resulting_risk_money": 100.0 * final_multiplier,
    }
    kwargs.update(overrides)
    return SizingResult(**kwargs)


def make_cost_breakdown(**overrides: Any) -> CostBreakdown:
    kwargs: dict[str, Any] = {
        "cost_mode": CostMode.REALISTIC,
        "gross_price_edge": 850.0,
        "spread": 12.0,
        "commission": 9.6,
        "slippage": 24.0,
        "funding_financing": 3.2,
        "other_execution_costs": 8.0,
        "net_trading_edge": 850.0 - (12.0 + 9.6 + 24.0 + 3.2 + 8.0),
    }
    kwargs.update(overrides)
    return CostBreakdown(**kwargs)


def make_reward_risk(**overrides: Any) -> RewardRiskEstimate:
    kwargs: dict[str, Any] = {
        "cost_mode": CostMode.REALISTIC,
        "target_level": 60_900.0,
        "entry_reference": 60_050.0,
        "stop_distance": 788.0,
        "gross_target_distance": 850.0,
        "expected_slippage": 24.0,
        "commission_fee": 9.6,
        "spread_cost": 12.0,
        "expected_adverse_selection": 5.0,
        "partial_fill_risk": 3.0,
        "estimated_net_r": (850.0 - 56.8 - 788.0 * 0.0) / 788.0,
        "gross_r": 850.0 / 788.0,
        "breakdown": make_cost_breakdown(),
    }
    kwargs.update(overrides)
    return RewardRiskEstimate(**kwargs)


def make_risk_decision(**overrides: Any) -> RiskDecision:
    """قرار مرفوض نموذجي (أبسط الأشكال القانونية — أساس موثق ونقص مقصود)."""
    kwargs: dict[str, Any] = {
        "decision_id": "rd-0001",
        "scenario_id": "sc-0001",
        "symbol": "BTCUSDT",
        "direction": Direction.LONG,
        "decided_at": _dt(),
        "approved": False,
        "rejection_basis": RejectionBasis.HARD_BLOCK,
        "hard_blocks": (make_no_trade_explanation(),),
        "soft_suppressions": (),
        "soft_total": 0.0,
        "stop": make_stop(),
        "sizing": None,
        "reward_risk": None,
        "order_intent": None,
        "explanation": make_explanation(rejected=True),
        "parameter_fingerprint": "sha256:fixture",
    }
    kwargs.update(overrides)
    return RiskDecision(**kwargs)


def make_explanation(*, rejected: bool = False) -> ExplanationObject:
    """كائن تفسير §2.8 مكتمل — سبب الرفض عند الرفض حصرًا."""
    return ExplanationObject(
        market_context="TREND_PULLBACK، تقلب مئينه 62.4، جودة HEALTHY",
        liquidity_map="منطقة اجتياح بيعية مؤكدة أسفل الدخول (lz-001)",
        structural_state="مجموعة البنية: حاضرة بدليل صافٍ +0.4100",
        supporting_evidence=("LIQUIDITY_SWEEP_LOW [liquidity.detector] c_i=+0.7140",),
        opposing_evidence=("HTF_BEARISH [market_state.htf_bias] c_i=-0.3200",),
        trigger="ZONE_RECLAIM رُصد عند 2026-09-27T02:00:00Z",
        invalidation="59400.0 بعازلة 120.0 بقبول إغلاق (§18.5)",
        expected_path="نحو سيولة شرائية عند 60900.0 (§10.5)",
        cost_estimate="REALISTIC: حافة صافية 793.2 للوحدة بعد تكاليف 56.8 (§25.2)",
        rejection_reason="مفتاح الإيقاف مفعّل (§22.1 رقم 15)" if rejected else None,
    )


def make_experience(**overrides: Any) -> ExperienceRecord:
    kwargs: dict[str, Any] = {
        "market_state_snapshot": make_market_state(),
        "scenario_snapshot": make_scenario(),
        "evidence_snapshot": [make_evidence()],
        "risk_snapshot": make_risk_decision(),
        "execution_snapshot": {
            "basis": "scenario_level_mvp",
            "order_policy": "LIMIT_AT_ZONE",
            "measurement": "planned_entry_market_path",
        },
        "fill_sequence": [],  # لا تعبئات قبل مرحلة التنفيذ (§24 — موثق لا صمت)
        "position_path": [],
        "mfe": 0.0,
        "mae": 0.0,
        "holding_time": 0.0,
        "exit_reason": "REJECTED_BY_RISK: مفتاح الإيقاف مفعّل (§22.1 رقم 15)",
        "gross_pnl": 0.0,
        "costs": 0.0,
        "net_pnl": 0.0,
        "net_r": 0.0,
        "regime": MarketRegime.TREND_PULLBACK,
        "session": SessionType.UTC_DAY,
    }
    kwargs.update(overrides)
    return ExperienceRecord(**kwargs)


def _all_examples() -> list[tuple[str, BaseModel]]:
    return [
        ("EventEnvelope", make_envelope()),
        ("TradeEvent", make_trade_event()),
        ("Candle", make_candle()),
        ("FootprintBar", make_footprint()),
        ("MarketStateSnapshot", make_market_state()),
        ("EvidenceRecord", make_evidence()),
        ("PriceZone", PriceZone(price_low=59_800.0, price_high=60_050.0)),
        ("TriggerDefinition", make_trigger()),
        ("InvalidationRule", make_invalidation()),
        ("TargetZone", TargetZone(price_level=60_900.0, zone_id="lz-high-001")),
        ("Scenario", make_scenario()),
        ("OrderIntent", make_order_intent()),
        ("SlippageRecord", make_slippage()),
        ("LatencyRecord", make_latency()),
        ("MacroEventWindow", make_macro_window()),
        ("EvaluationContext", EvaluationContext()),
        ("NoTradeExplanation", make_no_trade_explanation()),
        ("StructuralStop", make_stop()),
        ("SizingModifier", make_sizing_modifier()),
        ("SizingResult", make_sizing()),
        ("CostBreakdown", make_cost_breakdown()),
        ("RewardRiskEstimate", make_reward_risk()),
        ("RiskDecision", make_risk_decision()),
        ("ExperienceRecord", make_experience()),
    ]


# ─── Round-trip ───


class TestRoundTrip:
    """JSON round-trip لكل نموذج — العقد يبقى مطابقًا لنفسه عبر السلك."""

    @pytest.mark.parametrize(
        ("name", "instance"),
        _all_examples(),
        ids=[name for name, _ in _all_examples()],
    )
    def test_json_round_trip(self, name: str, instance: BaseModel) -> None:
        text = instance.model_dump_json()
        restored = type(instance).model_validate_json(text)
        assert restored == instance, f"round-trip فشل لـ{name}"

    def test_str_enum_serializes_to_plain_value(self) -> None:
        dumped = make_market_state().model_dump()
        assert dumped["regime"] == "TREND_PULLBACK"
        assert dumped["htf_bias"] == "BULLISH"
        assert isinstance(dumped["regime"], str)
        text = make_market_state().model_dump_json()
        assert "TREND_PULLBACK" in text
        assert "BULLISH" in text


# ─── الحدود ───


class TestBoundsRejection:
    """القيم خارج حدود الخطة تُرفض بـValidationError."""

    @pytest.mark.parametrize("bad", [-1.5, -1.0001, 1.0001, 1.5, 2.0])
    def test_direction_score_out_of_range(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            make_evidence(direction_score=bad)

    @pytest.mark.parametrize("bad", [-0.1, -0.0001, 1.0001, 1.1, 2.0])
    def test_unit_fields_out_of_range(self, bad: float) -> None:
        for field in ("raw_strength", "quality", "freshness", "independence_discount"):
            with pytest.raises(ValidationError, match=field):
                make_evidence(**{field: bad})

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 7.5])
    def test_scenario_score_is_unit_interval(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="scenario_score"):
            make_scenario(scenario_score=bad)

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 1.5])
    def test_calibrated_probability_is_unit_interval(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="calibrated_probability"):
            make_scenario(calibrated_probability=bad)

    @pytest.mark.parametrize("bad", [-0.1, 100.1, 101.0, -1.0])
    def test_volatility_percentile_bounded_0_100(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="volatility_percentile"):
            make_market_state(volatility_percentile=bad)

    @pytest.mark.parametrize("bad", [-0.001, 1.001, 1.5])
    def test_footprint_shares_are_unit_intervals(self, bad: float) -> None:
        for field in ("buy_share", "sell_share"):
            with pytest.raises(ValidationError, match=field):
                make_footprint(**{field: bad})

    @pytest.mark.parametrize("bad", [-1, -0.5, 3.5])
    def test_footprint_counts_non_negative(self, bad: int) -> None:
        for field in ("row_count", "buy_imbalance_count", "sell_imbalance_count"):
            with pytest.raises(ValidationError, match=field):
                make_footprint(**{field: bad})

    @pytest.mark.parametrize("bad", [0.0, -60_000.0])
    def test_prices_strictly_positive(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            make_trade_event(price=bad)
        with pytest.raises(ValidationError):
            make_candle(open=bad)

    @pytest.mark.parametrize("bad", [-1.0, -0.001])
    def test_volumes_non_negative(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            make_trade_event(quantity=bad)
        with pytest.raises(ValidationError):
            make_candle(volume=bad)

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_candle_unit_fields(self, bad: float) -> None:
        for field in ("body_fraction", "close_location_value"):
            with pytest.raises(ValidationError, match=field):
                make_candle(**{field: bad})

    @pytest.mark.parametrize("bad", [0.0, -5.0])
    def test_order_intent_positive_budget_and_stop(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            make_order_intent(risk_budget=bad)
        with pytest.raises(ValidationError):
            make_order_intent(stop=bad)

    @pytest.mark.parametrize("bad", [-1.0, -0.01])
    def test_order_intent_non_negative_limits(self, bad: float) -> None:
        for field in ("max_slippage", "max_latency"):
            with pytest.raises(ValidationError, match=field):
                make_order_intent(**{field: bad})

    def test_experience_costs_non_negative(self) -> None:
        with pytest.raises(ValidationError, match="costs"):
            make_experience(costs=-1.0)

    def test_experience_holding_time_non_negative(self) -> None:
        with pytest.raises(ValidationError, match="holding_time"):
            make_experience(holding_time=-0.5)


# ─── عقد الوقت §7.1 ───


class TestTimeContract:
    """الزمن الساذج مرفوض؛ الواعي بطابع غير UTC يطبَّع إلى UTC."""

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="event_time"):
            EventEnvelope(
                event_id=uuid4(),
                schema_version="1.0.0",
                event_type=EventType.CHOCH,
                event_time=datetime(2026, 9, 27, 2, 0),  # ساذج — مرفوض (§7.1)
                receive_time=_dt(second=1),
                source="structure.detector",
                trace_id="t",
                correlation_id=None,
                payload={},
            )

    def test_non_utc_timezone_normalized_to_utc(self) -> None:
        plus3 = timezone(timedelta(hours=3))
        env = EventEnvelope(
            event_id=uuid4(),
            schema_version="1.0.0",
            event_type=EventType.CHOCH,
            event_time=datetime(2026, 9, 27, 5, 0, tzinfo=plus3),  # 05:00+03 == 02:00Z
            receive_time=_dt(second=1),
            source="structure.detector",
            trace_id="t",
            correlation_id=None,
            payload={},
        )
        assert env.event_time.utcoffset() == timedelta(0)
        assert env.event_time == _dt()

    def test_naive_candle_bar_time_rejected(self) -> None:
        data = make_candle().model_dump()
        data["bar_time"] = datetime(2026, 9, 27, 2, 0)
        with pytest.raises(ValidationError):
            Candle.model_validate(data)


# ─── الجمود والحقول الغريبة ───


class TestFrozenAndExtra:
    """كل نموذج مجمّد (لا تعديل) ويمنع الحقول الغريبة (عقد مغلق)."""

    @pytest.mark.parametrize(
        ("name", "instance"),
        _all_examples(),
        ids=[name for name, _ in _all_examples()],
    )
    def test_frozen_rejects_mutation(self, name: str, instance: BaseModel) -> None:
        first_field = next(iter(type(instance).model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(instance, first_field, None)

    @pytest.mark.parametrize(
        ("name", "instance"),
        _all_examples(),
        ids=[name for name, _ in _all_examples()],
    )
    def test_extra_fields_forbidden(self, name: str, instance: BaseModel) -> None:
        data = instance.model_dump()
        poisoned = {**data, "sorcerer_field": 42}
        with pytest.raises(ValidationError, match=r"[Ee]xtra"):
            type(instance).model_validate(poisoned)

    def test_envelope_correlation_id_required_but_nullable(self) -> None:
        env = make_envelope()
        assert env.correlation_id is None
        data = env.model_dump()
        assert "correlation_id" in data  # حقل من التسعة حاضرًا دومًا (§32)


# ─── افتراضات النمذجة الموثقة ───


class TestDerivedAssumptions:
    """الافتراضات الموثقة في docstrings تعمل كما صُممت."""

    def test_scenario_defaults_before_calibration(self) -> None:
        scenario = make_scenario()
        assert scenario.calibrated_probability is None  # §19.6: تعدم قبل المعايرة

    def test_scenario_transition_is_immutable_reasoned_record(self) -> None:
        """سجل الانتقال (§31.3): ملحق-فقط موثق السبب — والفراغ مرفوض."""
        from datetime import timedelta

        record = ScenarioTransition(
            scenario_id="sc-0001",
            from_state=ScenarioState.DRAFT,
            to_state=ScenarioState.ACTIVE,
            transition_time=_dt() + timedelta(minutes=1),
            reason="ترقية §18.4: مجموعتان داعمتان ولا حجب",
        )
        assert record.model_config["frozen"]  # التاريخ لا يُطفَّر
        assert record.model_config["extra"] == "forbid"
        with pytest.raises(ValidationError, match="reason"):
            ScenarioTransition(
                scenario_id="sc-0001",
                from_state=ScenarioState.DRAFT,
                to_state=ScenarioState.ACTIVE,
                transition_time=_dt(),
                reason="   ",  # سبب فارغ بعد التقليم — رفض صاخب
            )

    def test_optional_feed_fields_default_to_none(self) -> None:
        trade = TradeEvent(
            event_time_utc=_dt(),
            receive_time_utc=_dt(second=1),
            source_timeframe="1m",
            venue="BINANCE_USDM",
            symbol="BTCUSDT",
            feed_id="binance.aggTrades",
            price=60_000.0,
            quantity=0.25,
        )
        assert trade.sequence_id is None  # §7.1: «عندما يوفره المصدر»
        assert trade.source_latency_ms is None  # §7.1: «حيث يمكن قياسه»
        assert trade.buyer_is_maker is None  # مصادر بلا علم العدوانية (D-02)

    def test_footprint_optional_rows_default_to_none(self) -> None:
        data = make_footprint().model_dump()
        data["max_positive_delta_row"] = None
        data["max_negative_delta_row"] = None
        bar = FootprintBar.model_validate(data)
        assert bar.max_positive_delta_row is None
        assert bar.max_negative_delta_row is None


# ─── عقود المخاطرة (§22/§23/§25.2 — المرحلة 8) ───


class TestRiskContracts:
    """عقود المرحلة 8: الحدود والمدققات والعقود المتبادلة."""

    def test_evaluation_context_defaults_are_all_healthy(self) -> None:
        """السياق الفارغ = سوق صالح تمامًا — أساس حقن الحواجب المستقل."""
        context = EvaluationContext()
        assert context.data_quality is DataQuality.HEALTHY
        assert context.instrument_tradable
        assert context.venue_healthy
        assert context.kill_switch is False
        assert context.embargo_windows == ()
        assert context.conflicting_scenario_ids == ()
        assert context.positions_open == 0
        assert context.session is SessionType.UTC_DAY

    def test_no_trade_explanation_retry_contract(self) -> None:
        """§22.3: السماح بلا شرط مرفوض، والمنع مع شرط مرفوض."""
        with pytest.raises(ValidationError, match="retry_condition"):
            make_no_trade_explanation(
                whether_retry_is_allowed=True,
                retry_condition=None,
            )
        with pytest.raises(ValidationError, match="retry_condition"):
            make_no_trade_explanation(
                whether_retry_is_allowed=False,
                retry_condition="عودة الجودة إلى HEALTHY",
            )

    def test_no_trade_explanation_requires_triggering_conditions(self) -> None:
        with pytest.raises(ValidationError, match="triggering_conditions"):
            make_no_trade_explanation(triggering_conditions="  ")

    def test_sizing_modifier_never_raises_size(self) -> None:
        """المعدل ∈ (0, 1] — لا رفع للتحجيم أبدًا (بوابة الخروج 8)."""
        with pytest.raises(ValidationError, match="خارج"):
            make_sizing_modifier(multiplier=1.2)
        with pytest.raises(ValidationError, match="خارج"):
            make_sizing_modifier(multiplier=0.0)

    def test_sizing_result_risk_never_exceeds_budget(self) -> None:
        """الخاصية المركزية 8.3: الخطر الناتج ≤ الميزانية — مرفوض بنيويًا."""
        with pytest.raises(ValidationError, match="يتجاوز الميزانية"):
            make_sizing(resulting_risk_money=150.0)

    def test_sizing_result_position_within_caps(self) -> None:
        with pytest.raises(ValidationError, match="سقف الأداة"):
            make_sizing(position_size=3.0)
        with pytest.raises(ValidationError, match="سعة المحفظة"):
            make_sizing(position_size=6.0, instrument_cap=10.0)

    def test_cost_breakdown_decomposition_identity(self) -> None:
        """§25.2: الصافي = الإجمالي − المكونات الخمسة — محقاة إلزامية."""
        with pytest.raises(ValidationError, match="غير متطابق"):
            make_cost_breakdown(net_trading_edge=999.0)
        breakdown = make_cost_breakdown()
        total = (
            breakdown.spread
            + breakdown.commission
            + breakdown.slippage
            + breakdown.funding_financing
            + breakdown.other_execution_costs
        )
        assert abs(breakdown.net_trading_edge - (breakdown.gross_price_edge - total)) < 1e-9

    def test_reward_risk_components_match_breakdown(self) -> None:
        """مكونات §23.5 = تحلل §25.2 — حساب واحد لا حسابان."""
        mismatched = make_cost_breakdown(
            spread=50.0,
            net_trading_edge=850.0 - (50.0 + 9.6 + 24.0 + 3.2 + 8.0),
        )
        with pytest.raises(ValidationError, match="لا تطابق تحلل"):
            make_reward_risk(breakdown=mismatched)

    def test_risk_decision_approved_requires_completeness(self) -> None:
        """الترخيص اكتمال: كل الأجزاء حاضرة ولا حواجب ولا أساس رفض."""
        with pytest.raises(ValidationError, match="ناقص الأجزاء"):
            make_risk_decision(
                approved=True,
                rejection_basis=None,
                hard_blocks=(),
                sizing=None,  # جزء غائب — الترخيص ناقص
                reward_risk=make_reward_risk(),
                order_intent=make_order_intent(),
                explanation=make_explanation(rejected=False),
            )
        complete = make_risk_decision(
            approved=True,
            rejection_basis=None,
            hard_blocks=(),
            sizing=make_sizing(),
            reward_risk=make_reward_risk(),
            order_intent=make_order_intent(),
            explanation=make_explanation(rejected=False),
        )
        assert complete.approved

    def test_risk_decision_rejected_requires_basis_and_no_intent(self) -> None:
        with pytest.raises(ValidationError, match="بلا أساس"):
            make_risk_decision(rejection_basis=None)
        with pytest.raises(ValidationError, match="نية أمر"):
            make_risk_decision(order_intent=make_order_intent())

    def test_macro_window_high_impact_and_blocks(self) -> None:
        """§17.3: HIGH وحده عالي الأثر والنافذة مغلقة الطرفين."""
        window = make_macro_window()
        assert window.high_impact
        assert window.blocks(_dt(minute=20))  # داخل نافذة ما قبل الحدث
        assert not window.blocks(_dt(minute=50))  # بعد انقضاء النافذة
        low = make_macro_window(importance="MEDIUM")
        assert not low.high_impact
        assert not low.blocks(_dt(minute=20))  # غير عالي الأثر لا يحجب أبدًا

    def test_experience_record_risk_snapshot_is_typed(self) -> None:
        """شد المرحلة 8: risk_snapshot قرار مخاطرة نموذجي لا dict خام."""
        record = make_experience()
        assert isinstance(record.risk_snapshot, RiskDecision)
        assert not record.risk_snapshot.approved
