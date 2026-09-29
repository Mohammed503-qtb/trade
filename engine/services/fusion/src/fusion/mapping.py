"""خريطة الدليل — تجميع أنواع §20 في مجموعات §19.3 واستخلاص القطبية والقوة.

قلب المهمة 6.1: كل نوع من أنواع القاموس الخمسة والأربعين موطَّن في إحدى
مجموعات الدليل الست (أو في خانة الحجب الصلب — ليس دليلًا اتجاهيًا أصلًا)،
والقطبية تُستخرج من حقول الحمولة نفسها لا من جدول مختلق: الحمولة موثقة
النموذج (EVENT_PAYLOAD_MODELS) وقيمها هي القياس.

مصدر القوة لكل نوع هو «Primary measurement» العمودي في §20 حرفيًا:
قياسات الحمولة المطبَّعة أصلًا (ATR-relative / نِسَب / مئينات) تمر كما
هي، وغير المحدودة تُشبَع بـ``saturate`` (دالة رتيبة حتمية إلى [0, 1]).

الأنواع بلا حمولة موثقة بعد (HTF كحدث بثّ، POC/VA §12.5، الهارمونيك
5b، الجلسات والتقلب كأحداث، الكلي) موطَّنة في الخريطة استباقيًا —
محرك البناء يرفضها صاخبة إن وصلت بلا حمولة: الغياب إعلان صريح لا صمت
موافقة.
"""

from __future__ import annotations

from schemas import (
    DEFAULT_EVENT_WEIGHTS,
    EventType,
    EvidenceGroup,
    HTFBias,
)
from schemas.liquidity import BreakAcceptEventPayload, LiquiditySide, SweepEventPayload
from schemas.orderflow import (
    AbsorbedPressure,
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    FlowDirection,
    ImbalanceClusterEventPayload,
    ImbalanceSide,
)
from schemas.patterns import (
    CandlePatternEventPayload,
    ClassicalPatternEventPayload,
    PatternDirection,
)
from schemas.structure import (
    BreakDirection,
    DisplacementEventPayload,
    FvgDirection,
    FvgEventPayload,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    StructureBreakPayload,
    StructureConsequence,
)

__all__ = [
    "EVENT_EVIDENCE_GROUPS",
    "GROUP_ORDER",
    "HARD_BLOCK_EVENT_TYPES",
    "extract_polarity",
    "extract_raw_strength",
    "htf_event_for_bias",
    "prior_weight_for",
    "saturate",
]

# ───────────────────────── الخريطة الكاملة §19.3 ─────────────────────────

#: نوع الحدث → مجموعة الدليل — التقسيم بحرفية أعمدة «Purpose» في §19.3:
#: البنية (HTF/BOS/CHoCH/إزاحة)، السيولة والموقع (مناطق/sweep/FVG/OB/
#: premium-discount)، التدفق (دلتا/امتصاص/POC-VA/اختلالات)، حركة السعر
#: (شموع/كلاسيكي/هارمونيك)، التقلب والجلسة (نظام وسياق تنفيذ)، الكلي.
EVENT_EVIDENCE_GROUPS: dict[EventType, EvidenceGroup] = {
    # STRUCTURE — «HTF/MTF structure, BOS, CHoCH, displacement»
    EventType.HTF_BULLISH: EvidenceGroup.STRUCTURE,
    EventType.HTF_BEARISH: EvidenceGroup.STRUCTURE,
    EventType.INTERNAL_BOS: EvidenceGroup.STRUCTURE,
    EventType.EXTERNAL_BOS: EvidenceGroup.STRUCTURE,
    EventType.CHOCH: EvidenceGroup.STRUCTURE,
    EventType.DISPLACEMENT_UP: EvidenceGroup.STRUCTURE,
    EventType.DISPLACEMENT_DOWN: EvidenceGroup.STRUCTURE,
    # LIQUIDITY_LOCATION — «liquidity zones, sweeps, FVG/OB location,
    # premium/discount» (كسر القمة/القاع بقبول هو استهلاك سيولة لا بنية)
    EventType.LIQUIDITY_SWEEP_HIGH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.LIQUIDITY_SWEEP_LOW: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.BREAK_AND_ACCEPT_HIGH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.BREAK_AND_ACCEPT_LOW: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.FVG_BULLISH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.FVG_BEARISH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.ORDER_BLOCK_BULLISH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.ORDER_BLOCK_BEARISH: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.PREMIUM_LOCATION: EvidenceGroup.LIQUIDITY_LOCATION,
    EventType.DISCOUNT_LOCATION: EvidenceGroup.LIQUIDITY_LOCATION,
    # ORDER_FLOW — «delta, absorption, POC/VA, imbalances»
    EventType.ABSORPTION_BUY: EvidenceGroup.ORDER_FLOW,
    EventType.ABSORPTION_SELL: EvidenceGroup.ORDER_FLOW,
    EventType.FLOW_CONTINUATION_UP: EvidenceGroup.ORDER_FLOW,
    EventType.FLOW_CONTINUATION_DOWN: EvidenceGroup.ORDER_FLOW,
    EventType.EXHAUSTION_UP: EvidenceGroup.ORDER_FLOW,
    EventType.EXHAUSTION_DOWN: EvidenceGroup.ORDER_FLOW,
    EventType.POC_ACCEPTANCE: EvidenceGroup.ORDER_FLOW,
    EventType.POC_REJECTION: EvidenceGroup.ORDER_FLOW,
    EventType.VAH_REJECTION: EvidenceGroup.ORDER_FLOW,
    EventType.VAL_REJECTION: EvidenceGroup.ORDER_FLOW,
    EventType.BUY_IMBALANCE_CLUSTER: EvidenceGroup.ORDER_FLOW,
    EventType.SELL_IMBALANCE_CLUSTER: EvidenceGroup.ORDER_FLOW,
    # PRICE_ACTION — «candles, classical, harmonics»
    EventType.BULLISH_ENGULFING: EvidenceGroup.PRICE_ACTION,
    EventType.BEARISH_ENGULFING: EvidenceGroup.PRICE_ACTION,
    EventType.REJECTION_CANDLE: EvidenceGroup.PRICE_ACTION,
    EventType.INSIDE_BAR_BREAK: EvidenceGroup.PRICE_ACTION,
    EventType.CLASSICAL_BREAKOUT: EvidenceGroup.PRICE_ACTION,
    EventType.CLASSICAL_FAILED_BREAKOUT: EvidenceGroup.PRICE_ACTION,
    EventType.HARMONIC_COMPLETION: EvidenceGroup.PRICE_ACTION,
    # VOLATILITY_SESSION — «regime and execution context»
    EventType.RANGE_COMPRESSION: EvidenceGroup.VOLATILITY_SESSION,
    EventType.RANGE_EXPANSION: EvidenceGroup.VOLATILITY_SESSION,
    EventType.SESSION_OPENING_DRIVE: EvidenceGroup.VOLATILITY_SESSION,
    EventType.SESSION_REVERSAL: EvidenceGroup.VOLATILITY_SESSION,
    # MACRO — «macro regime and event-risk context only»
    EventType.MACRO_HIGH_IMPACT_NEAR: EvidenceGroup.MACRO,
}

#: الحجب الصلب (§20 وزن None): ليس دليلًا اتجاهيًا ولا يدخل سجل الدليل
#: أبدًا — منطق بولياني خارج الحساب كليًا (D-03-د). المرحلة 8 تبني
#: اختباراتها الخمسة عشر §22.1؛ هنا توطينها حتى لا يمر نوع حجب كدليل.
HARD_BLOCK_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.DATA_STALE,
        EventType.SPREAD_EXTREME,
        EventType.LATENCY_EXTREME,
        EventType.RISK_LIMIT_REACHED,
    }
)

#: ترتيب المجموعات الحتمي — ترتيب ظهورها في جدول §19.3 (يحكم ترتيب
#: group_scores في اللقطة وترتيب توقيع الإتاحة).
GROUP_ORDER: tuple[EvidenceGroup, ...] = (
    EvidenceGroup.STRUCTURE,
    EvidenceGroup.LIQUIDITY_LOCATION,
    EvidenceGroup.ORDER_FLOW,
    EvidenceGroup.PRICE_ACTION,
    EvidenceGroup.VOLATILITY_SESSION,
    EvidenceGroup.MACRO,
)


def saturate(value: float) -> float:
    """تشبع رتبي حتمي للقياسات الموجبة غير المحدودة إلى [0, 1).

    ``x / (1 + x)``: صفر يبقى صفرًا، والقيمة تناهى إلى 1 دون بلوغها —
    رتيبة صارمة (لا قفزات) وبلا معاملات (لا عتبات كونية مختلقة). القياس
    المطبَّع أصلًا (نِسَب [0,1]) لا يمر من هنا أصلًا.
    """
    if value < 0.0:
        raise ValueError(f"saturate لقياس موجب حصرًا — وُجد {value}")
    return value / (1.0 + value)


def htf_event_for_bias(bias: HTFBias) -> EventType | None:
    """حدث §20 الموازي لحالة انحياز الإطار الأعلى — None لغير المؤكد.

    الانحياز المنشور في لقطة الحالة (§9.2: «HTF bias is contextual
    evidence») يدخل الدمج دليلًا مشتقًا من الحالة بمصدر موثق
    ``market_state.htf_bias`` — NEUTRAL/TRANSITION/UNKNOWN ليست دليلًا
    اتجاهيًا فتُعاد None (إعلان صريح لا صمت).
    """
    if bias is HTFBias.BULLISH:
        return EventType.HTF_BULLISH
    if bias is HTFBias.BEARISH:
        return EventType.HTF_BEARISH
    return None


# ───────────────────────── القطبية من الحمولة ─────────────────────────


def extract_polarity(event_type: EventType, payload: object) -> int:
    """قطبية الحدث الذاتية ∈ {−1, 0, +1} — من حقول الحمولة حصرًا.

    الموجب = دلالة صاعدة، السالب = دلالة هابطة، الصفر = سياقي لا اتجاه.
    الاتجاه النسبي للسيناريو (المساندة/المعارضة §19.5) يحسبه باني السجل
    لا هذه الدالة — القطبية خاصية الحدث، والاصطفاف خاصية السيناريو.
    """
    # ── البنية: كسور واتجاهات صريحة في الحمولة ──
    if isinstance(payload, StructureBreakPayload):
        return 1 if payload.break_direction is BreakDirection.UP else -1
    if isinstance(payload, DisplacementEventPayload):
        return 1 if payload.direction is BreakDirection.UP else -1
    if isinstance(payload, FvgEventPayload | OrderBlockEventPayload):
        return 1 if payload.direction is FvgDirection.BULLISH else -1
    if isinstance(payload, PremiumDiscountEventPayload):
        # §11.7: فوق المنصف premium (سياق بيع) وتحته discount (سياق شراء).
        return -1 if payload.location is PremiumDiscountSide.PREMIUM else 1

    # ── السيولة: موقع الاجتياح/القبول يحدد الدلالة ──
    if isinstance(payload, SweepEventPayload):
        # اجتياح سيولة شرائية عند القمم ثم رفض ⇒ دلالة هابطة؛ بيعية عند
        # القيعان ثم رفض ⇒ صاعدة (كاشف 3-d: الاسترجاع إغلاق خلف الحافة
        # القريبة في وجهة الرفض).
        return -1 if payload.zone_side is LiquiditySide.BUY_SIDE else 1
    if isinstance(payload, BreakAcceptEventPayload):
        # قبول خلف الحافة البعيدة: فوق القمم ⇒ صاعدة، تحت القيعان ⇒ هابطة.
        return 1 if payload.zone_side is LiquiditySide.BUY_SIDE else -1

    # ── التدفق: جهة العدوان/الجهد المنهَك ──
    if isinstance(payload, AbsorptionEventPayload):
        # امتصاص ضغط بيعي ⇒ صاعد؛ شرائي ⇒ هابط (النوعان §20 حرفيًا).
        return 1 if payload.absorbed_pressure is AbsorbedPressure.SELL else -1
    if isinstance(payload, FlowContinuationEventPayload):
        return 1 if payload.direction is FlowDirection.UP else -1
    if isinstance(payload, ExhaustionEventPayload):
        # إنهاك جهد صاعد يقوّض الاستمرار الصاعد ⇒ دلالة هابطة، وبالعكس.
        return -1 if payload.direction is FlowDirection.UP else 1
    if isinstance(payload, ImbalanceClusterEventPayload):
        return 1 if payload.side is ImbalanceSide.BUY else -1

    # ── الأنماط ──
    if isinstance(payload, CandlePatternEventPayload):
        if payload.direction is PatternDirection.BULLISH:
            return 1
        if payload.direction is PatternDirection.BEARISH:
            return -1
        return 0
    if isinstance(payload, ClassicalPatternEventPayload):
        up = payload.break_direction is BreakDirection.UP
        if event_type is EventType.CLASSICAL_FAILED_BREAKOUT:
            # فشل الكسر يقلب الدلالة: كسر صاعد استُرجع ⇒ دليل هبوط (§20
            # «Break + reclaim»).
            return -1 if up else 1
        return 1 if up else -1

    raise ValueError(
        f"نوع بلا مستخلص قطبية موثق: {event_type} مع حمولة {type(payload).__name__} — "
        "الأنواع بلا حمولة §20 (POC/VA، الهارمونيك، الجلسات، الكلي) لا تدخل "
        "السجل حتى توثق حمولتها (غياب الحمولة إعلان صريح لا صمت موافقة)"
    )


# ───────────────────────── القوة من الحمولة ─────────────────────────

#: سلّم النتيجة البنيوية لإزاحة الـOrder Block (§11.6 خطوة 3) — القياس
#: «Displacement consequence» في §20: رتبي موثق لا مستويات مختلقة.
_OB_CONSEQUENCE_STRENGTH: dict[StructureConsequence, float] = {
    StructureConsequence.NONE_YET: 0.5,  # تحقق لم يكتمل — المنطقة صالحة
    # بناؤها (الإزاحة المولِّدة إلزامية في الحمولة) لكن بلا نتيجة موثقة.
    StructureConsequence.LIQUIDITY_INTERACTION: 0.75,  # تفاعل سيولة معنوي.
    StructureConsequence.BOS: 1.0,  # كسر بنية مؤكد — اكتمال الخطوة 3.
}


def extract_raw_strength(event_type: EventType, payload: object) -> float:
    """قوة الحدث الخام ∈ [0, 1] — «Primary measurement» §20 حرفيًا.

    القياسات المطبَّعة أصلًا في الحمولة (نِسَب [0, 1]) تمر مباشرة؛
    والموجبة غير المحدودة (مضاعفات ATR، z-score، كفاءة) تُشبَع بـ
    ``saturate``. الجدول الكامل موثق في كل فرع أدناه بمرجعه.
    """
    # ── البنية ──
    if isinstance(payload, StructureBreakPayload):
        # §20 INTERNAL/EXTERNAL_BOS وCHOCH: «Break distance / ATR».
        return saturate(payload.breach_distance_atr)
    if isinstance(payload, DisplacementEventPayload):
        # §20: «Range z-score, ATR multiple» — z-score المدى القياس الأنظف.
        return saturate(abs(payload.range_zscore))
    if isinstance(payload, FvgEventPayload):
        # §20: «Gap/ATR».
        return saturate(payload.size_atr)
    if isinstance(payload, OrderBlockEventPayload):
        # §20: «Displacement consequence + freshness» — سلّم النتيجة الرتبي.
        return _OB_CONSEQUENCE_STRENGTH[payload.structure_consequence]
    if isinstance(payload, PremiumDiscountEventPayload):
        # §20: «Normalized distance» — الإقصاء عن المنصف مقيدًا بالوحدة
        # (الخروج عن النطاق معلومة إضافية لا قوة أعلى).
        return min(abs(payload.normalized_distance), 1.0)

    # ── السيولة ──
    if isinstance(payload, SweepEventPayload):
        # §20: «Excursion, reclaim speed» — عمق التجاوز مشبعًا يضربه عامل
        # سرعة الاسترجاع (استرجاع فوري 0 ⇒ كامل؛ كل شمعة تأخير تنصّفه).
        return saturate(payload.excursion_atr) / (1.0 + float(payload.reclaim_bars))
    if isinstance(payload, BreakAcceptEventPayload):
        # §20: «Acceptance ratio» — مطبَّع أصلًا [0, 1] فيمر مباشرة.
        return float(payload.acceptance_ratio)

    # ── التدفق ──
    if isinstance(payload, AbsorptionEventPayload):
        # §20: «Delta vs excursion» — حصة الدلتا الممتصة من الحجم الكلي
        # هي حجم العدوان الممتص (جهة التباين مع الامتداد في الكاشف).
        return abs(float(payload.delta_share))
    if isinstance(payload, FlowContinuationEventPayload):
        # §20: «Delta efficiency» — استجابة لكل وحدة جهد.
        return saturate(float(payload.efficiency))
    if isinstance(payload, ExhaustionEventPayload):
        # §20: «Efficiency decay» — التراجع تحت الوحدة قوة إنهاك؛ وما
        # تحسن (≥ 1) ليس إنهاكًا فقوته صفر.
        return 1.0 - min(float(payload.decay_ratio), 1.0)
    if isinstance(payload, ImbalanceClusterEventPayload):
        # §20: «Imbalance density» — كثافة الاختلالات لكل شريط في العنقيد.
        return saturate(float(payload.total_imbalances) / float(payload.bar_count))

    # ── الأنماط ──
    if isinstance(payload, CandlePatternEventPayload):
        # §20 (Body ratio / Wick ratio / compression-expansion): ``strength``
        # الحمولة هو القياس العمودي الموحد [0, 1] من 5-b.
        return float(payload.strength)
    if isinstance(payload, ClassicalPatternEventPayload):
        if event_type is EventType.CLASSICAL_FAILED_BREAKOUT:
            # §20: «Failure speed» — جودة البنية مضروبة في عامل سرعة
            # الفشل (استرجاع فوري ⇒ الجودة كاملة؛ كل شمعة تنصّفها).
            return float(payload.quality) / (1.0 + float(payload.failure_speed or 0.0))
        # §20 CLASSICAL_BREAKOUT: «Break quality» — جودة §13.2 مباشرة.
        return float(payload.quality)

    raise ValueError(
        f"نوع بلا مستخلص قوة موثق: {event_type} مع حمولة {type(payload).__name__} — "
        "الأنواع بلا حمولة موثقة لا تدخل السجل (نمط رفض extract_polarity)"
    )


def prior_weight_for(event_type: EventType) -> float:
    """الوزن الابتدائي §20 — يرفض صاخبًا الحجب الصلب بلا وزن اتجاهي.

    ``DEFAULT_EVENT_WEIGHTS`` منسوخ من عمود Weight حرفيًا (المرحلة 0)؛
    None يعني HARD BLOCK — توجيهه إلى باني السجل خطأ معماري (D-03-د).
    """
    weight = DEFAULT_EVENT_WEIGHTS[event_type]
    if weight is None:
        raise ValueError(
            f"{event_type} حجب صلب (وزن None §20) — لا يدخل سجل الدليل: "
            "veto منطق بولياني خارج الحساب كليًا (D-03-د)"
        )
    return weight
