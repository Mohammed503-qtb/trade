"""الهجرة الثانية — جداول السلاسل الزمنية (§31.2) + ميتاداتا المخزن الخام.

- ``market_events`` (§31.2 «Raw normalized trade/quote events when retained in
  the database»): الأحداث الخام المطبَّعة عند إبقائها في القاعدة. event_id
  يُفهم مفهوم ``schemas.EventEnvelope.event_id`` لكن الجدول مستقل تمامًا عن
  الظرف — الصف هنا هو TradeEvent نفسه بلا تغليف. ``instrument_id`` عمود
  uuid بلا FK: §31.2 لا ينص مفتاحًا أجنبيًا، والربط المرجعي بأداة seed
  يأتي لاحقًا مع ملء الجدول (المهمة 1.6) فلا يُستبق هنا. إزالة التكرار
  عبر فهرس فريد جزئي (symbol, sequence_id) حيث sequence_id ليس فارغًا —
  الأحداث بلا تسلسل (مصادر بلا معرف) خارج الفهرس كي لا تصطدم كأنها
  نسخ مكررة.
- ``candles`` (§31.2 + نموذج ``schemas.Candle``): مفتاح الشمعة الواحدة
  (instrument_id, timeframe, bar_time) — الشمعة المتطورة تُحدَّث في مكانها
  لا تُستنسخ (سياسة §27). ``instrument_id`` نص حر يقبل المفتاح الطبيعي
  المركب "venue:symbol" (نوع الحقل في schemas هو str) — الربط بـ UUID
  الأدوات مرحلة لاحقة مع seed. عمود المدى اسمه ``range_`` بشرطة سفلية
  لاحقة (لا ``range`` المحجوزة): هذا هو العرف الذي يتبعه SQLAlchemy نفسه
  للأسماء المحجوزة (``metadata_``)، ويبقى العمود قابلاً للوصول من أي
  عميل SQL بلا اقتباس — الأنظف من الصيغة المقتبسة «range».
- ``raw_batches`` (ميتاداتا المخزن الخام — المهمة 1.5): سجل الدفعات
  المكتوبة كملفات Parquet في S3 (SeaweedFS بواجهة minio — قرار ADR-006)؛
  الخام خالد في الكائني والميتاداتا القابلة للاستعلام في PG (بنية §5.2
  من الخطة: تخزين الكائنات + سجل القاعدة).

فهرس (symbol, event_time) لمسار القراءة الزمني، وفهرس (symbol, start_time)
لـ raw_batches لتعداد دفعات رمز في نطاق. القيود أسماء مجردة البادئة —
خريطة التسمية في env.py تكملها (ck_%(table_name)s_%(constraint_name)s).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0002_timeseries_tables"
down_revision: Union[str, Sequence[str], None] = "0001_reference_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: إنشاء market_events وcandles وraw_batches بقيودها وفهارسها."""
    # ── market_events (§31.2) ──
    op.create_table(
        "market_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        # uuid بلا FK — §31.2 لا ينص مفتاحًا أجنبيًا؛ الربط المرجعي يأتي مع seed (المهمة 1.6)
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("receive_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sequence_id", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("buyer_is_maker", sa.Boolean(), nullable=True),
        sa.Column("quality", sa.Text(), nullable=False),
        sa.Column("source_timeframe", sa.Text(), nullable=False),
        sa.Column("feed_id", sa.Text(), nullable=False),
        sa.Column("source_latency_ms", sa.Numeric(), nullable=True),
        sa.PrimaryKeyConstraint("event_id", name="pk_market_events"),
        # الأسماء مجردة البادئة — خريطة التسمية في env.py تكملها (ck_%(table_name)s_%(constraint_name)s)
        sa.CheckConstraint("price > 0", name="price_positive"),
        sa.CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
    )
    # فهرس فريد جزئي: إزالة التكرار على (symbol, sequence_id) حيث التسلسل موجود فقط
    op.create_index(
        "ux_market_events_symbol_sequence_id",
        "market_events",
        ["symbol", "sequence_id"],
        unique=True,
        postgresql_where=sa.text("sequence_id IS NOT NULL"),
    )
    op.create_index(
        "ix_market_events_symbol_event_time",
        "market_events",
        ["symbol", "event_time"],
    )

    # ── candles (§31.2 + schemas.Candle) ──
    op.create_table(
        "candles",
        # نص حر — يقبل المفتاح الطبيعي المركب "venue:symbol" (نوع الحقل في schemas هو str)
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("bar_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("quality", sa.Text(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("open", sa.Numeric(), nullable=False),
        sa.Column("high", sa.Numeric(), nullable=False),
        sa.Column("low", sa.Numeric(), nullable=False),
        sa.Column("close", sa.Numeric(), nullable=False),
        sa.Column("volume", sa.Numeric(), nullable=False),
        # range_ لا range — اسم محجوز في SQL؛ الشرطة اللاحقة عرف SQLAlchemy للأسماء المحجوزة
        sa.Column("range_", sa.Numeric(), nullable=False),
        sa.Column("body_size", sa.Numeric(), nullable=False),
        sa.Column("upper_wick", sa.Numeric(), nullable=False),
        sa.Column("lower_wick", sa.Numeric(), nullable=False),
        sa.Column("body_fraction", sa.Numeric(), nullable=False),
        sa.Column("close_location_value", sa.Numeric(), nullable=False),
        sa.Column("true_range", sa.Numeric(), nullable=False),
        sa.Column("realized_volatility", sa.Numeric(), nullable=False),
        # الشمعة الواحدة مفتاحها الثلاثي — المتطورة تُحدَّث لا تُستنسخ (§27)
        sa.PrimaryKeyConstraint("instrument_id", "timeframe", "bar_time", name="pk_candles"),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="prices_positive"
        ),
        sa.CheckConstraint(
            "volume >= 0 AND range_ >= 0 AND body_size >= 0 AND upper_wick >= 0 "
            "AND lower_wick >= 0 AND true_range >= 0 AND realized_volatility >= 0",
            name="metrics_nonnegative",
        ),
        sa.CheckConstraint(
            "body_fraction >= 0 AND body_fraction <= 1 "
            "AND close_location_value >= 0 AND close_location_value <= 1",
            name="fractions_in_unit_interval",
        ),
    )

    # ── raw_batches (ميتاداتا المخزن الخام — المهمة 1.5) ──
    op.create_table(
        "raw_batches",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("feed_id", sa.Text(), nullable=False),
        sa.Column("start_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("s3_bucket", sa.Text(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("parquet_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parquet_md5", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("batch_id", name="pk_raw_batches"),
        sa.CheckConstraint(
            "event_count >= 0 AND parquet_bytes >= 0", name="counts_nonnegative"
        ),
    )
    op.create_index(
        "ix_raw_batches_symbol_start_time",
        "raw_batches",
        ["symbol", "start_time"],
    )


def downgrade() -> None:
    """الهبوط: إزالة جداول هذه الهجرة بترتيب عكسي (الفهارس تسقط مع جداولها)."""
    op.drop_table("raw_batches")
    op.drop_table("candles")
    op.drop_table("market_events")
