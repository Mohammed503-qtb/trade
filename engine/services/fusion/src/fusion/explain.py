"""كائن التفسير (§2.8) — بناء شرح كل قرار من لقطة الدمج وسجلها.

«Every trade intent must have an explanation object containing: market
context, liquidity map, structural state, supporting evidence, opposing
evidence, trigger, invalidation, expected path, cost estimate, and reason
for rejection when no trade is taken» — الحقول العشرة بالترتيب.

مبدأ البناء: **المشتق قبل المُمرر** — ما يمكن اشتقاقه حتميًا من لقطة
الدمج وسجلها يُشتق (سلسلتا المساندة والمعارضة سطرًا لكل دليل بإسهامه
الموقعة، والسياق من لقطة الحالة، وحالة البنية من درجة مجموعتها)، وما
تملكه مراحل لاحقة يمرر صريحًا أو يوثق غيابه بتأجيل معلن (المشغل
والإبطال: مقترحات المرحلة 7 D-04؛ تقدير التكاليف: المرحلة 8 §25.2) —
لا فراغ صامت ولا اختلاق.

كل نص مشتق حتمي تمامًا: من حقول النماذج بتنسيق ثابت — بلا ساعة ولا
عشوائية — فتفسير الإعادة يطابق تفسير الحياة بايت-بايت.
"""

from __future__ import annotations

from collections.abc import Sequence

from schemas import (
    EvidenceGroup,
    EvidenceRecord,
    ExplanationObject,
    FusionSnapshot,
    MarketStateSnapshot,
)

__all__ = ["build_explanation"]

#: تأجيلات موثقة للحقول التي تملكها مراحل لاحقة — نص ثابت واحد يمنع
#: تفرق الصياغات (نمط CALIBRATION_DEFERRAL_REASON).
_TRIGGER_DEFERRAL = (
    "المشغل القابل للرصد تعرفه مقترحات السيناريو (المرحلة 7 — D-04): "
    "لا سيناريو بلا موقع وآلية ومطلق وإبطال، والتوصيل لم يبن بعد"
)
_INVALIDATION_DEFERRAL = (
    "قاعدة الإبطال البنيوية (§18.5 + §23.4: بنية + هامش تقلب + شرط قبول) "
    "تعرّفها دورة حياة السيناريو — المرحلة 7"
)
_PATH_DEFERRAL = (
    "المسار المتوقع نحو أهداف سيولة معرّفة (§10.5) يكتمل مع مقترحات السيناريو — المرحلة 7"
)
_COST_DEFERRAL = (
    "تقدير التكاليف الصافية (§25.2 بأنماطها الثلاثة) مسؤولية وحدة "
    "المخاطرة — المرحلة 8: لا تقدير تكاليف بعد"
)
_NO_STATE_NOTE = "بلا لقطة حالة سوق ممررة عند الدمج — السياق النظامي غير متوفر لهذه اللقطة"


def _fmt(value: float) -> str:
    """تنسيق رقمي حتمي — إشارة دائمًا وأربع منازل."""
    return f"{value:+.4f}"


def _evidence_lines(records: Sequence[EvidenceRecord], *, opposition: bool) -> tuple[str, ...]:
    """سطر لكل دليل: النوع والمصدر والمساهمة الموقعة — بترتيب السجل."""
    selected = [record for record in records if record.opposition is opposition]
    return tuple(
        f"{record.event_type.value} [{record.source}] c_i={_fmt(_signed_contribution(record))}"
        for record in selected
    )


def _signed_contribution(record: EvidenceRecord) -> float:
    """المساهمة الموقعة للسجل — معادلة §19.2 (مرجع compute.contribution)."""
    return (
        record.prior_weight
        * record.direction_score
        * record.raw_strength
        * record.quality
        * record.freshness
        * record.independence_discount
        * record.context_modifier
    )


def _group_summary(snapshot: FusionSnapshot, group: EvidenceGroup) -> str:
    """حالة مجموعة دليل من اللقطة — حضورها ودرجتها وسقفها الفعلي."""
    for item in snapshot.group_scores:
        if item.group is group:
            return (
                f"حاضرة بدليل صافٍ {_fmt(item.raw_sum)} (عضو مؤهل: "
                f"{item.qualified_count}) ودرجة مسقوفة {_fmt(item.score)} "
                f"من سقف {item.effective_share:.4f}"
            )
    return f"غائبة من الدليل المؤهل ({group.value}) — حصتها أُعيد توزيعها"


def build_explanation(
    snapshot: FusionSnapshot,
    records: Sequence[EvidenceRecord],
    *,
    market_state: MarketStateSnapshot | None = None,
    market_context: str | None = None,
    liquidity_map: str | None = None,
    structural_state: str | None = None,
    trigger: str | None = None,
    invalidation: str | None = None,
    expected_path: str | None = None,
    cost_estimate: str | None = None,
    rejection_reason: str | None = None,
) -> ExplanationObject:
    """كائن التفسير §2.8 من لقطة دمج وسجلها.

    :param snapshot: لقطة الدمج — مصدر الحساب الموثق.
    :param records: سجل الدليل بترتيب الإدخال (نفس مدخلات الحساب) —
        سلسلتا المساندة والمعارضة تشتقان منه.
    :param market_state: لقطة الحالة عند الدمج — سياق موثق إن توفر.
    :param market_context: صياغة سياق ممررة تتقدم الاشتقاق إن أعطيت.
    :param liquidity_map: خريطة السيولة (تُملأ بمحتوى أغنى من مقترحات
        المرحلة 7) — وإلا فملخص مجموعة السيولة/الموقع من اللقطة.
    :param structural_state: الحالة البنيوية — وإلا فملخص مجموعة البنية.
    :param trigger: المشغل (D-04 — المرحلة 7) — وإلا فتأجيل موثق.
    :param invalidation: الإبطال (§18.5) — وإلا فتأجيل موثق.
    :param expected_path: المسار المتوقع (§10.5) — وإلا فتأجيل موثق.
    :param cost_estimate: تقدير التكاليف (§25.2 — المرحلة 8) — وإلا
        فتأجيل موثق.
    :param rejection_reason: سبب الرفض عند عدم أخذ صفقة — يمرر كما هو
        (None ما لم يُرفض).
    """
    if market_context is not None:
        context_line = market_context
    elif market_state is not None:
        context_line = (
            f"{market_state.regime.value}، تقلب مئينه "
            f"{market_state.volatility_percentile:.1f}، جودة "
            f"{market_state.data_quality.value}، انحياز الإطار الأعلى "
            f"{market_state.htf_bias.value} ({market_state.timeframe})"
        )
    else:
        context_line = _NO_STATE_NOTE

    return ExplanationObject(
        market_context=context_line,
        liquidity_map=liquidity_map
        if liquidity_map is not None
        else f"مجموعة السيولة/الموقع: {_group_summary(snapshot, EvidenceGroup.LIQUIDITY_LOCATION)}",
        structural_state=structural_state
        if structural_state is not None
        else f"مجموعة البنية: {_group_summary(snapshot, EvidenceGroup.STRUCTURE)}",
        supporting_evidence=_evidence_lines(records, opposition=False),
        opposing_evidence=_evidence_lines(records, opposition=True),
        trigger=trigger if trigger is not None else _TRIGGER_DEFERRAL,
        invalidation=invalidation if invalidation is not None else _INVALIDATION_DEFERRAL,
        expected_path=expected_path if expected_path is not None else _PATH_DEFERRAL,
        cost_estimate=cost_estimate if cost_estimate is not None else _COST_DEFERRAL,
        rejection_reason=rejection_reason,
    )
