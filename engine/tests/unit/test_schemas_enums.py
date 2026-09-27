"""اختبارات التعدادات — مطابقة حرفية لقيم Master Plan.

كل قائمة مرجعية أدناه منسوخة من نص الخطة نفسه (وليس من الشيفرة) لتكون
ثابتة مرجعية مستقلة: §7.4، §27.1، §9.2، §9.3، §19.3، §20، §18.2، §24.2،
§10.4، §22.1، وA-03 (للجلسات).
"""

from __future__ import annotations

from enum import StrEnum

import pytest
from schemas.enums import (
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_GROUP_SHARES,
    DataQuality,
    Direction,
    EventType,
    EvidenceGroup,
    HardBlockReason,
    HTFBias,
    MarketRegime,
    OrderPolicy,
    ScenarioState,
    SessionType,
    SignalState,
    SweepClassification,
)

# ─── الثوابت المرجعية (منسوخة من نص الخطة) ───

# §7.4 — حالات جودة البيانات التسع
PLAN_DATA_QUALITY = [
    "HEALTHY",
    "DELAYED",
    "PARTIAL",
    "DUPLICATED",
    "OUT_OF_ORDER",
    "STALE",
    "GAP_DETECTED",
    "UNAVAILABLE",
    "QUARANTINED",
]

# §27.1 — حالات الإشارة الأربع
PLAN_SIGNAL_STATES = ["DEVELOPING", "CONFIRMED", "INVALIDATED", "RETRACTED"]

# الاتجاه المثالث
PLAN_DIRECTIONS = ["LONG", "SHORT", "FLAT"]

# §9.2 — انحياز HTF
PLAN_HTF_BIAS = ["BULLISH", "BEARISH", "NEUTRAL", "TRANSITION", "UNKNOWN"]

# §9.3 — نظام السوق
PLAN_MARKET_REGIMES = [
    "TREND_EXPANSION",
    "TREND_PULLBACK",
    "RANGE_BALANCE",
    "RANGE_EXPANSION",
    "COMPRESSION",
    "VOLATILITY_SHOCK",
    "TRANSITION",
    "UNKNOWN",
]

# §9.4 + A-03 — الجلسة = يوم UTC + آسيا/أوروبا/أمريكا اختياريًا + صيانة
PLAN_SESSION_TYPES = ["UTC_DAY", "ASIA", "EUROPE", "AMERICA", "MAINTENANCE"]

# §19.3 — مجموعات الدليل الست
PLAN_EVIDENCE_GROUPS = [
    "STRUCTURE",
    "LIQUIDITY_LOCATION",
    "ORDER_FLOW",
    "PRICE_ACTION",
    "VOLATILITY_SESSION",
    "MACRO",
]

# §20 — قاموس الأحداث كاملًا (45 نوعًا بترتيب القاموس)
PLAN_EVENT_TYPES = [
    "HTF_BULLISH",
    "HTF_BEARISH",
    "INTERNAL_BOS",
    "EXTERNAL_BOS",
    "CHOCH",
    "DISPLACEMENT_UP",
    "DISPLACEMENT_DOWN",
    "LIQUIDITY_SWEEP_HIGH",
    "LIQUIDITY_SWEEP_LOW",
    "BREAK_AND_ACCEPT_HIGH",
    "BREAK_AND_ACCEPT_LOW",
    "ABSORPTION_BUY",
    "ABSORPTION_SELL",
    "FLOW_CONTINUATION_UP",
    "FLOW_CONTINUATION_DOWN",
    "EXHAUSTION_UP",
    "EXHAUSTION_DOWN",
    "FVG_BULLISH",
    "FVG_BEARISH",
    "ORDER_BLOCK_BULLISH",
    "ORDER_BLOCK_BEARISH",
    "PREMIUM_LOCATION",
    "DISCOUNT_LOCATION",
    "POC_ACCEPTANCE",
    "POC_REJECTION",
    "VAH_REJECTION",
    "VAL_REJECTION",
    "BUY_IMBALANCE_CLUSTER",
    "SELL_IMBALANCE_CLUSTER",
    "BULLISH_ENGULFING",
    "BEARISH_ENGULFING",
    "REJECTION_CANDLE",
    "INSIDE_BAR_BREAK",
    "CLASSICAL_BREAKOUT",
    "CLASSICAL_FAILED_BREAKOUT",
    "HARMONIC_COMPLETION",
    "RANGE_COMPRESSION",
    "RANGE_EXPANSION",
    "SESSION_OPENING_DRIVE",
    "SESSION_REVERSAL",
    "MACRO_HIGH_IMPACT_NEAR",
    "DATA_STALE",
    "SPREAD_EXTREME",
    "LATENCY_EXTREME",
    "RISK_LIMIT_REACHED",
]

# §18.2 — دورة حياة السيناريو: السبعة الأساسية ثم النهايات الخمس البديلة
PLAN_SCENARIO_STATES = [
    "DRAFT",
    "ACTIVE",
    "TRIGGERED",
    "AUTHORIZED",
    "EXECUTING",
    "IN_TRADE",
    "COMPLETED",
    "INVALIDATED",
    "EXPIRED",
    "SUPPRESSED",
    "REJECTED_BY_RISK",
    "CANCELLED_BY_DATA_QUALITY",
]

# §24.2 — سياسات التنفيذ الخمس
PLAN_ORDER_POLICIES = [
    "MARKET_WITH_SLIPPAGE_GUARD",
    "LIMIT_AT_ZONE",
    "STAGED_LIMIT_MARKET",
    "REDUCE_ONLY_EXIT",
    "EMERGENCY_FLATTEN",
]

# §10.4 — تصنيف الاجتياح
PLAN_SWEEP_CLASSIFICATIONS = [
    "FAILED_SWEEP",
    "PARTIAL_SWEEP",
    "CONFIRMED_SWEEP",
    "BREAK_AND_ACCEPT",
    "UNKNOWN",
]

# §22.1 — الحجب الصلب الخمسة عشر (النص إنجليزي وصياغة الأسماء بترتيب البنود)
PLAN_HARD_BLOCK_REASONS = [
    "DATA_UNRELIABLE",
    "INSTRUMENT_UNAVAILABLE",
    "VENUE_CONNECTION_UNHEALTHY",
    "SPREAD_EXCEEDS_BUDGET",
    "SLIPPAGE_EXCEEDS_BUDGET",
    "LATENCY_EXCEEDS_BUDGET",
    "RISK_LIMITS_REACHED",
    "STOP_NOT_RELIABLE",
    "BROKER_REJECTS_ORDER",
    "MACRO_EMBARGO_WINDOW",
    "SCENARIO_INVALIDATED",
    "ENTRY_TOO_LATE",
    "CONFLICTING_SCENARIO",
    "SCENARIO_ALREADY_CONSUMED",
    "KILL_SWITCH",
]

ENUM_REFERENCE: list[tuple[type[StrEnum], list[str]]] = [
    (DataQuality, PLAN_DATA_QUALITY),
    (SignalState, PLAN_SIGNAL_STATES),
    (Direction, PLAN_DIRECTIONS),
    (HTFBias, PLAN_HTF_BIAS),
    (MarketRegime, PLAN_MARKET_REGIMES),
    (SessionType, PLAN_SESSION_TYPES),
    (EvidenceGroup, PLAN_EVIDENCE_GROUPS),
    (EventType, PLAN_EVENT_TYPES),
    (ScenarioState, PLAN_SCENARIO_STATES),
    (OrderPolicy, PLAN_ORDER_POLICIES),
    (SweepClassification, PLAN_SWEEP_CLASSIFICATIONS),
    (HardBlockReason, PLAN_HARD_BLOCK_REASONS),
]


class TestEnumValuesMatchPlan:
    """كل تعدادة تطابق قيم الخطة حرفيًا — نفس القيم وبنفس الترتيب."""

    @pytest.mark.parametrize(
        ("enum_cls", "expected"),
        ENUM_REFERENCE,
        ids=[cls.__name__ for cls, _ in ENUM_REFERENCE],
    )
    def test_values_match_plan_verbatim(self, enum_cls: type[StrEnum], expected: list[str]) -> None:
        values = [member.value for member in enum_cls]
        assert values == expected

    @pytest.mark.parametrize(
        ("enum_cls", "expected"),
        ENUM_REFERENCE,
        ids=[cls.__name__ for cls, _ in ENUM_REFERENCE],
    )
    def test_values_unique(self, enum_cls: type[StrEnum], expected: list[str]) -> None:
        assert len(expected) == len(set(expected))

    @pytest.mark.parametrize(
        ("enum_cls", "expected"),
        ENUM_REFERENCE,
        ids=[cls.__name__ for cls, _ in ENUM_REFERENCE],
    )
    def test_is_str_enum(self, enum_cls: type[StrEnum], expected: list[str]) -> None:
        assert issubclass(enum_cls, StrEnum)
        assert issubclass(enum_cls, str)
        for member in enum_cls:
            assert isinstance(member, str)
            assert member.value == member  # قيمة العضو == نصه (UPPERCASE)


class TestPlanCounts:
    """تثبيت الأعداد المذكورة صراحة في الخطة."""

    def test_data_quality_nine_states(self) -> None:
        assert len(list(DataQuality)) == 9  # §7.4

    def test_hard_block_fifteen_reasons(self) -> None:
        assert len(list(HardBlockReason)) == 15  # §22.1

    def test_event_type_dictionary_complete(self) -> None:
        assert len(list(EventType)) == 45  # قاموس §20 كاملًا

    def test_scenario_states_lifecycle(self) -> None:
        assert len(list(ScenarioState)) == 12  # §18.2: سبعة أساسية + خمسة بديلة


class TestPlanNumericConstants:
    """الثوابت الرقمية منقولة حرفيًا: حصص §19.3 وأوزان §20."""

    def test_default_group_shares_verbatim(self) -> None:
        # §19.3 حرفيًا: 25/20/30/10/10/5 — تبدأ كأولويات لا كحقائق دائمة
        assert DEFAULT_GROUP_SHARES == {
            EvidenceGroup.STRUCTURE: 0.25,
            EvidenceGroup.LIQUIDITY_LOCATION: 0.20,
            EvidenceGroup.ORDER_FLOW: 0.30,
            EvidenceGroup.PRICE_ACTION: 0.10,
            EvidenceGroup.VOLATILITY_SESSION: 0.10,
            EvidenceGroup.MACRO: 0.05,
        }

    def test_default_group_shares_cover_all_and_sum_to_one(self) -> None:
        assert set(DEFAULT_GROUP_SHARES) == set(EvidenceGroup)
        assert sum(DEFAULT_GROUP_SHARES.values()) == pytest.approx(1.0)

    def test_default_event_weights_verbatim(self) -> None:
        # عمود Weight في §20 حرفيًا — None للحجب الصلب (ليس دليلًا اتجاهيًا)
        assert DEFAULT_EVENT_WEIGHTS == {
            EventType.HTF_BULLISH: 0.90,
            EventType.HTF_BEARISH: 0.90,
            EventType.INTERNAL_BOS: 0.80,
            EventType.EXTERNAL_BOS: 1.00,
            EventType.CHOCH: 0.75,
            EventType.DISPLACEMENT_UP: 0.90,
            EventType.DISPLACEMENT_DOWN: 0.90,
            EventType.LIQUIDITY_SWEEP_HIGH: 0.95,
            EventType.LIQUIDITY_SWEEP_LOW: 0.95,
            EventType.BREAK_AND_ACCEPT_HIGH: 0.85,
            EventType.BREAK_AND_ACCEPT_LOW: 0.85,
            EventType.ABSORPTION_BUY: 0.90,
            EventType.ABSORPTION_SELL: 0.90,
            EventType.FLOW_CONTINUATION_UP: 0.70,
            EventType.FLOW_CONTINUATION_DOWN: 0.70,
            EventType.EXHAUSTION_UP: 0.65,
            EventType.EXHAUSTION_DOWN: 0.65,
            EventType.FVG_BULLISH: 0.55,
            EventType.FVG_BEARISH: 0.55,
            EventType.ORDER_BLOCK_BULLISH: 0.65,
            EventType.ORDER_BLOCK_BEARISH: 0.65,
            EventType.PREMIUM_LOCATION: 0.35,
            EventType.DISCOUNT_LOCATION: 0.35,
            EventType.POC_ACCEPTANCE: 0.45,
            EventType.POC_REJECTION: 0.45,
            EventType.VAH_REJECTION: 0.40,
            EventType.VAL_REJECTION: 0.40,
            EventType.BUY_IMBALANCE_CLUSTER: 0.55,
            EventType.SELL_IMBALANCE_CLUSTER: 0.55,
            EventType.BULLISH_ENGULFING: 0.35,
            EventType.BEARISH_ENGULFING: 0.35,
            EventType.REJECTION_CANDLE: 0.30,
            EventType.INSIDE_BAR_BREAK: 0.35,
            EventType.CLASSICAL_BREAKOUT: 0.45,
            EventType.CLASSICAL_FAILED_BREAKOUT: 0.60,
            EventType.HARMONIC_COMPLETION: 0.45,
            EventType.RANGE_COMPRESSION: 0.45,
            EventType.RANGE_EXPANSION: 0.55,
            EventType.SESSION_OPENING_DRIVE: 0.45,
            EventType.SESSION_REVERSAL: 0.45,
            EventType.MACRO_HIGH_IMPACT_NEAR: 0.00,
            EventType.DATA_STALE: None,
            EventType.SPREAD_EXTREME: None,
            EventType.LATENCY_EXTREME: None,
            EventType.RISK_LIMIT_REACHED: None,
        }

    def test_default_event_weights_cover_all_events(self) -> None:
        assert set(DEFAULT_EVENT_WEIGHTS) == set(EventType)

    def test_hard_block_events_carry_no_directional_weight(self) -> None:
        for event in (
            EventType.DATA_STALE,
            EventType.SPREAD_EXTREME,
            EventType.LATENCY_EXTREME,
            EventType.RISK_LIMIT_REACHED,
        ):
            assert DEFAULT_EVENT_WEIGHTS[event] is None
