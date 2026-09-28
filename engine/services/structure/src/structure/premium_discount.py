"""محرك الموقع premium/discount — §11.7 حرفيًا.

نص §11.7: «For a defined dealing range: equilibrium = (range_high +
range_low) / 2; premium = price > equilibrium; discount = price <
equilibrium. The dealing range must be explicitly named. The engine
refuses ambiguous premium/discount calculations that change range
definition silently.» — الترجمة التشغيلية بتلات ثلاث:

**النطاق معرّى الاسم صراحةً (الرفض الملتبس)**: الاسم الوحيد في هذا الطور
``"external_range"`` (ثابت معلن — لا مقبض إعداد: قابليته للتهيئة تفتح
باب التباس التعريف الذي يرفضه §11م)، ومصدره **المتطرفات الخارجية
المؤكدة** المُغذاة من المستدعي: ``range_low`` = أدنى سعر قاع خارجي،
``range_high`` = أعلى سعر قمة خارجية (نفس اشتقاق حدود النطاق في خريطة
السيولة — تناظر المصدر). المتطرفات الداخلية تُقبل في التغذية وتُهمل
للنطاق (حركة داخل الإطار لا تحده). النطاق **غير معرف** ما لم يوجد قمة
خارجية وقاع خارجي معًا وسعراه متباعدان قطعيًا (``range_low <
range_high`` — النطاق المنحل قسمةٌ على صفر في المسافة المطبة) — قد
يستمر التعريف معلقًا مؤقتًا (قمة خارجية دون قاع أدنى منها سعرًا)،
والامتداد أحادي الاتجاه (السقف لا ينقص والأرضية لا ترتفع) يصلح التعريف
حتمًا مع أول متطرف مؤهل.

**لا إعادة تعريف صامتة**: النطاق **يمتد وحده** — قمة خارجية جديدة فوق
السقف ترفعه، وقاع خارجي جديد تحت الأرضية يخفضها؛ النطاق **لا يتقلص
أبدًا** (إعادة الترسيس خارجة عن هذا الطور ومسؤولية طبقة الدمج/المرحلة 7
حيث تُدار دورة حياة النطاقات صراحةً) — فلا يتغير حد أُعلن يومًا بلا
حدثٍ مسمّى. امتداد النطاق يُعيد تقييم الموقع في الشمعة نفسها والحمولة
تحمل حدود النطاق الجاري فيصح التفسير بلا غموض.

**الموقع (متساويات صارمة حرفيًا)**: ``equilibrium = (range_high +
range_low) / 2``؛ الإغلاق فوقها ``PREMIUM`` وتحتها ``DISCOUNT``،
والمساواة بالضبط ``NEUTRAL`` (§11.7 يعطي المتساويات الصارمة وحدها —
السعر على المنصف عينه ليس في أي الجانبين). الرياضيات صرفة موقعية **بلا
عتبات ولا حالة تقلب** — لذلك ``update`` لا يقبل معامل تقلب أصلًا
(التوحيد الشكلي بمعامل غير مقروء يعقّد العقد بلا معلومة).

**البث عند الانتقالات حصرًا** — جدول الانتقالات الموثق كاملًا:

=====================  =====================  =====================
من \\ إلى              PREMIUM                DISCOUNT
=====================  =====================  =====================
UNKNOWN (بلا نطاق)     ``PREMIUM_LOCATION``   ``DISCOUNT_LOCATION``
PREMIUM                —                      ``DISCOUNT_LOCATION``
DISCOUNT               ``PREMIUM_LOCATION``   —
NEUTRAL                لا بث                  لا بث
=====================  =====================  =====================

- أول تحديد للموقع بعد اكتمال النطاق يُبث (انتقال من غير المعرف — من
  ``UNKNOWN``).
- **الانتقالات إلى المحايد ومنه لا تُبث أبدًا** (المحايد حالة معلنة تُقرأ
  من :attr:`state` لا حدثًا يُبث): عودة الجانب نفسه بعد محايد لا تُبث —
  سجل الأحداث يصف عبور المنصف بين الجانبين، والموقع الجاري يُقرأ من
  الحالة.
- البقاء في الجانب نفسه لا يُبث (انتقال فقط).

``normalized_distance`` = (close − equilibrium) / ((range_high −
range_low) / 2) — إقصاء مطبَّع يجوز أن يتجاوز ‎±1‎ عندما يخرج السعر من
النطاق نفسه (خارج النطاق معلومة لا خطأ — موثق في الأسس 3-a).

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_premium_discount.py):

- **لا-نظرة-مستقبلية (§26.3)**: الموقع عند الشمعة t دالة في الإغلاق
  والمتطرفات المؤكدة حتى t حصرًا (``confirmation_time`` المتطرف المُغذى
  لا يعلو ``bar_time`` الشمعة الجارية — حارس صاخب).
- **الحتمية الصرفة**: نفس الشموع والمتطرفات ⇒ نفس الأحداث والحالة
  بالتطابق التام.
- **الصخب في التحقق**: عقود :mod:`structure._guards` للشموع، ومتطرف
  بإطار غريب، أو مكرر المعرف، أو بعلاقته القانونية مكسورة
  (``bar_time > confirmation_time``)، أو مؤكد في المستقبل — كلها
  ``ValueError`` صاخبة.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from schemas import (
    Candle,
    EventType,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    Swing,
    SwingDirection,
    SwingScope,
)

from ._guards import StreamGuards
from .events import EmittedEvent

__all__ = [
    "RANGE_NAME",
    "PremiumDiscountConfig",
    "PremiumDiscountEngine",
    "PremiumDiscountLocation",
    "PremiumDiscountSnapshot",
]

#: اسم نطاق المعالجة الوحيد في هذا الطور (§11.7 «must be explicitly
#: named») — المتطرفات الخارجية المؤكدة مصدرُه؛ ثابت معلن لا مقبض إعداد
#: (قابلية تهيئته تفتح باب التباس التعريف الصامت الذي يرفضه §11.7).
RANGE_NAME = "external_range"


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class PremiumDiscountConfig:
    """إعداد محرك الموقع — **بلا مقابض في هذا الطور** (موثق عمدًا).

    الرياضيات صرفة موقعية بنص §11.7 (منصف ومتساويتان صارمتان) بلا عتبة
    ولا نافذة؛ ومصدر النطاق واسمه مقيدان تعريفيًا بالطور (المتطرفات
    الخارجية باسم ``"external_range"``) — فلا شيء قابل للضبط هنا أصلًا.
    وجود الصنف تناظرُ بنيةٍ مع بقية المكونات ومقعدٌ للامتداد الموثق.
    """


# ═══════════════════════ الحالة واللقطات ═══════════════════════


class PremiumDiscountLocation(StrEnum):
    """موقع الإغلاق من منصف النطاق **الداخلي التتبعي** — أربع حالات.

    تمييزًا له عن :class:`~schemas.structure.PremiumDiscountSide` البثية
    (الجانبان حصرًا — قيمتا §20): ``UNKNOWN`` (النطاق غير معرف بعد —
    «يرفض المحرك الحساب الملتبس» فيعود بلا أحداث) و``NEUTRAL`` (الإغلاق
    على المنصف بالضبط — حالة معلنة تُقرأ لا تُبث) حالتان تتبعيتان لا
    حدث لهما في قاموس §20.
    """

    UNKNOWN = "UNKNOWN"  # النطاق غير معرف بعد (أو منحل)
    NEUTRAL = "NEUTRAL"  # close == equilibrium بالضبط
    PREMIUM = "PREMIUM"  # close > equilibrium
    DISCOUNT = "DISCOUNT"  # close < equilibrium


@dataclass(frozen=True)
class PremiumDiscountSnapshot:
    """لقطة حالة الموقع — النطاق معرّى الاسم بحدوده أو غيابه المعلن.

    ``range_low``/``range_high``/``equilibrium`` كلها ``None`` قبل تعريف
    النطاق (غياب معلن لا قيمة مزيفة)، و``location`` من
    :class:`PremiumDiscountLocation` — الموقع الجاري حتى دون بث.
    """

    range_name: str
    range_low: float | None
    range_high: float | None
    equilibrium: float | None
    location: PremiumDiscountLocation


# ═════════════════════════════ المحرك ═════════════════════════════


class PremiumDiscountEngine:
    """محرك الموقع الموضعي لكل (أداة، إطار) — شمع مغلقة فقط (§11.7).

    الاستخدام (التركيب في :class:`structure.engine.StructureEngine`): غذّه
    كل شمعة مغلقة مع المتطرفات المؤكدة **عند الشمعة نفسها** (يُهمل منها
    غير الخارجي)؛ البث عند انتقالات الجانب حصرًا (جدول الترويسة)،
    والحالة الجارية دومًا عبر :attr:`state`. انظر عقود الموديول.
    """

    def __init__(
        self,
        config: PremiumDiscountConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else PremiumDiscountConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        self._range_high: float | None = None  # أعلى قمة خارجية (لا ينقص)
        self._range_low: float | None = None  # أدنى قاع خارجي (لا يرتفع)
        self._location = PremiumDiscountLocation.UNKNOWN
        self._seen_swing_ids: set[str] = set()

    # ── الخصائص ──

    @property
    def config(self) -> PremiumDiscountConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يمرر في البناء."""
        return self._guards.timeframe

    @property
    def state(self) -> PremiumDiscountSnapshot:
        """لقطة الحالة الجارية — النطاق معرّى الاسم أو غيابه المعلن."""
        defined = self._range_high is not None and self._range_low is not None
        return PremiumDiscountSnapshot(
            range_name=RANGE_NAME,
            range_low=self._range_low,
            range_high=self._range_high,
            equilibrium=self._equilibrium() if defined else None,
            location=self._location,
        )

    # ── التغذية ──

    def update(
        self,
        candle: Candle,
        new_swings: Sequence[Swing] = (),
    ) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة ومتطرفاتها المؤكدة — بثّ انتقالات الجانب.

        ترتيب المعالجة الداخلي (حتمي موثق): قبول الشمعة ← تحقق المتطرفات
        وتمديد النطاق بالخارجي منها ← تقييم الموقع بالإغلاق ضد المنصف
        الجاري (شامل امتداد الشمعة نفسها) ← البث عند الانتقال حصرًا.
        """
        self._guards.check_candle(candle)
        for swing in new_swings:
            self._accept_swing(swing, candle)
        self._extend_range(new_swings)
        equilibrium = self._equilibrium()
        if equilibrium is None:
            # النطاق غير معرف أو منحل — الرفض الملتبس لا الحساب الناقص
            # (الموقع يبقى UNKNOWN حتى يكتمل التعريف).
            return []
        if candle.close > equilibrium:
            location = PremiumDiscountLocation.PREMIUM
        elif candle.close < equilibrium:
            location = PremiumDiscountLocation.DISCOUNT
        else:
            location = PremiumDiscountLocation.NEUTRAL
        events = self._transition(location, candle, equilibrium)
        self._location = location
        return events

    # ── الداخلية ──

    def _accept_swing(self, swing: Swing, candle: Candle) -> None:
        """حوارس المتطرف المُغذى — الصخب لا السكوت (عقود الموديول).

        :raises ValueError: متطرف بإطار غريب عن هوية المحرك، أو بعلاقته
            القانونية مكسورة (``bar_time > confirmation_time``)، أو مؤكد
            في المستقبل (``confirmation_time > bar_time`` الشمعة الجارية
            — تسريب §26.3)، أو مكرر المعرف.
        """
        timeframe = self._guards.timeframe
        if timeframe is not None and swing.timeframe != timeframe:
            raise ValueError(
                f"متطرف بإطار غريب عن هوية المحرك: {swing.timeframe!r} مقابل "
                f"{timeframe!r} — النطاق المعرّى لإطار واحد حصرًا"
            )
        if swing.bar_time > swing.confirmation_time:
            raise ValueError(
                f"علاقة قانونية مكسورة: bar_time {swing.bar_time} بعد "
                f"confirmation_time {swing.confirmation_time} — الفارق بينهما هو "
                "تأخير التأكيد ولا يكون سالبًا أبدًا (§11.1)"
            )
        if swing.confirmation_time > candle.bar_time:
            raise ValueError(
                f"متطرف مؤكد في المستقبل: confirmation_time {swing.confirmation_time} "
                f"أحدث من شمعة التقييم {candle.bar_time} — تسريب §26.3 يُرفض صاخبًا"
            )
        if swing.swing_id in self._seen_swing_ids:
            raise ValueError(f"متطرف مكرر المعرف: {swing.swing_id} — التغذية لمرة واحدة")
        self._seen_swing_ids.add(swing.swing_id)

    def _extend_range(self, new_swings: Sequence[Swing]) -> None:
        """تمديد النطاق بالمتطرفات الخارجية — امتداد أحادي لا تقلص أبدًا.

        القمة الخارجية ترفع السقف إذا علتْه، والقاع الخارجي يخفض الأرضية
        إذا نزل تحتها؛ ما دون ذلك لا يمس النطاق (لا إعادة تعريف صامتة —
        عقود الموديول). المتطرف الداخلي يُهمل أصلًا (حركة داخل الإطار).
        """
        for swing in new_swings:
            if swing.external_or_internal is not SwingScope.EXTERNAL:
                continue
            if swing.direction is SwingDirection.HIGH:
                if self._range_high is None or swing.price > self._range_high:
                    self._range_high = swing.price
            elif self._range_low is None or swing.price < self._range_low:
                self._range_low = swing.price

    def _equilibrium(self) -> float | None:
        """المنصف الحرفي: ``(range_high + range_low) / 2`` (§11.7)."""
        if self._range_high is None or self._range_low is None:
            return None
        if self._range_high <= self._range_low:
            return None  # نطاق منحل/معلق — لا منصف لمنطق منحل
        return (self._range_high + self._range_low) / 2.0

    def _transition(
        self,
        location: PremiumDiscountLocation,
        candle: Candle,
        equilibrium: float,
    ) -> list[EmittedEvent]:
        """تطبيق جدول الانتقالات — البث عند عبور الجانبين وأول تحديد فقط.

        الانتقالات إلى المحايد ومنه لا تُبث (عقود الموديول): سجل الأحداث
        يصف عبور المنصف بين الجانبين والحالة تُقرأ لكل شمعة.
        """
        previous = self._location
        if location is PremiumDiscountLocation.NEUTRAL or previous is location:
            return []
        if previous is PremiumDiscountLocation.NEUTRAL:
            return []  # عودة إلى الجانب نفسه بعد محايد — لا بث
        side = (
            PremiumDiscountSide.PREMIUM
            if location is PremiumDiscountLocation.PREMIUM
            else PremiumDiscountSide.DISCOUNT
        )
        event_type = (
            EventType.PREMIUM_LOCATION
            if location is PremiumDiscountLocation.PREMIUM
            else EventType.DISCOUNT_LOCATION
        )
        assert self._range_high is not None and self._range_low is not None
        half_width = (self._range_high - self._range_low) / 2.0
        payload = PremiumDiscountEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=candle.bar_time,
            range_name=RANGE_NAME,
            range_low=self._range_low,
            range_high=self._range_high,
            equilibrium=equilibrium,
            location=side,
            normalized_distance=(candle.close - equilibrium) / half_width,
            price=candle.close,
        )
        return [EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)]

    def _required_instrument(self) -> str:
        """أداة المحرك — البث لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار المحرك — البث لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
