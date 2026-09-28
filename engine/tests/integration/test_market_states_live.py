"""اختبارات لقطات حالة السوق الحية (المهمة 2-f) — علامة integration.

تتطلب البنية التحتية الحية: postgres (رابط common.config.database_url —
5543 في البيئة المحلية) وNATS (nats_url — 4222).

التغطية:
- الهجرة 0003: ``alembic upgrade head`` عبر واجهة التشغيل الفعلية
  (python -m alembic من جذر المحرك) ينشئ ``market_states`` (§31.3) —
  أعمدة/أنواع/إلغائية عبر information_schema، القيمة الافتراضية created_at،
  الفهرس الفريد والفهرس DESC عبر pg_indexes، وقيود CHECK عبر pg_constraint.
- المخزن الحي: upsert ⇒ latest متطابقة ⇒ إعادة upsert نفسها idempotent
  (العدد لم يتغير) ⇒ لقطة أحدث لا تمس القديمة ⇒ نفس المفتاح بقيم جديدة
  يحدّث الصف (DO UPDATE لا DO NOTHING).
- NATS الحي (بوابة المهمة — المستهلك): عميل nats حقيقي يشترك بموضوع
  جالب، SnapshotPublisher ينشر لقطة، الاستلام خلال 5 ثوان؛ الرؤوس
  (event_type/schema_version) والحمولة تمر jsonschema ضد المخطط المصدَّر،
  ثم drain نظيف. عزل الموضوع بأداة وهمية خاصة بهذه المهمة (test-2f).

عقد النهاية: مهما كانت النتائج، تُترك القاعدة عند upgrade head.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import nats
import pytest
from common.config import Settings, load_settings
from engine_worker.publisher import SnapshotPublisher
from jsonschema import validate as jsonschema_validate
from market_state.htf_bias import HtfBiasState
from market_state.regime import RegimeState
from market_state.snapshot import SnapshotInputs, build_snapshot
from market_state.store import MarketStateStore, snapshot_instrument_uuid
from market_state.volatility import VolatilityState
from schemas import SCHEMA_VERSION, HTFBias, MarketRegime, MarketStateSnapshot
from schemas.export import GENERATED_DIR

pytestmark = pytest.mark.integration

ENGINE_ROOT = Path(__file__).resolve().parents[2]

REVISION_0002 = "0002_timeseries_tables"


def _alembic_head() -> str:
    """رأس السلسلة الفعلي عبر ‎python -m alembic heads‎ — بلا تدبيس يتقادم."""
    import subprocess
    import sys

    proc = subprocess.run(  # مفسرنا وموديولنا الثابت، لا مدخل خارجي
        [sys.executable, "-m", "alembic", "heads"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"فشل alembic heads: {proc.stderr}"
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "خرج alembic heads فارغ — لا رأس؟"
    return lines[0].split(" ")[0]


# أداة وهمية معزولة لهذه المهمة — لا يعبث بها مستهلك آخر للموضوعات
INSTRUMENT = "test-2f:SNAPSHOT"
TIMEFRAME = "5m"

SCHEMA_PATH = GENERATED_DIR / "MarketStateSnapshot.schema.json"

_T1 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
_T2 = _T1 + timedelta(minutes=5)

# الأعمدة المتوقعة: الاسم → (نوع information_schema، is_nullable)
EXPECTED_COLUMNS: dict[str, tuple[str, str]] = {
    "instrument_id": ("uuid", "NO"),
    "timeframe": ("character varying", "NO"),
    "event_time": ("timestamp with time zone", "NO"),
    "regime": ("character varying", "NO"),
    "htf_bias": ("character varying", "NO"),
    "volatility_percentile": ("double precision", "NO"),
    "data_quality": ("character varying", "NO"),
    "session_id": ("character varying", "NO"),
    "payload": ("jsonb", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
}

EXPECTED_CHECK_CONSTRAINTS = {"ck_market_states_volatility_percentile_range"}

UNIQUE_INDEX = "ux_market_states_instrument_timeframe_event_time"
LATEST_INDEX = "ix_market_states_latest_snapshot"


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


def _snapshot(event_time: datetime, regime: MarketRegime, percentile: float) -> MarketStateSnapshot:
    """لقطة عبر البنّاء الحقيقي من حالات موضعية مصنوعة يدويًا (لا كائنات مخبأة)."""
    return build_snapshot(
        SnapshotInputs(
            instrument=INSTRUMENT,
            timeframe=TIMEFRAME,
            event_time=event_time,
            regime_state=RegimeState(regime=regime, bars_seen=120, data_sufficient=True),
            bias_state=HtfBiasState(bias=HTFBias.BULLISH, bars_seen=60, data_sufficient=True),
            volatility_state=VolatilityState(
                atr=1.25,
                atr_percentile=percentile / 100.0,
                realized_vol=0.0011,
                range_expansion_percentile=0.42,
                vol_of_vol=0.12,
                gap_shock=0.05,
                spread_to_range=0.30,
                expected_holding_vol_1h=0.002,
                data_sufficient=True,
                bar_time=event_time,
            ),
        )
    )


@pytest.fixture
async def pg() -> AsyncIterator[asyncpg.Connection]:
    """جلسة asyncpg مباشرة للتحقق من المخطط وعمليات المخزن."""
    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture(autouse=True, scope="module")
def _head_contract() -> Iterator[None]:
    """العقد: القاعدة عند head قبل الوحدة (جداول موجودة أيا كان الترتيب) وبعدها."""
    _run_alembic("upgrade", "head")
    yield
    _run_alembic("upgrade", "head")


async def _columns(pg: asyncpg.Connection, table: str) -> dict[str, tuple[str, str]]:
    """أعمدة جدول من information_schema: الاسم → (النوع، قابلية الإلغاء)."""
    rows = await pg.fetch(
        """
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {str(r["column_name"]): (str(r["data_type"]), str(r["is_nullable"])) for r in rows}


async def _varchar_limits(pg: asyncpg.Connection, table: str) -> dict[str, int]:
    """أطوال أعمدة character varying — تثبيت هوامش أطوال التعدادات."""
    rows = await pg.fetch(
        """
        SELECT column_name, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
          AND data_type = 'character varying'
        """,
        table,
    )
    return {str(r["column_name"]): int(r["character_maximum_length"]) for r in rows}


async def _defaults(pg: asyncpg.Connection, table: str) -> dict[str, str]:
    """القيم الافتراضية لجدول من information_schema (غير المفترضة غائبة)."""
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
    """أسماء الفهارس → تعريف CREATE الكامل (يكشف UNIQUE وDESC)."""
    rows = await pg.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
    return {str(r["indexname"]): str(r["indexdef"]) for r in rows}


async def _check_constraint_defs(pg: asyncpg.Connection) -> dict[str, str]:
    """قيود CHECK — الاسم → نص pg_get_constraintdef."""
    rows = await pg.fetch(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace AND contype = 'c'
        """
    )
    return {str(r["conname"]): str(r["definition"]) for r in rows}


async def _current_version(pg: asyncpg.Connection) -> str | None:
    """رأس alembic الحالي (None إن كان سجل الرؤوس فارغًا)."""
    value = await pg.fetchval("SELECT version_num FROM alembic_version")
    return None if value is None else str(value)


@pytest.mark.integration
async def test_upgrade_head_creates_market_states(pg: asyncpg.Connection) -> None:
    """الهجرة: market_states بأعمدته وأنواعه وفهرسيه وقيد المقياس (§31.3)."""
    _run_alembic("upgrade", "head")
    assert await _current_version(pg) == _alembic_head()

    assert await _columns(pg, "market_states") == EXPECTED_COLUMNS, (
        "أعمدة market_states لا تطابق المتوقع"
    )

    # أطوال VARCHAR فوق أطوال قيم التعدادات بهامش (8/31/15/23/20)
    limits = await _varchar_limits(pg, "market_states")
    assert limits == {
        "timeframe": 8,
        "regime": 31,
        "htf_bias": 15,
        "data_quality": 23,
        "session_id": 20,
    }

    # created_at بلا افتراض خادمي now()
    defaults = await _defaults(pg, "market_states")
    assert "now()" in defaults.get("created_at", "")

    indexes = await _index_defs(pg)
    # الفهرس الفريد — هدف ON CONFLICT للكتابة idempotent
    unique = indexes.get(UNIQUE_INDEX, "")
    assert "UNIQUE INDEX" in unique, f"ليس فريدًا: {unique!r}"
    for column in ("instrument_id", "timeframe", "event_time"):
        assert column in unique, f"العمود {column} غائب عن الفهرس الفريد: {unique!r}"
    # فهرس أحدث-لقطة — الترتيب التنازلي الصريح لمسار ORDER BY event_time DESC
    latest = indexes.get(LATEST_INDEX, "")
    assert "event_time DESC" in latest, f"ليس تنازليًا عند event_time: {latest!r}"

    checks = await _check_constraint_defs(pg)
    assert set(checks) >= EXPECTED_CHECK_CONSTRAINTS
    percentile_check = checks["ck_market_states_volatility_percentile_range"]
    assert "volatility_percentile" in percentile_check
    assert "0" in percentile_check and "100" in percentile_check, (
        f"قيد المقياس ليس [0,100]: {percentile_check!r}"
    )


@pytest.mark.integration
async def test_store_upsert_latest_idempotent(pg: asyncpg.Connection) -> None:
    """المخزن الحي: upsert ⇒ latest متطابقة ⇒ idempotent ⇒ الأحدث لا يمس القديم."""
    store = MarketStateStore()
    # تنظيف أثر أي تشغيل سابق لنفس الأداة المعزولة
    await pg.execute(
        "DELETE FROM market_states WHERE instrument_id = $1",
        snapshot_instrument_uuid(INSTRUMENT),
    )

    first = _snapshot(_T1, MarketRegime.TREND_PULLBACK, 62.4)
    second = _snapshot(_T2, MarketRegime.VOLATILITY_SHOCK, 90.0)

    # الكتابة الأولى: صف واحد وlatest متطابقة (إعادة البناء عبر pydantic)
    await store.upsert_snapshot(pg, first)
    assert await store.count_snapshots(pg, INSTRUMENT) == 1
    assert await store.latest_snapshot(pg, INSTRUMENT, TIMEFRAME) == first

    # عمود الجلسة مشتق حتميًا من event_time (يوم UTC ISO — متسق مع الشمعة)
    session_id = await pg.fetchval(
        "SELECT session_id FROM market_states WHERE instrument_id = $1 AND event_time = $2",
        snapshot_instrument_uuid(INSTRUMENT),
        _T1,
    )
    assert session_id == _T1.date().isoformat()

    # الحمولة: الترميز القانوني يفك ويمر المخطط المصدَّر (مصدر الحقيقة)
    payload_text = await pg.fetchval(
        "SELECT payload::text FROM market_states WHERE instrument_id = $1 AND event_time = $2",
        snapshot_instrument_uuid(INSTRUMENT),
        _T1,
    )
    payload = json.loads(str(payload_text))
    assert payload["instrument"] == INSTRUMENT
    jsonschema_validate(payload, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

    # إعادة إرسال اللقطة نفسها: idempotent — العدد لم يتغير (مرة-على-الأقل)
    await store.upsert_snapshot(pg, first)
    assert await store.count_snapshots(pg, INSTRUMENT) == 1

    # لقطة أحدث: صف ثانٍ ولا تمس القديمة (كلا المفتاحين محفوظ)
    await store.upsert_snapshot(pg, second)
    assert await store.count_snapshots(pg, INSTRUMENT) == 2
    assert await store.latest_snapshot(pg, INSTRUMENT, TIMEFRAME) == second

    # نفس المفتاح بقيم جديدة ⇒ DO UPDATE يحدّث الصف (لا DO NOTHING)
    revised = _snapshot(_T1, MarketRegime.RANGE_BALANCE, 10.0)
    await store.upsert_snapshot(pg, revised)
    assert await store.count_snapshots(pg, INSTRUMENT) == 2  # لا تكرار
    assert await store.latest_snapshot(pg, INSTRUMENT, TIMEFRAME) == second  # الأحدث لم تُمس
    stored_regime = await pg.fetchval(
        "SELECT regime FROM market_states WHERE instrument_id = $1 AND event_time = $2",
        snapshot_instrument_uuid(INSTRUMENT),
        _T1,
    )
    assert stored_regime == "RANGE_BALANCE"

    # أداة أخرى بلا صفوف (فرع WHERE للعدّ) والعدّ الكلي يرى الصفين
    assert await store.count_snapshots(pg, "test-2f:OTHER") == 0
    assert await store.count_snapshots(pg) >= 2

    # التنظيف: إعادة الأداة المعزولة نظيفة لمنع تضخم العدّ الكلي عبر التشغيلات
    await pg.execute(
        "DELETE FROM market_states WHERE instrument_id = $1",
        snapshot_instrument_uuid(INSTRUMENT),
    )


@pytest.mark.integration
async def test_nats_live_consumer_roundtrip() -> None:
    """بوابة المهمة: مستهلك NATS حقيقي يستلم لقطة SnapshotPublisher (مثال §32).

    عزل الموضوع: الأداة الوهمية test-2f:SNAPSHOT ⇒ الموضوع
    market.state.test-2f-snapshot.5m.updated لا يشترك فيه مستهلك آخر.
    """
    settings: Settings = load_settings()
    snapshot = _snapshot(_T1, MarketRegime.TREND_PULLBACK, 62.4)

    received: list[object] = []
    got_message = asyncio.Event()

    async def _on_message(msg: object) -> None:
        received.append(msg)
        got_message.set()

    nc = await nats.connect(servers=[settings.nats_url], connect_timeout=5)
    try:
        # اشتراك جالب (wildcard) بالموضوع المعزول لهذه المهمة
        await nc.subscribe("market.state.test-2f-snapshot.*.updated", cb=_on_message)

        publisher = SnapshotPublisher(nc)
        await publisher.publish(snapshot)

        # الركض حتى الاستلام — مهلة 5 ثوان (عقد البوابة)
        await asyncio.wait_for(got_message.wait(), timeout=5.0)

        assert len(received) == 1
        msg = received[0]
        headers = getattr(msg, "headers", None)
        assert headers is not None, "بلا رؤوس — نمط §32 يقتضي event_type/schema_version"
        assert headers["event_type"] == "market.state.updated"
        assert headers["schema_version"] == SCHEMA_VERSION

        data = getattr(msg, "data", b"")
        payload = json.loads(data)
        jsonschema_validate(payload, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        decoded = MarketStateSnapshot.model_validate_json(data.decode("utf-8"))
        assert decoded == snapshot  # حمولة النبضة تفك back إلى اللقطة نفسها
    finally:
        # drain نظيف: إلغاء الاشتراك ودفع ما تبقى ثم الإغلاق
        await nc.drain()
        if not nc.is_closed:
            await nc.close()


@pytest.mark.integration
async def test_downgrade_one_step_then_reupgrade(pg: asyncpg.Connection) -> None:
    """الهبوط إلى 0002 يزيل جداول 0003/0004 معًا ثم الصعود يعيدها."""
    _run_alembic("upgrade", "head")  # نقطة بداية مضمونة
    _run_alembic("downgrade", REVISION_0002)

    rows = await pg.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables = {str(r["table_name"]) for r in rows}
    assert "market_states" not in tables, f"الجدول لم يُززل: {tables}"
    for phase3_table in ("structure_events", "liquidity_zones", "pattern_events"):
        assert phase3_table not in tables, f"جدول 0004 لم يُززل: {phase3_table}"
    assert {"market_events", "candles", "raw_batches"} <= tables, f"تضررت جداول 0002: {tables}"
    assert {"instruments", "feeds", "strategies"} <= tables, f"تضررت جداول 0001: {tables}"
    assert await _current_version(pg) == REVISION_0002

    _run_alembic("upgrade", "head")
    assert await _current_version(pg) == _alembic_head()
    assert await _columns(pg, "market_states") == EXPECTED_COLUMNS
