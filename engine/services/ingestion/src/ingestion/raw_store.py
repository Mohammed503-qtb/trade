"""المخزن الخام — دفعات aggTrades كملفات Parquet في S3 + ميتاداتا في PG (المهمة 1.5).

الخام خالد في الكائني (SeaweedFS بواجهة minio — قرار ADR-006) كسلسلة ملفات
Parquet مضغوطة، والقاعدة تحمل سجل الدفعات القابل للاستعلام
(``raw_batches`` — هجرة 0002، بنية §5.2: تخزين الكائنات + سجل القاعدة).

قرارات موثقة:
- الضغط ``zstd``: نسبة أعلى من snappy بفك سريع — الأرشيف يُكتب مرة
  ويُقرأ للإعادة فقط، فحجم القرص أولوية.
- الحتمية البايتية (بوابة المرحلة 1: نفس المدخلات ⇒ نفس hash): مخطط
  أعمدة ثابت على مستوى الوحدة بترتيب تصريح ``TradeEvent`` حرفيًا (لا
  مستنبط من البيانات)، فرز مستقر حسب event_time فقط (Timsort يحفظ
  ترتيب المتساويين زمنيًا كما وردوا)، ولا طوابع كتابة في ملف Parquet
  — نفس القائمة ⇒ نفس بايتات الملف بالضبط. ``sorting_columns`` تعلن
  الفرز في ميتاداتا الملف للقراء (قراءة انتقائية لاحقة)، والفرز نفسه
  فعلناه يدويًا قبل الكتابة.
- الـhash: MD5 بـ ``usedforsecurity=False`` — غرضه التحقق من سلامة
  التنزيل لا الأمن (يتقاطع مع عرف ETag في تخزين S3)، وأوفر كلفة من
  SHA-256 على دفعات كبيرة.
- التزامن: pyarrow وminio-py متزامنان بالكامل (حاجبون للحلقة) — كل
  نداءاتهم عبر ``asyncio.to_thread``؛ asyncpg غير متزامن أصلًا فيبقى
  مباشرة.
- بنية مفتاح S3: ``raw/{venue}/{symbol}/{yyyy/mm/dd}/{batch_id}.parquet``
  حيث اليوم تاريخ أول حدث بالتوقيت UTC (تجزئة طبيعية باليوم — نطاق
  الإعادة اليومي)، وbatch_id عشوائي UUID4 يمنع التصادم بين الدفعات.
- قيد اتساق موثق: الرفع يسبق إدراج الميتاداتا؛ فشل الإدراج بعد رفع
  ناجح يترك كائنًا يتيمًا (لا معاملات موزعة في نطاق هذه المهمة) —
  يُرصد بالمصالحة اللاحقة ولا يُكتم.
- عمود ``created_at`` في PG له ``now()`` افتراضيًا — الدفعة ميتاداتا
  نقية لا تحمل أي زمن كتابة في ملفها (حتمية البايتات أولًا).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from common.config import Settings, load_settings
from minio import Minio
from schemas import TradeEvent

# ── الثوابت المعلنة (الحتمية مشروطة بها) ────────────────────────────────
# ترتيب الأعمدة ثابت بترتيب تصريح TradeEvent في schemas — لا يستنبط من البيانات
TRADE_EVENTS_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("event_time_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("receive_time_utc", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("source_timeframe", pa.string(), nullable=False),
        pa.field("venue", pa.string(), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("feed_id", pa.string(), nullable=False),
        pa.field("sequence_id", pa.string(), nullable=True),
        pa.field("source_latency_ms", pa.float64(), nullable=True),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("quantity", pa.float64(), nullable=False),
        pa.field("buyer_is_maker", pa.bool_(), nullable=True),
    ]
)

# zstd لا snappy: أرشفة تُقرأ نادرًا — النسبة أولوية (راجع رأس الوحدة)
_PARQUET_COMPRESSION = "zstd"
# إعلان الفرز في ميتاداتا الملف: عمود الزمن تصاعديًا — يقرؤه أي عميل Parquet
_PARQUET_SORTING: tuple[pq.SortingColumn, ...] = pq.SortingColumn.from_ordering(
    TRADE_EVENTS_SCHEMA, [("event_time_utc", "ascending")]
)

_INSERT_BATCH_SQL = """
    INSERT INTO raw_batches
        (batch_id, symbol, venue, feed_id, start_time, end_time, event_count,
         s3_bucket, s3_key, parquet_bytes, parquet_md5)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    RETURNING batch_id, symbol, venue, feed_id, start_time, end_time, event_count,
              s3_bucket, s3_key, parquet_bytes, parquet_md5, created_at
"""

_SELECT_BATCH_SQL = """
    SELECT batch_id, symbol, venue, feed_id, start_time, end_time, event_count,
           s3_bucket, s3_key, parquet_bytes, parquet_md5, created_at
    FROM raw_batches
    WHERE batch_id = $1
"""

_SELECT_BATCHES_SQL = """
    SELECT batch_id, symbol, venue, feed_id, start_time, end_time, event_count,
           s3_bucket, s3_key, parquet_bytes, parquet_md5, created_at
    FROM raw_batches
    WHERE symbol = $1 AND start_time <= $3 AND end_time >= $2
    ORDER BY start_time
"""


class RawStoreError(RuntimeError):
    """خطأ عام في المخزن الخام — فشل صاخب لا صمت."""


class BatchNotFoundError(RawStoreError):
    """دفعة غير موجودة في سجل الميتاداتا (raw_batches)."""


# ── دوال نقية (قابلة للاختبار بلا أي بنية تحتية) ─────────────────────────
def _as_utc(value: datetime) -> datetime:
    """تطبيع إلى UTC — عقد الوقت §7.1 (رفض الساذج مسؤولية schemas)."""
    if value.tzinfo is None:
        raise RawStoreError("طابع زمني ساذج بلا منطقة — عقد §7.1 يرفضه")
    return value.astimezone(UTC)


def _event_sort_key(event: TradeEvent) -> datetime:
    """مفتاح الفرز: زمن الحدث فقط — فرز مستقر يحفظ ترتيب المتساويين كما وردوا."""
    return event.event_time_utc


def build_s3_key(venue: str, symbol: str, batch_day: datetime, batch_id: uuid.UUID) -> str:
    """مفتاح S3: ``raw/{venue}/{symbol}/{yyyy/mm/dd}/{batch_id}.parquet``.

    اليوم تاريخ أول حدث بالتوقيت UTC (التجزئة الطبيعية للنطاق اليومي)،
    وbatch_id في الاسم يجعل كل دفعة كائنًا مستقلًا لا يُستبدل.
    """
    day = _as_utc(batch_day)
    return f"raw/{venue}/{symbol}/{day:%Y/%m/%d}/{batch_id}.parquet"


def events_to_arrow_table(events: Sequence[TradeEvent]) -> pa.Table:
    """قائمة TradeEvent → جدول Arrow بمخطط الأعمدة الثابت (بترتيب التصريح)."""
    return pa.Table.from_pydict(
        {
            "event_time_utc": [e.event_time_utc for e in events],
            "receive_time_utc": [e.receive_time_utc for e in events],
            "source_timeframe": [e.source_timeframe for e in events],
            "venue": [e.venue for e in events],
            "symbol": [e.symbol for e in events],
            "feed_id": [e.feed_id for e in events],
            "sequence_id": [e.sequence_id for e in events],
            "source_latency_ms": [e.source_latency_ms for e in events],
            "price": [e.price for e in events],
            "quantity": [e.quantity for e in events],
            "buyer_is_maker": [e.buyer_is_maker for e in events],
        },
        schema=TRADE_EVENTS_SCHEMA,
    )


def arrow_table_to_events(table: pa.Table) -> list[TradeEvent]:
    """جدول Arrow → قائمة TradeEvent (تطبيع الطوابع إلى UTC بعد القراءة)."""
    data = {name: table.column(name).to_pylist() for name in table.schema.names}
    return [
        TradeEvent(
            event_time_utc=_as_utc(data["event_time_utc"][i]),
            receive_time_utc=_as_utc(data["receive_time_utc"][i]),
            source_timeframe=data["source_timeframe"][i],
            venue=data["venue"][i],
            symbol=data["symbol"][i],
            feed_id=data["feed_id"][i],
            sequence_id=data["sequence_id"][i],
            source_latency_ms=data["source_latency_ms"][i],
            price=data["price"][i],
            quantity=data["quantity"][i],
            buyer_is_maker=data["buyer_is_maker"][i],
        )
        for i in range(table.num_rows)
    ]


def write_parquet_bytes(events: Sequence[TradeEvent]) -> bytes:
    """ترتيب الأحداث بالوقت ثم كتابة Parquet مضغوط — بايتات حتمية.

    حتمية الملف مشروطة بثوابت الوحدة (المخطط، الضغط، الفرز) ولا تعتمد
    على أي حالة — نفس القائمة تعطي نفس البايتات في كل نداء.
    """
    ordered = sorted(events, key=_event_sort_key)
    table = events_to_arrow_table(ordered)
    sink = io.BytesIO()
    pq.write_table(
        table,
        sink,
        compression=_PARQUET_COMPRESSION,
        sorting_columns=list(_PARQUET_SORTING),
    )
    return sink.getvalue()


def read_parquet_bytes(data: bytes) -> list[TradeEvent]:
    """فك بايتات Parquet → قائمة TradeEvent (round-trip مطابق)."""
    table = pq.read_table(io.BytesIO(data))
    if list(table.schema.names) != list(TRADE_EVENTS_SCHEMA.names):
        raise RawStoreError(f"ملف Parquet ليس دفعة أحداث بهذا المخطط: {list(table.schema.names)}")
    return arrow_table_to_events(table)


def _batch_bounds(events: Sequence[TradeEvent]) -> tuple[datetime, datetime]:
    """حدا الدفعة الزمنيان: أقدم وأحدث زمن حدث (بلا افتراض ترتيب القائمة)."""
    times = [e.event_time_utc for e in events]
    return min(times), max(times)


def _md5_hex(data: bytes) -> str:
    """بصمة سلامة التنزيل لا أمن — راجع رأس الوحدة (usedforsecurity=False)."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


# ── سجل الميتاداتا ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class RawBatchInfo:
    """صف سجل الدفعات raw_batches — صورة كاملة للدفعة المكتوبة في S3."""

    batch_id: uuid.UUID
    symbol: str
    venue: str
    feed_id: str
    start_time: datetime
    end_time: datetime
    event_count: int
    s3_bucket: str
    s3_key: str
    parquet_bytes: int
    parquet_md5: str
    created_at: datetime | None = None


def _row_to_info(row: Any) -> RawBatchInfo:
    """صف asyncpg من raw_batches → RawBatchInfo (أنواع PG مطابقة للحقول)."""
    return RawBatchInfo(
        batch_id=row["batch_id"],
        symbol=row["symbol"],
        venue=row["venue"],
        feed_id=row["feed_id"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        event_count=row["event_count"],
        s3_bucket=row["s3_bucket"],
        s3_key=row["s3_key"],
        parquet_bytes=row["parquet_bytes"],
        parquet_md5=row["parquet_md5"],
        created_at=row["created_at"],
    )


class RawStore:
    """المخزن الخام: كتابة/قراءة دفعات Parquet في S3 + سجل الميتاداتا في PG.

    كل الإعدادات من ``common.config`` (نقطة النهاية والمفاتيح والbucket
    والقاعدة) — لا قيم مكتوبة في الشيفرة. عمليات pyarrow وminio المتزامنة
    تُنفذ عبر ``asyncio.to_thread`` كي لا تسد حلقة الأحداث؛ asyncpg غير
    متزامن أصلًا. الإنشاء كسول للعميل والاتصالات، والإغلاق صريح عبر
    ``aclose`` أو ``async with``.
    """

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or load_settings()
        self._client: Minio | None = None
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    # ── البنية التحتية الكسولة ──
    def _minio(self) -> Minio:
        """عميل minio كسول الإنشاء من الإعدادات المركزية."""
        if self._client is None:
            s = self._settings
            self._client = Minio(
                s.s3_endpoint,
                access_key=s.s3_access_key,
                secret_key=s.s3_secret_key,
                secure=s.s3_secure,
            )
        return self._client

    async def _pg(self) -> asyncpg.Pool:
        """اتصالات PG كسولة — سقف 4 اتصالات يحمي حد postgres المحافظ."""
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    self._pool = await asyncpg.create_pool(
                        self._settings.database_url, min_size=1, max_size=4
                    )
        return self._pool

    # ── العمليات المتزامنة (تُستدعى عبر asyncio.to_thread فقط) ──
    def _ensure_bucket_sync(self) -> None:
        if not self._minio().bucket_exists(self._settings.s3_bucket):
            self._minio().make_bucket(self._settings.s3_bucket)

    def _put_object_sync(self, key: str, data: bytes) -> None:
        self._minio().put_object(self._settings.s3_bucket, key, io.BytesIO(data), length=len(data))

    def _get_object_sync(self, bucket: str, key: str) -> bytes:
        response = None
        try:
            response = self._minio().get_object(bucket, key)
            chunks: list[bytes] = []
            for chunk in response.stream(64 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    @staticmethod
    def _decode_verified_sync(data: bytes, expected_md5: str) -> list[TradeEvent]:
        """تحقق السلامة ثم فك الدفعة — بصمة لا تطابق تعني ملفًا تالفًا/مستبدلًا."""
        actual = _md5_hex(data)
        if actual != expected_md5:
            raise RawStoreError(
                f"بصمة الدفعة لا تطابق الميتاداتا — ملف تالف أو مستبدل: {actual} != {expected_md5}"
            )
        return read_parquet_bytes(data)

    # ── الواجهة العامة ──
    async def ensure_bucket(self) -> None:
        """إنشاء الbucket إن غاب — idempotent (آمنة على كل نداء)."""
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def write_batch(self, events: Sequence[TradeEvent]) -> RawBatchInfo:
        """كتابة دفعة aggTrades كملف Parquet في S3 + صف ميتاداتا في PG.

        الدفعة يجب أن تكون متجانسة: venue وsymbol وfeed_id واحدتان لكل
        الأحداث (مفتاح S3 وصف الميتاداتا واحدان لكل دفعة). الأحداث تُفرز
        داخليًا بالوقت (فرز مستقر) قبل الكتابة — حتمية البايتات.
        """
        if not events:
            raise ValueError("دفعة فارغة — لا ملف بلا أحداث")
        first = events[0]
        for field in ("venue", "symbol", "feed_id"):
            values = {getattr(e, field) for e in events}
            if len(values) != 1:
                raise ValueError(
                    f"دفعة غير متجانسة على {field}: {sorted(values)!r} — مفتاح S3 "
                    "وصف الميتاداتا واحدان لكل دفعة"
                )
            if not values.pop():
                raise ValueError(f"حقل {field} فارغ — لا يصلح جزءًا في مفتاح S3")

        # الكتابة حاجزة (pyarrow) — خارج حلقة الأحداث
        data = await asyncio.to_thread(write_parquet_bytes, events)
        batch_id = uuid.uuid4()
        start_time, end_time = _batch_bounds(events)
        key = build_s3_key(first.venue, first.symbol, start_time, batch_id)

        await asyncio.to_thread(self._put_object_sync, key, data)

        pool = await self._pg()
        row = await pool.fetchrow(
            _INSERT_BATCH_SQL,
            batch_id,
            first.symbol,
            first.venue,
            first.feed_id,
            start_time,
            end_time,
            len(events),
            self._settings.s3_bucket,
            key,
            len(data),
            _md5_hex(data),
        )
        if row is None:  # غير واقعي مع RETURNING — حرس صريح لا افتراض
            raise RawStoreError("إدراج الميتاداتا لم يعند صفًا — حالة غير متوقعة")
        return _row_to_info(row)

    async def read_batch(self, batch_id: uuid.UUID) -> list[TradeEvent]:
        """تنزيل دفعة وفكها — تحقق بصمة السلامة قبل الفك (round-trip مطابق)."""
        pool = await self._pg()
        row = await pool.fetchrow(_SELECT_BATCH_SQL, batch_id)
        if row is None:
            raise BatchNotFoundError(f"دفعة غير موجودة في سجل الميتاداتا: {batch_id}")
        data = await asyncio.to_thread(self._get_object_sync, row["s3_bucket"], row["s3_key"])
        return await asyncio.to_thread(self._decode_verified_sync, data, row["parquet_md5"])

    async def list_batches(self, symbol: str, start: datetime, end: datetime) -> list[RawBatchInfo]:
        """تعداد دفعات رمز تتقاطع مع النطاق [start, end].

        التقاطع لا الاحتواء: دفعة تبدأ قبل ``start`` وتمتد داخله تُرجَع
        (الغرض قراءة نطاق زمني كامل من الخام) — مرتبة ببداية الدفعة.
        """
        pool = await self._pg()
        rows = await pool.fetch(_SELECT_BATCHES_SQL, symbol, _as_utc(start), _as_utc(end))
        return [_row_to_info(r) for r in rows]

    async def aclose(self) -> None:
        """إغلاق اتصالات PG (عميل minio عديم الحالة — لا يغلق شيئًا)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> RawStore:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
