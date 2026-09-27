"""نقطة دخول worker — إعداد البنية التحتية المشتركة ثم تشغيل الخط.

المرحلة 0: إثبات الطوبولوجيا فقط (اتصال + نبض). خط الأنابيب الحقيقي
يبدأ من المرحلة 1 (ingestion) ويتراكم حتى المرحلة 8 (risk).

المهمة 2-f: قبل النبض مباشرة، تشغيل تجريبي واحد يبث لقطة مثال §32 عبر
SnapshotPublisher — إثبات توصيل رسالة ``market.state.updated`` على NATS
الحي (لا يمس هيكل النبض إطلاقًا: حلقة القياس نفسها بلا تغيير).
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


async def _heartbeat_forever() -> None:
    settings = load_settings()
    # تشغيل تجريبي واحد قبل النبض — إثبات توصيل ناشر §32 (المهمة 2-f)
    demo_state = await _publish_demo_snapshot(settings.nats_url)
    await log.ainfo("worker.demo_publish", state=demo_state, schema_version=schemas.SCHEMA_VERSION)
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
