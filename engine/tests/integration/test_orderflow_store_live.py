"""اختبارات مخزن التدفق الحية — footprint_bars/rows وorderflow_events
(علامة integration: تتطلب postgres حيًا عند upgrade head).

الدورة الكاملة للمهمة 4-e على القاعدة الفعلية:

- شريط فوتبرنت upsert مرتين ⇒ صف واحد محدَّث (المتطور يُحدَّث لا يُستنسخ).
- صفوف الشريط استبدال مرتين ⇒ نفس الصفوف (idempotent) والاحتفاظ قرار
  الكاتب (§31.2: لا كتابة تلقائية مع كل شريط).
- حدث تدفق upsert مرتين ⇒ صف واحد (event_id الحتمي — روح D-07).
- قراءة round-trip عبر pydantic تعيد النماذج كما كُتبت.
- النوع غير التدفقي يُرفض صراحة (لا كتابة صامتة لجدول غير موطن).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from common.config import load_settings
from orderflow.events import EmittedEvent
from orderflow.rows import (
    METHODOLOGY_AGGTRADE_TAKER,
    FootprintRow,
)
from orderflow.store import FLOW_EVENT_TYPES, FootprintStore, OrderflowStoreError
from schemas import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    DataQuality,
    EventType,
    FootprintBar,
)

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
BAR_TIME = datetime(2026, 9, 27, 19, 40, tzinfo=UTC)


def make_bar(*, is_closed: bool = True) -> FootprintBar:
    """شريط فوتبرنت صالح كامل الحقول (منهجية 4-b القانونية §12.7)."""
    return FootprintBar(
        instrument_id=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BAR_TIME,
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        source_feed="binance-usdm-aggtrades",
        methodology=METHODOLOGY_AGGTRADE_TAKER,
        buy_volume=1640.42,
        sell_volume=2507.47,
        total_volume=4147.89,
        delta=-866.05,
        buy_share=1640.42 / 4147.89,
        sell_share=2507.47 / 4147.89,
        poc=83459.4,
        vah=83480.1,
        val=83440.2,
        row_count=37,
        buy_imbalance_count=4,
        sell_imbalance_count=6,
    )


def make_absorption_event() -> EmittedEvent:
    """حدث امتصاص كامل الشروط §12.3 — مرشح غير مؤكد."""
    return EmittedEvent(
        event_type=EventType.ABSORPTION_BUY,
        event_time=BAR_TIME,
        payload=AbsorptionEventPayload(
            instrument=INSTRUMENT,
            timeframe=TIMEFRAME,
            bar_time=BAR_TIME,
            absorbed_pressure=AbsorbedPressure.SELL,
            delta=-412.5,
            delta_share=-0.62,
            excursion_atr=0.31,
            conditions=AbsorptionConditions(
                elevated_delta=True,
                limited_extension=True,
                repeated_response=True,
                opposite_displacement=None,
            ),
            zone_id=None,
            confirmed=False,
        ),
    )


@pytest.mark.integration
class TestFootprintStoreLive:
    async def test_upsert_bar_idempotent_and_round_trip(self, conn: asyncpg.Connection) -> None:
        """إرسالان ⇒ صف واحد؛ والقراءة تعيد النموذج بالتطابق."""
        store = FootprintStore()
        evolving = make_bar(is_closed=False)
        await store.upsert_bar(conn, evolving)
        closed = make_bar(is_closed=True)
        await store.upsert_bar(conn, closed)  # المتطور اكتمل — تحديث لا استنساخ

        count = await conn.fetchval("SELECT count(*) FROM footprint_bars")
        assert count == 1
        bars = await store.read_bars(conn, INSTRUMENT, TIMEFRAME)
        assert len(bars) == 1
        assert bars[0] == closed  # pydantic round-trip بالتطابق التام

    async def test_replace_rows_idempotent_and_ordered(self, conn: asyncpg.Connection) -> None:
        """استبدالان بنفس الصفوف ⇒ نفس الصفوف؛ والترتيب تصاعدي بالسعر."""
        store = FootprintStore()
        bar = make_bar()
        await store.upsert_bar(conn, bar)
        rows = (
            FootprintRow(price=83460.0, buy_volume=11.5, sell_volume=2.0),
            FootprintRow(price=83459.0, buy_volume=3.0, sell_volume=9.5),
            FootprintRow(price=83461.0, buy_volume=1.0, sell_volume=4.0),
        )
        await store.replace_rows(conn, bar, rows)
        await store.replace_rows(conn, bar, rows)  # إعادة الإرسال idempotent

        count = await conn.fetchval("SELECT count(*) FROM footprint_rows")
        assert count == 3
        read_back = await store.read_rows(conn, INSTRUMENT, TIMEFRAME, BAR_TIME)
        assert read_back == [
            FootprintRow(price=83459.0, buy_volume=3.0, sell_volume=9.5),
            FootprintRow(price=83460.0, buy_volume=11.5, sell_volume=2.0),
            FootprintRow(price=83461.0, buy_volume=1.0, sell_volume=4.0),
        ]

    async def test_upsert_event_idempotent_and_round_trip(self, conn: asyncpg.Connection) -> None:
        """حدثان متطابقان ⇒ صف واحد؛ والقراءة تعيد EmittedEvent بالتطابق."""
        store = FootprintStore()
        event = make_absorption_event()
        await store.upsert_event(conn, event)
        await store.upsert_event(conn, event)  # at-least-once ⇒ تحديث لا تكرار

        count = await conn.fetchval("SELECT count(*) FROM orderflow_events")
        assert count == 1
        events = await store.read_events(conn, INSTRUMENT, TIMEFRAME)
        assert len(events) == 1
        assert events[0] == event  # round-trip بالتطابق (النوع والوقت والحمولة)

    async def test_non_flow_event_rejected(self, conn: asyncpg.Connection) -> None:
        """النوع البنيوي ليس من موطن orderflow_events — رفض صاخب موثق."""
        store = FootprintStore()
        bogus = EmittedEvent(
            event_type=EventType.INTERNAL_BOS,  # بنيوي — خارج الأنواع الثمانية
            event_time=BAR_TIME,
            payload=make_absorption_event().payload,  # الحمولة لا تهم — النوع يُرفض أولًا
        )
        with pytest.raises(OrderflowStoreError, match="ليس من تدفق المرحلة 4"):
            await store.upsert_event(conn, bogus)

    async def test_flow_event_types_are_the_documented_eight(self) -> None:
        """عقد §31.3: الموطن يغطي الأنواع التدفقية الثمانية حصرًا."""
        assert {
            EventType.ABSORPTION_BUY,
            EventType.ABSORPTION_SELL,
            EventType.FLOW_CONTINUATION_UP,
            EventType.FLOW_CONTINUATION_DOWN,
            EventType.EXHAUSTION_UP,
            EventType.EXHAUSTION_DOWN,
            EventType.BUY_IMBALANCE_CLUSTER,
            EventType.SELL_IMBALANCE_CLUSTER,
        } == FLOW_EVENT_TYPES


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    """اتصال على القاعدة الحية مع تنظيف بيانات الاختبار بعده."""
    settings = load_settings()
    connection = await asyncpg.connect(settings.database_url)
    try:
        await connection.execute("DELETE FROM footprint_rows")
        await connection.execute("DELETE FROM footprint_bars")
        await connection.execute("DELETE FROM orderflow_events")
        yield connection
    finally:
        await connection.execute("DELETE FROM footprint_rows")
        await connection.execute("DELETE FROM footprint_bars")
        await connection.execute("DELETE FROM orderflow_events")
        await connection.close()
