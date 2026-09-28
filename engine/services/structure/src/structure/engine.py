"""الواجهة الجامعة لمحرك البنية — §11 كاملًا عبر مسار واحد لكل شمعة.

تملك :class:`StructureEngine` كاشفًا واحدًا لكل نوع (متطرفات/كسور/إزاحة/
فجوات/كتل أوامر/موقع) لزوج (أداة، إطار) واحد، وتؤلف بينها بترتيب موثق
عند كل شمعة مغلقة:

1. المتطرفات المؤكدة عند الشمعة تُستخرج من :class:`~structure.swings.SwingDetector`
   وتُسجَّل فورًا لدى محرك الكسور (``on_swing`` قبل ``update`` — برهان أمان
   الترتيب داخل :class:`~structure.bos.StructureBreakEngine`) وتُمرَّر
   كذلك لمحرك الموقع (الخارجي وحده يمس النطاق — §11.7).
2. شمعة الكسور تُقيَّم (INTERNAL_BOS/EXTERNAL_BOS/CHOCH — حتى حدث لكل اتجاه).
3. شمعة الإزاحة تُقيَّم (DISPLACEMENT_UP/DOWN — حدث واحد كأقصى).
4. شمعة الفجوات تُقيَّم (FVG_BULLISH/BEARISH — حدث واحد كأقصى؛ الكشف
   ثلاثي الشموع مستقل عن مخرجات 1-3 كليًا).
5. كتل الأوامر تُقيَّم (ORDER_BLOCK_BULLISH/BEARISH — تستهلك أحداثَ
   الإزاحة والكسر المؤكدة **في الشمعة نفسها**: المرشحات تُبنى من الإزاحة
   قبل معالجة الكسر حتى يحقق كسرُ الشمعة نفسها مرشحتَها، والبث عند شمعة
   الكسر حصرًا — خطوة 3 من أنبوب §11.6 بالبث المؤجل الموثق).
6. الموقع يُقيَّم (PREMIUM/DISCOUNT_LOCATION — النطاق المعرَّى يمتد
   بالمتطرفات الخارجية المؤكدة عند الشمعة قبل حساب الموقع §11.7).

الخرج قائمة :class:`~structure.events.EmittedEvent` بترتيب حتمي موثق:
**كسور البنية (UP ثم DOWN) ثم الإزاحة ثم الفجوات ثم كتل الأوامر ثم
الموقع** (والترتيب داخل كل كاشف بترتيبه المعلن في وحدته). **تجميع
المغلف** (``event_id``/``trace_id``/``receive_time``) مسؤولية الناشر
اللاحق (3-f) ولا يُبنى هنا.

العقود الموثقة (تُقفل في tests/property/test_structure_properties.py):

- **لا-نظرة-مستقبلية (§26.3)**: كل مكون آلة حالة تزايدية — خرج البادئة
  [0..k] لا يتغير بتمديد الذيل أبدًا (خاصية البادئة المفروضة على
  الواجهة كاملة مع محرك التقلب الموازي).
- **الحتمية الصرفة**: نفس الشموع وحالات التقلب ⇒ نفس الأحداث والمتطرفات
  والفجوات والمناطق والموقع بالتطابق التام (بما فيه المعرفات الحتمية).
- **حالة ملغومة بعد خرق العقد**: حوارس الواجهة تعمل **قبل** أي تقدم في
  المكونات، فالرفض (شمعة متطورة/متأخرة/مكررة/حالة مستقبلية) لا يترك أثرًا
  جانبيًا؛ ومع ذلك فالخرق خطأ قانوني — أنشئ محركًا بديلًا بعد إصلاح
  المصدر (لا استرداد).
- **حالة التقلب من المستدعي**: الواجهة لا تشغّل ``VolatilityEngine`` —
  المستدعي يمرر الحالة عند كل شمعة (نمط verify_phase2 نفسه)؛ ``None``
  مقبولة (أول شمعة) فتُغلق كل الأبواب المعتمدة عليها بلا قيم مزيفة.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from market_state.volatility import VolatilityState
from schemas import BreakDirection, Candle, Swing

from ._guards import StreamGuards
from .bos import BosConfig, StructureBreakEngine
from .displacement import DisplacementConfig, DisplacementDetector
from .events import EmittedEvent
from .fvg import FvgConfig, FvgSnapshot, FvgTracker
from .order_blocks import OrderBlockConfig, OrderBlockSnapshot, OrderBlockTracker
from .premium_discount import (
    PremiumDiscountConfig,
    PremiumDiscountEngine,
    PremiumDiscountSnapshot,
)
from .swings import SwingConfig, SwingDetector

__all__ = ["StructureConfig", "StructureEngine"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class StructureConfig:
    """إعداد محرك البنية الكامل — تجميع إعدادات المكونات الستة.

    القيم الافتراضية **نقاط انطلاق إعدادية للتقييم والمعايرة — ليست
    توصيات تداول** (نفس عقد ``VolatilityConfig``): العتبات السعرية أصلًا
    ليست هنا — مضاعِفاتها في ``VolatilityConfig.multipliers`` وكل تقييم
    يقرأها من حالة التقلب عند الشمعة.
    """

    #: كاشف المتطرفات (§11.1): تأخير التأكيد وقوة البروز.
    swings: SwingConfig = field(default_factory=SwingConfig)
    #: محرك الكسور (§11.2-3): سياسة خرق الفتيل.
    bos: BosConfig = field(default_factory=BosConfig)
    #: كاشف الإزاحة (§11.4): البوابات الإحصائية والنوافذ.
    displacement: DisplacementConfig = field(default_factory=DisplacementConfig)
    #: متعقّب الفجوات (§11.5): هندسة ثلاثية الشموع صرفة — بلا مقابض (موثق).
    fvg: FvgConfig = field(default_factory=FvgConfig)
    #: متعقّب كتل الأوامر (§11.6): نافذتا التتبع والتحقق وأوزان الجودة.
    order_blocks: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    #: محرك الموقع (§11.7): رياضيات صرفة موقعية — بلا مقابض (موثق).
    premium_discount: PremiumDiscountConfig = field(default_factory=PremiumDiscountConfig)


# ═════════════════════════════ المحرك ═════════════════════════════


class StructureEngine:
    """واجهة بنية السوق لزوج (أداة، إطار) واحد — شمع مغلقة فقط.

    الاستخدام: أنشئ محركًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)،
    وغذّه كل شمعة مغلقة مع حالة التقلب عند الشمعة نفسها؛ الخرج أحداث
    مؤكدة عند تلك الشمعة حصرًا. لعمق الحالة (المتطرفات الحية، الفجوات
    المعلقة، مناطق كتل الأوامر، الموقع الجاري...) تُعرَض المكونات نفسها
    عبر الخصائص واللوقطات — لتغذية السيولة (3-d) والانحياز (3-e) والدمج
    (3-f) عبر المستدعي.
    """

    def __init__(
        self,
        config: StructureConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else StructureConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        self._swings = SwingDetector(
            self._config.swings, instrument_id=instrument_id, timeframe=timeframe
        )
        self._bos = StructureBreakEngine(
            self._config.bos, instrument_id=instrument_id, timeframe=timeframe
        )
        self._displacement = DisplacementDetector(
            self._config.displacement, instrument_id=instrument_id, timeframe=timeframe
        )
        self._fvg = FvgTracker(self._config.fvg, instrument_id=instrument_id, timeframe=timeframe)
        self._order_blocks = OrderBlockTracker(
            self._config.order_blocks, instrument_id=instrument_id, timeframe=timeframe
        )
        self._premium = PremiumDiscountEngine(
            self._config.premium_discount, instrument_id=instrument_id, timeframe=timeframe
        )

    # ── الخصائص ──

    @property
    def config(self) -> StructureConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.timeframe

    @property
    def swings(self) -> tuple[Swing, ...]:
        """المتطرفات المؤكدة بترتيب التأكيد — سجل تراكمي للمصبّات (3-d/3-e)."""
        return self._swings.swings

    @property
    def last_external_high(self) -> Swing | None:
        """آخر قمة خارجية — سقف الإطار الخارجي الجاري."""
        return self._swings.last_external_high

    @property
    def last_external_low(self) -> Swing | None:
        """آخر قاع خارجي — أرضية الإطار الخارجي الجاري."""
        return self._swings.last_external_low

    @property
    def framework_direction(self) -> BreakDirection | None:
        """اتجاه الإطار الخارجي (آخر كسر خارجي) — None قبل أول كسر خارجي."""
        return self._bos.framework_direction

    @property
    def swing_detector(self) -> SwingDetector:
        """كاشف المتطرفات — وصول عميق للحالة عند الحاجة (3-d/3-e)."""
        return self._swings

    @property
    def break_engine(self) -> StructureBreakEngine:
        """محرك الكسور — المستويات الحية وآلة الإطار."""
        return self._bos

    @property
    def displacement_detector(self) -> DisplacementDetector:
        """كاشف الإزاحة — عدّاد النوافذ الإحصائية."""
        return self._displacement

    @property
    def fvg_tracker(self) -> FvgTracker:
        """متعقّب الفجوات — الملء والإبطال التتبعيان (§11.5)."""
        return self._fvg

    @property
    def order_block_tracker(self) -> OrderBlockTracker:
        """متعقّب كتل الأوامر — المرشحات المعلقة والمناطق الحية (§11.6)."""
        return self._order_blocks

    @property
    def premium_discount_engine(self) -> PremiumDiscountEngine:
        """محرك الموقع — النطاق المعرّى وحالة الجانب (§11.7)."""
        return self._premium

    # ── القراءة ──

    def gaps(self) -> tuple[FvgSnapshot, ...]:
        """لقطات الفجوات بترتيب التكوين — تفويض للمتعقّب (§11.5)."""
        return self._fvg.gaps()

    def order_blocks(self) -> tuple[OrderBlockSnapshot, ...]:
        """لقطات مناطق كتل الأوامر بترتيب البث — تفويض للمتعقّب (§11.6)."""
        return self._order_blocks.order_blocks()

    def premium_discount_state(self) -> PremiumDiscountSnapshot:
        """لقطة موقع premium/discount الجاري — تفويض للمحرك (§11.7)."""
        return self._premium.state

    # ── التغذية ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة — الأحداث المؤكدة **عند هذه الشمعة** حصرًا.

        الترتيب الداخلي (حتمي موثق في ترويسة الموديول): تسجيل متطرفات
        الشمعة ← تقييم الكسور ← الإزاحة ← الفجوات ← كتل الأوامر (بأحداث
        الإزاحة والكسر الجارية) ← الموقع (بمتطرفات الشمعة). الحالة
        ``vol=None`` مقبولة (لا حالة تقلب بعد).
        """
        # الحوارس قبل أي تقدم في المكونات — الرفض بلا أثر جانبي (عقود الموديول).
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        new_swings = self._swings.update(candle, vol)
        for swing in new_swings:
            self._bos.on_swing(swing)
        bos_events = self._bos.update(candle, vol)
        displacement_events = self._displacement.update(candle, vol)
        events: list[EmittedEvent] = list(bos_events)
        events.extend(displacement_events)
        events.extend(self._fvg.update(candle, vol))
        events.extend(self._order_blocks.update(candle, vol, displacement_events, bos_events))
        events.extend(self._premium.update(candle, new_swings))
        return events
