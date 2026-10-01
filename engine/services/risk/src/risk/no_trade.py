"""محرك لا-تداول (§22) — الحجب الصلب الخمسة عشر والكتم اللين العشر.

«No-Trade is a first-class subsystem. Its job is to reject trades even
when a directional scenario looks attractive» (§22) — الرفض مواطن أول
لا استثناء لاحق.

المبادئ:

- **كل الحواجب المشتعلة تُجمع لا أولها فقط**: كل خرق موثق برمزه
  وشرطه (§22.3)، وسبب انتقال الرفض عند المحرك يسمي الأول بترتيب
  الخطة والعدد الكلي — لا رفض بجزء من الحقيقة.
- **الحقن المستقل**: كل حاجب يشتعل من حقيقة واحدة في
  ``EvaluationContext`` (أو قياس واحد من الوقف/التكاليف) — بوابة
  «كلٌّ باختبار حقن فشل مستقل» تبني عليها اختباراتها واحدًا واحدًا.
- **دلالات إعادة المحاولة موثقة لكل رمز** (§22.3 ``whether_retry_is_
  allowed`` + ``retry_condition``): اللين كله قابل للإعادة بزوال سببه،
  والصلب منه ما يزول سببه (جودة/فاتحة/نافذة كلي...) وما لا يُعاد
  أبدًا (إبطال السيناريو — «a new scenario must be opened» §18.5،
  ودخول فات — ظروف تنفيذ مختلفة بنيويًا).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from schemas import (
    DataQuality,
    Direction,
    EvaluationContext,
    FusionSnapshot,
    HardBlockReason,
    MarketRegime,
    MarketStateSnapshot,
    NoTradeExplanation,
    NoTradeSeverity,
    Scenario,
    ScenarioState,
    SoftSuppressionReason,
    StructuralStop,
)

from .parameter_sets import RiskConfig

__all__ = [
    "evaluate_hard_blocks",
    "evaluate_soft_suppressions",
    "location_quality",
    "soft_weight_total",
]

#: جودات البيانات التي تصل قرار الدخول (§7.4) — نفس قائمة محرك
#: السيناريوهات: التدهور الآمن لا التداول الأعمى (§49).
_DECISION_SAFE_QUALITIES: Final[frozenset[DataQuality]] = frozenset(
    {DataQuality.HEALTHY, DataQuality.DELAYED}
)

#: خريطة دلالات إعادة المحاولة للحجب الصلب — None يعني منعًا مؤبدًا
#: (لا إعادة لهذا السيناريو أبدًا؛ التوثيق يوجه لفتح سيناريو جديد).
_RETRY_CONDITIONS: Final[dict[HardBlockReason, str | None]] = {
    HardBlockReason.DATA_UNRELIABLE: (
        "عودة جودة البيانات إلى HEALTHY/DELAYED وعمرها دون الحد الأقصى"
    ),
    HardBlockReason.INSTRUMENT_UNAVAILABLE: "عودة الأداة للتداول داخل ساعات القبول",
    HardBlockReason.VENUE_CONNECTION_UNHEALTHY: "استعادة صحة اتصال وجهة التنفيذ",
    HardBlockReason.SPREAD_EXCEEDS_BUDGET: ("عودة الفاتحة المقدَّرة دون نسبة الحافة/الوقف المقررة"),
    HardBlockReason.SLIPPAGE_EXCEEDS_BUDGET: "عودة الانزلاق المتوقع داخل الميزانية",
    HardBlockReason.LATENCY_EXCEEDS_BUDGET: "عودة كمون التنفيذ دون الحد الأقصى",
    HardBlockReason.RISK_LIMITS_REACHED: (
        "فتح نافذة مخاطرة جديدة (يومية/متدحرجة) أو انخفاض الاستخدام دون السقوف"
    ),
    HardBlockReason.STOP_NOT_RELIABLE: "عودة إمكان وضع الوقف ومطابقته موثوقًا",
    HardBlockReason.BROKER_REJECTS_ORDER: "قبول الوسيط للأداة أو نوع الأمر",
    HardBlockReason.MACRO_EMBARGO_WINDOW: "مضي لحظة القرار خارج نافذة الحظر الكلي",
    HardBlockReason.SCENARIO_INVALIDATED: None,  # لا إنقاذ — سيناريو جديد (§18.5)
    HardBlockReason.ENTRY_TOO_LATE: None,  # ظروف تنفيذ مختلفة بنيويًا — موقع جديد
    HardBlockReason.CONFLICTING_SCENARIO: "حسم السيناريو الأسبق الأعلى (نهاية أو إبطال)",
    HardBlockReason.SCENARIO_ALREADY_CONSUMED: (
        "استنساخ من حدث مرسِم جديد — «no new structural information» تعني أن "
        "المعلومة البنيوية الجديدة وحدها تفتح الباب"
    ),
    HardBlockReason.KILL_SWITCH: "رفع مفتاح الإيقاف يدويًا من المشغّل",
}

#: شروط إعادة المحاولة للكتمات اللين — كلها قابلة للإعادة بزوال سببها.
_SOFT_RETRY_CONDITIONS: Final[dict[SoftSuppressionReason, str]] = {
    SoftSuppressionReason.POOR_LOCATION: (
        "تحسن جودة الموقع — درجات §10.3 للمنطقة المرسبة فوق العتبة"
    ),
    SoftSuppressionReason.WEAK_OR_CORRELATED_EVIDENCE: (
        "ارتفاع الدرجة الخام فوق الحد أو تنوّع المجموعات الحاضرة"
    ),
    SoftSuppressionReason.VOLATILITY_TOO_LOW: "ارتفاع مئين التقلب فوق الحد الأدنى",
    SoftSuppressionReason.VOLATILITY_TOO_EXTREME: "انخفاض مئين التقلب دون الحد الأقصى",
    SoftSuppressionReason.REGIME_TRANSITION: "استقرار تصنيف النظام خارج TRANSITION",
    SoftSuppressionReason.TARGET_TOO_CLOSE: "هدف أبعد يرفع R الإجمالية فوق الحد",
    SoftSuppressionReason.STOP_TOO_WIDE: "وقف أضيق (بنية أقرب) دون العتبة اللينة",
    SoftSuppressionReason.SESSION_CONFLICT: "دخول جلسة سلوكها مواتٍ للسكالب",
    SoftSuppressionReason.CHASING_EXPANDED_MOVE: ("دخول قرب مرجع المنطقة — انجراف دون العتبة"),
    SoftSuppressionReason.HORIZON_EXCEEDED: "سيناريو أفق زمنه داخل أفق السكالب",
}


def _hard_explanation(
    code: HardBlockReason,
    conditions: str,
    offsetting: Sequence[str],
) -> NoTradeExplanation:
    """بناء تفسير حاجب صلب — دلالة الإعادة من الخريطة الموثقة."""
    retry_condition = _RETRY_CONDITIONS[code]
    return NoTradeExplanation(
        no_trade_code=code,
        severity=NoTradeSeverity.HARD,
        triggering_conditions=conditions,
        offsetting_evidence=tuple(offsetting),
        whether_retry_is_allowed=retry_condition is not None,
        retry_condition=retry_condition,
    )


def _soft_explanation(
    code: SoftSuppressionReason,
    conditions: str,
    offsetting: Sequence[str],
) -> NoTradeExplanation:
    """بناء تفسير كتمة لينة — الإعادة مسموحة دائمًا بشرطها الموثق."""
    return NoTradeExplanation(
        no_trade_code=code,
        severity=NoTradeSeverity.SOFT,
        triggering_conditions=conditions,
        offsetting_evidence=tuple(offsetting),
        whether_retry_is_allowed=True,
        retry_condition=_SOFT_RETRY_CONDITIONS[code],
    )


# ───────────────────────── الحجب الصلب (§22.1) ─────────────────────────


def evaluate_hard_blocks(
    scenario: Scenario,
    stop: StructuralStop | None,
    *,
    context: EvaluationContext,
    config: RiskConfig,
    decision_time: datetime,
    close: float,
    target_level: float,
    round_trip_costs: float,
) -> tuple[NoTradeExplanation, ...]:
    """الحواجب الصلبة الخمسة عشر بترتيب الخطة — كل المشتعل يُجمع.

    :param scenario: السيناريو المرشح (يجب أن يكون TRIGGERED — البوابة 11).
    :param stop: الوقف المحسوب (§23.4) — حاجبا 4/8 يقيسان عليه؛
        None يعني استحالة حسابه أصلاً (حاجب 8).
    :param context: وقائع التشغيل لحظة القرار.
    :param config: إصدار معاملات المخاطرة (مخوم بالبصمة).
    :param decision_time: لحظة القرار (زمن شمعة القرار).
    :param close: إغلاق شمعة القرار — قياس التأخر (حاجب 12).
    :param target_level: مستوى الهدف المعتمد (أقرب هدف §10.5).
    :param round_trip_costs: التكاليف المتوقعة ذهابًا وإيابًا (وحدة سعر).
    :returns: كل الحواجب المشتعلة بترتيب §22.1 — فارغة عند السلامة.
    """
    fired: list[NoTradeExplanation] = []
    supporting = tuple(scenario.supporting_evidence)
    direction_sign = 1.0 if scenario.direction is Direction.LONG else -1.0

    # 1. بيانات راكدة/فاسدة/مكررة/ناقصة الحقول — الجودة غير الآمنة أو
    #    العمر المتجاوز (التكرار يحجبه إزالة التكرار upstream — الحقن هنا).
    quality_unsafe = context.data_quality not in _DECISION_SAFE_QUALITIES
    stale = context.data_age_seconds > config.max_data_staleness_s
    if quality_unsafe or stale:
        parts = [
            f"جودة البيانات {context.data_quality.value} خارج "
            f"{sorted(q.value for q in _DECISION_SAFE_QUALITIES)} (§7.4)",
            f"عمر البيانات {context.data_age_seconds:.1f}s > الحد "
            f"{config.max_data_staleness_s:.1f}s",
        ]
        active = " و ".join(
            part for part, on in zip(parts, (quality_unsafe, stale), strict=True) if on
        )
        fired.append(
            _hard_explanation(
                HardBlockReason.DATA_UNRELIABLE,
                active,
                supporting,
            )
        )

    # 2. الأداة موقوفة/غير متاحة/خارج ساعات القبول.
    if not context.instrument_tradable:
        note = (
            context.instrument_status_note.strip()
            if context.instrument_status_note.strip()
            else "بلا توثيق حالة من المصدر — التعطيل وحده حاجب"
        )
        fired.append(
            _hard_explanation(
                HardBlockReason.INSTRUMENT_UNAVAILABLE,
                f"الأداة غير قابلة للتداول لحظة القرار: {note}",
                supporting,
            )
        )

    # 3. اتصال وجهة التنفيذ غير سليم.
    if not context.venue_healthy:
        fired.append(
            _hard_explanation(
                HardBlockReason.VENUE_CONNECTION_UNHEALTHY,
                "فحص صحة اتصال الوجهة سلبي لحظة القرار",
                supporting,
            )
        )

    # 4. الفاتحة تتجاوز النسبة المقررة من الحافة المتوقعة أو مسافة الوقف —
    #    الميزانية أوسح الحدين (ADR-026): النص يعرض الأساسين بديلين
    #    («of expected edge or stop distance») فأيّهما أوسع هو الميزان —
    #    والقراءة الضيقة (أيهما ضاق حكمت) تجعل كل سكالب بوقف رشيق
    #    متعذر التداول بأي فاتحة واقعية، وهذا التضييق تقرره الكتمة
    #    اللين (§22.2 هدف قريب/وقف عريض) لا الحاجب الصلب.
    if stop is not None:
        expected_edge = max(0.0, (target_level - stop.entry_reference) * direction_sign)
        edge_budget = config.max_spread_pct_of_edge * expected_edge
        stop_budget = config.max_spread_pct_of_stop * stop.stop_distance
        spread_budget = max(edge_budget, stop_budget)
        if context.spread_estimate > spread_budget:
            fired.append(
                _hard_explanation(
                    HardBlockReason.SPREAD_EXCEEDS_BUDGET,
                    f"الفاتحة المقدَّرة {context.spread_estimate:.2f} تتجاوز ميزانيتها "
                    f"(أوسح الحدين): {config.max_spread_pct_of_edge:.0%} من الحافة "
                    f"({edge_budget:.2f}) أو {config.max_spread_pct_of_stop:.0%} من "
                    f"الوقف ({stop_budget:.2f})",
                    supporting,
                )
            )

    # 5. الانزلاق المتوقع يتجاوز ميزانية التكلفة.
    if context.slippage_estimate > config.max_slippage_budget:
        fired.append(
            _hard_explanation(
                HardBlockReason.SLIPPAGE_EXCEEDS_BUDGET,
                f"الانزلاق المتوقع {context.slippage_estimate:.2f} > الميزانية "
                f"{config.max_slippage_budget:.2f} (ذهاب وإياب)",
                supporting,
            )
        )

    # 6. كمون التنفيذ يتجاوز الحد الأقصى لأفق الاستراتيجية.
    if context.latency_ms > config.max_latency_ms:
        fired.append(
            _hard_explanation(
                HardBlockReason.LATENCY_EXCEEDS_BUDGET,
                f"الكمون {context.latency_ms:.0f}ms > الحد {config.max_latency_ms:.0f}ms",
                supporting,
            )
        )

    # 7. سقوف المخاطرة مستنفدة — مراكز/يومي/متدحرج/تعرض مترابط.
    limits_reached: list[str] = []
    if context.positions_open >= config.simultaneous_position_cap:
        limits_reached.append(
            f"المراكز المفتوحة {context.positions_open} ≥ سقف {config.simultaneous_position_cap}"
        )
    if context.correlated_exposure >= config.correlated_exposure_cap:
        limits_reached.append(
            f"التعرض المترابط {context.correlated_exposure} ≥ سقف {config.correlated_exposure_cap}"
        )
    if context.risk_used_today >= config.daily_loss_cap:
        limits_reached.append(
            f"مستهلك اليوم {context.risk_used_today:.2f} ≥ السقف اليومي {config.daily_loss_cap:.2f}"
        )
    if context.risk_used_rolling >= config.rolling_loss_cap:
        limits_reached.append(
            f"المستهلك المتدحرج {context.risk_used_rolling:.2f} ≥ السقف "
            f"{config.rolling_loss_cap:.2f}"
        )
    if limits_reached:
        fired.append(
            _hard_explanation(
                HardBlockReason.RISK_LIMITS_REACHED,
                "؛ ".join(limits_reached),
                supporting,
            )
        )

    # 8. الوقف غير موثوق — خارجي (لا يمكن وضعه/مطابقته) أو داخلي
    #    (مسافة تتجاوز السقف المطبَّع أو وقف غير موجب).
    stop_problems: list[str] = []
    if stop is None:
        stop_problems.append("تعذر حساب الوقف البنيوي أصلًا")
    else:
        if not context.stop_reliable:
            stop_problems.append("الوجهة لا تتيح وضعه/مطابقته موثوقًا")
        if stop.stop_price <= 0.0:
            stop_problems.append(f"سعر وقف غير موجب {stop.stop_price}")
        if stop.stop_distance_atr > config.max_stop_distance_atr:
            stop_problems.append(
                f"مسافة الوقف {stop.stop_distance_atr:.2f} ATR > السقف "
                f"{config.max_stop_distance_atr:.2f} ATR"
            )
    if stop_problems:
        fired.append(
            _hard_explanation(
                HardBlockReason.STOP_NOT_RELIABLE,
                "؛ ".join(stop_problems),
                supporting,
            )
        )

    # 9. الوسيط/البورصة يرفض الأداة أو نوع الأمر.
    if not context.broker_accepts_order:
        fired.append(
            _hard_explanation(
                HardBlockReason.BROKER_REJECTS_ORDER,
                f"الوسيط لا يقبل {config.entry_policy.value} على هذه الأداة",
                supporting,
            )
        )

    # 10. حدث كلي عالي الأثر داخل نافذة الحظر (§17.3).
    embargo_hits = [window for window in context.embargo_windows if window.blocks(decision_time)]
    if embargo_hits:
        nearest = embargo_hits[0]
        fired.append(
            _hard_explanation(
                HardBlockReason.MACRO_EMBARGO_WINDOW,
                f"{len(embargo_hits)} نافذة حظر نشطة — أقربها «{nearest.title}» عند "
                f"{nearest.event_time.isoformat()} (نافذة من "
                f"-{nearest.pre_event_window_s:.0f}s إلى "
                f"+{nearest.post_event_window_s:.0f}s)",
                supporting,
            )
        )

    # 11. السيناريو مُبطَل سلفًا — قرار المخاطرة لا يُبنى فوق جثة.
    if scenario.state is not ScenarioState.TRIGGERED:
        fired.append(
            _hard_explanation(
                HardBlockReason.SCENARIO_INVALIDATED,
                f"حالة السيناريو {scenario.state.value} — قرار الدخول لا يصدر إلا "
                "عن TRIGGERED حي (§18.2/§18.5)",
                supporting,
            )
        )

    # 12. الدخول فات — المكافأة المتبقية بعد التكاليف لا تعوّض (§23.5
    #     بثوب التأخر: المسافة من الإغلاق الحالي لا من مرجع الدخول).
    if stop is not None and stop.stop_distance > 0.0:
        remaining_reward = (target_level - close) * direction_sign - round_trip_costs
        remaining_r = remaining_reward / stop.stop_distance
        if remaining_r < config.min_remaining_r:
            fired.append(
                _hard_explanation(
                    HardBlockReason.ENTRY_TOO_LATE,
                    f"المكافأة المتبقية من الإغلاق {close:.2f} إلى الهدف "
                    f"{target_level:.2f} بعد تكاليف {round_trip_costs:.2f} تساوي "
                    f"{remaining_r:.3f}R < الحد {config.min_remaining_r:.2f}R",
                    supporting,
                )
            )

    # 13. سيناريو أعلى أسبقية متضاد غير محسوم — خطر ثنائي.
    if context.conflicting_scenario_ids:
        fired.append(
            _hard_explanation(
                HardBlockReason.CONFLICTING_SCENARIO,
                f"سيناريوهات متضادة أعلى أسبقية غير محسومة: "
                f"{', '.join(context.conflicting_scenario_ids)}",
                supporting,
            )
        )

    # 14. المرسِم نفسه استُهلك ولا معلومة بنيوية جديدة تشكّلت.
    if scenario.proposed_from_event_id in context.consumed_anchor_event_ids:
        fired.append(
            _hard_explanation(
                HardBlockReason.SCENARIO_ALREADY_CONSUMED,
                f"الحدث المرسي {scenario.proposed_from_event_id} استُهلك سلفًا ولم "
                "تتشكل بعده معلومة بنيوية جديدة",
                supporting,
            )
        )

    # 15. حالة الطوارئ/مفتاح الإيقاف.
    if context.kill_switch:
        fired.append(
            _hard_explanation(
                HardBlockReason.KILL_SWITCH,
                "مفتاح الإيقاف مفعّل — كل دخول جديد ممنوع بلا استثناء",
                supporting,
            )
        )

    return tuple(fired)


# ───────────────────────── الكتم اللين (§22.2) ─────────────────────────


def location_quality(scenario: Scenario) -> float:
    """جودة موقع السيناريو — متوسط درجات §10.3 الثلاث للمنطقة المرسبة.

    الغياب = صفر موثق (منطقة بلا درجات ليست موقعًا جيدًا بل بيانات
    ناقصة تُعامل بأدنى جودة — لا تفاؤل صامت).
    """
    zone = scenario.location_snapshot.get("zone")
    if not isinstance(zone, dict):
        return 0.0
    scores: list[float] = []
    for key in ("reaction_score", "unmitigated_score", "importance_score"):
        value = zone.get(key)
        if isinstance(value, int | float) and 0.0 <= float(value) <= 1.0:
            scores.append(float(value))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def evaluate_soft_suppressions(
    scenario: Scenario,
    snapshot: FusionSnapshot,
    market_state: MarketStateSnapshot | None,
    *,
    stop: StructuralStop,
    context: EvaluationContext,
    config: RiskConfig,
    decision_time: datetime,
    close: float,
    target_level: float,
) -> tuple[NoTradeExplanation, ...]:
    """الكتمات اللينة العشر بترتيب الخطة — كل المشتعلة تُجمع موثقة.

    الكتم قرار مجموع (§8.2 بأوزان إعدادية): ``soft_weight_total`` يحسب
    المجموع الذي تقارنه المحرك بالعتبة — الاشتعال الفردي يوثق وحده
    حتى لو لم يبلغ المجموع.
    """
    fired: list[NoTradeExplanation] = []
    supporting = tuple(scenario.supporting_evidence)
    direction_sign = 1.0 if scenario.direction is Direction.LONG else -1.0

    # 1. منتصف نطاق بموقع رديء — درجات §10.3 للمنطقة المرسبة.
    quality = location_quality(scenario)
    if quality < config.min_location_quality:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.POOR_LOCATION,
                f"جودة الموقع {quality:.3f} < الحد {config.min_location_quality:.2f} "
                "(متوسط درجات §10.3 للمنطقة المرسبة — منتصف النطاق)",
                supporting,
            )
        )

    # 2. دليل ضعيف أو شديد الارتباط — الدرجة الخام دون الحد أو مجموعة
    #    واحدة تحمل معظم الحصة الفعلية.
    weak = abs(snapshot.raw_evidence_score) < config.min_evidence_score
    concentration = max(
        (group.effective_share for group in snapshot.group_scores),
        default=0.0,
    )
    correlated = concentration > config.max_group_concentration
    if weak or correlated:
        parts: list[str] = []
        if weak:
            parts.append(
                f"الدرجة الخام {snapshot.raw_evidence_score:+.4f} دون الحد "
                f"{config.min_evidence_score:.2f} بالقيمة المطلقة"
            )
        if correlated:
            parts.append(
                f"تركّز مجموعة واحدة {concentration:.2f} من الحصة الفعلية > الحد "
                f"{config.max_group_concentration:.2f} — دليل شديد الارتباط"
            )
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.WEAK_OR_CORRELATED_EVIDENCE,
                "؛ ".join(parts),
                supporting,
            )
        )

    # 3-4. التقلب — مئين دون الأدنى (لا حركة للهدف) أو فوق الأقصى
    #      (لا وقف آمن) — القياس من لقطة الحالة المتبناة.
    if market_state is not None:
        percentile = float(market_state.volatility_percentile)
        if percentile < config.vol_percentile_min:
            fired.append(
                _soft_explanation(
                    SoftSuppressionReason.VOLATILITY_TOO_LOW,
                    f"مئين التقلب {percentile:.1f} < الأدنى "
                    f"{config.vol_percentile_min:.1f} — حركة الهدف مستبعدة",
                    supporting,
                )
            )
        if percentile > config.vol_percentile_max:
            fired.append(
                _soft_explanation(
                    SoftSuppressionReason.VOLATILITY_TOO_EXTREME,
                    f"مئين التقلب {percentile:.1f} > الأقصى "
                    f"{config.vol_percentile_max:.1f} — وقف آمن متعذر",
                    supporting,
                )
            )

        # 5. السوق ينتقل بين الأنظمة — تصنيف TRANSITION.
        if market_state.regime is MarketRegime.TRANSITION:
            fired.append(
                _soft_explanation(
                    SoftSuppressionReason.REGIME_TRANSITION,
                    "تصنيف النظام TRANSITION — اللحظة بين نظامين لا تستقر على قراءة",
                    supporting,
                )
            )

    # 6. الهدف قريب — R الإجمالية دون الحد الأدنى.
    gross_r = (target_level - stop.entry_reference) * direction_sign / stop.stop_distance
    if gross_r < config.min_target_r:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.TARGET_TOO_CLOSE,
                f"R الإجمالية {gross_r:.2f} < الحد {config.min_target_r:.2f} — "
                "المسافة إلى الهدف لا تكافئ المخاطرة",
                supporting,
            )
        )

    # 7. الوقف عريض — فوق العتبة اللينة (دون السقف الصلب — ذاك حاجب 8).
    if stop.stop_distance_atr > config.soft_stop_wideness_atr:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.STOP_TOO_WIDE,
                f"مسافة الوقف {stop.stop_distance_atr:.2f} ATR > العتبة اللينة "
                f"{config.soft_stop_wideness_atr:.2f} ATR",
                supporting,
            )
        )

    # 8. التعارض مع سلوك الجلسة — الجلسات المسودة إعداديًا.
    if context.session in config.session_blacklist:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.SESSION_CONFLICT,
                f"الجلسة {context.session.value} ضمن القائمة المسودة — "
                "سلوكها يتنافر مع أفق السكالب",
                supporting,
            )
        )

    # 9. مطاردة حركة متمددة — الانجراف عن مرجع الدخول فوق العتبة.
    drift_atr = abs(close - stop.entry_reference) / stop.atr
    if drift_atr > config.chase_drift_atr:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.CHASING_EXPANDED_MOVE,
                f"الانجراف عن مرجع الدخول {drift_atr:.2f} ATR > العتبة "
                f"{config.chase_drift_atr:.2f} ATR — الحركة متمددة سلفًا",
                supporting,
            )
        )

    # 10. أفق التملك المتوقع يتجاوز أفق السكالب — نافذة الانقضاء
    #     الباقية مقياس أفق هذا السيناريو.
    remaining_horizon_s = (scenario.expiry_time - decision_time).total_seconds()
    if remaining_horizon_s > config.max_holding_time_s:
        fired.append(
            _soft_explanation(
                SoftSuppressionReason.HORIZON_EXCEEDED,
                f"الأفق المتبقي {remaining_horizon_s:.0f}s > أفق السكالب "
                f"{config.max_holding_time_s:.0f}s",
                supporting,
            )
        )

    return tuple(fired)


def soft_weight_total(config: RiskConfig, suppressions: Sequence[NoTradeExplanation]) -> float:
    """مجموع أوزان الكتمات المشتعلة — يُقارن بالعتبة عند المحرك."""
    total = 0.0
    for suppression in suppressions:
        if isinstance(suppression.no_trade_code, SoftSuppressionReason):
            total += config.soft_weights.get(suppression.no_trade_code, 0.0)
    return total
