"""اختبارات وحدة المخزن الخام — بلا شبكة إطلاقًا (المهمة 1.5).

تغطي الطبقة النقية من raw_store: بنية مفتاح S3، الحتمية البايتية
(بوابة المرحلة 1: نفس المدخلات ⇒ نفس البايتات)، تحويلات الأعمدة
(قائمة TradeEvent ⇄ جدول Arrow ⇄ Parquet)، حدود الدفعة، وتحققات
الدفعات الفارغة/المختلطة قبل أي I/O (الإنشاء كسول — لا اتصال ينشأ).
ملف مؤقت محلي (tmp_path) يغطي مسار القراءة من ملف فعلي — لا S3 هنا.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from ingestion.raw_store import (
    TRADE_EVENTS_SCHEMA,
    RawStore,
    RawStoreError,
    _batch_bounds,
    _md5_hex,
    arrow_table_to_events,
    build_s3_key,
    events_to_arrow_table,
    read_parquet_bytes,
    write_parquet_bytes,
)
from schemas import TradeEvent

VENUE = "binance-usdm-futures"
FEED = "binance-usdm-aggtrades"
SYMBOL = "SYNTHTEST"
BASE_TIME = datetime(2024, 3, 5, 1, 2, 3, 456789, tzinfo=UTC)


def _event(
    index: int,
    *,
    seq: str | None = None,
    buyer_is_maker: bool | None = None,
    latency_ms: float | None = None,
    symbol: str = SYMBOL,
) -> TradeEvent:
    """صنع حدث اصطناعي بزمن متناسب مع الفهرس (فارق 100ms بين الأحداث)."""
    event_time = BASE_TIME + timedelta(milliseconds=index * 100)
    return TradeEvent(
        event_time_utc=event_time,
        receive_time_utc=event_time + timedelta(milliseconds=5),
        source_timeframe="1t",
        venue=VENUE,
        symbol=symbol,
        feed_id=FEED,
        sequence_id=seq,
        source_latency_ms=latency_ms,
        price=60_000.0 + index,
        quantity=0.001 * (index + 1),
        buyer_is_maker=buyer_is_maker,
    )


def _sample_events() -> list[TradeEvent]:
    """عينة تغطي الحقول الاختيارية: تسلسل غائب، علم غائب، كمون غائب."""
    return [
        _event(0, seq="101", buyer_is_maker=True, latency_ms=1.5),
        _event(1, seq=None, buyer_is_maker=None, latency_ms=None),
        _event(2, seq="103", buyer_is_maker=False, latency_ms=2.5),
        _event(3, seq="104", buyer_is_maker=True, latency_ms=0.0),
        _event(4, seq="105", buyer_is_maker=False, latency_ms=100.25),
    ]


# ── بنية مفتاح S3 ──────────────────────────────────────────────────────
def test_build_s3_key_structure() -> None:
    """المفتاح: raw/{venue}/{symbol}/{yyyy/mm/dd}/{batch_id}.parquet بأصفار التاريخ."""
    batch_id = uuid.uuid4()
    key = build_s3_key(VENUE, SYMBOL, BASE_TIME, batch_id)
    assert key == f"raw/{VENUE}/{SYMBOL}/2024/03/05/{batch_id}.parquet"


def test_build_s3_key_utc_normalization() -> None:
    """الطابع الواعي يطبَّع إلى UTC — طوكيو 10:00 صباحًا = 01:00 UTC نفس اليوم."""
    tokyo = timezone(timedelta(hours=9))
    batch_id = uuid.uuid4()
    key = build_s3_key(VENUE, SYMBOL, datetime(2024, 3, 5, 10, 0, 0, tzinfo=tokyo), batch_id)
    assert key == f"raw/{VENUE}/{SYMBOL}/2024/03/05/{batch_id}.parquet"


def test_build_s3_key_rejects_naive_datetime() -> None:
    """الطابع الساذج مرفوض — عقد الوقت §7.1."""
    with pytest.raises(RawStoreError, match="ساذج"):
        build_s3_key(VENUE, SYMBOL, datetime(2024, 3, 5), uuid.uuid4())


# ── تحويلات الأعمدة (قائمة ⇄ جدول Arrow) ───────────────────────────────
def test_arrow_schema_fixed_column_order() -> None:
    """ترتيب الأعمدة ثابت بترتيب تصريح TradeEvent — لا يستنبط من البيانات."""
    assert list(TRADE_EVENTS_SCHEMA.names) == [
        "event_time_utc",
        "receive_time_utc",
        "source_timeframe",
        "venue",
        "symbol",
        "feed_id",
        "sequence_id",
        "source_latency_ms",
        "price",
        "quantity",
        "buyer_is_maker",
    ]


def test_events_arrow_roundtrip_with_optional_nulls() -> None:
    """قائمة → جدول → قائمة مطابقة مع الحقول الاختيارية الفارغة."""
    events = _sample_events()
    table = events_to_arrow_table(events)
    assert table.num_rows == len(events)
    assert list(table.schema.names) == list(TRADE_EVENTS_SCHEMA.names)
    assert arrow_table_to_events(table) == events


def test_arrow_preserves_nulls_in_optional_columns() -> None:
    """الأعمدة القابلة للإلغاء تحفظ None حرفيًا (sequence_id/latency/buyer_is_maker)."""
    events = [_event(0, seq=None, buyer_is_maker=None, latency_ms=None)]
    table = events_to_arrow_table(events)
    assert table.column("sequence_id").to_pylist() == [None]
    assert table.column("buyer_is_maker").to_pylist() == [None]
    assert table.column("source_latency_ms").to_pylist() == [None]


# ── Parquet: كتابة/قراءة/حتمية ─────────────────────────────────────────
def test_parquet_bytes_roundtrip() -> None:
    """نفس القائمة: كتابة بايتات ثم فكها = القائمة الأصلية (بالترتيب الزمني)."""
    events = _sample_events()
    data = write_parquet_bytes(events)
    assert read_parquet_bytes(data) == events


def test_parquet_file_roundtrip(tmp_path: Path) -> None:
    """الملف على القرص قابل للقراءة بأي عميل Parquet قياسي (pyarrow مباشرة)."""
    path = tmp_path / "batch.parquet"
    path.write_bytes(write_parquet_bytes(_sample_events()))
    table = pq.read_table(str(path))
    assert arrow_table_to_events(table) == _sample_events()


def test_parquet_bytes_are_deterministic() -> None:
    """بوابة المرحلة 1: نفس المدخلات ⇒ نفس البايتات ⇒ نفس الـhash."""
    events = _sample_events()
    data_a = write_parquet_bytes(events)
    data_b = write_parquet_bytes(events)
    assert data_a == data_b
    assert _md5_hex(data_a) == _md5_hex(data_b)


def test_parquet_bytes_sort_by_event_time() -> None:
    """الفرز الداخلي بالزمن: قائمة مخلوطة الأزمنة تنتج بايتات الترتيب المصنف."""
    events = _sample_events()
    shuffled = [events[3], events[0], events[4], events[1], events[2]]
    # الأزمنة صارمة التزايد ⇒ الفرز يعيد الترتيب نفسه في الحالتين
    assert write_parquet_bytes(shuffled) == write_parquet_bytes(events)


def test_parquet_metadata_declares_sorting() -> None:
    """ميتاداتا الملف تعلن الفرز على عمود الزمن — للقراءة الانتقائية لاحقًا."""
    data = write_parquet_bytes(_sample_events())
    metadata = pq.read_metadata(pa.BufferReader(data))
    assert metadata.row_group(0).sorting_columns is not None
    assert len(metadata.row_group(0).sorting_columns) == 1


def test_read_parquet_rejects_foreign_schema() -> None:
    """ملف Parquet عمود مختلف (ليس دفعة أحداثنا) يُرفض صراحة لا يُفك جزئيًا."""
    foreign = pa.table({"not_a_trade_column": pa.array([1, 2, 3])})
    sink = pa.BufferOutputStream()
    pq.write_table(foreign, sink)
    with pytest.raises(RawStoreError, match="ليس دفعة أحداث"):
        read_parquet_bytes(sink.getvalue().to_pybytes())


def test_read_parquet_rejects_garbage_bytes() -> None:
    """بايتات فاسدة لا تشبه Parquet — فشل صريح من المكتبة يمر كما هو."""
    with pytest.raises(Exception, match="magic bytes not found"):
        read_parquet_bytes(b"garbage-not-parquet-at-all" * 8)


# ── حدود الدفعة ────────────────────────────────────────────────────────
def test_batch_bounds_from_unsorted_list() -> None:
    """الحدود min/max للزمن بغض النظر عن ترتيب القائمة المدخلة."""
    events = _sample_events()
    start, end = _batch_bounds(list(reversed(events)))
    assert start == BASE_TIME
    assert end == BASE_TIME + timedelta(milliseconds=4 * 100)


# ── تحقق الدفعات قبل أي I/O (إنشاء كسول — بلا شبكة) ────────────────────
async def test_write_batch_rejects_empty_batch() -> None:
    """دفعة فارغة مرفوضة قبل أي كتابة/اتصال."""
    async with RawStore() as store:
        with pytest.raises(ValueError, match="دفعة فارغة"):
            await store.write_batch([])


async def test_write_batch_rejects_mixed_streams() -> None:
    """خلط رمزين في دفعة واحدة مرفوض — مفتاح S3 وصف الميتاداتا واحدان."""
    async with RawStore() as store:
        mixed = [_event(0, symbol="BTCUSDT"), _event(1, symbol="ETHUSDT")]
        with pytest.raises(ValueError, match="غير متجانسة"):
            await store.write_batch(mixed)


async def test_write_batch_rejects_empty_symbol() -> None:
    """رمز فارغ لا يصلح جزءًا في مفتاح S3 (raw/venue//…)."""
    async with RawStore() as store:
        with pytest.raises(ValueError, match="فارغ"):
            await store.write_batch([_event(0, symbol="")])


def test_md5_hex_is_stable() -> None:
    """بصمة السلامة حتمية على نفس البايتات (مستخدمة في مقارنة التنزيل)."""
    data = write_parquet_bytes(_sample_events())
    assert _md5_hex(data) == hashlib.md5(data, usedforsecurity=False).hexdigest()
