"""كاشف الإزاحة — §11.4 حرفيًا.

نص §11.4: «Displacement measures unusually directional price travel relative
to recent volatility... A displacement event requires a directional
range/impulse above a rolling percentile and meaningful closing efficiency»
— الترجمة التشغيلية: بوابات متزامنة عند الشمعة المغلقة، كل واحدة منها
شرط لازم مستقل (اختبار كل بوابة على حدة في tests/unit/test_displacement.py):

1. **مئيني توسع المدى** ``range_expansion_percentile`` (من حالة التقلب §16،
   لا يُحسب هنا) ≥ ``percentile_min`` — **عتبة إحصائية كمّية لا سعرية**:
   موقع الشمعة داخل توزيع مداياتها الأخيرة، لا مسافة سعرية أبدًا (تمييز
   صريح عن عتبات §16 التطبيعية ``atr × multiplier`` — كلا النوعين نسبي،
   ومصدرهما مختلف عمدًا).
2. **كفاءة الجسم**: ``|close − open| / (high − low)`` ≥ ``body_min`` — من
   OHLCV الخام حصرًا (عقد A-02: لا قراءة الحقول المشتقة المخزنة).
3. **موقع الإغلاق المتطرف**: ``(close − low)/(high − low)`` (1 = إغلاق عند
   القمة) ≥ ``close_extreme_min`` للاندفاع الصاعد، و``≤ 1 − close_extreme_min``
   للهابط.
4. **مضاعف ATR**: ``(high − low)/atr`` ≥ ``threshold(DISPLACEMENT_MIN)`` —
   العتبة التطبيعية الوحيدة هنا (§16).
5. **الاتجاه**: صاعد إذا ``close > open`` وهابط إذا ``close < open`` —
   **الديدجات (تساوٍ تام) بلا حدث**.
6. **الدافئ الإحصائي**: ``range_zscore`` متاحًا محدودًا — نافذة z-score
   خلفية شاملة للقيمة الحالية (عقد quantmath) على سلسلة المدى؛ النافذة
   الناقصة أو الراكدة تمامًا (انحراف صفري ⇒ nan) ⇒ لا حدث (إحصاء منحل
   لا يُختلق).

**تعاريف الحمولة (§11.4 الحرفية)**:

- ``velocity`` = مدى الاندفاع ÷ عدد شموعه: «الاندفاع» أطول سلسلة شموع
  متتالية **بنفس اتجاه الحدث** منتهية بالشمعة الحالية، مقيدة بـ
  ``velocity_window`` شموع؛ و«مدى الاندفاع» ``أقصى قمته − أدنى قاعه``
  (سفر صافٍ لكل شمعة).
- ``follow_through`` = 0.0 عند البث (صفر شموع منقضية بعد الاندفاع) — لا
  قياس من مستقبل أبدًا (§26.3)؛ التتبع اللاحق مسؤولية المستهلك.

**قاعدة التكرار (قرار موثق)**: **بث لكل شمعة مستوفية** — كاشف خام لا يُسقط
معلومة قابلة للقياس؛ تجميع الركض (runs) المتتالية وحساب الطازجية مسؤولية
السيناريوهات/الدمج (§19) التي ترى السياق كاملًا. حدث واحد كأقصى في الشمعة
(اتجاه واحد ممكن بحكم التعريف).

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_displacement.py):

- **لا-نظرة-مستقبلية (§26.3)**: الحكم من الشمعة الحالية ونافذتها الخلفية
  حصرًا (خاصية البادئة في tests/property/test_structure_properties.py).
- **الحتمية الصرفة**: نفس الشموع والحالات ⇒ نفس الأحداث بالتطابق التام.
- **الصخب في التحقق**: عقود :mod:`structure._guards` كاملة (شمع مغلقة،
  هوية، ترتيب تصاعدي قطعي، وحالة تقلب من المستقبل مرفوضة).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite

from features import ranges as ranges_of
from market_state.volatility import ThresholdKey, VolatilityState
from quantmath import rolling_zscore
from schemas import BreakDirection, Candle, DisplacementEventPayload, EventType

from ._guards import StreamGuards
from .events import EmittedEvent

__all__ = ["DisplacementConfig", "DisplacementDetector"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class DisplacementConfig:
    """إعداد كاشف الإزاحة — نقاط انطلاق إعدادية للتقييم والمعايرة
    (ليست توصيات تداول).

    ملاحظة مواءمة موثقة: ``zscore_window`` ينبغي أن يوازي نافذة مئيني توسع
    المدى في إعداد التقلب (‎100 = 100‎ افتراضيًا) — النوافذ المتباينة قد
    تحجب أحداثًا أثناء دافئ الأطول منهما (السلوك موثق لا صامت).
    """

    #: مئيني توسع المدى الأدنى لقبول الشمعة (كمّ إحصائي لا سعر — §11.4).
    percentile_min: float = 0.90
    #: كفاءة الجسم الدنيا: ``|close − open| / range``.
    body_min: float = 0.6
    #: حد تطرف موقع الإغلاق للحدث الصاعد (1 − القيمة للهابط).
    close_extreme_min: float = 0.8
    #: نافذة z-score المدى الخلفية الشاملة للقيمة الحالية.
    zscore_window: int = 100
    #: سقف عدد شموع الاندفاع في حساب السرعة.
    velocity_window: int = 3

    def __post_init__(self) -> None:
        if not isfinite(self.percentile_min) or not 0.0 < self.percentile_min <= 1.0:
            raise ValueError(
                f"percentile_min يجب أن يكون كمًّا محدودًا في (0, 1]؛ وُجد {self.percentile_min!r}"
            )
        if not isfinite(self.body_min) or not 0.0 < self.body_min <= 1.0:
            raise ValueError(f"body_min يجب أن يكون نسبة محدودة في (0, 1]؛ وُجد {self.body_min!r}")
        if not isfinite(self.close_extreme_min) or not 0.5 < self.close_extreme_min <= 1.0:
            raise ValueError(
                f"close_extreme_min يجب أن يكون نسبة محدودة في (0.5, 1]؛ "
                f"وُجد {self.close_extreme_min!r}"
            )
        if self.zscore_window < 2:
            raise ValueError(f"zscore_window يجب أن يكون ≥ 2؛ وُجد {self.zscore_window}")
        if self.velocity_window < 1:
            raise ValueError(f"velocity_window يجب أن يكون ≥ 1؛ وُجد {self.velocity_window}")


# ═════════════════════════════ الكاشف ═════════════════════════════


class DisplacementDetector:
    """كاشف الإزاحة الموضعي لكل (أداة، إطار) — شمع مغلقة فقط (§11.4).

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)
    وغذّه كل شمعة مغلقة مع حالة التقلب عند الشمعة نفسها (المستدعي يشغّل
    ``VolatilityEngine`` بالتوازي). ``vol = None`` أو أي قيمة دافئة ``None``
    تُغلق بوابتها وتمنع الحدث — لا قيم مزيفة. انظر عقود الموديول كاملة.
    """

    def __init__(
        self,
        config: DisplacementConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else DisplacementConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        self._buffer: deque[Candle] = deque(maxlen=self._config.zscore_window)

    # ── الخصائص ──

    @property
    def config(self) -> DisplacementConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._guards.timeframe

    @property
    def bars_seen(self) -> int:
        """عدد الشموع المستهلكة — يكشف اكتمال نافذة الإحصاء."""
        return len(self._buffer)

    # ── التغذية ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """تقييم شمعة مغلقة — حدث واحد عند الاقتضاء أو لا شيء.

        القائمة فارغة أو عنصر واحد حصرًا (اتجاه واحد ممكن لكل شمعة بحكم
        تعريف الاتجاه من الجسم) — عقد «حدث واحد كأقصى في الشمعة».
        """
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        self._buffer.append(candle)
        # ── البوابة 5: الاتجاه — الديدجة بلا اتجاه بلا حدث ──
        if candle.close > candle.open:
            direction = BreakDirection.UP
        elif candle.close < candle.open:
            direction = BreakDirection.DOWN
        else:
            return []
        # ── البوابة 1: مئيني توسع المدى (كم إحصائي من حالة التقلب) ──
        expansion = vol.range_expansion_percentile if vol is not None else None
        if expansion is None or expansion < self._config.percentile_min:
            return []
        # ── البوابة 4: مضاعف ATR (العتبة التطبيعية §16) ──
        threshold = vol.threshold(ThresholdKey.DISPLACEMENT_MIN) if vol is not None else None
        atr = vol.atr if vol is not None else None
        price_range = candle.high - candle.low
        if threshold is None or atr is None or atr <= 0.0:
            return []
        atr_multiple = price_range / atr
        if atr_multiple < threshold:
            return []
        # ── البوابة 2: كفاءة الجسم (من الخام — عقد A-02) ──
        body_fraction = abs(candle.close - candle.open) / price_range if price_range > 0.0 else 0.0
        if body_fraction < self._config.body_min:
            return []
        # ── البوابة 3: موقع الإغلاق المتطرف ──
        close_location = (candle.close - candle.low) / price_range if price_range > 0.0 else 0.5
        if direction is BreakDirection.UP:
            if close_location < self._config.close_extreme_min:
                return []
        elif close_location > 1.0 - self._config.close_extreme_min:
            return []
        # ── البوابة 6: الدافئ الإحصائي — z-score متاحًا محدودًا ──
        zscore = self._range_zscore()
        if zscore is None:
            return []
        payload = DisplacementEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=candle.bar_time,
            direction=direction,
            range_zscore=zscore,
            body_fraction=body_fraction,
            close_location=close_location,
            atr_multiple=atr_multiple,
            velocity=self._velocity(direction),
            follow_through=0.0,
        )
        event_type = (
            EventType.DISPLACEMENT_UP
            if direction is BreakDirection.UP
            else EventType.DISPLACEMENT_DOWN
        )
        return [EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)]

    # ── الداخلية ──

    def _range_zscore(self) -> float | None:
        """z-score مدى الشمعة الحالية ضمن نافذتها الخلفية الشاملة لها.

        ``None`` عند النافذة الناقصة أو الراكدة تمامًا (انحراف صفري ⇒ nan
        بعقد quantmath) — انحراف إحصائي منحل لا يُختلق منه قيمة.
        """
        values = ranges_of(list(self._buffer))
        scored = rolling_zscore(values, self._config.zscore_window)
        if scored.shape[0] == 0:
            return None
        zscore = float(scored[-1])
        return zscore if isfinite(zscore) else None

    def _velocity(self, direction: BreakDirection) -> float:
        """سرعة الاندفاع: مداه الصافي ÷ عدد شموعه (تعريف موثق في الترويسة).

        الشمعة الحالية أول أعضاء الاندفاع دائمًا (اتجاه الحدث مشتق منها)،
        ثم تُمدَّد السلسلة خلفيًا بالشموع المتتالية بنفس الاتجاه حصرًا حتى
        ``velocity_window`` شموع — القرار من النافذة المنقضية فقط (§26.3).
        """
        history = list(self._buffer)
        impulse_high = history[-1].high
        impulse_low = history[-1].low
        bars = 1
        for candle in reversed(history[:-1]):
            if bars >= self._config.velocity_window:
                break
            if direction is BreakDirection.UP:
                same_direction = candle.close > candle.open
            else:
                same_direction = candle.close < candle.open
            if not same_direction:
                break
            bars += 1
            impulse_high = max(impulse_high, candle.high)
            impulse_low = min(impulse_low, candle.low)
        return (impulse_high - impulse_low) / bars

    def _required_instrument(self) -> str:
        """أداة الكاشف — الحدث لا يُبث إلا بعد أول شمعة (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار الكاشف — الحدث لا يُبث إلا بعد أول شمعة (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
