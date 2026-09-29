"""مكتشف البُنى الكلاسيكية الثماني (§13.2) — المرشحات والكسر والفشل.

«الأنماط أوصاف مضغوطة لسلوك السعر لا تنبئات سحرية» (§13): كل بنية هنا
هندسة قابلة للقياس من قطوع محلية، وكل حدث يحمل مخرجات §13.2 الثمانية
حرفيًا في ``ClassicalPatternEventPayload`` (أسس 5-a). الحدثان القانونيان
حصرًا (قاموس §20): **CLASSICAL_BREAKOUT** عند إغلاق شمعة خارج مستوى كسر
بنية مكتملة، و**CLASSICAL_FAILED_BREAKOUT** عند استرجاع الكسر خلال مدى
أشرطة معلنة (زوج الفشل: ``reclaim_level`` + ``failure_speed``). النمط غير
المكسور **لا يُبث أبدًا** — لا نوع له في القاموس — والهندسة الغامضة تبقى
مرشحة ضعيفة (``status=CANDIDATE`` وجودة منخفضة) تساهم قليلًا أو لا تساهم
في الدمج (§13.2 حرفيًا) — والوزن مسؤولية fusion (§19) لا الكاشف.

القرار المعماري الملزم (worklog 5-a)
------------------------------------
عقد استقلال الكواشف (import-linter) **يمنع استيراد structure** —
القمم/القيعان هنا **قطوع هندسية محلية فورية** (:func:`find_pivots`
— fractal بنظرة خلفية ``k`` تؤكد عند مرور ``k`` شمعة) وليست swings
البنيوية المؤكدة المتأخرة (§11.1): وظيفيًا مختلفة — الهندسة الكلاسيكية
تحتاج قطوعًا فورية للبناء، والكاشف لا يستهلك متطرفات البنية إطلاقًا.

آلة الكشف (لا-نظرة §26.3 + حتمية + لا رفرفة §27)
--------------------------------------------------
:class:`ClassicalPatternDetector` تتابعية شمعة-بشمعة وكل قرار من الشمعة
الحالية والسواب حصرًا، والبث عند إقفال الشمعة الحاسمة. القطوع تُعاد
حسابها **صرفة** فوق نافذة خلفية (``window``) عند كل شمعة — لا حالة
تراكمية — فالحتمية بنيوية. المرشح النشط **واحد** لكل كاشف (قرار موثق:
أول بنية تكتمل تحتل الموضع بترتيب أولوية الرأس والكتفين ثم المزدوج ثم
الخطوط ثم العلم — لا تراكم يفسد الحتمية). دورته:

1. **بناء** من أحدث القطوع المؤكدة وفق هندسة كل بنية (أدناه).
2. **كسر**: إغلاق خارج ``breakout_level`` بهامش ``break_margin_ratio`` من
   ارتفاع النمط وبجهة النمط ⇒ بث CLASSICAL_BREAKOUT بمخرجات §13.2
   الثمانية وفتح نافذة تتبع الفشل. البُنى الخطية (مثلث/إسفين/قناة/
   نطاق) ثنائية الجهة: الجهة تُحسم عند الكسر نفسه.
3. **إبطال صامت موثق**: إغلاق يتجاوز ``invalidation_level`` بلا كسر
   قانوني ⇒ إسقاط بلا بث — لا نوع للإبطال في قاموس §20.
4. **فشل الكسر** (§20 «Break + reclaim | Failure speed»): خلال
   ``failure_max_bars`` من الكسر، إغلاق يعود داخل حدود النمط ⇒ بث
   CLASSICAL_FAILED_BREAKOUT مرة واحدة — ``reclaim_level`` حد
   الاسترجاع و``failure_speed`` عدد أشرطة الكسر-حتى-الاسترجاع (كلما
   قلَّت كان الفشل أبلغ) — ثم التصفية النهائية.

هندسات البُنى الثماني (كل الحدود نسب — لا ثوابت مطلقة)
--------------------------------------------------------
- **قمة/قاع مزدوج** (آخر ثلاث قطوع H-L-H / L-H-L): الطرفان متطابقان
  ضمن ``double_tolerance`` من ارتفاع النمط والرقبة البينية أعمق من
  ``min_neck_depth`` منه. breakout=الرقبة، invalidation=أقصى الطرفين،
  measured=الرقبة±الارتفاع.
- **رأس وكتفان / معكوسه** (خمس قطوع H-L-H-L-H / L-H-L-H-L): الرأس
  يبرز فوق أعلى كتف بمقدار ``min_head_prominence`` من الارتفاع
  والكتفان متقاربان ضمن ``shoulder_tolerance``. breakout=أدنى نقطتي
  الرقبة (تحفظ موثق)، invalidation=الرأس، measured=الرقبة∓(الرأس−الرقبة).
- **الخطوط الرباعية — مثلث/إسفين/قناة/نطاق** (أربع قطوع متناوبة تصنع
  خط قمم وخط قيعان): التصنيف بميلَي الخطين — مختلفا الإشارة ⇒
  **مثلث**؛ بنفس الإشارة مع تقارب ⇒ **إسفين**؛ بنفس الإشارة ومتقارب
  النسبة (≤ ``channel_parallel_tolerance``) ⇒ **قناة**؛ شبه أفقيين
  (|الميل|/السعر ≤ ``flat_slope_max``) ⇒ **نطاق**. الكسر عبر امتداد
  الخط المستقرَأ خطيًا إلى الشمعة الحالية (فوق العلوي صعودًا/تحت
  السفلي هبوطًا) وinvalidation الخط المقابل وmeasured عرض البنية
  بجهة الكسر.
- **العلم** (عمود + تجميع): حركة ``pole_min_bars``.. شموع بامتداد ≥
  ``pole_min_range_ratio`` من متوسط مدى ``reference_window`` ثم تجميع
  آخر ``flag_max_bars`` شموع بمدى ≤ ``flag_max_narrow_ratio`` من
  ارتفاع العمود. breakout=حد التجميع الجهوي، invalidation=المقابل،
  measured=الحد±ارتفاع العمود.

الجودة نقاء هندسي مطبَّع [0,1] لكل بنية؛ ``quality ≥
confirmed_quality_min`` ⇒ CONFIRMED وإلا CANDIDATE (الغامض يُبث إن
انكسر ووزنه شأن الدمج §19).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from schemas import (
    AnchorPoint,
    BreakDirection,
    Candle,
    ClassicalPatternEventPayload,
    ClassicalPatternType,
    EventType,
    PatternStatus,
)

__all__ = [
    "ClassicalConfig",
    "ClassicalPatternDetector",
    "EmittedEvent",
    "Pivot",
    "PivotKind",
    "find_pivots",
]


# ═══════════════════════ الإعداد ═══════════════════════


@dataclass(frozen=True)
class ClassicalConfig:
    """إعداد البُنى الكلاسيكية — نسب موثقة (لا ثوابت مطلقة)."""

    #: قوة fractal للقطوع المحلية: قمة أعلى من k قبلها وk بعدها (≥ 1).
    pivot_strength: int = 2
    #: نافذة الرصد الخلفية (شمعة) — تُعاد فوقها حسبة القطوع الصرفة.
    window: int = 120
    #: أقصى تفاوت طرفي القمة/القاع المزدوجين نسبةً إلى ارتفاع النمط.
    double_tolerance: float = 0.10
    #: أدنى عمق الرقبة نسبةً إلى ارتفاع النمط (المزدوج).
    min_neck_depth: float = 0.25
    #: أدنى بروز الرأس فوق أعلى كتف نسبةً إلى ارتفاع النمط.
    min_head_prominence: float = 0.10
    #: أقصى تفاوت الكتفين نسبةً إلى ارتفاع النمط.
    shoulder_tolerance: float = 0.30
    #: أقصى ميل نسبي (|الميل|/السعر) يعد معه الخط أُفقيًا.
    flat_slope_max: float = 0.002
    #: أقصى فرق النسبة المئوية بين تقاربَي الخطين للموازاة (القناة).
    channel_parallel_tolerance: float = 0.20
    #: أدنى امتداد العمود نسبةً إلى متوسط مدى نافذة المرجع.
    pole_min_range_ratio: float = 3.0
    #: أدنى عدد شموع العمود.
    pole_min_bars: int = 2
    #: أقصى عدد شموع تجميع العلم.
    flag_max_bars: int = 8
    #: أقصى مدى للتجميع نسبةً إلى ارتفاع العمود.
    flag_max_narrow_ratio: float = 0.50
    #: نافذة متوسط المدى المرجعي لقوة العمود.
    reference_window: int = 20
    #: أقصى أشرطة نافذة فشل الكسر (سقف «Failure speed» §20).
    failure_max_bars: int = 8
    #: عتبة الجودة الفاصلة بين CONFIRMED وCANDIDATE (§13.2).
    confirmed_quality_min: float = 0.60
    #: هامش كسر إغلاقي نسبةً إلى ارتفاع النمط (كسر حاسم لا ملامسة).
    break_margin_ratio: float = 0.02

    def __post_init__(self) -> None:
        if self.pivot_strength < 1:
            raise ValueError(f"pivot_strength ≥ 1 حصرًا؛ وُجد {self.pivot_strength}")
        for name in (
            "double_tolerance",
            "min_neck_depth",
            "min_head_prominence",
            "shoulder_tolerance",
            "flag_max_narrow_ratio",
            "confirmed_quality_min",
            "break_margin_ratio",
        ):
            value = getattr(self, name)
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} نسبة صارمة من (0, 1)؛ وُجد {value}")
        if self.pole_min_range_ratio <= 1.0:
            raise ValueError("pole_min_range_ratio > 1 حصرًا (عمود أقوى من المدى العادي)")
        if self.pole_min_bars < 1:
            raise ValueError("pole_min_bars ≥ 1 حصرًا")
        if self.flag_max_bars < 2:
            raise ValueError("flag_max_bars ≥ 2 حصرًا")
        if self.failure_max_bars < 1:
            raise ValueError("failure_max_bars ≥ 1 حصرًا")
        if self.reference_window < 2:
            raise ValueError("reference_window ≥ 2 حصرًا")
        if self.flat_slope_max <= 0.0 or self.channel_parallel_tolerance <= 0.0:
            raise ValueError("flat_slope_max وchannel_parallel_tolerance موجبان حصرًا")


# ═══════════════════════ القطوع المحلية ═══════════════════════


class PivotKind(StrEnum):
    """نوع القطع المحلي — قمة أو قاع."""

    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class Pivot:
    """قطع هندسي محلي (fractal خلفي) — ليس متطرفًا بنيويًا (§11.1)."""

    index: int  # فهرس الشمعة داخل مدخلات الكاشف التراكمية
    bar_time: datetime
    price: float
    kind: PivotKind


def find_pivots(candles: list[Candle], k: int) -> list[Pivot]:
    """القطوع المحلية المؤكدة — fractal بقوة خلفية، دالة صرفة حتمية.

    القمة عند ``i`` تؤكد بعد وصول ``k`` شمعة بعدها (مقارنة صارمة ``k``
    قبلها و``k`` بعدها) — كل معلومة متاحة لحظة التأكيد (لا-نظرة §26.3).
    تعاقب صارم: متتاليان بنفس النوع يبقى أقصاهما — الخرج متناوب
    HIGH/LOW دائمًا بترتيب فهرسي تصاعدي.
    """
    n = len(candles)
    raw: list[Pivot] = []
    for i in range(k, n - k):
        candidate = candles[i]
        is_high = all(candidate.high > candles[j].high for j in range(i - k, i + k + 1) if j != i)
        is_low = all(candidate.low < candles[j].low for j in range(i - k, i + k + 1) if j != i)
        if is_high:
            raw.append(Pivot(i, candidate.bar_time, candidate.high, PivotKind.HIGH))
        elif is_low:
            raw.append(Pivot(i, candidate.bar_time, candidate.low, PivotKind.LOW))
    pivots: list[Pivot] = []
    for pivot in raw:
        if pivots and pivots[-1].kind is pivot.kind:
            previous = pivots[-1]
            keep_new = (
                pivot.price > previous.price
                if pivot.kind is PivotKind.HIGH
                else pivot.price < previous.price
            )
            if keep_new:
                pivots[-1] = pivot
        else:
            pivots.append(pivot)
    return pivots


# ═══════════════════════ السجل المبثوث ═══════════════════════


@dataclass(frozen=True)
class EmittedEvent:
    """حدث بنية كلاسيكية — خرج الكاشف ومدخل مجمّع المغلف (نمط §32)."""

    event_type: EventType
    event_time: datetime
    payload: ClassicalPatternEventPayload


# ═══════════════════════ المرشح الداخلي ═══════════════════════


@dataclass(frozen=True)
class _Line:
    """خط هندسي من قطعين — ميل نسبي واستقراء إلى فهرس لاحق."""

    i1: int
    p1: float
    i2: int
    p2: float

    def value_at(self, index: int) -> float:
        """قيمة الخط المُستقرأة عند فهرس — خطي من نقطتيه."""
        if self.i2 == self.i1:
            return self.p2
        slope = (self.p2 - self.p1) / (self.i2 - self.i1)
        return self.p2 + slope * (index - self.i2)

    @property
    def slope(self) -> float:
        if self.i2 == self.i1:
            return 0.0
        return (self.p2 - self.p1) / (self.i2 - self.i1)


@dataclass(frozen=True)
class _Candidate:
    """مرشح بنية مكتمل غير مكسور — كائن داخلي لا يُبث أبدًا."""

    pattern_type: ClassicalPatternType
    #: جهة الكسر المتوقعة؛ None للبُنى الخطية ثنائية الجهة (تُحسم عند الكسر).
    direction: BreakDirection | None
    breakout_level: float
    invalidation_level: float
    measured_move: float
    anchors: tuple[AnchorPoint, ...]
    quality: float
    geometry: dict[str, float]
    #: ارتفاع النمط المرجعي لهامش الكسر (سعرًا مطلقًا).
    height: float
    #: فهرس آخر شمعة عند البناء — مرجع إزاحة استقراء الخطوط بعد النمو.
    built_at: int
    #: للبُنى الخطية: الخطان العلوي والسفلي للاستقراء والكسر الجهوي.
    upper_line: _Line | None = None
    lower_line: _Line | None = None


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _try_double(pivots: list[Pivot], cfg: ClassicalConfig) -> _Candidate | None:
    """القمة/القاع المزدوج — آخر ثلاث قطوع متناوبة بنهاية كتلة الطرفين."""
    if len(pivots) < 3:
        return None
    side1, neck, side2 = pivots[-3], pivots[-2], pivots[-1]
    if side1.kind is not side2.kind or neck.kind is side1.kind:
        return None
    height = abs(side1.price - neck.price)
    if height <= 0.0:
        return None
    if neck.price <= 0.0:
        return None
    # عمق الرقبة نسبةً إلى الارتفاع: البنية ذات معنى فقط برقبة وافرة
    if height / max(side1.price, side2.price) < cfg.min_neck_depth * 0.5:
        return None
    mismatch = abs(side1.price - side2.price) / height
    if mismatch > cfg.double_tolerance:
        return None
    is_top = side1.kind is PivotKind.HIGH
    pattern = ClassicalPatternType.DOUBLE_TOP if is_top else ClassicalPatternType.DOUBLE_BOTTOM
    direction = BreakDirection.DOWN if is_top else BreakDirection.UP
    breakout = neck.price
    if is_top:
        invalidation = max(side1.price, side2.price)
        measured = breakout - (invalidation - breakout)
    else:
        invalidation = min(side1.price, side2.price)
        measured = breakout + (breakout - invalidation)
    roles = (
        ("P1_PEAK", "P2_NECKLINE", "P3_PEAK")
        if is_top
        else ("P1_TROUGH", "P2_NECKLINE", "P3_TROUGH")
    )
    anchors = (
        AnchorPoint(time=side1.bar_time, price=side1.price, role=roles[0]),
        AnchorPoint(time=neck.bar_time, price=neck.price, role=roles[1]),
        AnchorPoint(time=side2.bar_time, price=side2.price, role=roles[2]),
    )
    # الجودة: تطابق الطرفين (الأغلب) + عمق الرقبة النسبي المطبَّع
    match_score = 1.0 - mismatch / cfg.double_tolerance
    neck_score = _clamp01(height / abs(invalidation - breakout) / 2.0)
    quality = _clamp01(0.6 * match_score + 0.4 * neck_score)
    return _Candidate(
        pattern_type=pattern,
        direction=direction,
        breakout_level=breakout,
        invalidation_level=invalidation,
        measured_move=measured,
        anchors=anchors,
        quality=quality,
        geometry={
            "height": height,
            "mismatch_ratio": mismatch,
            "neck_depth_ratio": _clamp01(height / abs(invalidation - breakout) / 2.0),
            "width_bars": float(side2.index - side1.index),
        },
        height=height,
        built_at=0,
    )


def _try_hs(pivots: list[Pivot], cfg: ClassicalConfig) -> _Candidate | None:
    """الرأس والكتفان/معكوسه — خمس قطوع ببروز رأس وتقارب كتفين."""
    if len(pivots) < 5:
        return None
    s1, n1, head, n2, s2 = pivots[-5], pivots[-4], pivots[-3], pivots[-2], pivots[-1]
    # تعاقب القطوع المتناوب (مضمون من find_pivots) يجعل الأنماط
    # H L H L H (علوي) أو L H L H L (سفلي) حصراً — لا فحص أنواع إضافياً:
    # الكتفان والرأس بنفس النوع بالضرورة، والبروز هو المفحوض أدناه.
    _ = (s1, n1, head, n2, s2)
    top_side = s1.kind is PivotKind.HIGH
    # المدى الكامل للأعلى: رأس − أدنى رقبة؛ وللسفلي: أعلى رقبة − رأس.
    height = max(head.price, n1.price, n2.price) - min(head.price, n1.price, n2.price)
    if height <= 0.0:
        return None
    shoulders_mismatch = abs(s1.price - s2.price) / height
    if shoulders_mismatch > cfg.shoulder_tolerance:
        return None
    if top_side:
        prominence = (head.price - max(s1.price, s2.price)) / height
    else:
        prominence = (min(s1.price, s2.price) - head.price) / height
    if prominence < cfg.min_head_prominence:
        return None
    pattern = (
        ClassicalPatternType.HEAD_AND_SHOULDERS
        if top_side
        else ClassicalPatternType.INVERSE_HEAD_AND_SHOULDERS
    )
    direction = BreakDirection.DOWN if top_side else BreakDirection.UP
    breakout = min(n1.price, n2.price) if top_side else max(n1.price, n2.price)
    if top_side:
        invalidation = head.price
        measured = breakout - (invalidation - breakout)
    else:
        invalidation = head.price
        measured = breakout + (breakout - invalidation)
    roles = (
        "LEFT_SHOULDER",
        "NECKLINE_LEFT",
        "HEAD",
        "NECKLINE_RIGHT",
        "RIGHT_SHOULDER",
    )
    anchors = tuple(
        AnchorPoint(time=p.bar_time, price=p.price, role=role)
        for p, role in zip((s1, n1, head, n2, s2), roles, strict=True)
    )
    # الجودة: بروز الرأس + تقارب الكتفين
    quality = _clamp01(
        0.6 * _clamp01(prominence / (2.0 * cfg.min_head_prominence))
        + 0.4 * (1.0 - shoulders_mismatch / cfg.shoulder_tolerance)
    )
    return _Candidate(
        pattern_type=pattern,
        direction=direction,
        breakout_level=breakout,
        invalidation_level=invalidation,
        measured_move=measured,
        anchors=anchors,
        quality=quality,
        geometry={
            "height": height,
            "head_prominence": prominence,
            "shoulders_mismatch": shoulders_mismatch,
            "neckline_gap": abs(n1.price - n2.price) / height,
            "width_bars": float(s2.index - s1.index),
        },
        height=height,
        built_at=0,
    )


def _try_lines(pivots: list[Pivot], cfg: ClassicalConfig) -> _Candidate | None:
    """البُنى الخطية الرباعية — مثلث/إسفين/قناة/نطاق من أربع قطوع متناوبة."""
    if len(pivots) < 4:
        return None
    p1, p2, p3, p4 = pivots[-4], pivots[-3], pivots[-2], pivots[-1]
    # تعاقب متناوب (مضمون من find_pivots): p1/p3 بنفس النوع وp2/p4
    # بالمعاكس — الخط العلوي من زوج القمم والسفلي من زوج القيعان.
    if p1.kind is PivotKind.HIGH:
        upper = _Line(p1.index, p1.price, p3.index, p3.price)
        lower = _Line(p2.index, p2.price, p4.index, p4.price)
    else:
        upper = _Line(p2.index, p2.price, p4.index, p4.price)
        lower = _Line(p1.index, p1.price, p3.index, p3.price)
    mid_price = (p1.price + p2.price + p3.price + p4.price) / 4.0
    if mid_price <= 0.0:
        return None
    upper_slope_rel = upper.slope / mid_price
    lower_slope_rel = lower.slope / mid_price
    width = abs(upper.value_at(p4.index) - lower.value_at(p4.index))
    if width <= 0.0:
        return None
    if abs(upper_slope_rel) <= cfg.flat_slope_max and abs(lower_slope_rel) <= cfg.flat_slope_max:
        pattern = ClassicalPatternType.RANGE_BREAKOUT
    elif upper_slope_rel * lower_slope_rel < 0.0:
        pattern = ClassicalPatternType.TRIANGLE
    else:
        # نفس الإشارة: تقارب ⇒ إسفين، توازٍ ⇒ قناة
        convergence = (upper_slope_rel - lower_slope_rel) / max(
            abs(upper_slope_rel), abs(lower_slope_rel), 1e-12
        )
        if abs(convergence) > cfg.channel_parallel_tolerance:
            pattern = ClassicalPatternType.WEDGE
        else:
            pattern = ClassicalPatternType.CHANNEL
    roles = ("P1", "P2", "P3", "P4")
    anchors = tuple(
        AnchorPoint(time=p.bar_time, price=p.price, role=role)
        for p, role in zip((p1, p2, p3, p4), roles, strict=True)
    )
    # الجودة: انتظام الأضلاع — فرق عرض البنية بين طرفيها مطبَّعًا
    width_start = abs(upper.value_at(p1.index) - lower.value_at(p1.index))
    if width_start <= 0.0:
        return None
    narrowing = width / width_start
    regularity = _clamp01(1.0 - abs(narrowing - 1.0))
    quality = _clamp01(0.5 * regularity + 0.5 * _clamp01(width / (2.0 * width_start) + 0.5))
    return _Candidate(
        pattern_type=pattern,
        direction=None,  # ثنائية الجهة — تُحسم عند الكسر
        breakout_level=0.0,  # الخطوط تحدد المستوى عند الفحص الجهوي
        invalidation_level=0.0,
        measured_move=0.0,
        anchors=anchors,
        quality=quality,
        geometry={
            "upper_slope_rel": upper_slope_rel,
            "lower_slope_rel": lower_slope_rel,
            "width": width,
            "width_start": width_start,
            "narrowing_ratio": narrowing,
            "width_bars": float(p4.index - p1.index),
        },
        height=width,
        built_at=0,
        upper_line=upper,
        lower_line=lower,
    )


def _try_flag(candles: list[Candle], cfg: ClassicalConfig) -> _Candidate | None:
    """العلم — عمود قوي فتجيمع ضيق (دالة صرفة على نهاية النافذة)."""
    n = len(candles)
    if n < cfg.reference_window + cfg.pole_min_bars + 2:
        return None
    # متوسط مدى المرجع (نافذة خلفية قبل منطقة العمود المحتملة)
    ref = candles[-(cfg.flag_max_bars + cfg.reference_window) : -cfg.flag_max_bars]
    if len(ref) < cfg.reference_window // 2:
        return None
    mean_range = sum(c.high - c.low for c in ref) / len(ref)
    if mean_range <= 0.0:
        return None
    # التجميع: آخر flag_max_bars شمعة
    flag_zone = candles[-cfg.flag_max_bars :]
    flag_high = max(c.high for c in flag_zone)
    flag_low = min(c.low for c in flag_zone)
    flag_range = flag_high - flag_low
    # العمود: الحركة المفاجئة حصرًا — آخر pole_min_bars شمعة قبل التجميع
    # (قرار موثق: لا يُقاس من قاع النافذة كلها، فالصعود البطيء السابق
    # ليس جزءًا من الاندفاع)
    pole_zone = candles[-(cfg.flag_max_bars + cfg.pole_min_bars) : -cfg.flag_max_bars]
    if len(pole_zone) < cfg.pole_min_bars:
        return None
    pole_start = min(c.low for c in pole_zone)
    pole_end = max(c.high for c in pole_zone)
    pole_height = pole_end - pole_start
    if pole_height < cfg.pole_min_range_ratio * mean_range:
        return None
    if pole_height <= 0.0:
        return None
    if flag_range > cfg.flag_max_narrow_ratio * pole_height:
        return None
    # العلم الصاعد: كسر فوق قمة التجميع؛ الهابط: تحت قاعه
    anchors = (
        AnchorPoint(time=pole_zone[0].bar_time, price=pole_start, role="POLE_BASE"),
        AnchorPoint(time=pole_zone[-1].bar_time, price=pole_end, role="POLE_TOP"),
        AnchorPoint(time=flag_zone[0].bar_time, price=flag_high, role="FLAG_HIGH"),
        AnchorPoint(time=flag_zone[-1].bar_time, price=flag_low, role="FLAG_LOW"),
    )
    quality = _clamp01(
        0.5 * _clamp01(pole_height / (cfg.pole_min_range_ratio * mean_range) / 2.0)
        + 0.5 * (1.0 - flag_range / (cfg.flag_max_narrow_ratio * pole_height))
    )
    return _Candidate(
        pattern_type=ClassicalPatternType.FLAG,
        direction=None,  # جهة العمود تحدد عند الكسر (فوق التجميع صعودًا)
        breakout_level=0.0,
        invalidation_level=0.0,
        measured_move=0.0,
        anchors=anchors,
        quality=quality,
        geometry={
            "pole_height": pole_height,
            "flag_range": flag_range,
            "narrow_ratio": flag_range / pole_height,
            "pole_strength": pole_height / mean_range,
            "width_bars": float(cfg.flag_max_bars),
        },
        height=pole_height,
        built_at=0,
        upper_line=_Line(0, flag_high, 1, flag_high),
        lower_line=_Line(0, flag_low, 1, flag_low),
    )


# ═══════════════════════ الكاشف ═══════════════════════


@dataclass
class _BreakState:
    """حالة كسر نشط يُتتبَّص فشله — بنية لا-رفرفة.

    ``bars_since_break`` عدّاد أشرطة منذ الكسر (0 عند البث) — بلا فهارس
    مطلقة تفسدها قصة النافذة؛ ``failure_speed`` = قيمته لحظة الاسترجاع.
    """

    candidate: _Candidate
    direction: BreakDirection
    breakout_level: float
    invalidation_level: float
    measured_move: float
    bars_since_break: int = 0


class ClassicalPatternDetector:
    """كاشف البُنى الكلاسيكية لكل (أداة، إطار) — شموع مغلقة فقط.

    الاستخدام: أنشئ كاشفًا وغذّه الشموع المغلقة بترتيبها؛
    ``on_candle`` يعيد حدث هذه الشمعة (صفر أو واحد — الكسر ثم فشله
    كلاهما مرة واحدة لكل مرشح). الحتمية بنيوية: كل القرارات دوال صرفة
    للنافذة الخلفية والمرشح النشط.

    **بصمتا البناء** (قرار لا-رفرفة §27 موثق): الأنماط القطعية (رأس
    وكتفان/مزدوج/خطوط) لا تُعاد بنيتها إلا بتغير بصمة القطوع المؤكدة
    (‎bar_time/النوع/السعر‎ — مستقرة عبر قص النافذة) عن بصمة آخر بناء
    قطعي ناجح؛ فلا إعادة بناء لنمط مكسور أو مبطل بقطوعه القديمة. العلم
    زمني البناء (عمود+تجميع لا قطوع فيه غالبًا) فيعاد فحصه كل شمعة
    بلا مرشح حي، بمنع تكرار علم بنطاق تجميعه نفسه ببصمة خاصة.
    """

    def __init__(
        self,
        config: ClassicalConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        if (instrument_id is None) != (timeframe is None):
            raise ValueError("الهوية تُمرَّر كاملة (أداة وإطار معًا) أو تُترك لتُلتقط من أول شمعة")
        self._config = config if config is not None else ClassicalConfig()
        self._instrument_id = instrument_id
        self._timeframe = timeframe
        self._candles: list[Candle] = []
        self._last_bar_time: datetime | None = None
        self._candidate: _Candidate | None = None
        self._candidate_dead: bool = False
        self._break: _BreakState | None = None
        #: بصمة القطوع لآخر بناء قطعي ناجح — تمنع إعادة بناء النمط نفسه
        #: بعد كسره/إبطاله ما لم تؤكد قطوع جديدة (لا-رفرفة §27).
        self._built_pivot_sig: tuple[tuple[datetime, str, float], ...] | None = None
        #: بصمة آخر علم مبنى (نطاق تجميعه) — تمنع إعادة بناء العلم نفسه.
        self._built_flag_sig: tuple[datetime, datetime, float, float] | None = None

    @property
    def config(self) -> ClassicalConfig:
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

    def on_candle(self, candle: Candle) -> tuple[EmittedEvent, ...]:
        """استهلاك شمعة مغلقة — صفر أو حدث واحد لهذه الشمعة."""
        self._guard(candle)
        self._candles.append(candle)
        if len(self._candles) > self._config.window:
            del self._candles[: len(self._candles) - self._config.window]
        # 1) تتبع فشل كسر نشط أولًا (أولوية الحدث الأحدث §20) —
        #    العدّاد يزيد قبل الفحص: سرعة الفشل = عدد الأشرطة منذ الكسر
        #    شاملةً شمعة الاسترجاع (كسر في b واسترجاع في b+k ⇒ سرعة k).
        if self._break is not None:
            self._break.bars_since_break += 1
            failure = self._check_failure()
            if failure is not None:
                self._break = None
                return (failure,)
            if self._break.bars_since_break >= self._config.failure_max_bars:
                self._break = None  # نافذة الفشل انقضت — كسر ناجح نهائيًا
            return ()
        # 2) فحص كسر المرشح النشط — وإن مات بهذه الشمعة (تجاوز حد البطلان)
        #    يُستأنف البناء فورًا بالشمعة نفسها (كل معلومة الهندسة البديلة
        #    متاحة: قطوعها مؤكدة قبلها والكسر بالإغلاق الحالي).
        if self._candidate is not None and not self._candidate_dead:
            event = self._check_break()
            if event is not None:
                return (event,)
            if not self._candidate_dead:
                return ()
        # 3) بناء مرشح جديد (لا-رفرفة §27):
        #    الأنماط القطعية فقط عند تغير بصمة القطوع عن آخر بناء قطعي
        #    ناجح (فلا إعادة لنمط مكسور بقطوعه القديمة)، والعلم الزمني
        #    يُعاد فحصه كل شمعة بلا مرشح — بمنع تكرار علم بنطاقه نفسه.
        pivots = find_pivots(self._candles, self._config.pivot_strength)
        pivots_sig = tuple((p.bar_time, p.kind.value, p.price) for p in pivots)
        candidate: _Candidate | None = None
        if pivots_sig != self._built_pivot_sig:
            candidate = self._build_pivot_candidate(pivots)
            if candidate is not None:
                self._built_pivot_sig = pivots_sig
        if candidate is None:
            flag = _try_flag(self._candles, self._config)
            if flag is not None:
                flag_sig = self._flag_signature(flag)
                if flag_sig != self._built_flag_sig:
                    candidate = flag
                    self._built_flag_sig = flag_sig
        if candidate is not None:
            self._candidate = replace(candidate, built_at=len(self._candles) - 1)
            self._candidate_dead = False
            # المرشح الجديد قد ينكسر بهذه الشمعة نفسها
            event = self._check_break()
            if event is not None:
                return (event,)
        return ()

    def on_candles(self, candles: list[Candle]) -> tuple[EmittedEvent, ...]:
        """تغذية دفعة — مطابقة تمامًا للتغذية شمعة-بشمعة (حتمية)."""
        events: list[EmittedEvent] = []
        for candle in candles:
            events.extend(self.on_candle(candle))
        return tuple(events)

    # ── الداخلية ──

    def _build_pivot_candidate(self, pivots: list[Pivot]) -> _Candidate | None:
        """بناء مرشح قطعي بترتيب الأولوية (رأس وكتفان ← مزدوج ← خطوط)."""
        for builder in (_try_hs, _try_double):
            candidate = builder(pivots, self._config)
            if candidate is not None:
                return candidate
        return _try_lines(pivots, self._config)

    @staticmethod
    def _flag_signature(flag: _Candidate) -> tuple[datetime, datetime, float, float]:
        """بصمة العلم — نطاق تجميعه الزمني والسعري (تمنع إعادة بنائه)."""
        anchors = flag.anchors
        return (
            anchors[2].time,
            anchors[3].time,
            anchors[2].price,
            anchors[3].price,
        )

    def _check_break(self) -> EmittedEvent | None:
        """فحص كسر المرشح النشط عند الشمعة الحالية — بث أو إبطال صامت."""
        candidate = self._candidate
        assert candidate is not None
        candle = self._candles[-1]
        margin = self._config.break_margin_ratio * candidate.height
        if candidate.direction is not None:
            # بنية أحادية الجهة: المزدوج والرأس والكتفان
            if candidate.direction is BreakDirection.DOWN:
                if candle.close < candidate.breakout_level - margin:
                    return self._emit_break(
                        candidate, BreakDirection.DOWN, candidate.breakout_level
                    )
                if candle.close > candidate.invalidation_level:
                    self._candidate_dead = True
                return None
            if candle.close > candidate.breakout_level + margin:
                return self._emit_break(candidate, BreakDirection.UP, candidate.breakout_level)
            if candle.close < candidate.invalidation_level:
                self._candidate_dead = True
            return None
        # بنية خطية ثنائية الجهة — امتداد الخطوط بإزاحة الأشرطة منذ البناء
        upper = candidate.upper_line
        lower = candidate.lower_line
        assert upper is not None and lower is not None
        elapsed = (len(self._candles) - 1) - candidate.built_at
        upper_now = upper.value_at(upper.i2 + elapsed)
        lower_now = lower.value_at(lower.i2 + elapsed)
        # الهدف المقاس: عرض البنية للخطيات؛ ارتفاع العمود للعلم (§13.2)
        extension = (
            candidate.height
            if candidate.pattern_type is ClassicalPatternType.FLAG
            else abs(upper_now - lower_now)
        )
        if candle.close > upper_now + margin:
            return self._emit_break(
                candidate,
                BreakDirection.UP,
                upper_now,
                measured_override=upper_now + extension,
                invalidation_override=lower_now,
            )
        if candle.close < lower_now - margin:
            return self._emit_break(
                candidate,
                BreakDirection.DOWN,
                lower_now,
                measured_override=lower_now - extension,
                invalidation_override=upper_now,
            )
        return None

    def _check_failure(self) -> EmittedEvent | None:
        """فحص استرجاع كسر نشط خلال نافذة الفشل — بث CLASSICAL_FAILED_BREAKOUT."""
        state = self._break
        assert state is not None
        candle = self._candles[-1]
        if state.direction is BreakDirection.UP and candle.close < state.breakout_level:
            return self._emit_failure(state)
        if state.direction is BreakDirection.DOWN and candle.close > state.breakout_level:
            return self._emit_failure(state)
        return None

    def _emit_break(
        self,
        candidate: _Candidate,
        direction: BreakDirection,
        breakout_level: float,
        measured_override: float | None = None,
        invalidation_override: float | None = None,
    ) -> EmittedEvent:
        """بث كسر مؤكد وفتح نافذة تتبع الفشل."""
        measured = measured_override if measured_override is not None else candidate.measured_move
        invalidation = (
            invalidation_override
            if invalidation_override is not None
            else candidate.invalidation_level
        )
        payload = ClassicalPatternEventPayload(
            instrument=self._instrument_id or "",
            timeframe=self._timeframe or "",
            bar_time=self._candles[-1].bar_time,
            pattern_type=candidate.pattern_type,
            geometry=dict(candidate.geometry),
            anchor_points=candidate.anchors,
            completion_time=self._candles[-1].bar_time,
            breakout_level=breakout_level,
            invalidation_level=invalidation,
            measured_move=measured,
            quality=candidate.quality,
            break_direction=direction,
            status=(
                PatternStatus.CONFIRMED
                if candidate.quality >= self._config.confirmed_quality_min
                else PatternStatus.CANDIDATE
            ),
        )
        self._break = _BreakState(
            candidate=candidate,
            direction=direction,
            breakout_level=breakout_level,
            invalidation_level=invalidation,
            measured_move=measured,
        )
        self._candidate = None
        self._candidate_dead = False
        return EmittedEvent(
            event_type=EventType.CLASSICAL_BREAKOUT,
            event_time=self._candles[-1].bar_time,
            payload=payload,
        )

    def _emit_failure(self, state: _BreakState) -> EmittedEvent:
        """بث فشل الكسر — الاسترجاع خلال النافذة (§20)."""
        candidate = state.candidate
        payload = ClassicalPatternEventPayload(
            instrument=self._instrument_id or "",
            timeframe=self._timeframe or "",
            bar_time=self._candles[-1].bar_time,
            pattern_type=candidate.pattern_type,
            geometry=dict(candidate.geometry),
            anchor_points=candidate.anchors,
            completion_time=self._candles[-1].bar_time,
            breakout_level=state.breakout_level,
            invalidation_level=state.invalidation_level,
            measured_move=state.measured_move,
            quality=candidate.quality,
            break_direction=state.direction,
            status=(
                PatternStatus.CONFIRMED
                if candidate.quality >= self._config.confirmed_quality_min
                else PatternStatus.CANDIDATE
            ),
            reclaim_level=self._candles[-1].close,
            failure_speed=float(state.bars_since_break),
        )
        return EmittedEvent(
            event_type=EventType.CLASSICAL_FAILED_BREAKOUT,
            event_time=self._candles[-1].bar_time,
            payload=payload,
        )

    def _guard(self, candle: Candle) -> None:
        """حارس التدفق — إقفال وهوية وترتيب (نمط كواشف المراحل 3/4)."""
        if not candle.is_closed:
            raise ValueError("الكاشف يستهلك الشموع المغلقة فقط (§27)")
        if self._instrument_id is None:
            self._instrument_id = candle.instrument_id
            self._timeframe = candle.timeframe
        else:
            expected_instrument = self._instrument_id
            expected_timeframe = self._timeframe
            assert expected_timeframe is not None
            if candle.instrument_id != expected_instrument:
                raise ValueError(
                    f"خلط أدوات على كاشف واحد: {expected_instrument!r} ثم {candle.instrument_id!r}"
                )
            if candle.timeframe != expected_timeframe:
                raise ValueError(f"خلط أطر زمنية: {expected_timeframe!r} ثم {candle.timeframe!r}")
        last = self._last_bar_time
        if last is not None:
            if candle.bar_time == last:
                raise ValueError(f"تكرار bar_time: {candle.bar_time}")
            if candle.bar_time < last:
                raise ValueError(f"شمعة متأخرة: {candle.bar_time} بعد {last}")
        self._last_bar_time = candle.bar_time
