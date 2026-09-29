"""الهجرة الخامسة — جداول التدفق والفوتبرنت (§31.2 + §31.3، المهمة 4-e).

§31.3 حرفيًا:

- ``orderflow_events``: «Absorption, exhaustion, delta/imbalance events» —
  أحداث التدفق الثمانية الموثقة حمولاتها في 4-a (ABSORPTION_BUY/SELL،
  FLOW_CONTINUATION_UP/DOWN، EXHAUSTION_UP/DOWN، BUY/SELL_IMBALANCE_CLUSTER)
  بنفس بنية structure_events (نفس قرار ADR-021: الأعمدة المسطحة القابلة
  للفهرسة + ``payload`` JSONB بالترميز القانوني للمخطط المصدَّر).

§31.2 حرفيًا:

- ``footprint_bars``: «buy/sell/total/delta، POC/VAH/VAL، imbalance
  summaries، source feed» — الشريط كائن متغير الحالة (المتطور يُحدَّث لا
  يُستنسخ — عقيدة الشموع نفسها): الكتابة upsert على المفتاح الطبيعي
  (instrument_id, timeframe, bar_time) و``payload`` JSONB بالفوتبرنت
  الكامل مصدر الحقيقة للحقول المستقبلية. ``methodology`` إلزامية عمودًا
  (§12.7: وسم المصدر والمنهجية في كل سجل — لا استثناء).

- ``footprint_rows``: «Only retained when required for research or a
  detected event; partitioned by date/instrument» — الاحتفاظ الصفّي مقيد
  عمدًا (لا تخزين غير محدود للمحاكاة البصرية §8.2): الكاتب يقرر أي
  أشرطة تستحق الصفوف (الأشرطة ذات الأحداث التدفقية المكتشفة)، والاستبدال
  لكل شريط idempotent (حذف ثم إدراج داخل معاملة المستدعي). التقسيم
  الفعلي بdate/instrument مؤجل إلى الخادم الهدف (قرار موثق: تقسيم PG
  التصريحي خارج need المحلية — جدول مفهرس يفي بالبوابة، والترقية
  إجرائية موصى بها عند النشر الفعلي).

``event_id`` uuid5 حتمي (روح D-07) — إعادة الإرسال (at-least-once §32)
تُحدّث ولا تكرر أبدًا عبر ON CONFLICT DO UPDATE. الفهارس: الفريد
الطبيعي لكل جدول (هدف upsert) + فهرس استعلام زمني (أداة، إطار،
event_time DESC) لسلاسل «أحدث الأحداث» في الدمج (المرحلة 6) — نفس
قرارات 0003/0004.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0005_orderflow_tables"
down_revision: Union[str, Sequence[str], None] = "0004_phase3_analysis_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: جداول التدفق الثلاثة بفهارسها الطبيعية والزمنية."""
    # ── orderflow_events (§31.3: امتصاص/إنهاك/دلتا/اختلال) ──
    op.create_table(
        "orderflow_events",
        # uuid5 حتمي من هوية الحدث الكاملة (D-07) — لا uuid4 عشوائي أبدًا
        sa.Column("event_id", sa.Uuid(), nullable=False),
        # نوع §20 التدفقي (ABSORPTION_BUY/ABSORPTION_SELL/FLOW_CONTINUATION_*/
        # EXHAUSTION_*/BUY_IMBALANCE_CLUSTER/SELL_IMBALANCE_CLUSTER)
        sa.Column("event_type", sa.String(length=31), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        # شريط التأكيد (لا-نظرة-مستقبلية §26.3: البث/التخزين بعدها حصرًا)
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # الحمولة القانونية §12+§20 — JSONB بالترميز المصدَّر
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_orderflow_events_event_id",
        "orderflow_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_orderflow_events_instrument_timeframe_time",
        "orderflow_events",
        ["instrument_id", "timeframe", sa.text("event_time DESC")],
    )

    # ── footprint_bars (§31.2: مقاييس الشريط + وسم المصدر والمنهجية §12.7) ──
    op.create_table(
        "footprint_bars",
        # المفتاح الطبيعي: (instrument_id, timeframe, bar_time) — هدف upsert
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("bar_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("quality", sa.String(length=31), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        # وسم المصدر والمنهجية إلزاميان (§12.7) — عمودان لا عمود واحد:
        # المصدر عدةُ تغذية والمنهجية عقد التصنيف ذاته
        sa.Column("source_feed", sa.Text(), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False),
        # مقاييس §8.2 المسطحة القابلة للفهرسة/الاستعلام
        sa.Column("buy_volume", sa.Numeric(), nullable=False),
        sa.Column("sell_volume", sa.Numeric(), nullable=False),
        sa.Column("total_volume", sa.Numeric(), nullable=False),
        sa.Column("delta", sa.Numeric(), nullable=False),
        sa.Column("poc", sa.Numeric(), nullable=False),
        sa.Column("vah", sa.Numeric(), nullable=False),
        sa.Column("val", sa.Numeric(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("buy_imbalance_count", sa.Integer(), nullable=False),
        sa.Column("sell_imbalance_count", sa.Integer(), nullable=False),
        # مصدر الحقيقة الكامل (المشتقات والحقول المستقبلية) — JSONB قانوني
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_footprint_bars_natural_key",
        "footprint_bars",
        ["instrument_id", "timeframe", "bar_time"],
        unique=True,
    )

    # ── footprint_rows (§31.2: احتفاظ مقيد بالأحداث المكتشفة/البحث) ──
    op.create_table(
        "footprint_rows",
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("bar_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # الصف: سعر + حجما الطرفين المتسببين (منهجية aggtrades-taker-side)
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("buy_volume", sa.Numeric(), nullable=False),
        sa.Column("sell_volume", sa.Numeric(), nullable=False),
    )
    op.create_index(
        "ux_footprint_rows_natural_key",
        "footprint_rows",
        ["instrument_id", "timeframe", "bar_time", "price"],
        unique=True,
    )


def downgrade() -> None:
    """الهبوط: إزالة جداول التدفق الثلاثة (الترتيب العكسي للإنشاء)."""
    op.drop_index("ux_footprint_rows_natural_key", table_name="footprint_rows")
    op.drop_table("footprint_rows")
    op.drop_index("ux_footprint_bars_natural_key", table_name="footprint_bars")
    op.drop_table("footprint_bars")
    op.drop_index("ix_orderflow_events_instrument_timeframe_time", table_name="orderflow_events")
    op.drop_index("ux_orderflow_events_event_id", table_name="orderflow_events")
    op.drop_table("orderflow_events")
