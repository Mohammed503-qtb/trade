"""الهجرة الرابعة — جداول تحليلات المرحلة 3: structure_events وliquidity_zones
وpattern_events (§31.3).

§31.3 حرفيًا:

- ``structure_events``: «BOS/CHoCH/swing/displacement events» — أحداث البنية
  المؤكدة من كواشف §11 (كسرات داخلية/خارجية/CHOCH والإزاحات) **ومتطرفات
  §11.1 المؤكدة** (سجل المتطرفات نفسه: القائمة تذكر swing صراحة — تُخزن
  بنوع معرف موثق SWING_CONFIRMED بلا بث NATS لأن قاموس §20 لا يعرف نوع
  متطرف أصلًا).
- ``liquidity_zones``: «Stores every detected liquidity zone and lifecycle
  state» — كل منطقة سيولة §10.2 بحالتها التتبعية الكاملة (دورة الحياة
  §31.3) — الكتابة upsert على مفتاح zone_id الحتمي (uuid5 خالٍ من الأسعار).
- ``pattern_events``: «Candlestick, classical, harmonic, FVG, OB and phase
  detections» — طور المرحلة 3 يملأ FVG (§11.5) وOB (§11.6) والموقع
  premium/discount (§11.7 قراءة نمط موضعي — قرار موثق في ADR-021)؛
  امتداد الشموع/الكلاسيكي/الهارمونيك مسؤولية المرحلة 5a على الجدول نفسه.

الأعمدة المسطحة القابلة للفهرسة والاستعلام + ``payload`` JSONB بالترميز
القانوني للمخطط المصدَّر (مصدر الحقيقة للحقول المستقبلية) — نفس قرار
market_states في 0003. ``event_id``/``zone_id`` معرفات uuid5 حتمية (روح
D-07: إعادة الإرسال تحت عقيدة at-least-once §32 تُحدث ولا تكرر أبدًا عبر
ON CONFLICT DO UPDATE).

الفهارس: الفريد الطبيعي لكل جدول (هدف upsert) + فهرس استعلام زمني
(أداة، إطار، event_time DESC) لسلاسل «أحدث الأحداث» في الدمج (المرحلة 6).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0004_phase3_analysis_tables"
down_revision: Union[str, Sequence[str], None] = "0003_market_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: الجداول الثلاثة بفهارسها الطبيعية والزمنية."""
    # ── structure_events (§31.3: BOS/CHoCH/swing/displacement) ──
    op.create_table(
        "structure_events",
        # uuid5 حتمي من هوية الحدث الكاملة (D-07) — لا uuid4 عشوائي أبدًا
        sa.Column("event_id", sa.Uuid(), nullable=False),
        # نوع §20 (INTERNAL_BOS/EXTERNAL_BOS/CHOCH/DISPLACEMENT_UP/DISPLACEMENT_DOWN)
        # أو SWING_CONFIRMED الموثقة لسجل المتطرفات (انظر docstring الموديول)
        sa.Column("event_type", sa.String(length=31), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        # شمعة التأكيد (لا-نظرة-مستقبلية §26.3: البث/التخزين بعدها حصرًا)
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # أصناف الإحداث الخمسة للمخطط: بنية/سيولة/تدفق/فعل-سعر/تقلب-جلسة (§19.3)
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_structure_events_event_id",
        "structure_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_structure_events_instrument_timeframe_time",
        "structure_events",
        ["instrument_id", "timeframe", sa.text("event_time DESC")],
    )

    # ── liquidity_zones (§31.3: كل منطقة وحالة دورتها) ──
    op.create_table(
        "liquidity_zones",
        # uuid5 حتمي خالٍ من الأسعار (نطاق engine.liquidity.zone.v1 — عقد zones)
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        # BUY_SIDE/SELL_SIDE (§10.1)
        sa.Column("side", sa.String(length=9), nullable=False),
        sa.Column("price_low", sa.Float(), nullable=False),
        sa.Column("price_high", sa.Float(), nullable=False),
        # زمن أصل المنطقة (طابع شمعة المصدر §10.2 origin_time)
        sa.Column("origin_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # PRIOR_SWING/EQUAL_LEVEL/SESSION_EXTREME/PREV_DAY_EXTREME/PREV_WEEK_EXTREME/RANGE_BOUNDARY
        sa.Column("source_type", sa.String(length=19), nullable=False),
        # ACTIVE/SWEPT/CONSUMED/INVALIDATED — دورة الحياة §31.3
        sa.Column("state", sa.String(length=11), nullable=False),
        # تصنيف الاجتياح الخمسي §10.4 (UNKNOWN قبل أي تقييم)
        sa.Column("sweep_status", sa.String(length=17), nullable=False),
        sa.Column("test_count", sa.Integer(), nullable=False),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # درجات §10.3 داخل [0, 1] — «ليست احتمالات» (توافق أنواع schemas)
        sa.CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="liquidity_zones_importance_range",
        ),
    )
    op.create_index("ux_liquidity_zones_zone_id", "liquidity_zones", ["zone_id"], unique=True)
    op.create_index(
        "ix_liquidity_zones_instrument_timeframe_state",
        "liquidity_zones",
        ["instrument_id", "timeframe", "state"],
    )

    # ── pattern_events (§31.3: طور 3 يملأ FVG/OB/premium-discount) ──
    op.create_table(
        "pattern_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        # FVG_BULLISH/FVG_BEARISH/ORDER_BLOCK_BULLISH/ORDER_BLOCK_BEARISH/
        # PREMIUM_LOCATION/DISCOUNT_LOCATION (§20) — والمرحلة 5a توسع
        sa.Column("event_type", sa.String(length=31), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ux_pattern_events_event_id", "pattern_events", ["event_id"], unique=True)
    op.create_index(
        "ix_pattern_events_instrument_timeframe_time",
        "pattern_events",
        ["instrument_id", "timeframe", sa.text("event_time DESC")],
    )


def downgrade() -> None:
    """الهبوط: إسقاط الثلاثة مع فهارسها (عمليات عكسية نظيفة)."""
    op.drop_table("pattern_events")
    op.drop_table("liquidity_zones")
    op.drop_table("structure_events")
