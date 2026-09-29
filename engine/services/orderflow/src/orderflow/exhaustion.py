"""كاشف الإنهاك — §12.4 حرفيًا: تراجع الفعالية الاتجاهية قياسًا لا توصية.

نص §12.4: الإنهاك «تراجع في الفعالية الاتجاهية»: امتداد متناقص لكل وحدة
حجم اتجاهي، متابعة متناقصة، قمم/قيعان فاشلة متكررة، كفاءة دلتا متدهورة —
«**الإنهاك وحده ليس إشارة انعكاس**». الحمولة قياس تراجع لا تشير لحالة
تداول: التقييم وربط الإنهاك بانعكاس محتمل مسؤولية الدمج (§19) والسياق.

**الترجمة التشغيلية الموثقة لعناصر §12.4 الأربعة**:

- **(أ) امتداد متناقص لكل وحدة حجم اتجاهي** و**(د) كفاءة دلتا متدهورة**:
  القياس نفسه (نص المهمة يجعل (د) «نفس أ») — كفاءة النافذة الحالية مقابل
  السابقة: ``decay_ratio = efficiency / efficiency_prev`` حيث كفاءة كل نصف
  **متوسط كفاءات أشرطته الفردية** (:func:`orderflow.effort.efficiency`
  لكل شريط: استجابة باتجاه جهد الشريط ÷ atr ÷ ‎|حصة الدلتا|‎).
- **(ب) متابعة متناقصة**: ``follow_through`` = حصة أشرطة النافذة التي
  حققت استجابة باتجاه الجهد المنهَك بعتبة المواصلة
  (``continuation_min_key`` — فاصل «الاستجابة القوية» §12.2) فأعلى؛
  «متناقصة» تعني هبوط الحصة دون ``follow_through_max``. المقام الأشرطة
  القابلة للحكم فقط (ذات عتبة مواصلة وقتها) — الأشرطة بلا تقلب لا
  تُحسب نجاحًا ولا فشلًا (غياب دليل لا دليل).
- **(ج) قمم/قيعان فاشلة متكررة**: عدّ نافذة لكل اتجاه — الشريط «قمة
  فاشلة» إذا تجاوز أقصى قمم النافذة الخلفية المكتملة ثم أغلق دونها
  (والمرآة للقاع الفاشل). قبل اكتمال النافذة الخلفية لا مرجع فلا رصد.
  **لا يحتاج تقلبًا** — مقارنة سعرية صرفة بين شموع النافذة.

**نافذة مستقلة لكل اتجاه**: كفاءات آخر ``window`` شريطًا **ذات جهد في
الاتجاه** تُتتبع في عدّاء خاص بها — الإنهاك صفة جهد اتجاهي (صاعد/هابط)
فتُقاس سلسلته وحدها؛ شريط الحكم (ذو الجهد في الاتجاه) هو الذي يُدخل
العينة الأخيرة ويُقيَّم، فاتجاه الحدث = اتجاه جهد الشريط المؤكِد. نوافذ
السلوك السعري (الأشرطة/علامات الفشل/علامات المواصلة) تشمل كل الأشرطة —
«داخل النافذة» تعني آخر ``window`` شريطًا بلا استثناء.

**عتبات الإعلان (قياس لا توصية)**: عند اكتمال النافذة الاتجاهية، يُبث
``EXHAUSTION_UP/DOWN`` باتجاه الجهد المنهَك إذا تحقق معًا: الأساس الكمي
أ+د ببلوغ ``decay_ratio ≤ decay_max`` (‎< 1 إلزامًا فبلوغه يضم التراجع)،
وعدد الفشل ``≥ failed_extremes_min``، والمتابعة ``≤ follow_through_max``،
مع **موجبية كفاءتي النصفين** (عقد الحمولة 4-a: ``PositiveFloat`` — النصف
غير الموجب لا decay له يُقاس فلا يُبث).

**ما يتعطل بلا تقلب (§16)**: (أ)/(د) تحتاجان atr لكل عينة كفاءة، و(ب)
تحتاج عتبة المواصلة — كلاهما يتوقف دون تحديث (الأشرطة المعطلة لا تدخل
نوافذهما أصلًا)؛ (ج) يستمر (سعري صرف). بلا تقلب إطلاقًا لا تكتمل نافذة
الكفاءة فلا إنهاك يُعلن أبدًا.

**البث لكل شريط مستوفٍ** (قرار موثق بنمط كاشف الإزاحة الخام): الكاشف
قياس خام لا يُسقط معلومة قابلة للقياس — التباعد/التجميع مسؤولية الدمج
(§19) التي ترى السياق كاملًا. حدث واحد كأقصى في الشريط (اتجاه واحد
ممكن بحكم تعريفه من جهد الشريط).

**الحتمية الصرفة ولا-نظرة-المستقبلية (§26.3)**: القرار من النافذة
المنقضية [أقدم..شريط الحكم] حصرًا — «النافذة السابقة» للأ extremes هي
الأشرطة قبل شريط الحكم؛ و``event_time = bar_time`` الشريط المؤكِد.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    Candle,
    EventType,
    ExhaustionEventPayload,
    FlowDirection,
    FootprintBar,
)

from .effort import FlowGuards, bar_delta_share, directional_response, efficiency, usable_atr
from .events import EmittedEvent

__all__ = ["ExhaustionConfig", "ExhaustionDetector"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class ExhaustionConfig:
    """إعداد كاشف الإنهاك — نقاط انطلاق إعدادية معلنة (ليست توصيات).

    الامتداد الموثق عن نص المهمة: ``continuation_min_key`` (مفتاح عتبة
    علامات المواصلة — فاصل §12.2 نفسه، بنمط الحقن في كاشف الامتصاص).
    """

    #: نافذة التقييم بالأشرطة — **زوجية إلزامًا**: نصفان متساويان
    #: (أقدم/أحدث) للمقارنة؛ ولكل اتجاه عدّاء كفاءات خاص بطولها.
    window: int = 20
    #: نسبة التراجع القصوى للكفاءة كي يُعلن «تراجعًا» —
    #: ``decay_ratio ≤ decay_max``؛ أقل من 1 إلزامًا (وإلا لم يكن تراجعًا
    #: أصلًا فلا يُقاس به عنصرا أ+د).
    decay_max: float = 0.6
    #: الحد الأدنى لعدد القمم/القيعان الفاشلة في النافذة (العنصر ج).
    failed_extremes_min: int = 2
    #: الحد الأقصى لحصة أشرطة المواصلة في النافذة (العنصر ب) — «متابعة
    #: متناقصة» تعني هبوط الحصة دون هذا الحد.
    follow_through_max: float = 0.3
    #: مفتاح عتبة المواصلة (علامات المتابعة) — فاصل «الاستجابة القوية» §12.2.
    continuation_min_key: ThresholdKey = ThresholdKey.FLOW_RESPONSE_MIN

    def __post_init__(self) -> None:
        if self.window < 2 or self.window % 2 != 0:
            raise ValueError(
                f"window يجب أن يكون عددًا زوجيًا ≥ 2 (نصفان متساويان)؛ وُجد {self.window}"
            )
        if not isfinite(self.decay_max) or not 0.0 < self.decay_max < 1.0:
            raise ValueError(f"decay_max يجب أن يكون نسبة محدودة في (0, 1)؛ وُجد {self.decay_max!r}")
        if self.failed_extremes_min < 1:
            raise ValueError(f"failed_extremes_min يجب أن يكون ≥ 1؛ وُجد {self.failed_extremes_min}")
        if not isfinite(self.follow_through_max) or not 0.0 <= self.follow_through_max <= 1.0:
            raise ValueError(
                f"follow_through_max يجب أن يكون حصة محدودة في [0, 1]؛ "
                f"وُجد {self.follow_through_max!r}"
            )
        if not isinstance(self.continuation_min_key, ThresholdKey):
            raise ValueError(
                f"continuation_min_key يجب أن يكون مفتاح ThresholdKey؛ وُجد "
                f"{self.continuation_min_key!r}"
            )


# ═════════════════════════════ الكاشف ═════════════════════════════


class ExhaustionDetector:
    """كاشف الإنهاك الموضعي لكل (أداة، إطار) — أشرطة فوتبرنت مكتملة فقط.

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اتركه يلتقط الهوية من أول شريط)
    وغذّه الثلاثية (شريط الفوتبرنت، الشمعة المقابلة، حالة التقلب عند
    الشريط نفسه) بترتيب الوصول — انظر عقود الموديول كاملة.
    """

    def __init__(
        self,
        config: ExhaustionConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else ExhaustionConfig()
        window = self._config.window
        self._guards = FlowGuards(instrument_id=instrument_id, timeframe=timeframe)
        # نوافذ السلوك السعري (كل الأشرطة) — قمم/قيعان فاشلة وعلامات مواصلة.
        self._bars: deque[Candle] = deque(maxlen=window)
        self._failed_high: deque[bool] = deque(maxlen=window)
        self._failed_low: deque[bool] = deque(maxlen=window)
        self._follow_up: deque[bool | None] = deque(maxlen=window)
        self._follow_down: deque[bool | None] = deque(maxlen=window)
        # نوافذ الكفاءة الاتجاهية — أشرطة الجهد في الاتجاه وحدها.
        self._up_effs: deque[float] = deque(maxlen=window)
        self._down_effs: deque[float] = deque(maxlen=window)

    @property
    def config(self) -> ExhaustionConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

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
        """تقييم شريط مكتمل — حدث إنهاك واحد عند الاقتضاء أو لا شيء.

        القائمة فارغة أو عنصر واحد حصرًا (اتجاه واحد ممكن لكل شريط بحكم
        تعريفه من جهد الشريط المؤكِد).
        """
        self._guards.check(bar, candle, vol)
        share = bar_delta_share(bar)
        atr = usable_atr(vol)
        # ── (ب) علامتا المواصلة — None: غير قابل للحكم (لا عتبة تطبيعية) ──
        cont_threshold: float | None = None
        if vol is not None and atr is not None:
            cont_threshold = vol.threshold(self._config.continuation_min_key)
        up_mark: bool | None
        down_mark: bool | None
        if cont_threshold is not None:
            up_mark = (candle.close - candle.open) >= cont_threshold
            down_mark = (candle.open - candle.close) >= cont_threshold
        else:
            up_mark = None
            down_mark = None
        # ── (ج) قمة/قاع فاشلان — مقارنة سعرية صرفة ضد النافذة الخلفية ──
        # المكتملة (قبلها لا مرجع فلا رصد) — بلا تقلب إطلاقًا.
        failed_high = False
        failed_low = False
        if len(self._bars) == self._config.window:
            prior_high = max(b.high for b in self._bars)
            prior_low = min(b.low for b in self._bars)
            failed_high = candle.high > prior_high and candle.close < prior_high
            failed_low = candle.low < prior_low and candle.close > prior_low
        self._bars.append(candle)
        self._failed_high.append(failed_high)
        self._failed_low.append(failed_low)
        self._follow_up.append(up_mark)
        self._follow_down.append(down_mark)
        # ── (أ)+(د) عينة الكفاءة الاتجاهية — بلا جهد أو بلا تطبيع لا عينة ──
        if share == 0.0 or atr is None:
            return []
        direction = 1 if share > 0.0 else -1
        response = directional_response(candle, direction)
        eff = efficiency(response / atr, abs(share))
        effs = self._up_effs if direction > 0 else self._down_effs
        effs.append(eff)
        if len(effs) < self._config.window:
            return []
        half = self._config.window // 2
        samples = list(effs)
        prev_eff = sum(samples[:half]) / half  # النصف الأقدم
        curr_eff = sum(samples[half:]) / half  # النصف الأحدث (يشمل شريط الحكم)
        if prev_eff <= 0.0 or curr_eff <= 0.0:
            # عقد الحمولة (PositiveFloat): النصف غير الموجب لا decay له
            # يُقاس فلا يُبث — الكفاءة الصرفة قد تكون سالبة، الحمولة لا.
            return []
        decay_ratio = curr_eff / prev_eff
        if decay_ratio > self._config.decay_max:
            return []
        failed = sum(self._failed_high if direction > 0 else self._failed_low)
        if failed < self._config.failed_extremes_min:
            return []
        marks = self._follow_up if direction > 0 else self._follow_down
        judged = [m for m in marks if m is not None]
        if not judged:
            # لا شريط قابل للحكم في النافذة — المتابعة غير مقيسة فلا إعلان.
            return []
        follow_through = sum(1 for m in judged if m) / len(judged)
        if follow_through > self._config.follow_through_max:
            return []
        payload = ExhaustionEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=bar.bar_time,
            direction=FlowDirection.UP if direction > 0 else FlowDirection.DOWN,
            efficiency=curr_eff,
            efficiency_prev=prev_eff,
            decay_ratio=decay_ratio,
            failed_extremes=failed,
            follow_through=follow_through,
        )
        event_type = EventType.EXHAUSTION_UP if direction > 0 else EventType.EXHAUSTION_DOWN
        return [EmittedEvent(event_type=event_type, event_time=bar.bar_time, payload=payload)]

    # ── الداخلية ──

    def _required_instrument(self) -> str:
        """أداة الكاشف — الحدث لا يُبث إلا بعد أول شريط (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار الكاشف — الحدث لا يُبث إلا بعد أول شريط (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
