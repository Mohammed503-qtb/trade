"""الهجرة السابعة — جدولا السيناريوهات (§31.3 + المرحلة 7).

§31.3 حرفيًا:

- ``scenarios``: «Scenario lifecycle and thesis» — السيناريو الحالي
  بحالته وأطروحته: الأعمدة المسطحة القابلة للفهرسة (الرمز والاتجاه
  والقالب والحالة والدرجة والانقضاء) + ``payload`` JSONB بالترميز
  القانوني للنموذج كاملاً (نفس قرار ADR-021 المعتمد منذ 0003).
  upsert على ``scenario_id`` الحتمي — إعادة الإرسال تحدّث ولا تكرر.

- ``scenario_transitions``: «Immutable lifecycle transitions with
  timestamp and reason» — سجل ملحق-فقط: فهرس فريد على (السيناريو،
  من-حالة، إلى-حالة) يجعل إعادة الإرسال idempotent بلا ازدواج،
  والقراءة بترتيب الوقوع تعرض دورة الحياة كاملة قابلية للتدقيق
  (بوابة الخروج 7: كل TRIGGERED له مشغل وإبطال معرّفان).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0007_scenario_tables"
down_revision: Union[str, Sequence[str], None] = "0006_fusion_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: جدولا السيناريوهات بفهارسهما."""
    # ── scenarios (§31.3: «Scenario lifecycle and thesis») ──
    op.create_table(
        "scenarios",
        # uuid5 حتمي من (القالب، الحدث المرسي، الموقع، الاتجاه) — D-04
        sa.Column("scenario_id", sa.Text(), nullable=False),
        # رمز التداول — تجانس الأداة شرط محرك (التنافس 7.4)
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        # هوية القالب §21.2
        sa.Column("template", sa.String(length=16), nullable=False),
        # الحالة الحالية §18.2 (12 حالة)
        sa.Column("state", sa.String(length=32), nullable=False),
        # النظام المسجل لحظة الإنشاء (§18.1 regime)
        sa.Column("regime", sa.String(length=32), nullable=False),
        # الحدث المرسي المؤكد (D-04) — وصلة الأثر إلى جداول الأحداث
        sa.Column("proposed_from_event_id", sa.Uuid(), nullable=False),
        # الدرجة الخام [0, 1] — ليست احتمالًا (§2.6/قرار الإسقاط ADR-025)
        sa.Column("scenario_score", sa.Double(), nullable=False),
        # الزعنفة الزمنية (D-04) — انقضاء الترخيص
        sa.Column("expiry_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # النموذج كاملًا بالترميز القانوني (ADR-021) — السياق والموقع
        # والأطروحة والدليل والمشغل والإبطال والأهداف.
        sa.Column("payload", postgresql.JSONB(), nullable=False),
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
        sa.PrimaryKeyConstraint("scenario_id"),
    )
    op.create_index(
        "ix_scenarios_symbol_state",
        "scenarios",
        ["symbol", "state"],
    )
    op.create_index(
        "ix_scenarios_proposed_from_event_id",
        "scenarios",
        ["proposed_from_event_id"],
    )
    op.create_index(
        "ix_scenarios_expiry_time",
        "scenarios",
        ["expiry_time"],
    )

    # ── scenario_transitions (§31.3: انتقالات دورة الحياة) ──
    op.create_table(
        "scenario_transitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=False),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("transition_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # السبب المعلّل — لا انتقال بلا توثيق (§31.3 «with ... reason»)
        sa.Column("reason", sa.Text(), nullable=False),
        # النموذج كاملًا بالترميز القانوني — snapshot للانتقال قابل للتدقيق
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.scenario_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "scenario_id",
            "from_state",
            "to_state",
            "transition_time",
            name="uq_scenario_transitions_identity",
        ),
    )
    op.create_index(
        "ix_scenario_transitions_scenario_time",
        "scenario_transitions",
        ["scenario_id", "transition_time"],
    )


def downgrade() -> None:
    """الهبوط: إزالة الجدولين بترتيب عكس الصعود (FK أولًا)."""
    op.drop_table("scenario_transitions")
    op.drop_table("scenarios")
