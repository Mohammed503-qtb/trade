"""متعقّب كتل الأوامر (Order Blocks) — §11.6 حرفيًا.

نص §11.6: «An Order Block is defined operationally as a bounded
pre-displacement consolidation/candle region that precedes a structurally
meaningful displacement and remains relevant after the move» — الترجمة
التشغيلية خط أنابيب خمسي عند كل إزاحة مؤكدة:

1. **إزاحة مؤكدة** (حدث DISPLACEMENT_UP/DOWN من كاشف §11.4 يصله هذا
   المتعقّب من المستدعي — لا يستورده أبدًا: كاشف فوق كاشف محظور بعقد
   استقلال الكاشفات).
2. **تتبع خلفي من الشمعة i-1** (i = شمعة الإزاحة): تُتخطى شموع الاندفاع
   (أجسام باتجاه الإزاحة نفسه) وصولًا إلى **الشمعة المعاكسة الأخيرة**
   (جسمها بعكس الاتجاه)؛ ثم تُمد العنقيد خلفيًا بالشموع المعاكسة
   المتتالية **المتراصة**: عضو جديد ينضم إذا كان انفصال مداه عن اتحاد
   مدى الأعضاء الحاليين ≤ ``threshold(EQUAL_LEVEL_TOLERANCE)`` — هذا
   التسامح هو التسامح التعريفي الموثق لـ«compact opposing cluster»
   (مفتاح §10.1/§11.6 في حالة التقلب — عتبة تطبيعية ``atr × multiplier``
   ككل المفاتيح). الديدجة (close == open) ليست معاكسة ولا اندفاعية —
   توقف التتبع. أقصى عمق التتبع ``trace_window`` شموع من شمعة الإزاحة.
3. **التحقق من النتيجة البنيوية** («verify the impulse generated
   meaningful structure change or liquidity interaction»): كسر بنية مؤكد
   (INTERNAL_BOS/EXTERNAL_BOS/CHOCH — الأنواع الثلاثة §11.2-3) باتجاه
   الإزاحة نفسه خلال نافذة ``consequence_window`` شموع من شمعة الإزاحة.
4. **تحديد المنطقة المصدرية**: ``[min(low), max(high)]`` للشمعة/العنقيد
   المعاكس (``origin_time`` = طابع أقدم عضو).
5. **تتبع الاختبارات وردود الأفعال** (أدناه).

**قرار البث المؤجل (الاختيار الموثق)**: خطوة 3 تُقيَّم **قبل** البث —
المرشحة تُبنى عند الإزاحة (خطوتا 2 و4) وتبقى معلقة بلا حدث، فإذا أكد
كسرٌ موافق ضمن النافذة **بُثّ ORDER_BLOCK_BULLISH/BEARISH عند شمعة
الكسر** (``event_time`` = شمعة التأكيد — لا-نظرة-مستقبلية صريحة)، وإلا
**دُرَت** المرشحة نهائيًا بلا بث أبدًا (لم يوجد حدث أصلًا — لا بثًا ثم
إبطالًا). نتيجتان مباشرتان موثقتان: ``structure_consequence`` في الحمولة
``BOS`` حصرًا عند البث (قيمة ``NONE_YET`` في المخطط للاستخدام اللاحق لا
تُبث بهذا المتعقّب)، و``LIQUIDITY_INTERACTION`` **غير موصولة في هذا
الطور** (كاشف السيولة مستقل بعقد import-linter — التحقق السيولي مسؤولية
طبقة الدمج فوق الكاشفين، والقيمة معلنة في المخطط لذلك الاستخدام).

**تسمية الاتجاه (موثقة بدقة)**: OB **صاعدة** = شموع معاكسة **هبطة** قبل
إزاحة صاعدة (UP→BULLISH)؛ و**هابطة** = شموع معاكسة **صاعدة** قبل إزاحة
هابطة (DOWN→BEARISH) — قطبية المنطقة تتبع قطبية الإزاحة المولِّدة
(أسماء §20 نفسها)، لا قطبية الشموع المعاكسة.

**تتبع الاختبارات (خطوة 5)**: من الشريط **التالي** للبث حصرًا — «حلقة
تفاعل» = أقصى سلسلة شموع متتالية يقطع مداها المنطقةَ
(‎low ≤ zone_high وhigh ≥ zone_low‎)؛ تبدأ حلقة جديدة بعد شريط غير قاطع؛
``retest_count`` = عدد الحلقات. جودة رد الفعل لكل شمعة اختبار:
``clamp01(tanh(رفض/atr))`` حيث الرفض = بُعد الإغلاق عن **الحافة البعيدة**
(الصاعدة: ``close − zone_low``؛ الهابطة: ``zone_high − close``) — الإغلاق
وراءها رفضٌ منفي يُقصّ إلى 0.0 لا رفضًا سالبًا، و``atr`` غائب ⇒ 0.0
معلنة (نمط قوة المتطرفات). آخر قيمة تُحفظ ``last_reaction_score``.

**الجودة (درجة داخلية تتبعية للمرحلة 7 — لا تُبث أبدًا)**: متوسط موزون
مقصوص إلى [0, 1]: ``tanh(atr_multiple / magnitude_saturation)`` (حجم
الإزاحة — ``atr_multiple`` من حمولتها)، ``1.0`` للنتيجة ``BOS`` (ثابتة
في هذا الطور بحكم البث المؤجل)، اضمحلال طزاجة
``0.5 ** (age / freshness_halflife)`` بعمرٍ بالشموع منذ البث (معامل زمني
لا سعري)، و``last_reaction_score`` (صفر معلن قبل أول اختبار — غياب
الدليل لا دليل). **التدفق/الحجم بُعدٌ غير متاح بعد** (محرك تدفق الطلبات
المرحلة 4 §12) — مستثنى بوزن صفر وموثق هنا عمدًا.

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_order_blocks.py):

- **لا-نظرة-مستقبلية (§26.3)**: التتبع الخلفي من سجل الشموع المنقضية
  حصرًا، والبث عند شمعة الكسر المؤكِدة لا قبلها، والأحداث المُغذاة
  تُقيَّم بشرط ``event_time == bar_time`` الشمعة الجارية (عقد التوصيل
  من الواجهة الجامعة).
- **الحتمية الصرفة**: نفس الشموع والأحداث ⇒ نفس المناطق والمعرفات
  بالتطابق التام — ``ob_id`` و``displacement_id`` مفاتيح ``uuid5``
  خالية من الأسعار (روح D-07).
- **العتبات التطبيعية (§16)**: التراص وحده عتبة سعرية وهي من
  ``vol.threshold(EQUAL_LEVEL_TOLERANCE)`` حصرًا؛ ``size_atr`` قسمة على
  ATR عند شمعة البث؛ بقية المقابض زمنية بالشموع أو نسب بلا وحدة.
- **الصخب في التحقق**: عقود :mod:`structure._guards` كاملة، وحدث بنوع
  غريب، أو طابع/هوية لا يطابقان شمعة الجارية، أو إزاحة مكررة المعرف —
  كلها ``ValueError`` صاخبة. **اتساق التغذية**: وقوع أي حدث إزاحة/كسر
  مع ``atr`` غائب أو منحل تناقضٌ صريح (بوابات الكاشفين المولِّدين
  توجب ATR عند صدورهما — §11.4 بوابة 4 و§11.2 عتبة الكسر) ⇒ رفض صاخب.

ترتيب المعالجة داخل الشمعة (حتمي موثق — جزء من عقد الحتمية): قبول
الشمعة وتحديث السجل ← معالجة أحداث الإزاحة (إنشاء المرشحات — قبل الكسور
حتى يحقق كسرُ الشمعة نفسها مرشحتَها) ← معالجة أحداث الكسر (تحقق المرشحات
المطابقة وبثّها) ← تتبع اختبارات المناطق الحية ← درد المرشحات المتقادمة.

«لا يُفسَّر Order Block أبدًا كدليل على أمر مؤسسي» (§11.6 حرفيًا) —
المنطقة فرضية موضعية تُقاس جودتها، لا معرفة بأوامر أحد.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, tanh
from uuid import NAMESPACE_URL, uuid5
from uuid import UUID as _UUID

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    BreakDirection,
    Candle,
    DisplacementEventPayload,
    EventType,
    FvgDirection,
    OrderBlockEventPayload,
    StructureBreakPayload,
    StructureConsequence,
)

from ._guards import StreamGuards
from .events import EmittedEvent

__all__ = [
    "OrderBlockConfig",
    "OrderBlockQualityWeights",
    "OrderBlockSnapshot",
    "OrderBlockTracker",
    "displacement_event_id",
]

#: مساحتا أسماء المعرفات — uuid5 فوق NAMESPACE_URL بمفاتيح نطاق معلنة
#: (نمط ترميز المتطرفات والفجوات نفسه — روح D-07).
_OB_NAMESPACE: _UUID = uuid5(NAMESPACE_URL, "ai-market-reasoning-engine/structure/order-block")
_DISPLACEMENT_NAMESPACE: _UUID = uuid5(
    NAMESPACE_URL, "ai-market-reasoning-engine/structure/displacement"
)

#: أنواع أحداث الكسر الثلاثة المؤكِّدة (§11.2-3) — كلها «structure change».
_BREAK_EVENT_TYPES = frozenset({EventType.INTERNAL_BOS, EventType.EXTERNAL_BOS, EventType.CHOCH})


# ═════════════════════════════ الإعداد ═════════════════════════════


def _check_nonnegative(name: str, value: float) -> None:
    """تحقق صاخب لعدد محدود غير سالب."""
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"قيمة {name} يجب أن تكون عددًا محدودًا غير سالب؛ وُجدت {value!r}")


@dataclass(frozen=True)
class OrderBlockQualityWeights:
    """أوزان مزج أبعاد جودة المنطقة الأربعة المتاحة — نسب بلا وحدة.

    نقاط انطلاق إعدادية للتقييم والمعايرة (دفتر التجارب/الاستئصال) — ليست
    توصيات تداول. المزج متوسط موزون يُطبَّع بمجموع الأوزان فالنتيجة في
    [0, 1] دائمًا. البعد الخامس (``volume/flow behavior`` §11.6) **غير
    متاح بعد** — محرك تدفق الطلبات المرحلة 4 (§12) — فلا وزن له هنا
    عمدًا؛ يضاف عند توفره بتحديث موثق.
    """

    #: وزن حجم الإزاحة (tanh(atr_multiple / magnitude_saturation)).
    magnitude: float = 0.35
    #: وزن النتيجة البنيوية (1.0 عند BOS — ثابتة في هذا الطور بالبث المؤجل).
    consequence: float = 0.20
    #: وزن الطزاجة (اضمحلال أُسي بعمر المنطقة بالشموع منذ البث).
    freshness: float = 0.25
    #: وزن جودة رد فعل الاختبار (آخر درجة — 0.0 معلنة قبل أول اختبار).
    retest: float = 0.20

    def __post_init__(self) -> None:
        names = ("magnitude", "consequence", "freshness", "retest")
        for name in names:
            _check_nonnegative(f"وزن {name}", float(getattr(self, name)))
        if sum(float(getattr(self, name)) for name in names) <= 0.0:
            raise ValueError("مجموع أوزان الجودة يجب أن يكون موجبًا — مزج بلا مقاييس لا معنى له")


#: الأوزان الافتراضية كثابت وحيد (نمط DEFAULT_MULTIPLIERS) — كائن مجمّد
#: يشارَك بسلامة بين الإعدادات.
_DEFAULT_QUALITY_WEIGHTS = OrderBlockQualityWeights()


@dataclass(frozen=True)
class OrderBlockConfig:
    """إعداد متعقّب كتل الأوامر — نقاط انطلاق إعدادية للتقييم والمعايرة
    (ليست توصيات تداول).

    المقابض الزمنية بالشموع لا السعرية (بوابة §16): التراص وحده عتبة
    تطبيعية من حالة التقلب (``EQUAL_LEVEL_TOLERANCE``) وليس من هنا.
    """

    #: أقصى عمق التتبع الخلفي بالشموع من شمعة الإزاحة (تخطي الاندفاع
    #: + العنقيد المعاكس) — تجاوزه بلا شمعة معاكسة ⇒ لا مرشح.
    trace_window: int = 10
    #: نافذة التحقق: يحقق المرشحةَ كسرٌ مؤكد في الشمعة j إذا
    #: ``0 ≤ j − i ≤ consequence_window`` (i = شمعة الإزاحة)؛ بعدها تُدرد.
    consequence_window: int = 5
    #: نصف عمر الطزاجة بالشموع من شمعة البث (96 شمعة ≈ يوم على إطار 15m).
    freshness_halflife: int = 96
    #: مرجع إشباع حجم الإزاحة (atr_multiple) في tanh — تُقارن عنده.
    magnitude_saturation: float = 2.0
    #: أوزان مزج الجودة — تُطبَّع بمجموعها عند الحساب.
    quality_weights: OrderBlockQualityWeights = _DEFAULT_QUALITY_WEIGHTS

    def __post_init__(self) -> None:
        if self.trace_window < 1:
            raise ValueError(f"trace_window يجب أن يكون ≥ 1؛ وُجد {self.trace_window}")
        if self.consequence_window < 0:
            raise ValueError(
                f"consequence_window يجب أن يكون ≥ 0 (صفر = الكسر بشمعة الإزاحة نفسها)؛ "
                f"وُجد {self.consequence_window}"
            )
        if self.freshness_halflife < 1:
            raise ValueError(f"freshness_halflife يجب أن يكون ≥ 1؛ وُجد {self.freshness_halflife}")
        if not isfinite(self.magnitude_saturation) or self.magnitude_saturation <= 0.0:
            raise ValueError(
                f"magnitude_saturation يجب أن يكون عددًا محدودًا موجبًا؛ "
                f"وُجد {self.magnitude_saturation!r}"
            )


# ═══════════════════════ اللقطات والسجلات الداخلية ═══════════════════════


@dataclass(frozen=True)
class OrderBlockSnapshot:
    """لقطة منطقة حية — حقول الحمولة مع أبعاد التتبع (خطوة 5 + الجودة).

    ``quality`` الدرجة الداخلية المركبة ([0, 1] — للمرحلة 7 لا للبث)،
    و``age_bars`` عمر المنطقة بالشموع منذ البث (معامل الطزاجة).
    """

    ob_id: str
    direction: FvgDirection
    zone_low: float
    zone_high: float
    origin_time: datetime
    displacement_id: str
    structure_consequence: StructureConsequence
    size_atr: float
    retest_count: int
    last_reaction_score: float
    quality: float
    emission_time: datetime
    age_bars: int


@dataclass
class _Candidate:
    """مرشحة معلقة تنتظر تحقق النتيجة البنيوية (خطوة 3 قبل البث)."""

    displacement_id: str
    direction: BreakDirection
    zone_low: float
    zone_high: float
    origin_time: datetime
    atr_multiple: float
    created_index: int  # عدّاد شمعة الإزاحة (ساعة المتعقّب)


@dataclass
class _LiveBlock:
    """منطقة حية بعد البث — يجري تتبع الاختبارات والجودة (خطوة 5)."""

    ob_id: str
    direction: BreakDirection
    zone_low: float
    zone_high: float
    origin_time: datetime
    displacement_id: str
    structure_consequence: StructureConsequence
    size_atr: float
    atr_multiple: float
    emission_index: int
    emission_time: datetime
    retest_count: int = 0
    last_reaction_score: float = 0.0
    in_zone: bool = False  # داخل حلقة تفاعل جارية؟


# ═══════════════════════ معرف الإزاحة الحتمي ═══════════════════════


def displacement_event_id(event: EmittedEvent) -> str:
    """معرف حتمي لحدث إزاحة مؤكد — ``uuid5`` بمفتاح خالٍ من الأسعار.

    حمولة الإزاحة (الأسس 3-a) بلا معرف — يُشتق هنا من هوية الحدث الكاملة
    بالصيغة الحرفية:
    ``uuid5(namespace, f"{instrument}|{timeframe}|{bar_time.isoformat()}|{direction.value}")``
    حيث ``bar_time`` شمعة الاندفاع المؤكِدة. الحتمية تجعل المفتاح قابلاً
    لإعادة الاشتقاق من أي مستهلك يحمل الحدث نفسه (الدمج 3-f يربط
    ``displacement_id`` في حمولة الكتلة بهذه الصيغة).

    :raises ValueError: الحدث ليس إزاحة (DISPLACEMENT_UP/DOWN).
    """
    payload = event.payload
    if not isinstance(payload, DisplacementEventPayload) or event.event_type not in (
        EventType.DISPLACEMENT_UP,
        EventType.DISPLACEMENT_DOWN,
    ):
        raise ValueError(
            f"displacement_event_id لحدث إزاحة حصرًا؛ وُجد {event.event_type.value!r} — "
            "معرف الإزاحة يُشتق من هوية حدث إزاحة لا غير"
        )
    key = (
        f"{payload.instrument}|{payload.timeframe}|"
        f"{payload.bar_time.isoformat()}|{payload.direction.value}"
    )
    return str(uuid5(_DISPLACEMENT_NAMESPACE, key))


# ═════════════════════════════ المتعقّب ═════════════════════════════


class OrderBlockTracker:
    """متعقّب كتل الأوامر الموضعي لكل (أداة، إطار) — شمع مغلقة فقط (§11.6).

    الاستخدام (التركيب في :class:`structure.engine.StructureEngine`): غذّه
    كل شمعة مغلقة مع حالة التقلب + أحداث الإزاحة والكسر المؤكدة **عند
    الشمعة نفسها** (توصيل الواجهة الجامعة)؛ البث مؤجل حتى تحقق النتيجة
    البنيوية (خطوة 3) فيقع عند شمعة الكسر حصرًا. انظر عقود الموديول.
    """

    def __init__(
        self,
        config: OrderBlockConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else OrderBlockConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        # سجل الشموع لأجل التتبع الخلفي: الشمعة الجارية + trace_window سابقة.
        self._history: deque[Candle] = deque(maxlen=self._config.trace_window + 1)
        self._bar_index = -1  # ساعة المتعقّب (عدّاد الشموع المقبولة)
        self._pending: list[_Candidate] = []
        self._live: list[_LiveBlock] = []
        self._seen_displacement_ids: set[str] = set()

    # ── الخصائص ──

    @property
    def config(self) -> OrderBlockConfig:
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

    def order_blocks(self) -> tuple[OrderBlockSnapshot, ...]:
        """لقطات المناطق الحية بترتيب البث — تُبنى طازجة من السجل الحي."""
        return tuple(self._snapshot(block) for block in self._live)

    # ── التغذية ──

    def update(
        self,
        candle: Candle,
        vol: VolatilityState | None,
        displacement_events: Sequence[EmittedEvent] = (),
        bos_events: Sequence[EmittedEvent] = (),
    ) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة وأحداثها المؤكدة — بثّ المناطق المتحققة عندها.

        الأحداث تُغذى **في شمعة تأكيدها حصرًا** (عقد التوصيل من الواجهة):
        ``event_time == candle.bar_time`` وهوية الحمولة تطابق هوية المتعقّب.
        خروج القائمة فارغًا أو أحداث بث بترتيب إنشاء المرشحات (الأقدم أولًا).
        """
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        self._bar_index += 1
        displacements = self._validate_events(
            candle, displacement_events, (EventType.DISPLACEMENT_UP, EventType.DISPLACEMENT_DOWN)
        )
        breaks = self._validate_events(candle, bos_events, _BREAK_EVENT_TYPES)
        # اتساق التغذية: أحداث هذا الشريط وجدت بفضل ATR عند مولديها — غيابه
        # هنا تناقض صريح يُرفض صاخبًا (عقود الموديول).
        if (displacements or breaks) and (vol is None or vol.atr is None or vol.atr <= 0.0):
            raise ValueError(
                "تغذية غير متسقة: أحداث إزاحة/كسر مع حالة تقلب بلا ATR صالحة — "
                "بوابات الكاشفين المولِّدين توجب ATR عند صدور الحدث (§11.4 بوابة 4، "
                "§11.2 عتبة الكسر)"
            )
        self._history.append(candle)
        # الترتيب الحتمي الموثق: الإزاحة (إنشاء المرشحات) قبل الكسر (تحقيقها)
        # حتى يحقق كسرُ الشمعة نفسها مرشحتَها.
        events: list[EmittedEvent] = []
        for event in displacements:
            events.extend(self._process_displacement(event, vol))
        for event in breaks:
            events.extend(self._process_break(event, vol))
        self._track_retests(candle, vol)
        self._expire_stale()
        return events

    # ── الداخلية: التحقق من الأحداث ──

    def _validate_events(
        self,
        candle: Candle,
        events: Sequence[EmittedEvent],
        expected: frozenset[EventType] | tuple[EventType, ...],
    ) -> list[EmittedEvent]:
        """فرض عقد التغذية: النوع والطابع والهوية — الرفض صاخب لا صامت.

        :raises ValueError: حدث بنوع خارج المسموح، أو ``event_time`` لا
            يطابق ``bar_time`` الشمعة الجارية، أو حمولة بهوية لا تطابق
            هوية المتعقّب، أو إزاحة مكررة المعرف.
        """
        validated: list[EmittedEvent] = []
        for event in events:
            if event.event_type not in expected:
                raise ValueError(
                    f"حدث بنوع غير متوقع في هذا الموضع: {event.event_type.value!r} — "
                    f"المسموح هنا {sorted(t.value for t in expected)}"
                )
            if event.event_time != candle.bar_time:
                raise ValueError(
                    f"حدث بطابع لا يطابق شمعة الجارية: {event.event_time} مقابل "
                    f"{candle.bar_time} — الأحداث تُغذى في شمعة تأكيدها حصرًا (§26.3)"
                )
            payload = event.payload
            if (
                payload.instrument != self._guards.instrument_id
                or payload.timeframe != self._guards.timeframe
            ):
                raise ValueError(
                    f"حمولة بهوية غريبة عن المتعقّب: ({payload.instrument!r}, "
                    f"{payload.timeframe!r}) مقابل "
                    f"({self._guards.instrument_id!r}, {self._guards.timeframe!r})"
                )
            if event.event_type in (EventType.DISPLACEMENT_UP, EventType.DISPLACEMENT_DOWN):
                assert isinstance(payload, DisplacementEventPayload)
                did = displacement_event_id(event)
                if did in self._seen_displacement_ids:
                    raise ValueError(f"إزاحة مكررة المعرف: {did} — التغذية لمرة واحدة")
                self._seen_displacement_ids.add(did)
            validated.append(event)
        return validated

    # ── الداخلية: خطوة 2 + 4 — التتبع الخلفي والمنطقة ──

    def _process_displacement(
        self, event: EmittedEvent, vol: VolatilityState | None
    ) -> list[EmittedEvent]:
        """إنشاء مرشحة من إزاحة مؤكدة — بلا بث (البث المؤجل خطوة 3)."""
        payload = event.payload
        assert isinstance(payload, DisplacementEventPayload)
        source = self._trace_source(payload.direction, vol)
        if source is None:
            return []
        zone_low, zone_high, origin_time = source
        self._pending.append(
            _Candidate(
                displacement_id=displacement_event_id(event),
                direction=payload.direction,
                zone_low=zone_low,
                zone_high=zone_high,
                origin_time=origin_time,
                atr_multiple=payload.atr_multiple,
                created_index=self._bar_index,
            )
        )
        return []

    def _trace_source(
        self, direction: BreakDirection, vol: VolatilityState | None
    ) -> tuple[float, float, datetime] | None:
        """التتبع الخلفي (خطوة 2): الشمعة/العنقيد المعاكس قبل الاندفاع.

        يعيد ``(zone_low, zone_high, origin_time)`` أو ``None`` (لا مصدر).
        أقصى عمق ``trace_window`` شمعة تُفحص من i-1 خلفيًا؛ التراص بعتبة
        ``EQUAL_LEVEL_TOLERANCE`` (انفصال مدا العضو الجديد عن اتحاد مدى
        الأعضاء الحاليين). الديدجة توقف التتبع (لا جسم معاكس فيها).
        """
        assert vol is not None and vol.atr is not None and vol.atr > 0.0  # عقود الاتساق
        tolerance = vol.threshold(ThresholdKey.EQUAL_LEVEL_TOLERANCE)
        assert tolerance is not None  # atr صالح ⇒ العتبة محسوبة (عقود الحالة)
        history = list(self._history)
        if len(history) < 2:
            return None  # لا سابق كافٍ للتتبع أصلًا
        examined = 0
        index = len(history) - 2  # الشمعة i-1 (الجارية عند -1)
        # ── تخطي شموع الاندفاع: أجسام باتجاه الإزاحة نفسه ──
        seed: Candle | None = None
        while index >= 0 and examined < self._config.trace_window:
            examined += 1
            current = history[index]
            if _body_direction(current) is direction:
                index -= 1
                continue
            seed = current
            break
        # ── البذرة: أول شمعة بلا جسم اندفاعي — معاكسة أو ديدجة ──
        if seed is None or _body_direction(seed) is None:
            return None  # لا معاكسة في النافذة، أو ديدجة (لا جسم معاكس فيها)
        members_low, members_high = seed.low, seed.high
        earliest_time = seed.bar_time
        index -= 1
        # ── مد العنقيد: شموع معاكسة متتالية متراصة ضمن التسامح ──
        while index >= 0 and examined < self._config.trace_window:
            examined += 1
            member = history[index]
            if _body_direction(member) is not _opposite(direction):
                break  # انتهى العنقيد (اندفاعية أو ديدجة)
            if _separation(member.low, member.high, members_low, members_high) > tolerance:
                break  # غير متراصة — خارج التسامح التعريفي
            members_low = min(members_low, member.low)
            members_high = max(members_high, member.high)
            earliest_time = member.bar_time
            index -= 1
        return members_low, members_high, earliest_time

    # ── الداخلية: خطوة 3 — التحقق والبث ──

    def _process_break(
        self, event: EmittedEvent, vol: VolatilityState | None
    ) -> list[EmittedEvent]:
        """تحقيق المرشحات المطابقة بكسر مؤكد — البث عند شمعة الكسر حصرًا.

        كسر باتجاه الإزاحة يحقق كل مرشحة مطابقة عمرها داخل النافذة
        (‎0 ≤ j − i ≤ consequence_window‎) — بترتيب الإنشاء (الأقدم أولًا).
        صلاحية ``atr`` مضمونة بعقد الاتساق في :meth:`update` (حدث الكسر
        وجد أصلًا بعتبة ATR عند مولده).
        """
        payload = event.payload
        assert isinstance(payload, StructureBreakPayload)
        atr = vol.atr if vol is not None else None
        assert atr is not None and atr > 0.0  # عقود الاتساق (حدث كسر وجد بعتبة ATR)
        events: list[EmittedEvent] = []
        remaining: list[_Candidate] = []
        for candidate in self._pending:
            age = self._bar_index - candidate.created_index
            if (
                candidate.direction is payload.break_direction
                and age <= self._config.consequence_window
            ):
                events.append(self._emit(candidate, event, atr))
            else:
                remaining.append(candidate)
        self._pending = remaining
        return events

    def _emit(self, candidate: _Candidate, break_event: EmittedEvent, atr: float) -> EmittedEvent:
        """بناء حدث البث والمنطقة الحية (خطوة 4 مكتملة عند شمعة الكسر)."""
        break_payload = break_event.payload
        assert isinstance(break_payload, StructureBreakPayload)
        candle_time = break_event.event_time
        is_bullish = candidate.direction is BreakDirection.UP
        direction = FvgDirection.BULLISH if is_bullish else FvgDirection.BEARISH
        ob_id = self._ob_id(candidate)
        payload = OrderBlockEventPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=candle_time,
            direction=direction,
            zone_low=candidate.zone_low,
            zone_high=candidate.zone_high,
            origin_time=candidate.origin_time,
            displacement_id=candidate.displacement_id,
            structure_consequence=StructureConsequence.BOS,
            size_atr=(candidate.zone_high - candidate.zone_low) / atr,
        )
        self._live.append(
            _LiveBlock(
                ob_id=ob_id,
                direction=candidate.direction,
                zone_low=candidate.zone_low,
                zone_high=candidate.zone_high,
                origin_time=candidate.origin_time,
                displacement_id=candidate.displacement_id,
                structure_consequence=StructureConsequence.BOS,
                size_atr=payload.size_atr,
                atr_multiple=candidate.atr_multiple,
                emission_index=self._bar_index,
                emission_time=candle_time,
            )
        )
        event_type = EventType.ORDER_BLOCK_BULLISH if is_bullish else EventType.ORDER_BLOCK_BEARISH
        return EmittedEvent(event_type=event_type, event_time=candle_time, payload=payload)

    # ── الداخلية: خطوة 5 — الاختبارات وردود الأفعال ──

    def _track_retests(self, candle: Candle, vol: VolatilityState | None) -> None:
        """تتبع حلقات التفاعل لكل منطقة حية — من الشريط التالي للبث.

        حلقة جديدة تبدأ بعد شريط غير قاطع للمنطقة (``in_zone`` قفل الحلقة)؛
        ودرجة رد الفعل تُحدَّث في كل شمعة قاطعة (آخر قيمة تحفظ).
        """
        for block in self._live:
            if block.emission_index >= self._bar_index:
                continue  # شمعة البث نفسها ليست اختبارًا (عقد الترويسة)
            intersects = candle.low <= block.zone_high and candle.high >= block.zone_low
            if not intersects:
                block.in_zone = False
                continue
            if not block.in_zone:
                block.retest_count += 1
                block.in_zone = True
            block.last_reaction_score = self._reaction_score(candle, vol, block)

    def _reaction_score(
        self, candle: Candle, vol: VolatilityState | None, block: _LiveBlock
    ) -> float:
        """جودة رد الفعل: ``clamp01(tanh(الرفض / atr))`` — الصيغة الموثقة.

        الرفض = بُعد الإغلاق عن الحافة البعيدة (وجه الإبطال): الصاعدة
        ``close − zone_low`` والهابطة ``zone_high − close`` — الرفض المنفي
        (إغلاق وراء الحافة) يُقصّ إلى 0.0، وATR غائب/منحل ⇒ 0.0 معلنة.
        """
        atr = vol.atr if vol is not None else None
        if atr is None or atr <= 0.0:
            return 0.0
        if block.direction is BreakDirection.UP:
            rejection = candle.close - block.zone_low
        else:
            rejection = block.zone_high - candle.close
        return _clamp01(tanh(rejection / atr))

    # ── الداخلية: الجودة واللقطات ──

    def _snapshot(self, block: _LiveBlock) -> OrderBlockSnapshot:
        """لقطة منطقة — الجودة تُحسب عند الطلب من العمر الجاري (حتمية)."""
        age = self._bar_index - block.emission_index
        weights = self._config.quality_weights
        total = weights.magnitude + weights.consequence + weights.freshness + weights.retest
        magnitude_score = tanh(block.atr_multiple / self._config.magnitude_saturation)
        consequence_score = 1.0 if block.structure_consequence is StructureConsequence.BOS else 0.0
        freshness_score = 0.5 ** (age / self._config.freshness_halflife)
        quality = (
            weights.magnitude * magnitude_score
            + weights.consequence * consequence_score
            + weights.freshness * freshness_score
            + weights.retest * block.last_reaction_score
        ) / total
        return OrderBlockSnapshot(
            ob_id=block.ob_id,
            direction=(
                FvgDirection.BULLISH
                if block.direction is BreakDirection.UP
                else FvgDirection.BEARISH
            ),
            zone_low=block.zone_low,
            zone_high=block.zone_high,
            origin_time=block.origin_time,
            displacement_id=block.displacement_id,
            structure_consequence=block.structure_consequence,
            size_atr=block.size_atr,
            retest_count=block.retest_count,
            last_reaction_score=block.last_reaction_score,
            quality=_clamp01(quality),
            emission_time=block.emission_time,
            age_bars=age,
        )

    def _expire_stale(self) -> None:
        """درد المرشحات التي تجاوزت نافذة التحقق بلا كسر موافق — بلا بث."""
        self._pending = [
            candidate
            for candidate in self._pending
            if self._bar_index - candidate.created_index <= self._config.consequence_window
        ]

    def _ob_id(self, candidate: _Candidate) -> str:
        """معرف حتمي للمنطقة — ``uuid5`` بمفتاح خالٍ من الأسعار.

        الصيغة الحرفية للمفتاح:
        ``f"{instrument_id}|{timeframe}|{origin_time.isoformat()}|{displacement_id}"``
        — إزاحة واحدة تولد مرشحة واحدة كأقصى (تكرار الإزاحة مرفوض صاخبًا)
        فالمفتاح فريد، وخالٍ من الأسعار فيثبت تحت التحجيم السعري (روح D-07).
        """
        identity = self._guards.instrument_id, self._guards.timeframe
        key = (
            f"{identity[0]}|{identity[1]}|"
            f"{candidate.origin_time.isoformat()}|{candidate.displacement_id}"
        )
        return str(uuid5(_OB_NAMESPACE, key))

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


# ═══════════════════════ مساعدات هندسية صرفة ═══════════════════════


def _body_direction(candle: Candle) -> BreakDirection | None:
    """اتجاه جسم الشمعة — ``None`` للديدجة (close == open)."""
    if candle.close > candle.open:
        return BreakDirection.UP
    if candle.close < candle.open:
        return BreakDirection.DOWN
    return None


def _opposite(direction: BreakDirection) -> BreakDirection:
    """القطبية المعاكسة."""
    return BreakDirection.DOWN if direction is BreakDirection.UP else BreakDirection.UP


def _separation(low_a: float, high_a: float, low_b: float, high_b: float) -> float:
    """انفصال مدى عن مدى: ``max(0, max(الأدنيين) − min(الأعلى))``.

    صفر عند التقاطع أو التلاصق — مقياس المسافة بين المدىين لا بين النقاط.
    """
    return max(0.0, max(low_a, low_b) - min(high_a, high_b))


def _clamp01(value: float) -> float:
    """حصر صريح في [0, 1] — خطأ الفاصلة العائمة لا يخرق عقد الدرجات."""
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)
