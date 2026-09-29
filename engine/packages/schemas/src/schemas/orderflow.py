"""حمولات أحداث التدفق المبثوثة — الامتصاص والاستمرار والإنهاك وعناقيد
الاختلال (§12 + §20 التدفقية + §32).

المصدر: §12.1-12.7 (محرك التدفق والفوتبرنت) و§20 (قاموس الأحداث: الصفوف
ABSORPTION_BUY/ABSORPTION_SELL وFLOW_CONTINUATION_UP/DOWN و
EXHAUSTION_UP/DOWN وBUY/SELL_IMBALANCE_CLUSTER) و§32 (المغلف).

العقود الموثقة في هذه الوحدة:

- **الحتمية الصرفة**: كل نموذج مجمّد (frozen) ويمنع الحقول الغريبة
  (extra="forbid") — الحمولة تُبنى مرة واحدة فلا تُعدَّل ولا تُوسَّع بصمت.

- **لا-نظرة-مستقبلية (§26.3)**: ``bar_time`` هو الشمعة التي أكّدت الحدث —
  الكاشف يبث بعد إقفالها حصرًا (فصل المتطور عن المؤكد §27).

- **الوسم الإلزامي للمصدر (§12.7)**: حجم الشراء/البيع التدفقي تصنيف مبني
  على علم ``buyer_is_maker`` لمصدر بيانات محدد — «ليس كل مشتريي السوق
  مقابل كل بائعيه»؛ ``source_feed`` و``methodology`` إلزاميان في سجل
  الفوتبرنت ذاته (``FootprintBar`` في ``market.py``)، والحمولات هنا تحمل
  القياسات المشتقة منه فتظل مشروطة بالمصدر نفسه.

- **العتبات التطبيعية (§16)**: كل امتداد/استجابة سعرية في الحمولات
  مُطبَّعة بـATR المحلي (``excursion_atr`` و``response_atr``) — لا ثابت
  ticks/pips مطلق. النسب عديمة الأبعاد (``delta_share``) قياسات صرفة
  لا تحتاج تطبيعًا سعريًا.

- **المرشحية القابلة للتأكيد (§12.2/§12.3)**: «هذه فرضيات يجب أن تؤكدها
  الاستجابة اللاحقة» — الامتصاخ والإنهاك يخرجان مرشحين
  (``confirmed=False`` حتى تأكيد لاحق)، والاستمرار حدث توافق مباشر.

- **الصخب في التحقق**: المدخل الفاسد (كفاءة سالبة، نطاق خارج حده، حقل
  غريب) يُرفض بـValidationError ولا يُصحَّح صمتًا أبدًا.

الحقول المشتركة لكل حمولة (تمركز ذاتي — الحمولة تفهم بلا سياق خارجي):
``instrument`` و``timeframe`` و``bar_time`` (الشمعة التي أكّدت الحدث).
البث يجري داخل EventEnvelope (§32) وتُتحقق الحمولة ضد مخططها المُصدَّر
في generated/.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ._types import (
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SignedUnit,
    UnitInterval,
    UTCDatetime,
)


class _OrderFlowModel(BaseModel):
    """أساس موحد لحمولات التدفق: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ═══════════════════════ تعدادات التدفق §12 ═══════════════════════


class FlowDirection(StrEnum):
    """اتجاه الحركة التدفقية — صعودًا أم هبوطًا (§12.2).

    يخدم FLOW_CONTINUATION وEXHAUSTION (اتجاه الجهد الذي يُقاس مفعوله).
    """

    UP = "UP"  # جهد/استجابة صاعدة
    DOWN = "DOWN"  # جهد/استجابة هابطة


class AbsorbedPressure(StrEnum):
    """جهة الضغط المُمتص (§12.3 + §20).

    ABSORPTION_BUY = «الضغط البيعي امتُص» (عدوانية بيعية كبيرة بردّ محدود)
    ⇒ الضغط الممتص SELL والعكس لـABSORPTION_SELL. الحقل يجعل الحمولة
    متمركزة ذاتيًا (تُفهم بلا معرفة النوع).
    """

    SELL = "SELL"  # ضغط بيعي امتُص (الحدث ABSORPTION_BUY)
    BUY = "BUY"  # ضغط شرائي امتُص (الحدث ABSORPTION_SELL)


class ImbalanceSide(StrEnum):
    """جهة الاختلال الصفّي (§12.6).

    اختلال شرائي = صف الشراء يهيمن على صف البيع المقابل؛ الاختلالات
    المتكررة بجهة واحدة تصنع عنقيدًا (BUY/SELL_IMBALANCE_CLUSTER).
    """

    BUY = "BUY"  # اختلالات شرائية صفّية
    SELL = "SELL"  # اختلالات بيعية صفّية


# ═══════════════════════ شروط الامتصاص §12.3 ═══════════════════════


class AbsorptionConditions(BaseModel):
    """الشروط الأربعة لمرشح الامتصاص (§12.3 حرفيًا).

    الشرط الرابع اختياري (``None`` حتى يحدث) — «إزاحة لاحقة معاكسة
    اختيارية»؛ بقية الشروط إلزامية لكي يُعدّ المرشح مكتمل الشروط.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 1) دلتا اتجاهية أو حجم مرتفع عند منطقة («elevated directional delta
    #: or volume at a zone»).
    elevated_delta: bool
    #: 2) امتداد سعري محدود نسبةً إلى العدوان («limited price extension
    #: relative to the aggression»).
    limited_extension: bool
    #: 3) استجابة متكررة أو فشل في المواصلة («repeated response or
    #: failure to continue»).
    repeated_response: bool
    #: 4) إزاحة لاحقة معاكسة — اختيارية (``None`` حتى تُرصد).
    opposite_displacement: bool | None = None


# ═══════════════════════ حمولات أحداث التدفق §20 ═══════════════════════


class AbsorptionEventPayload(_OrderFlowModel):
    """حمولة الامتصاص — تخدم ABSORPTION_BUY / ABSORPTION_SELL
    (§12.3 + §20: «Delta vs excursion»).

    عدم توافق بين الحجم المتداول العدواني والحركة السعرية المحققة عند
    موقع ذي معنى. المرشح يخرج غير مؤكد (``confirmed=False``): «فرضيات يجب
    أن تؤكدها الاستجابة اللاحقة» (§12.2) — التأكيد لا يخترع حدثًا جديدًا
    بل يرفع درجة المرشح نفسه.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة التي أكّدت اكتمال شروط المرشح

    absorbed_pressure: AbsorbedPressure  # الجهة الممتصة (تطابق النوع §20)
    #: الدلتا الموقعة للشريط (buy_volume − sell_volume) — سالبة في
    #: ABSORPTION_BUY (عدوانية بيعية) وموجبة في ABSORPTION_SELL.
    delta: float
    #: حصة الدلتا من الحجم الكلي ∈ [-1,1] — قياس «ارتفاع العدوانية»
    #: عديم الأبعاد (شرط 1).
    delta_share: SignedUnit
    #: الامتداد السعري المحقق باتجاه العدوان بمضاعفات ATR المحلي —
    #: «محدود» إذا لم يتجاوز عتبة ABSORPTION_EXTENSION_MAX (شرط 2).
    excursion_atr: PositiveFloat
    #: الشروط الأربعة الموثقة لحظة إصدار المرشح (§12.3).
    conditions: AbsorptionConditions
    #: معرف منطقة السيولة/البنية التي وقع عندها المرشح إن وُجدت — «جودة
    #: الامتصاص ترتفع عند حدود سيولة مرسومة أو بنيوية» (§12.3).
    zone_id: str | None = None
    #: مرشح قابل للتأكيد لاحقًا (§12.2) — يبدأ False دائمًا عند الإصدار.
    confirmed: bool = False


class FlowContinuationEventPayload(_OrderFlowModel):
    """حمولة توافق التدفق — تخدم FLOW_CONTINUATION_UP / FLOW_CONTINUATION_DOWN
    (§12.2 + §20: «Delta efficiency»).

    «دلتا موجبة كبيرة + صعود قوي ⇒ شراء عدواني مقبول» — الجهد والنتيجة
    يتفقان. حدث مباشر لا مرشح: التوافق قياس لحظة إغلاق الشريط.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة التي قيست فيها الموافقة

    direction: FlowDirection
    delta: float  # دلتا الشريط الموقعة (موجبة صعودًا/سالبة هبوطًا)
    delta_share: SignedUnit  # حصة الدلتا ∈ [-1,1] — حجم الجهد
    #: استجابة السعر باتجاه الجهد بمضاعفات ATR المحلي — «قوية» إذا بلغت
    #: عتبة FLOW_RESPONSE_MIN على الأقل.
    response_atr: PositiveFloat
    #: كفاءة الدلتا: الاستجابة لكل وحدة جهد (``response_atr / |delta_share|``)
    #: — القياس الأولي للحدث في §20.
    efficiency: PositiveFloat


class ExhaustionEventPayload(_OrderFlowModel):
    """حمولة الإنهاك — تخدم EXHAUSTION_UP / EXHAUSTION_DOWN
    (§12.4 + §20: «Efficiency decay»).

    تراجع الفعالية الاتجاهية: امتداد أقل لكل وحدة حجم اتجاهي، ومتابعة
    متناقصة، وقمم/قيعان فاشلة متكررة، وكفاءة دلتا متدهورة. «الإنهاك وحده
    ليس إشارة انعكاس» (§12.4) — الحمولة قياس تراجع لا توصية.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # الشمعة التي تأكد فيها التراجع

    direction: FlowDirection  # اتجاه الجهد المنهَك
    #: كفاءة الدلتا الحالية (استجابة لكل وحدة جهد) — تراجع عن السابقة.
    efficiency: PositiveFloat
    #: كفاءة النافذة السابقة — مرجع التراجع.
    efficiency_prev: PositiveFloat
    #: نسبة التراجع ``efficiency / efficiency_prev`` — «تراجع» يعني < 1.
    decay_ratio: PositiveFloat
    #: عدد القمم/القيعان الفاشلة المتكررة في النافذة («repeated failed
    #: highs/lows» §12.4).
    failed_extremes: NonNegativeInt
    #: متابعة الحركة المتدهورة داخل النافذة ∈ [0,1] («reducing
    #: follow-through» §12.4).
    follow_through: UnitInterval


class ImbalanceClusterEventPayload(_OrderFlowModel):
    """حمولة عنقيد الاختلالات — تخدم BUY_IMBALANCE_CLUSTER /
    SELL_IMBALANCE_CLUSTER (§12.6 + §20).

    «اختلال معزول له وزن اتجاهي منخفض؛ اختلالات متكررة متوائمة مع
    الإزاحة والبنية تحمل دليلًا أكثر» (§12.6) — النظام يخزن الرصد الخام
    (عدادات الشريط) والأهمية السياقية معًا.
    """

    instrument: str
    timeframe: str
    bar_time: UTCDatetime  # آخر شمعة في العنقيد (المؤكِدة)

    side: ImbalanceSide
    #: عدد أشرطة الفوتبرنت المتتالية التي كوّنت العنقيد (≥ 1 دائمًا).
    bar_count: PositiveInt
    #: مجموع عدادات الاختلال بجهة العنقيد عبر أشرطته (خام §12.6).
    total_imbalances: NonNegativeInt
    #: أقصى نسبة صفّية مفردة داخل العنقيد (شراء الصف مقابل بيع مقابله).
    max_row_ratio: PositiveFloat
    #: الأهمية السياقية (§12.6): هل تواءم العنقيد مع إزاحة/بنية مؤكدة؟
    aligned_with_displacement: bool
