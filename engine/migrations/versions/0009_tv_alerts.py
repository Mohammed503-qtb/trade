"""الهجرة التاسعة — جدول تنبيهات الويبهوك (المرحلة 10).

§31.6 حرفيًا: ``alerts`` — «Webhook events and delivery status».

العقد (§36 + D-07 + D-09): كل تنبيه خام يصل الحافة يُخزن بصف واحد لا
يتغير جوهره أبدًا؛ مفتاح الـidempotency (D-07:
``sha256(schema_version|source|alert_id|instrument|bar_time|event)``)
يشتقه الخادم حصرًا ويقيد بقيد فريد — التنبيه المكرر يُقرّ بصف واحد
(§36 خطوة 3) لا صفين. حالة التسليم (AlertDeliveryStatus) تتقدم:
RECEIVED → PROCESSED أو REJECTED_CANONICAL (إعادة التحقق القانوني
خطوة 7)؛ والرفض البويّ (REJECTED_AUTH/REJECTED_SCHEMA) يخزن أيضًا
للرصد. عمود ``processing_result`` JSONB يوثق إعادة التحقق كاملة
(AlertRevalidation) — لا أمر حي في MVP (المرحلة 11 مؤجلة معلنة).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0009_tv_alerts"
down_revision: Union[str, Sequence[str], None] = "0008_risk_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: جدول alerts بفهارسه وقيوده."""
    op.create_table(
        "alerts",
        # معرف التنبيه — UUID حتمي فوق مفتاح D-07 (تسليم واحد لكل تنبيه خام)
        sa.Column("alert_id", sa.Text(), nullable=False),
        # مفتاح الـidempotency المشتق خادميًا (D-07) — قيد فريد صارم
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        # الحقول الخام الخمسة (§36) — مرجع الاشتقاق والتتبع
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_alert_id", sa.Text(), nullable=False),
        sa.Column("instrument", sa.Text(), nullable=False),
        sa.Column("bar_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("price", sa.Double(), nullable=False),
        # الجسم الخام كما وصل بايت-بايت — الأرشيف القانوني (§36 خطوة 4)
        sa.Column("raw_body", postgresql.JSONB(), nullable=False),
        # حالة التسليم (AlertDeliveryStatus) — تتقدم بالمعالجة الخلفية
        sa.Column("status", sa.String(length=32), nullable=False),
        # نتيجة إعادة التحقق القانوني (خطوة 7) — NULL قبل اكتمالها
        sa.Column("processing_result", postgresql.JSONB(), nullable=True),
        sa.Column("received_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("processed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("alert_id", name="pk_alerts"),
        sa.UniqueConstraint("idempotency_key", name="uq_alerts_idempotency_key"),
    )
    op.create_index(
        "ix_alerts_instrument_bar_time",
        "alerts",
        ["instrument", "bar_time"],
    )
    op.create_index("ix_alerts_status_received_at", "alerts", ["status", "received_at"])
    op.create_index("ix_alerts_event", "alerts", ["event"])


def downgrade() -> None:
    """الهبوط: إزالة جدول alerts وفهارسه."""
    op.drop_index("ix_alerts_event", table_name="alerts")
    op.drop_index("ix_alerts_status_received_at", table_name="alerts")
    op.drop_index("ix_alerts_instrument_bar_time", table_name="alerts")
    op.drop_table("alerts")
