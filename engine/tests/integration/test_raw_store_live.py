"""اختبارات المخزن الخام الحية — علامة integration (PG + SeaweedFS الحقيقيان).

جولة كاملة ضد البنية الفعلية (المهمة 1.5، بوابة build_plan: كتابة/قراءة/
تعداد): ensure_bucket (idempotent)، كتابة دفعة اصطناعية صغيرة من صناعة
الاختبار (لا شبكة خارجية)، قراءتها (round-trip مطابق)، التعداد بالنطاق،
والتحقق من الميتاداتا مقابل الكائن الفعلي في S3.

قرار التنظيف موثق: الحذف الكامل بعد كل اختبار (الكائن من S3 والصف من
raw_batches) — لا تُترك دفعة اختبار موسومة، فالرأس نظيف للاختبارات
اللاحقة والمستهلك الحقيقي؛ لو فشل الاختبار قبل التنظيف يبقى الأثر
للتشخيص اليدوي (فشل صاخب خير من تنظيف صامت يحجب السبب).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from common.config import Settings, load_settings
from ingestion.raw_store import BatchNotFoundError, RawStore, build_s3_key
from minio import Minio
from schemas import TradeEvent

VENUE = "binance-usdm-futures"
FEED = "binance-usdm-aggtrades"
SYMBOL = "SYNTHTEST"  # رمز اصطناعي مميز — لا يتصادم مع بيانات فعلية
BASE_TIME = datetime(2024, 3, 5, 1, 2, 3, 456789, tzinfo=UTC)
MD5_HEX = re.compile(r"^[0-9a-f]{32}$")


def _event(index: int) -> TradeEvent:
    """حدث اصطناعي بزمن متناسب مع الفهرس — تغطية الحقول الاختيارية بالتناوب."""
    event_time = BASE_TIME + timedelta(milliseconds=index * 100)
    return TradeEvent(
        event_time_utc=event_time,
        receive_time_utc=event_time + timedelta(milliseconds=5),
        source_timeframe="1t",
        venue=VENUE,
        symbol=SYMBOL,
        feed_id=FEED,
        sequence_id=None if index % 3 == 0 else str(1000 + index),
        source_latency_ms=None if index % 2 == 0 else 1.5 * index,
        price=60_000.0 + index,
        quantity=0.001 * (index + 1),
        buyer_is_maker=None if index % 4 == 0 else bool(index % 2),
    )


def _minio_client(settings: Settings) -> Minio:
    """عميل S3 من الإعدادات المركزية — لا قيم مكتوبة في الاختبار."""
    return Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_secure,
    )


async def _cleanup_synthetic_batches(pg: asyncpg.Connection) -> None:
    """التنظيف الموثق: حذف كائنات وصفوف رمز الاختبار الاصطناعي كاملة."""
    settings = load_settings()
    rows = await pg.fetch("SELECT s3_bucket, s3_key FROM raw_batches WHERE symbol = $1", SYMBOL)
    client = _minio_client(settings)
    for row in rows:
        client.remove_object(row["s3_bucket"], row["s3_key"])
    await pg.execute("DELETE FROM raw_batches WHERE symbol = $1", SYMBOL)


@pytest.fixture
async def store() -> AsyncIterator[RawStore]:
    """مخزن خام ضد البنية الحية — يُغلق اتصالاته عند الختم."""
    s = RawStore()
    try:
        yield s
    finally:
        await s.aclose()


@pytest.fixture
async def pg() -> AsyncIterator[asyncpg.Connection]:
    """جلسة asyncpg مباشرة للتحقق من الميتاداتا والتنظيف."""
    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.mark.integration
async def test_raw_store_live_roundtrip(store: RawStore, pg: asyncpg.Connection) -> None:
    """الجولة الكاملة: bucket → كتابة → ميتاداتا → قراءة → تعداد → حذف."""
    await store.ensure_bucket()
    await store.ensure_bucket()  # idempotent — النداء المكرر آمن

    events = [_event(i) for i in range(8)]
    try:
        info = await store.write_batch(events)

        # الميتاداتا مطابقة للمدخلات والقيم المحسوبة
        assert info.symbol == SYMBOL
        assert info.venue == VENUE
        assert info.feed_id == FEED
        assert info.event_count == len(events)
        assert info.start_time == events[0].event_time_utc
        assert info.end_time == events[-1].event_time_utc
        assert MD5_HEX.match(info.parquet_md5), f"بصمة غير سليمة: {info.parquet_md5!r}"
        assert info.created_at is not None
        settings = load_settings()
        assert info.s3_bucket == settings.s3_bucket
        # المفتاح الموثق: raw/{venue}/{symbol}/{yyyy/mm/dd}/{batch_id}.parquet
        assert info.s3_key == build_s3_key(VENUE, SYMBOL, BASE_TIME, info.batch_id)
        assert info.s3_key == f"raw/{VENUE}/{SYMBOL}/2024/03/05/{info.batch_id}.parquet"

        # الصف في raw_batches فعلاً — القيم المخزنة تطابق ما أُعيد
        row = await pg.fetchrow("SELECT * FROM raw_batches WHERE batch_id = $1", info.batch_id)
        assert row is not None, "صف الميتاداتا لم يُدرج"
        assert row["parquet_bytes"] == info.parquet_bytes
        assert row["parquet_md5"] == info.parquet_md5

        # الكائن في S3 بحجم الملف المُعلن في الميتاداتا
        stat = _minio_client(settings).stat_object(info.s3_bucket, info.s3_key)
        assert stat.size == info.parquet_bytes

        # القراءة: round-trip مطابق (القائمة المرجعة بترتيب زمن الحدث)
        readback = await store.read_batch(info.batch_id)
        assert readback == events

        # التعداد: نطاق يتقاطع يجد الدفعة، نطاق بعيد لا يجدها
        listed = await store.list_batches(
            SYMBOL,
            start=BASE_TIME - timedelta(hours=1),
            end=BASE_TIME + timedelta(hours=1),
        )
        assert info.batch_id in {b.batch_id for b in listed}
        listed_far = await store.list_batches(
            SYMBOL,
            start=BASE_TIME + timedelta(days=30),
            end=BASE_TIME + timedelta(days=31),
        )
        assert info.batch_id not in {b.batch_id for b in listed_far}

        # دفعة غير موجودة: خطأ صريح لا صمت
        with pytest.raises(BatchNotFoundError):
            await store.read_batch(uuid.uuid4())
    finally:
        await _cleanup_synthetic_batches(pg)


@pytest.mark.integration
async def test_raw_store_live_batch_isolation(store: RawStore, pg: asyncpg.Connection) -> None:
    """دفعتان متتاليتان لا تتداخلان: معرّفان ومفتاحان مختلفان بذات المدخلات.

    حتمية المحتوى (نفس القائمة ⇒ نفس البايتات ⇒ نفس البصمة) لا تعني
    استبدال الدفعة — كل كتابة دفعة جديدة بمفتاح مستقل (قرار موثق في
    رأس الوحدة: batch_id عشوائي يمنع التصادم بين الدفعات).
    """
    try:
        events = [_event(i) for i in range(6)]
        first = await store.write_batch(events)
        second = await store.write_batch(events)
        assert first.batch_id != second.batch_id
        assert first.s3_key != second.s3_key
        assert first.parquet_md5 == second.parquet_md5  # نفس المدخلات ⇒ نفس البايتات
        assert await store.read_batch(first.batch_id) == events
        assert await store.read_batch(second.batch_id) == events

        listed = await store.list_batches(
            SYMBOL, start=BASE_TIME - timedelta(minutes=1), end=BASE_TIME + timedelta(minutes=1)
        )
        ids = {b.batch_id for b in listed}
        assert first.batch_id in ids and second.batch_id in ids
    finally:
        await _cleanup_synthetic_batches(pg)


@pytest.mark.integration
async def test_raw_store_live_leaves_no_trace(pg: asyncpg.Connection) -> None:
    """عقد النظافة: لا صفوف لرمز الاختبار الاصطناعي بعد جولات هذه الوحدة."""
    count = await pg.fetchval("SELECT count(*) FROM raw_batches WHERE symbol = $1", SYMBOL)
    assert count == 0, f"بقي أثر اختبار: {count} صفًا"
