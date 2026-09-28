"""كائنات السيولة القانونية — خريطة السيولة ومناطقها واجتياحاتها (§10)
وحمولات أحداثها المبثوثة عبر المغلف (§20 السيولية + §32).

المصدر: §10.1 (مصادر السيولة)، §10.2 (كائن المنطقة)، §10.3 (قوة المنطقة)،
§10.4 (كشف الاجتياح)، §20 (قاموس الأحداث)، §31.3 (دورة حياة المنطقة)،
§32 (المغلف).

العقود الموثقة في هذه الوحدة:

- **الحتمية الصرفة**: كل نموذج مجمّد (frozen) ويمنع الحقول الغريبة
  (extra="forbid") — المنطقة عقد لا يُعدَّل بعد الكتابة؛ التحديث يمر
  بنسخة جديدة موثقة لا بطفرة صامتة.

- **لا-نظرة-مستقبلية (§26.3)**: كل حمولة تحمل ``bar_time`` الشمعة التي
  أكّدت الحدث — «الاجتياح تسلسل لا فتيل واحد» (§10.4) والبث لا يسبق
  اكتمال التسلسل على شمعة مقفلة (§27).

- **العتبات التطبيعية (§16)**: تجاوز الاجتياح وراء حافة المنطقة
  (``excursion_atr``) مُطبَّع بـATR المحلي — لا ثابت مطلق.

- **الصخب في التحقق**: الفاصل السعري المعكوس (price_low > price_high)
  والقيم خارج حدودها وحقول أجنبية — كلها ValidationError صارمة، لا
  تصحيح صامت.

- **«الدرجة ليست احتمالًا» (§10.3 حرفيًا)**: ``reaction_score`` و
  ``unmitigated_score`` و``importance_score`` درجات قوة خام — لا
  تُعامل احتمالات فوز أبدًا (قاعدة §2.6 نفسها).

الخريطة استدلالية لا معرفة مباشرة: «إنها خريطة مستنتَجة لا معرفة
بأوامر كل مشارك» (§10 تمهيد) — تُقرأ كفرضيات عن مواضع السيولة.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._types import (
    NonNegativeInt,
    PositiveFloat,
    Price,
    UnitInterval,
    UTCDatetime,
)
from .enums import SweepClassification


class _LiquidityModel(BaseModel):
    """أساس موحد لكائنات السيولة: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ═══════════════════════ تعدادات السيولة §10 ═══════════════════════


class LiquiditySide(StrEnum):
    """جانب السيولة (§10.1 حرفيًا) — أي جانب السوق تراكمت عنده الأوامر.

    - ``BUY_SIDE``: سيولة شرائية عند القمم — «Buy-side candidates: prior
      swing highs; equal highs; session highs; previous day/week highs;
      range boundaries; obvious repeated highs; untested external
      liquidity» (§10.1). يجتاحها البائعون فيصعد السعر إليها ثم يُرفض.
    - ``SELL_SIDE``: سيولة بيعية عند القعور — «Sell-side candidates:
      prior swing lows; equal lows; session lows; previous day/week lows;
      range boundaries; obvious repeated lows; untested external
      liquidity» (§10.1).
    """

    BUY_SIDE = "BUY_SIDE"  # عند القمم (stop-buy فوق المستويات)
    SELL_SIDE = "SELL_SIDE"  # عند القعور (stop-sell تحت المستويات)


class LiquiditySourceType(StrEnum):
    """نوع مصدر المنطقة — قوائم §10.1 مصنّفة إلى أنواع قابلة للبرمجة.

    القرار الموثق: «obvious repeated highs/lows» و«untested external
    liquidity» ليستا نوعَي مصدر بل **خصيصتين تُقاسان**: التكرار عبر
    ``test_count`` وطزاجة المنطقة عبر حالتها (``ZoneState`` و
    ``sweep_status``) — عدُّهما نوعين مستقلين يكرر المعلومة نفسها ويكسر
    تعامد الحقول.
    """

    PRIOR_SWING = "PRIOR_SWING"  # متطرف سابق مؤكد (§11.1)
    EQUAL_LEVEL = "EQUAL_LEVEL"  # قمم/قيعان متساوية ضمن تسامح معلن
    SESSION_EXTREME = "SESSION_EXTREME"  # قمة/قاع الجلسة (§9.4)
    PREV_DAY_EXTREME = "PREV_DAY_EXTREME"  # قمة/قاع اليوم السابق
    PREV_WEEK_EXTREME = "PREV_WEEK_EXTREME"  # قمة/قاع الأسبوع السابق
    RANGE_BOUNDARY = "RANGE_BOUNDARY"  # حدود نطاق المعالجة (§11.7)


class ZoneState(StrEnum):
    """حالة دورة حياة المنطقة (§31.3: «liquidity zones … and lifecycle
    state») — مدخل «whether the zone has already been consumed» في قوة
    المنطقة (§10.3) يُقرأ من هنا.

    - ``ACTIVE``: قائمة لم تُجتَح بعد.
    - ``SWEPT``: اجتاحها حدث LIQUIDITY_SWEEP_* مؤكد (§10.4).
    - ``CONSUMED``: استُهلكت بقبول (BREAK_AND_ACCEPT — §10.4/§20) فلم تعد
      هدفًا معتبرًا.
    - ``INVALIDATED``: بطل تعريفها البنيوي (المتطرف المصدر انكسر كسرًا
      خارجيًا مثلًا) — تُبقى للتاريخ لا للاستهداف.
    """

    ACTIVE = "ACTIVE"
    SWEPT = "SWEPT"
    CONSUMED = "CONSUMED"
    INVALIDATED = "INVALIDATED"


# ═══════════════════════ كائن المنطقة §10.2 ═══════════════════════


class LiquidityZone(_LiquidityModel):
    """منطقة سيولة (§10.2 حرفيًا) — خريطة مستنتَجة لمواضع الأوامر.

    الحقول الاثنا عشر الحرفية من نص §10.2 كاملة هنا. الامتدادات
    التشغيلية الموثقة: ``instrument`` و``timeframe`` (تمركز ذاتي —
    المنطقة تُنقل وتُؤرشف مستقلة عن المجري الذي أنشأها)، و``state``
    (حالة دورة الحياة §31.3 — مدخل الاستهلاك في قوة المنطقة §10.3).

    ``age`` عمر المنطقة بالشموع **عند آخر تحديث** — قيمة مشتقة ديناميكيًا
    (أصل السجل − آخر شمعة) والقيمة المخزونة لقطة وقت الكتابة، فقديمتها
    تُعاد اشتقاقها عند القراءة لا تُصدَّق كوقت حي.

    ``reaction_score`` و``unmitigated_score`` و``importance_score`` مدخلات
    قوة المنطقة السبعة (§10.3) بدرجات خام — «الدرجة ليست احتمالًا»
    (§10.3 حرفيًا).
    """

    # حقول §10.2 الحرفية
    zone_id: str
    side: LiquiditySide
    price_low: Price
    price_high: Price
    origin_time: UTCDatetime
    age: NonNegativeInt  # بالشموع عند آخر تحديث — لقطة لا قيمة حية
    source_type: LiquiditySourceType
    test_count: NonNegativeInt
    last_test_time: UTCDatetime | None  # None = لم تُختبر قط (منطقة طازجة)
    sweep_status: SweepClassification  # التصنيف الخمسي §10.4
    reaction_score: UnitInterval  # جودة رد الفعل السابق (§10.3)
    unmitigated_score: UnitInterval  # طزاجة/عدم التخفيف (§10.3)
    importance_score: UnitInterval  # الأهمية البنيوية (§10.3)

    # الامتدادات التشغيلية الموثقة
    instrument: str
    timeframe: str
    state: ZoneState

    @model_validator(mode="after")
    def _price_band_ordered(self) -> Self:
        """المنطقة فاصل سعري مرتب صعودًا — المعكوس مدخل فاسد يُرفض.

        ``price_low == price_high`` جائز: مستوى واحد (متطرف معزول مثلًا)
        منطقة صفرية العرض قبل تعريضها بحافة تسامح.
        """
        if self.price_low > self.price_high:
            raise ValueError(
                f"فاصل المنطقة معكوس: price_low={self.price_low} > "
                f"price_high={self.price_high} — المنطقة فاصل سعري "
                "[price_low, price_high] مرتب صعودًا دائمًا (§10.2)"
            )
        return self


# ═══════════════════ حمولات أحداث §20 السيولية ═══════════════════


class SweepEventPayload(_LiquidityModel):
    """حمولة اجتياح السيولة — تخدم LIQUIDITY_SWEEP_HIGH / LIQUIDITY_SWEEP_LOW
    (§10.4 + §20): حدث بثّ بعد اكتمال التسلسل، لا الفتيل الأول.

    «الاجتياح تسلسل لا فتيل واحد» (§10.4): ``penetration_reached`` هي
    الشرط 3 (بلغ التجاوز عتبة نسبةً إلى التقلب المحلي وعرض المنطقة)،
    و``reclaim_bars`` سرعة الاسترجاع — قياس §20 الرئيس («Excursion,
    reclaim speed»). ``classification`` دائمًا CONFIRMED_SWEEP عند بث هذه
    الأنواع (البث نفسه هو التأكيد) لكن يبقى الحقل للتقرير الذاتي
    للتصنيف عند البث — لا للاختزال الصامت؛ التصنيفات الأخرى
    (FAILED/PARTIAL/BREAK_AND_ACCEPT/UNKNOWN) حالات كاشف لا تُبث بهذين
    النوعين.

    ``test_count_at_event`` لقطة عدّاد الاختبارات لحظة الحدث — تجعل
    الحمولة مكتفية ذاتيًا للتقادم (§31.3) بلا الرجوع لسجل المنطقة.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة التي أكّدت اكتمال التسلسل (§10.4)

    zone_id: str  # المنطقة المستهلَكة — الربط الإلزامي (§10.4 شرط 5)
    zone_side: LiquiditySide
    classification: SweepClassification  # §10.4 — التقرير الذاتي عند البث
    excursion_atr: PositiveFloat  # أقصى تجاوز وراء الحافة مطبَّعًا بـATR
    penetration_reached: bool  # الشرط 3 §10.4 — عتبة التغلغل
    reclaim_bars: NonNegativeInt  # سرعة الاسترجاع (§20 «reclaim speed»)
    test_count_at_event: NonNegativeInt  # لقطة العداد لحظة الحدث


class BreakAcceptEventPayload(_LiquidityModel):
    """حمولة الكسر بالقبول — تخدم BREAK_AND_ACCEPT_HIGH / BREAK_AND_ACCEPT_LOW
    (§20): «Break + closes/volume acceptance» والقياس الرئيس «Acceptance
    ratio».

    هذا الطرف المقابل للاجتياح في التصنيف الخمسي (§10.4): القبول خلف
    الحافة يستهلك المنطقة (``ZoneState.CONSUMED``) بدل اجتياحها ورفضها.
    ``window_bars`` نافذة القياس المعلنة، و``acceptance_ratio`` نسبة
    الإغلاقات المقبولة وراء الحافة داخلها.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة التي أكّدت القبول

    zone_id: str
    zone_side: LiquiditySide
    excursion_atr: PositiveFloat  # أقصى تجاوز وراء الحافة مطبَّعًا بـATR
    acceptance_ratio: UnitInterval  # نسبة الإغلاقات المقبولة وراء الحافة (§20)
    window_bars: NonNegativeInt  # نافذة القياس المعلنة (شموع)
