"""حوارس التدفق المشتركة لكواشف البنية — هوية وترتيب وشمع مغلقة (§26.3/§27).

عقد واحد تلتزم به كواشف البنية الثلاثة (متطرفات/كسور/إزاحة) والواجهة
الجامعة، فلا يتكرر منطق الحراسة ولا يتباين سلوكها بين كاشف وآخر:

- **الهوية**: كاشف واحد = زوج (أداة، إطار) واحد — تُلتقط من أول شمعة أو
  تُمرَّر صراحةً في البناء؛ أي خلط لاحق ⇒ ``ValueError`` صاخب (نمط
  ``VolatilityEngine._ensure_identity``).

- **الترتيب التصاعدي الصارم**: ``bar_time`` الجديدة يجب أن تعلو آخر شمعة
  **قطعيًا** — التساوي تكرارٌ والانخفاض تأخرٌ وكلاهما ``ValueError``.
  **قرار موثق يخالف محرك التقلب عمدًا**: ذاك المحرك يتجاهل المتأخرة
  ويحصيها (سمات نافذية تقبل الإعادة الحسابية)، أما كواشف البنية فآلات
  حالة متسلسلة حساسة للترتيب (مرشح التأكيد، سجل المستويات، ركض الاندفاع)
  — الشمعة المتأخرة أو المكررة تكسر آلة الحالة وتقوّض حتمية ``swing_id``
  والسجلات، فالرفض القانوني الصاخب هو السلوك الوحيد الأمين.

- **الشمع المغلقة فقط (§27/§33.2)**: ``is_closed=False`` ⇒ ``ValueError``
  فوري — فصل المتطور عن المؤكد مسؤولية الابتلاع.

- **حارس لا-نظرة-مستقبلية (§26.3)**: حالة تقلب بطابع زمني **أحدث من
  الشمعة** خطأ قانوني — تسريب صريح من المستقبل يُرفض صاخبًا. الحالة
  الأقدم مسموحة (قيمها الدافئة ``None`` تعلن نفسها؛ محاذاة الحالة
  مسؤولية المستدعي).
"""

from __future__ import annotations

from datetime import datetime

from market_state.volatility import VolatilityState
from schemas import Candle

__all__ = ["StreamGuards"]


class StreamGuards:
    """حوارس هوية/ترتيب/إغلاق لتدفق شموع موضعي واحد — انظر عقود الموديول."""

    def __init__(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._identity: tuple[str, str] | None = (
            (instrument_id, timeframe)
            if instrument_id is not None and timeframe is not None
            else None
        )
        self._last_bar_time: datetime | None = None

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._identity[0] if self._identity is not None else None

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._identity[1] if self._identity is not None else None

    def check_candle(self, candle: Candle) -> None:
        """فرض عقود الشمعة الواحدة: مغلقة، هوية واحدة، ترتيب تصاعدي قطعي.

        :raises ValueError: شمعة متطورة، أو خلط أداة/إطار، أو ``bar_time``
            لا يعلو آخر شمعة قطعيًا (تكرار أو تأخر) — انظر عقود الموديول.
        """
        if not candle.is_closed:
            raise ValueError(
                "الكاشف يستهلك الشموع المغلقة فقط (§27/§33.2) — "
                "فصل المتطور عن المؤكد مسؤولية الابتلاع عبر is_closed"
            )
        if self._identity is None:
            self._identity = (candle.instrument_id, candle.timeframe)
            self._last_bar_time = candle.bar_time
            return
        expected_instrument, expected_timeframe = self._identity
        if candle.instrument_id != expected_instrument:
            raise ValueError(
                f"خلط أدوات على كاشف واحد: استُهل على {expected_instrument!r} "
                f"ووصلت شمعة {candle.instrument_id!r} — أنشئ كاشفًا لكل (أداة، إطار)"
            )
        if candle.timeframe != expected_timeframe:
            raise ValueError(
                f"خلط أطر زمنية على كاشف واحد: استُهل على {expected_timeframe!r} "
                f"ووصلت شمعة {candle.timeframe!r} — أنشئ كاشفًا لكل (أداة، إطار)"
            )
        last = self._last_bar_time
        assert last is not None  # الهوية لا تثبت إلا مع آخر طابع
        if candle.bar_time == last:
            raise ValueError(
                f"تكرار bar_time لشمعة مغلقة سبق استهلاكها: {candle.bar_time} — "
                "التكرار خطأ قانوني عند المغلقات"
            )
        if candle.bar_time < last:
            raise ValueError(
                f"شمعة متأخرة (bar_time أقدم من آخر مغلقة): {candle.bar_time} "
                f"بعد {last} — كواشف البنية آلات حالة متسلسلة ترفض المتأخرة "
                "رفضًا صريحًا (خلافًا لمحرك التقلب الذي يتجاهلها ويحصيها)"
            )
        self._last_bar_time = candle.bar_time

    def check_vol(self, candle: Candle, vol: VolatilityState | None) -> None:
        """حارس لا-نظرة-مستقبلية: حالة تقلب من المستقبل خطأ قانوني صاخب.

        الحالة الغائبة (``None`` — أول شمعة للمستدعي) والحالة الأقدم مسموحتان:
        الأولى لا تحمل شيئًا يُقرأ، والثانية قيمها الدافئة ``None`` تعلن نفسها.

        :raises ValueError: ``vol.bar_time`` أحدث من ``candle.bar_time``.
        """
        if vol is None or vol.bar_time is None:
            return
        if vol.bar_time > candle.bar_time:
            raise ValueError(
                f"حالة تقلب من المستقبل: vol.bar_time={vol.bar_time} أحدث من "
                f"شمعة الحكم {candle.bar_time} — تسريب §26.3 يُرفض صاخبًا"
            )
