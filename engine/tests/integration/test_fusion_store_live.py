"""اختبارات مخزن الدمج الحية (علامة integration: postgres حي عند الرأس 0006).

بوابات المهمة 6-e (نفس عقود مخازن 3-f/4-e/5-d):

- **upsert idempotent**: الأدلة مرتين ⇒ صفوفها نفسها محدَّثة (لا تكرار)
  واللقطات مرتين عند اللحظة نفسها ⇒ صف واحد.
- **السلسلة باستعلام واحد** (بوابة الخروج 6): ``read_chain`` جولة SQL
  واحدة تعيد أدلة السيناريو كاملة بترتيب حتمي + أحدث لقطة — عدد
  الاستعلامات يُقاس فعليًا (وكيل عدّاد حول الاتصال).
- **round-trip قانوني**: ما يُقرأ يعاد بناؤه عبر النماذج ويطابق ما كُتب
  بالتساوي (نموذجًا لا dict خام) — وعمود المساهمة يطابق المعادلة §19.2.
- **عزل السيناريوهات**: دليل سيناريو لا يظهر في سلسلة آخر.
- **تاريخ اللقطات**: fusion_time متناقصًا والسلسلة تعرض الأحدث.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from common.config import load_settings
from fusion.compute import FusionEngine, contribution
from fusion.ledger import EvidenceLedgerBuilder
from fusion.store import FusionStore, fusion_snapshot_id
from pydantic import BaseModel
from schemas import (
    DataQuality,
    Direction,
    EventType,
    EvidenceRecord,
    FusionSnapshot,
    HTFBias,
    MarketRegime,
    MarketStateSnapshot,
    PatternDirection,
)
from schemas.orderflow import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
)
from schemas.patterns import CandlePatternEventPayload, CandlePatternFamily
from schemas.structure import (
    BreakDirection,
    DisplacementEventPayload,
    StructureBreakPayload,
    SwingScope,
)

#: طوابع العينة (بنّاؤون مضمّنون — التكاملية لا تستورد وحدات اختبار
#: الوحدة: مسارا الوحدة مختلفان في mypy/pytest).
BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def _break(index: int) -> StructureBreakPayload:
    """كسر خارجي بمعاملات متوسطة قابلة للحساب اليدوي."""
    return StructureBreakPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        swing_id=f"swing-{index}",
        swing_scope=SwingScope.EXTERNAL,
        break_direction=BreakDirection.UP,
        breach_distance_atr=1.0,
        closing_acceptance=0.8,
        follow_through=0.5,
    )


def _displacement(index: int) -> DisplacementEventPayload:
    return DisplacementEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        direction=BreakDirection.UP,
        range_zscore=2.0,
        body_fraction=0.8,
        close_location=0.9,
        atr_multiple=2.0,
        velocity=1.5,
        follow_through=0.6,
    )


def _absorption(index: int) -> AbsorptionEventPayload:
    return AbsorptionEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        absorbed_pressure=AbsorbedPressure.SELL,
        delta=-40.0,
        delta_share=-0.4,
        excursion_atr=0.2,
        conditions=AbsorptionConditions(
            elevated_delta=True, limited_extension=True, repeated_response=False
        ),
    )


def _engulfing_bearish(index: int) -> CandlePatternEventPayload:
    return CandlePatternEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        family=CandlePatternFamily.ENGULFING,
        direction=PatternDirection.BEARISH,
        feature_readings={
            "body_fraction": 0.6,
            "wick_asymmetry": 0.4,
            "close_location": 0.2,
            "range_percentile": 0.7,
            "gap_relationship": 0.5,
            "volume_relationship": 0.6,
        },
        strength=0.7,
        bars_in_pattern=2,
    )


SCENARIO = "test-6e-fusion-chain"
SCENARIO_OTHER = "test-6e-other"


class _Ev:
    """حدث مكشوف اختباري — العقد الثلاثي نفسه (نمط كواشف المراحل)."""

    def __init__(self, event_type: EventType, event_time: datetime, payload: BaseModel) -> None:
        self.event_type = event_type
        self.event_time = event_time
        self.payload = payload


def _market_state() -> MarketStateSnapshot:
    return MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        event_time=BASE_TIME,
        regime=MarketRegime.TREND_EXPANSION,
        htf_bias=HTFBias.BULLISH,
        volatility_percentile=65.0,
        data_quality=DataQuality.HEALTHY,
    )


def _build_ledger(scenario: str) -> tuple[list[EvidenceRecord], FusionSnapshot]:
    """سجل نموذجي: انحياز + كسر خارجي وإزاحة عند شمعة واحدة (دفعة
    مترابطة تُخصم)، امتصاص وابتلاع معاكس بعدها (تناقض صريح §19.5)."""
    events = [
        _Ev(EventType.EXTERNAL_BOS, BASE_TIME, _break(0)),
        _Ev(EventType.DISPLACEMENT_UP, BASE_TIME, _displacement(0)),
        _Ev(EventType.ABSORPTION_BUY, BASE_TIME + timedelta(minutes=1), _absorption(1)),
        _Ev(
            EventType.BEARISH_ENGULFING,
            BASE_TIME + timedelta(minutes=1),
            _engulfing_bearish(1),
        ),
    ]
    as_of = BASE_TIME + timedelta(minutes=2)
    records = EvidenceLedgerBuilder().build(
        events,
        scenario_id=scenario,
        direction=Direction.LONG,
        as_of=as_of,
        market_state=_market_state(),
    )
    snapshot = FusionEngine().compute(
        records, scenario_id=scenario, direction=Direction.LONG, fusion_time=as_of
    )
    return records, snapshot


class _CountingConnection:
    """وكيل عدّاد حول الاتصال — يقيس جولات SQL الفعلية (بوابة الجولة الواحدة)."""

    def __init__(self, inner: asyncpg.Connection) -> None:
        self._inner = inner
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.fetch(query, *args)

    async def execute(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.execute(query, *args)

    async def executemany(self, query: str, *args: Any) -> Any:
        self.queries.append(query)
        return await self._inner.executemany(query, *args)


@pytest.fixture
async def pg() -> asyncpg.Connection:
    """اتصال حي عند الرأس — تنظيف أدلة السيناريوهات الاختبارية بعد كل اختبار."""
    settings = load_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        yield conn
    finally:
        await conn.execute("DELETE FROM evidence_items WHERE scenario_id LIKE 'test-6e-%'")
        await conn.execute("DELETE FROM fusion_snapshots WHERE scenario_id LIKE 'test-6e-%'")
        await conn.close()


@pytest.mark.integration
class TestFusionStoreLive:
    async def test_upsert_idempotent_and_round_trip(self, pg: asyncpg.Connection) -> None:
        """كتابة مرتين ⇒ صفوف محدَّثة لا مكررة، والقراءة تعيد السجل كاملًا."""
        records, snapshot = _build_ledger(SCENARIO)
        store = FusionStore()
        await store.upsert_evidence(pg, records, scenario_id=SCENARIO)
        await store.upsert_snapshot(pg, snapshot)
        # الإرسال الثاني (at-least-once) — idempotent
        await store.upsert_evidence(pg, records, scenario_id=SCENARIO)
        await store.upsert_snapshot(pg, snapshot)

        count = await pg.fetchval(
            "SELECT count(*) FROM evidence_items WHERE scenario_id = $1", SCENARIO
        )
        assert count == len(records)
        snap_count = await pg.fetchval(
            "SELECT count(*) FROM fusion_snapshots WHERE scenario_id = $1", SCENARIO
        )
        assert snap_count == 1

        restored, restored_snapshot = await store.read_chain(pg, SCENARIO)
        assert len(restored) == len(records)
        # round-trip بالتساوي عبر النماذج (بترتيب القاعدة الحتمي)
        by_id = {r.evidence_id: r for r in records}
        for record in restored:
            assert record == by_id[record.evidence_id]
        assert restored_snapshot is not None
        assert restored_snapshot == snapshot

    async def test_contribution_column_matches_formula(self, pg: asyncpg.Connection) -> None:
        """عمود المساهمة يطابق معادلة §19.2 لكل صف — السجل والعمود متسقان."""
        records, _ = _build_ledger(SCENARIO)
        await FusionStore().upsert_evidence(pg, records, scenario_id=SCENARIO)
        rows = await pg.fetch(
            "SELECT evidence_id, contribution FROM evidence_items WHERE scenario_id = $1",
            SCENARIO,
        )
        by_id = {r.evidence_id: contribution(r) for r in records}
        assert rows
        for row in rows:
            assert row["contribution"] == pytest.approx(by_id[str(row["evidence_id"])])

    async def test_read_chain_is_single_query(self, pg: asyncpg.Connection) -> None:
        """بوابة الخروج 6 حرفيًا: السلسلة الكاملة (أدلة + لقطة) بجولة
        واحدة — عدّاد الجولات يُفحص فعليًا."""
        records, snapshot = _build_ledger(SCENARIO)
        store = FusionStore()
        await store.upsert_evidence(pg, records, scenario_id=SCENARIO)
        await store.upsert_snapshot(pg, snapshot)

        counting = _CountingConnection(pg)
        # الوكيل بنيوي ( fetchrow فقط تستهلكه read_chain) — التعليق أدناه
        # لتجاوز توقيع asyncpg.Connection الحرفي
        restored, restored_snapshot = await store.read_chain(counting, SCENARIO)
        assert len(counting.queries) == 1, (
            f"السلسلة استهلكت {len(counting.queries)} جولة — البوابة جولة واحدة"
        )
        assert len(restored) == len(records)
        assert restored_snapshot is not None
        assert restored_snapshot.scenario_id == SCENARIO

    async def test_scenario_isolation(self, pg: asyncpg.Connection) -> None:
        """دليل سيناريو لا يتسرب إلى سلسلة آخر (معرفات مشتملة السيناريو)."""
        records_a, _ = _build_ledger(SCENARIO)
        records_b, snapshot_b = _build_ledger(SCENARIO_OTHER)
        store = FusionStore()
        await store.upsert_evidence(pg, records_a, scenario_id=SCENARIO)
        await store.upsert_evidence(pg, records_b, scenario_id=SCENARIO_OTHER)
        await store.upsert_snapshot(pg, snapshot_b)

        restored_a, _ = await store.read_chain(pg, SCENARIO)
        assert all(r.evidence_id in {x.evidence_id for x in records_a} for r in restored_a)
        restored_b, snapshot_b_restored = await store.read_chain(pg, SCENARIO_OTHER)
        assert len(restored_b) == len(records_b)
        assert snapshot_b_restored is not None
        # سيناريو بلا دليل ولا لقطة ⇒ سلسلة فارغة بلا خطأ ولا اختلاق
        empty, none_snapshot = await store.read_chain(pg, "test-6e-nothing")
        assert empty == []
        assert none_snapshot is None

    async def test_snapshot_history_latest_first(self, pg: asyncpg.Connection) -> None:
        """لقطتان عند لحظتين مختلفتين ⇒ التاريخ الأحدث أولًا والسلسلة
        تعرض الأحدث."""
        records, _ = _build_ledger(SCENARIO)
        store = FusionStore()
        await store.upsert_evidence(pg, records, scenario_id=SCENARIO)
        early = FusionEngine().compute(
            records,
            scenario_id=SCENARIO,
            direction=Direction.LONG,
            fusion_time=BASE_TIME + timedelta(minutes=2),
        )
        late = FusionEngine().compute(
            records,
            scenario_id=SCENARIO,
            direction=Direction.LONG,
            fusion_time=BASE_TIME + timedelta(minutes=3),
        )
        await store.upsert_snapshot(pg, early)
        await store.upsert_snapshot(pg, late)

        history = await store.read_snapshots(pg, SCENARIO)
        assert [s.fusion_time for s in history] == [late.fusion_time, early.fusion_time]
        _, latest = await store.read_chain(pg, SCENARIO)
        assert latest is not None
        assert latest.fusion_time == late.fusion_time

    async def test_event_id_column_links_source(self, pg: asyncpg.Connection) -> None:
        """وصلة السلسلة: أدلة الأحداث تحمل event_id الحتمي (نفس اشتقاق
        المخازن) ودليل الحالة event_id NULL."""
        records, _ = _build_ledger(SCENARIO)
        await FusionStore().upsert_evidence(pg, records, scenario_id=SCENARIO)
        rows = await pg.fetch(
            "SELECT source, event_id FROM evidence_items WHERE scenario_id = $1",
            SCENARIO,
        )
        by_source = {r["source"]: r["event_id"] for r in rows}
        assert by_source["market_state.htf_bias"] is None
        assert by_source["analysis-event:EXTERNAL_BOS"] is not None
        # المشتق نفسه uuid5 فوق (type|instrument|timeframe|time|digest) —
        # البصمة الخامسة تميز الأحداث متعددة المناطق عند الشمعة نفسها (ADR-024)
        from fusion.ledger import _source_event_id
        from schemas import payload_digest

        break_payload = _break(0)
        expected = uuid_module.UUID(
            _source_event_id(
                EventType.EXTERNAL_BOS,
                INSTRUMENT,
                TIMEFRAME,
                BASE_TIME,
                payload_digest(break_payload),
            )
        )
        assert by_source["analysis-event:EXTERNAL_BOS"] == expected

    async def test_snapshot_id_deterministic(self, pg: asyncpg.Connection) -> None:
        """معرف اللقطة حتمي من (السيناريو، اللحظة) — إعادة الحساب نفسها."""
        moment = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        first = fusion_snapshot_id(SCENARIO, moment)
        second = fusion_snapshot_id(SCENARIO, moment)
        assert first == second
        assert first != fusion_snapshot_id(SCENARIO, moment + timedelta(seconds=1))
        assert first != fusion_snapshot_id(SCENARIO_OTHER, moment)
