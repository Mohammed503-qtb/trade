"""الهجرة الأولى — الجداول المرجعية الثلاثة (§31.1 حرفيًا).

تطابق قسم §31.1 من الخطة الأم (docs/Master Plan.md) حرفيًا في الأعمدة
وأنواعها وقيودها؛ الإضافات التشغيلية فقط هي created_at/updated_at وقيود
الإيجابية والفهارس الفريدة المطلوبة لدقة البيانات المرجعية:

- ``instruments``: الأدوات القابلة للتداول — الرمز فريد عالميًا، وtick_size
  وlot_size موجبان إجباريًا (CheckConstraint)، وpair (venue, symbol) فريد
  عبر فهرس صريح.
- ``feeds``: مصادر البيانات — منهجية كل مصدر إلزامية (methodology_version،
  اتساقًا مع §12.7 وسم منهجية الـfootprint)، والثلاثية
  (provider, venue, data_type) فريدة عبر فهرس صريح.
- ``strategies``: الاستراتيجيات المسجلة — الاسم فريد، ملف المخاطر إلزامي،
  والتفعيل false افتراضيًا (لا استراتيجية نشطة إلا بقرار صريح).

UUID عبر sa.Uuid() والطوابع الزمنية postgresql.TIMESTAMP(timezone=True)
(timestamptz). الجداول الزمنية (§31.2) والتحليلية (§31.3) تأتي مع
مراحلها — لا شيء هنا فوق §31.1.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0001_reference_tables"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: إنشاء instruments وfeeds وstrategies بقيودها وفهارسها."""
    # ── instruments (§31.1) ──
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("tick_size", sa.Numeric(), nullable=False),
        sa.Column("lot_size", sa.Numeric(), nullable=False),
        sa.Column("quote_currency", sa.Text(), nullable=False),
        sa.Column(
            "contract_multiplier",
            sa.Numeric(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("instrument_id", name="pk_instruments"),
        sa.UniqueConstraint("symbol", name="uq_instruments_symbol"),
        # الأسماء مجردة البادئة — خريطة التسمية في env.py تكملها (ck_%(table_name)s_%(constraint_name)s)
        sa.CheckConstraint("tick_size > 0", name="tick_size_positive"),
        sa.CheckConstraint("lot_size > 0", name="lot_size_positive"),
    )
    op.create_index(
        "ux_instruments_venue_symbol",
        "instruments",
        ["venue", "symbol"],
        unique=True,
    )

    # ── feeds (§31.1) ──
    op.create_table(
        "feeds",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column("latency_profile", sa.Text(), nullable=True),
        sa.Column("methodology_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("feed_id", name="pk_feeds"),
    )
    op.create_index(
        "ux_feeds_provider_venue_data_type",
        "feeds",
        ["provider", "venue", "data_type"],
        unique=True,
    )

    # ── strategies (§31.1) ──
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("risk_profile", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("strategy_id", name="pk_strategies"),
        sa.UniqueConstraint("name", name="uq_strategies_name"),
    )


def downgrade() -> None:
    """الهبوط: إزالة الجداول المرجعية بترتيب عكسي (الفهارس تسقط مع جداولها)."""
    op.drop_table("strategies")
    op.drop_table("feeds")
    op.drop_table("instruments")
