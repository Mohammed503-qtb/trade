"""باعث توافق التدفق — جهد كبير + استجابة قوية ⇒ ‏FLOW_CONTINUATION (§12.2).

المصفوفة (:func:`orderflow.effort.classify_effort_vs_result`) القياس، وهذا
الباعث الردف الرقيق الذي يحول خلية التوافق منها إلى حدث §20 مبثوث
(«دلتا موجبة كبيرة + صعود قوي ⇒ شراء عدواني مقبول») — حدث مباشر لا
مرشح: التوافق قياس لحظة إغلاق الشريط فلا حالة تُحمل بين الأشرطة.

عقود الباعث:

- **الإصدار عند الإقفال حصرًا (§26.3/§27)**: يُقيَّم الشريط المكتمل فقط؛
  ``event_time = bar_time`` الشريط ذاته (لا تأكيد لاحق — التوافق ظاهرة
  الشريط الحاضرة).

- **جهة واحدة لكل شريط**: خلية التوافق تحدد الاتجاه من إشارة الدلتا —
  شريط بلا جهد كبير أو باستجابة ضعيفة لا يصدر شيئًا (خلايا المصفوفة
  الأخرى ميادين كواشف أخرى: EFFORT_NO_RESULT ميدان الامتصاص §12.3).

- **الحتمية الصرفة**: الباعث عديم الحالة — نفس الثلاثية ⇒ نفس القرار؛
  الحارس (:class:`orderflow.effort.FlowGuards`) يفرض الترتيب التصاعدي
  والثنائية المتطابقة على من يريد ضمانه (المسار الحي)، والباعث نفسه
  يعمل بلا كائن معلقات بين الاستدعاءات.
"""

from __future__ import annotations

from market_state.volatility import VolatilityState
from schemas import (
    Candle,
    EventType,
    FlowContinuationEventPayload,
    FlowDirection,
    FootprintBar,
)

from .effort import (
    EffortResultState,
    FlowGuards,
    bar_delta_share,
    classify_effort_vs_result,
    directional_response,
    usable_atr,
)
from .events import EmittedEvent

__all__ = ["ContinuationEmitter"]


class ContinuationEmitter:
    """باعث توافق التدفق — ردفف رقيق فوق مصفوفة الجهد/النتيجة §12.2.

    الاستخدام: ``update(bar, candle, vol)`` لكل شريط مكتمل — قائمة فارغة
    أو حدث توافق واحد حصرًا.
    """

    def __init__(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._guards = FlowGuards(instrument_id=instrument_id, timeframe=timeframe)

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شريط إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شريط إن لم تُمرر في البناء."""
        return self._guards.timeframe

    def update(
        self,
        bar: FootprintBar,
        candle: Candle,
        vol: VolatilityState | None,
    ) -> list[EmittedEvent]:
        """تقييم شريط مكتمل — توافق واحد عند الاقتضاء أو لا شيء."""
        self._guards.check(bar, candle, vol)
        state = classify_effort_vs_result(bar, candle, vol)
        if state is not EffortResultState.AGREE_EFFORT_RESULT:
            return []
        share = bar_delta_share(bar)
        atr = usable_atr(vol)
        assert atr is not None and atr > 0.0  # التوافق يستلزم تقلبًا قابلًا للاستخدام
        direction = 1 if share > 0.0 else -1
        response = directional_response(candle, direction)
        response_atr = response / atr
        efficiency = response_atr / abs(share)
        assert self._guards.instrument_id is not None and self._guards.timeframe is not None
        payload = FlowContinuationEventPayload(
            instrument=self._guards.instrument_id,
            timeframe=self._guards.timeframe,
            bar_time=bar.bar_time,
            direction=FlowDirection.UP if direction > 0 else FlowDirection.DOWN,
            delta=bar.delta,
            delta_share=share,
            response_atr=response_atr,
            efficiency=efficiency,
        )
        event_type = (
            EventType.FLOW_CONTINUATION_UP if direction > 0 else EventType.FLOW_CONTINUATION_DOWN
        )
        return [EmittedEvent(event_type=event_type, event_time=bar.bar_time, payload=payload)]
