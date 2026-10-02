"""نافذة القراءة المتحركة (§26.3) — المنع المعماري لبيانات المستقبل.

«The replay framework exposes only data available at each simulated
timestamp» — الإطار لا *يعد* بعدم النظر للمستقبل؛ إنه **لا يُظهر**
غير المتاح لحظة المحاكاة: الشمعة لا تُرى إلا مغلقةً (بدأت قبل
``as_of`` بفترة إطار كاملة) والحدث لا يُرى إلا بعد لحظته
(``event_time ≤ as_of``).

آلية الإنفاذ المعمارية (لا التزامًا أدبيًا):

- النافذة تُبنى مرة واحدة فوق السلاسل الكاملة ثم **تُجمّد**؛ كل قراءة
  يمر عبر ``as_of`` صريحة، والقِطع مرهونة بشرط زمني لا بفهرس.
- أي طلب بعقارب متقدمة يستقبل **قِطعة فارغة** لا استثناءً — فالمستقبل
  ليس خطأً يُصلح بل عدماً لا يُرى (الخطأ الحقيقي حالة إدخال معكوسة
  تكتشفها النافذة وتصيح بها فورًا).

الفحوص الستة §26.3 تبني فوق هذه الآلية: فاحص «لا فهرسة شموع
مستقبل» يثبت أن كل ما رآه المستهلك عند كل لحظة كان مغمضًا بحكم
البناء لا بالاتفاق.
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from schemas import Candle

__all__ = ["ReplayWindow", "timed_event"]


@dataclass(frozen=True, slots=True)
class timed_event:
    """حدث موثّق اللحظة — أزواج (اللحظة، الحمولة) التي تعبر النافذة.

    «no future swing confirmation leakage / no future footprint row
    usage» يُنفذان بهذا العقد الموحد: كل ما يستهلكه المحرك من أحداث
    يحمل لحظته الصريحة فتقارنها النافذة بـ``as_of``.
    """

    event_time: dt.datetime
    payload: object


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """نافذة القراءة المتحركة فوق شموع إطار واحد وأحداث موثّقة اللحظة.

    :param candles: شموع الإطار مرتبة زمنيًا (يتحقق الباني).
    :param timeframe_s: عرض الشمعة بالثواني — الشمعة مغلقة عند
        ``bar_time + timeframe_s``.
    :param events: أحداث موثّقة اللحظة مرتبة زمنيًا (اختياري).

    كل الاستعلامات **بلا نسخ** (قِطع tuple) — الحتمية والنقاء بلا
    حالة قابلة للتطفل.
    """

    candles: tuple[Candle, ...]
    timeframe_s: float
    events: tuple[timed_event, ...] = ()

    def __post_init__(self) -> None:
        if self.timeframe_s <= 0.0:
            raise ValueError(f"عرض إطار غير موجب: {self.timeframe_s} ثانية")
        for previous, current in itertools.pairwise(self.candles):
            if current.bar_time <= previous.bar_time:
                raise ValueError(
                    f"شموع غير مرتبة زمنيًا: {previous.bar_time} ثم {current.bar_time} — "
                    "النافذة تُبنى فوق سلسلة مرتبة حصرًا"
                )
        for earlier_event, later_event in itertools.pairwise(self.events):
            if later_event.event_time < earlier_event.event_time:
                raise ValueError(
                    f"أحداث غير مرتبة زمنيًا: {earlier_event.event_time} ثم {later_event.event_time}"
                )

    # ───────────────────────── الشموع المغلقة حصرًا ─────────────────────────

    def closed_candles(self, as_of: dt.datetime) -> tuple[Candle, ...]:
        """الشموع المغلقة عند ``as_of`` — بدأت وانتهت قبل اللحظة.

        شمعة ``bar_time`` تغطي ``[bar_time, bar_time + timeframe_s)``؛
        فهي مرئية عند ``as_of`` إذا كان ``bar_time + timeframe_s ≤
        as_of`` — الشمعة الجارية (المفتوحة) **لا تُرى أبدًا**.
        """
        horizon = self._as_of(as_of)
        cutoff = horizon - dt.timedelta(seconds=self.timeframe_s)
        return tuple(c for c in self.candles if c.bar_time <= cutoff)

    def closed_until_index(self, as_of: dt.datetime) -> int:
        """عدد الشموع المغلقة عند ``as_of`` — موضع القراءة الحتمي."""
        return len(self.closed_candles(as_of))

    # ───────────────────────── الأحداث المنقضية حصرًا ─────────────────────────

    def events_until(self, as_of: dt.datetime) -> tuple[timed_event, ...]:
        """الأحداث التي لحظتها ≤ ``as_of`` — لا مراجعة قبل الإصدار (§26.3-4)."""
        horizon = self._as_of(as_of)
        return tuple(e for e in self.events if e.event_time <= horizon)

    # ───────────────────────── حوارس الاستقامة ─────────────────────────

    @staticmethod
    def _as_of(as_of: dt.datetime) -> dt.datetime:
        """توحيد عقارب المحاكاة — datetime مع اتجاه صحيح فقط.

        :raises ValueError: عقرب غير datetime (يمنع الفهرسة المقنعة
            بـ``as_of`` — كل قراءة زمنية لا رقمية).
        """
        if not isinstance(as_of, dt.datetime):
            raise ValueError(
                f"عقرب المحاكاة يجب أن يكون datetime لا {type(as_of).__name__} — "
                "النافذة زمنية-حدث حصرًا (§26.1 event time only)"
            )
        return as_of

    def audit_visible_candles_closed(self, as_of: dt.datetime, consumed: Sequence[Candle]) -> bool:
        """تدقيق §26.3-1: كل شمعة استُهلكت عند ``as_of`` كانت مغلقة.

        فاحص البوابة يمرر ما استهلكه المستهلك فعلاً — النافذة تحكم
        أن كلًّا منها مرئية قانونًا عند اللحظة ذاتها.
        """
        legal = {c.bar_time for c in self.closed_candles(as_of)}
        return all(c.bar_time in legal for c in consumed)
