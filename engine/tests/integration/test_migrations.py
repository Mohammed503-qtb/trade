"""اختبارات هجرة Alembic — المهمة 0.6 (علامة integration: تتطلب postgres حيًا).

دورة الحياة الكاملة عبر واجهة التشغيل الفعلية نفسها (python -m alembic من جذر
المحرك — كما تستدعيها خدمة migrate في supervisor وcompose):
- الصعود: upgrade head ينشئ الجداول المرجعية الثلاثة بأعمدتها (§31.1).
- الهبوط: downgrade base يزيل كل أثر من المخطط public.
- إعادة الصعود: نفس الرؤية 0001_reference_tables وحتمية alembic_version
  عند تكرار upgrade head.

عقد نهائي: مهما كانت نتائج الاختبارات، تُترك القاعدة عند upgrade head
(fixture تلقائي في نهاية الوحدة) — لا تُترك فارغة أبدًا.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from common.config import load_settings

ENGINE_ROOT = Path(__file__).resolve().parents[2]

# رأس السلسلة — يُحدَّث مع كل هجرة جديدة (الآن 0002_timeseries_tables)
HEAD_REVISION = "0002_timeseries_tables"

# الأعمدة المتوقعة لكل جدول (§31.1 حرفيًا): الاسم → (نوع information_schema، is_nullable)
EXPECTED_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "instruments": {
        "instrument_id": ("uuid", "NO"),
        "symbol": ("text", "NO"),
        "asset_class": ("text", "NO"),
        "venue": ("text", "NO"),
        "tick_size": ("numeric", "NO"),
        "lot_size": ("numeric", "NO"),
        "quote_currency": ("text", "NO"),
        "contract_multiplier": ("numeric", "NO"),
        "status": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "feeds": {
        "feed_id": ("uuid", "NO"),
        "provider": ("text", "NO"),
        "venue": ("text", "NO"),
        "data_type": ("text", "NO"),
        "timezone": ("text", "NO"),
        "latency_profile": ("text", "YES"),
        "methodology_version": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "strategies": {
        "strategy_id": ("uuid", "NO"),
        "name": ("text", "NO"),
        "description": ("text", "YES"),
        "risk_profile": ("text", "NO"),
        "version": ("text", "NO"),
        "active": ("boolean", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
}

# القيم الافتراضية المطلوبة (تُطابق جزئيًا — بأسماء information_schema المطبَّعة)
EXPECTED_DEFAULTS: dict[str, dict[str, str]] = {
    "instruments": {
        "contract_multiplier": "1",
        "status": "ACTIVE",
        "created_at": "now()",
        "updated_at": "now()",
    },
    "feeds": {"timezone": "UTC", "created_at": "now()"},
    "strategies": {"active": "false", "created_at": "now()", "updated_at": "now()"},
}

# الفهارس الفريدة الصريحة المطلوبة
EXPECTED_UNIQUE_INDEXES = {
    "ux_instruments_venue_symbol",
    "ux_feeds_provider_venue_data_type",
}

# قيود إيجابية الحقول الدقيقة (تُكمل خريطة التسمية البادئة تلقائيًا)
EXPECTED_CHECK_CONSTRAINTS = {
    "ck_instruments_tick_size_positive",
    "ck_instruments_lot_size_positive",
}


def _run_alembic(*args: str) -> None:
    """تشغيل أمر alembic كما تشغّله خدمة migrate حرفيًا: python -m alembic من جذر المحرك."""
    proc = subprocess.run(  # noqa: S603 — مفسرنا وموديولنا الثابت، لا مدخل خارجي
        [sys.executable, "-m", "alembic", *args],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"فشل alembic {' '.join(args)} بخروج {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


@pytest.fixture
async def pg() -> AsyncIterator[asyncpg.Connection]:
    """جلسة asyncpg مباشرة للتحقق من المخطط — لا عميل psql في هذا التوزيع."""
    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture(autouse=True, scope="module")
def _finish_at_head() -> Iterator[None]:
    """العقد النهائي: أيًا كانت النتائج، القاعدة تُترك عند upgrade head."""
    yield
    _run_alembic("upgrade", "head")


async def _columns(pg: asyncpg.Connection, table: str) -> dict[str, tuple[str, str]]:
    """أعمدة جدول من information_schema: الاسم → (النوع، قابلية الإلغاء)."""
    rows = await pg.fetch(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {str(r["column_name"]): (str(r["data_type"]), str(r["is_nullable"])) for r in rows}


async def _defaults(pg: asyncpg.Connection, table: str) -> dict[str, str]:
    """القيم الافتراضية لجدول من information_schema (الأعمدة غير المفترضة غائبة)."""
    rows = await pg.fetch(
        """
        SELECT column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1 AND column_default IS NOT NULL
        """,
        table,
    )
    return {str(r["column_name"]): str(r["column_default"]) for r in rows}


async def _public_tables(pg: asyncpg.Connection) -> set[str]:
    """كل جداول المخطط public."""
    rows = await pg.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    return {str(r["table_name"]) for r in rows}


async def _index_names(pg: asyncpg.Connection) -> set[str]:
    """أسماء فهارس المخطط public."""
    rows = await pg.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    return {str(r["indexname"]) for r in rows}


async def _check_constraints(pg: asyncpg.Connection) -> set[str]:
    """أسماء قيود CHECK في المخطط public (connamespace يرشح قيود NOT NULL المدمجة)."""
    rows = await pg.fetch(
        "SELECT conname FROM pg_constraint "
        "WHERE connamespace = 'public'::regnamespace AND contype = 'c'"
    )
    return {str(r["conname"]) for r in rows}


@pytest.mark.integration
async def test_upgrade_head_creates_reference_tables(pg: asyncpg.Connection) -> None:
    """الصعود: الجداول المرجعية الثلاثة بأعمدها وأنواعها وافتراضاتها (§31.1)."""
    _run_alembic("upgrade", "head")

    assert {"instruments", "feeds", "strategies"} <= await _public_tables(pg)

    for table, expected in EXPECTED_COLUMNS.items():
        actual = await _columns(pg, table)
        assert actual == expected, f"أعمدة {table} لا تطابق §31.1: {actual!r}"

        defaults = await _defaults(pg, table)
        for column, fragment in EXPECTED_DEFAULTS[table].items():
            assert column in defaults, f"{table}.{column} بلا قيمة افتراضية"
            assert fragment in defaults[column], (
                f"{table}.{column}: القيمة الافتراضية {defaults[column]!r} لا تحوي {fragment!r}"
            )

    assert await _index_names(pg) >= EXPECTED_UNIQUE_INDEXES
    assert await _check_constraints(pg) >= EXPECTED_CHECK_CONSTRAINTS
    # سجل رؤوس alembic نفسه موجود ويشير إلى رأسنا
    version = await pg.fetchval("SELECT version_num FROM alembic_version")
    assert version == HEAD_REVISION


@pytest.mark.integration
async def test_downgrade_base_drops_reference_tables(pg: asyncpg.Connection) -> None:
    """الهبوط: downgrade base يزيل الجداول الثلاثة ويفرّغ سجل الرؤوس."""
    _run_alembic("upgrade", "head")  # نقطة بداية مضمونة مهما كان ترتيب التشغيل
    _run_alembic("downgrade", "base")

    # الجداول المرجعية زالت كلها
    tables = await _public_tables(pg)
    assert not (EXPECTED_COLUMNS.keys() & tables), f"بقي ما لا يجوز: {tables}"

    # alembic_version قد يبقى كجدول إدارة — لكن يجب أن يكون خاليًا من الرؤوس
    assert tables <= {"alembic_version"}, f"لا يجوز بقاء غير alembic_version: {tables}"
    if "alembic_version" in tables:
        heads = await pg.fetchval("SELECT count(*) FROM alembic_version")
        assert heads == 0, "سجل الرؤوس يجب أن يخلو بعد downgrade base"


@pytest.mark.integration
async def test_reupgrade_after_downgrade_is_idempotent(pg: asyncpg.Connection) -> None:
    """إعادة الصعود: هبوط كامل ثم صعودان متتاليان — الرؤية نفسها بلا أثر مزدوج."""
    _run_alembic("downgrade", "base")
    _run_alembic("upgrade", "head")
    _run_alembic("upgrade", "head")  # تكرار head = لا-عملية نظيفة (idempotence)

    version = await pg.fetchval("SELECT version_num FROM alembic_version")
    assert version == HEAD_REVISION

    for table, expected in EXPECTED_COLUMNS.items():
        assert await _columns(pg, table) == expected, f"أعمدة {table} بعد إعادة الصعود"

    assert await _index_names(pg) >= EXPECTED_UNIQUE_INDEXES
    assert await _check_constraints(pg) >= EXPECTED_CHECK_CONSTRAINTS
