"""مخزن لقطات حالة السوق — كتابة/قراءة جدول market_states (§31.3، المهمة 2-f).

نفس روح ``ingestion.market_store`` (المهمة 1.6): asyncpg مباشر، معرف أداة
حتمي، وكتابة idempotent عبر ON CONFLICT — لكن العقد هنا أرفع درجة:

- **المخزن لا يفتح اتصاله بنفسه أبدًا**: كل عملية تستقبل ``conn`` من
  المستدعي — عقد موثق يسهّل الاختبار (اتصال اختبار صريح) والمعاملات
  المركبة (الكاتب الحي قد يخزّن اللقطة ويبثها في معاملة واحدة إن شاء).

- ``instrument_id`` = ``uuid5(_INSTRUMENT_NAMESPACE, instrument)`` حيث
  ``instrument`` هو المفتاح المركب ``"venue:symbol"`` — **نفس الترميز
  الحتمي** الذي تحسبه ``ingestion.market_store.instrument_uuid(venue,
  symbol)`` لأن السلسلة المُمدّدة حرفيًا ``f"{venue}:{symbol}"`` هي المفتاح
  المركب نفسه، فينتج المعرف نفسه بتّية. عرّفنا الترميز محليًا (لا
  استيراد من ingestion — الحزمتان طبقتان متكافئتان وحزمة market_state لا
  تعتمد بنيويًا على ingestion) وثبّتنا التطابق اختباريًا بمساواة مباشرة
  مع دالة ingestion — تثبيت العرف لا تكرار للمنطق.

- ``payload`` يُكتب بالترميز القانوني ``model_dump_json()`` — نفس البايتات
  التي يبثها الناشر عبر NATS (مثال §32): مصدر حقيقة موحد للمسارين؛
  إعادة البناء تمر عبر ``model_validate`` (التحقق عبر pydantic).

- ``session_id`` (العمود) يُشتق حتميًا من ``event_time`` عبر
  :func:`market_state.snapshot.snapshot_session_id` — الصف كله قابل لإعادة
  الاشتقاق من اللقطة وحدها فلا انحراف بين مساري البناء والتخزين (متسق مع
  ``Candle.session_id`` = تاريخ الشمعة UTC).

- **idempotent بالتصميم**: ``ON CONFLICT (instrument_id, timeframe,
  event_time) DO UPDATE`` — هدف الفهرس الفريد لهجرة 0003؛ إعادة إرسال
  اللقطة نفسها (عقيدة الإرسال مرة-على-الأقل) تحدّث الأعمدة والحمولة
  ولا تكرر الصف أبدًا.
"""

from __future__ import annotations

import json
import uuid as uuid_module

import asyncpg
from schemas import MarketStateSnapshot

from market_state.snapshot import snapshot_session_id

__all__ = [
    "MarketStateStore",
    "MarketStateStoreError",
    "snapshot_instrument_uuid",
]

#: مساحة اسم معرف الأداة — نفس ترميز ingestion.market_store حرفيًا:
#: uuid5(namespace, "venue:symbol") تحديد لا عشوائية — نفس الأداة ⇒ نفس
#: المعرف دائمًا (عبر الجلسات والإعادات) إلى حين حلقة seed المرجعية.
_INSTRUMENT_NAMESPACE = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
)


class MarketStateStoreError(RuntimeError):
    """خلل في كتابة/قراءة لقطات حالة السوق — خطأ تشغيلي صريح."""


def snapshot_instrument_uuid(instrument: str) -> uuid_module.UUID:
    """معرف أداة حتمي من المفتاح المركب ``venue:symbol`` — اصطلاح 1.6 نفسه.

    ``uuid5(namespace, instrument)`` حيث ``instrument`` هو حرفيًا السلسلة
    التي تُمدِّد ``f"{venue}:{symbol}"`` في ingestion — فالمفتاح المركب
    ينتج معرف ingestion نفسه بتّية (مثبت اختباريًا بالمساواة المباشرة).
    التطابق مضمون أيضًا عبر الفواصل: ``partition(":")`` على أول فاصلة يعيد
    تركيب السلسلة نفسها.
    """
    if not instrument:
        raise MarketStateStoreError("مفتاح أداة فارغ — المتوقع «venue:symbol»")
    return uuid_module.uuid5(_INSTRUMENT_NAMESPACE, instrument)


class MarketStateStore:
    """كتابة/قراءة لقطات حالة السوق — عمليات صغيرة مستقلة على اتصال المستدعي."""

    async def upsert_snapshot(
        self, conn: asyncpg.Connection, snapshot: MarketStateSnapshot
    ) -> None:
        """كتابة لقطة idempotent على (instrument_id, timeframe, event_time).

        إعادة إرسال اللقطة نفسها تحدّث الصف (DO UPDATE) — قانونية تحت عقيدة
        الإرسال مرة-على-الأقل؛ والحمولة بالترميز القانوني للمخطط المصدَّر.
        """
        await conn.execute(
            """
            INSERT INTO market_states (
                instrument_id, timeframe, event_time, regime, htf_bias,
                volatility_percentile, data_quality, session_id, payload
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (instrument_id, timeframe, event_time) DO UPDATE SET
                regime = EXCLUDED.regime,
                htf_bias = EXCLUDED.htf_bias,
                volatility_percentile = EXCLUDED.volatility_percentile,
                data_quality = EXCLUDED.data_quality,
                session_id = EXCLUDED.session_id,
                payload = EXCLUDED.payload
            """,
            snapshot_instrument_uuid(snapshot.instrument),
            snapshot.timeframe,
            snapshot.event_time,
            snapshot.regime.value,
            snapshot.htf_bias.value,
            float(snapshot.volatility_percentile),
            snapshot.data_quality.value,
            snapshot_session_id(snapshot.event_time),
            snapshot.model_dump_json(),
        )

    async def latest_snapshot(
        self, conn: asyncpg.Connection, instrument: str, timeframe: str
    ) -> MarketStateSnapshot | None:
        """أحدث لقطة لأداة/إطار — ``ORDER BY event_time DESC LIMIT 1`` أو None.

        إعادة البناء من الصف: الحقول من الأعمدة المسطحة والتحقق عبر pydantic؛
        ``instrument`` وحده من الحمولة — uuid5 أحادي الاتجاه لا يُعكس،
        والحمولة مصدر الحقيقة للحقول غير المسطحة.
        """
        row = await conn.fetchrow(
            """
            SELECT * FROM market_states
            WHERE instrument_id = $1 AND timeframe = $2
            ORDER BY event_time DESC
            LIMIT 1
            """,
            snapshot_instrument_uuid(instrument),
            timeframe,
        )
        if row is None:
            return None
        payload = row["payload"]
        if isinstance(payload, (str, bytes, bytearray)):
            payload = json.loads(payload)
        return MarketStateSnapshot.model_validate(
            {
                "instrument": payload["instrument"],
                "timeframe": row["timeframe"],
                "event_time": row["event_time"],
                "regime": row["regime"],
                "htf_bias": row["htf_bias"],
                "volatility_percentile": float(row["volatility_percentile"]),
                "data_quality": row["data_quality"],
            }
        )

    async def count_snapshots(self, conn: asyncpg.Connection, instrument: str | None = None) -> int:
        """عدد اللقطات (لكل الأدوات أو لأداة واحدة) — للاختبارات والرصد."""
        if instrument is None:
            count = await conn.fetchval("SELECT count(*) FROM market_states")
        else:
            count = await conn.fetchval(
                "SELECT count(*) FROM market_states WHERE instrument_id = $1",
                snapshot_instrument_uuid(instrument),
            )
        return int(count or 0)
