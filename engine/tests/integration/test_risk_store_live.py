"""اختبارات مخزن المخاطرة ودفتر التجارب الحية (علامة integration: postgres عند 0008).

بوابات المرحلة 8-g:

- **هجرة 0008**: الجداول الثلاثة (decisions/trade_intents/experience_ledger)
  عند الرأس بأعمدتها المتوقعة.
- **upsert idempotent**: القرار مرتين ⇒ صفه نفسه محدَّث (لا تكرار)،
  والتجربة مرتين ⇒ صف واحد (DO NOTHING — الدفتر ملحق-فقط).
- **القراءة بجولة واحدة**: ``read_decision_with_lifecycle`` جولة SQL
  واحدة تعيد القرار والسيناريو وانتقالاته (عدّاد فعلي).
- **بوابة الخروج 8 نصًا**: ``audit_risk_gate`` — المحقق يمر وصفر مخالفين،
  والمخدوش (قرار مرخَّص بحاجب صلب) يُعرف باسمه.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from common.config import load_settings
from learning.ledger import build_experience_record, experience_id_for
from learning.store import ExperienceStore
from risk.engine import RiskEngine
from risk.store import RiskStore
from scenarios.lifecycle import apply_transition
from scenarios.proposer import AnchorEvent, ScenarioProposer
from scenarios.store import ScenarioStore
from schemas import (
    Candle,
    DataQuality,
    EvaluationContext,
    EventType,
    HTFBias,
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    MarketRegime,
    MarketStateSnapshot,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
    SessionType,
    SweepClassification,
    ZoneState,
)
from schemas.liquidity import SweepEventPayload

#: طابع المرسِم وشمعة القرار المرجعية.
ANCHOR_TIME = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
DECISION_TIME = ANCHOR_TIME + timedelta(minutes=1)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
ATR = 200.0
ZONE_ID = "test-8-zone-001"


class _CountingConnection:
    """وكيل عدّاد — يقيس جولات SQL الفعلية (نمط fusion/scenarios)."""

    def __init__(self, inner: asyncpg.Connection) -> None:
        self._inner = inner
        self.queries = 0

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.queries += 1
        rows: list[Any] = await self._inner.fetch(query, *args)
        return rows

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.queries += 1
        return await self._inner.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.queries += 1
        return await self._inner.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        self.queries += 1
        status: str = await self._inner.execute(query, *args)
        return status

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _liquidity_zone(zone_id: str, side: LiquiditySide, low: float, high: float) -> LiquidityZone:
    return LiquidityZone(
        zone_id=zone_id,
        side=side,
        price_low=low,
        price_high=high,
        origin_time=ANCHOR_TIME - timedelta(hours=6),
        age=120,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=2,
        last_test_time=ANCHOR_TIME - timedelta(hours=1),
        sweep_status=SweepClassification.CONFIRMED_SWEEP,
        reaction_score=0.6,
        unmitigated_score=0.7,
        importance_score=0.8,
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        state=ZoneState.ACTIVE,
    )


def _triggered_and_decision(
    *,
    approved: bool = True,
    template: ScenarioTemplate = ScenarioTemplate.REVERSAL,
    zone_id: str = ZONE_ID,
) -> tuple[Scenario, Any, Sequence[Any], MarketStateSnapshot]:
    """سيناريو TRIGGERED حقيقي بقراره — بنّاؤون مضمّنون (مسار تكاملي).

    الحتمية تضمن أن كل استدعاء بنفس المنطقة يعيد نفس السيناريو والقرار
    (uuid5) — والمنطقة الفريدة لكل اختبار تعزله عن بقية الحالة المشتركة.
    """
    from liquidity.targets import TargetEntry, TargetMap

    zone = _liquidity_zone(zone_id, LiquiditySide.SELL_SIDE, 59_800.0, 59_900.0)
    payload = SweepEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=ANCHOR_TIME,
        zone_id=zone_id,
        zone_side=LiquiditySide.SELL_SIDE,
        classification=SweepClassification.CONFIRMED_SWEEP,
        excursion_atr=1.0,
        penetration_reached=True,
        reclaim_bars=1,
        test_count_at_event=3,
    )
    state = MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe="15m",
        event_time=ANCHOR_TIME,
        regime=MarketRegime.TREND_PULLBACK,
        htf_bias=HTFBias.BULLISH,
        volatility_percentile=60.0,
        data_quality=DataQuality.HEALTHY,
    )

    def buy_target(zone_id: str, low: float, high: float, dist: float, rel: float) -> TargetEntry:
        return TargetEntry(
            zone=_liquidity_zone(zone_id, LiquiditySide.BUY_SIDE, low, high),
            zone_low=low,
            zone_high=high,
            distance_atr=dist,
            relevance=rel,
        )

    def sell_target(zone_id: str, low: float, high: float, dist: float, rel: float) -> TargetEntry:
        return TargetEntry(
            zone=_liquidity_zone(zone_id, LiquiditySide.SELL_SIDE, low, high),
            zone_low=low,
            zone_high=high,
            distance_atr=dist,
            relevance=rel,
        )

    targets = TargetMap(
        above=(
            buy_target("lz-buy-001", 60_800.0, 60_900.0, 2.2, 0.9),
            buy_target("lz-buy-002", 61_400.0, 61_500.0, 3.4, 0.7),
        ),
        below=(
            sell_target("lz-sell-002", 59_400.0, 59_500.0, 0.8, 0.8),
            sell_target("lz-sell-003", 59_000.0, 59_100.0, 1.9, 0.6),
        ),
    )
    proposer = ScenarioProposer()
    outcome = proposer.propose(
        AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, payload),
        zone=zone,
        targets=targets,
        state=state,
        atr=ATR,
    )
    proposal = next(s for s in outcome.proposals if s.template is template)
    scenario = proposal.model_copy(update={"state": ScenarioState.TRIGGERED})

    from fusion.compute import FusionEngine
    from fusion.ledger import EvidenceLedgerBuilder

    anchor = AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, payload)
    ledger = EvidenceLedgerBuilder()
    records = ledger.build(
        [anchor],
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        as_of=DECISION_TIME,
        market_state=state,
    )
    snapshot = FusionEngine().compute(
        records,
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        fusion_time=DECISION_TIME,
    )
    candle = Candle(
        instrument_id="BINANCE_USDM:BTCUSDT",
        timeframe=TIMEFRAME,
        bar_time=DECISION_TIME,
        session_id="sess-8",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=59_870.0,
        high=59_910.0,
        low=59_860.0,
        close=59_880.0,
        volume=100.0,
        range=50.0,
        body_size=10.0,
        upper_wick=30.0,
        lower_wick=20.0,
        body_fraction=0.2,
        close_location_value=0.4,
        true_range=60.0,
        realized_volatility=0.001,
    )
    context = EvaluationContext(
        spread_estimate=12.0,
        slippage_estimate=20.0,
        latency_ms=250.0,
    )
    if not approved:
        context = context.model_copy(update={"kill_switch": True})
    engine = RiskEngine()
    evaluation = engine.evaluate(
        scenario,
        snapshot=snapshot,
        records=records,
        market_state=state,
        candle=candle,
        atr=ATR,
        context=context,
        trigger_reason="مشغل DISPLACEMENT_CONFIRM رُصد",
    )
    return scenario, evaluation.decision, records, state


@pytest.fixture
async def pg() -> asyncpg.Connection:
    """اتصال حي على قاعدة الاختبار."""
    settings = load_settings()
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.mark.integration
class TestMigration0008:
    """هجرة الجداول الثلاثة عند الرأس."""

    async def test_tables_exist_with_expected_columns(self, pg: asyncpg.Connection) -> None:
        for table, column in (
            ("decisions", "parameter_fingerprint"),
            ("trade_intents", "risk_budget"),
            ("experience_ledger", "net_r"),
        ):
            row = await pg.fetchval(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = $2",
                table,
                column,
            )
            assert row == 1, f"عمود {column} غائب عن {table}"

    async def test_rejected_decision_has_no_intent_row(self, pg: asyncpg.Connection) -> None:
        """عقد التخزين: المرفوض لا صف تنفيذ له أصلاً (§22)."""
        _scenario, decision, _records, _state = _triggered_and_decision(
            approved=False, zone_id="test-8-zone-rejected-no-intent"
        )
        assert not decision.approved
        store = RiskStore()
        scenario_store = ScenarioStore()
        async with pg.transaction():
            await scenario_store.upsert_scenario(pg, _scenario)
            await store.write_outcome(pg, decision)
        count = await pg.fetchval(
            "SELECT COUNT(*) FROM trade_intents WHERE decision_id = $1",
            decision.decision_id,
        )
        assert count == 0


@pytest.mark.integration
class TestDecisionRoundTrip:
    """الكتابة idempotent والقراءة بجولة واحدة وبوابة الخروج نصًا."""

    async def test_decision_upsert_idempotent(self, pg: asyncpg.Connection) -> None:
        scenario, decision, _records, _state = _triggered_and_decision(zone_id="test-8-zone-upsert")
        assert decision.approved
        store = RiskStore()
        # السيناريو أولاً (FK للقرار)
        scenario_store = ScenarioStore()
        await scenario_store.upsert_scenario(pg, scenario)
        async with pg.transaction():
            await store.write_outcome(pg, decision)
            await store.write_outcome(pg, decision)  # idempotent
        count = await pg.fetchval(
            "SELECT COUNT(*) FROM decisions WHERE decision_id = $1",
            decision.decision_id,
        )
        assert count == 1
        intents = await pg.fetchval(
            "SELECT COUNT(*) FROM trade_intents WHERE decision_id = $1",
            decision.decision_id,
        )
        assert intents == 1
        restored = await store.read_decision(pg, decision.decision_id)
        assert restored is not None
        assert restored.model_dump_json() == decision.model_dump_json()

    async def test_read_decision_with_lifecycle_single_query(self, pg: asyncpg.Connection) -> None:
        scenario, decision, _records, _state = _triggered_and_decision(
            zone_id="test-8-zone-lifecycle"
        )
        store = RiskStore()
        scenario_store = ScenarioStore()
        # السيناريو وانتقالا الترخيص يكتبان أولاً (أصل قابل للتدقيق)
        authorized, transition = apply_transition(
            scenario,
            (decision.approved and ScenarioState.AUTHORIZED) or ScenarioState.REJECTED_BY_RISK,
            transition_time=decision.decided_at,
            reason="ترخيص المخاطرة (اختبار تكاملي)",
        )
        await scenario_store.write_lifecycle(pg, authorized, (transition,))
        await store.write_outcome(pg, decision)

        counting = _CountingConnection(pg)
        outcome = await store.read_decision_with_lifecycle(counting, scenario.scenario_id)
        assert outcome is not None
        restored_decision, restored_scenario, transitions = outcome
        assert restored_decision.decision_id == decision.decision_id
        assert restored_scenario.scenario_id == scenario.scenario_id
        assert len(transitions) >= 1
        assert counting.queries == 1  # جولة SQL واحدة — أثر كامل

    async def test_rejection_log_lists_rejected_only(self, pg: asyncpg.Connection) -> None:
        scenario_ok, approved, _r1, _s1 = _triggered_and_decision(
            approved=True, zone_id="test-8-zone-rejections"
        )
        scenario_no, rejected, _r2, _s2 = _triggered_and_decision(
            approved=False,
            template=ScenarioTemplate.BREAKOUT,
            zone_id="test-8-zone-rejections",
        )
        assert approved.approved and not rejected.approved
        assert approved.decision_id != rejected.decision_id  # سيناريوهان مختلفان
        store = RiskStore()
        scenario_store = ScenarioStore()
        async with pg.transaction():
            await scenario_store.upsert_scenario(pg, scenario_ok)
            await scenario_store.upsert_scenario(pg, scenario_no)
            await store.write_outcome(pg, approved)
            await store.write_outcome(pg, rejected)
        rejections = await store.list_rejections(pg)
        ids = [d.decision_id for d in rejections]
        assert rejected.decision_id in ids
        assert approved.decision_id not in ids

    async def test_audit_risk_gate_zero_violators_on_clean_rows(
        self, pg: asyncpg.Connection
    ) -> None:
        scenario_ok, approved, _r1, _s1 = _triggered_and_decision(
            approved=True, zone_id="test-8-zone-audit-clean"
        )
        scenario_no, rejected, _r2, _s2 = _triggered_and_decision(
            approved=False,
            template=ScenarioTemplate.BREAKOUT,
            zone_id="test-8-zone-audit-clean",
        )
        assert approved.approved and not rejected.approved
        store = RiskStore()
        scenario_store = ScenarioStore()
        async with pg.transaction():
            await scenario_store.upsert_scenario(pg, scenario_ok)
            await scenario_store.upsert_scenario(pg, scenario_no)
            await store.write_outcome(pg, approved)
            await store.write_outcome(pg, rejected)
        total, violators = await store.audit_risk_gate(pg)
        assert total >= 2
        # قرارات هذا الاختبار سليمة — لا تنتمي للمخالفين (العزل بمنطقة فريدة)
        own = {approved.decision_id, rejected.decision_id}
        assert not (own & set(violators))

    async def test_audit_risk_gate_catches_approved_with_hard_block(
        self, pg: asyncpg.Connection
    ) -> None:
        """قرار مرخَّص مع حاجب صلب — خرق يُعرف باسمه (البوابة نصًا)."""
        scenario, decision, _records, _state = _triggered_and_decision(
            approved=False, zone_id="test-8-zone-audit-tamper"
        )
        assert not decision.approved
        assert decision.hard_blocks  # مرفوض بحاجب القتل الطارئ
        # العبث المقصود: ترخيص قرار يحمل حاجبه الصلب — تناقض جوهري
        violating = decision.model_copy(update={"approved": True})
        store = RiskStore()
        scenario_store = ScenarioStore()
        async with pg.transaction():
            await scenario_store.upsert_scenario(pg, scenario)
            await store.upsert_decision(pg, violating)
        _total, violators = await store.audit_risk_gate(pg)
        assert violating.decision_id in violators


@pytest.mark.integration
class TestExperienceLedgerLive:
    """دفتر التجارب — صف واحد لكل سيناريو ملحق-فقط."""

    async def test_experience_upsert_once_only(self, pg: asyncpg.Connection) -> None:
        scenario, decision, records, _state = _triggered_and_decision(
            zone_id="test-8-zone-experience"
        )
        assert decision.approved
        closed = scenario.model_copy(update={"state": ScenarioState.INVALIDATED})
        closing_time = decision.decided_at + timedelta(minutes=5)
        from schemas import ScenarioTransition

        closing = ScenarioTransition(
            scenario_id=closed.scenario_id,
            from_state=ScenarioState.AUTHORIZED,
            to_state=ScenarioState.INVALIDATED,
            transition_time=closing_time,
            reason="إبطال §18.5: قبول خلف المستوى البنيوي",
        )
        record = build_experience_record(
            closed,
            decision=decision,
            closing_transition=closing,
            records=records,
            market_path=[],
            session=SessionType.UTC_DAY,
        )
        store = ExperienceStore()
        scenario_store = ScenarioStore()
        async with pg.transaction():
            await scenario_store.upsert_scenario(pg, scenario)
            await store.upsert_experience(pg, record)
            await store.upsert_experience(pg, record)  # idempotent — DO NOTHING
        count = await pg.fetchval(
            "SELECT COUNT(*) FROM experience_ledger WHERE scenario_id = $1",
            closed.scenario_id,
        )
        assert count == 1
        restored = await store.read_experience(pg, closed.scenario_id)
        assert restored is not None
        assert restored.exit_reason == closing.reason
        assert restored.risk_snapshot.decision_id == decision.decision_id
        row_id = await pg.fetchval(
            "SELECT experience_id FROM experience_ledger WHERE scenario_id = $1",
            closed.scenario_id,
        )
        assert row_id == experience_id_for(closed.scenario_id)
