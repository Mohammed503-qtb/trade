"""الهجرة السادسة — جداول الدمج (§31.3 + المهمة 6-e).

§31.3 حرفيًا:

- ``evidence_items``: «Every evidence input to fusion» — كل سجل §19.1
  يدخل الدمج يخزَّن كاملًا: الأعمدة المسطحة القابلة للفهرسة (المساهمة
  الموقعة c_i والطراوة والخصم والمعارضة ومجموعة الارتباط) + ``payload``
  JSONB بالترميز القانوني للسجل كله (نفس قرار ADR-021 المعتمد في
  0003/0004/0005). ``event_id`` يقبل NULL للدليل المشتق من الحالة
  (انحياز الإطار الأعلى §9.2) — لا حدث بثّ مصدرًا له.

- ``fusion_snapshots`` (امتداد موثق لقائمة §31.3 — ADR-024): لقطة الدمج
  الكاملة عند كل لحظة قرار — درجات المجموعات المسقوفة وتوقيع الإتاحة
  وقائمة المعارضة والدرجة الخام — هي «أثر الاستدلال» (§35.3) الذي
  تعرضه اللوحة الدنيا (المرحلة 10) وتقارنه الإعادة (المرحلة 9)؛ بدون
  أرشفة اللقطات لا استعلام واحد يعرض سلسلة الدليل كاملة (بوابة الخروج
  6). upsert على (scenario_id, fusion_time): نفس لحظة القرار ⇒ نفس الصف
  (idempotent).

``evidence_id`` و``snapshot_id`` uuid5 حتمي (روح D-07) — إعادة الإرسال
تحدّث ولا تكرر. فهرس السلسلة (scenario_id, event_time) يخدم استعلام
السلسلة الواحد: الأدلة بترتيب حتمي + أحدث لقطة في جولة واحدة.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0006_fusion_tables"
down_revision: Union[str, Sequence[str], None] = "0005_orderflow_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: جدولا الدمج بفهارسهما."""
    # ── evidence_items (§31.3: كل مدخل دليل إلى الدمج) ──
    op.create_table(
        "evidence_items",
        # uuid5 حتمي من (السيناريو، هوية الحدث/الحالة) — لا uuid4 أبدًا
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        # هوية السيناريو — الدليل ملك السيناريو لا يتسرب بينها
        sa.Column("scenario_id", sa.Text(), nullable=False),
        # الحدث المصدر إن وجد — NULL للدليل المشتق من الحالة (§9.2)
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=31), nullable=False),
        sa.Column("evidence_group", sa.String(length=31), nullable=False),
        # شريط/لحظة التأكيد (لا-نظرة §26.3)
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # ── أعمدة §19.1 المسطحة القابلة للفهرسة/الاستعلام ──
        sa.Column("direction_score", sa.Double(), nullable=False),
        sa.Column("raw_strength", sa.Double(), nullable=False),
        sa.Column("quality", sa.Double(), nullable=False),
        sa.Column("freshness", sa.Double(), nullable=False),
        sa.Column("independence_discount", sa.Double(), nullable=False),
        sa.Column("prior_weight", sa.Double(), nullable=False),
        sa.Column("context_modifier", sa.Double(), nullable=False),
        # المساهمة الموقعة c_i (§19.2) مخزنة للسلسلة والتفسير والعرض
        sa.Column("contribution", sa.Double(), nullable=False),
        # قائمة المعارضة الصريحة §19.5 — علم السجل المعاكس
        sa.Column("opposition", sa.Boolean(), nullable=False),
        # مجموعة الارتباط §19.4 — NULL خارج الدفعات (دليل الحالة)
        sa.Column("correlation_group_id", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        # مصدر الحقيقة الكامل — JSONB بالترميز القانوني للسجل
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_evidence_items_evidence_id",
        "evidence_items",
        ["evidence_id"],
        unique=True,
    )
    # فهرس السلسلة: أدلة السيناريو بترتيب زمني حتمي — استعلام البوابة
    op.create_index(
        "ix_evidence_items_scenario_time",
        "evidence_items",
        ["scenario_id", sa.text("event_time ASC"), "evidence_id"],
    )

    # ── fusion_snapshots (امتداد موثق ADR-024: أثر الاستدلال §35.3) ──
    op.create_table(
        "fusion_snapshots",
        # uuid5 حتمي من (السيناريو، لحظة القرار) — إعادة الحساب نفسه
        # عند اللحظة نفسها تحدّث صفها (idempotent)
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("fusion_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        # الدرجة الخام الكلية [−1, +1] — عمود قابل للفرز والعرض
        sa.Column("raw_evidence_score", sa.Double(), nullable=False),
        sa.Column("vetoed", sa.Boolean(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        # اللقطة الكاملة — JSONB بالترميز القانوني (درجات المجموعات
        # وتوقيع الإتاحة والمعارضة والمعايرة المؤجلة)
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # لحظة القرار الواحدة للسيناريو الواحد ⇒ صف واحد (هدف upsert)
    op.create_index(
        "ux_fusion_snapshots_scenario_time",
        "fusion_snapshots",
        ["scenario_id", "fusion_time"],
        unique=True,
    )
    op.create_index(
        "ux_fusion_snapshots_snapshot_id",
        "fusion_snapshots",
        ["snapshot_id"],
        unique=True,
    )


def downgrade() -> None:
    """الهبوط: إزالة جدولي الدمج (الترتيب العكسي للإنشاء)."""
    op.drop_index("ux_fusion_snapshots_snapshot_id", table_name="fusion_snapshots")
    op.drop_index("ux_fusion_snapshots_scenario_time", table_name="fusion_snapshots")
    op.drop_table("fusion_snapshots")
    op.drop_index("ix_evidence_items_scenario_time", table_name="evidence_items")
    op.drop_index("ux_evidence_items_evidence_id", table_name="evidence_items")
    op.drop_table("evidence_items")
