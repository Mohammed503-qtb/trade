"""ناشر لقطات حالة السوق عبر NATS — الرسالة القانونية لمثال §32.

عقد رفيع عمدًا (مسؤوليات النقل تبقى للمنصة/worker الخارجي):

- يقبل عميل NATS **محضّرًا** (متصلًا) — لا يتصل بنفسه ولا يدير دورة
  حياته؛ الاتصال/الإغلاق/drain مسؤولية المستدعي (عقد قابل للحقن في
  الاختبار بعميل وهمي).
- **لا يعالج إعادة الاتصال ولا التراجع** (retry/backoff) — سياسة المنصة
  أو حلقة worker الخارجية؛ الناشر يبث ويفلوش فقط.
- الترميز: ``model_dump_json()`` — الترميز القانوني للمخطط المصدَّر؛ نفس
  البايتات التي يخزنها ``MarketStateStore`` في عمود payload (مصدر حقيقة
  موحد للمسارين).
- الرؤوس (نمط §32): ``schema_version`` من ``schemas.SCHEMA_VERSION`` —
  المصدر المولَّد لا سلاسل يدوية (خاتمة §32: «must be generated/validated
  from typed schemas, not hand-maintained strings») — و``event_type:
  market.state.updated``.
- الموضوع: ``{prefix}.state.{instrument}.{timeframe}.updated`` — الأداة
  تُنظّف من كل رمز غير كلمة-حرفية إلى شرطة (تجميع المتتاليات في شرطة
  واحدة، lowercase، بلا بادئة/لاحقة شرطة) كي يبقى الموضوع رمز NATS
  قانونيًا قابلًا للاشتراك الجالب.
"""

from __future__ import annotations

import re
from typing import Protocol

import schemas
from schemas import MarketStateSnapshot

__all__ = [
    "MARKET_STATE_EVENT_TYPE",
    "NATSPublishClient",
    "SnapshotPublisher",
]

#: نوع حدث تحديث لقطة حالة السوق — نمط §32 حرفيًا
MARKET_STATE_EVENT_TYPE = "market.state.updated"

#: كل ما ليس حرفًا كلمة-حرفية (A-Z/a-z/0-9) — يُستبدل بشرطات مجمَّعة
_NON_WORD_RUN = re.compile(r"[^A-Za-z0-9]+")


class NATSPublishClient(Protocol):
    """الحد الأدنى الذي يحتاجه الناشر من عميل NATS — هيكلي قابل للحقن.

    التوقيع مطابق لعميل nats-py فيما يستدعيه الناشر (‎``publish(subject,
    payload, reply, headers)`` و``flush()``) فيحققُه أي عميل حقيقي بلا لص،
    ويحققه العميل الوهمي في الاختبارات حرفيًا.
    """

    async def publish(
        self,
        subject: str,
        payload: bytes = b"",
        reply: str = "",
        headers: dict[str, str] | None = None,
    ) -> None: ...

    async def flush(self) -> None: ...


def normalize_instrument(instrument: str) -> str:
    """تنظيف الأداة لرمز موضوع NATS — شرطات بدل غير الكلمة-الحرفية.

    المتتاليات غير الكلمة-الحرفية تُجمَّع في شرطة واحدة (``A--B__C`` ←
    ``a-b-c``) والحواف تُقلم والنتيجة lowercase — مفتاح موضوع قانوني
    قابل للاشتراك الجالب.
    """
    normalized = _NON_WORD_RUN.sub("-", instrument.strip()).strip("-").lower()
    if not normalized:
        raise ValueError(f"اسم أداة لا ينتج رمز موضوع قانونيًا (فارغ بعد التنظيف): {instrument!r}")
    return normalized


class SnapshotPublisher:
    """ناشر رفيع للقطات حالة السوق — بث وflush، لا إعادة اتصال ولا تراجع."""

    def __init__(self, nc: NATSPublishClient, subject_prefix: str = "market") -> None:
        self._nc = nc
        self._subject_prefix = subject_prefix

    def subject(self, instrument: str, timeframe: str) -> str:
        """موضوع اللقطة: ``{prefix}.state.{instrument}.{timeframe}.updated``."""
        return (
            f"{self._subject_prefix}.state.{normalize_instrument(instrument)}.{timeframe}.updated"
        )

    async def publish(self, snapshot: MarketStateSnapshot) -> None:
        """بث اللقطة بالترميز القانوني + رؤوس §32 ثم flush.

        الحمولة ``model_dump_json()`` كما هي (بايتات UTF-8) — بلا إعادة
        ترميز تعرض الدقة؛ والتحقق ضد المخطط المصدَّر مسؤولية المستهلك.
        """
        payload = snapshot.model_dump_json().encode("utf-8")
        headers = {
            "schema_version": schemas.SCHEMA_VERSION,
            "event_type": MARKET_STATE_EVENT_TYPE,
        }
        await self._nc.publish(
            self.subject(snapshot.instrument, snapshot.timeframe),
            payload,
            headers=headers,
        )
        await self._nc.flush()
