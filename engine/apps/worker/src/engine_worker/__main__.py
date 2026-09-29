"""نقطة دخول worker — إعداد البنية التحتية المشتركة ثم تشغيل الخط.

المرحلة 0: إثبات الطوبولوجيا فقط (اتصال + نبض). خط الأنابيب الحقيقي
يبدأ من المرحلة 1 (ingestion) ويتراكم حتى المرحلة 8 (risk).

المهمة 2-f: قبل النبض مباشرة، تشغيل تجريبي واحد يبث لقطة مثال §32 عبر
SnapshotPublisher — إثبات توصيل رسالة ``market.state.updated`` على NATS
الحي (لا يمس هيكل النبض إطلاقًا: حلقة القياس نفسها بلا تغيير).

المهمة 3-f: تشغيل تجريبي ثانٍ يبث حدثًا بنيويًا مثالًا (INTERNAL_BOS)
عبر AnalysisEventPublisher بمغلف §32 الكامل ومعرف event_id حتمي (روح
D-07) على الموضوع ``market.event.example.1m.internal_bos`` — إثبات توصيل
مسار أحداث التحليل (الكواشف الحية تُوصَّل مع باقي خط الأنابيب لاحقًا).

المهمة 4-e: تشغيل تجريبي ثالث يبث حدثًا تدفقيًا مثالًا (ABSORPTION_BUY —
مرشح امتصاص شرائي كامل الشروط §12.3) عبر الناشر نفسه بتوسعة البروتوكول
(EmittedEventLike) على الموضوع ``market.event.example.1m.absorption_buy``
— إثبات توصيل مسار أحداث التدفق من كواشف المرحلة 4.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import schemas
import structlog
from common.config import load_settings

log = structlog.get_logger(__name__)


async def _probe_nats(url: str) -> str:
    try:
        from nats.aio.client import Client as NATSClient

        nc: NATSClient = NATSClient()
        await nc.connect(servers=[url], connect_timeout=3, max_reconnect_attempts=1)
        await nc.flush()
        await nc.drain()
        return "ok"
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


async def _probe_pg(url: str) -> str:
    try:
        import asyncpg

        conn = await asyncio.wait_for(asyncpg.connect(url), timeout=3)
        await conn.fetchval("SELECT 1")
        await conn.close()
        return "ok"
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


async def _publish_demo_snapshot(nats_url: str) -> str:
    """تشغيل تجريبي: بث لقطة مثال §32 حرفيًا عبر SnapshotPublisher مرة واحدة.

    القيم هي مثال §32 نفسه (instrument=EXAMPLE، timeframe=5m،
    regime=TREND_PULLBACK، htf_bias=BULLISH، volatility_percentile=62.4،
    HEALTHY عند 2026-09-27T02:00:00Z): توثيق تنفيذي لشكل الرسالة القانونية
    على الموضوع ``market.state.example.5m.updated``. بناء اللقطة هنا مباشر
    من schemas (المرحلة الحالية نبض — بنّاء الدمج من market_state يُوصَّل
    مع باقي خط الأنابيب في مرحلة الابتلاع الحية). الفشل غير قاتل: يُسجَّل
    في نبضة التشغيل الأولى ولا يوقف العملية.
    """
    try:
        from nats.aio.client import Client as NATSClient

        from engine_worker.publisher import SnapshotPublisher

        nc: NATSClient = NATSClient()
        await nc.connect(servers=[nats_url], connect_timeout=3, max_reconnect_attempts=1)
        try:
            publisher = SnapshotPublisher(nc)
            snapshot = schemas.MarketStateSnapshot(
                instrument="EXAMPLE",
                timeframe="5m",
                event_time=datetime(2026, 9, 27, 2, 0, tzinfo=UTC),
                regime=schemas.MarketRegime.TREND_PULLBACK,
                htf_bias=schemas.HTFBias.BULLISH,
                volatility_percentile=62.4,
                data_quality=schemas.DataQuality.HEALTHY,
            )
            await publisher.publish(snapshot)
            return f"published:{publisher.subject(snapshot.instrument, snapshot.timeframe)}"
        finally:
            await nc.drain()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


async def _publish_demo_analysis_event(nats_url: str) -> str:
    """تشغيل تجريبي: بث حدث بنيوي مثال بمغلف §32 عبر AnalysisEventPublisher.

    حدث INTERNAL_BOS مثالي (كسر داخلي صاعد عند 2026-09-27T02:05:00Z
    للمستوى sw-h-example) — المغلف بمعرف event_id حتمي (روح D-07) عبر
    build_envelope (المصنع النقي — receive_time = event_time في هذا
    التوثيق التنفيذي). الفشل غير قاتل كعاده.
    """
    try:
        from nats.aio.client import Client as NATSClient
        from structure.events import EmittedEvent

        from engine_worker.analysis_publisher import AnalysisEventPublisher, build_envelope

        nc: NATSClient = NATSClient()
        await nc.connect(servers=[nats_url], connect_timeout=3, max_reconnect_attempts=1)
        try:
            publisher = AnalysisEventPublisher(nc)
            event_time = datetime(2026, 9, 27, 2, 5, tzinfo=UTC)
            event = EmittedEvent(
                event_type=schemas.EventType.INTERNAL_BOS,
                event_time=event_time,
                payload=schemas.StructureBreakPayload(
                    instrument="EXAMPLE",
                    timeframe="1m",
                    bar_time=event_time,
                    swing_id="sw-h-example",
                    swing_scope=schemas.SwingScope.INTERNAL,
                    break_direction=schemas.BreakDirection.UP,
                    breach_distance_atr=1.4,
                    closing_acceptance=0.8,
                    follow_through=0.0,
                    choch_prior_direction=None,
                ),
            )
            envelope = build_envelope(
                event,
                "EXAMPLE",
                source="engine_worker.demo",
                trace_id="worker-demo",
                receive_time=event_time,
            )
            await publisher.publish(envelope)
            return f"published:{publisher.subject(envelope.event_type, 'EXAMPLE', '1m')}"
        finally:
            await nc.drain()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


async def _publish_demo_flow_event(nats_url: str) -> str:
    """تشغيل تجريبي (4-e): بث حدث تدفقي مثال عبر ناشر أحداث التحليل.

    ABSORPTION_BUY كامل الشروط §12.3 (عدوانية بيعية −0.62 وامتداد محدود
    0.31×ATR وفشل مواصلة متكرر) بمرشح غير مؤكد (confirmed=False — فرضية
    تؤكدها الاستجابة اللاحقة §12.2) — المغلف بمعرف event_id حتمي عبر
    build_envelope (توسعة البروتوكول — سجل orderflow.EmittedEvent).
    """
    try:
        from nats.aio.client import Client as NATSClient
        from orderflow.events import EmittedEvent as FlowEmittedEvent
        from schemas import AbsorbedPressure, AbsorptionConditions

        from engine_worker.analysis_publisher import AnalysisEventPublisher, build_envelope

        nc: NATSClient = NATSClient()
        await nc.connect(servers=[nats_url], connect_timeout=3, max_reconnect_attempts=1)
        try:
            publisher = AnalysisEventPublisher(nc)
            event_time = datetime(2026, 9, 28, 3, 5, tzinfo=UTC)
            event = FlowEmittedEvent(
                event_type=schemas.EventType.ABSORPTION_BUY,
                event_time=event_time,
                payload=schemas.AbsorptionEventPayload(
                    instrument="EXAMPLE",
                    timeframe="1m",
                    bar_time=event_time,
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
            envelope = build_envelope(
                event,
                "EXAMPLE",
                source="engine_worker.demo",
                trace_id="worker-demo-flow",
                receive_time=event_time,
            )
            await publisher.publish(envelope)
            return f"published:{publisher.subject(envelope.event_type, 'EXAMPLE', '1m')}"
        finally:
            await nc.drain()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


async def _heartbeat_forever() -> None:
    settings = load_settings()
    # تشغيلان تجريبيان قبل النبض — إثبات توصيل ناشر §32 (2-f) ومسار
    # أحداث التحليل الحتمية (3-f)
    demo_state = await _publish_demo_snapshot(settings.nats_url)
    demo_event = await _publish_demo_analysis_event(settings.nats_url)
    demo_flow = await _publish_demo_flow_event(settings.nats_url)
    await log.ainfo(
        "worker.demo_publish",
        state=demo_state,
        analysis_event=demo_event,
        flow_event=demo_flow,
        schema_version=schemas.SCHEMA_VERSION,
    )
    beat = 0
    while True:
        nats_state = await _probe_nats(settings.nats_url)
        pg_state = await _probe_pg(settings.database_url)
        beat += 1
        await log.ainfo(
            "worker.heartbeat",
            beat=beat,
            schema_version=schemas.SCHEMA_VERSION,
            nats=nats_state,
            pg=pg_state,
        )
        await asyncio.sleep(30)


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_heartbeat_forever())


if __name__ == "__main__":
    main()
