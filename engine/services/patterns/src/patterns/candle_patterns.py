"""عائلات أنماط الشموع الثماني (§13.1) — مستعارات مسماة لتركيبات السمات الست.

§13.1 حرفيًا: «Named patterns are aliases for feature combinations» — كل
عائلة هنا تركيبة **عتبات نسبية موثقة** على السمات الست المسجلة في 5-a
(body_fraction / wick_asymmetry / close_location / range_percentile /
gap_relationship / volume_relationship)، تُستهلك حصرًا عبر دوال
:mod:`features.candle_features` بالمسار الوحيد (A-02) — لا يُشتق أي
سمة يدويًا في هذا الملف. «الأنماط أوصاف مضغوطة لسلوك السعر لا تنبئات
سحرية» (§13): العتبات نقاط انطلاق إعدادية للتقييم والمعايرة، والتراكب
بين العائلات متوقع بالتصميم (المستعار الواحد يجمع تركيبات متقاطعة:
الشمعة المبتلِعة إغلاقها قوي غالبًا، والمطرقة دبوس بسياق).

البنية: دوال تصنيف **صرفة** ‎(list[Candle], config) → CandleClassification | None‎
لكل عائلة (تصنّف عند الشمعة الأخيرة — شمعة القرار — وسياقها كله خلفي)،
وكاشف حالة :class:`CandlePatternDetector` يبث الأنواع الثلاثة ذات
الأحداث في قاموس §20 حصرًا على نمط :mod:`orderflow.imbalance`.

بوابة الدافئ الموحدة (قرار معماري موثق)
----------------------------------------
التصنيف — صرفًا كان أو داخل الكاشف — لا يصدر إلا إذا كانت السمات الست
**محدودة كلها** عند شمعة القرار: أي nan دافئ في نوافذ
range_percentile/gap_relationship/volume_relationship يُسقط التصنيف
(no-classification، لا تخمين). العلة: ``feature_readings`` في الحمولة
والتصنيف معًا يحملان السمات الست كاملة — «التركيب المستعار ظاهر» عقد
5-a — فسجل بقراءات ناقصة مستعار مكسور. النتيجة العملية: أقل طول مدخلات
لاكتمال الدافئ = أكبر نافذة في الإعداد (و+2 لكسر الداخلية: مئيني الأم
عند الموضع الثالث من النهاية يحتاج نافذته كاملة). النمط الذي تكتمل
هندسته أثناء الدافئ **لا يُستدرك رجعيًا** أبدًا (لا-نظرة/لا-رفرفة):
التصنيف يقع عند شمعة قرار مكتملة الدافئ أو لا يقع.

هندسات العائلات الثماني (كل العتبات نسب من [0,1] — لا ثوابت مطلقة)
--------------------------------------------------------------------
**ENGULFING** (حدث §20 بوزن 0.35): المبتلِعة جسمها ≥
``engulfing_body_fraction_min`` من مداها، والمُبتلَعة جسم فعلي
(body_fraction ≥ ``engulfed_body_fraction_min`` وجسم > 0 — الدوجي لا
يُبتلَع)، ومجال جسم الحالية يغطي مجال جسم السابقة (احتواء غير صارم)،
والألوان متعاكسة (التعريف الكلاسيكي الموثق: الصاعدة تبتلع هابطة
والعكس — يمنع عدّ شمعة الاستمرار ابتلاعًا)، والإغلاق قوي بجهة
الابتلاع: close_location ≥ ``engulfing_close_location_min`` للصاعد و
≤ 1−الحد للهابط. ``strength`` = مقياس §20 «Body ratio»: نسبة جسم
المبتلِعة إلى جسم المُبتلَعة r (≥ 1 بالاحتواء) مطبَّعة بالإشباع
r/(r+1) — وتُحسب بصورتها المستقرة الآمنة من الانفجار
``جسم_المبتلِعة / (الجسمين معًا)`` ∈ [0.5, 1).

**PIN_REJECTION** (حدث REJECTION_CANDLE بوزن 0.30): جسم صغير نسبيًا
(body_fraction ≤ ``rejection_body_fraction_max``) + ذيل مهيمن بجهة الرفض
(wick_asymmetry ≤ −``rejection_wick_asymmetry_min`` لذيل سفلي ⇒ BULLISH،
و≥ +الحد لعلوي ⇒ BEARISH). ``strength`` = مقياس §20 «Wick ratio»: حصة
الذيل المهيمن من المدى = ذيل/مدى — وهي جبريًا ‎((1−body_fraction) +
|wick_asymmetry|)/2‎ فتظهر في فضاء السمات نفسه. جوانب §20 «location»
محققة ضمنًا بالهندسة: الإغلاق ≥ الذيل السفلي/المدى عند الرفض الهابط
(‎close ≥ min(open,close) ⇒ close_location ≥ الذيل_السفلي/المدى‎) فلا
عتبة إضافية تُشترط.

**INSIDE_BAR** (تصنيف سياقي غير مبثوث): مدى الشمعة داخل مدى سابقتها
(احتواء غير صارم؛ الشمعة المطابقة لأمها داخلية بانضغاط 0.0 موثق) —
direction NEUTRAL قبل الكسر (عقد PatternDirection في 5-a) وstrength =
1 − مدى_الداخلية/مدى_الأم (الأم منعدمة المدى ⇒ الداخلية كذلك ⇒ انضغاط
كامل 1.0).

**INSIDE_BAR_BREAK** (حدث §20 بوزن 0.35): ثلاث شموع — أم (سياق) فداخلية
(احتواء غير صارم في مدى الأم) فكاسرة **تغلق** خارج مدى الأم جهةً
(الإغلاق حصرًا لا الذيل: مسبار الذيل ليس كسرًا مؤكدًا — §26.3/§27).
``bars_in_pattern=2`` (الداخلية + الكاسرة؛ الأم مرجع السياق) و``bar_time``
لشمعة الكسر. ``strength`` = مقياس §20 «Range compression/expansion»
بقرار موثق: تباين الانضغاط-فالتوسع ‎(مئيني_مدى_الكاسرة − مئيني_مدى_الأم + 1)/2‎
— أم هادئة في نافذتها (مئيني منخفض = انضغاط حقيقي قبْل الكسر) يكسرها
كاسر متوسع (مئيني مرتفع) فتبلغ القيمة 1.0، والعكس صفرًا؛ الطرفان من
``range_percentile`` المسجلة والمتوسط يضمن [0,1].

**HAMMER_SHOOTING_STAR** (سياقي): هندسة الرفض نفسها (العتبتان
المشتركتان أعلاه — §13.1 يفصل السياق لا الهندسة) **+ سياق اتجاه سابق**:
استكشاف صارم تحت قيعان آخر ``trend_context_bars``−1 شمعة (مطرقة، BULLISH)
أو فوق قممها (شهاب، BEARISH) — القرار الموثق لتعريف «القاع/القمة»: جديد
قطعي داخل نافذة خلفية، كله خلفي (لا-نظرة). strength = Wick ratio نفسه.

**DOJI** (سياقي): body_fraction ≤ ``doji_body_fraction_max`` — NEUTRAL،
strength = 1 − body_fraction (استقلال تام كلما انعدم الجسم؛ المسطحة
مدى منعدم جسمها 0.0 بحكم السمة ⇒ دوجي مطلق 1.0).

**MORNING_EVENING_STAR** (سياقي، ثلاثية): أولى معاكسة وافرة (body_fraction
≥ ``star_flank_body_fraction_min``) فنجمة صغيرة الجسم (≤
``star_body_fraction_max``) فثالثة موجهة وافرة تغلق داخل جسم الأولى بعد
منتصفه (بوابة الاختراق الكلاسيكية عند المنتصف). قرار موثق لأسواق 24/7
المتصلة: لا شرط فجوة للنجمة (الفجوات نادرة؛ التوقف مضغوط الجسم هو
الجوهر، وgap_relationship تبقى في القراءات لا في البوابة). strength =
عمق اختراق الثالثة داخل جسم الأولى مطبَّعًا: منتصف الجسم ⇒ 0.5 وقمة
الجسم ⇒ 1.0 وما فوق ⇒ مشبعًا 1.0 (تثبيت حدّي [0,1]).

**STRONG_CLOSING** (سياقي): جسم وافر (≥ ``strong_close_body_fraction_min``)
+ إغلاق جهوي قوي (close_location ≥ ``strong_close_location_min`` أو ≤
1−الحد). strength = متوسط (الإغلاق الجهوي، حصة الجسم). عتبتا الإغلاق
الجهوية تنحصر [0.5, 1] حتمًا كي لا تتقاطع جهتا المرآة (m و1−m).

**EXPANSION** (سياقي): range_percentile ≥
``expansion_range_percentile_min`` (نافذة الإطار الأوسع) — الاتجاه من
إشارة الجسم (صفر ⇒ NEUTRAL موثق) وstrength = المئيني نفسه (قراءة §20
العمودية «Vol percentile» بروح التوسع).

الكاشف والأحداث (§20 + §26.3 + §27)
------------------------------------
:class:`CandlePatternDetector` آلة تتابعية شمعة-بشمعة على نمط
imbalance.py (أقرب مرجع): شموع **مغلقة** فقط، هوية واحدة (أداة/إطار
تُلتقط من أول شمعة أو تمرَّر كاملة)، وترتيب bar_time تصاعدي قطعي —
التكرار والمتأخر يُرفضان رفضًا صاخبًا. لا رفرفة بنيويًا: كل شمعة
تُستهلك مرة واحدة والتصنيف دالة صرفة لنافذتها الخلفية، فيُبث كل نمط
مرة واحدة عند شمعة قراره حصرًا. عند الشمعة الواحدة قد يتحقق أكثر من
نمط (تراكب المستعارات متوقع) فتُعاد الأحداث **بترتيب عائلات §13.1**:
الابتلاع ثم الرفض ثم كسر الداخلية. الأوزان الافتراضية (0.35/0.30/0.35)
شأن الدمج (§19) عبر ``DEFAULT_EVENT_WEIGHTS`` — الكاشف يُبث ولا يزن.

``EmittedEvent`` المحلي هنا على نمط structure/events.py حرفيًا (نوع +
وقت + حمولة 5-a)؛ تجميع المغلف (event_id/trace_id/receive_time) مسؤولية
الناشر اللاحق وحده (§32) ولا يُبنى هنا — والمنسق يصدّره لاحقًا من
الحزمة (هذا الملف لا يعدّل ``__init__.py``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from features import (
    FeatureSeries,
    body_fraction_series,
    close_location_series,
    gap_relationship_series,
    range_percentile_series,
    volume_relationship_series,
    wick_asymmetry_series,
)
from schemas import (
    Candle,
    CandlePatternEventPayload,
    CandlePatternFamily,
    EventType,
    PatternDirection,
)

__all__ = [
    "CandleClassification",
    "CandlePatternConfig",
    "CandlePatternDetector",
    "EmittedEvent",
    "classify_doji",
    "classify_engulfing",
    "classify_expansion",
    "classify_hammer_shooting_star",
    "classify_inside_bar",
    "classify_inside_bar_break",
    "classify_last_candle",
    "classify_morning_evening_star",
    "classify_rejection",
    "classify_strong_closing",
]


# ═════════════════════════════ الإعداد ═════════════════════════════


def _check_unit_interval(name: str, value: float) -> None:
    """عتبة نسبية موثقة من [0,1] — أي خرق رفض صاخب لا صمت."""
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} عتبة نسبية من [0,1] حصرًا؛ وُجد {value!r}")


def _check_mirror_interval(name: str, value: float) -> None:
    """عتبة إغلاق جهوية تناظرية: من [0.5, 1] كي لا تتقاطع جهتا المرآة (m و1−m)."""
    if not isfinite(value) or not 0.5 <= value <= 1.0:
        raise ValueError(f"{name} عتبة جهوية من [0.5, 1] حصرًا (تناظر m/1-m)؛ وُجد {value!r}")


@dataclass(frozen=True)
class CandlePatternConfig:
    """إعداد عائلات الشموع الثماني — نقاط انطلاق إعدادية للتقييم
    والمعايرة (ليست توصيات تداول).

    كل العتبات نسب من [0,1] موثقة في هندسة عائلتها برأس الموديول؛
    النوافذ الثلاث لأصحاب الدافئ تطابق مسميات السجل المركزي
    (range_percentile_100 / gap_relationship_20 / volume_relationship_20
    في 5-a) وتقبل التجاوز.
    """

    # الابتلاع (BULLISH/BEARISH_ENGULFING §20)
    #: حصة جسم المبتلِعة من مداها — جسم وافر يحسم الجهة.
    engulfing_body_fraction_min: float = 0.55
    #: حصة جسم المُبتلَعة الدنيا — جسم فعلي يُبتلَع (الدوجي لا يُبتلَع).
    engulfed_body_fraction_min: float = 0.10
    #: إغلاق المبتلِعة في أعلى مداها (الصاعد) — الهابط مرآة ≤ 1−الحد.
    engulfing_close_location_min: float = 0.70

    # الرفض/الدبوس (REJECTION_CANDLE §20) — يشترك معه المطرقة/الشهاب
    #: أدنى هيمنة ذيلية بجهة الرفض |wick_asymmetry| (ذيل سفلي ⇒ صاعد).
    rejection_wick_asymmetry_min: float = 0.60
    #: أقصى حصة جسم شمعة الرفض — الجسم الصغير شرط الدبوس.
    rejection_body_fraction_max: float = 0.30

    # سياق الاتجاه للمطرقة/الشهاب (استكشاف جديد داخل نافذة خلفية)
    #: عدد الشموع في سياق الاتجاه: شمعة النمط + السواب (≥ 2).
    trend_context_bars: int = 5

    # الدوجي
    #: أقصى حصة جسم الدوجي.
    doji_body_fraction_max: float = 0.10

    # النجمة الصباحية/المسائية (ثلاثية)
    #: أقصى حصة جسم النجمة (شمعة التوقف).
    star_body_fraction_max: float = 0.30
    #: أدنى حصة جسمَي الشمعتين الطرفيتين (الأولى والثالثة).
    star_flank_body_fraction_min: float = 0.50

    # الإغلاق القوي
    #: إغلاق جهوي قوي: أعلى المدى للصاعد والمرآة ≤ 1−الحد للهابط.
    strong_close_location_min: float = 0.80
    #: أدنى حصة الجسم في شمعة الإغلاق القوي.
    strong_close_body_fraction_min: float = 0.60

    # التوسع
    #: أدنى مئيني مدى تعد به الشمعة متوسعة داخل نافذتها.
    expansion_range_percentile_min: float = 0.90

    # نوافذ السمات ذات الدافئ (مطابقة مسميات السجل المركزي)
    #: نافذة مئيني المدى (عقد rolling_percentile: ≥ 2).
    range_percentile_window: int = 100
    #: نافذة علاقة الفجوة (عقد rolling_mean: ≥ 1).
    gap_relationship_window: int = 20
    #: نافذة علاقة الحجم (عقد rolling_mean: ≥ 1).
    volume_relationship_window: int = 20

    def __post_init__(self) -> None:
        _check_unit_interval("engulfing_body_fraction_min", self.engulfing_body_fraction_min)
        _check_unit_interval("engulfed_body_fraction_min", self.engulfed_body_fraction_min)
        _check_mirror_interval("engulfing_close_location_min", self.engulfing_close_location_min)
        _check_unit_interval("rejection_wick_asymmetry_min", self.rejection_wick_asymmetry_min)
        _check_unit_interval("rejection_body_fraction_max", self.rejection_body_fraction_max)
        _check_unit_interval("doji_body_fraction_max", self.doji_body_fraction_max)
        _check_unit_interval("star_body_fraction_max", self.star_body_fraction_max)
        _check_unit_interval("star_flank_body_fraction_min", self.star_flank_body_fraction_min)
        _check_mirror_interval("strong_close_location_min", self.strong_close_location_min)
        _check_unit_interval("strong_close_body_fraction_min", self.strong_close_body_fraction_min)
        _check_unit_interval("expansion_range_percentile_min", self.expansion_range_percentile_min)
        if self.trend_context_bars < 2:
            raise ValueError(
                f"trend_context_bars يجب أن يكون ≥ 2 (شمعة النمط + سابقة واحدة على "
                f"الأقل)؛ وُجد {self.trend_context_bars}"
            )
        if self.range_percentile_window < 2:
            raise ValueError(
                f"range_percentile_window يجب أن يكون ≥ 2 (عقد rolling_percentile)؛ "
                f"وُجد {self.range_percentile_window}"
            )
        if self.gap_relationship_window < 1:
            raise ValueError(
                f"gap_relationship_window يجب أن يكون ≥ 1 (عقد rolling_mean)؛ "
                f"وُجد {self.gap_relationship_window}"
            )
        if self.volume_relationship_window < 1:
            raise ValueError(
                f"volume_relationship_window يجب أن يكون ≥ 1 (عقد rolling_mean)؛ "
                f"وُجد {self.volume_relationship_window}"
            )


def _resolve(config: CandlePatternConfig | None) -> CandlePatternConfig:
    """الإعداد الفعلي — None يعني الافتراضات الموثقة."""
    return config if config is not None else CandlePatternConfig()


# ═════════════════ سلاسل السمات والقراءات (المسار الوحيد A-02) ═════════════════


@dataclass(frozen=True)
class _Series:
    """سلاسل السمات الست فوق مدخلات التصنيف — تُحسب بدوال features حصرًا."""

    body_fraction: FeatureSeries
    wick_asymmetry: FeatureSeries
    close_location: FeatureSeries
    range_percentile: FeatureSeries
    gap_relationship: FeatureSeries
    volume_relationship: FeatureSeries


def _feature_series(candles: list[Candle], config: CandlePatternConfig) -> _Series:
    """حساب السمات الست بنوافذ الإعداد — لا اشتقاق يدوي أبدًا (A-02).

    الفورية الثلاث بلا معاملات؛ وذوات النوافذ بنوافذ الإعداد (تطابق
    مسميات السجل أو تجاوزها). أي تناقض في المدخلات (خلط أدوات/أطر أو
    ترتيب مكسور) يرفضه عقد :mod:`features.windows` الصاخب.
    """
    return _Series(
        body_fraction=body_fraction_series(candles),
        wick_asymmetry=wick_asymmetry_series(candles),
        close_location=close_location_series(candles),
        range_percentile=range_percentile_series(candles, config.range_percentile_window),
        gap_relationship=gap_relationship_series(candles, config.gap_relationship_window),
        volume_relationship=volume_relationship_series(candles, config.volume_relationship_window),
    )


def _readings_at(series: _Series, index: int) -> dict[str, float]:
    """قراءات السمات الست عند موضع (الفهرس السالب مقبول) — المفاتيح مطابقة
    ``CANDLE_FEATURE_KEYS`` حرفيًا (عقد الحمولة 5-a: مفاتيح الست حصرًا)."""
    return {
        "body_fraction": float(series.body_fraction[index]),
        "wick_asymmetry": float(series.wick_asymmetry[index]),
        "close_location": float(series.close_location[index]),
        "range_percentile": float(series.range_percentile[index]),
        "gap_relationship": float(series.gap_relationship[index]),
        "volume_relationship": float(series.volume_relationship[index]),
    }


def _warmup_complete(readings: dict[str, float]) -> bool:
    """بوابة الدافئ الموحدة: السمات الست محدودة كلها عند شمعة القرار."""
    return all(isfinite(value) for value in readings.values())


# ═════════════════════════ سجلا الخرج ═════════════════════════


@dataclass(frozen=True)
class CandleClassification:
    """تصنيف عائلة شموعية عند شمعة القرار — خرج الدوال الصرفة.

    تصنيف سياقي للاستهلاك الداخلي (الاستئصال 5a.3 والسمات): العائلات
    الثماني كلها تُصنَّف هنا، والثلاثة ذات الأنواع في قاموس §20 وحدها
    يبثها الكاشف أحداثًا. ``feature_readings`` تحمل السمات الست عند شمعة
    القرار — التركيبة المستعارة (§13.1) ظاهرة كاملة.
    """

    family: CandlePatternFamily
    direction: PatternDirection
    strength: float
    #: bar_time شمعة القرار (آخر شمعة في هندسة العائلة — موثقة لكل عائلة).
    bar_time: datetime
    feature_readings: dict[str, float]


@dataclass(frozen=True)
class EmittedEvent:
    """حدث نمط شموعي مؤكد عند إقفال شمعة القرار — خرج الكاشف ومدخل مجمّع
    المغلف.

    على نمط :mod:`structure.events` حرفيًا: ``event_type`` نوع §20 الموثق،
    و``event_time`` هو ``bar_time`` الشمعة المؤكِدة (لا-نظرة-مستقبلية
    §26.3)، و``payload`` حمولة 5-a المجمّدة. تجميع المغلف
    (event_id/trace_id/receive_time) مسؤولية الناشر اللاحق وحده (§32)
    ولا يُبنى هنا إطلاقًا.
    """

    event_type: EventType
    event_time: datetime
    payload: CandlePatternEventPayload


# ═══════════════════ مصنِّفات العائلات (داخلية موحدة الإطعام) ═══════════════════
# كل مصنِّف: (candles, series, config) → تصنيف عند الشمعة الأخيرة أو None —
# بوابة الدافئ أولًا ثم هندسة العائلة؛ الترتيب هنا هو ترتيب §13.1.


def _engulfing_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """الابتلاع — هندسته الموثقة برأس الموديول؛ شمعة القرار هي المبتلِعة."""
    if len(candles) < 2:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    last, prev = candles[-1], candles[-2]
    # ألوان متعاكسة (التعريف الكلاسيكي): الصاعدة تبتلع هابطة والعكس.
    bullish = prev.close < prev.open and last.close > last.open
    bearish = prev.close > prev.open and last.close < last.open
    if not (bullish or bearish):
        return None
    body_prev = abs(prev.close - prev.open)
    body_last = abs(last.close - last.open)
    bf_prev = float(series.body_fraction[-2])
    if bf_prev < config.engulfed_body_fraction_min or body_prev <= 0.0:
        return None  # لا جسم فعلي يُبتلَع (دوجي/مسطحة)
    if readings["body_fraction"] < config.engulfing_body_fraction_min:
        return None  # جسم المبتلِعة غير وافر
    # الاحتواء الهندسي: مجال جسم الحالية يغطي مجال جسم السابقة (غير صارم).
    if not (
        min(last.open, last.close) <= min(prev.open, prev.close)
        and max(last.open, last.close) >= max(prev.open, prev.close)
    ):
        return None
    if bullish:
        if readings["close_location"] < config.engulfing_close_location_min:
            return None  # الإغلاق ليس قويًا بجهة الابتلاع الصاعد
        direction = PatternDirection.BULLISH
    else:
        if readings["close_location"] > 1.0 - config.engulfing_close_location_min:
            return None  # الإغلاق ليس قويًا بجهة الابتلاع الهابط
        direction = PatternDirection.BEARISH
    # §20 «Body ratio» بالصورة المستقرة r/(r+1) — الاحتواء يضمن r ≥ 1
    # فتكون القيمة في [0.5, 1) بلا انفجار عند أجسام متناهية الصغر.
    strength = body_last / (body_last + body_prev)
    return CandleClassification(
        family=CandlePatternFamily.ENGULFING,
        direction=direction,
        strength=strength,
        bar_time=last.bar_time,
        feature_readings=readings,
    )


def _rejection_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """الدبوس/الرفض — ذيل مهيمن بجهة الرفض وجسم صغير؛ شمعة القرار وحدها."""
    if not candles:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    last = candles[-1]
    if readings["body_fraction"] > config.rejection_body_fraction_max:
        return None
    upper_wick = last.high - max(last.open, last.close)
    lower_wick = min(last.open, last.close) - last.low
    if readings["wick_asymmetry"] <= -config.rejection_wick_asymmetry_min:
        direction = PatternDirection.BULLISH  # ذيل سفلي مهيمن — رفض هبوطي
        dominant = lower_wick
    elif readings["wick_asymmetry"] >= config.rejection_wick_asymmetry_min:
        direction = PatternDirection.BEARISH  # ذيل علوي مهيمن — رفض صاعد
        dominant = upper_wick
    else:
        return None
    price_range = last.high - last.low
    if price_range <= 0.0:
        return None  # حارس هندسي: العتبة الموجبة تستلزم مدى موجبًا أصلًا
    # §20 «Wick ratio»: حصة الذيل المهيمن من المدى — تكافئ جبريًا
    # ((1−body_fraction) + |wick_asymmetry|)/2 فتبقى في فضاء السمات.
    strength = dominant / price_range
    return CandleClassification(
        family=CandlePatternFamily.PIN_REJECTION,
        direction=direction,
        strength=strength,
        bar_time=last.bar_time,
        feature_readings=readings,
    )


def _hammer_star_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """المطرقة/الشهاب — هندسة الرفض + استكشاف جديد في سياق اتجاه خلفي."""
    context_len = config.trend_context_bars
    if len(candles) < context_len:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    last = candles[-1]
    if readings["body_fraction"] > config.rejection_body_fraction_max:
        return None
    context = candles[-context_len:-1]  # السواب حصرًا — لا نظرة أمامية
    if readings["wick_asymmetry"] <= -config.rejection_wick_asymmetry_min:
        # مطرقة: رفض هبوطي عند قاع — استكشاف صارم تحت قيعان السياق.
        if last.low >= min(candle.low for candle in context):
            return None
        direction = PatternDirection.BULLISH
        dominant = min(last.open, last.close) - last.low
    elif readings["wick_asymmetry"] >= config.rejection_wick_asymmetry_min:
        # شهاب: رفض صاعد عند قمة — استكشاف صارم فوق قمم السياق.
        if last.high <= max(candle.high for candle in context):
            return None
        direction = PatternDirection.BEARISH
        dominant = last.high - max(last.open, last.close)
    else:
        return None
    price_range = last.high - last.low
    if price_range <= 0.0:
        return None  # حارس هندسي (نفس علة الرفض)
    strength = dominant / price_range
    return CandleClassification(
        family=CandlePatternFamily.HAMMER_SHOOTING_STAR,
        direction=direction,
        strength=strength,
        bar_time=last.bar_time,
        feature_readings=readings,
    )


def _inside_bar_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """الشمعة الداخلية (سياقيًا، قبل الكسر) — NEUTRAL بعقد PatternDirection."""
    if len(candles) < 2:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    last, prev = candles[-1], candles[-2]
    if last.high > prev.high or last.low < prev.low:
        return None  # المدى ليس داخل مدى السابقة
    mother_range = prev.high - prev.low
    # أم منعدمة المدى ⇒ الداخلية منعدمة كذلك ⇒ انضغاط كامل (موثق).
    strength = 1.0 if mother_range <= 0.0 else 1.0 - (last.high - last.low) / mother_range
    return CandleClassification(
        family=CandlePatternFamily.INSIDE_BAR,
        direction=PatternDirection.NEUTRAL,
        strength=strength,
        bar_time=last.bar_time,
        feature_readings=readings,
    )


def _inside_break_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """كسر الشمعة الداخلية — أم فداخلية فكاسرة تغلق خارج مدى الأم."""
    if len(candles) < 3:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    mother, inside, breaker = candles[-3], candles[-2], candles[-1]
    if inside.high > mother.high or inside.low < mother.low:
        return None  # لا شمعة داخلية فلا كسر يُرصد
    mother_rp = float(series.range_percentile[-3])
    if not isfinite(mother_rp):
        return None  # نافذة مئيني الأم لم تكتمل بعد (الدافئ الممتد)
    if breaker.close > mother.high:
        direction = PatternDirection.BULLISH
    elif breaker.close < mother.low:
        direction = PatternDirection.BEARISH
    else:
        return None  # الإغلاق داخل مدى الأم — مسبار الذيل ليس كسرًا مؤكدًا
    # §20 «Range compression/expansion»: تباين مئينيَي الأم (انضغاط)
    # والكاسرة (توسع) مطبَّعًا إلى [0,1] — القرار موثق برأس الموديول.
    strength = (readings["range_percentile"] - mother_rp + 1.0) / 2.0
    return CandleClassification(
        family=CandlePatternFamily.INSIDE_BAR,
        direction=direction,
        strength=strength,
        bar_time=breaker.bar_time,
        feature_readings=readings,
    )


def _doji_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """الدوجي — جسم منعدم تقريبًا؛ NEUTRAL بقوة 1−حصة الجسم."""
    if not candles:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    if readings["body_fraction"] > config.doji_body_fraction_max:
        return None
    return CandleClassification(
        family=CandlePatternFamily.DOJI,
        direction=PatternDirection.NEUTRAL,
        strength=1.0 - readings["body_fraction"],
        bar_time=candles[-1].bar_time,
        feature_readings=readings,
    )


def _star3_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """النجمة الصباحية/المسائية — ثلاثية؛ شمعة القرار هي الثالثة."""
    if len(candles) < 3:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    first, third = candles[-3], candles[-1]
    bf_first = float(series.body_fraction[-3])
    bf_star = float(series.body_fraction[-2])
    if bf_star > config.star_body_fraction_max:
        return None  # النجمة ذات جسم وافر — ليست توقفًا مضغوطًا
    body_first = abs(first.close - first.open)
    if body_first <= 0.0 or bf_first < config.star_flank_body_fraction_min:
        return None  # الأولى بلا جسم فعلي وافر
    if readings["body_fraction"] < config.star_flank_body_fraction_min:
        return None  # الثالثة غير وافرة
    mid = (first.open + first.close) / 2.0
    if first.close < first.open and third.close > third.open:
        # صباحية: أولى هابطة فنجمة فثالثة صاعدة تغلق فوق منتصف جسم الأولى.
        if third.close < mid:
            return None
        direction = PatternDirection.BULLISH
        penetration = (third.close - mid) / body_first
    elif first.close > first.open and third.close < third.open:
        # مسائية: المرآة — ثالثة هابطة تغلق تحت منتصف جسم الأولى.
        if third.close > mid:
            return None
        direction = PatternDirection.BEARISH
        penetration = (mid - third.close) / body_first
    else:
        return None  # الطرفان غير متعاكسين — ليست نجمة انعكاسية
    # عمق اختراق الثالثة: منتصف الجسم ⇒ 0.5، قمته ⇒ 1.0، وما فوق مشبع.
    strength = min(1.0, max(0.0, 0.5 + penetration))
    return CandleClassification(
        family=CandlePatternFamily.MORNING_EVENING_STAR,
        direction=direction,
        strength=strength,
        bar_time=third.bar_time,
        feature_readings=readings,
    )


def _strong_closing_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """الإغلاق القوي — جسم وافر يغلق بعمق جهة مداه."""
    if not candles:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    body_fraction = readings["body_fraction"]
    close_location = readings["close_location"]
    if body_fraction < config.strong_close_body_fraction_min:
        return None
    if close_location >= config.strong_close_location_min:
        direction = PatternDirection.BULLISH
        strength = (close_location + body_fraction) / 2.0
    elif close_location <= 1.0 - config.strong_close_location_min:
        direction = PatternDirection.BEARISH
        strength = ((1.0 - close_location) + body_fraction) / 2.0
    else:
        return None  # الإغلاق متوسط المدى — لا جهة حاسمة
    return CandleClassification(
        family=CandlePatternFamily.STRONG_CLOSING,
        direction=direction,
        strength=strength,
        bar_time=candles[-1].bar_time,
        feature_readings=readings,
    )


def _expansion_at(
    candles: list[Candle], series: _Series, config: CandlePatternConfig
) -> CandleClassification | None:
    """التوسع — مدى يرتب في أعلى مئيني نافذته؛ الاتجاه من إشارة الجسم."""
    if not candles:
        return None
    readings = _readings_at(series, -1)
    if not _warmup_complete(readings):
        return None
    if readings["range_percentile"] < config.expansion_range_percentile_min:
        return None
    last = candles[-1]
    if last.close > last.open:
        direction = PatternDirection.BULLISH
    elif last.close < last.open:
        direction = PatternDirection.BEARISH
    else:
        direction = PatternDirection.NEUTRAL  # جسم منعدم — توسع بلا جهة (موثق)
    return CandleClassification(
        family=CandlePatternFamily.EXPANSION,
        direction=direction,
        strength=readings["range_percentile"],
        bar_time=last.bar_time,
        feature_readings=readings,
    )


# ═══════════════════ الدوال الصرفة العلنية ═══════════════════


def classify_engulfing(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف الابتلاع (صاعد/هابط) عند الشمعة الأخيرة — دالة صرفة حتمية.

    انظر هندسة العائلة وقرارَي الألوان المتعاكسة والاحتواء غير الصارم
    برأس الموديول. ``None`` عند غياب النمط أو نقص السياق أو الدافئ.
    """
    cfg = _resolve(config)
    if len(candles) < 2:
        return None
    return _engulfing_at(candles, _feature_series(candles, cfg), cfg)


def classify_rejection(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف الدبوس/الرفض (ذيل سفلي ⇒ BULLISH وعلوي ⇒ BEARISH) — دالة صرفة."""
    cfg = _resolve(config)
    if not candles:
        return None
    return _rejection_at(candles, _feature_series(candles, cfg), cfg)


def classify_hammer_shooting_star(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف المطرقة/الشهاب — هندسة الرفض + سياق اتجاه خلفي — دالة صرفة."""
    cfg = _resolve(config)
    if len(candles) < cfg.trend_context_bars:
        return None
    return _hammer_star_at(candles, _feature_series(candles, cfg), cfg)


def classify_inside_bar(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف الشمعة الداخلية (NEUTRAL قبل الكسر) — دالة صرفة."""
    cfg = _resolve(config)
    if len(candles) < 2:
        return None
    return _inside_bar_at(candles, _feature_series(candles, cfg), cfg)


def classify_inside_bar_break(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف كسر الشمعة الداخلية (أم فداخلية فكاسرة) — دالة صرفة.

    شمعة القرار هي الكاسرة؛ يلزم اكتمال مئيني الأم أيضًا (دافئ ممتد
    بمقدار موضعين إضافيين).
    """
    cfg = _resolve(config)
    if len(candles) < 3:
        return None
    return _inside_break_at(candles, _feature_series(candles, cfg), cfg)


def classify_doji(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف الدوجي (NEUTRAL) — دالة صرفة."""
    cfg = _resolve(config)
    if not candles:
        return None
    return _doji_at(candles, _feature_series(candles, cfg), cfg)


def classify_morning_evening_star(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف النجمة الصباحية/المسائية (ثلاثية) — دالة صرفة."""
    cfg = _resolve(config)
    if len(candles) < 3:
        return None
    return _star3_at(candles, _feature_series(candles, cfg), cfg)


def classify_strong_closing(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف شمعة الإغلاق القوي (صاعد/هابط) — دالة صرفة."""
    cfg = _resolve(config)
    if not candles:
        return None
    return _strong_closing_at(candles, _feature_series(candles, cfg), cfg)


def classify_expansion(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> CandleClassification | None:
    """تصنيف شمعة التوسع (اتجاه إشارة الجسم، وقد يكون NEUTRAL) — دالة صرفة."""
    cfg = _resolve(config)
    if not candles:
        return None
    return _expansion_at(candles, _feature_series(candles, cfg), cfg)


def classify_last_candle(
    candles: list[Candle], config: CandlePatternConfig | None = None
) -> tuple[CandleClassification, ...]:
    """كل تصنيفات العائلات المتحققة عند الشمعة الأخيرة — بترتيب §13.1.

    ترتيب حتمي موثق: الابتلاع، الدبوس/الرفض، المطرقة/الشهاب، الداخلية،
    كسر الداخلية، الدوجي، النجمة، الإغلاق القوي، التوسع. التراكب متوقع
    (المستعارات متقاطعة بالتصميم)؛ القائمة الفارغة قانونية.
    """
    cfg = _resolve(config)
    if not candles:
        return ()
    series = _feature_series(candles, cfg)
    candidates = (
        _engulfing_at(candles, series, cfg),
        _rejection_at(candles, series, cfg),
        _hammer_star_at(candles, series, cfg),
        _inside_bar_at(candles, series, cfg),
        _inside_break_at(candles, series, cfg),
        _doji_at(candles, series, cfg),
        _star3_at(candles, series, cfg),
        _strong_closing_at(candles, series, cfg),
        _expansion_at(candles, series, cfg),
    )
    return tuple(item for item in candidates if item is not None)


# ═════════════════════════ الكاشف (§20) ═════════════════════════


def _buffer_capacity(config: CandlePatternConfig) -> int:
    """سعة المخزن الخلفي: أكبر نافذة سمات أو سياق اتجاه أو نمط + هامش 2.

    النوافذ تلزم قراءات الشمعة الأخيرة؛ وكسر الداخلية يحتاج مئيني الأم
    (الموضع الثالث من النهاية) فيلزمه نافذة كاملة تنتهي عنده — الهامش
    الموضعي +2 يضمنها عند امتلاء المخزن.
    """
    return (
        max(
            config.range_percentile_window,
            config.gap_relationship_window,
            config.volume_relationship_window,
            config.trend_context_bars,
            3,
        )
        + 2
    )


class CandlePatternDetector:
    """كاشف أنماط الشموع المبثوثة لكل (أداة، إطار) — شموع مغلقة فقط.

    يبث الأنواع الثلاثة ذات الأحداث في قاموس §20 حصرًا:
    BULLISH/BEARISH_ENGULFING (bars_in_pattern=2) وREJECTION_CANDLE
    (=1) وINSIDE_BAR_BREAK (=2 وbar_time لشمعة الكسر) — عند إقفال الشمعة
    الحاسمة حصرًا (§26.3). لا رفرفة بنيويًا (§27): كل شمعة تُستهلك مرة
    واحدة بترتيب صارم، والتصنيف دالة صرفة للنافذة الخلفية. عند الشمعة
    الواحدة قد يتحقق أكثر من نمط فتُعاد الأحداث بترتيب عائلات §13.1.

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اترك الهوية تُلتقط من أول شمعة)
    وغذّه كل شمعة مغلقة بترتيبها؛ ``on_candle`` يعيد أحداث هذه الشمعة
    وحدها، و``on_candles`` دفعة مطابقة للتغذية شمعة-بشمعة (حتمية).
    """

    def __init__(
        self,
        config: CandlePatternConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        if (instrument_id is None) != (timeframe is None):
            raise ValueError(
                "الهوية تُمرَّر كاملة (أداة وإطار معًا) أو تُترك لتُلتقط من أول "
                "شمعة — تمرير أحدهما وحده لبسٌ صامت لا يُقبل"
            )
        self._config = config if config is not None else CandlePatternConfig()
        self._instrument_id = instrument_id
        self._timeframe = timeframe
        self._last_bar_time: datetime | None = None
        self._buffer: list[Candle] = []
        self._capacity = _buffer_capacity(self._config)

    # ── الخصائص ──

    @property
    def config(self) -> CandlePatternConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يمرر في البناء."""
        return self._timeframe

    # ── التغذية ──

    def on_candle(self, candle: Candle) -> tuple[EmittedEvent, ...]:
        """استهلاك شمعة مغلقة — أحداث هذه الشمعة وحدها (صفر أو أكثر).

        الترتيب الداخلي (حتمي موثق): الحارس ← ضم المخزن الخلفي وقصّه إلى
        السعة ← حساب السمات الست مرة واحدة ← تصنيف الأنواع الثلاثة بترتيب
        عائلات §13.1 ← البث عند الشمعة الحالية حصرًا.
        """
        self._guard(candle)
        self._buffer.append(candle)
        overflow = len(self._buffer) - self._capacity
        if overflow > 0:
            del self._buffer[:overflow]  # الأقدم خارج كل نافذة وسياق
        series = _feature_series(self._buffer, self._config)
        events: list[EmittedEvent] = []
        engulfing = _engulfing_at(self._buffer, series, self._config)
        if engulfing is not None:
            event_type = (
                EventType.BULLISH_ENGULFING
                if engulfing.direction is PatternDirection.BULLISH
                else EventType.BEARISH_ENGULFING
            )
            events.append(self._emit(engulfing, event_type, bars_in_pattern=2))
        rejection = _rejection_at(self._buffer, series, self._config)
        if rejection is not None:
            events.append(self._emit(rejection, EventType.REJECTION_CANDLE, bars_in_pattern=1))
        inside_break = _inside_break_at(self._buffer, series, self._config)
        if inside_break is not None:
            events.append(self._emit(inside_break, EventType.INSIDE_BAR_BREAK, bars_in_pattern=2))
        return tuple(events)

    def on_candles(self, candles: Sequence[Candle]) -> tuple[EmittedEvent, ...]:
        """تغذية دفعة — مطابقة تمامًا للتغذية شمعة-بشمعة بترتيبها (حتمية)."""
        events: list[EmittedEvent] = []
        for candle in candles:
            events.extend(self.on_candle(candle))
        return tuple(events)

    # ── الداخلية ──

    def _emit(
        self,
        classification: CandleClassification,
        event_type: EventType,
        *,
        bars_in_pattern: int,
    ) -> EmittedEvent:
        """بناء السجل المبثوث — الحمولة بقراءات شمعة القرار الفعلية."""
        instrument = self._instrument_id
        timeframe = self._timeframe
        assert instrument is not None and timeframe is not None  # تثبتان معًا في الحارس
        payload = CandlePatternEventPayload(
            instrument=instrument,
            timeframe=timeframe,
            bar_time=classification.bar_time,
            family=classification.family,
            direction=classification.direction,
            feature_readings=dict(classification.feature_readings),
            strength=classification.strength,
            bars_in_pattern=bars_in_pattern,
        )
        return EmittedEvent(
            event_type=event_type, event_time=classification.bar_time, payload=payload
        )

    def _guard(self, candle: Candle) -> None:
        """حارس التدفق — إقفال وهوية وترتيب (نمط كواشف المرحلتين 3/4)."""
        if not candle.is_closed:
            raise ValueError(
                "الكاشف يستهلك الشموع المغلقة فقط (§27 فصل المتطور عن المؤكد) — "
                "الشمعة المتطورة لا تدخل آلة الأنماط"
            )
        if self._instrument_id is None:
            self._instrument_id = candle.instrument_id
            self._timeframe = candle.timeframe
        else:
            expected_instrument = self._instrument_id
            expected_timeframe = self._timeframe
            assert expected_timeframe is not None  # الهوية تثبت معًا أو تغيب معًا
            if candle.instrument_id != expected_instrument:
                raise ValueError(
                    f"خلط أدوات على كاشف واحد: استُهل على {expected_instrument!r} "
                    f"ووصلت شمعة {candle.instrument_id!r} — أنشئ كاشفًا لكل (أداة، إطار)"
                )
            if candle.timeframe != expected_timeframe:
                raise ValueError(
                    f"خلط أطر زمنية على كاشف واحد: استُهل على {expected_timeframe!r} "
                    f"ووصلت شمعة {candle.timeframe!r} — أنشئ كاشفًا لكل (أداة، إطار)"
                )
        last = self._last_bar_time
        if last is not None:
            if candle.bar_time == last:
                raise ValueError(
                    f"تكرار bar_time لشمعة سبق استهلاكها: {candle.bar_time} — "
                    "التكرار خطأ قانوني عند المغلقات"
                )
            if candle.bar_time < last:
                raise ValueError(
                    f"شمعة متأخرة (bar_time أقدم من آخر مستهلك): {candle.bar_time} "
                    f"بعد {last} — آلة الأنماط التتابعية ترفض المتأخر رفضًا صريحًا"
                )
        self._last_bar_time = candle.bar_time
