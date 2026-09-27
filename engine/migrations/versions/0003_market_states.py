"""الهجرة الثالثة — جدول لقطات حالة السوق market_states (§31.3 + مثال §32).

§31.3 حرفيًا: ``market_states`` «Stores regime, HTF/MTF state, volatility
state, session state, and quality state» — لقطة حالة السوق المبثوثة عند كل
شمعة مغلقة (المهمة 2-f). النموذج القانوني ``schemas.MarketStateSnapshot``
(مثال §32) والأعمدة المسطحة القابلة للاستعلام والفهرسة:

- ``instrument_id`` عمود uuid بترميز ``uuid5(namespace, "venue:symbol")``
  الحتمي نفسه المعتمد في ingestion.market_store (المهمة 1.6): الأداة نفسها
  ⇒ المعرف نفسه عبر الجلسات والإعادات. بلا FK — §31.3 لا ينص مفتاحًا
  أجنبيًا (نفس قرار market_events في 0002).
- ``timeframe`` VARCHAR(8) و``event_time`` timestamptz — مفتاح اللقطة
  الزمني (أداة، إطار، لحظة).
- ``regime`` VARCHAR(31) و``htf_bias`` VARCHAR(15) و``data_quality``
  VARCHAR(23): فوق أطوال قيم التعدادات (أطولها 16/10/12 حرفًا) بهامش —
  قيم التعدادات UPPERCASE من schemas.enums.
- ``volatility_percentile`` DOUBLE PRECISION بقيد CLOSED RANGE توافقًا مع
  نوع ``Percentile`` في schemas (‎``ge=0, le=100`` — «مئين مغلق
  [0.0, 100.0] مثل مئين التقلب (مثال §32)») ومثال §32 نفسه (62.4):
  المئيني هنا نسبة مئوية [0, 100] لا كسرة — المحرك الموضعي يخرج كسرة
  [0, 1] وطبقة الدمج (بنّاء اللقطة 2-f) تضربها في 100 عند البناء.
- ``session_id`` VARCHAR(20): يوم UTC بصيغة ISO (متسق مع Candle.session_id)
  — يُشتق حتميًا من event_time عند التخزين.
- ``payload`` JSONB: اللقطة الكاملة بالترميز القانوني للمخطط المصدَّر
  ``MarketStateSnapshot.schema.json`` (‎additionalProperties: false) — مصدر
  الحقيقة للحقول المستقبلية؛ الأعمدة المسطحة للفهرسة والاستعلام السريع.
- ``created_at`` timestamptz بلا افتراض خادمي now() — أثر الكتابة.

idempotent بالتصميم: الفهرس الفريد (instrument_id, timeframe, event_time)
هو هدف ON CONFLICT لـDO UPDATE في المخزن — إعادة إرسال اللقطة نفسها
قانونية تحت عقيدة الإرسال مرة-على-الأقل (§32: at-least-once) فتحدَّث
الأعمدة والحمولة ولا يتكرر الصف أبدًا. وفهرس ثانٍ
(instrument_id, timeframe, event_time DESC) يخدم استعلام «أحدث لقطة»
(‎ORDER BY event_time DESC LIMIT 1) بترتيب وصول مطابق.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# معرفات المراجعة — يقرؤها alembic فقط
revision: str = "0003_market_states"
down_revision: Union[str, Sequence[str], None] = "0002_timeseries_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """الصعود: إنشاء market_states بفهرسيه (الفريد + أحدث-لقطة DESC) وقيد المقياس."""
    # ── market_states (§31.3 + مثال §32) ──
    op.create_table(
        "market_states",
        # uuid بترميز uuid5(namespace, "venue:symbol") الحتمي — قرار market_events في 0002
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("event_time", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("regime", sa.String(length=31), nullable=False),
        sa.Column("htf_bias", sa.String(length=15), nullable=False),
        sa.Column("volatility_percentile", sa.Float(), nullable=False),
        sa.Column("data_quality", sa.String(length=23), nullable=False),
        sa.Column("session_id", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # مقياس المئيني [0, 100] — توافق نوع Percentile في schemas ومثال §32 (62.4)
        sa.CheckConstraint(
            "volatility_percentile >= 0 AND volatility_percentile <= 100",
            name="volatility_percentile_range",
        ),
    )
    # المفتاح الطبيعي للقطة: (أداة، إطار، لحظة) — هدف ON CONFLICT للكتابة idempotent
    op.create_index(
        "ux_market_states_instrument_timeframe_event_time",
        "market_states",
        ["instrument_id", "timeframe", "event_time"],
        unique=True,
    )
    # استعلام «أحدث لقطة»: WHERE instrument_id=? AND timeframe=? ORDER BY event_time DESC
    op.create_index(
        "ix_market_states_latest_snapshot",
        "market_states",
        ["instrument_id", "timeframe", sa.text("event_time DESC")],
    )


def downgrade() -> None:
    """الهبوط: إزالة market_states (الفهارس تسقط مع جدولها)."""
    op.drop_table("market_states")
