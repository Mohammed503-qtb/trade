"""كاشف الامتصاص — §12.3 حرفيًا: الشروط الأربعة مرشحًا قابلًا للتأكيد.

نص §12.3: «الامتصاص عدم توافق بين الحجم المتداول العدواني والحركة
السعرية المحققة عند موقع ذي معنى» — والمرشح يتطلب: (1) دلتا اتجاهية
أو حجم مرتفع عند منطقة، (2) امتدادًا سعريًا محدودًا نسبةً إلى العدوان،
(3) استجابة متكررة أو فشلًا في المواصلة، (4) إزاحة لاحقة معاكسة
(اختيارية). «هذه فرضيات يجب أن تؤكدها الاستجابة اللاحقة» (§12.2) — لذا
المرشح يخرج ``confirmed=False`` دائمًا عند الإنشاء، والتأكيد اللاحق يرفع
درجة المرشح نفسه ولا يخترع حدثًا موازيًا.

**الترجمة التشغيلية الموثقة للشروط**:

- **الشرط 1 (elevated_delta)**: ``|delta_share| ≥ elevated_share_min``
  بجهة معروفة — الحد موجب قطعًا فالدلتا المعدومة لا تعبر أبدًا.
- **الشرط 2 (limited_extension)**: امتداد السعر باتجاه العدوان
  ``sign(delta)·(close−open)`` مقابل العتبة التطبيعية
  ``vol.threshold(extension_max_key)`` **سعرًا بسعر** (§16:
  ``threshold = atr × multiplier`` — درس ADR-020: لا خلط أبعاد أبدًا؛
  المساواة عند الحد «محدود» — حد مغلق). الامتداد **السالب** (إغلاق معاكس
  للعدوان) يجتاز الشرط دومًا: عدم التقدم باتجاه العدوان هو حد
  «المحدودية» الأقصى — أبلغ صور عدم التوافق.
- **الشرط 3 (repeated_response)**: عداءان داخليان متتاليان (لكل اتجاه):
  عدد الأشرطة المتتالية التي «فشلت في المواصلة» بذلك الاتجاه — الشريط
  يفشل إذا كانت استجابته بالاتجاه دون عتبة المواصلة
  (``continuation_min_key`` — فاصل «الاستجابة القوية» نفسه في §12.2)،
  والنجاح (استجابة ≥ العتبة) يصفّر العداء. **الشمعة الصغيرة تفشل في
  الاتجاهين معًا** (السوق لم يواصل شيئًا)، وشريط الحكم نفسه يُحسب في
  العداء (حالة موضعية تتراكم عبر ``update``). الشريط بلا حالة تقلب لا
  يُحكم: العداءان يبقيان كما هما — غياب دليل لا يُحسب فشلًا ولا نجاحًا.
- **الشرط 4 (opposite_displacement)**: اختياري عبر ``displacement_watcher``
  محقون — الإزاحة شأن كاشف البنية وعقود الطبقات تمنع استيراده هنا،
  فالمراقب **يُوصَّل في بوابة المرحلة 4-f**. غير محقون ⇒
  ``conditions.opposite_displacement = None`` (غير مرصود — صادق).

**قاعدة عدم التكرار (موثقة)**: بمجرد بث مرشح لجهة (ABSORPTION_BUY
للامتصاص الضغط البيعي / ABSORPTION_SELL للشرائي) تُقفل تلك الجهة حتى
**ينكسر الشرط 1** لها (شريط غير مرتفع بجهتها — محايد أو معاكس) **ثم
يعود** — لا سيل بث لنفس الحالة المستمرة؛ تباعد الأحداث صفة عمدية
لمرشحٍ قابل للتأكيد. القفلان مستقلان (جهة لا تمنع الأخرى).

**الامتداد الموجب شرط حمولة**: ``excursion_atr`` في الحمولة عقد 4-a
``PositiveFloat`` (يقيس امتدادًا محققًا باتجاه العدوان بمضاعفات ATR) —
فالمكتمل الشروط بامتداد معدوم/معاكس **لا يُبث** (الحمولة لا تحمله
بأمانة) والحالة تبقى **مسلحة بلا قفل**: أول شريط لاحق مكتمل بامتداد
موجب يبث. الإغلاق المعاكس القوي إزاحة معاكسة — ميدان الشرط 4 والكاشف
البنيوي، لا هذه الحمولة.

**لا مرشح بلا تقلب (§16 صارم)**: الشرط 2 عتبة تطبيعية حصرية —
``vol=None`` أو ATR غائب/منحل ⇒ الشرط لا يُقيَّم ولا يُبث مرشح (والشرط
3 يتوقف عن التحديث كذلك لأن عتبة المواصلة تطبيعية).

**عقود لا-نظرة-المستقبلية (§26.3) والحتمية**: ``event_time = bar_time``
الشريط الذي اكتملت عنده الشروط — البث بعده حصرًا؛ ونفس التدفق ⇒ نفس
الأحداث بالتطابق التام (لا عشوائية ولا وقت ولا حالة خفية).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    Candle,
    EventType,
    FootprintBar,
)

from .effort import FlowGuards, bar_delta_share, directional_response, usable_atr
from .events import EmittedEvent

__all__ = ["AbsorptionConfig", "AbsorptionDetector"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class AbsorptionConfig:
    """إعداد كاشف الامتصاص — نقاط انطلاق إعدادية معلنة (ليست توصيات).

    الامتدادات الموثقة عن نص المهمة: ``continuation_min_key`` (مفتاح عتبة
    «فشل المواصلة» — فاصل §12.2 نفسه، بنمط ``extension_max_key`` القابل
    للحقن) وحقنا ``zone_resolver``/``displacement_watcher`` (وصلات بوابة
    4-f — عقود الطبقات تمنع استيراد السيولة/البنية داخل طبقة الكواشف).
    """

    #: حد «العدوانية المرتفعة» (الشرط 1): ‎|delta_share| ≥ الحد؛ نسبة
    #: عديمة الأبعاد محدودة في (0, 1].
    elevated_share_min: float = 0.5
    #: مفتاح عتبة الامتداد الأقصى (الشرط 2) — عتبة تطبيعية atr × معامل.
    extension_max_key: ThresholdKey = ThresholdKey.ABSORPTION_EXTENSION_MAX
    #: مفتاح عتبة المواصلة (الشرط 3) — فاصل «الاستجابة القوية» §12.2.
    continuation_min_key: ThresholdKey = ThresholdKey.FLOW_RESPONSE_MIN
    #: نافذة «الاستجابة المتكررة/فشل المواصلة» (الشرط 3): عدد الأشرطة
    #: الفاشلة المتتالية اللازم للاكتمال — بما فيها شريط الحكم.
    repeated_response_bars: int = 3
    #: معرف منطقة السيولة/البنية عند الشريط (§12.3: «جودة الامتصاص ترتفع
    #: عند حدود سيولة مرسومة أو بنيوية») — يُوصَّل في بوابة 4-f؛
    #: ``None`` = غير مرصود.
    zone_resolver: Callable[[Candle], str | None] | None = None
    #: مراقب الإزاحة المعاكسة اللاحقة (الشرط 4 الاختياري) — يُوصَّل في 4-f.
    displacement_watcher: Callable[[Candle], bool] | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.elevated_share_min) or not 0.0 < self.elevated_share_min <= 1.0:
            raise ValueError(
                f"elevated_share_min يجب أن يكون نسبة محدودة في (0, 1]؛ "
                f"وُجد {self.elevated_share_min!r}"
            )
        if not isinstance(self.extension_max_key, ThresholdKey):
            raise ValueError(
                f"extension_max_key يجب أن يكون مفتاح ThresholdKey؛ وُجد {self.extension_max_key!r}"
            )
        if not isinstance(self.continuation_min_key, ThresholdKey):
            raise ValueError(
                f"continuation_min_key يجب أن يكون مفتاح ThresholdKey؛ وُجد "
                f"{self.continuation_min_key!r}"
            )
        if self.repeated_response_bars < 1:
            raise ValueError(
                f"repeated_response_bars يجب أن يكون ≥ 1؛ وُجد {self.repeated_response_bars}"
            )


# ═════════════════════════════ الكاشف ═════════════════════════════


class AbsorptionDetector:
    """كاشف الامتصاص الموضعي لكل (أداة، إطار) — أشرطة فوتبرنت مكتملة فقط.

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اتركه يلتقط الهوية من أول شريط)
    وغذّه الثلاثية (شريط الفوتبرنت، الشمعة المقابلة، حالة التقلب عند
    الشريط نفسه) بترتيب الوصول — انظر عقود الموديول كاملة.
    """

    def __init__(
        self,
        config: AbsorptionConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else AbsorptionConfig()
        self._guards = FlowGuards(instrument_id=instrument_id, timeframe=timeframe)
        # عداءا فشل المواصلة (لكل اتجاه) — يتراكمان عبر update ويتصفّران
        # عند النجاح (الشرط 3 حالة موضعية لا لقطة شريط).
        self._fail_up = 0
        self._fail_down = 0
        # قفلا عدم التكرار لكل جهة (ABSORPTION_BUY / ABSORPTION_SELL) —
        # يُقفل عند البث ويُسلَّح عند انكسار الشرط 1 للجهة.
        self._locked_buy = False
        self._locked_sell = False

    @property
    def config(self) -> AbsorptionConfig:
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
        """تقييم شريط مكتمل — مرشح واحد عند الاقتضاء أو لا شيء.

        القائمة فارغة أو عنصر واحد حصرًا (جهة واحدة ممكنة لكل شريط بحكم
        إشارة الدلتا) — عقد «مرشح واحد كأقصى في الشريط».
        """
        self._guards.check(bar, candle, vol)
        share = bar_delta_share(bar)
        atr = usable_atr(vol)
        # ── الشرط 3 (التحديث أولًا: شريط الحكم يُحسب في العداء) ──
        # عتبة المواصلة تطبيعية: بلا تقلب لا حكم — العداءان يبقيان (موثق).
        if vol is not None and atr is not None:
            cont_threshold = vol.threshold(self._config.continuation_min_key)
            if cont_threshold is not None:
                up_response = candle.close - candle.open
                self._fail_up = self._fail_up + 1 if up_response < cont_threshold else 0
                self._fail_down = self._fail_down + 1 if -up_response < cont_threshold else 0
        # ── الشرط 1 + فك أقفال عدم التكرار ──
        magnitude = abs(share)
        elevated_sell = magnitude >= self._config.elevated_share_min and share < 0.0
        elevated_buy = magnitude >= self._config.elevated_share_min and share > 0.0
        if not elevated_sell:
            self._locked_buy = False  # انكسار الشرط 1 لجهة ABSORPTION_BUY
        if not elevated_buy:
            self._locked_sell = False  # انكسار الشرط 1 لجهة ABSORPTION_SELL
        if not (elevated_sell or elevated_buy):
            return []
        # ── الشرط 2 (عتبة تطبيعية حصرًا — لا مرشح بلا تقلب) ──
        if vol is None or atr is None:
            return []
        ext_threshold = vol.threshold(self._config.extension_max_key)
        if ext_threshold is None:
            return []
        direction = -1 if elevated_sell else 1
        extension = directional_response(candle, direction)
        if extension > ext_threshold:
            return []
        # ── الشرط 3 (الاكتمال) ──
        fail_streak = self._fail_down if elevated_sell else self._fail_up
        if fail_streak < self._config.repeated_response_bars:
            return []
        # ── الحمولة تقيس امتدادًا محققًا موجبًا (عقد 4-a: PositiveFloat) ──
        # المكتمل بامتداد معدوم/معاكس لا يُبث والحالة تبقى مسلحة (موثق).
        if extension <= 0.0:
            return []
        if elevated_sell and self._locked_buy:
            return []
        if elevated_buy and self._locked_sell:
            return []
        return [self._emit(bar, candle, atr, extension, share, elevated_sell)]

    # ── الداخلية ──

    def _emit(
        self,
        bar: FootprintBar,
        candle: Candle,
        atr: float,
        extension: float,
        share: float,
        sell_aggression: bool,
    ) -> EmittedEvent:
        """بناء مرشح الامتصاص وقفل جهته — كل الحقول من شريط الحكم حصرًا."""
        watcher = self._config.displacement_watcher
        resolver = self._config.zone_resolver
        if sell_aggression:
            # الضغط البيعي امتُص ⇒ فرصة شراء (§20: ABSORPTION_BUY).
            event_type = EventType.ABSORPTION_BUY
            pressure = AbsorbedPressure.SELL
            self._locked_buy = True
        else:
            event_type = EventType.ABSORPTION_SELL
            pressure = AbsorbedPressure.BUY
            self._locked_sell = True
        payload = AbsorptionEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=bar.bar_time,
            absorbed_pressure=pressure,
            delta=bar.delta,
            delta_share=share,
            excursion_atr=extension / atr,
            conditions=AbsorptionConditions(
                elevated_delta=True,
                limited_extension=True,
                repeated_response=True,
                opposite_displacement=watcher(candle) if watcher is not None else None,
            ),
            zone_id=resolver(candle) if resolver is not None else None,
            confirmed=False,
        )
        return EmittedEvent(event_type=event_type, event_time=bar.bar_time, payload=payload)

    def _required_instrument(self) -> str:
        """أداة الكاشف — المرشح لا يُبث إلا بعد أول شريط (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار الكاشف — المرشح لا يُبث إلا بعد أول شريط (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
