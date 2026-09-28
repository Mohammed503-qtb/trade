"""الكائنات البنيوية القانونية — المتطرفات والكسور والإزاحة (§11) وحمولات
أحداثها المبثوثة عبر المغلف (§20 البنيوية + §32).

المصدر: §11.1 (Swing)، §11.2-3 (BOS/CHoCH)، §11.4 (الإزاحة)، §11.5 (FVG)،
§11.6 (Order Block)، §11.7 (Premium/Discount)، §20 (قاموس الأحداث)، §32 (المغلف).

العقود الموثقة في هذه الوحدة:

- **الحتمية الصرفة**: كل نموذج مجمّد (frozen) ويمنع الحقول الغريبة
  (extra="forbid") — الكائن يُبنى مرة واحدة فلا يُعدَّل ولا يُوسَّع بصمت.

- **لا-نظرة-مستقبلية (§26.3)**: كل حمولة تحمل ``bar_time`` الشمعة التي
  أكّدت الحدث — التأكيد لا يسبق الشمعة؛ الكاشف يبث بعد إقفالها حصرًا
  (فصل المتطور عن المؤكد §27)، والمتطرف نفسه يحمل ``confirmation_time``
  بعد قاعدة النظر الخلفي المعلنة (§11.1).

- **العتبات التطبيعية (§16)**: كل مسافة/حجم في الحمولات مُطبَّع بـATR
  المحلي (``breach_distance_atr`` و``size_atr`` و``atr_multiple``...) —
  لا ثابت ticks/pips مطلق في أي عقد بنيوي.

- **الصخب في التحقق**: المدخل الفاسد (فاصل سعر معكوس، قيمة خارج حدودها،
  حقل غريب) يُرفض بـValidationError ولا يُصحَّح صمتًا أبدًا.

الحقول المشتركة لكل حمولة (تمركز ذاتي كمثال §32 — الحمولة تفهم بلا سياق
خارجي): ``instrument`` و``timeframe`` و``bar_time`` (الشمعة التي أكّدت
الحدث). البث يجري داخل EventEnvelope (§32) وتُتحقق الحمولة ضد مخططها
المُصدَّر في generated/.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._types import (
    FiniteFloat,
    PositiveFloat,
    Price,
    UnitInterval,
    UTCDatetime,
)


class _StructureModel(BaseModel):
    """أساس موحد للكائنات البنيوية: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ═══════════════════════ تعدادات البنية §11 ═══════════════════════


class SwingDirection(StrEnum):
    """قطبية المتطرف (§11.1) — قمة أم قاع.

    §11.1 يسمي الحقل ``direction`` دون نطاق قيم؛ HIGH/LOW يطابق لغة §10.1
    نفسها («prior swing highs» / «prior swing lows») وأسماء أحداث §20
    (LIQUIDITY_SWEEP_HIGH / LIQUIDITY_SWEEP_LOW) — لا LONG/SHORT لأن
    المتطرف مستوى لا انحيازًا اتجاهيًا.
    """

    HIGH = "HIGH"  # قمة متطرفة (swing high)
    LOW = "LOW"  # قاع متطرف (swing low)


class SwingScope(StrEnum):
    """نطاق المتطرف (§11.1 حرفيًا — اسم الحقل ``external_or_internal``).

    القيمتان من §11.2 نفسه: «classify as internal or external» — البنية
    الخارجية هي الإطار الأكبر والداخلية حركة داخله.
    """

    EXTERNAL = "EXTERNAL"
    INTERNAL = "INTERNAL"


class BreakDirection(StrEnum):
    """اتجاه الكسر أو الإزاحة — صعودًا أم هبوطًا (§11.2/§11.4).

    مستوى الكسر/الاندفاع ثنائي القطبية، لا LONG/SHORT — القرار الاتجاهي
    مسؤولية الدمج (§19) لا الكاشف.
    """

    UP = "UP"
    DOWN = "DOWN"


class FvgDirection(StrEnum):
    """قطبية الفجوة/المنطقة المصدرية (§11.5/§11.6).

    BULLISH/BEARISH يطابق أسماء أحداث §20 نفسها (FVG_BULLISH/BEARISH
    وORDER_BLOCK_BULLISH/BEARISH).
    """

    BULLISH = "BULLISH"  # فجوة صاعدة / منطقة مصدرية صاعدة
    BEARISH = "BEARISH"  # فجوة هابطة / منطقة مصدرية هابطة


class FvgState(StrEnum):
    """حالة الفجوة في لحظة البث (§11.5).

    حدث البث هو التكوين حصرًا (``CREATED``)؛ الملء والنفاد («fill
    percentage» و«first mitigation time» و«invalidation/consumption
    state» بنص §11.5) حالة تتبعية داخل الكاشف تُقرأ عند الحاجة — «لا
    يُفترض أن كل فجوة يجب أن تُملأ» (§11.5) فلا تُبث حالة ملء كأنها حدث.
    """

    CREATED = "CREATED"


class StructureConsequence(StrEnum):
    """النتيجة البنيوية للإزاحة المولِّدة لمنطقة Order Block (§11.6 خطوة 3).

    «Verify the impulse generated meaningful structure change or liquidity
    interaction» — الخطوة الثالثة من خط الأنابيب؛ القيمة ``NONE_YET``
    تعني أن التحقق لم يكتمل بعد لا أن المنطقة باطلة.
    """

    BOS = "BOS"  # كسر بنية مؤكد (§11.2)
    LIQUIDITY_INTERACTION = "LIQUIDITY_INTERACTION"  # تفاعل سيولة معنوي (§10)
    NONE_YET = "NONE_YET"  # التحقق لم يكتمل بعد


class PremiumDiscountSide(StrEnum):
    """جانب النطاق (§11.7 حرفيًا): فوق المنصف premium وتحته discount."""

    PREMIUM = "PREMIUM"  # price > equilibrium
    DISCOUNT = "DISCOUNT"  # price < equilibrium


# ═══════════════════════ كائن البنية §11.1 ═══════════════════════


class Swing(_StructureModel):
    """متطرف مؤكد (§11.1 حرفيًا) — يُؤكَّد فقط بعد اكتمال قاعدة النظر
    الخلفي/التأكيد، والقاعدة «لا تعتمد على شموع مستقبلية في الوضع الحي
    بعد تأخير التأكيد المطلوب» (§11.1).

    **الامتداد التشغيلي الموثق الوحيد**: ``bar_time`` — وقت شمعة القمة/
    القاع نفسها. §11.1 لا يذكره لكنه لازم لعقدين تشغيليين: (أ) ``origin_time``
    لمناطق البنية المنبثقة عن المتطرف (§11.6)، و(ب) الترتيب الزمني
    للمتطرفات عند تساوي أوقات التأكيد. العلاقة القانونية:
    ``confirmation_time = bar_time + تأخير التأكيد`` — الفارق بينهما هو
    قاعدة النظر الخلفي نفسها، ولا يجوز أن يكون سالبًا أبدًا.
    """

    swing_id: str
    price: Price
    timeframe: str
    direction: SwingDirection
    strength: UnitInterval
    confirmation_time: UTCDatetime
    external_or_internal: SwingScope
    #: الامتداد الموثق: وقت شمعة القمة/القاع نفسها (انظر docstring الصنف).
    bar_time: UTCDatetime


# ═══════════════════════ حمولات أحداث §20 البنيوية ═══════════════════════


class StructureBreakPayload(_StructureModel):
    """حمولة كسر البنية — تخدم INTERNAL_BOS / EXTERNAL_BOS / CHOCH
    (§11.2-3 + §20) داخل EventEnvelope (§32).

    ``swing_scope`` يعيد نطاق المتطرف المكسور (داخلي/خارجي — تصنيف §11.2)،
    و``breach_distance_atr`` هو «breach distance normalized by ATR/local
    range» (مقياس §11.2) و``closing_acceptance`` «closing acceptance».
    ``choch_prior_direction`` يُضع للـCHOCH حصرًا (§11.3: «اتجاه
    الاستمرار السابق المنتَهَك») ويبقى None لكسري BOS.
    """

    # حقول التمركز المشتركة — الشمعة التي أكّدت الكسر (لا-نظرة-مستقبلية §26.3)
    instrument: str
    timeframe: str
    bar_time: UTCDatetime

    swing_id: str  # المتطرف المكسور (§11.1)
    swing_scope: SwingScope
    break_direction: BreakDirection
    breach_distance_atr: PositiveFloat  # مسافة الكسر مطبَّعة بـATR (§11.2)
    closing_acceptance: UnitInterval  # قبول الإغلاق (§11.2)
    follow_through: UnitInterval  # المتابعة بعد الكسر (§11.2)
    #: CHOCH فقط — اتجاه الاستمرار السابق المنتَهَك (§11.3)؛ None لكسري BOS.
    choch_prior_direction: BreakDirection | None = None


class DisplacementEventPayload(_StructureModel):
    """حمولة الإزاحة — تخدم DISPLACEMENT_UP / DISPLACEMENT_DOWN
    (§11.4 + §20): السمات الست الحرفية لنص §11.4.

    «الإزاحة تقيس حركة سعرية اتجاهية غير معتادة نسبةً إلى التقلب الحديث»
    (§11.4) — كل قيمة هنا قياس لتلك الحركة، و``velocity`` مدى لكل شمعة
    (موجب دائمًا: الإزاحة سفر لا اتجاه، والاتجاه في ``direction``).
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # شمعة الاندفاع المؤكدة

    direction: BreakDirection
    range_zscore: FiniteFloat  # z-score المدى مقابل التقلب الحديث (§11.4)
    body_fraction: UnitInterval  # كفاءة الجسم (§11.4)
    close_location: UnitInterval  # موقع الإغلاق داخل المدى (§11.4)
    atr_multiple: PositiveFloat  # المدى بمضاعفات ATR المحلي (§11.4)
    velocity: PositiveFloat  # المدى/شمعة — سرعة السفر (§11.4)
    follow_through: UnitInterval  # المتابعة بعد الاندفاع (§11.4)


class FvgEventPayload(_StructureModel):
    """حمولة تكوين فجوة القيمة — تخدم FVG_BULLISH / FVG_BEARISH
    (§11.5 + §20): «الفجوة تُخزَّن فاصلًا سعريًا» مع وقت الأصل والاتجاه
    والحجم المُطبَّع بـATR المحلي (§11.5).

    حدث البث هو التكوين (``state=CREATED`` انظر FvgState)؛ الملء والنفاد
    حالة تتبعية في الكاشف لا تُبث — «لا يُفترض أن كل فجوة يجب أن تُملأ».
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة الثالثة التي أكّدت الفجوة (§11.5)

    direction: FvgDirection
    gap_low: Price  # حافة الفجوة الدنيا (فاصل سعري §11.5)
    gap_high: Price  # حافة الفجوة العليا
    size_atr: PositiveFloat  # الحجم مُطبَّع بـATR المحلي (§11.5)
    state: FvgState

    @model_validator(mode="after")
    def _gap_interval_ordered(self) -> Self:
        """الفجوة فاصل سعري مرتب صعودًا — الفاصل المعكوس مدخل فاسد يُرفض."""
        if self.gap_low > self.gap_high:
            raise ValueError(
                f"فاصل الفجوة معكوس: gap_low={self.gap_low} > gap_high={self.gap_high} — "
                "الفجوة فاصل سعري [gap_low, gap_high] مرتب صعودًا دائمًا (§11.5)"
            )
        return self


class OrderBlockEventPayload(_StructureModel):
    """حمولة تكوين Order Block — تخدم ORDER_BLOCK_BULLISH / ORDER_BLOCK_BEARISH
    (§11.6 + §20): المنطقة المصدرية قبل إزاحة مؤكدة «تظل ذات صلة بعد الحركة».

    ``origin_time`` وقت الشمعة/العنقود المعاكس المصدر (خطوة 2 من خط
    الأنابيب §11.6)، و``displacement_id`` الإزاحة المؤكدة المولِّدة
    (خطوة 1)، و``structure_consequence`` نتيجة الخطوة 3. «لا يُفسَّر
    Order Block أبدًا كدليل على أمر مؤسسي» (§11.6).
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # شمعة تأكيد الإزاحة المولِّدة

    direction: FvgDirection  # قطبية المنطقة المصدرية
    zone_low: Price
    zone_high: Price
    origin_time: UTCDatetime  # وقت الشمعة/العنقود المعاكس المصدر (§11.6)
    displacement_id: str  # الإزاحة المؤكدة المولِّدة (§11.6 خطوة 1)
    structure_consequence: StructureConsequence  # §11.6 خطوة 3
    size_atr: PositiveFloat  # عرض المنطقة مطبَّعًا بـATR المحلي

    @model_validator(mode="after")
    def _zone_interval_ordered(self) -> Self:
        """المنطقة فاصل سعري مرتب صعودًا — الفاصل المعكوس مدخل فاسد يُرفض."""
        if self.zone_low > self.zone_high:
            raise ValueError(
                f"فاصل المنطقة معكوس: zone_low={self.zone_low} > zone_high={self.zone_high} — "
                "المنطقة فاصل سعري [zone_low, zone_high] مرتب صعودًا دائمًا (§11.6)"
            )
        return self


class PremiumDiscountEventPayload(_StructureModel):
    """حمولة الموقع داخل نطاق المعالجة — تخدم PREMIUM_LOCATION /
    DISCOUNT_LOCATION (§11.7 + §20).

    «يجب تسمية نطاق المعالجة صراحةً» (§11.7) — لذلك ``range_name`` إلزامي،
    والمحرك «يرفض حسابات premium/discount ملتبسة تغيّر تعريف النطاق بصمت».
    ``normalized_distance`` = (price − equilibrium) / ((range_high −
    range_low) / 2): إقصاء مطبَّع قد يتجاوز ±1 عندما يخرج السعر من
    النطاق نفسه — القيمة خارج [−1, +1] معلومة (خروج عن النطاق) لا خطأ.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # شمعة تقييم الموقع

    range_name: str  # اسم النطاق المعرّى صراحةً (§11.7)
    range_low: Price
    range_high: Price
    equilibrium: Price  # (range_high + range_low) / 2 (§11.7 حرفيًا)
    location: PremiumDiscountSide
    normalized_distance: FiniteFloat  # قد يتجاوز ±1 خارج النطاق (موثق أعلاه)
    price: Price

    @model_validator(mode="after")
    def _range_well_defined(self) -> Self:
        """النطاق المنحل (low ≥ high) يبطل التعريف كله — يُرفض صامتًا لا.

        ``normalized_distance`` تقسم على (range_high − range_low)/2، فالنطاق
        المنحل قسمة على صفر؛ §11.7 يرفض النطاق الملتبس صامت التعريف.
        """
        if self.range_low >= self.range_high:
            raise ValueError(
                f"نطاق معالجة منحل أو معكوس: range_low={self.range_low} ≥ "
                f"range_high={self.range_high} — النطاق المعرّى يجب أن يكون "
                "فاصلًا موجب العرض (§11.7)"
            )
        return self
