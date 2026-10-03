"""اختبارات هجرة 0009 — جدول تنبيهات الويبهوك (علامة integration: postgres حي).

نفس دورة 0005/0008 عبر واجهة التشغيل الفعلية: صعود يخلق alerts بقيده
الفريد، هبوط خطوة يزيله، إعادة الصعود تعيد الرؤية نفسها.

عقد نهائي: مهما كانت النتائج، تُترك القاعدة عند upgrade head.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from common.config import load_settings

ENGINE_ROOT = Path(__file__).resolve().parents[2]

REVISION_0008 = "0008_risk_tables"


@pytest.fixture
async def pg() -> AsyncIterator[asyncpg.Connection]:
    """جلسة asyncpg للتحقق من المخطط — نمط test_migrations نفسه."""
    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """تشغيل alembic بواجهته الفعلية من جذر المحرك."""
    return subprocess.run(  # noqa: S603 — مفسرنا وموديولنا الثابت، لا مدخل خارجي
        [sys.executable, "-m", "alembic", *args],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
class TestMigration0009:
    async def test_upgrade_creates_alerts_with_unique_key(self, pg: asyncpg.Connection) -> None:
        proc = _alembic("upgrade", "head")
        assert proc.returncode == 0, proc.stderr
        columns = await pg.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'alerts' ORDER BY column_name"
        )
        names = {r["column_name"] for r in columns}
        assert {
            "alert_id",
            "idempotency_key",
            "schema_version",
            "source",
            "source_alert_id",
            "instrument",
            "bar_time",
            "timeframe",
            "event",
            "price",
            "raw_body",
            "status",
            "processing_result",
            "received_at",
            "processed_at",
        } <= names
        # القيد الفريد على مفتاح D-07 — جوهر الـidempotency.
        constraints = await pg.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'alerts' AND constraint_type = 'UNIQUE'"
        )
        assert any("idempotency" in r["constraint_name"] for r in constraints)

    async def test_unique_key_rejects_duplicate_alert(self, pg: asyncpg.Connection) -> None:
        proc = _alembic("upgrade", "head")
        assert proc.returncode == 0, proc.stderr
        await pg.execute(
            """
            INSERT INTO alerts (alert_id, idempotency_key, schema_version, source,
                source_alert_id, instrument, bar_time, timeframe, event, price,
                raw_body, status, received_at)
            VALUES ('a1', 'key-1', '1.0.0', 'tradingview', 'x', 'BTC', now(),
                '1', 'CHOCH', 100.0, '{}', 'RECEIVED', now())
            """
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await pg.execute(
                """
                INSERT INTO alerts (alert_id, idempotency_key, schema_version, source,
                    source_alert_id, instrument, bar_time, timeframe, event, price,
                    raw_body, status, received_at)
                VALUES ('a2', 'key-1', '1.0.0', 'tradingview', 'x', 'BTC', now(),
                    '1', 'CHOCH', 100.0, '{}', 'RECEIVED', now())
                """
            )
        await pg.execute("DELETE FROM alerts")

    async def test_downgrade_then_reupgrade(self, pg: asyncpg.Connection) -> None:
        assert _alembic("upgrade", "head").returncode == 0
        down = _alembic("downgrade", REVISION_0008)
        assert down.returncode == 0, down.stderr
        exists = await pg.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alerts')"
        )
        assert exists is False
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
        exists2 = await pg.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alerts')"
        )
        assert exists2 is True
