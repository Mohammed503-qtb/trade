"""اختبارات هجرة 0006 — جداول الدمج (علامة integration: تتطلب postgres حيًا).

نفس دورة 0002/0004/0005 عبر واجهة التشغيل الفعلية (python -m alembic من
جذر المحرك):
- الصعود: upgrade head ينشئ evidence_items (§31.3: «Every evidence input
  to fusion») وfusion_snapshots (امتداد ADR-024: أثر الاستدلال §35.3)
  بأعمدتهما وفهارسهما.
- الهبوط خطوة واحدة: downgrade 0005 يزيل جدولي 0006 ويُبقي جداول 0005.
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

REVISION_0005 = "0005_orderflow_tables"


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
    "evidence_items": {
        "evidence_id": ("uuid", "NO"),
        "scenario_id": ("text", "NO"),
        # NULL للدليل المشتق من الحالة (انحياز §9.2 بلا حدث بث)
        "event_id": ("uuid", "YES"),
        "event_type": ("character varying", "NO"),
        "evidence_group": ("character varying", "NO"),
        "event_time": ("timestamp with time zone", "NO"),
        "direction_score": ("double precision", "NO"),
        "raw_strength": ("double precision", "NO"),
        "quality": ("double precision", "NO"),
        "freshness": ("double precision", "NO"),
        "independence_discount": ("double precision", "NO"),
        "prior_weight": ("double precision", "NO"),
        "context_modifier": ("double precision", "NO"),
        "contribution": ("double precision", "NO"),
        "opposition": ("boolean", "NO"),
        "correlation_group_id": ("text", "YES"),
        "source": ("text", "NO"),
        "payload": ("jsonb", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "fusion_snapshots": {
        "snapshot_id": ("uuid", "NO"),
        "scenario_id": ("text", "NO"),
        "fusion_time": ("timestamp with time zone", "NO"),
        "direction": ("character varying", "NO"),
        "raw_evidence_score": ("double precision", "NO"),
        "vetoed": ("boolean", "NO"),
        "evidence_count": ("integer", "NO"),
        "snapshot": ("jsonb", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
}

EXPECTED_INDEXES: dict[str, set[str]] = {
    "evidence_items": {
        "ux_evidence_items_evidence_id",
        "ix_evidence_items_scenario_time",
    },
    "fusion_snapshots": {
        "ux_fusion_snapshots_scenario_time",
        "ux_fusion_snapshots_snapshot_id",
    },
}


@pytest.mark.integration
class TestMigration0006:
    async def test_upgrade_columns_and_indexes(self, pg: asyncpg.Connection) -> None:
        """الصعود: العمودان للجدولين والفهارس كما صُممت."""
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
        """الهبوط خطوة إلى 0005 ثم إعادة الصعود — دورة كاملة idempotent."""
        head = _alembic_head()
        down = _alembic("downgrade", REVISION_0005)
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
