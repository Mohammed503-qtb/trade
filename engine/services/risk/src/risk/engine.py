"""محرك المخاطرة (§23) — من TRIGGERED إلى قرار ترخيص أو رفض موثق.

«The Risk Engine receives an approved trade intent candidate, not raw
technical analysis» — مدخله سيناريو TRIGGERED خرج من محرك المرحلة 7
بمشغله وإبطاله المعرّفين (بوابة الخروج 7)، ومخرجه قرار واحد مكتمل
(§31.3 decisions): إما ترخيص بنية أمر §24.1 كاملة، وإما رفض موثق
الأساس بتفسير §22.3 لكل سبب وتفسير §2.8 بتقدير تكاليف مسدد.

ترتيب البوابات حتمي موثق (أي تبديل يغيّر الدلالة):

1. **الوقف البنيوي** (§23.4) — قبل كل شيء: حاجبا 4/8 يقيسان عليه
   ووحدة R تُبنى منه.
2. **الحجب الصلب** (§22.1) — أي حاجب يقطع الطريق: لا كتم ولا تحجيم.
3. **الكتم اللين** (§22.2) — مجموع موزون مقابل العتبة.
4. **الحافة الصافية** (§23.5 بـREALISTIC — نمط القبول الوحيد §25.1).
5. **التحجيم** (§23.2) — الأساس فالمعدلات الستة فالسقوف.
6. **النية والتفسير** (§24.1/§2.8) — الترخيص اكتمال لا وعد.

الحتمية: لا ساعة ولا عشوائية — الزمن من شمعة القرار، والمعرفات
uuid5 حتمية (روح D-07: قرار واحد لكل سيناريو، إعادة التقييم لا تكرر).
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Sequence
from datetime import datetime, timedelta

from fusion.explain import build_explanation
from pydantic import BaseModel, ConfigDict
from schemas import (
    Candle,
    EvaluationContext,
    EvidenceRecord,
    ExplanationObject,
    FusionSnapshot,
    MarketStateSnapshot,
    NoTradeExplanation,
    OrderIntent,
    RejectionBasis,
    RewardRiskEstimate,
    RiskDecision,
    Scenario,
    ScenarioState,
    SizingResult,
    StructuralStop,
    validate_explanation_completeness,
)

from .costs import estimate_reward_risk, round_trip_cost
from .no_trade import evaluate_hard_blocks, evaluate_soft_suppressions, soft_weight_total
from .parameter_sets import RiskConfig, default_risk_config
from .sizing import compute_sizing
from .stop import compute_structural_stop

__all__ = ["RiskEngine", "RiskEvaluation"]

#: مساحات أسماء المعرفات الحتمية — قرار ونيتان (أمر وعميل) لكل سيناريو.
_DECISION_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/risk-decision"
)
_INTENT_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/trade-intent"
)
_CLIENT_ORDER_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/client-order"
)


def decision_id_for(scenario_id: str) -> str:
    """معرف القرار الحتمي — قرار ترخيص واحد لكل سيناريو (idempotent)."""
    return str(uuid_module.uuid5(_DECISION_NAMESPACE, scenario_id))


def trade_intent_id_for(scenario_id: str) -> str:
    """معرف نية الأمر الحتمي — نيّة واحدة لكل سيناريو مرخَّص."""
    return str(uuid_module.uuid5(_INTENT_NAMESPACE, scenario_id))


def _client_order_id_for(scenario_id: str) -> str:
    """معرف أمر العميل الحتمي — بصمة المستدعي عند التنفيذ (§24.1)."""
    return str(uuid_module.uuid5(_CLIENT_ORDER_NAMESPACE, scenario_id))


class RiskEvaluation(BaseModel):
    """نتيجة تقييم واحد — القرار وجهة الانتقال الذي يقوده.

    نموذج داخلي (لا يُخزن كما هو): القرار وحده يُخزن في decisions،
    والانتقال يطبقه المشغل (طبقة التطبيقات) عبر ``scenarios.lifecycle``
    — عقد الطبقات يفصل المحركات: المخاطرة تقرر ودورة الحياة تنفّذ
    (استقلال طبقة القرار مفروض بـimport-linter).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: RiskDecision
    #: الحالة الهدف من TRIGGERED — AUTHORIZED أو REJECTED_BY_RISK (§18.2).
    target_state: ScenarioState
    #: سبب الانتقال الموثق — كثيف من القرار نفسه (لا انتقال بلا سبب §31.3).
    transition_reason: str


class RiskEngine:
    """قائد قرار المخاطرة — حتمي: نفس المدخلات ⇒ نفس القرار بايت-بايت."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config if config is not None else default_risk_config()

    @property
    def config(self) -> RiskConfig:
        """الإعداد المجمّد — للقراءة والبصمة."""
        return self._config

    def evaluate(
        self,
        scenario: Scenario,
        *,
        snapshot: FusionSnapshot,
        records: Sequence[EvidenceRecord],
        market_state: MarketStateSnapshot | None,
        candle: Candle,
        atr: float,
        context: EvaluationContext,
        trigger_reason: str = "",
    ) -> RiskEvaluation:
        """تقييم سيناريو TRIGGERED — القرار والانتقال معاً.

        :param snapshot: لقطة الدمج لحظة القرار (صورة الدليل النهائية).
        :param records: سجل الدليل بترتيب الإدخال — وقود التفسير §2.8.
        :param market_state: لقطة الحالة المتبناة (للكتم والتحجيم).
        :param candle: شمعة القرار المغلقة (لا-نظرة §26.3).
        :param atr: ATR شمعة القرار — مقياس الوقف والعتبات.
        :param context: وقائع التشغيل — الحقائق التي تحكم الحواجب.
        :param trigger_reason: سبب الانتقال إلى TRIGGERED (توثيق التفسير).
        :raises ValueError: سيناريو بلا هدف أساسي — D-04 يضمن وجوده
            (لا هدف = لا استنساخ)، وغيابه عبث خارج المسار الموثق.
        """
        if not scenario.primary_targets:
            raise ValueError(
                f"السيناريو {scenario.scenario_id} بلا هدف أساسي — D-04: "
                "«لا هدف = لا استنساخ» فمقترح حي بلا هدف عبث خارج المسار"
            )
        decision_time = candle.bar_time
        target_level = scenario.primary_targets[0].price_level

        # (1) الوقف البنيوي — قبل كل بوابات القياس.
        stop = compute_structural_stop(
            scenario, atr=atr, config=self._config, latency_ms=context.latency_ms
        )

        # (2) الحجب الصلب — أي حاجب يقطع الطريق كله.
        hard_blocks = evaluate_hard_blocks(
            scenario,
            stop,
            context=context,
            config=self._config,
            decision_time=decision_time,
            close=float(candle.close),
            target_level=target_level,
            round_trip_costs=round_trip_cost(self._config, self._config.acceptance_cost_mode),
        )

        # (3) الكتم اللين — يُقيس فقط بعد سلامة الصلب (الكتم فوق حاجب
        #     تشويش للموثوقية: الرفض الصلب كافٍ وسببه أقوى).
        soft_suppressions: tuple[NoTradeExplanation, ...] = ()
        soft_total = 0.0
        if not hard_blocks and stop is not None:
            soft_suppressions = evaluate_soft_suppressions(
                scenario,
                snapshot,
                market_state,
                stop=stop,
                context=context,
                config=self._config,
                decision_time=decision_time,
                close=float(candle.close),
                target_level=target_level,
            )
            soft_total = soft_weight_total(self._config, soft_suppressions)

        sizing: SizingResult | None = None
        reward_risk: RewardRiskEstimate | None = None
        order_intent: OrderIntent | None = None
        rejection_basis: RejectionBasis | None = None

        if hard_blocks:
            # رفض صلب — الأساس الأول في الترتيب.
            rejection_basis = RejectionBasis.HARD_BLOCK
        elif soft_total >= self._config.soft_threshold:
            # رفض لين موزون — المجموع تجاوز العتبة.
            rejection_basis = RejectionBasis.SOFT_SUPPRESSED
        else:
            assert stop is not None  # لا حاجب 8 ⇒ الوقف محسوب صالح
            # (4) الحافة الصافية §23.5 — بـREALISTIC (نمط القبول §25.1).
            reward_risk = estimate_reward_risk(
                stop,
                target_level=target_level,
                direction=scenario.direction,
                config=self._config,
                cost_mode=self._config.acceptance_cost_mode,
            )
            if reward_risk.estimated_net_r < self._config.min_net_r:
                rejection_basis = RejectionBasis.NET_EDGE_INSUFFICIENT
            else:
                # (5) التحجيم §23.2 — الناجون وحدهم.
                sizing = compute_sizing(
                    scenario,
                    stop,
                    config=self._config,
                    context=context,
                    market_state=market_state,
                    decision_time=decision_time,
                )
                # (6) نية الأمر §24.1 — الترخيص اكتمال.
                order_intent = self._build_intent(
                    scenario, stop=stop, sizing=sizing, decision_time=decision_time
                )

        approved = rejection_basis is None
        explanation = self._build_explanation(
            scenario,
            snapshot=snapshot,
            records=records,
            market_state=market_state,
            stop=stop,
            reward_risk=reward_risk,
            sizing=sizing,
            trigger_reason=trigger_reason,
            rejected=not approved,
            rejection_basis=rejection_basis,
            hard_blocks=hard_blocks,
            soft_suppressions=soft_suppressions,
            soft_total=soft_total,
        )

        decision = RiskDecision(
            decision_id=decision_id_for(scenario.scenario_id),
            scenario_id=scenario.scenario_id,
            symbol=scenario.symbol,
            direction=scenario.direction,
            decided_at=decision_time,
            approved=approved,
            rejection_basis=rejection_basis,
            hard_blocks=hard_blocks,
            soft_suppressions=soft_suppressions,
            soft_total=soft_total,
            stop=stop,
            sizing=sizing,
            reward_risk=reward_risk,
            order_intent=order_intent,
            explanation=explanation,
            parameter_fingerprint=self._config.fingerprint,
        )
        validate_explanation_completeness(explanation, rejected=not approved)

        target_state = ScenarioState.AUTHORIZED if approved else ScenarioState.REJECTED_BY_RISK
        return RiskEvaluation(
            decision=decision,
            target_state=target_state,
            transition_reason=self._transition_reason(decision),
        )

    # ───────────────────────── الداخل ─────────────────────────

    def _build_intent(
        self,
        scenario: Scenario,
        *,
        stop: StructuralStop,
        sizing: SizingResult,
        decision_time: datetime,
    ) -> OrderIntent:
        """نية الأمر المعتمدة (§24.1) — من هندسة السيناريو والتحجيم.

        الانقضاء: الأقرب بين نافذة السيناريو وأفق السكالب (§23.3) —
        النية لا تعيش أطول من كليهما.
        """
        horizon_expiry = decision_time + timedelta(seconds=self._config.max_holding_time_s)
        expiry = min(scenario.expiry_time, horizon_expiry)
        return OrderIntent(
            trade_intent_id=trade_intent_id_for(scenario.scenario_id),
            scenario_id=scenario.scenario_id,
            symbol=scenario.symbol,
            side=scenario.direction,
            entry_policy=self._config.entry_policy,
            entry_zone=scenario.entry_zone,
            stop=stop.stop_price,
            targets=list(scenario.primary_targets),
            max_slippage=self._config.max_slippage_budget,
            max_latency=self._config.max_latency_ms,
            expiry=expiry,
            risk_budget=sizing.resulting_risk_money,
            client_order_id=_client_order_id_for(scenario.scenario_id),
        )

    def _build_explanation(
        self,
        scenario: Scenario,
        *,
        snapshot: FusionSnapshot,
        records: Sequence[EvidenceRecord],
        market_state: MarketStateSnapshot | None,
        stop: StructuralStop | None,
        reward_risk: RewardRiskEstimate | None,
        sizing: SizingResult | None,
        trigger_reason: str,
        rejected: bool,
        rejection_basis: RejectionBasis | None,
        hard_blocks: tuple[NoTradeExplanation, ...],
        soft_suppressions: tuple[NoTradeExplanation, ...],
        soft_total: float,
    ) -> ExplanationObject:
        """كائن التفسير §2.8 — التكلفة مسددة والرفض معلل دوماً.

        المشغل والإبطال والمسار من هندسة السيناريو نفسها (المرحلة 7
        سددت حقولها)؛ تقدير التكاليف يسدد هنا (وعد المرحلة 6).
        """
        trigger_line = (
            trigger_reason.strip()
            if trigger_reason.strip()
            else f"مشغل {scenario.trigger_definition.condition_type} معرّف (§18.4)"
        )
        invalidation_rule = scenario.invalidation
        invalidation_line = (
            f"مستوى بنيوي {invalidation_rule.structural_level:.2f} ± عازلة "
            f"{invalidation_rule.volatility_buffer:.2f}"
            + (" بقبول إغلاق (§18.5)" if invalidation_rule.accept_through else " بفتيل (§18.5)")
            + (
                f" + عدم يقين تنفيذ {stop.execution_uncertainty:.2f} ⇒ وقف "
                f"{stop.stop_price:.2f} (§23.4)"
                if stop is not None
                else " — تعذر حساب الوقف (§23.4)"
            )
        )
        targets_line = " ← ".join(
            f"{target.price_level:.2f} ({target.zone_id})" for target in scenario.primary_targets
        )
        path_line = (
            f"من منطقة الدخول [{scenario.entry_zone.price_low:.2f}, "
            f"{scenario.entry_zone.price_high:.2f}] نحو أهداف السيولة: {targets_line} (§10.5)"
        )
        if reward_risk is not None:
            total_costs = (
                reward_risk.breakdown.gross_price_edge - reward_risk.breakdown.net_trading_edge
            )
            cost_line = (
                f"{reward_risk.cost_mode.value}: حافة إجمالية "
                f"{reward_risk.gross_target_distance:.2f} وتكاليف "
                f"{total_costs:.2f} "
                f"للوحدة ⇒ صافي {reward_risk.breakdown.net_trading_edge:.2f} "
                f"({reward_risk.estimated_net_r:+.3f}R) (§25.2/§23.5)"
            )
        else:
            cost_line = (
                "التكاليف لم تُقدَّر — الرفض قطعه قبل مرحلة الحافة (الحجب الصلب/الكتم اللين أسبق)"
            )

        rejection_reason: str | None = None
        if rejected:
            assert rejection_basis is not None
            if rejection_basis is RejectionBasis.HARD_BLOCK:
                first = hard_blocks[0]
                rejection_reason = (
                    f"حاجب صلب §22.1: {first.no_trade_code.value} — "
                    f"{first.triggering_conditions}"
                    + (f" (+{len(hard_blocks) - 1} حواجب أخرى)" if len(hard_blocks) > 1 else "")
                )
            elif rejection_basis is RejectionBasis.SOFT_SUPPRESSED:
                codes = ", ".join(s.no_trade_code.value for s in soft_suppressions)
                rejection_reason = (
                    f"كتم لين §22.2: المجموع الموزون {soft_total:.2f} ≥ العتبة "
                    f"{self._config.soft_threshold:.2f} ({codes})"
                )
            else:
                assert reward_risk is not None
                rejection_reason = (
                    f"حافة صافية غير كافية §23.5: {reward_risk.estimated_net_r:+.3f}R "
                    f"< الحد {self._config.min_net_r:.2f}R بنمط "
                    f"{reward_risk.cost_mode.value}"
                )

        sizing_note = (
            f" — الحجم {sizing.position_size:.6f} (خطر ناتج "
            f"{sizing.resulting_risk_money:.2f} ≤ ميزانية {sizing.risk_budget:.2f})"
            if sizing is not None
            else ""
        )
        market_context = (
            f"{market_state.regime.value}، تقلب مئينه "
            f"{market_state.volatility_percentile:.1f}، جودة "
            f"{market_state.data_quality.value}، انحياز الإطار الأعلى "
            f"{market_state.htf_bias.value} ({market_state.timeframe}) — قرار المخاطرة "
            f"عند {scenario.state.value}{sizing_note}"
            if market_state is not None
            else f"بلا لقطة حالة معتمدة — قرار المخاطرة عند {scenario.state.value}"
        )

        return build_explanation(
            snapshot,
            records,
            market_state=market_state,
            market_context=market_context,
            trigger=trigger_line,
            invalidation=invalidation_line,
            expected_path=path_line,
            cost_estimate=cost_line,
            rejection_reason=rejection_reason,
        )

    def _transition_reason(self, decision: RiskDecision) -> str:
        """سبب انتقال دورة الحياة — توثيق كثيف من القرار نفسه."""
        if decision.approved:
            sizing = decision.sizing
            reward = decision.reward_risk
            stop = decision.stop
            assert sizing is not None and reward is not None and stop is not None
            return (
                f"ترخيص المخاطرة (§23): الحواجب الصلبة صافية والكتم "
                f"{decision.soft_total:.2f} دون العتبة والحافة الصافية "
                f"{reward.estimated_net_r:+.3f}R ≥ {self._config.min_net_r:.2f}R — "
                f"الحجم {sizing.position_size:.6f} بخطر ناتج "
                f"{sizing.resulting_risk_money:.2f} ووقف §23.4 عند "
                f"{stop.stop_price:.2f}"
            )
        assert decision.rejection_basis is not None
        if decision.hard_blocks:
            codes = ", ".join(block.no_trade_code.value for block in decision.hard_blocks)
            return f"رفض المخاطرة — حاجب صلب §22.1 ({len(decision.hard_blocks)}): {codes}"
        if decision.rejection_basis is RejectionBasis.SOFT_SUPPRESSED:
            codes = ", ".join(s.no_trade_code.value for s in decision.soft_suppressions)
            return (
                f"رفض المخاطرة — كتم لين §22.2: المجموع {decision.soft_total:.2f} "
                f"≥ العتبة {self._config.soft_threshold:.2f} ({codes})"
            )
        reward = decision.reward_risk
        assert reward is not None
        return (
            f"رفض المخاطرة — حافة صافية §23.5: {reward.estimated_net_r:+.3f}R < "
            f"{self._config.min_net_r:.2f}R ({reward.cost_mode.value})"
        )
