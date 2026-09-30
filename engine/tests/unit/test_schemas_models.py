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
    EventEnvelope,
    EvidenceRecord,
    ExperienceRecord,
    FootprintBar,
    InvalidationRule,
    LatencyRecord,
    MarketRegime,
    MarketStateSnapshot,
    OrderIntent,
    PriceZone,
    Scenario,
    SessionType,
    SlippageRecord,
    TargetZone,
    TradeEvent,
    TriggerDefinition,
)
from schemas.enums import DataQuality, Direction, EventType, EvidenceGroup, ScenarioState

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


def make_experience(**overrides: Any) -> ExperienceRecord:
    kwargs: dict[str, Any] = {
        "market_state_snapshot": make_market_state(),
        "scenario_snapshot": make_scenario(),
        "evidence_snapshot": [make_evidence()],
        "risk_snapshot": {"risk_budget": 100.0, "stop_distance_value": 720.0},
        "execution_snapshot": {"order_policy": "LIMIT_AT_ZONE"},
        "fill_sequence": [{"price": 60_008.5, "quantity": 0.138, "buyer_is_maker": False}],
        "position_path": [
            {"time": "2026-09-27T02:05:00Z", "quantity": 0.138, "avg_price": 60_008.5},
        ],
        "mfe": 1.21,  # بمضاعفات R من مسار الدخول الفعلي (§29.2)
        "mae": 0.34,
        "holding_time": 2_760.0,  # ثوانٍ
        "exit_reason": "target_hit",
        "gross_pnl": 121.0,
        "costs": 8.5,
        "net_pnl": 112.5,
        "net_r": 1.125,
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
