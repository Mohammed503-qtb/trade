"""المشغلات القابلة للرصد (7.3 + §18.4) — آلات حالة شريطية حتمية.

«A scenario may become TRIGGERED only when its defined trigger is
observed» (§18.4) — المشغل يعرَّف هيكليًا (``TriggerDefinition``:
condition_type + params) ويُرصد فعليًا على شموع إطار التنفيذ المغلقة
وأحداث البنية المؤكدة، لا بجملة نثرية.

الأنواع الخمسة المعدودة (كلها من مدخلات قابلة للرصد فقط — لا-نظرة
§26.3: إغلاقات وأحداث شمعة مقفلة):

- **DISPLACEMENT_CONFIRM** (انعكاس §21.2): حدث إزاحة §11.4 باتجاه
  السيناريو على إطار التنفيذ — «execution-timeframe displacement»
  (مثال §18.3 حرفيًا).
- **INTERNAL_BOS** (استمرار §21.2): كسر بنية داخلية §11.2 باتجاه
  السيناريو — «internal BOS/displacement».
- **ACCEPTANCE_BEYOND** (اختراق من اجتياح): ``window`` إغلاقات متتالية
  خلف ``level`` بجهة الاختراق — القبول عدُّ إغلاقات لا فتيلًا واحدًا
  (روح §10.4).
- **RETEST_HOLD** (اختراق من كسر-قبول): لمسُ نطاق حول الحافة ثم إغلاق
  صامد في جهة الاختراق — «retest/continuation» (§21.2).
- **ZONE_RECLAIM** (انعكاس من كسر-قبول): إغلاق كامل خلف مستوى
  الاسترجاع — فشل القبول حدث إغلاق لا مجرد فتيل.

كل آلة صرفة وحتمية: نفس التعريف ونفس المدخلات ⇒ نفس القراءات،
والحالة التشغيلية (عدادات/لمس) تعيش في ``TriggerRuntime`` بيد المستدعي
لا داخل التعريف المجمّد.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

from schemas import BreakDirection, Candle, Direction, EventType, TriggerDefinition

__all__ = [
    "SUPPORTED_CONDITION_TYPES",
    "StructureEventRef",
    "TriggerRuntime",
    "TriggerSpecError",
    "advance",
]

#: الأنواع الخمسة المدعومة — عدٌّ مغلق يرفض غيره صاخبًا.
SUPPORTED_CONDITION_TYPES: frozenset[str] = frozenset(
    {
        "DISPLACEMENT_CONFIRM",
        "INTERNAL_BOS",
        "ACCEPTANCE_BEYOND",
        "RETEST_HOLD",
        "ZONE_RECLAIM",
    }
)


class TriggerSpecError(ValueError):
    """تعريف مشغل فاسد — نوع غير مدعوم أو معاملات ناقصة/مناقضة."""


@dataclass
class TriggerRuntime:
    """الحالة التشغيلية لآلة مشغل واحد — عدادات ولمس، بيد المستدعي.

    «قابلة للرصد» تعني أيضًا قابلة للإعادة: الحالة مشتقة حتميًا من تسلسل
    الأشرطة السابق فنفس الشموع ⇒ نفس القراءات (§26.2).
    """

    #: إجمالي الإغلاقات المتتالية خلف المستوى (ACCEPTANCE_BEYOND).
    consecutive_closes: int = 0
    #: هل لمس الشمعةُ نطاق الحافة (RETEST_HOLD)؟ يبقى بعد اللمس الأول.
    touched: bool = False


class StructureEventRef(NamedTuple):
    """إحالة حدث بنية موحّدة — (النوع، الإطار، اتجاه الكسر أو None).

    مسار معرّب واحد لمشغلي البنية بدل فحص الحمولات المتباينة هنا:
    المستدعي (المحرك) يبنيها من أحداث كاشف البنية مفلترةً للأداة.
    """

    event_type: EventType
    timeframe: str
    break_direction: BreakDirection | None


def advance(
    definition: TriggerDefinition,
    runtime: TriggerRuntime,
    *,
    candle: Candle,
    structure_events: Sequence[StructureEventRef] = (),
    atr: float | None = None,
) -> bool:
    """تقديم آلة المشغل شريطةً واحدة — هل اشتعل المشغل عند هذا الإغلاق؟

    :param definition: التعريف المجمّد (النوع + المعاملات).
    :param runtime: الحالة التشغيلية (تتحور في المكان — عدادات/لمس).
    :param candle: شمعة إطار التنفيذ **المغلقة** (لا-نظرة §26.3).
    :param structure_events: إحالات أحداث البنية المؤكدة عند الشمعة،
        مفلترة للأداة بيد المستدعي.
    :param atr: ATR الشمعة الجارية — نطاق ``RETEST_HOLD`` مضاعفُ تقلبٍ
        لا رقمًا كونيًا (المعامل ``band_atr`` مضاعف)؛ غيابه (دافئ
        التقلب بعد) يعني تعذر الاشتعال لا افتراضًا صامتًا.
    :returns: ``True`` إن رُصد المشغل فعليًا عند هذا الشريط.
    :raises TriggerSpecError: تعريف فاسد.
    """
    spec = definition.condition_type
    if spec not in SUPPORTED_CONDITION_TYPES:
        raise TriggerSpecError(
            f"نوع مشغل غير مدعوم: {spec!r} — المدعوم حصرًا: {sorted(SUPPORTED_CONDITION_TYPES)}"
        )
    params = definition.params
    direction = _direction_of(params, spec=spec)

    if spec == "DISPLACEMENT_CONFIRM":
        tf = _timeframe_of(params, spec=spec)
        wanted = (
            EventType.DISPLACEMENT_UP
            if direction is Direction.LONG
            else EventType.DISPLACEMENT_DOWN
        )
        return any(ref.event_type is wanted and ref.timeframe == tf for ref in structure_events)

    if spec == "INTERNAL_BOS":
        tf = _timeframe_of(params, spec=spec)
        for ref in structure_events:
            if ref.event_type is not EventType.INTERNAL_BOS or ref.timeframe != tf:
                continue
            if ref.break_direction is None:
                continue
            aligned = (
                ref.break_direction is BreakDirection.UP
                if direction is Direction.LONG
                else ref.break_direction is BreakDirection.DOWN
            )
            if aligned:
                return True
        return False

    if spec == "ACCEPTANCE_BEYOND":
        level = _float_param(params, "level", spec=spec)
        window = int(_float_param(params, "window", spec=spec))
        if window < 1:
            raise TriggerSpecError(f"مشغل {spec} بنافذة غير موجبة: {window}")
        beyond = candle.close > level if direction is Direction.LONG else candle.close < level
        runtime.consecutive_closes = runtime.consecutive_closes + 1 if beyond else 0
        return runtime.consecutive_closes >= window

    if spec == "RETEST_HOLD":
        boundary = _float_param(params, "boundary", spec=spec)
        band_atr = _float_param(params, "band_atr", spec=spec)
        if band_atr <= 0.0:
            raise TriggerSpecError(f"مشغل {spec} بنطاق غير موجب: {band_atr}")
        if atr is None or atr <= 0.0:
            # النطاق من بنية التقلب (§23.4) — بلا مقياس لا لمس موثق.
            return False
        band = band_atr * atr
        # اللمس: تقاطع مدى الشمعة مع نطاق الحافة — أول عودة إلى المنطقة.
        if candle.high >= boundary - band and candle.low <= boundary + band:
            runtime.touched = True
        # الاشتعال: لمس سابق + إغلاق صامد في جهة الاختراق.
        if runtime.touched:
            holding = (
                candle.close >= boundary
                if direction is Direction.LONG
                else candle.close <= boundary
            )
            if holding:
                return True
        return False

    # ZONE_RECLAIM — إغلاق كامل خلف المستوى (فشل القبول حدث إغلاق).
    level = _float_param(params, "level", spec=spec)
    return candle.close > level if direction is Direction.LONG else candle.close < level


def _direction_of(params: dict[str, Any], *, spec: str) -> Direction:
    """قراءة اتجاه المشغل من معاملاته — LONG/SHORT حصرًا (FLAT مرفوض)."""
    raw = str(params.get("direction", ""))
    try:
        direction = Direction(raw)
    except ValueError as exc:
        raise TriggerSpecError(f"مشغل {spec} بلا اتجاه قانوني: {raw!r}") from exc
    if direction is not Direction.LONG and direction is not Direction.SHORT:
        raise TriggerSpecError(f"مشغل {spec} باتجاه غير اتجاهي: {direction}")
    return direction


def _timeframe_of(params: dict[str, Any], *, spec: str) -> str:
    """قراءة إطار المشغل — مطابقة أحداث البنية تتم عليه."""
    tf = str(params.get("timeframe", ""))
    if not tf:
        raise TriggerSpecError(f"مشغل {spec} بلا إطار — مطابقة الأحداث مستحيلة")
    return tf


def _float_param(params: dict[str, Any], key: str, *, spec: str) -> float:
    """قراءة معامل رقمي — النقص أو الفساد رفض صاخب لا افتراض صامت."""
    if key not in params:
        raise TriggerSpecError(f"مشغل {spec} بلا معامل {key!r} — التعريف ناقص")
    try:
        return float(params[key])
    except (TypeError, ValueError) as exc:
        raise TriggerSpecError(f"مشغل {spec} بمعامل {key!r} غير رقمي: {params[key]!r}") from exc
