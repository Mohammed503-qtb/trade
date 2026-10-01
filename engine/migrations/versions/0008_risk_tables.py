"""الهجرة الثامنة — جداول المخاطرة والقرار ودفتر التجارب (المرحلة 8).

§31 حرفيًا:

- ``decisions`` (§31.3): «Final decision object and all gates» — قرار
  المخاطرة الواحد لكل سيناريو TRIGGERED: الأعمدة المسطحة القابلة
  للفهرسة (الرمز والاتجاه والترخيص والأساس والعدّادات والبصمة) +
  ``payload`` JSONB بالترميز القانوني للقرار كاملاً (تفسير §2.8
  والحاجب §22.3 والتحجيم §23.2 والتكاليف §25.2). upsert على
  ``decision_id`` الحتمي — قرار واحد لكل سيناريو (روح D-07).

- ``trade_intents`` (§31.4): «Approved execution specifications» — نيّة
  الأمر §24.1 للمرخَّصين حصرًا: الأعمدة المسطحة (الجانب/السياسة/
  الوقف/السقوف/الانقضاء/الميزانية) + ``payload`` بالنية كاملة. لا صف
  لمرسوم بلا قرار معتمد (FK إلى decisions).

- ``experience_ledger`` (§31.5): «Immutable one-row-per-trade or
  one-row-per-scenario experience reference» — صف السيناريو الواحد في
  MVP: الأعمدة المسطحة للتصفح (الحالة النهائية وexit_reason وMFE/MAE
  وnet_r والنظام والجلسة) + ``payload`` بسجل §29.1 كاملاً (17 حقلاً).
  unique على scenario_id — صف واحد لكل سيناريو أبدًا.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0008_risk_tables"
down_revision: Union[str, Sequence[str], None] = "0007_scenario_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: الجداول الثلاثة بفهارسها وقيودها."""
    # ── decisions (§31.3: «Final decision object and all gates») ──
    op.create_table(
        "decisions",
        # uuid5 حتمي فوق السيناريو — قرار ترخيص واحد لكل سيناريو
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("decided_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # هل رُخّص الدخول؟ — عمود سجل الرفض/الترخيص للوحة (§35.3)
        sa.Column("approved", sa.Boolean(), nullable=False),
        # أساس الرفض (§22.1/§22.2/§23.5) — NULL للمرخَّصين حصرًا
        sa.Column("rejection_basis", sa.String(length=32), nullable=True),
        # عدّادات البوابات — التصفح السريع دون فك JSONB
        sa.Column("hard_block_count", sa.Integer(), nullable=False),
        sa.Column("soft_suppression_count", sa.Integer(), nullable=False),
        # R الصافية المقدرة — NULL عند القطع قبل مرحلة الحافة
        sa.Column("estimated_net_r", sa.Double(), nullable=True),
        # بصمة إصدار معاملات المخاطرة (parameter_sets)
        sa.Column("parameter_fingerprint", sa.Text(), nullable=False),
        # القرار كاملاً بالترميز القانوني (ADR-021) — التفسير والبوابات
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
        sa.PrimaryKeyConstraint("decision_id"),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.scenario_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_decisions_symbol_decided_at",
        "decisions",
        ["symbol", "decided_at"],
    )
    # سجل الرفض للوحة (§35.3) — المرشحات الأولى على العمود المسطح
    op.create_index(
        "ix_decisions_approved",
        "decisions",
        ["approved"],
    )

    # ── trade_intents (§31.4: «Approved execution specifications») ──
    op.create_table(
        "trade_intents",
        # uuid5 حتمي فوق السيناريو — نيّة واحدة لكل سيناريو مرخَّص
        sa.Column("trade_intent_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("entry_policy", sa.String(length=32), nullable=False),
        sa.Column("stop", sa.Double(), nullable=False),
        sa.Column("max_slippage", sa.Double(), nullable=False),
        sa.Column("max_latency", sa.Double(), nullable=False),
        sa.Column("expiry", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # المخاطرة النقدية المسموحة — من التحجيم الناتج لا السقف
        sa.Column("risk_budget", sa.Double(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("trade_intent_id"),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["decisions.decision_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.scenario_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_trade_intents_symbol_expiry",
        "trade_intents",
        ["symbol", "expiry"],
    )

    # ── experience_ledger (§31.5: صف مرجعي واحد لكل تجربة) ──
    op.create_table(
        "experience_ledger",
        # uuid5 حتمي فوق السيناريو — صف واحد لكل سيناريو مُقيَّم
        sa.Column("experience_id", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        # الحالة النهائية §18.2 — تصفح «كيف تنتهي السيناريوهات المُقيَّمة»
        sa.Column("exit_state", sa.String(length=32), nullable=False),
        # سبب النهاية حرفيًا من انتقالها — لا تلخيص يعيد صياغة التوثيق
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("mfe", sa.Double(), nullable=False),
        sa.Column("mae", sa.Double(), nullable=False),
        sa.Column("holding_time", sa.Double(), nullable=False),
        sa.Column("net_r", sa.Double(), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("session", sa.String(length=32), nullable=False),
        # سجل §29.1 كاملاً (17 حقلاً) بالترميز القانوني
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("experience_id"),
        # «one-row-per-scenario»: صف واحد لكل سيناريو أبدًا — إعادة الكتابة
        # idempotent (DO NOTHING في المخزن) لا تكرار ولا تحريف
        sa.UniqueConstraint("scenario_id", name="uq_experience_ledger_scenario"),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.scenario_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_experience_ledger_symbol_exit_state",
        "experience_ledger",
        ["symbol", "exit_state"],
    )
    op.create_index(
        "ix_experience_ledger_regime",
        "experience_ledger",
        ["regime"],
    )


def downgrade() -> None:
    """الهبوط: إزالة الجداول الثلاثة بترتيب عكس الصعود (FK أولًا)."""
    op.drop_table("experience_ledger")
    op.drop_table("trade_intents")
    op.drop_table("decisions")
