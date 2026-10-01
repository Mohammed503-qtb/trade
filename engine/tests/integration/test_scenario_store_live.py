"""اختبارات مخزن السيناريوهات الحية (علامة integration: postgres عند 0007).

بوابات المرحلة 7-e:

- **upsert idempotent**: السيناريو مرتين ⇒ صفه نفسه محدَّث (لا تكرار)،
  والانتقال مرتين ⇒ صف واحد (DO NOTHING — التاريخ لا يُعاد كتابته).
- **دورة الحياة باستعلام واحد**: ``read_lifecycle`` جولة SQL واحدة
  تعيد السيناريو وانتقالاته بترتيب الوقوع — عدد الاستعلامات يُقاس
  فعليًا (وكيل عدّاد حول الاتصال).
- **round-trip قانوني**: ما يُقرأ يعاد بناؤه عبر النماذج ويطابق ما كُتب
  بالتساوي (نموذجًا لا dict خام).
- **بوابة الخروج 7**: ``audit_licensing_readiness`` يفحص كل مرخِّص —
  المحقق يمر والمخدوش يُعرف باسمه.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from common.config import load_settings
from scenarios.engine import ScenarioEngine
from scenarios.lifecycle import apply_transition
from scenarios.store import ScenarioStore, transition_id_for
from schemas import (
    DataQuality,
    EventType,
    HTFBias,
    LiquiditySide,
    LiquiditySourceType,
    MarketRegime,
    MarketStateSnapshot,
    ScenarioState,
    ScenarioTemplate,
    SweepClassification,
    ZoneState,
)
from schemas.liquidity import SweepEventPayload

#: طابع المرسِم المرجعي (بنّاؤون مضمّنون — التكاملية لا تستورد وحدة
#: اختبار الوحدة: مسارا الوحدة مختلفان في mypy/pytest).
ANCHOR_TIME = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
ATR = 200.0
ZONE_ID = "test-7-zone-001"


def _zone() -> Any:
    from schemas import LiquidityZone

    return LiquidityZone(
        zone_id=ZONE_ID,
        side=LiquiditySide.SELL_SIDE,
        price_low=59_800.0,
        price_high=59_900.0,
        origin_time=ANCHOR_TIME - timedelta(hours=6),
        age=120,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=2,
        last_test_time=ANCHOR_TIME - timedelta(hours=1),
        sweep_status=SweepClassification.UNKNOWN,
        reaction_score=0.6,
        unmitigated_score=0.7,
        importance_score=0.8,
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        state=ZoneState.ACTIVE,
    )


def _state(bias: HTFBias = HTFBias.BULLISH) -> MarketStateSnapshot:
    return MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        event_time=ANCHOR_TIME,
        regime=MarketRegime.TREND_PULLBACK,
        htf_bias=bias,
        volatility_percentile=60.0,
        data_quality=DataQuality.HEALTHY,
    )


def _sweep_payload() -> SweepEventPayload:
    return SweepEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=ANCHOR_TIME,
        zone_id=ZONE_ID,
        zone_side=LiquiditySide.SELL_SIDE,
        classification=SweepClassification.CONFIRMED_SWEEP,
        excursion_atr=1.0,
        penetration_reached=True,
        reclaim_bars=1,
        test_count_at_event=3,
    )


class _CountingConnection:
    """وكيل عدّاد حول الاتصال — قياس فعلي لجولات SQL (نمط 6-e)."""

    def __init__(self, inner: asyncpg.Connection) -> None:
        self._inner = inner
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.queries.append(query)
        rows: list[Any] = await self._inner.fetch(query, *args)
        return rows

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        self.queries.append(query)
        status: str = await self._inner.execute(query, *args)
        return status

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _engine_with_anchor() -> ScenarioEngine:
    """محرك بمرسِم اجتياح واحد — ثلاثة مقترحات جاهزة للقيادة."""
    from liquidity.targets import TargetEntry, TargetMap
    from schemas import LiquiditySide, LiquidityZone

    engine = ScenarioEngine()
    above_zone = LiquidityZone(
        zone_id="test-7-buy-001",
        side=LiquiditySide.BUY_SIDE,
        price_low=60_500.0,
        price_high=60_600.0,
        origin_time=ANCHOR_TIME - timedelta(hours=6),
        age=100,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=0,
        last_test_time=None,
        sweep_status=SweepClassification.UNKNOWN,
        reaction_score=0.5,
        unmitigated_score=0.8,
        importance_score=0.7,
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        state=ZoneState.ACTIVE,
    )
    below_zone = LiquidityZone(
        zone_id="test-7-sell-002",
        side=LiquiditySide.SELL_SIDE,
        price_low=59_400.0,
        price_high=59_500.0,
        origin_time=ANCHOR_TIME - timedelta(hours=6),
        age=100,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=0,
        last_test_time=None,
        sweep_status=SweepClassification.UNKNOWN,
        reaction_score=0.5,
        unmitigated_score=0.8,
        importance_score=0.7,
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        state=ZoneState.ACTIVE,
    )
    targets = TargetMap(
        above=(
            TargetEntry(
                zone=above_zone,
                zone_low=60_500.0,
                zone_high=60_600.0,
                distance_atr=1.2,
                relevance=0.9,
            ),
        ),
        below=(
            TargetEntry(
                zone=below_zone,
                zone_low=59_400.0,
                zone_high=59_500.0,
                distance_atr=0.8,
                relevance=0.8,
            ),
        ),
    )
    engine.on_anchor(
        EventType.LIQUIDITY_SWEEP_LOW,
        ANCHOR_TIME,
        _sweep_payload(),
        zone=_zone(),
        targets=targets,
        state=_state(),
        atr=ATR,
    )
    return engine


@pytest.fixture
async def pg() -> asyncpg.Connection:
    """اتصال حي عند الرأس — تنظيف سيناريوهات الاختبار بعد كل اختبار."""
    settings = load_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        yield conn
    finally:
        await conn.execute("DELETE FROM scenarios WHERE symbol = $1", INSTRUMENT)
        await conn.close()


@pytest.mark.integration
class TestScenarioStoreLive:
    async def test_upsert_idempotent_and_round_trip(self, pg: asyncpg.Connection) -> None:
        engine = _engine_with_anchor()
        store = ScenarioStore()
        scenario = next(s for s in engine.scenarios() if s.template is ScenarioTemplate.REVERSAL)
        await store.upsert_scenario(pg, scenario)
        await store.upsert_scenario(pg, scenario)  # at-least-once

        count = await pg.fetchval(
            "SELECT count(*) FROM scenarios WHERE scenario_id = $1", scenario.scenario_id
        )
        assert count == 1

        restored = await store.read_scenario(pg, scenario.scenario_id)
        assert restored is not None
        assert restored == scenario  # round-trip قانوني بالنموذج كاملًا

    async def test_transitions_append_only_idempotent(self, pg: asyncpg.Connection) -> None:
        engine = _engine_with_anchor()
        store = ScenarioStore()
        draft = next(s for s in engine.scenarios() if s.template is ScenarioTemplate.REVERSAL)
        active, record = apply_transition(
            draft,
            ScenarioState.ACTIVE,
            transition_time=ANCHOR_TIME + timedelta(minutes=1),
            reason="ترقية اختبارية §18.4",
        )
        await store.write_lifecycle(pg, active, (record,))
        await store.append_transition(pg, record)  # إعادة إرسال — DO NOTHING

        count = await pg.fetchval(
            "SELECT count(*) FROM scenario_transitions WHERE scenario_id = $1",
            draft.scenario_id,
        )
        assert count == 1

    async def test_lifecycle_single_query_and_order(self, pg: asyncpg.Connection) -> None:
        """دورة الحياة كاملة بجولة SQL واحدة — الانتقالات بترتيب الوقوع."""
        engine = _engine_with_anchor()
        store = ScenarioStore()
        draft = next(s for s in engine.scenarios() if s.template is ScenarioTemplate.REVERSAL)
        current = draft
        records = []
        for step, (target, reason) in enumerate(
            (
                (ScenarioState.ACTIVE, "ترقية"),
                (ScenarioState.TRIGGERED, "مشغل"),
                (ScenarioState.SUPPRESSED, "تنافس"),
            ),
            start=1,
        ):
            current, record = apply_transition(
                current,
                target,
                transition_time=ANCHOR_TIME + timedelta(minutes=step),
                reason=reason,
            )
            records.append(record)
        await store.write_lifecycle(pg, current, records)

        counting = _CountingConnection(pg)
        lifecycle = await store.read_lifecycle(counting, draft.scenario_id)
        assert lifecycle is not None
        scenario, transitions = lifecycle
        assert scenario.state is ScenarioState.SUPPRESSED
        assert [t.to_state for t in transitions] == [
            ScenarioState.ACTIVE,
            ScenarioState.TRIGGERED,
            ScenarioState.SUPPRESSED,
        ]
        # بوابة القياس: استعلام قراءة واحد حصرًا
        read_queries = [q for q in counting.queries if "FROM scenarios" in q]
        assert len(read_queries) == 1

    async def test_licensing_audit_gate(self, pg: asyncpg.Connection) -> None:
        """بوابة الخروج 7: كل مرخِّص له مشغل وإبطال — والمخدوش يُعرف."""
        store = ScenarioStore()
        engine = _engine_with_anchor()
        # مرخِّص محقق: TRIGGERED بمشغل وإبطال معرّفين من المُقترِح
        draft = next(s for s in engine.scenarios() if s.template is ScenarioTemplate.REVERSAL)
        active, rec_active = apply_transition(
            draft,
            ScenarioState.ACTIVE,
            transition_time=ANCHOR_TIME + timedelta(minutes=1),
            reason="ترقية",
        )
        triggered, rec_trigger = apply_transition(
            active,
            ScenarioState.TRIGGERED,
            transition_time=ANCHOR_TIME + timedelta(minutes=2),
            reason="مشغل DISPLACEMENT_CONFIRM رُصد",
        )
        await store.write_lifecycle(pg, triggered, (rec_active, rec_trigger))
        # مرخِّص مخدوش: TRIGGERED بمشغل فارغ (عبث خارج المسار الموثق)
        tampered = triggered.model_copy(
            update={
                "trigger_definition": triggered.trigger_definition.model_copy(
                    update={"condition_type": "MYSTERY", "params": {}}
                ),
                "scenario_id": "0" * 8 + "-0000-4000-8000-" + "000000000001",
            }
        )
        await store.upsert_scenario(pg, tampered)

        checked, violators = await store.audit_licensing_readiness(pg)
        assert checked == 2
        assert violators == (tampered.scenario_id,)

    async def test_transition_id_deterministic(self) -> None:
        """معرف الانتقال uuid5 حتمي — نفس الهوية ⇒ نفس المعرف."""
        from schemas import ScenarioTransition

        transition = ScenarioTransition(
            scenario_id="sc-1",
            from_state=ScenarioState.DRAFT,
            to_state=ScenarioState.ACTIVE,
            transition_time=ANCHOR_TIME,
            reason="اختبار",
        )
        assert transition_id_for(transition) == transition_id_for(transition)
        other = transition.model_copy(update={"reason": "سبب آخر"})
        assert transition_id_for(other) == transition_id_for(
            transition
        )  # السبب خارج الهوية — التوقيت والحالات والمعرف هوية
