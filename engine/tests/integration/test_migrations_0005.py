"""اختبارات هجرة 0005 — جداول التدفق والفوتبرنت (علامة integration: تتطلب postgres حيًا).

نفس دورة 0002/0004 عبر واجهة التشغيل الفعلية (python -m alembic من جذر المحرك):
- الصعود: upgrade head ينشئ orderflow_events وfootprint_bars وfootprint_rows
  (§31.2 + §31.3) بأعمدتها وفهارسها.
- الهبوط خطوة واحدة: downgrade 0004 يزيل جداول 0005 ويُبقي جداول 0004.
- إعادة الصعود: نفس الرؤية عند تكرار upgrade head.

عقد نهائي: مهما كانت النتائج، تُترك القاعدة عند upgrade head.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest
from common.config import load_settings

ENGINE_ROOT = Path(__file__).resolve().parents[2]

REVISION_0004 = "0004_phase3_analysis_tables"


def _alembic_head() -> str:
    """رأس سلسلة الهجرات الفعلي عبر ‎python -m alembic heads‎ — بلا تدبيس يدوي."""
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"فشل alembic heads بخروج {proc.returncode}: {proc.stderr}"
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "خرج alembic heads فارغ — لا رأس في السلسلة؟"
    return lines[0].split(" ")[0]


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """تشغيل alembic بواجهته الفعلية من جذر المحرك."""
    return subprocess.run(  # noqa: S603 — مفسرنا وموديولنا الثابت، لا مدخل خارجي
        [sys.executable, "-m", "alembic", *args],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# الأعمدة المتوقعة: الاسم → (نوع information_schema، is_nullable)
EXPECTED_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "orderflow_events": {
        "event_id": ("uuid", "NO"),
        "event_type": ("character varying", "NO"),
        "instrument_id": ("uuid", "NO"),
        "timeframe": ("character varying", "NO"),
        "event_time": ("timestamp with time zone", "NO"),
        "payload": ("jsonb", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "footprint_bars": {
        "instrument_id": ("uuid", "NO"),
        "timeframe": ("character varying", "NO"),
        "bar_time": ("timestamp with time zone", "NO"),
        "quality": ("character varying", "NO"),
        "is_closed": ("boolean", "NO"),
        "source_feed": ("text", "NO"),
        "methodology": ("text", "NO"),
        "buy_volume": ("numeric", "NO"),
        "sell_volume": ("numeric", "NO"),
        "total_volume": ("numeric", "NO"),
        "delta": ("numeric", "NO"),
        "poc": ("numeric", "NO"),
        "vah": ("numeric", "NO"),
        "val": ("numeric", "NO"),
        "row_count": ("integer", "NO"),
        "buy_imbalance_count": ("integer", "NO"),
        "sell_imbalance_count": ("integer", "NO"),
        "payload": ("jsonb", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "footprint_rows": {
        "instrument_id": ("uuid", "NO"),
        "timeframe": ("character varying", "NO"),
        "bar_time": ("timestamp with time zone", "NO"),
        "price": ("numeric", "NO"),
        "buy_volume": ("numeric", "NO"),
        "sell_volume": ("numeric", "NO"),
    },
}

EXPECTED_INDEXES: dict[str, set[str]] = {
    "orderflow_events": {
        "ux_orderflow_events_event_id",
        "ix_orderflow_events_instrument_timeframe_time",
    },
    "footprint_bars": {"ux_footprint_bars_natural_key"},
    "footprint_rows": {"ux_footprint_rows_natural_key"},
}


@pytest.mark.integration
class TestMigration0005:
    async def test_upgrade_columns_and_indexes(self, pg: asyncpg.Connection) -> None:
        """الصعود: الأعمدة الثلاثة الجداول والفهارس كما صُممت."""
        for table, columns in EXPECTED_COLUMNS.items():
            rows = await pg.fetch(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table,
            )
            assert rows, f"الجدول {table} غير موجود بعد الصعود"
            actual = {r["column_name"]: (r["data_type"], r["is_nullable"]) for r in rows}
            for col, expected in columns.items():
                assert actual.get(col) == expected, f"{table}.{col}: {actual.get(col)} ≠ {expected}"

        for table, indexes in EXPECTED_INDEXES.items():
            rows = await pg.fetch(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = $1",
                table,
            )
            index_names = {r["indexname"] for r in rows}
            assert indexes <= index_names, f"فهارس {table} الناقصة: {indexes - index_names}"

    async def test_downgrade_then_reupgrade(self, pg: asyncpg.Connection) -> None:
        """الهبوط خطوة إلى 0004 ثم إعادة الصعود — دورة كاملة idempotent."""
        head = _alembic_head()
        down = _alembic("downgrade", REVISION_0004)
        assert down.returncode == 0, f"فشل الهبوط: {down.stderr}"

        for table in EXPECTED_COLUMNS:
            exists = await pg.fetchval("SELECT to_regclass($1)", f"public.{table}")
            assert exists is None, f"الجدول {table} بقي بعد الهبوط"

        up = _alembic("upgrade", "head")
        assert up.returncode == 0, f"فشل إعادة الصعود: {up.stderr}"
        for table in EXPECTED_COLUMNS:
            exists = await pg.fetchval("SELECT to_regclass($1)", f"public.{table}")
            assert exists is not None, f"الجدول {table} لم يعد بعد إعادة الصعود"
        # الرأس عاد حيث كان
        assert _alembic_head() == head


@pytest.fixture
async def pg() -> asyncpg.Connection:
    """اتصال مباشر على القاعدة الحية — تُترك القاعدة عند upgrade head دائمًا."""
    settings = load_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, f"فشل الصعود التمهيدي: {up.stderr}"
        yield conn
    finally:
        _alembic("upgrade", "head")
        await conn.close()
