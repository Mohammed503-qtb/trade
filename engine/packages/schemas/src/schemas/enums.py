"""كل تعدادات المحرك — منقولة حرفيًا من Master Plan.

كل تعدادة StrEnum بقيم UPPERCASE كما وردت في الخطة:
- DataQuality التسع حالات (§7.4)
- SignalState الأربع (§27.1)
- Direction (§2/§18)
- HTFBias (§9.2) وMarketRegime (§9.3) وSessionType (§9.4 + A-03)
- EvidenceGroup الست (§19.3) مع الحصص الافتراضية
- EventType — قاموس الأحداث كاملًا (§20) حرفيًا
- ScenarioState (§18.2) وOrderPolicy (§24.2)
- HardBlockReason الخمسة عشر (§22.1) وSweepClassification (§10.4)
- SoftSuppressionReason العشرة وNoTradeSeverity (§22.2/§22.3)
- CostMode الثلاثة (§25.1) وRejectionBasis وSizingModifierName الستة (§23.2)
- SizingCapBasis (§23.2 «capped by absolute portfolio and instrument limits»)

الثوابت الرقمية (حصص المجموعات §19.3 وأوزان الأحداث §20) منقولة حرفيًا مع
تعليق الفقرة — لا قيمة مختلقة هنا أبدًا.
"""

from __future__ import annotations

from enum import StrEnum


class DataQuality(StrEnum):
    """حالات جودة البيانات التسع لكل شريحة أداة/زمن (§7.4).

    فقط HEALTHY وDELAYED (بموافقة صريحة) يصلان معالجة القرار العادية.
    """

    HEALTHY = "HEALTHY"
    DELAYED = "DELAYED"
    PARTIAL = "PARTIAL"
    DUPLICATED = "DUPLICATED"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    STALE = "STALE"
    GAP_DETECTED = "GAP_DETECTED"
    UNAVAILABLE = "UNAVAILABLE"
    QUARANTINED = "QUARANTINED"


class SignalState(StrEnum):
    """حالات الإشارة الأربع في الزمن الحقيقي (§27.1) — فصل المتطور عن المؤكد.

    DEVELOPING معلوماتي فقط ولا يفوّض أمرًا حيًا؛ CONFIRMED وحده مؤهل
    للمعالجة العادية.
    """

    DEVELOPING = "DEVELOPING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    RETRACTED = "RETRACTED"


class Direction(StrEnum):
    """الاتجاه الاتجاهي المثالث — LONG/SHORT وFLAT للحياد الصريح."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class HTFBias(StrEnum):
    """انحياز الإطار الأعلى كحالة موضعية (§9.2) — دليل سياقي لا مشغّل تداول."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class MarketRegime(StrEnum):
    """تصنيف نظام السوق (§9.3) — القيم الثماني حرفيًا."""

    TREND_EXPANSION = "TREND_EXPANSION"
    TREND_PULLBACK = "TREND_PULLBACK"
    RANGE_BALANCE = "RANGE_BALANCE"
    RANGE_EXPANSION = "RANGE_EXPANSION"
    COMPRESSION = "COMPRESSION"
    VOLATILITY_SHOCK = "VOLATILITY_SHOCK"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class SessionType(StrEnum):
    """أنواع الجلسات (§9.4 + قرار A-03 في plan_review).

    §9.4 لا يعطي قيمًا حرفية؛ A-03 يحسم: الجلسة = حدود يوم UTC (UTC_DAY)
    + ساعات سياق سلوكي اختيارية (آسيا/أوروبا/أمريكا) + نوافذ صيانة المنصة.
    الجلسة بيانات سياقية لا إشارة اتجاه بذاتها.
    """

    UTC_DAY = "UTC_DAY"
    ASIA = "ASIA"
    EUROPE = "EUROPE"
    AMERICA = "AMERICA"
    MAINTENANCE = "MAINTENANCE"


class EvidenceGroup(StrEnum):
    """مجموعات الدليل الست (§19.3) — تجميع لتجنب العد المزدوج (§2.3)."""

    STRUCTURE = "STRUCTURE"
    LIQUIDITY_LOCATION = "LIQUIDITY_LOCATION"
    ORDER_FLOW = "ORDER_FLOW"
    PRICE_ACTION = "PRICE_ACTION"
    VOLATILITY_SESSION = "VOLATILITY_SESSION"
    MACRO = "MACRO"


# الحصص الافتراضية للمجموعات (§19.3 حرفيًا) — «starting priors» لا حقائق
# دائمة؛ تُعاد اختبارها في دفتر التجارب وتُدار إصداريًا عبر parameter_sets.
DEFAULT_GROUP_SHARES: dict[EvidenceGroup, float] = {
    EvidenceGroup.STRUCTURE: 0.25,  # بنية HTF/MTF، BOS، CHoCH، إزاحة
    EvidenceGroup.LIQUIDITY_LOCATION: 0.20,  # مناطق سيولة، sweep، FVG/OB، premium/discount
    EvidenceGroup.ORDER_FLOW: 0.30,  # دلتا، امتصاص، POC/VA، اختلالات
    EvidenceGroup.PRICE_ACTION: 0.10,  # شموع، كلاسيكي، هارمونيك
    EvidenceGroup.VOLATILITY_SESSION: 0.10,  # نظام السوق وسياق التنفيذ
    EvidenceGroup.MACRO: 0.05,  # نظام كلي وسياق مخاطرة الأحداث فقط
}


class EventType(StrEnum):
    """قاموس الأحداث الإنتاجي الأولي (§20 حرفيًا — 45 نوعًا).

    لا يُختلق نوع حدث خارج هذا القاموس؛ الأوزان الافتراضية المرافقة في
    DEFAULT_EVENT_WEIGHTS أدناه منقولة من عمود Weight في §20.
    الأنواع الأربعة الأخيرة (None) ليست دليلًا اتجاهيًا بل حجبًا صلبًا (§22).
    """

    HTF_BULLISH = "HTF_BULLISH"  # بنية صاعدة مؤكدة للإطار الأعلى
    HTF_BEARISH = "HTF_BEARISH"  # بنية هابطة مؤكدة للإطار الأعلى
    INTERNAL_BOS = "INTERNAL_BOS"  # كسر بنية داخلية
    EXTERNAL_BOS = "EXTERNAL_BOS"  # كسر بنية خارجية بقبول
    CHOCH = "CHOCH"  # أول خرق ذو معنى لنمط الاستمرار السابق
    DISPLACEMENT_UP = "DISPLACEMENT_UP"  # اندفاع صاعد قوي
    DISPLACEMENT_DOWN = "DISPLACEMENT_DOWN"  # اندفاع هابط قوي
    LIQUIDITY_SWEEP_HIGH = "LIQUIDITY_SWEEP_HIGH"  # اجتياح سيولة شرائية ثم رفض
    LIQUIDITY_SWEEP_LOW = "LIQUIDITY_SWEEP_LOW"  # اجتياح سيولة بيعية ثم رفض
    BREAK_AND_ACCEPT_HIGH = "BREAK_AND_ACCEPT_HIGH"  # كسر قمة بقبول
    BREAK_AND_ACCEPT_LOW = "BREAK_AND_ACCEPT_LOW"  # كسر قاع بقبول
    ABSORPTION_BUY = "ABSORPTION_BUY"  # امتصاص ضغط بيعي
    ABSORPTION_SELL = "ABSORPTION_SELL"  # امتصاص ضغط شرائي
    FLOW_CONTINUATION_UP = "FLOW_CONTINUATION_UP"  # توافق التدفق والسعر صعودًا
    FLOW_CONTINUATION_DOWN = "FLOW_CONTINUATION_DOWN"  # توافق التدفق والسعر هبوطًا
    EXHAUSTION_UP = "EXHAUSTION_UP"  # فقدان الصعود فعاليته
    EXHAUSTION_DOWN = "EXHAUSTION_DOWN"  # فقدان الهبوط فعاليته
    FVG_BULLISH = "FVG_BULLISH"  # فجوة ثلاثية صاعدة
    FVG_BEARISH = "FVG_BEARISH"  # فجوة ثلاثية هابطة
    ORDER_BLOCK_BULLISH = "ORDER_BLOCK_BULLISH"  # منطقة مصدرية صاعدة قبل الإزاحة
    ORDER_BLOCK_BEARISH = "ORDER_BLOCK_BEARISH"  # منطقة مصدرية هابطة قبل الإزاحة
    PREMIUM_LOCATION = "PREMIUM_LOCATION"  # السعر فوق منصف نطاق المعالجة
    DISCOUNT_LOCATION = "DISCOUNT_LOCATION"  # السعر تحت منصف نطاق المعالجة
    POC_ACCEPTANCE = "POC_ACCEPTANCE"  # قبول حول POC
    POC_REJECTION = "POC_REJECTION"  # رفض من POC
    VAH_REJECTION = "VAH_REJECTION"  # رفض سقف القيمة
    VAL_REJECTION = "VAL_REJECTION"  # رفض أرضية القيمة
    BUY_IMBALANCE_CLUSTER = "BUY_IMBALANCE_CLUSTER"  # تكرار اختلالات شرائية صفّية
    SELL_IMBALANCE_CLUSTER = "SELL_IMBALANCE_CLUSTER"  # تكرار اختلالات بيعية صفّية
    BULLISH_ENGULFING = "BULLISH_ENGULFING"  # ابتلاع صاعد
    BEARISH_ENGULFING = "BEARISH_ENGULFING"  # ابتلاع هابط
    REJECTION_CANDLE = "REJECTION_CANDLE"  # شمعة رفض قوية
    INSIDE_BAR_BREAK = "INSIDE_BAR_BREAK"  # انضغاط ثم توسع
    CLASSICAL_BREAKOUT = "CLASSICAL_BREAKOUT"  # كسر بنية هندسية
    CLASSICAL_FAILED_BREAKOUT = "CLASSICAL_FAILED_BREAKOUT"  # كسر فاشل باسترجاع
    HARMONIC_COMPLETION = "HARMONIC_COMPLETION"  # اكتمال توافقي صالح
    RANGE_COMPRESSION = "RANGE_COMPRESSION"  # مزاد ضيق
    RANGE_EXPANSION = "RANGE_EXPANSION"  # توسع مرتفع
    SESSION_OPENING_DRIVE = "SESSION_OPENING_DRIVE"  # حركة اتجاهية مبكرة قوية
    SESSION_REVERSAL = "SESSION_REVERSAL"  # انعكاس الحركة المبكرة
    MACRO_HIGH_IMPACT_NEAR = "MACRO_HIGH_IMPACT_NEAR"  # حدث كلي عالي الأثر قريب
    DATA_STALE = "DATA_STALE"  # بيانات سوق راكدة — حجب صلب
    SPREAD_EXTREME = "SPREAD_EXTREME"  # فاتحة مرتفعة جدًا — حجب صلب
    LATENCY_EXTREME = "LATENCY_EXTREME"  # كمون تنفيذ غير آمن — حجب صلب
    RISK_LIMIT_REACHED = "RISK_LIMIT_REACHED"  # استنفاد ميزانية المخاطرة — حجب صلب


# الأوزان الافتراضية (عمود Weight في §20 حرفيًا) — «starting priors» تسبق
# معدّلات السياق والجودة، وليست نسب فوز. None = حجب صلب (ليس دليلًا اتجاهيًا).
# MACRO_HIGH_IMPACT_NEAR وزنه 0.00 لأنه يعدّل الأهلية والمخاطرة فقط (حاشية §20).
DEFAULT_EVENT_WEIGHTS: dict[EventType, float | None] = {
    EventType.HTF_BULLISH: 0.90,
    EventType.HTF_BEARISH: 0.90,
    EventType.INTERNAL_BOS: 0.80,
    EventType.EXTERNAL_BOS: 1.00,
    EventType.CHOCH: 0.75,
    EventType.DISPLACEMENT_UP: 0.90,
    EventType.DISPLACEMENT_DOWN: 0.90,
    EventType.LIQUIDITY_SWEEP_HIGH: 0.95,
    EventType.LIQUIDITY_SWEEP_LOW: 0.95,
    EventType.BREAK_AND_ACCEPT_HIGH: 0.85,
    EventType.BREAK_AND_ACCEPT_LOW: 0.85,
    EventType.ABSORPTION_BUY: 0.90,
    EventType.ABSORPTION_SELL: 0.90,
    EventType.FLOW_CONTINUATION_UP: 0.70,
    EventType.FLOW_CONTINUATION_DOWN: 0.70,
    EventType.EXHAUSTION_UP: 0.65,
    EventType.EXHAUSTION_DOWN: 0.65,
    EventType.FVG_BULLISH: 0.55,
    EventType.FVG_BEARISH: 0.55,
    EventType.ORDER_BLOCK_BULLISH: 0.65,
    EventType.ORDER_BLOCK_BEARISH: 0.65,
    EventType.PREMIUM_LOCATION: 0.35,
    EventType.DISCOUNT_LOCATION: 0.35,
    EventType.POC_ACCEPTANCE: 0.45,
    EventType.POC_REJECTION: 0.45,
    EventType.VAH_REJECTION: 0.40,
    EventType.VAL_REJECTION: 0.40,
    EventType.BUY_IMBALANCE_CLUSTER: 0.55,
    EventType.SELL_IMBALANCE_CLUSTER: 0.55,
    EventType.BULLISH_ENGULFING: 0.35,
    EventType.BEARISH_ENGULFING: 0.35,
    EventType.REJECTION_CANDLE: 0.30,
    EventType.INSIDE_BAR_BREAK: 0.35,
    EventType.CLASSICAL_BREAKOUT: 0.45,
    EventType.CLASSICAL_FAILED_BREAKOUT: 0.60,
    EventType.HARMONIC_COMPLETION: 0.45,
    EventType.RANGE_COMPRESSION: 0.45,
    EventType.RANGE_EXPANSION: 0.55,
    EventType.SESSION_OPENING_DRIVE: 0.45,
    EventType.SESSION_REVERSAL: 0.45,
    EventType.MACRO_HIGH_IMPACT_NEAR: 0.00,
    EventType.DATA_STALE: None,
    EventType.SPREAD_EXTREME: None,
    EventType.LATENCY_EXTREME: None,
    EventType.RISK_LIMIT_REACHED: None,
}


class ScenarioState(StrEnum):
    """دورة حياة السيناريو (§18.2) — السبعة الأساسية + النهايات الخمس البديلة.

    الدرب الأساسي: DRAFT → ACTIVE → TRIGGERED → AUTHORIZED → EXECUTING →
    IN_TRADE → COMPLETED. النهايات البديلة: INVALIDATED/EXPIRED/SUPPRESSED/
    REJECTED_BY_RISK/CANCELLED_BY_DATA_QUALITY (12 حالة إجمالًا).
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    IN_TRADE = "IN_TRADE"
    COMPLETED = "COMPLETED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    SUPPRESSED = "SUPPRESSED"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    CANCELLED_BY_DATA_QUALITY = "CANCELLED_BY_DATA_QUALITY"


class OrderPolicy(StrEnum):
    """سياسات التنفيذ الخمس (§24.2).

    الاستراتيجية تحدد السياسة المسموحة؛ محرك التنفيذ يختار أأمن تنفيذ
    صالح داخل تلك القيود.
    """

    MARKET_WITH_SLIPPAGE_GUARD = "MARKET_WITH_SLIPPAGE_GUARD"  # سوق مع حارس انزلاق أقصى
    LIMIT_AT_ZONE = "LIMIT_AT_ZONE"  # حد عند منطقة معرفة
    STAGED_LIMIT_MARKET = "STAGED_LIMIT_MARKET"  # توليفة مرحلية حد/سوق
    REDUCE_ONLY_EXIT = "REDUCE_ONLY_EXIT"  # خروج تقليلي فقط
    EMERGENCY_FLATTEN = "EMERGENCY_FLATTEN"  # تسطيح طارئ


class ScenarioTemplate(StrEnum):
    """قوالب السيناريو الثلاثة (§21.2 حرفيًا) — هوية مقترح D-04.

    «These are scenario templates, not hard-coded universal truths» — القالب
    سلسلة سببية موثقة تُستنسخ عند حدث مؤكد فوق موقع سيولة مرسوم، لا
    قاعدة تحكم جامدة.
    """

    #: انعكاس: سيولة كبرى ← اجتياح ← امتصاص/إنهاك ← إزاحة ← استرجاع
    #: بنية ← إعادة اختبار/مشغل (§21.2 Reversal candidate).
    REVERSAL = "REVERSAL"
    #: استمرار: بنية HTF مصطفة ← ارتداد لموقع موثق ← تدفق يعيد الاصطفاف
    #: ← BOS/إزاحة داخلية ← مشغل استمرار (§21.2 Continuation candidate).
    CONTINUATION = "CONTINUATION"
    #: اختراق: انضغاط ← بناء سيولة ← توسع ← قبول خلف الحافة ← إعادة
    #: اختبار/استمرار (§21.2 Breakout candidate).
    BREAKOUT = "BREAKOUT"


class SweepClassification(StrEnum):
    """تصنيف الاجتياح الخمسي (§10.4) — الاجتياح تسلسل لا فتيل واحد."""

    FAILED_SWEEP = "FAILED_SWEEP"
    PARTIAL_SWEEP = "PARTIAL_SWEEP"
    CONFIRMED_SWEEP = "CONFIRMED_SWEEP"
    BREAK_AND_ACCEPT = "BREAK_AND_ACCEPT"
    UNKNOWN = "UNKNOWN"


class HardBlockReason(StrEnum):
    """أسباب الحجب الصلب الخمسة عشر (§22.1 حرفيًا — بترقيم الخطة).

    أي سبب منها يمنع دخولًا جديدًا مهما بدت الدرجة الاتجاهية جذابة (§2.4).
    النص الإنجليزي الأصلي مثبت كتعليق فوق كل عضو.
    """

    # 1. Market data is stale, corrupted, duplicated beyond tolerance, or
    #    missing required fields.
    DATA_UNRELIABLE = "DATA_UNRELIABLE"
    # 2. Instrument status is halted, unavailable, or outside approved
    #    trading hours.
    INSTRUMENT_UNAVAILABLE = "INSTRUMENT_UNAVAILABLE"
    # 3. Execution venue connection is unhealthy.
    VENUE_CONNECTION_UNHEALTHY = "VENUE_CONNECTION_UNHEALTHY"
    # 4. Estimated spread exceeds the configured percentage of expected edge
    #    or stop distance.
    SPREAD_EXCEEDS_BUDGET = "SPREAD_EXCEEDS_BUDGET"
    # 5. Expected slippage exceeds the cost budget.
    SLIPPAGE_EXCEEDS_BUDGET = "SLIPPAGE_EXCEEDS_BUDGET"
    # 6. Execution latency exceeds the maximum allowed for the strategy
    #    horizon.
    LATENCY_EXCEEDS_BUDGET = "LATENCY_EXCEEDS_BUDGET"
    # 7. Position/risk limits have been reached.
    RISK_LIMITS_REACHED = "RISK_LIMITS_REACHED"
    # 8. A required stop cannot be reliably placed or reconciled.
    STOP_NOT_RELIABLE = "STOP_NOT_RELIABLE"
    # 9. Broker/exchange rejects the instrument or order type.
    BROKER_REJECTS_ORDER = "BROKER_REJECTS_ORDER"
    # 10. A high-impact scheduled event is inside the configured embargo
    #     window for the instrument.
    MACRO_EMBARGO_WINDOW = "MACRO_EMBARGO_WINDOW"
    # 11. Scenario invalidation has already occurred.
    SCENARIO_INVALIDATED = "SCENARIO_INVALIDATED"
    # 12. Entry is too late and remaining reward cannot compensate for
    #     execution costs.
    ENTRY_TOO_LATE = "ENTRY_TOO_LATE"
    # 13. Conflicting higher-priority scenario creates unresolved bilateral
    #     risk.
    CONFLICTING_SCENARIO = "CONFLICTING_SCENARIO"
    # 14. The same scenario was already consumed and no new structural
    #     information has formed.
    SCENARIO_ALREADY_CONSUMED = "SCENARIO_ALREADY_CONSUMED"
    # 15. The system is in emergency/kill-switch state.
    KILL_SWITCH = "KILL_SWITCH"


class SoftSuppressionReason(StrEnum):
    """الكتمات اللينة العشر (§22.2 حرفيًا — بنص الخطة).

    «The system may also decline when: ...» — ليست رفضًا صلبًا بل كتمًا
    موزونًا (§8.2 بأوزان إعدادية): تُجمع أوزان المشتعلة منها وتُقارن
    بعتبة؛ تجاوزها يمنع الدخول بأسباب موثقة كالصلب (§22.3) لكن مع
    قابلية إعادة المحاولة دائمًا — الظرف يزول بزوال سببه.
    """

    # 1. price is mid-range with poor location
    POOR_LOCATION = "POOR_LOCATION"
    # 2. evidence is weak or highly correlated
    WEAK_OR_CORRELATED_EVIDENCE = "WEAK_OR_CORRELATED_EVIDENCE"
    # 3. volatility is too low for the target movement
    VOLATILITY_TOO_LOW = "VOLATILITY_TOO_LOW"
    # 4. volatility is too extreme for safe stop placement
    VOLATILITY_TOO_EXTREME = "VOLATILITY_TOO_EXTREME"
    # 5. the market is transitioning between regimes
    REGIME_TRANSITION = "REGIME_TRANSITION"
    # 6. the target is too close
    TARGET_TOO_CLOSE = "TARGET_TOO_CLOSE"
    # 7. the stop is too wide
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    # 8. the setup conflicts with session behavior
    SESSION_CONFLICT = "SESSION_CONFLICT"
    # 9. the signal requires chasing an already-expanded move
    CHASING_EXPANDED_MOVE = "CHASING_EXPANDED_MOVE"
    # 10. expected holding time exceeds the scalp horizon
    HORIZON_EXCEEDED = "HORIZON_EXCEEDED"


class NoTradeSeverity(StrEnum):
    """شدة سبب عدم التداول (§22.3 «severity») — صلب أو لين.

    الصلب (§22.1): أي حاجب يمنع الدخول منعًا قاطعًا مهما بدت الدرجة
    جذابة. اللين (§22.2): كتم موزون يُجمع مع نظائره قبل الحسم.
    """

    HARD = "HARD"
    SOFT = "SOFT"


class CostMode(StrEnum):
    """أنماط التكلفة الثلاثة (§25.1 حرفيًا).

    «A strategy cannot pass production gates based only on optimistic
    costs» — REALISTIC وحده نمط القبول؛ OPTIMISTIC تشخيصي وSTRESS
    لفحص المتانة.
    """

    OPTIMISTIC = "OPTIMISTIC"  # تشخيصي فقط — لا قبول إنتاجي به أبدًا
    REALISTIC = "REALISTIC"  # نمط القبول (acceptance mode)
    STRESS = "STRESS"  # نمط المتانة (robustness mode)


class RejectionBasis(StrEnum):
    """أسس رفض القرار الثلاثة — تصنيف سبب الرفض في كائن القرار.

    §22.1 و§22.2 يبقيان حرفيين في أكوادهما؛ رفض «الحافة الصافية
    غير كافية» (§23.5: «A setup can be rejected because the gross
    target is large but cost-adjusted edge is insufficient») أساس
    ثالث مستقل لأنه قرار كمي بعد التحجيم والتكاليف لا حاجب حالة.
    """

    HARD_BLOCK = "HARD_BLOCK"  # حاجب صلب §22.1 (واحد فأكثر)
    SOFT_SUPPRESSED = "SOFT_SUPPRESSED"  # كتم لين موزون تجاوز العتبة §22.2
    NET_EDGE_INSUFFICIENT = "NET_EDGE_INSUFFICIENT"  # حافة صافية غير كافية §23.5


class SizingModifierName(StrEnum):
    """معدلات التحجيم الستة (§23.2 حرفيًا بترتيب الخطة).

    «Then apply: volatility modifier; liquidity modifier; execution-
    quality modifier; correlation modifier; daily drawdown modifier;
    scenario quality modifier after calibration» — كل معدل يضرب الحجم
    الأساسي، ولا معدل يرفع الأحجام أبدًا (خاصية «الخطر الناتج ≤
    السقف دائمًا» — بوابة الخروج 8).
    """

    VOLATILITY = "VOLATILITY"
    LIQUIDITY = "LIQUIDITY"
    EXECUTION_QUALITY = "EXECUTION_QUALITY"
    CORRELATION = "CORRELATION"
    DAILY_DRAWDOWN = "DAILY_DRAWDOWN"
    SCENARIO_QUALITY = "SCENARIO_QUALITY"


class SizingCapBasis(StrEnum):
    """أي السقوف المطلقة قيّدت الحجم (§23.2 «capped by absolute
    portfolio and instrument limits»).

    NONE: لم يقيّد سقف الحجم — المعدلات وحدها خفضته أو تركته.
    """

    NONE = "NONE"
    INSTRUMENT = "INSTRUMENT"
    PORTFOLIO = "PORTFOLIO"
