"""أنماط الشموع والبُنى الكلاسيكية (§13) — الكائنات وحمولات أحداثها (§20+§32).

«الأنماط أوصاف مضغوطة لسلوك السعر، لا تنبئات سحرية مستقلة» (§13) — كل
نموذج هنا قياس هندسي/سماتي موثق قابلاً للاختبار، والأسماء المتداولة
**مستعارات لتركيبات سمات** (§13.1: "Named patterns are aliases for feature
combinations") لا كيانات مستقلة بسلطة خاصة.

المصدر: §13.1 (سمات الشموع وعائلاتها الثماني)، §13.2 (البُنى الكلاسيكية
الثمانية ومخرجاتها الإلزامية)، §20 (أنواع أحداث الأنماط الخمسة وأوزانها)،
§32 (المغلف).

العقود الموثقة في هذه الوحدة:

- **الحتمية الصرفة**: كل نموذج مجمّد (frozen) يمنع الحقول الغريبة
  (extra="forbid") — عقد الكائنات القانونية في كل الحزمة.

- **لا-نظرة-مستقبلية (§26.3)**: كل حمولة تحمل ``bar_time`` الشمعة التي
  أكّدت النمط/الكسر — الكاشف يبث بعد إقفالها حصرًا.

- **الغامض مرشح لا كاذب (§13.2 حرفيًا)**: "If the geometry is ambiguous,
  the pattern remains a candidate and contributes little or nothing to
  Evidence Fusion" — الحمولة تحمل ``quality`` القياسية و``status``
  (CANDIDATE/CONFIRMED)؛ المرشح الضعيف يُبث إن كان نوعه من قاموس §20
  (الكسر/الكسر الفاشل) ويبقى وزنه مسؤولية الدمج (§19)، والنمط غير
  المكتمل لا يُبث أصلًا (لا نوع له في القاموس).

- **مخرجات §13.2 الثمانية حرفيًا**: pattern_type, geometry,
  anchor_points, completion_time, breakout_level, invalidation_level,
  measured_move, quality — كلها في ``ClassicalPatternEventPayload``
  بالأسماء نفسها.

- **قرار موثق — geometry قياسات رقمية حصرًا**: الحقل ``geometry``
  خريطة اسم-إلى-عدد (مثل ``height_atr`` و``slope`` و``width_bars``)؛
  التصنيفات الفرعية (مثل اتجاهَي ضلعي المثلث) تُستنتج من القياسات
  والأنكورات معًا — لا حقول نصية حرة داخل الهندسة.

- **قرار موثق — مفاتيح السمات الست حصرًا**: ``feature_readings`` في حمولة
  الشموع تقبل المفاتيح من أسماء سمات §13.1 الست حرفيًا (عقد
  ``CANDLE_FEATURE_KEYS``)؛ أي مفتاح آخر رفض صاخب لا صمت.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._types import (
    FiniteFloat,
    PositiveInt,
    Price,
    UnitInterval,
    UTCDatetime,
)
from .structure import BreakDirection


class _PatternsModel(BaseModel):
    """أساس موحد لكائنات الأنماط: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ═══════════════════════ تعدادات الأنماط §13 ═══════════════════════


class CandlePatternFamily(StrEnum):
    """عائلات أنماط الشموع الثماني (§13.1 حرفيًا بالترتيب).

    كل عائلة مستعار لتركيبة من السمات الست — لا تحمل سلطة تنبؤية
    ذاتية؛ فُصلت hammer/shooting star عن pin/rejection لأن الأولى
    تشترط سياق الاتجاه السابق (قاع/قمة) بينما الثانية رفض في الموضع
    أياً كان السياق (§13.1 يسميهما عائلتين مستقلتين).
    """

    ENGULFING = "ENGULFING"  # ابتلاع
    PIN_REJECTION = "PIN_REJECTION"  # شمعة رفض/دبوس
    HAMMER_SHOOTING_STAR = "HAMMER_SHOOTING_STAR"  # مطرقة/شهاب بسياق
    INSIDE_BAR = "INSIDE_BAR"  # شمعة داخلية
    DOJI = "DOJI"  # دوجي
    MORNING_EVENING_STAR = "MORNING_EVENING_STAR"  # نجمة صباحية/مسائية
    STRONG_CLOSING = "STRONG_CLOSING"  # شمعة إغلاق قوية
    EXPANSION = "EXPANSION"  # شمعة توسع


class PatternDirection(StrEnum):
    """توجيه النمط — يطابق لغة أحداث §20 الشمعية (BULLISH_ENGULFING).

    ``NEUTRAL`` للعائلات غير الموجهة عند التصنيف السياقي (مثل doji
    وinside bar قبل الكسر)؛ الأحداث المبثوثة (§20) توجيهية حصرًا.
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class ClassicalPatternType(StrEnum):
    """عائلات البُنى الكلاسيكية الثماني (§13.2) بجهاتها المفصولة.

    §13.2 يسمي ثماني عائلات: double top/bottom وhead and shoulders /
    inverse تعدّها الخطة عائلة واحدة ثنائية الجهة — القرار الموثق:
    فصل الجهتين في قيمتين صريحتين (أوضح للدمج والتقارير)، فالقيم
    الفعلية: قمة/قاع مزدوجان (2) + رأس وكتفان ومعكوسه (2) + مثلث +
    إسفين + علم + قناة + كسر نطاق + كسر فاشل (6) = 10 قيم لثماني
    عائلات مفصولة الجهة.
    """

    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    HEAD_AND_SHOULDERS = "HEAD_AND_SHOULDERS"
    INVERSE_HEAD_AND_SHOULDERS = "INVERSE_HEAD_AND_SHOULDERS"
    TRIANGLE = "TRIANGLE"
    WEDGE = "WEDGE"
    FLAG = "FLAG"
    CHANNEL = "CHANNEL"
    RANGE_BREAKOUT = "RANGE_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"


class PatternStatus(StrEnum):
    """حالة النمط لحظة الحدث (§13.2 حرفيًا).

    الهندسة الغامضة تبقى ``CANDIDATE`` وتساهم قليلاً أو لا تساهم في
    الدمج (§13.2)؛ ``CONFIRMED`` للهندسة النظيفة المكتملة.
    """

    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"


#: أسماء سمات الشموع الست القانونية (§13.1 حرفيًا) — المفاتيح المقبولة
#: حصرًا في ``CandlePatternEventPayload.feature_readings``.
CANDLE_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        "body_fraction",
        "wick_asymmetry",
        "close_location",
        "range_percentile",
        "gap_relationship",
        "volume_relationship",
    }
)


# ═══════════════════════ كائن الإرساء الهندسي ═══════════════════════


class AnchorPoint(_PatternsModel):
    """نقطة إرساء هندسية في نمط كلاسيكي (§13.2 ``anchor_points``).

    ``role`` اسم الدور الحر الموثق (P1..Pn للقمم/القيعان المتعاقبة،
    NECKLINE لرقبة الرأس والكتفين، POLE/BREAKOUT...) — البُنى الثماني
    تتشارك شكل النقطة لا أدوارها، فالحقل نص موسوم يوثقه الكاشف في
    هندسته؛ الشموع المتطابقة زمنًا ممنوعة (إرساء واحد لكل لحظة).
    """

    time: UTCDatetime
    price: Price
    role: str

    @model_validator(mode="after")
    def _role_non_empty(self) -> Self:
        if not self.role.strip():
            raise ValueError("role الإرساء لا يجوز فارغًا — سمِّ الدور الهندسي (مثل P1/NECKLINE)")
        return self


# ═══════════════════════ حمولتا أحداث §20 للأنماط ═══════════════════════


class CandlePatternEventPayload(_PatternsModel):
    """حمولة نمط شموعي — تخدم BULLISH_ENGULFING / BEARISH_ENGULFING /
    REJECTION_CANDLE / INSIDE_BAR_BREAK (§13.1 + §20) داخل المغلف (§32).

    «الأسماء مستعارات لتركيبات سمات»: ``feature_readings`` تحمل قراءات
    السمات الست القانونية (مفاتيح ``CANDLE_FEATURE_KEYS`` حصرًا) التي
    قرّرت العائلة — قيمها عند شمعة القرار (آخر شمعة من شموع النمط ما
    لم توثّق العائلة غير ذلك في هندستها). ``strength`` مقياس «لماذا
    يهم» العمودي في §20 (نسبة الجسم للابتلاع، نسبة الذيل للرفض،
    ضغط/توسع المدى للداخلية).
    """

    # حقول التمركز المشتركة — الشمعة التي أكّدت النمط (لا-نظرة §26.3)
    instrument: str
    timeframe: str
    bar_time: UTCDatetime

    family: CandlePatternFamily
    direction: PatternDirection
    #: قراءات السمات المكوِّنة — المستعار المُسمّى (§13.1).
    feature_readings: dict[str, float]
    strength: UnitInterval
    bars_in_pattern: PositiveInt

    @model_validator(mode="after")
    def _feature_keys_legal(self) -> Self:
        illegal = set(self.feature_readings) - CANDLE_FEATURE_KEYS
        if illegal:
            raise ValueError(
                f"مفاتيح سمات غير قانونية في feature_readings: {sorted(illegal)} — "
                f"المفاتيح القانونية حصرًا: {sorted(CANDLE_FEATURE_KEYS)} (§13.1)"
            )
        if not self.feature_readings:
            raise ValueError(
                "feature_readings فارغة — النمط الشموعي مستعار لتركيبة سمات "
                "(§13.1) فلا يصح نمط بلا قراءات سماته المكوِّنة"
            )
        return self


class ClassicalPatternEventPayload(_PatternsModel):
    """حمولة حدث البنية الكلاسيكية — تخدم CLASSICAL_BREAKOUT /
    CLASSICAL_FAILED_BREAKOUT (§13.2 + §20) بمخرجات §13.2 الثمانية
    حرفيًا بالأسماء نفسها.

    ``geometry`` قياسات رقمية مسماة (قرار الوحدة الموثق في رأس الموديول)
    مثل ``height_atr`` و``width_bars`` و``slope_per_bar``. للكسر الفاشل
    (§20: "Break + reclaim | Failure speed") يُستوفى ``reclaim_level``
    و``failure_speed`` (سرعة الاسترجاع: كسر ثم استرجاع خلال مدى أشرطة
    أقل) ويبقيان None للكسر الناجح — عقد الحمولة المشتركة نفسه الذي
    تتبعه ``StructureBreakPayload`` لثلاثة أنواع.
    """

    # حقول التمركز المشتركة — الشمعة التي أكّدت الكسر/فشله (لا-نظرة §26.3)
    instrument: str
    timeframe: str
    bar_time: UTCDatetime

    # ── مخرجات §13.2 الثمانية (الأسماء حرفيًا) ──
    pattern_type: ClassicalPatternType
    geometry: dict[str, float]
    anchor_points: tuple[AnchorPoint, ...]
    completion_time: UTCDatetime
    breakout_level: Price
    invalidation_level: Price
    measured_move: Price
    quality: UnitInterval

    # ── سياق الحدث ──
    break_direction: BreakDirection
    status: PatternStatus
    #: الكسر الفاشل حصرًا (§20) — مستوى الاسترجاع وسرعة الفشل؛ None للكسر الناجح.
    reclaim_level: Price | None = None
    failure_speed: FiniteFloat | None = None

    @model_validator(mode="after")
    def _anchors_and_failure_contract(self) -> Self:
        if not (2 <= len(self.anchor_points) <= 8):
            raise ValueError(
                f"anchor_points يجب أن تحمل 2..8 نقاط إرساء (§13.2 هندسات البُنى "
                f"الثماني) — وُجد {len(self.anchor_points)}"
            )
        if not self.geometry:
            raise ValueError(
                "geometry فارغة — النمط الكلاسيكي يلزمه قياس هندسي موثق واحد على الأقل (§13.2)"
            )
        if (self.reclaim_level is None) != (self.failure_speed is None):
            raise ValueError(
                "reclaim_level وfailure_speed زوج الفشل (§20 CLASSICAL_FAILED_BREAKOUT) "
                "— يحضران معًا أو يغيبان معًا"
            )
        return self
