"""الواجهة الجامعة لمحرك البنية — §11.1-§11.4 عبر مسار واحد لكل شمعة.

تملك :class:`StructureEngine` كاشفًا واحدًا لكل نوع (متطرفات/كسور/إزاحة)
لزوج (أداة، إطار) واحد، وتؤلف بينها بترتيب موثق عند كل شمعة مغلقة:

1. المتطرفات المؤكدة عند الشمعة تُستخرج من :class:`~structure.swings.SwingDetector`
   وتُسجَّل فورًا لدى محرك الكسور (``on_swing`` قبل ``update`` — برهان أمان
   الترتيب داخل :class:`~structure.bos.StructureBreakEngine`).
2. شمعة الكسور تُقيَّم (INTERNAL_BOS/EXTERNAL_BOS/CHOCH — حتى حدث لكل اتجاه).
3. شمعة الإزاحة تُقيَّم (DISPLACEMENT_UP/DOWN — حدث واحد كأقصى).

الخرج قائمة :class:`~structure.events.EmittedEvent` بترتيب حتمي موثق
(كسور البنية UP ثم DOWN، ثم الإزاحة). **تجميع المغلف** (``event_id``/
``trace_id``/``receive_time``) مسؤولية الناشر اللاحق (3-f) ولا يُبنى هنا.

العقود الموثقة (تُقفل في tests/property/test_structure_properties.py):

- **لا-نظرة-مستقبلية (§26.3)**: كل مكون آلة حالة تزايدية — خرج البادئة
  [0..k] لا يتغير بتمديد الذيل أبدًا (خاصية البادئة المفروضة على
  الواجهة كاملة مع محرك التقلب الموازي).
- **الحتمية الصرفة**: نفس الشموع وحالات التقلب ⇒ نفس الأحداث والمتطرفات
  بالتطابق التام.
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
from .swings import SwingConfig, SwingDetector

__all__ = ["StructureConfig", "StructureEngine"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class StructureConfig:
    """إعداد محرك البنية الكامل — تجميع إعدادات المكونات الثلاثة.

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


# ═════════════════════════════ المحرك ═════════════════════════════


class StructureEngine:
    """واجهة بنية السوق لزوج (أداة، إطار) واحد — شمع مغلقة فقط.

    الاستخدام: أنشئ محركًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)،
    وغذّه كل شمعة مغلقة مع حالة التقلب عند الشمعة نفسها؛ الخرج أحداث
    مؤكدة عند تلك الشمعة حصرًا. لعمق الحالة (المتطرفات الحية، الإطار
    الخارجي...) تُعرَض المكونات نفسها عبر الخصائص — لتغذية السيولة (3-c)
    والانحياز (3-e) عبر المستدعي.
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
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._guards.timeframe

    @property
    def swings(self) -> tuple[Swing, ...]:
        """المتطرفات المؤكدة بترتيب التأكيد — سجل تراكمي للمصبّات (3-c/3-e)."""
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
        """كاشف المتطرفات — وصول عميق للحالة عند الحاجة (3-c/3-e)."""
        return self._swings

    @property
    def break_engine(self) -> StructureBreakEngine:
        """محرك الكسور — المستويات الحية وآلة الإطار."""
        return self._bos

    @property
    def displacement_detector(self) -> DisplacementDetector:
        """كاشف الإزاحة — عدّاد النوافذ الإحصائية."""
        return self._displacement

    # ── التغذية ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة — الأحداث المؤكدة **عند هذه الشمعة** حصرًا.

        الترتيب الداخلي (حتمي موثق): تسجيل متطرفات الشمعة ← تقييم الكسور
        ← تقييم الإزاحة. الحالة ``vol=None`` مقبولة (لا حالة تقلب بعد).
        """
        # الحوارس قبل أي تقدم في المكونات — الرفض بلا أثر جانبي (عقود الموديول).
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        events: list[EmittedEvent] = []
        for swing in self._swings.update(candle, vol):
            self._bos.on_swing(swing)
        events.extend(self._bos.update(candle, vol))
        events.extend(self._displacement.update(candle, vol))
        return events
