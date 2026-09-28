"""خريطة السيولة — المصادر ودورة الحياة وقوة المنطقة (§10.1-§10.3).

المصدر: §10.1 (مصادر السيولة)، §10.2 (كائن المنطقة)، §10.3 (قوة المنطقة)،
§31.3 (جدول liquidity_zones ودورة الحياة)، §11.1 (Swing كقيم مؤكدة تصل من
المستدعي)، §9.4 + قرار A-03 (الجلسة = حدود يوم UTC)، §10.5 (الخريطة
يستهلكها بناة الأهداف).

الخريطة «تمثل مواضع لها أسباب بنيوية لأن يواجه السعر فيها اهتمامًا معاكسًا
أو نشاط وقف؛ إنها خريطة مستنتَجة لا معرفة مباشرة بأوامر كل مشارك» (§10 تمهيد).

العقود الموثقة في هذه الوحدة (تُختبر حرفيًا في tests/unit/test_liquidity_zones.py):

- **الحتمية الصرفة**: نفس الشموع والمتطرفات بالترتيب نفسه ⇒ نفس الخريطة
  بالتطابق التام — معرفات ``zone_id`` مفاتيح uuid5 حتمية (روح D-07)، وترتيب
  المعالجة داخل الشمعة معلن أدناه، ولا عشوائية ولا ساعة ولا حالة خفية.
  اللقطات المعادة ``schemas.LiquidityZone`` مجمّدة تُبنى طازجة من السجل الحي؛
  المحرك يحتفظ بالنسخ الحية ويوزع لقطات لا يوزع مخزنه.

- **لا-نظرة-مستقبلية (§26.3)**: مناطق الشمعة t تُشتق من معطيات [0..t] حصرًا:
  المتطرفات تصل كقيم ``schemas.Swing`` مؤكدة من المستدعي (التوصيل
  structure→liquidity مسؤولية المستدعي — عقد استقلال الكاشفات يمنع استيراد
  كاشف آخر)، والكاشف المرتبط (SweepDetector) يقيّم الشمعة t ضد خريطة
  [0..t−1] قبل تحديثها بالشمعة t نفسها — فلا تُجتاح منطقةٌ بشمعة تأسيسها.

- **العتبات التطبيعية (§16)**: كل مسافة سعرية هنا عتبة ``atr × multiplier``
  من :class:`~market_state.volatility.VolatilityState` وحدها (تسامح
  المتساويات ``EQUAL_LEVEL_TOLERANCE`` ومسافة الصلة ``ZONE_PROXIMITY``) —
  لا ثابت سعري مطلق في أي مسار. بقية المقابض زمنية بالشموع
  (``freshness_halflife``) أو نسب بلا وحدة (الأوزان) — موثقة في مواضعها،
  ولا يوجد بينها ثابت سعري.

- **الصخب في التحقق**: الشمعة المتطورة (is_closed=False)، وخلط
  الأدوات/الأطر، والترتيب غير الصاعد الصارم (تكرار أو تأخر)، والمتطرف من
  إطار زمني آخر — كلها ``ValueError`` صاخبة، لا تصحيح صامت.

- **«الدرجة ليست احتمالًا» (§10.3 حرفيًا)**: ``reaction_score`` و
  ``unmitigated_score`` و``importance_score`` درجات قوة خام لفرضيات مواضع
  سيولة — ليست نسب فوز ولا توصيات تداول؛ الأوزان نقاط انطلاق إعدادية
  للتقييم والمعايرة.

**«obvious repeated highs/lows» و«untested external liquidity» خصيصتان
يُقاسان لا نوعا مصدر** (قرار 3-a الموثق في schemas): التكرار عبر
``test_count`` والطزاجة عبر الحالة — لذلك الأنواع الستة في
:class:`~schemas.liquidity.LiquiditySourceType` تغطي قوائم §10.1 كاملة.

معالجة الشمعة (ترتيب معلن — جزء من عقد الحتمية عند تعدد المصادر):

1. انقلاب اليوم UTC (مناطق PREV_DAY_EXTREME + إحالة مناطق جلسة الأمس)
   ثم انقلاب الأسبوع ISO (مناطق PREV_WEEK_EXTREME)؛
2. تتبع قصوى اليوم الجاري وتحديث مناطق الجلسة الحية (SESSION_EXTREME)؛
3. المتطرفات الجديدة: مناطق PRIOR_SWING ثم دمج EQUAL_LEVEL ثم تحديث
   حدود RANGE_BOUNDARY؛
4. إخراج لقطات المناطق متغيرة المادة هذا الشريط.

العمر ``age`` ساعة مشتقة (شموع منذ الأصل على ساعة المحرك) تُحدَّث في كل
لقطة بغضّ النظر عن قائمة «المتغير» — قائمة الإرجاع تخص المادة (إنشاء/
اختبار/تغلغل/رد فعل/حالة/نطاق) لا تقدم الساعة.

**تعريف الاختبار (§10.2 test_count)**: اختبار = تقاطع مدى الشمعة المتداول
``[low, high]`` مع فاصل المنطقة ``[price_low, price_high]`` (حواف مغلقة) —
يُحصى مرة لكل حلقة تفاعل (يبدؤها الكاشف المرتبط) لا لكل شمعة ملامسة.

جدول الانتقالات (دورة الحياة §31.3 — أحادية الاتجاه لا رجعة فيها):

- ACTIVE → SWEPT: الكاشف المرتبط أكمل CONFIRMED_SWEEP (استرجاع ضمن
  النافذة بعد بلوغ عتبة التغلغل §10.4) — يبث LIQUIDITY_SWEEP_* (§20).
- ACTIVE → CONSUMED: الكاشف أكمل BREAK_AND_ACCEPT (إغلاقات قبول كافية
  وراء الحافة البعيدة) — يبث BREAK_AND_ACCEPT_* (§20).
- ACTIVE → INVALIDATED: (أ) عبور قافز حاسم بلا لمس (إغلاق وراء الحافة
  البعيدة بهامش STRUCTURAL_LEVEL_BUFFER)، (ب) إحلال دمج المتساويات،
  (ج) إحالة انقلاب الجلسة (تخلفها PREV_DAY_EXTREME)، (د) إحلاء حد النطاق
  بحد خارجي أحدث.
- SWEPT/CONSUMED/INVALIDATED نهائية: لا انتقال منها أبدًا.

صيغ مفاتيح ``zone_id`` — uuid5 بنطاق ``engine.liquidity.zone.v1``، بلا أسعار
فيها (ثبات الهوية تحت التحجيم السعري؛ إعادة تسليم المتطرف نفسه تُلتقط
بالمفتاح الحتمي فلا ازدواج):

- PRIOR_SWING: ``{instrument}|{timeframe}|PRIOR_SWING|{swing_id}``
- EQUAL_LEVEL: ``{instrument}|{timeframe}|EQUAL_LEVEL|{side}|{الأعضاء مرتبين}``
- SESSION_EXTREME: ``{instrument}|{timeframe}|SESSION_EXTREME|{side}|{اليوم}|g{الجيل}``
- PREV_DAY_EXTREME: ``{instrument}|{timeframe}|PREV_DAY_EXTREME|{side}|{اليوم}``
- PREV_WEEK_EXTREME: ``{instrument}|{timeframe}|PREV_WEEK_EXTREME|{side}|{سنة ISO}-W{أسبوع ISO}``
- RANGE_BOUNDARY: ``{instrument}|{timeframe}|RANGE_BOUNDARY|{side}|{swing_id الحاكم}``
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isfinite, tanh
from types import MappingProxyType
from uuid import NAMESPACE_URL, uuid5

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    Candle,
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    SweepClassification,
    Swing,
    SwingDirection,
    SwingScope,
    ZoneState,
)

__all__ = [
    "ImportanceWeights",
    "LiquidityMapEngine",
    "ZoneBand",
    "ZoneConfig",
]

#: نطاق أسماء ثابت لمفاتيح uuid5 — هوية حتمية قابلة لإعادة الإنتاج (روح D-07).
_ZONE_NAMESPACE = uuid5(NAMESPACE_URL, "engine.liquidity.zone.v1")

#: حرس استدلال الأنواع لفرع التأسيس بلا وقت مستوى — غير مستدعى فعليًا
#: (كل مسارات التأسيس تمرر وقت المستوى المقتفى دومًا).
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

#: أصناف المصادر المشتقة من المتطرفات — قيمتها البنيوية تُحسب من المتطرف
#: (النطاق × القوة) لا من جدول المصادر.
_SWING_SOURCES = frozenset({LiquiditySourceType.PRIOR_SWING, LiquiditySourceType.EQUAL_LEVEL})


def _clamp01(value: float) -> float:
    """حصر صريح في [0, 1] — خطأ الفاصلة العائمة لا يخرق عقد الدرجات."""
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


# ═════════════════════════════ الإعداد ═════════════════════════════


def _check_unit(name: str, value: float) -> None:
    """تحقق صاخب لنطاق [0, 1]."""
    if not isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"قيمة {name} يجب أن تكون عددًا محدودًا في [0, 1]؛ وُجدت {value!r}")


def _check_positive_unit(name: str, value: float) -> None:
    """تحقق صاخب لنطاق (0, 1]."""
    _check_positive(name, value)
    _check_unit(name, value)


def _check_positive(name: str, value: float) -> None:
    """تحقق صاخب لقيمة محدودة موجبة."""
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"قيمة {name} يجب أن تكون عددًا محدودًا موجبًا؛ وُجدت {value!r}")


@dataclass(frozen=True)
class ImportanceWeights:
    """أوزان مزج مدخلات قوة المنطقة السبعة (§10.3) — نسب بلا وحدة.

    نقاط انطلاق إعدادية للتقييم والمعايرة (دفتر التجارب/الاستئصال) — ليست
    توصيات تداول. المزج متوسط موزون يُطبَّع بمجموع الأوزان فالنتيجة في
    [0, 1] دائمًا، ولا ثابت سعري هنا إطلاقًا (بوابة §16).
    """

    #: وزن الأهمية البنيوية (نطاق المتطرف × قوته — أو قيمة المصدر).
    structural: float = 0.30
    #: وزن عدد المستويات المتساوية/المتراصة (§10.3 «number and spacing»).
    equal_levels: float = 0.15
    #: وزن الطزاجة (اضمحلال أُسي بعمر المنطقة بالشموع).
    freshness: float = 0.20
    #: وزن دلالة الإطار الزمني (وزن يعلنه المستدعي لكل إطار).
    timeframe: float = 0.10
    #: وزن القرب من السعر (إشباع مسافة ZONE_PROXIMITY).
    distance: float = 0.15
    #: وزن جودة رد الفعل السابق.
    reaction: float = 0.10

    def __post_init__(self) -> None:
        names = (
            "structural",
            "equal_levels",
            "freshness",
            "timeframe",
            "distance",
            "reaction",
        )
        for name in names:
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"وزن {name} يجب أن يكون عددًا محدودًا غير سالب؛ وُجد {value!r}")
        if sum(float(getattr(self, name)) for name in names) <= 0.0:
            raise ValueError("مجموع أوزان الأهمية يجب أن يكون موجبًا — مزج بلا مقاييس لا معنى له")


#: الأوزان الافتراضية كثابت وحيد (نمط DEFAULT_MULTIPLIERS) — كائن مجمّد يشارك
#: بسلامة بين الإعدادات.
_DEFAULT_IMPORTANCE_WEIGHTS = ImportanceWeights()

#: القيم البنيوية الافتراضية للمصادر غير المشتقة من المتطرفات — نقاط انطلاق
#: إعدادية معلنة؛ مدخلا PRIOR_SWING/EQUAL_LEVEL غير مستخدمين لأن قيمتهما
#: تُحسبان من المتطرف (النطاق × القوة).
_DEFAULT_SOURCE_STRUCTURAL: Mapping[LiquiditySourceType, float] = MappingProxyType(
    {
        LiquiditySourceType.PRIOR_SWING: 0.0,
        LiquiditySourceType.EQUAL_LEVEL: 0.0,
        LiquiditySourceType.SESSION_EXTREME: 0.6,
        LiquiditySourceType.PREV_DAY_EXTREME: 0.8,
        LiquiditySourceType.PREV_WEEK_EXTREME: 0.9,
        LiquiditySourceType.RANGE_BOUNDARY: 0.9,
    }
)


@dataclass(frozen=True)
class ZoneConfig:
    """إعداد خريطة السيولة — مقابض زمنية/نسبية لا سعرية إطلاقًا.

    ``freshness_halflife`` **معامل زمني بالشموع لا ثابت سعري**: عمر المنطقة
    يقاس بالشموع المنقضية منذ أصلها (ساعة المحرك)؛ نصف عمر 96 شمعة = يوم
    تقريبي على إطار 15 دقيقة — نقطة انطلاق إعدادية للمعايرة، لا توصية.
    ``timeframe_weight`` دلالة الإطار كما يعلنها المستدعي (1.0 = إطار مرجعي
    كامل الدلالة) — إبقاؤها بسيطة عمدًا في هذا الطور.
    """

    #: نصف عمر الطزاجة بالشموع — مضاعفة العمر تقسم مساهمة الطزاجة إلى النصف.
    freshness_halflife: int = 96
    #: دلالة الإطار الزمني المعلنة من المستدعي ∈ (0, 1].
    timeframe_weight: float = 1.0
    #: عدد المستويات المتساوية الذي يشبع مساهمة العنقود (3+ مستويات مشبعة).
    equal_count_saturation: int = 3
    #: قاعدة الأهمية البنيوية للمتطرف الخارجي ∈ (0, 1].
    structural_external: float = 1.0
    #: قاعدة الأهمية البنيوية للمتطرف الداخلي ∈ (0, 1].
    structural_internal: float = 0.5
    #: أوزان مزج الأهمية — تُطبَّع بمجموعها عند الحساب.
    importance_weights: ImportanceWeights = _DEFAULT_IMPORTANCE_WEIGHTS
    #: قيم بنيوية للمصادر غير المشتقة من المتطرفات — تُدمج فوق الافتراضيات.
    source_structural: Mapping[LiquiditySourceType, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.freshness_halflife < 1:
            raise ValueError(f"freshness_halflife يجب أن يكون ≥ 1؛ وُجد {self.freshness_halflife}")
        _check_positive_unit("timeframe_weight", self.timeframe_weight)
        if self.equal_count_saturation < 1:
            raise ValueError(
                f"equal_count_saturation يجب أن يكون ≥ 1؛ وُجد {self.equal_count_saturation}"
            )
        _check_positive_unit("structural_external", self.structural_external)
        _check_positive_unit("structural_internal", self.structural_internal)
        merged: dict[LiquiditySourceType, float] = {
            **_DEFAULT_SOURCE_STRUCTURAL,
            **dict(self.source_structural),
        }
        for key, value in merged.items():
            _check_unit(f"source_structural[{key.value}]", value)
        # تجميد نهائي: الافتراضيات معدلة بالدمج والخريطة للقراءة فقط.
        object.__setattr__(self, "source_structural", MappingProxyType(merged))


# ═════════════════ لقطات الكاشف المرتبط ═════════════════


@dataclass(frozen=True)
class ZoneBand:
    """لقطة نطاق منطقة حية — الواجهة القرائية للكاشف المرتبط (SweepDetector).

    المناطق المعادة كلها ACTIVE (فقط ما يصح تفاعله)، بترتيب إنشائها في
    الخريطة. الكاشف يلتقط النطاق لحظة بدء التفاعل فيقيس التسلسل عليه لا
    على تحريك الخريطة اللاحق — عقد موثق في :mod:`liquidity.sweep`.
    """

    zone_id: str
    instrument: str
    timeframe: str
    side: LiquiditySide
    price_low: float
    price_high: float


# ═══════════════════════ سجل المنطقة الحي ═══════════════════════


@dataclass
class _ZoneRecord:
    """النسخة الحية للمنطقة داخل المحرك — اللقطات الموزعة مجمّدة منها.

    ``structural`` مركّبة الأهمية البنيوية [0, 1] تُحسب مرة عند الإنشاء (من
    المتطرف/المصدر) ولا تتبدل بعدها؛ بقية الحقول يطفّرها الكاشف المرتبط أو
    تتبع الجلسات. ``dirty`` راية «متغيرة المادة هذا الشريط». الدرجات الثلاث
    مشتقة عند اللقطة (دوال صرفة للسجل) لا مخزونة.
    """

    zone_id: str
    instrument: str
    timeframe: str
    side: LiquiditySide
    price_low: float
    price_high: float
    origin_time: datetime
    origin_bar: int
    source_type: LiquiditySourceType
    structural: float
    state: ZoneState = ZoneState.ACTIVE
    test_count: int = 0
    last_test_time: datetime | None = None
    sweep_status: SweepClassification = SweepClassification.UNKNOWN
    #: عمق أقصى رفض معياري بالـATR من آخر حسم رافض — tanh(هذه) عند اللقطة.
    reaction_depth_atr: float = 0.0
    #: أقصى تغلغل سعري مرصود (BUY: أعلى قمة / SELL: أدنى قاع) — None بلا لمس.
    penetration_extreme: float | None = None
    #: عدد أعضاء العنقود المتساوي (1 لغير العناقيد).
    equal_count: int = 1
    member_swing_ids: tuple[str, ...] = ()
    member_strengths: tuple[float, ...] = ()
    member_external: tuple[bool, ...] = ()
    dirty: bool = True


# ═══════════════════════ محرك الخريطة ═══════════════════════


class LiquidityMapEngine:
    """خريطة السيولة الموضعية لكل (أداة، إطار) — §10.1-§10.3.

    الاستخدام: أنشئ محركًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)،
    وغذّه شمعة مغلقة + حالة تقلب + متطرفات هذا الشريط المؤكدة (كقيم
    ``schemas.Swing`` من المستدعي) بترتيب زمني صاعد صارم.

    :raises ValueError: شمعة متطورة، أو خلط أداة/إطار، أو ``bar_time`` غير
        صاعد صعودًا صارمًا (تكرارًا أو تأخرًا)، أو متطرف من إطار آخر — كلها
        أخطاء قانونية صاخبة (لا تصحيح صامت).
    """

    def __init__(
        self,
        config: ZoneConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else ZoneConfig()
        self._identity: tuple[str, str] | None = (
            (instrument_id, timeframe)
            if instrument_id is not None and timeframe is not None
            else None
        )
        self._records: dict[str, _ZoneRecord] = {}
        self._bars = 0
        self._last_bar_time: datetime | None = None
        self._last_close: float | None = None
        self._last_vol: VolatilityState | None = None
        # تتبع الجلسة (يوم UTC) والأسبوع ISO.
        self._day: date | None = None
        self._week: tuple[int, int] | None = None
        self._day_high: float | None = None
        self._day_high_time: datetime | None = None
        self._day_high_bar: int = 0
        self._day_low: float | None = None
        self._day_low_time: datetime | None = None
        self._day_low_bar: int = 0
        self._week_high: float | None = None
        self._week_high_time: datetime | None = None
        self._week_low: float | None = None
        self._week_low_time: datetime | None = None
        self._session_live: dict[LiquiditySide, str | None] = {
            LiquiditySide.BUY_SIDE: None,
            LiquiditySide.SELL_SIDE: None,
        }
        self._session_generation: dict[tuple[LiquiditySide, date], int] = {}
        self._boundary_live: dict[LiquiditySide, str | None] = {
            LiquiditySide.BUY_SIDE: None,
            LiquiditySide.SELL_SIDE: None,
        }

    # ── الخصائص ──

    @property
    def config(self) -> ZoneConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._identity[0] if self._identity is not None else None

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._identity[1] if self._identity is not None else None

    @property
    def bars_consumed(self) -> int:
        """عدد الشموع المقبولة — ساعة المحرك التي يُقاس عليها العمر."""
        return self._bars

    # ── التغذية ──

    def validate_bar(self, candle: Candle) -> None:
        """تحقق القبول (مغلقة + هوية + ترتيب صاعد صارم) — قبل أي طفرة.

        عمومية مقصودة: تستدعيها :meth:`update` داخليًا، وتستدعيها الواجهة
        (:class:`~liquidity.engine.LiquidityEngine`) قبل تشغيل الكاشف المرتبط
        كي لا يطفّر الكاشف سجلًا قبل رفض شمعة فاسدة.
        """
        if not candle.is_closed:
            raise ValueError(
                "خريطة السيولة تستهلك الشموع المغلقة فقط (§27/§33.2) — "
                "فصل المتطور عن المؤكد مسؤولية الابتلاع عبر is_closed"
            )
        self._ensure_identity(candle)
        if self._last_bar_time is not None and candle.bar_time <= self._last_bar_time:
            raise ValueError(
                f"ترتيب غير صاعد صراحةً: bar_time الواردة {candle.bar_time} ≤ آخر مقبولة "
                f"{self._last_bar_time} — التكرار والتأخر كلاهما مرفوض رفضًا صاخبًا على "
                "خريطة السيولة (لا تجاهل محسوب)"
            )

    def update(
        self,
        candle: Candle,
        vol: VolatilityState | None,
        new_swings: Sequence[Swing] = (),
    ) -> list[LiquidityZone]:
        """استهلاك شمعة مغلقة وإرجاع لقطات المناطق متغيرة المادة هذا الشريط.

        «متغيرة المادة» = إنشاء أو اختبار أو تغلغل أو رد فعل أو حالة أو
        تحريك نطاق — أما العمر ``age`` فساعة مشتقة تتقدم في كل لقطة ولا
        يدخل تعريف التغير (موثق في رأس الوحدة). ترتيب المعالجة الداخلي
        معلن في رأس الوحدة وهو جزء من عقد الحتمية.
        """
        self.validate_bar(candle)
        self._bars += 1
        self._last_bar_time = candle.bar_time
        self._last_close = candle.close
        self._last_vol = vol
        self._rollovers(candle)
        self._track_session_extremes(candle)
        self._ingest_swings(candle, vol, new_swings)
        changed = [self._snapshot(record) for record in self._records.values() if record.dirty]
        for record in self._records.values():
            record.dirty = False
        return changed

    # ── القراءة ──

    def zones(self) -> list[LiquidityZone]:
        """كل لقطات الخريطة الحالية بترتيب الإنشاء (ترتيب إدراج السجل)."""
        return [self._snapshot(record) for record in self._records.values()]

    def zone(self, zone_id: str) -> LiquidityZone | None:
        """لقطة منطقة بمعرفها — None إذا لم توجد."""
        record = self._records.get(zone_id)
        return None if record is None else self._snapshot(record)

    def sweep_status(self, zone_id: str) -> SweepClassification | None:
        """آخر تصنيف اجتياح لمنطقة — None إذا لم توجد."""
        record = self._records.get(zone_id)
        return None if record is None else record.sweep_status

    # ── واجهة الكاشف المرتبط (SweepDetector) — توثيق التغيير ──

    def live_bands(self) -> list[ZoneBand]:
        """نطاقات المناطق النشطة بترتيب الإنشاء — مدخل مسح الكاشف المرتبط.

        المناطق غير النشطة مستبعدة، فيكتشف الكاشف موت منطقة باختفائها من
        القائمة ويطوي تفاعلها المعلق فورًا.
        """
        return [
            ZoneBand(
                zone_id=record.zone_id,
                instrument=record.instrument,
                timeframe=record.timeframe,
                side=record.side,
                price_low=record.price_low,
                price_high=record.price_high,
            )
            for record in self._records.values()
            if record.state is ZoneState.ACTIVE
        ]

    def zone_test_count(self, zone_id: str) -> int:
        """عدّاد اختبارات المنطقة لحظة النداء — لقطة الحمولات (شرط 5 §10.4)."""
        return self._require(zone_id).test_count

    def record_test(self, zone_id: str, bar_time: datetime) -> None:
        """حصيلة اختبار (لمس بدء حلقة تفاعل): test_count+1 وlast_test_time."""
        record = self._require(zone_id)
        record.test_count += 1
        record.last_test_time = bar_time
        record.dirty = True

    def record_penetration(self, zone_id: str, extreme_price: float) -> None:
        """تتبع أقصى تغلغل سعري — يغذي كسر الامتلاء في unmitigated_score."""
        record = self._require(zone_id)
        if record.side is LiquiditySide.BUY_SIDE:
            record.penetration_extreme = (
                extreme_price
                if record.penetration_extreme is None
                else max(record.penetration_extreme, extreme_price)
            )
        else:
            record.penetration_extreme = (
                extreme_price
                if record.penetration_extreme is None
                else min(record.penetration_extreme, extreme_price)
            )
        record.dirty = True

    def record_reaction(self, zone_id: str, depth_atr: float) -> None:
        """تسجيل جودة آخر رفض: عمق معياري بالـATR (يستبدل السابق).

        الدرجة عند اللقطة ``reaction_score = tanh(max(0, depth_atr))`` — رفض
        أعمق ⇒ درجة أعلى، وtanh يحصرها في [0, 1) حصرًا رياضيًا.
        """
        record = self._require(zone_id)
        record.reaction_depth_atr = max(0.0, depth_atr)
        record.dirty = True

    def finalize_sweep(self, zone_id: str) -> None:
        """ACTIVE → SWEPT بتصنيف CONFIRMED_SWEEP — بعد بث LIQUIDITY_SWEEP_*."""
        record = self._require_active(zone_id)
        record.state = ZoneState.SWEPT
        record.sweep_status = SweepClassification.CONFIRMED_SWEEP
        record.dirty = True

    def finalize_accept(self, zone_id: str) -> None:
        """ACTIVE → CONSUMED بتصنيف BREAK_AND_ACCEPT — بعد بث BREAK_AND_ACCEPT_*."""
        record = self._require_active(zone_id)
        record.state = ZoneState.CONSUMED
        record.sweep_status = SweepClassification.BREAK_AND_ACCEPT
        record.dirty = True

    def set_sweep_status(self, zone_id: str, classification: SweepClassification) -> None:
        """تصنيف غير حاسم (FAILED/PARTIAL/UNKNOWN) — المنطقة تبقى ACTIVE.

        PARTIAL_SWEEP وUNKNOWN ليستا في قاموس §20 فلا تُبثان حدثًا أبدًا —
        تخزَّنان في ``sweep_status`` للمنطقة فقط (§10.4/§20).
        """
        record = self._require_active(zone_id)
        record.sweep_status = classification
        record.dirty = True

    def invalidate_traversed(self, zone_id: str) -> None:
        """ACTIVE → INVALIDATED — عبور قافز حاسم بلا لمس (جدول الانتقالات (أ))."""
        record = self._require_active(zone_id)
        record.state = ZoneState.INVALIDATED
        record.dirty = True

    # ── الداخلية: هوية وسجلات ──

    def _ensure_identity(self, candle: Candle) -> None:
        """فرض زوج (أداة، إطار) واحد للمحرك — الالتقاط من أول شمعة أو الرفض."""
        if self._identity is None:
            self._identity = (candle.instrument_id, candle.timeframe)
            return
        expected_instrument, expected_timeframe = self._identity
        if candle.instrument_id != expected_instrument:
            raise ValueError(
                f"خلط أدوات على محرك واحد: استُهل على {expected_instrument!r} "
                f"ووصلت شمعة {candle.instrument_id!r} — أنشئ محركًا لكل (أداة، إطار)"
            )
        if candle.timeframe != expected_timeframe:
            raise ValueError(
                f"خلط أطر على محرك واحد: استُهل على {expected_timeframe!r} "
                f"ووصلت شمعة {candle.timeframe!r} — أنشئ محركًا لكل (أداة، إطار)"
            )

    def _require(self, zone_id: str) -> _ZoneRecord:
        """جلب سجل حي — المنطقة المجهولة خطأ قانوني صاخب."""
        record = self._records.get(zone_id)
        if record is None:
            raise ValueError(f"منطقة مجهولة: {zone_id!r} — لا طفرة على معرف غائب")
        return record

    def _require_active(self, zone_id: str) -> _ZoneRecord:
        """جلب سجل نشط — الطفرة على حالة نهائية انتهاك دورة حياة مرفوض."""
        record = self._require(zone_id)
        if record.state is not ZoneState.ACTIVE:
            raise ValueError(
                f"طفرة على منطقة في حالة نهائية {record.state.value}: {zone_id!r} — "
                "دورة الحياة أحادية الاتجاه (§31.3)"
            )
        return record

    # ── الداخلية: الانقلابات (يوم UTC / أسبوع ISO) ──

    def _rollovers(self, candle: Candle) -> None:
        """انقلاب اليوم ثم الأسبوع قبل تتبع قصوى الشمعة الجارية.

        الأسبوع = أسبوع ISO (iso_year/iso_week، الاثنين→الأحد UTC) — قرار
        موثق (ISO لا «7 أيام من الاثنين» الاصطناعية). الانقلاب يقاس على آخر
        شمعة مرصودة: فجوات البيانات لا تولّد مناطق لأيام/أسابيع فارغة.
        """
        bar_utc = candle.bar_time.astimezone(UTC)
        day = bar_utc.date()
        iso = bar_utc.isocalendar()
        week = (int(iso[0]), int(iso[1]))
        if self._day is not None and day > self._day:
            self._on_day_rollover(candle)
        if self._week is not None and week > self._week:
            self._on_week_rollover(candle)
        self._day = day
        self._week = week

    def _on_day_rollover(self, candle: Candle) -> None:
        """اكتمال يوم UTC: مناطق PREV_DAY_EXTREME عند قصواه وإحالة جلسته.

        أصل المنطقة الجديدة شمعة القمة/القاع المكتملة (origin_time/origin_bar
        عندها) فالعمر يقاس من المتطرف نفسه. قيم ``assert`` أدناه يحسمها
        الاستدعاء (يوجد يوم جارٍ فتوجد قصواه).
        """
        assert (
            self._day is not None
            and self._day_high is not None
            and self._day_low is not None
            and self._day_high_time is not None
            and self._day_low_time is not None
        )
        instrument = candle.instrument_id
        timeframe = candle.timeframe
        day_label = self._day.isoformat()
        structural = self._config.source_structural[LiquiditySourceType.PREV_DAY_EXTREME]
        self._create_level_zone(
            source_type=LiquiditySourceType.PREV_DAY_EXTREME,
            key=f"{instrument}|{timeframe}|PREV_DAY_EXTREME"
            f"|{LiquiditySide.BUY_SIDE.value}|{day_label}",
            side=LiquiditySide.BUY_SIDE,
            level=self._day_high,
            level_time=self._day_high_time,
            level_bar=self._day_high_bar,
            instrument=instrument,
            timeframe=timeframe,
            structural=structural,
        )
        self._create_level_zone(
            source_type=LiquiditySourceType.PREV_DAY_EXTREME,
            key=f"{instrument}|{timeframe}|PREV_DAY_EXTREME"
            f"|{LiquiditySide.SELL_SIDE.value}|{day_label}",
            side=LiquiditySide.SELL_SIDE,
            level=self._day_low,
            level_time=self._day_low_time,
            level_bar=self._day_low_bar,
            instrument=instrument,
            timeframe=timeframe,
            structural=structural,
        )
        # إحالة مناطق جلسة الأمس: ACTIVE → INVALIDATED (جدول الانتقالات (ج)).
        for side in (LiquiditySide.BUY_SIDE, LiquiditySide.SELL_SIDE):
            live_id = self._session_live.get(side)
            if live_id is not None:
                record = self._records.get(live_id)
                if record is not None and record.state is ZoneState.ACTIVE:
                    record.state = ZoneState.INVALIDATED
                    record.dirty = True
            self._session_live[side] = None
        self._day_high = None
        self._day_high_time = None
        self._day_low = None
        self._day_low_time = None

    def _on_week_rollover(self, candle: Candle) -> None:
        """اكتمال أسبوع ISO: مناطق PREV_WEEK_EXTREME عند قصواه — بلا مناطق أسبوعية حية.

        التتبع الأسبوعي لأغراض الانقلاب وحده (لا مناطق جلسة أسبوعية حية) —
        الجلسة الحية يومية بقرار A-03. عمر منطقة الأسبوع يبدأ من شريط
        الانقلاب (لا نتابع فهرس شمعة القمة الأسبوعية — القصوى تتبع الوقت
        فقط؛ عقد موثق: origin_bar = شريط التأسيس).
        """
        assert (
            self._week is not None
            and self._week_high is not None
            and self._week_low is not None
            and self._week_high_time is not None
            and self._week_low_time is not None
        )
        instrument = candle.instrument_id
        timeframe = candle.timeframe
        week_label = f"{self._week[0]}-W{self._week[1]:02d}"
        structural = self._config.source_structural[LiquiditySourceType.PREV_WEEK_EXTREME]
        self._create_level_zone(
            source_type=LiquiditySourceType.PREV_WEEK_EXTREME,
            key=f"{instrument}|{timeframe}|PREV_WEEK_EXTREME"
            f"|{LiquiditySide.BUY_SIDE.value}|{week_label}",
            side=LiquiditySide.BUY_SIDE,
            level=self._week_high,
            level_time=self._week_high_time,
            level_bar=self._bars,
            instrument=instrument,
            timeframe=timeframe,
            structural=structural,
        )
        self._create_level_zone(
            source_type=LiquiditySourceType.PREV_WEEK_EXTREME,
            key=f"{instrument}|{timeframe}|PREV_WEEK_EXTREME"
            f"|{LiquiditySide.SELL_SIDE.value}|{week_label}",
            side=LiquiditySide.SELL_SIDE,
            level=self._week_low,
            level_time=self._week_low_time,
            level_bar=self._bars,
            instrument=instrument,
            timeframe=timeframe,
            structural=structural,
        )
        self._week_high = None
        self._week_high_time = None
        self._week_low = None
        self._week_low_time = None

    # ── الداخلية: مناطق الجلسة الحية ──

    def _track_session_extremes(self, candle: Candle) -> None:
        """تحديث قصوى اليوم الجاري ومناطق الجلسة الحية عند كل امتداد.

        منطقة قمة الجلسة مستوى صفر العرض يتحرك مع القمة الجارية؛ عمرها يُعاد
        تأسيسه مع كل امتداد (أصلها شمعة المستوى الحالي — المنطقة بمنطقها تتبع
        المستوى الجاري لا أول ظهور لليوم). موت المنطقة (اجتياح/استهلاك/إبطال)
        لا يُحييها: الامتداد التالي بعد الموت يؤسس **جيلًا جديدًا** بهوية
        جديدة، والخريطة تحتفظ بالأجيال الميتة للتاريخ (دورة أحادية الاتجاه
        §31.3).
        """
        if self._day_high is None or candle.high > self._day_high:
            self._day_high = candle.high
            self._day_high_time = candle.bar_time
            self._day_high_bar = self._bars
            self._update_session_zone(LiquiditySide.BUY_SIDE, candle)
        if self._day_low is None or candle.low < self._day_low:
            self._day_low = candle.low
            self._day_low_time = candle.bar_time
            self._day_low_bar = self._bars
            self._update_session_zone(LiquiditySide.SELL_SIDE, candle)
        # قصوى الأسبوع الجاري — للتتبع والانقلاب فقط (بلا مناطق حية).
        if self._week_high is None or candle.high > self._week_high:
            self._week_high = candle.high
            self._week_high_time = candle.bar_time
        if self._week_low is None or candle.low < self._week_low:
            self._week_low = candle.low
            self._week_low_time = candle.bar_time

    def _update_session_zone(self, side: LiquiditySide, candle: Candle) -> None:
        """تحديث منطقة جلسة أحد الجانبين عند امتداد قصاه الجاري."""
        assert self._day is not None
        if side is LiquiditySide.BUY_SIDE:
            level, level_time = self._day_high, self._day_high_time
        else:
            level, level_time = self._day_low, self._day_low_time
        assert level is not None and level_time is not None
        live_id = self._session_live.get(side)
        record = self._records.get(live_id) if live_id is not None else None
        if record is not None and record.state is ZoneState.ACTIVE:
            improved = (
                level > record.price_high
                if side is LiquiditySide.BUY_SIDE
                else level < record.price_low
            )
            if improved:
                record.price_low = level
                record.price_high = level
                record.origin_time = level_time
                record.origin_bar = self._bars
                record.dirty = True
            return
        # لا منطقة حية: تأسيس جيل جديد عند المستوى الجاري.
        generation = self._session_generation.get((side, self._day), 0)
        record = self._create_level_zone(
            source_type=LiquiditySourceType.SESSION_EXTREME,
            key=(
                f"{candle.instrument_id}|{candle.timeframe}|SESSION_EXTREME"
                f"|{side.value}|{self._day.isoformat()}|g{generation}"
            ),
            side=side,
            level=level,
            level_time=level_time,
            level_bar=self._bars,
            instrument=candle.instrument_id,
            timeframe=candle.timeframe,
            structural=self._config.source_structural[LiquiditySourceType.SESSION_EXTREME],
        )
        self._session_generation[(side, self._day)] = generation + 1
        self._session_live[side] = record.zone_id

    def _create_level_zone(
        self,
        *,
        source_type: LiquiditySourceType,
        key: str,
        side: LiquiditySide,
        level: float,
        level_time: datetime | None,
        level_bar: int,
        instrument: str,
        timeframe: str,
        structural: float,
    ) -> _ZoneRecord:
        """تأسيس منطقة مستوى صفرية العرض بمفتاح uuid5 حتمي — idempotent.

        المفتاح الحتمي يلتقط إعادة التأسيس فلا ازدواج أبدًا (تعاد السجلات
        القائمة كما هي). ``level_time=None`` فرع غير مستدعى فعليًا (القصوى
        تؤسس ومعها وقتها دومًا) — الافتراض الموثق أدناه حرس استدلال النوع.
        """
        zone_id = str(uuid5(_ZONE_NAMESPACE, key))
        existing = self._records.get(zone_id)
        if existing is not None:
            return existing
        record = _ZoneRecord(
            zone_id=zone_id,
            instrument=instrument,
            timeframe=timeframe,
            side=side,
            price_low=level,
            price_high=level,
            origin_time=level_time if level_time is not None else _EPOCH,
            origin_bar=level_bar,
            source_type=source_type,
            structural=_clamp01(structural),
        )
        self._records[zone_id] = record
        return record

    # ── الداخلية: المتطرفات ──

    def _ingest_swings(
        self,
        candle: Candle,
        vol: VolatilityState | None,
        swings: Sequence[Swing],
    ) -> None:
        """هضم متطرفات الشريط: مناطق PRIOR_SWING ثم دمج EQUAL_LEVEL ثم الحدود.

        التجميع يُقيَّم لحظة وصول المتطرف فقط (لا إعادة معالجة بأثر رجعي
        عند توفر ATR لاحقًا — عقد بلا-نظرة-مستقبلية يمنع إعادة تشكيل تاريخ
        الخريطة). معيار الانضمام: سعر المتطرف ضمن التسامح من حافتي نطاق
        العنقود/المستوى القائم — تجميع متسلسل يجعل العنقود يتسع، وعرض
        المنطقة الناتج يشترك لاحقًا في عتبة كشف الاجتياح (§10.4 شرط 3).
        ``vol = None`` (قبيل أول شمعة عند محرك التقلب الموازي) يُعامل كغياب
        ATR: هضم بلا دمج متساويات — نفس عقد حزمة البنية (‎``VolatilityState
        | None`` عند التغذية).
        """
        atr = vol.atr if vol is not None else None
        tolerance: float | None = None
        if atr is not None and atr > 0.0:
            assert vol is not None
            threshold = vol.threshold(ThresholdKey.EQUAL_LEVEL_TOLERANCE)
            tolerance = threshold if (threshold is not None and threshold > 0.0) else None
        for swing in swings:
            if swing.timeframe != candle.timeframe:
                raise ValueError(
                    f"متطرف من إطار آخر على خريطة واحدة: الخريطة على "
                    f"{candle.timeframe!r} ووصل متطرف {swing.swing_id!r} على "
                    f"{swing.timeframe!r} — Multi-timeframe يوصل عبر محركات منفصلة"
                )
            side = (
                LiquiditySide.BUY_SIDE
                if swing.direction is SwingDirection.HIGH
                else LiquiditySide.SELL_SIDE
            )
            self._ingest_swing(candle, swing, side, tolerance)
            if swing.external_or_internal is SwingScope.EXTERNAL:
                self._update_range_boundary(candle, swing, side)

    def _ingest_swing(
        self,
        candle: Candle,
        swing: Swing,
        side: LiquiditySide,
        tolerance: float | None,
    ) -> None:
        """منطقة متطرف واحد: PRIOR_SWING منفردة أو دمج عنقود EQUAL_LEVEL."""
        instrument = candle.instrument_id
        timeframe = candle.timeframe
        cfg = self._config
        scope_base = (
            cfg.structural_external
            if swing.external_or_internal is SwingScope.EXTERNAL
            else cfg.structural_internal
        )
        prior_id = str(
            uuid5(
                _ZONE_NAMESPACE,
                f"{instrument}|{timeframe}|PRIOR_SWING|{swing.swing_id}",
            )
        )
        if prior_id in self._records:
            # إعادة تسليم متطرف معروف — المفتاح الحتمي يلتقطها (idempotent).
            return
        matches: list[_ZoneRecord] = []
        if tolerance is not None:
            for record in self._records.values():
                if (
                    record.side is side
                    and record.state is ZoneState.ACTIVE
                    and record.source_type in _SWING_SOURCES
                    and swing.price >= record.price_low - tolerance
                    and swing.price <= record.price_high + tolerance
                ):
                    matches.append(record)
        if not matches:
            record = _ZoneRecord(
                zone_id=prior_id,
                instrument=instrument,
                timeframe=timeframe,
                side=side,
                price_low=swing.price,
                price_high=swing.price,
                origin_time=swing.bar_time,
                origin_bar=self._bars,
                source_type=LiquiditySourceType.PRIOR_SWING,
                structural=_clamp01(scope_base * swing.strength),
                member_swing_ids=(swing.swing_id,),
                member_strengths=(swing.strength,),
                member_external=(swing.external_or_internal is SwingScope.EXTERNAL,),
            )
            self._records[prior_id] = record
            return
        # دمج عنقود: المتطرف الجديد + كل العناقيد/المستويات المطابقة.
        member_ids = sorted(
            {
                swing.swing_id,
                *(mid for record in matches for mid in record.member_swing_ids),
            }
        )
        cluster_id = str(
            uuid5(
                _ZONE_NAMESPACE,
                f"{instrument}|{timeframe}|EQUAL_LEVEL|{side.value}|{','.join(member_ids)}",
            )
        )
        if cluster_id in self._records:
            # إعادة تسليم عضو لعنقود قائم قائمًا بالفعل بهذه العضوية — لا إحلال.
            return
        strengths: list[float] = [swing.strength]
        strengths.extend(s for record in matches for s in record.member_strengths)
        externals: list[bool] = [swing.external_or_internal is SwingScope.EXTERNAL]
        externals.extend(e for record in matches for e in record.member_external)
        cluster_base = cfg.structural_external if any(externals) else cfg.structural_internal
        cluster_strength = sum(strengths) / len(strengths)
        price_low = min(swing.price, *(record.price_low for record in matches))
        price_high = max(swing.price, *(record.price_high for record in matches))
        origin_time = min(swing.bar_time, *(record.origin_time for record in matches))
        origin_bar = min(self._bars, *(record.origin_bar for record in matches))
        # إحلال الأعضاء: ACTIVE → INVALIDATED (جدول الانتقالات (ب)).
        for record in matches:
            record.state = ZoneState.INVALIDATED
            record.dirty = True
        cluster = _ZoneRecord(
            zone_id=cluster_id,
            instrument=instrument,
            timeframe=timeframe,
            side=side,
            price_low=price_low,
            price_high=price_high,
            origin_time=origin_time,
            origin_bar=origin_bar,
            source_type=LiquiditySourceType.EQUAL_LEVEL,
            structural=_clamp01(cluster_base * cluster_strength),
            equal_count=len(member_ids),
            member_swing_ids=tuple(member_ids),
            member_strengths=tuple(strengths),
            member_external=tuple(externals),
        )
        self._records[cluster_id] = cluster

    def _update_range_boundary(self, candle: Candle, swing: Swing, side: LiquiditySide) -> None:
        """تحديث حد نطاق المعالجة من المتطرفات الخارجية (§10.1/§11.7).

        الحد كائن حي واحد لكل جانب عند أقصى متطرف خارجي مرصود (بيعًا: أدناه)
        — يتحرك مع كل متطرف خارجي أحدث، ويُحل القديم بمنطقة INVALIDATED (جدول
        الانتقالات (د)). **ملاحظة تناظر موثقة**: حد النطاق نفسه على جانب
        البنية (premium/discount في 3-c) يُشتق من المتطرفات الخارجية نفسها
        التي يمررها المستدعي — توازن تصميمي مقصود بين الكاشفين، بلا ربط
        برمجي (عقد استقلال الكاشفات). ازدواج المستوى مع منطقة PRIOR_SWING
        للمتطرف الحاكم مقصود وموثق: الدلالتان مختلفتان (كسر حد النطاق غير
        اجتياح متطرف منفرد) والدمج مسؤولية التجميع (3-f).
        """
        live_id = self._boundary_live.get(side)
        record = self._records.get(live_id) if live_id is not None else None
        if record is not None:
            improved = (
                swing.price > record.price_high
                if side is LiquiditySide.BUY_SIDE
                else swing.price < record.price_low
            )
            if not improved:
                return
            if record.state is ZoneState.ACTIVE:
                record.state = ZoneState.INVALIDATED
                record.dirty = True
        structural = self._config.source_structural[LiquiditySourceType.RANGE_BOUNDARY]
        boundary = self._create_level_zone(
            source_type=LiquiditySourceType.RANGE_BOUNDARY,
            key=(
                f"{candle.instrument_id}|{candle.timeframe}|RANGE_BOUNDARY"
                f"|{side.value}|{swing.swing_id}"
            ),
            side=side,
            level=swing.price,
            level_time=swing.bar_time,
            level_bar=self._bars,
            instrument=candle.instrument_id,
            timeframe=candle.timeframe,
            structural=structural,
        )
        self._boundary_live[side] = boundary.zone_id

    # ── الداخلية: اللقطات والدرجات ──

    def _snapshot(self, record: _ZoneRecord) -> LiquidityZone:
        """بناء لقطة مجمّدة من السجل الحي — درجات مشتقة طازجة محصورة."""
        age = max(0, self._bars - record.origin_bar)
        return LiquidityZone(
            zone_id=record.zone_id,
            side=record.side,
            price_low=record.price_low,
            price_high=record.price_high,
            origin_time=record.origin_time,
            age=age,
            source_type=record.source_type,
            test_count=record.test_count,
            last_test_time=record.last_test_time,
            sweep_status=record.sweep_status,
            reaction_score=self._reaction_score(record),
            unmitigated_score=self._unmitigated_score(record),
            importance_score=self._importance_score(record),
            instrument=record.instrument,
            timeframe=record.timeframe,
            state=record.state,
        )

    def _reaction_score(self, record: _ZoneRecord) -> float:
        """جودة آخر رفض = tanh(عمقه المعياري) — بلا رفض بعد ⇒ 0 (لا معلومة)."""
        return _clamp01(tanh(max(0.0, record.reaction_depth_atr)))

    def _unmitigated_score(self, record: _ZoneRecord) -> float:
        """عدم التخفيف: 1.0 عند الإنشاء يتناقص مع الامتلاء وعدد الاختبارات.

        الصيغة الموثقة: ``unmitigated = (1 − fill) / (1 + test_count)`` حيث
        ``fill`` كسر فاصل المنطقة المُجتاز تاريخيًا (من الحافة القريبة)
        مشتقًا من أقصى تغلغل مرصود؛ المنطقة صفرية العرض تُعد ممتلئة الامتلاء
        كله متى تجاوز التغلغل مستواها صراحةً (لمسٌ عند المستوى لا يخففها).
        عند الإنشاء: fill=0 وtest_count=0 ⇒ 1.0 بالضبط.
        """
        width = record.price_high - record.price_low
        penetration = record.penetration_extreme
        if penetration is None:
            fill = 0.0
        elif width <= 0.0:
            beyond = (
                penetration > record.price_high
                if record.side is LiquiditySide.BUY_SIDE
                else penetration < record.price_low
            )
            fill = 1.0 if beyond else 0.0
        elif record.side is LiquiditySide.BUY_SIDE:
            fill = _clamp01((penetration - record.price_low) / width)
        else:
            fill = _clamp01((record.price_high - penetration) / width)
        return _clamp01((1.0 - fill) / (1.0 + record.test_count))

    def _importance_score(self, record: _ZoneRecord) -> float:
        """المزج الموثق لمدخلات §10.3 السبعة — «ليست احتمالًا» حرفيًا.

        متوسط موزون بمكونات [0, 1]: البنيوية (عند الإنشاء)، عدد المتساويات
        (مشبع عند ``equal_count_saturation``)، الطزاجة
        (``0.5 ** (age / freshness_halflife)`` — **معامل زمني بالشموع**)،
        دلالة الإطار (``timeframe_weight`` المعلنة من المستدعي)، القرب من
        السعر (إشباع خطي حتى مسافة ``ZONE_PROXIMITY`` ثم صفر)، وجود رد الفعل.
        المنطقة المستهلكة/المنتهية تُصفَّر كلها (مدخل «whether the zone has
        already been consumed» §10.3). القرب بلا مقياس تقلب متاح (قبل الدافئ)
        يعامل بأقصى الصلة لا بعقاب أعمى — قرار موثق: المناطق قبل الدافئ
        تتأسس قرب السعر أصلًا.
        """
        if record.state is not ZoneState.ACTIVE:
            return 0.0
        cfg = self._config
        weights = cfg.importance_weights
        total = (
            weights.structural
            + weights.equal_levels
            + weights.freshness
            + weights.timeframe
            + weights.distance
            + weights.reaction
        )
        age = max(0, self._bars - record.origin_bar)
        freshness = 0.5 ** (age / cfg.freshness_halflife)
        equal_component = min(1.0, record.equal_count / cfg.equal_count_saturation)
        distance_component = 1.0
        if self._last_vol is not None and self._last_close is not None:
            proximity = self._last_vol.threshold(ThresholdKey.ZONE_PROXIMITY)
            if proximity is not None and proximity > 0.0:
                mid = (record.price_low + record.price_high) / 2.0
                gap = abs(mid - self._last_close) / proximity
                distance_component = _clamp01(1.0 - gap)
        blended = (
            weights.structural * record.structural
            + weights.equal_levels * equal_component
            + weights.freshness * freshness
            + weights.timeframe * cfg.timeframe_weight
            + weights.distance * distance_component
            + weights.reaction * self._reaction_score(record)
        )
        return _clamp01(blended / total)
