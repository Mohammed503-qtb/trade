"""سجل الدليل (§19.1) ومخرجات دمجه (§19.2-6 + D-03) وكائن التفسير (§2.8).

الحدود حرفية من §19.1: direction_score ∈ [-1, +1] وraw_strength/quality/
freshness/independence_discount ∈ [0, 1]. prior_weight وcontext_modifier
مضاعفان تركهما النص بلا حد (§19.2) فبقيا float منتهيًا.

المرحلة 6 تضيف عقود المخرجات: لقطة الدمج الفردية (FusionSnapshot)
بتوقيتها لإتاحة المجموعات (D-03-ب + A-01) ودرجاتها المسقوفة tanh
(D-03-أ) وقائمة المعارضة الصريحة (§19.5) وتقرير المعاير (§19.6 —
البنية الآن والملء بعد بيانات OOS كافية)، وكائن التفسير (§2.8) الذي
يرافق كل قرار.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ._types import FiniteFloat, NonNegativeFloat, SignedUnit, UnitInterval, UTCDatetime
from .enums import Direction, EventType, EvidenceGroup

#: سبب تأجيل المعايرة القانوني الموحد (§19.6) — ثابت واحد يمنع تفرق
#: الصياغات بين اللقطات؛ تُلغى صياغته عندما يُبنى جهاز المعاير (المرحلة 9).
CALIBRATION_DEFERRAL_REASON = (
    "المعايرة مؤجلة حتى توفر بيانات خارج العينة الكافية (مسؤولية الإعادة "
    "والوسم — المرحلة 9): §19.6 يشترط معاير isotonic/Platt على بيانات لم "
    "تُستخدم في تحسين الدرجة الخام، والدرجة الخام لا توصف كاحتمال أبدًا"
)


class EvidenceRecord(BaseModel):
    """سجل دليل واحد — مجمّد ويمنع الحقول الغريبة (عقد §19.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    group: EvidenceGroup
    event_type: EventType
    direction_score: SignedUnit
    raw_strength: UnitInterval
    quality: UnitInterval
    freshness: UnitInterval
    independence_discount: UnitInterval
    prior_weight: FiniteFloat
    context_modifier: FiniteFloat
    opposition: bool
    source: str
    # مجموعة الارتباط (§19.4): الأحداث المنبثقة من الدفعة نفسها تُخصم
    # استقلاليتها فلا تُعد تأكيدات مستقلة (§2.3).
    correlation_group_id: str | None = None
    #: وقت تأكيد المصدر (شمعة القرار — لا-نظرة §26.3): مرساة سلسلة الجرد
    #: الزمنية في evidence_items (§31.3) — امتداد موثق بنمط
    #: correlation_group_id نفسه؛ الطراوة تُشتق منه عند البناء.
    event_time: UTCDatetime
    #: معرف الحدث المصدر الحتمي (uuid5 فوق هوية كاملة — روح D-07):
    #: وصلة السلسلة إلى جداول الأحداث (structure/orderflow/pattern_events)
    #: — None للدليل المشتق من الحالة (انحياز §9.2 بلا حدث بث مصدر).
    event_id: str | None = None


class _FusionModel(BaseModel):
    """أساس موحد لعقود الدمج — مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AvailabilitySignature(_FusionModel):
    """توقيع الإتاحة (D-03-ب + A-01) — سجل صريح لمن حضر ومن غاب.

    «إعادة توزيع حتمية عند الخلو + تسجيل توقيع إتاحة مع كل لقطة دمج»:
    أي قارئ للقطة يعرف أي المجموعات الست كان لها دليل مؤهل، وما الحصص
    الافتراضية، وما الحصص الفعلية بعد إعادة التوزيع التناسبي — فلا
    «تضخيم» درجة بالمجموعات الحاضرة يمر صامتًا (سبب رفض D-03 للمتوسط
    البسيط).
    """

    #: المجموعات ذات العضو المؤهل (|c_i| > 0) بترتيب §19.3 الحتمي.
    present_groups: tuple[EvidenceGroup, ...]
    #: المجموعات الخالية من الدليل المؤهل — حصصها أُعيد توزيعها.
    absent_groups: tuple[EvidenceGroup, ...]
    #: الحصص الافتراضية §19.3 كما دخلت الحساب (قبل إعادة التوزيع).
    default_shares: dict[EvidenceGroup, float]
    #: الحصص الفعلية بعد إعادة التوزيع التناسبي (للحاضرة حصرًا) —
    #: مجموعها 1.0 عند وجود مجموعة حاضرة واحدة على الأقل.
    effective_shares: dict[EvidenceGroup, float]
    #: مجموع الحصص المعاد توزيعها (حصص الغائبات مجتمعة).
    redistributed_share: NonNegativeFloat


class GroupScore(_FusionModel):
    """درجة مجموعة واحدة — الشفافية الرقمية الكاملة لخطوة الدمج.

    «درجة المجموعة = مجموع مساهمات أعضائها المؤهلين مطبَّقًا عليها سقف
    المجموعة (الحصة الافتراضية §19.3) بآلية تشبع tanh» (D-03-أ):
    ``score = effective_share × tanh(raw_sum / effective_share)`` —
    القيمة داخل (−effective_share, +effective_share) حتمًا مهما كثر
    الأعضاء أو ضخمت مساهماتهم.
    """

    group: EvidenceGroup
    #: عدد الأعضاء المؤهلين (|c_i| > 0) داخل المجموعة.
    qualified_count: int
    #: مجموع مساهمات الأعضاء الموقعة قبل السقف (يتضمن المعارضة السالبة).
    raw_sum: FiniteFloat
    #: الحصة الفعلية بعد إعادة التوزيع — سقف tanh للمجموعة.
    effective_share: UnitInterval
    #: الدرجة المسقوفة داخل (−effective_share, +effective_share).
    score: FiniteFloat


class CalibrationReport(_FusionModel):
    """تقرير المعايرة (§19.6) — «الدرجة الخام ليست احتمالًا» أبدًا.

    البنية مكتملة من day-one والملء مشروط: ``eligible=False`` حصرًا حتى
    تتوفر بيانات خارج العينة كافية لمعاير صريح (isotonic/Platt) على
    بيانات لم تُستخدم في تحسين الدرجة الخام — مسؤولية الإعادة والوسم
    (المرحلة 9). «الدرجة الخام لا توصف بأنها فرصة 94٪ أبدًا» (§19.6).
    """

    #: هل صارت الدرجة قابلة للترجمة احتمالًا معايرًا؟ False حتى المرحلة 9.
    eligible: bool = False
    #: الاحتمال المعاير — لا يظهر إلا عند eligible=True (§19.6).
    calibrated_probability: UnitInterval | None = None
    #: حجم عينة المعايرة — صفر حتى يُبنى جهاز المعايرة.
    calibration_sample_size: int = 0
    #: النظام الذي عُاير ضمنه (معايرة لكل نظام §19.6) — None بعد.
    calibration_regime: str | None = None
    #: سبب التأجيل موثقًا صراحة — إلزامي ما دام eligible=False: لا صمت.
    deferral_reason: str


class FusionSnapshot(_FusionModel):
    """لقطة دمج واحدة — النتيجة الكاملة القابلة للأرشفة والتفسير.

    مركز مخرجات المرحلة 6: تُحسب من سلسلة EvidenceRecord حتمية
    (c_i بمعادلة §19.2 حرفيًا) وتُخزن في fusion_snapshots وتُقرأ سلسلة
    الدليل كاملة (السجلات + اللقطة) باستعلام واحد — بوابة الخروج 6.
    """

    scenario_id: str
    direction: Direction
    #: لحظة الدمج المرجعية (طراوة الدليل تُقاس إليها — لا ساعة داخلية).
    fusion_time: UTCDatetime
    #: درجات المجموعات الحاضرة بترتيب §19.3 — الغائبات في التوقيع.
    group_scores: tuple[GroupScore, ...]
    #: الدرجة الخام الكلية ∈ (−1, +1) — «ليست احتمالًا» (§2.6/§19.6).
    raw_evidence_score: SignedUnit
    #: مجموع |c_i| للمساندة الخام (قبل السقف) — شفافية ما قبل الدمج.
    support_contribution: NonNegativeFloat
    #: مجموع |c_i| للمعارضة الخام (قبل السقف) — §19.5 صريح لا مضمَّر.
    opposition_contribution: NonNegativeFloat
    #: معرفات سجلات المعارضة — «قائمة معارضة صريحة داخل السيناريو» (§19.5).
    opposition_evidence_ids: tuple[str, ...]
    #: سلسلة الدليل كاملة بترتيب الإدخال — هوية اللقطة القابلة للتتبع.
    evidence_ids: tuple[str, ...]
    #: توقيع الإتاحة (D-03-ب) — من حضر ومن غاب وبأي حصص.
    availability: AvailabilitySignature
    #: الـveto منطق بولياني خارج الحساب كليًا (D-03-د): يُعلن ولا يعدل
    #: الدرجة — الاستهلاك (الترخيص) مسؤولية المراحل 7/8.
    vetoed: bool
    veto_reasons: tuple[str, ...]
    calibration: CalibrationReport


class ExplanationObject(_FusionModel):
    """كائن التفسير (§2.8 حرفيًا) — يرافق كل نية تداول وكل رفض.

    «Every trade intent must have an explanation object containing: market
    context, liquidity map, structural state, supporting evidence, opposing
    evidence, trigger, invalidation, expected path, cost estimate, and
    reason for rejection when no trade is taken» — الحقول العشرة بالترتيب.
    المرحلة 6 تبني الكائن من لقطة الدمج والسياق المتاح؛ الحقول التي
    تملؤها مراحل لاحقة تحمل نص التأجيل الصريح (لا فراغ صامت): تقدير
    التكاليف §25.2 يُستكمل في المرحلة 8، والمشغل الحي في المرحلة 7.
    """

    market_context: str
    liquidity_map: str
    structural_state: str
    supporting_evidence: tuple[str, ...]
    opposing_evidence: tuple[str, ...]
    trigger: str
    invalidation: str
    expected_path: str
    cost_estimate: str
    #: سبب الرفض عند عدم أخذ صفقة — «reason for rejection when no trade
    #: is taken»؛ None ما دام القرار لم يُرفض.
    rejection_reason: str | None = None


def validate_explanation_completeness(explanation: ExplanationObject, *, rejected: bool) -> None:
    """الفحص الآلي لاكتمال حقول التفسير (build_plan 6.5).

    يشترط: كل الحقول النصية غير فارغة (بعد تقليم الفراغات)، وقائمتا
    الدليل حاضرتان (قد تكون إحداهما فارغة عند انعدام المعارضة — ذلك
    دليل لا نقص توثيق)، و``rejection_reason`` إلزامي عند الرفض وممنوع
    الحضور عند عدمه.

    :raises ValueError: أول حقل ناقص باسمه — رسالة صاخبة لا صمت موافقة.
    """
    text_fields = (
        "market_context",
        "liquidity_map",
        "structural_state",
        "trigger",
        "invalidation",
        "expected_path",
        "cost_estimate",
    )
    for field in text_fields:
        if not getattr(explanation, field).strip():
            raise ValueError(f"حقل التفسير «{field}» فارغ — §2.8 يلزم كائن شرح مكتمل الحقول")
    if rejected and (
        explanation.rejection_reason is None or not explanation.rejection_reason.strip()
    ):
        raise ValueError("قرار مرفوض بلا rejection_reason — «reason for rejection» إلزامي (§2.8)")
    if not rejected and explanation.rejection_reason is not None:
        raise ValueError("rejection_reason حاضر بلا رفض — التوثيق الصادق لا يخترع رفضًا (§2.8)")
