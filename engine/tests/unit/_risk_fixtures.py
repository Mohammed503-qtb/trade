"""مساعدات مشتركة لاختبارات المخاطرة (المرحلة 8) — سيناريو TRIGGERED
حقيقي من مُقترِح المرحلة 7 (D-04) بلقطة دمج حية وشريعة قرار.

نمط ``_scenario_fixtures``: كل قيمة قابلة للحساب اليدوي وكل حقل قابل
للتجاوز — فروق الاختبارات من التغيير المقصود وحده. السيناريو المرجعي:
انعكاس صاعد من اجتياح منطقة بيعية [59_800, 59_900] بهدف أساسي عند
المنطقة الشرائية الأقرب (خريطة §10.5).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from _scenario_fixtures import (
    ANCHOR_TIME as ANCHOR_TIME,
)
from _scenario_fixtures import (
    ATR as ATR,
)
from _scenario_fixtures import (
    make_candle as make_candle,
)
from _scenario_fixtures import (
    make_market_state as make_market_state,
)
from _scenario_fixtures import (
    make_sweep_payload as make_sweep_payload,
)
from _scenario_fixtures import (
    make_target_map as make_target_map,
)
from _scenario_fixtures import (
    sell_zone as sell_zone,
)
from fusion.compute import FusionEngine
from fusion.ledger import EvidenceLedgerBuilder
from liquidity.targets import TargetMap
from scenarios.proposer import AnchorEvent, ScenarioProposer
from schemas import (
    Candle,
    DataQuality,
    EvaluationContext,
    EventType,
    EvidenceRecord,
    FusionSnapshot,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
)

__all__ = [
    "DECISION_TIME",
    "decision_candle",
    "fusion_snapshot_for",
    "healthy_context",
    "risk_target_map",
    "triggered_scenario",
]


#: لحظة القرار — شريط واحد بعد المرسِم (زمن شمعة مشغل افتراضي).
DECISION_TIME = ANCHOR_TIME + timedelta(minutes=1)


def risk_target_map() -> TargetMap:
    """خريطة أهداف مرجعية للمخاطرة — الهدف الأول أبعد (R ≈ 2.2).

    خريطة السيناريوهات الافتراضية تضع الهدف الأقرب عند 60_500 حيث
    R الإجمالية ≈ 1.498 — حدية قاتلة للاختبارات (فوق وتحت 1.5 تحرسا)؛
    هنا هدف أول عند 60_800 يبعد المرجع عن الحد بوضوح.
    """
    return make_target_map(
        above=(
            ("lz-buy-001", 60_800.0, 60_900.0, 2.2, 0.9),
            ("lz-buy-002", 61_400.0, 61_500.0, 3.4, 0.7),
        ),
        below=(
            ("lz-sell-002", 59_400.0, 59_500.0, 0.8, 0.8),
            ("lz-sell-003", 59_000.0, 59_100.0, 1.9, 0.6),
        ),
    )


def triggered_scenario(*, template: ScenarioTemplate = ScenarioTemplate.REVERSAL) -> Scenario:
    """سيناريو TRIGGERED حقيقي — مقترح D-04 مُرقّى إلى مشتعل.

    الترقية نسخ حالة صرفة (``model_copy``): بناء المسار الكامل مسؤولية
    اختبارات محرك المرحلة 7 — هنا الهندسة نفسها من المُقترِح الحقيقي.
    """
    proposer = ScenarioProposer()
    outcome = proposer.propose(
        AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
        zone=sell_zone(),
        targets=risk_target_map(),
        state=make_market_state(),
        atr=ATR,
    )
    for proposal in outcome.proposals:
        if proposal.template is template:
            return proposal.model_copy(update={"state": ScenarioState.TRIGGERED})
    raise AssertionError(f"قالب {template} غائب عن مقترحات المرسِم المرجعي")


def fusion_snapshot_for(
    scenario: Scenario, *, anchor_time: datetime = ANCHOR_TIME
) -> tuple[FusionSnapshot, list[EvidenceRecord]]:
    """لقطة دمج حية لسيناريو — سجل الولادة من المرسِم نفسه (§33.4)."""
    event = AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, anchor_time, make_sweep_payload())
    ledger = EvidenceLedgerBuilder()
    records = ledger.build(
        [event],
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        as_of=DECISION_TIME,
        market_state=make_market_state(),
    )
    snapshot = FusionEngine().compute(
        records,
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        fusion_time=DECISION_TIME,
    )
    return snapshot, list(records)


def decision_candle(*, close: float = 59_880.0, bar_time: datetime = DECISION_TIME) -> Candle:
    """شمعة القرار — إغلاق داخل منطقة الدخول (انجراف صفري تقريبًا).

    الدقيقة رقم 1 بعد المرسِم (= لحظة القرار) بقيم متماسكة حول الإغلاق.
    """
    index = round((bar_time - ANCHOR_TIME).total_seconds() / 60.0)
    return make_candle(
        int(index),
        open_=close - 10.0,
        high=close + 30.0,
        low=close - 20.0,
        close=close,
    )


def healthy_context(**overrides: object) -> EvaluationContext:
    """سياق تقييم سليم تمامًا — أساس حقن الحقائق الفردية.

    القيم الواقعية (لا الأصفار المثالية): فاتحة/انزلاق/كمون مقدَّرة
    من نمط التكلفة الواقعي — فتُقاس البوابات على وقائع تشغيلية.
    """
    defaults: dict[str, object] = {
        "data_quality": DataQuality.HEALTHY,
        "data_age_seconds": 2.0,
        "spread_estimate": 12.0,
        "slippage_estimate": 20.0,
        "latency_ms": 250.0,
    }
    defaults.update(overrides)
    return EvaluationContext.model_validate(defaults)
