"""اختبارات خصائص الحدود — hypothesis داخل الحدود يبني وخارجها يُرفض.

تولد قيمًا داخل النطاقات المعلنة (§19.1 ونحوها) فتبنى النماذج وتعيد
round-trip متطابقًا؛ وقيمًا خارجها فترفض بـValidationError.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from pydantic import ValidationError
from schemas import (
    Candle,
    Direction,
    EventEnvelope,
    EvidenceRecord,
    FootprintBar,
    InvalidationRule,
    MarketRegime,
    MarketStateSnapshot,
    PriceZone,
    Scenario,
    ScenarioState,
    TargetZone,
    TriggerDefinition,
)
from schemas.enums import DataQuality, EventType, EvidenceGroup, HTFBias

UTC = UTC

# ─── استراتيجيات الحدود ───

unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
signed_unit = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)
positive = st.floats(min_value=1e-9, max_value=1e9, allow_nan=False, allow_infinity=False)
non_negative = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)
percentile = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
non_negative_int = st.integers(min_value=0, max_value=10_000)

above_one = st.floats(min_value=1.0000001, max_value=1e6, allow_nan=False, allow_infinity=False)
below_zero = st.floats(min_value=-1e6, max_value=-0.0000001, allow_nan=False, allow_infinity=False)
below_minus_one = st.floats(
    min_value=-1e6, max_value=-1.0000001, allow_nan=False, allow_infinity=False
)
above_hundred = st.floats(min_value=100.0001, max_value=1e6, allow_nan=False, allow_infinity=False)
beyond_signed = st.one_of(above_one, below_minus_one)
non_positive = st.one_of(
    st.just(0.0),
    st.floats(min_value=-1e6, max_value=-1e-9, allow_nan=False, allow_infinity=False),
)

_offsets = st.sampled_from(
    [
        UTC,
        timezone(timedelta(hours=3)),
        timezone(timedelta(hours=-7)),
        timezone(timedelta(minutes=30)),
    ]
)
_aware_datetimes = st.builds(
    lambda naive, tz: naive.replace(tzinfo=tz),
    st.datetimes(min_value=datetime(1970, 1, 1), max_value=datetime(2099, 12, 31)),
    _offsets,
)

EVENT_TYPES = st.sampled_from(list(EventType))
EVIDENCE_GROUPS = st.sampled_from(list(EvidenceGroup))


# ─── مساعدات بناء kwargs ───


def _evidence_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "evidence_id": "ev-prop",
        "group": EvidenceGroup.ORDER_FLOW,
        "event_type": EventType.ABSORPTION_BUY,
        "direction_score": 0.5,
        "raw_strength": 0.5,
        "quality": 0.5,
        "freshness": 0.5,
        "independence_discount": 0.5,
        "prior_weight": 0.9,
        "context_modifier": 1.0,
        "opposition": False,
        "source": "prop.test",
        "correlation_group_id": None,
    }
    kwargs.update(overrides)
    return kwargs


def _candle_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "instrument_id": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
        "session_id": "s",
        "quality": DataQuality.HEALTHY,
        "is_closed": True,
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 10.0,
        "range": 15.0,
        "body_size": 5.0,
        "upper_wick": 5.0,
        "lower_wick": 5.0,
        "body_fraction": 0.33,
        "close_location_value": 0.66,
        "true_range": 15.0,
        "realized_volatility": 0.01,
    }
    kwargs.update(overrides)
    return kwargs


def _footprint_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "instrument_id": "BINANCE_USDM:BTCUSDT",
        "timeframe": "1m",
        "bar_time": datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
        "quality": DataQuality.HEALTHY,
        "is_closed": True,
        "source_feed": "binance.aggTrades",
        "methodology": "buyer_is_maker v1",
        "buy_volume": 60.0,
        "sell_volume": 40.0,
        "total_volume": 100.0,
        "delta": 20.0,
        "buy_share": 0.6,
        "sell_share": 0.4,
        "poc": 105.0,
        "vah": 108.0,
        "val": 102.0,
        "row_count": 7,
        "buy_imbalance_count": 1,
        "sell_imbalance_count": 0,
    }
    kwargs.update(overrides)
    return kwargs


def _scenario_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "scenario_id": "sc-prop",
        "symbol": "BTCUSDT",
        "direction": Direction.LONG,
        "regime": MarketRegime.COMPRESSION,
        "context_snapshot": MarketStateSnapshot(
            instrument="BTCUSDT",
            timeframe="15m",
            event_time=datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
            regime=MarketRegime.COMPRESSION,
            htf_bias=HTFBias.NEUTRAL,
            volatility_percentile=50.0,
            data_quality=DataQuality.HEALTHY,
        ),
        "location_snapshot": {"zone_ids": ["lz-1"]},
        "thesis": "فرضية اختبار",
        "supporting_evidence": ["ev-1"],
        "opposing_evidence": [],
        "trigger_definition": TriggerDefinition(
            condition_type="ZONE_RECLAIM", params={"zone_id": "lz-1"}
        ),
        "entry_zone": PriceZone(price_low=99.0, price_high=101.0),
        "invalidation": InvalidationRule(
            structural_level=95.0, volatility_buffer=2.0, accept_through=True
        ),
        "primary_targets": [TargetZone(price_level=110.0, zone_id="lz-2")],
        "secondary_targets": [],
        "expiry_time": datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
        "state": ScenarioState.DRAFT,
        "scenario_score": 0.5,
        "calibrated_probability": None,
    }
    kwargs.update(overrides)
    return kwargs


# ─── سجل الدليل (§19.1) ───


class TestEvidenceBounds:
    """حدود §19.1 حرفيًا: داخل النطاق يبني، خارجه يُرفض."""

    @given(
        direction_score=signed_unit,
        raw_strength=unit,
        quality=unit,
        freshness=unit,
        independence_discount=unit,
        prior_weight=finite,
        context_modifier=finite,
        group=EVIDENCE_GROUPS,
        event_type=EVENT_TYPES,
    )
    @hyp_settings(max_examples=75)
    def test_in_bounds_builds_and_round_trips(
        self,
        direction_score: float,
        raw_strength: float,
        quality: float,
        freshness: float,
        independence_discount: float,
        prior_weight: float,
        context_modifier: float,
        group: EvidenceGroup,
        event_type: EventType,
    ) -> None:
        record = EvidenceRecord(
            **_evidence_kwargs(
                direction_score=direction_score,
                raw_strength=raw_strength,
                quality=quality,
                freshness=freshness,
                independence_discount=independence_discount,
                prior_weight=prior_weight,
                context_modifier=context_modifier,
                group=group,
                event_type=event_type,
            )
        )
        restored = EvidenceRecord.model_validate_json(record.model_dump_json())
        assert restored == record

    @given(
        field=st.sampled_from(["raw_strength", "quality", "freshness", "independence_discount"]),
        bad=above_one,
    )
    @hyp_settings(max_examples=50)
    def test_unit_field_above_one_rejected(self, field: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            EvidenceRecord(**_evidence_kwargs(**{field: bad}))

    @given(
        field=st.sampled_from(["raw_strength", "quality", "freshness", "independence_discount"]),
        bad=below_zero,
    )
    @hyp_settings(max_examples=50)
    def test_unit_field_below_zero_rejected(self, field: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            EvidenceRecord(**_evidence_kwargs(**{field: bad}))

    @given(bad=beyond_signed)
    @hyp_settings(max_examples=50)
    def test_direction_score_beyond_signed_unit_rejected(self, bad: float) -> None:
        # داخل [-1, +1] كل شيء مباح؛ الخارج عن النطاق مرفوض — -1.0 و+1.0 حلال
        assert bad < -1.0 or bad > 1.0
        with pytest.raises(ValidationError):
            EvidenceRecord(**_evidence_kwargs(direction_score=bad))


# ─── الشمعة والفوتبرنت ولقطة الحالة (§8.1/§8.2/§32) ───


class TestMarketBounds:
    """أسعار موجبة وكميات غير سالبة ونسب [0,1] ومئينات [0,100]."""

    @given(
        open_=positive,
        high=positive,
        low=positive,
        close=positive,
        volume=non_negative,
        bar_range=non_negative,
        body_fraction=unit,
        close_location=unit,
    )
    @hyp_settings(max_examples=50)
    def test_candle_in_bounds_builds(
        self,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        bar_range: float,
        body_fraction: float,
        close_location: float,
    ) -> None:
        candle = Candle(
            **_candle_kwargs(
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                range=bar_range,
                body_fraction=body_fraction,
                close_location_value=close_location,
            )
        )
        restored = Candle.model_validate_json(candle.model_dump_json())
        assert restored == candle

    @given(field=st.sampled_from(["body_fraction", "close_location_value"]), bad=above_one)
    @hyp_settings(max_examples=40)
    def test_candle_unit_field_above_one_rejected(self, field: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_candle_kwargs(**{field: bad}))

    @given(bad=non_positive)
    @hyp_settings(max_examples=40)
    def test_candle_non_positive_price_rejected(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            Candle.model_validate(_candle_kwargs(open=bad))

    @given(buy_share=unit, sell_share=unit, rows=non_negative_int, delta=finite)
    @hyp_settings(max_examples=50)
    def test_footprint_in_bounds_builds(
        self, buy_share: float, sell_share: float, rows: int, delta: float
    ) -> None:
        bar = FootprintBar(
            **_footprint_kwargs(
                buy_share=buy_share, sell_share=sell_share, row_count=rows, delta=delta
            )
        )
        restored = FootprintBar.model_validate_json(bar.model_dump_json())
        assert restored == bar

    @given(field=st.sampled_from(["buy_share", "sell_share"]), bad=above_one)
    @hyp_settings(max_examples=40)
    def test_footprint_share_above_one_rejected(self, field: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            FootprintBar(**_footprint_kwargs(**{field: bad}))

    @given(vol=percentile)
    @hyp_settings(max_examples=40)
    def test_volatility_percentile_in_bounds_builds(self, vol: float) -> None:
        snapshot = MarketStateSnapshot(
            instrument="BTCUSDT",
            timeframe="15m",
            event_time=datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
            regime=MarketRegime.RANGE_BALANCE,
            htf_bias=HTFBias.NEUTRAL,
            volatility_percentile=vol,
            data_quality=DataQuality.HEALTHY,
        )
        assert 0.0 <= snapshot.volatility_percentile <= 100.0

    @given(bad=st.one_of(below_zero, above_hundred))
    @hyp_settings(max_examples=40)
    def test_volatility_percentile_out_of_bounds_rejected(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            MarketStateSnapshot(
                instrument="BTCUSDT",
                timeframe="15m",
                event_time=datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
                regime=MarketRegime.RANGE_BALANCE,
                htf_bias=HTFBias.NEUTRAL,
                volatility_percentile=bad,
                data_quality=DataQuality.HEALTHY,
            )


# ─── السيناريو (§18.1/§2.6) ───


class TestScenarioBounds:
    """الدرجة الخام والاحتمال المعاير كلاهما نطاق [0,1]."""

    @given(score=unit)
    @hyp_settings(max_examples=40)
    def test_scenario_score_in_bounds_builds(self, score: float) -> None:
        scenario = Scenario.model_validate(_scenario_kwargs(scenario_score=score))
        assert scenario.scenario_score == score

    @given(bad=st.one_of(below_zero, above_one))
    @hyp_settings(max_examples=40)
    def test_scenario_score_out_of_bounds_rejected(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            Scenario.model_validate(_scenario_kwargs(scenario_score=bad))

    @given(bad=st.one_of(below_zero, above_one))
    @hyp_settings(max_examples=40)
    def test_calibrated_probability_out_of_bounds_rejected(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            Scenario.model_validate(_scenario_kwargs(calibrated_probability=bad))


# ─── عقد الوقت (§7.1) ───


class TestTimeContractProperty:
    """أي زمن واعٍ يخزن UTC بنفس اللحظة؛ الساذج يُرفض دائمًا."""

    @given(when=_aware_datetimes)
    @hyp_settings(max_examples=60)
    def test_aware_datetimes_normalized_to_utc(self, when: datetime) -> None:
        env = EventEnvelope(
            event_id=uuid4(),
            schema_version="1.0.0",
            event_type=EventType.CHOCH,
            event_time=when,
            receive_time=when,
            source="prop.test",
            trace_id="t",
            correlation_id=None,
            payload={},
        )
        assert env.event_time.utcoffset() == timedelta(0)
        assert abs(env.event_time.timestamp() - when.timestamp()) < 1e-6
        restored = EventEnvelope.model_validate_json(env.model_dump_json())
        assert restored == env

    @given(when=st.datetimes(min_value=datetime(1970, 1, 1), max_value=datetime(2099, 12, 31)))
    @hyp_settings(max_examples=40)
    def test_naive_datetimes_always_rejected(self, when: datetime) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope(
                event_id=uuid4(),
                schema_version="1.0.0",
                event_type=EventType.CHOCH,
                event_time=when,  # ساذج — مرفوض (§7.1)
                receive_time=when,
                source="prop.test",
                trace_id="t",
                correlation_id=None,
                payload={},
            )
