"""اختبارات هجرة 0002 — جداول السلاسل الزمنية (علامة integration: تتطلب postgres حيًا).

نفس دورة 0001 عبر واجهة التشغيل الفعلية (python -m alembic من جذر المحرك):
- الصعود: upgrade head ينشئ market_events وcandles وraw_batches (§31.2 + ميتاداتا
  المخزن الخام) بأعمدتها وفهارسها الجزئية والمركبة وقيودها.
- الهبوط خطوة واحدة: downgrade 0001 يزيل جداول 0002 ويُبقي جداول 0001.
- إعادة الصعود: نفس الرؤية 0002_timeseries_tables عند تكرار upgrade head.

عقد نهائي: مهما كانت النتائج، تُترك القاعدة عند upgrade head.
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

REVISION_0002 = "0002_timeseries_tables"
REVISION_0001 = "0001_reference_tables"

# الأعمدة المتوقعة لكل جدول: الاسم → (نوع information_schema، is_nullable)
EXPECTED_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "market_events": {
        "event_id": ("uuid", "NO"),
        "instrument_id": ("uuid", "NO"),
        "venue": ("text", "NO"),
        "symbol": ("text", "NO"),
        "event_time": ("timestamp with time zone", "NO"),
        "receive_time": ("timestamp with time zone", "NO"),
        "sequence_id": ("text", "YES"),
        "price": ("numeric", "NO"),
        "quantity": ("numeric", "NO"),
        "buyer_is_maker": ("boolean", "YES"),
        "quality": ("text", "NO"),
        "source_timeframe": ("text", "NO"),
        "feed_id": ("text", "NO"),
        "source_latency_ms": ("numeric", "YES"),
    },
    "candles": {
        "instrument_id": ("text", "NO"),
        "timeframe": ("text", "NO"),
        "bar_time": ("timestamp with time zone", "NO"),
        "session_id": ("text", "NO"),
        "quality": ("text", "NO"),
        "is_closed": ("boolean", "NO"),
        "open": ("numeric", "NO"),
        "high": ("numeric", "NO"),
        "low": ("numeric", "NO"),
        "close": ("numeric", "NO"),
        "volume": ("numeric", "NO"),
        # range_ لا range — الكلمة المحجوزة تحلت بالشرطة اللاحقة (عرف SQLAlchemy)
        "range_": ("numeric", "NO"),
        "body_size": ("numeric", "NO"),
        "upper_wick": ("numeric", "NO"),
        "lower_wick": ("numeric", "NO"),
        "body_fraction": ("numeric", "NO"),
        "close_location_value": ("numeric", "NO"),
        "true_range": ("numeric", "NO"),
        "realized_volatility": ("numeric", "NO"),
    },
    "raw_batches": {
        "batch_id": ("uuid", "NO"),
        "symbol": ("text", "NO"),
        "venue": ("text", "NO"),
        "feed_id": ("text", "NO"),
        "start_time": ("timestamp with time zone", "NO"),
        "end_time": ("timestamp with time zone", "NO"),
        "event_count": ("integer", "NO"),
        "s3_bucket": ("text", "NO"),
        "s3_key": ("text", "NO"),
        "parquet_bytes": ("bigint", "NO"),
        "parquet_md5": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
}

# القيم الافتراضية المطلوبة — raw_batches فقط (created_at → now())
EXPECTED_DEFAULTS: dict[str, dict[str, str]] = {
    "raw_batches": {"created_at": "now()"},
}

# قيود CHECK المطلوبة (أسماء مكتملة البادئة من خريطة التسمية)
EXPECTED_CHECK_CONSTRAINTS = {
    "ck_market_events_price_positive",
    "ck_market_events_quantity_nonnegative",
    "ck_candles_prices_positive",
    "ck_candles_metrics_nonnegative",
    "ck_candles_fractions_in_unit_interval",
    "ck_raw_batches_counts_nonnegative",
}


def _run_alembic(*args: str) -> None:
    """تشغيل أمر alembic كما تشغّله خدمة migrate حرفيًا: python -m alembic."""
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
    """جلسة asyncpg مباشرة للتحقق من المخطط."""
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


async def _index_defs(pg: asyncpg.Connection) -> dict[str, str]:
    """أسماء الفهارس → تعريف CREATE الكامل (يكشف الجزئية WHERE من الفهرس الفريد)."""
    rows = await pg.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
    return {str(r["indexname"]): str(r["indexdef"]) for r in rows}


async def _check_constraints(pg: asyncpg.Connection) -> set[str]:
    """أسماء قيود CHECK في المخطط public."""
    rows = await pg.fetch(
        "SELECT conname FROM pg_constraint "
        "WHERE connamespace = 'public'::regnamespace AND contype = 'c'"
    )
    return {str(r["conname"]) for r in rows}


async def _constraint_defs(pg: asyncpg.Connection, kind: bytes) -> dict[str, str]:
    """تعريفات قيود نوع معين (b"p" = primary key) — الاسم → نص pg_get_constraintdef.

    عمود contype من نوع "char" المفرد في pg_catalog — asyncpg يتطلب bytes
    لمعامله لا str.
    """
    rows = await pg.fetch(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace AND contype = $1
        """,
        kind,
    )
    return {str(r["conname"]): str(r["definition"]) for r in rows}


async def _current_version(pg: asyncpg.Connection) -> str | None:
    """رأس alembic الحالي (None إن كان سجل الرؤوس فارغًا)."""
    value = await pg.fetchval("SELECT version_num FROM alembic_version")
    return None if value is None else str(value)


@pytest.mark.integration
async def test_upgrade_head_creates_timeseries_tables(pg: asyncpg.Connection) -> None:
    """الصعود: الجداول الزمنية الثلاثة بأعمدتها وأنواعها وفهارسها وقيودها (§31.2)."""
    _run_alembic("upgrade", "head")

    assert await _current_version(pg) == REVISION_0002

    for table, expected in EXPECTED_COLUMNS.items():
        actual = await _columns(pg, table)
        assert actual == expected, f"أعمدة {table} لا تطابق المتوقع: {actual!r}"

        defaults = await _defaults(pg, table)
        for column, fragment in EXPECTED_DEFAULTS.get(table, {}).items():
            assert column in defaults, f"{table}.{column} بلا قيمة افتراضية"
            assert fragment in defaults[column], (
                f"{table}.{column}: القيمة الافتراضية {defaults[column]!r} لا تحوي {fragment!r}"
            )

    # فهرس فريد جزئي: UNIQUE + WHERE sequence_id IS NOT NULL
    indexes = await _index_defs(pg)
    partial = indexes.get("ux_market_events_symbol_sequence_id", "")
    assert "UNIQUE INDEX" in partial, f"ليس فريدًا: {partial!r}"
    assert "sequence_id IS NOT NULL" in partial, f"ليس جزئيًا بشرط sequence_id: {partial!r}"

    # فهرسا القراءة الزمنية (غير فريدين)
    assert "ix_market_events_symbol_event_time" in indexes
    assert "ix_raw_batches_symbol_start_time" in indexes

    # المفتاح المركب للشمعة: الثلاثي (instrument_id, timeframe, bar_time) بترتيبه
    pks = await _constraint_defs(pg, b"p")
    assert "pk_candles" in pks, f"مفتاح candles المركب غائب: {sorted(pks)}"
    assert pks["pk_candles"] == "PRIMARY KEY (instrument_id, timeframe, bar_time)"

    # قيود CHECK الستة مكتملة البادئة
    assert await _check_constraints(pg) >= EXPECTED_CHECK_CONSTRAINTS


@pytest.mark.integration
async def test_downgrade_one_step_drops_timeseries_only(pg: asyncpg.Connection) -> None:
    """الهبوط خطوة: downgrade 0001 يزيل جداول 0002 ويُبقي الجداول المرجعية 0001."""
    _run_alembic("upgrade", "head")  # نقطة بداية مضمونة مهما كان ترتيب التشغيل
    _run_alembic("downgrade", REVISION_0001)

    rows = await pg.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables = {str(r["table_name"]) for r in rows}
    # جداول هذه الهجرة زالت كلها
    assert not (EXPECTED_COLUMNS.keys() & tables), f"بقي ما لا يجوز: {tables}"
    # الجداول المرجعية 0001 باقية لم تُمس
    assert {"instruments", "feeds", "strategies"} <= tables, f"تضررت جداول 0001: {tables}"
    assert await _current_version(pg) == REVISION_0001

    # إبقاء القاعدة عند الرأس الجديد لعقد الوحدة — نتركها عند 0001 حتى ينتهي هذا الاختبار
    # (الـfixture التلقائي يعيدها head عند ختم الوحدة)


@pytest.mark.integration
async def test_reupgrade_after_one_step_downgrade_is_idempotent(pg: asyncpg.Connection) -> None:
    """إعادة الصعود: هبوط خطوة ثم صعودان متتاليان — الرؤية نفسها بلا أثر مزدوج."""
    _run_alembic("downgrade", REVISION_0001)
    _run_alembic("upgrade", "head")
    _run_alembic("upgrade", "head")  # تكرار head = لا-عملية نظيفة (idempotence)

    assert await _current_version(pg) == REVISION_0002

    for table, expected in EXPECTED_COLUMNS.items():
        assert await _columns(pg, table) == expected, f"أعمدة {table} بعد إعادة الصعود"

    indexes = await _index_defs(pg)
    assert "ux_market_events_symbol_sequence_id" in indexes
    assert "sequence_id IS NOT NULL" in indexes["ux_market_events_symbol_sequence_id"]
    assert "ix_market_events_symbol_event_time" in indexes
    assert "ix_raw_batches_symbol_start_time" in indexes
    assert await _check_constraints(pg) >= EXPECTED_CHECK_CONSTRAINTS
