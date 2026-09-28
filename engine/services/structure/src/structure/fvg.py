"""متعقّب فجوات القيمة العادلة (FVG) — §11.5 حرفيًا.

نص §11.5: «For a three-bar sequence: bullish FVG candidate: current low >
high of bar two-bars-back; bearish FVG candidate: current high < low of bar
two-bars-back. The gap is stored as a price interval with: origin time;
direction; size normalized by local ATR; fill percentage; first mitigation
time; invalidation/consumption state. The engine does not assume every FVG
must fill.» — هذا الموديول الترجمة التشغيلية لتلك الفقرة كاملة.

**الكشف (ثلاثي الشموع، شموع مغلقة فقط §27)**: عند الشمعة i المرشحة
الصاعدة ``low[i] > high[i-2]`` **قطعيًا** (المساواة ليست فجوة)، وفاصلها
``[high[i-2], low[i]]``؛ والهابطة ``high[i] < low[i-2]`` وفاصلها
``[high[i], low[i-2]]``. الشمعة الوسطى i-1 لا تدخل الكشف أصلًا (تعريف
الفجوة ثلاثي الأطراف حصرًا) — القرار من الشموع ‎[i-2, i]‎ حصرًا فلا-نظرة-
مستقبلية **بالبناء**. **استحالة الاتجاهين معًا** (برهان): اجتماعهما
يلزم ``low[i] > high[i-2]`` و``high[i] < low[i-2]`` ومنه
``low[i-2] > high[i-2]`` — تناقض؛ فحدث واحد كأقصى في الشمعة.

**تخزين الفجوة (السمات الست الحرفية §11.5)** — السجل الداخلي
:class:`_TrackedGap` يحمل: ``origin_time`` (طابع شمعة التأكيد i نفسها —
الفجوة تُعرف عند إقفالها)، ``direction``، ``size_atr`` (العرض ÷ ATR عند
التكوين — «size normalized by local ATR»)، ``fill_fraction`` («fill
percentage»)، ``first_mitigation_time``، والحالة ``state``
(«invalidation/consumption state»). اللقطة العلنية
:class:`FvgSnapshot` مجمّدة تحمل الستة كلها مع الفاصل والمعرف.

**آلة الحالة التتبعية (داخلية لا تُبث — انظر البث أدناه)**:

- ``CREATED``: لم يتداول السعر داخل الفاصل قط (fill_fraction == 0).
- ``MITIGATED``: أول تغلغل جزئي (0 < fill_fraction < 1) — يسجل
  ``first_mitigation_time`` بطابع شمعة التغلغل الأولى.
- ``FILLED``: اجتياح المجال كاملًا داخل الشمعة (بلغ القاعُ الحافةَ البعيدة
  صعودًا: ``min_low ≤ gap_low`` — أو القمة الهابطة ``max_high ≥ gap_high``)
  **دون إغلاق وراء الحافة البعيدة**: ملء 100% بطريق الفتيل/التداول ثم
  ارتداد الإغلاق.
- ``INVALIDATED`` (النهائية): إغلاق **وراء الحافة البعيدة** صراحةً
  (الصاعدة: ``close < gap_low``؛ الهابطة: ``close > gap_high``) — الإغلاق
  وراء الحافة البعيدة قبولٌ يتجاوز الملء (الاجتياح الكامل حتمٌ به:
  low ≤ close < gap_low) ويُبطل الفجوة كمقاومة/دعم («invalidation/consumption
  state» §11.5) — تُقفز إليها من أي حالة (CREATED/MITIGATED/FILLED) مباشرة.

``fill_fraction`` رتيبة غير متناقصة (تتبع أقصى تغلغل: أدنى قاع منذ التكوين
للصاعدة / أعلى قمة للهابطة، مقصوصة إلى [0, 1]) وتُحدَّث في كل شمعة **بغضّ
النظر عن الحالة** — قياس التداول صحيح مستمرًا حتى بعد الإبطال.

**«لا يُفترض أن كل فجوة يجب أن تُملأ» (§11.5 حرفيًا)**: لا انتهاء صلاحية،
ولا إسقاطًا صامتًا، ولا ملءً افتراضيًا — الفجوة غير الملموسة تبقى
``CREATED`` (أو ``MITIGATED`` جزئيًا) إلى ما لا نهاية في سجل المتعقّب،
والتقليم مسؤولية طبقة التخزين اللاحقة (3-f/المرحلة 7) لا الكاشف.

**البث**: حدث ``FVG_BULLISH``/``FVG_BEARISH`` **مرة واحدة حصرًا** لكل فجوة
عند شمعة تكوينها، بحمولة :class:`~schemas.structure.FvgEventPayload` بحالة
``CREATED`` — الملء والإبطال حالة كاشف تتبعية تُقرأ من ``gaps()`` ولا
تُبث أبدًا (قاموس §20 لا يعرف حدث «فجوة مُملوءة» أصلاً، وFvgState في
الأسس 3-a واحدة هي CREATED لهذا العين).

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_fvg.py):

- **لا-نظرة-مستقبلية (§26.3)**: كشف الفجوة عند الشمعة i دالة في
  ‎[i-2, i]‎ حصرًا (خاصية البادئة في tests/property/test_structure_properties.py).
- **الحتمية الصرفة**: نفس الشموع والحالات ⇒ نفس الفجوات والمعرفات
  بالتطابق التام — ``gap_id`` مفتاح ``uuid5`` خالٍ من الأسعار (روح D-07)
  فثابت هويةً تحت التحجيم السعري.
- **العتبات التطبيعية (§16)**: ``size_atr`` قسمة على ATR من حالة التقلب
  عند التكوين وحدها — ``atr`` غائب (``vol=None`` أو دافئ) أو منحل
  (``atr ≤ 0``) ⇒ **لا تكوين فجوة ولا بث** (التطبيع أصل عقد التخزين
  ولا يُختلق حجم بلا أصل — نمط رفض الكسور نفسه)؛ الفجوة تكوَّن عند
  شمعة تعذّر فيها التطبيع **لا تُلتقط لاحقًا** (الكشف ثلاثي الشموع لا
  يتأخر).
- **الصخب في التحقق**: عقود :mod:`structure._guards` كاملة (شمعة متطورة،
  خلط أداة/إطار، تكرار/تأخر ``bar_time``، حالة تقلب من المستقبل).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5
from uuid import UUID as _UUID

from market_state.volatility import VolatilityState
from schemas import Candle, EventType, FvgDirection, FvgEventPayload, FvgState

from ._guards import StreamGuards
from .events import EmittedEvent

__all__ = [
    "FvgConfig",
    "FvgLifecycle",
    "FvgSnapshot",
    "FvgTracker",
]

#: مساحة اسم معرف الفجوة — نمط ترميز المتطرفات نفسه (uuid5 فوق
#: NAMESPACE_URL بمفتاح نطاق معلن): تحديد لا عشوائية — نفس المفتاح ⇒ نفس
#: المعرف دائمًا عبر الجلسات والإعادات (روح D-07).
_FVG_NAMESPACE: _UUID = uuid5(NAMESPACE_URL, "ai-market-reasoning-engine/structure/fvg")


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class FvgConfig:
    """إعداد متعقّب الفجوات — **بلا مقابض في هذا الطور** (موثق عمدًا).

    الكشف هندسة صرفة نصّها §11.5 (مقارنتان قطبيتان ثلاثيتا الشموع) والتطبيع
    الوحيد (``size_atr``) يقرأ ATR من حالة التقلب وحدها — فلا عتبة قابلة
    للضبط هنا أصلًا (بوابة §16: كل عتبة سعرية في حالات التقلب لا الإعداد).
    وجود الصنف تناظرُ بنيةٍ مع بقية المكونات ومقعدٌ للامتداد الموثق لاحقًا.
    """


# ═══════════════════════ الحالة التتبعية الداخلية ═══════════════════════


class FvgLifecycle(StrEnum):
    """دورة حياة الفجوة التتبعية (الداخلية) — غير بثية.

    تمييزًا لها عن :class:`~schemas.structure.FvgState` البثية (CREATED
    وحدها — قرار الأسس 3-a): هذه القيم الأربع هي «invalidation/consumption
    state» بنص §11.5 — حالة تُقرأ من اللقطات لا تُبث كأحداث.
    """

    CREATED = "CREATED"  # لم يُتداول داخل الفاصل قط
    MITIGATED = "MITIGATED"  # تغلغل جزئي (أول تخفيف)
    FILLED = "FILLED"  # اجتياح كامل دون إغلاق وراء الحافة البعيدة
    INVALIDATED = "INVALIDATED"  # إغلاق وراء الحافة البعيدة (نهائية)


@dataclass(frozen=True)
class FvgSnapshot:
    """لقطة فجوة معلقة — السمات الست الحرفية §11.5 مع الفاصل والمعرف.

    ``fill_fraction`` ∈ [0, 1] («fill percentage»)، و``first_mitigation_time``
    محدودة بلا قيمة قبل أول تغلغل (غياب معلن لا قيمة مزيفة)، و``state``
    من :class:`FvgLifecycle` (الحالة التتبعية — لا البثية).
    """

    gap_id: str
    origin_time: datetime
    direction: FvgDirection
    gap_low: float
    gap_high: float
    size_atr: float
    fill_fraction: float
    first_mitigation_time: datetime | None
    state: FvgLifecycle


@dataclass
class _TrackedGap:
    """فجوة في السجل الحي — كائن داخلي يجري (الملء والحالة يتحدثان).

    ``extreme``: أقصى تغلغل منذ التكوين — أدنى قاع للصاعدة (تبدأ قيمةُ
    شمعة التكوين = الحافة القريبة فلا تغلغل ذاتيًا) / أعلى قمة للهابطة.
    """

    gap_id: str
    origin_time: datetime
    direction: FvgDirection
    gap_low: float
    gap_high: float
    size_atr: float
    extreme: float
    fill_fraction: float = 0.0
    first_mitigation_time: datetime | None = None
    state: FvgLifecycle = FvgLifecycle.CREATED


# ═════════════════════════════ المتعقّب ═════════════════════════════


class FvgTracker:
    """متعقّب الفجوات الموضعي لكل (أداة، إطار) — شمع مغلقة فقط (§11.5).

    الاستخدام: أنشئ متعقّبًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)
    وغذّه كل شمعة مغلقة مع حالة التقلب عند الشمعة نفسها؛ الكشف من
    ‎[i-2, i]‎ حصرًا، والبث مرة واحدة عند التكوين، والملء/الإبطال يُقرآن
    من :meth:`gaps`. انظر عقود الموديول كاملة.
    """

    def __init__(
        self,
        config: FvgConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else FvgConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        # تاريخ الشمعتين السابقتين حصرًا — الكشف الثلاثي لا يحتاج أعمق.
        self._history: deque[Candle] = deque(maxlen=2)
        self._gaps: list[_TrackedGap] = []

    # ── الخصائص ──

    @property
    def config(self) -> FvgConfig:
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

    # ── القراءة ──

    def gaps(self) -> tuple[FvgSnapshot, ...]:
        """لقطات كل الفجوات بترتيب التكوين — سجل تراكمي لا رجعة فيه.

        «لا يُفترض أن كل فجوة يجب أن تُملأ»: الفجوات غير الملموسة تبقى في
        السجل إلى ما لا نهاية (لا تقليم في الكاشف) — اللقطات تُبنى طازجة
        من السجل الحي فلا يوزَّع المخزن الداخلي نفسه أبدًا.
        """
        return tuple(
            FvgSnapshot(
                gap_id=gap.gap_id,
                origin_time=gap.origin_time,
                direction=gap.direction,
                gap_low=gap.gap_low,
                gap_high=gap.gap_high,
                size_atr=gap.size_atr,
                fill_fraction=gap.fill_fraction,
                first_mitigation_time=gap.first_mitigation_time,
                state=gap.state,
            )
            for gap in self._gaps
        )

    # ── التغذية ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة — حدث التكوين **عند هذه الشمعة** حصرًا.

        قائمة فارغة أو حدث واحد حصرًا (استحالة الاتجاهين معًا — برهان
        الترويسة). ترتيب المعالجة الداخلي (حتمي موثق): تحديث الملء
        والحالات للفجوات القائمة بالشمعة الجارية ← كشف فجوة جديدة من
        ‎[i-2, i]‎ ← إلحاق الشمعة بالتاريخ. ``vol = None`` أو ATR دافئ/منحل
        ⇒ لا كشف (انظر عقود الموديول) مع استمرار تتبع الملء للقائم.
        """
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        for gap in self._gaps:
            self._track_fill(gap, candle)
        events = self._detect(candle, vol)
        self._history.append(candle)
        return events

    # ── الداخلية ──

    def _detect(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """كشف الفجوة الثلاثية عند الشمعة i من ‎[i-2, i]‎ حصرًا.

        المساواة ليست فجوة (نص §11.5 قاطع)، وغياب ATR صالح يمنع التكوين
        كله (``size_atr`` أصل عقد التخزين — عقود الموديول).
        """
        if len(self._history) < 2:
            return []  # لا شمعة i-2 بعد — أول شمعتين بلا كشف أصلًا
        atr = vol.atr if vol is not None else None
        if atr is None or atr <= 0.0:
            return []
        two_back = self._history[0]
        if candle.low > two_back.high:
            direction = FvgDirection.BULLISH
            gap_low, gap_high = two_back.high, candle.low
        elif candle.high < two_back.low:
            direction = FvgDirection.BEARISH
            gap_low, gap_high = candle.high, two_back.low
        else:
            return []
        gap = _TrackedGap(
            gap_id=self._gap_id(candle.bar_time, direction),
            origin_time=candle.bar_time,
            direction=direction,
            gap_low=gap_low,
            gap_high=gap_high,
            size_atr=(gap_high - gap_low) / atr,
            # بذرة أقصى التغلغل = الحافة القريبة (قيمة شمعة التكوين نفسها):
            # قاعها هو الحافة العليا للصاعدة وقمته الحافة الدنيا للهابطة.
            extreme=(candle.low if direction is FvgDirection.BULLISH else candle.high),
        )
        self._gaps.append(gap)
        payload = FvgEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=candle.bar_time,
            direction=direction,
            gap_low=gap_low,
            gap_high=gap_high,
            size_atr=gap.size_atr,
            state=FvgState.CREATED,
        )
        event_type = (
            EventType.FVG_BULLISH if direction is FvgDirection.BULLISH else EventType.FVG_BEARISH
        )
        return [EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)]

    def _track_fill(self, gap: _TrackedGap, candle: Candle) -> None:
        """تحديث الملء والحالة لفجوة قائمة بشمعة مغلقة — القواعد المرتبة.

        الترتيب حاسم وموثق: (1) الإبطال أولًا (الإغلاق وراء الحافة البعيدة
        يُقفز إلى النهائية مباشرة ويسترخص الملء الكامل المسجل بالشمعة نفسها)،
        (2) ثم الاجتياح الكامل ``FILLED``، (3) ثم التغلغل الجزئي
        ``MITIGATED``، (4) وإلا ``CREATED``. ``fill_fraction`` يُحدَّث قبل
        الحكم (قياس التداول) و``first_mitigation_time`` يسجل مرة واحدة.
        """
        width = gap.gap_high - gap.gap_low  # موجب دائمًا (كشف قطعي بالبناء)
        if gap.direction is FvgDirection.BULLISH:
            gap.extreme = min(gap.extreme, candle.low)
            penetrated = gap.gap_high - gap.extreme
            invalidated = candle.close < gap.gap_low
        else:
            gap.extreme = max(gap.extreme, candle.high)
            penetrated = gap.extreme - gap.gap_low
            invalidated = candle.close > gap.gap_high
        gap.fill_fraction = max(0.0, min(1.0, penetrated / width))
        if gap.fill_fraction > 0.0 and gap.first_mitigation_time is None:
            gap.first_mitigation_time = candle.bar_time
        if gap.state is FvgLifecycle.INVALIDATED:
            return  # نهائية بلا رجعة — القياس فوق يكفي والملء رتيب أصلًا
        if invalidated:
            gap.state = FvgLifecycle.INVALIDATED
        elif gap.fill_fraction >= 1.0:
            gap.state = FvgLifecycle.FILLED
        elif gap.fill_fraction > 0.0 and gap.state is FvgLifecycle.CREATED:
            gap.state = FvgLifecycle.MITIGATED
        # fill_fraction == 0.0 ⇒ الحالة قائمة كما هي (CREATED حصرًا بالعقد).

    def _gap_id(self, origin_time: datetime, direction: FvgDirection) -> str:
        """معرف حتمي قابل للإعادة — ``uuid5`` بمفتاح مركب موثق الصيغة.

        الصيغة الحرفية للمفتاح:
        ``f"{instrument_id}|{timeframe}|{origin_time.isoformat()}|{direction.value}"``
        — خالية من الأسعار عمدًا (ثبات الهوية تحت التحجيم السعري — روح
        D-07 وD-08)، وطابع شمعة التكوين فريد بحوارس الترتيب الصاعد الصارم
        وحدث واحد كأقصى في الشمعة (برهان الترويسة) فتفرد المفتاح مضمون.
        """
        identity = self._guards.instrument_id, self._guards.timeframe
        key = f"{identity[0]}|{identity[1]}|{origin_time.isoformat()}|{direction.value}"
        return str(uuid5(_FVG_NAMESPACE, key))

    def _required_instrument(self) -> str:
        """أداة المتعقّب — البث لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار المتعقّب — البث لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
