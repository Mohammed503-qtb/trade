"""نقطة دخول worker — إعداد البنية التحتية المشتركة ثم تشغيل الخط.

المرحلة 0: إثبات الطوبولوجيا فقط (اتصال + نبض). خط الأنابيب الحقيقي
يبدأ من المرحلة 1 (ingestion) ويتراكم حتى المرحلة 8 (risk).
"""

from __future__ import annotations

import asyncio
import contextlib

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


async def _heartbeat_forever() -> None:
    settings = load_settings()
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
