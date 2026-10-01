"""اختبارات محرك المخاطرة — مسارات الترخيص والرفض الثلاثة والحتمية.

البوابة المركزية: «كل خرق مخاطرة = رفض صلب موثق بكود» — كل أساس رفض
يُختبر بمساره، والترخيص يثبت اكتماله (نية أمر + تحجيم + تفسير بتكلفة
مسددة — وعد المرحلة 6).
"""

from __future__ import annotations

import pytest
from _risk_fixtures import (
    ATR,
    DECISION_TIME,
    decision_candle,
    fusion_snapshot_for,
    healthy_context,
    triggered_scenario,
)
from risk.engine import RiskEngine, RiskEvaluation, decision_id_for, trade_intent_id_for
from risk.parameter_sets import RiskConfig, default_risk_config
from schemas import (
    DataQuality,
    EvaluationContext,
    RejectionBasis,
    Scenario,
    ScenarioState,
    SessionType,
    validate_explanation_completeness,
)


def _evaluate(
    context: EvaluationContext | None = None,
    config: RiskConfig | None = None,
    **overrides: object,
) -> tuple[Scenario, RiskEvaluation]:
    scenario = triggered_scenario()
    snapshot, records = fusion_snapshot_for(scenario)
    engine = RiskEngine(config)
    evaluation = engine.evaluate(
        scenario,
        snapshot=snapshot,
        records=records,
        market_state=scenario.context_snapshot,
        candle=decision_candle(),
        atr=ATR,
        context=context or healthy_context(),
        trigger_reason="مشغل DISPLACEMENT_CONFIRM رُصد عند المرسِم +1m",
        **overrides,
    )
    return scenario, evaluation


class TestApprovalPath:
    """مسار الترخيص — القرار المكتمل والانتقال ونية الأمر."""

    def test_reference_setup_is_authorized(self) -> None:
        _scenario, evaluation = _evaluate()
        assert evaluation.decision.approved
        assert evaluation.target_state is ScenarioState.AUTHORIZED
        decision = evaluation.decision
        assert decision.rejection_basis is None
        assert decision.hard_blocks == ()
        assert decision.sizing is not None
        assert decision.reward_risk is not None
        assert decision.order_intent is not None
        assert decision.stop is not None

    def test_order_intent_complete_and_deterministic_ids(self) -> None:
        scenario, evaluation = _evaluate()
        intent = evaluation.decision.order_intent
        assert intent is not None
        assert intent.trade_intent_id == trade_intent_id_for(scenario.scenario_id)
        assert intent.scenario_id == scenario.scenario_id
        stop = evaluation.decision.stop
        sizing = evaluation.decision.sizing
        assert stop is not None and sizing is not None
        assert intent.stop == stop.stop_price
        assert intent.targets == list(scenario.primary_targets)
        # الميزانية = الخطر الناتج من التحجيم لا السقف الأعلى
        assert intent.risk_budget == pytest.approx(sizing.resulting_risk_money)
        # الانقضاء: الأقرب بين نافذة السيناريو وأفق السكالب
        config = default_risk_config()
        from datetime import timedelta

        horizon = DECISION_TIME + timedelta(seconds=config.max_holding_time_s)
        assert intent.expiry == min(scenario.expiry_time, horizon)

    def test_decision_id_deterministic_per_scenario(self) -> None:
        scenario, evaluation = _evaluate()
        assert evaluation.decision.decision_id == decision_id_for(scenario.scenario_id)

    def test_explanation_cost_estimate_paid(self) -> None:
        """وعد المرحلة 6 مسدد: تقدير التكاليف حاضر لا نص تأجيل."""
        _scenario, evaluation = _evaluate()
        explanation = evaluation.decision.explanation
        assert "REALISTIC" in explanation.cost_estimate
        assert "تقدير التكاليف" not in explanation.cost_estimate  # نص التأجيل اختفى
        assert explanation.rejection_reason is None
        validate_explanation_completeness(explanation, rejected=False)

    def test_transition_reason_is_substantive(self) -> None:
        _scenario, evaluation = _evaluate()
        assert "ترخيص المخاطرة" in evaluation.transition_reason
        assert evaluation.transition_reason.strip()


class TestRejectionPaths:
    """مسارات الرفض الثلاثة — صلب/لين/حافة، كل بمساره الموثق."""

    def test_hard_block_rejection(self) -> None:
        _scenario, evaluation = _evaluate(context=healthy_context(kill_switch=True))
        decision = evaluation.decision
        assert not decision.approved
        assert decision.rejection_basis is RejectionBasis.HARD_BLOCK
        assert decision.hard_blocks
        assert decision.order_intent is None
        assert evaluation.target_state is ScenarioState.REJECTED_BY_RISK
        assert decision.explanation.rejection_reason
        assert "KILL_SWITCH" in decision.explanation.rejection_reason
        validate_explanation_completeness(decision.explanation, rejected=True)

    def test_soft_suppression_rejection(self) -> None:
        # جلسة صيانة (0.4) + تقلب فوق الأقصى (0.4) + وقف عريض (0.3)
        # = 1.1 ≥ العتبة 1.0 — رفض لين موزون
        config = default_risk_config().model_copy(
            update={"vol_percentile_max": 50.0, "soft_stop_wideness_atr": 1.5}
        )
        scenario = triggered_scenario()
        snapshot, records = fusion_snapshot_for(scenario)
        engine = RiskEngine(config)
        evaluation = engine.evaluate(
            scenario,
            snapshot=snapshot,
            records=records,
            market_state=scenario.context_snapshot,
            candle=decision_candle(),
            atr=ATR,
            context=healthy_context(session=SessionType.MAINTENANCE),
        )
        decision = evaluation.decision
        assert not decision.approved
        assert decision.rejection_basis is RejectionBasis.SOFT_SUPPRESSED
        assert decision.soft_total >= config.soft_threshold
        assert evaluation.target_state is ScenarioState.REJECTED_BY_RISK
        assert "كتم لين" in evaluation.transition_reason

    def test_net_edge_rejection(self) -> None:
        """حافة صافية غير كافية §23.5 — هدف بعيد التكاليف أكلة."""
        config = default_risk_config().model_copy(update={"min_net_r": 90.0})
        _scenario, evaluation = _evaluate(config=config)
        decision = evaluation.decision
        assert not decision.approved
        assert decision.rejection_basis is RejectionBasis.NET_EDGE_INSUFFICIENT
        assert decision.reward_risk is not None  # الحافة حُسبت ثم رفضت
        assert decision.sizing is None  # التحجيم لم يبلغ
        assert "حافة صافية" in evaluation.transition_reason

    def test_hard_block_takes_precedence_over_soft(self) -> None:
        """الصلب يقطع قبل قياس اللين — سبق البوابات حتمي."""
        scenario = triggered_scenario()
        snapshot, records = fusion_snapshot_for(scenario)
        engine = RiskEngine()
        evaluation = engine.evaluate(
            scenario,
            snapshot=snapshot,
            records=records,
            market_state=scenario.context_snapshot,
            candle=decision_candle(),
            atr=ATR,
            context=healthy_context(kill_switch=True, session=SessionType.MAINTENANCE),
        )
        decision = evaluation.decision
        assert decision.rejection_basis is RejectionBasis.HARD_BLOCK
        # الكتم لم يُقيس أصلاً — لا كتمات موثقة بعد حاجب صلب
        assert decision.soft_suppressions == ()
        assert decision.soft_total == 0.0

    def test_no_target_is_loud_contract_violation(self) -> None:
        scenario = triggered_scenario()
        snapshot, records = fusion_snapshot_for(scenario)
        targetless = scenario.model_copy(update={"primary_targets": []})
        engine = RiskEngine()
        with pytest.raises(ValueError, match="بلا هدف أساسي"):
            engine.evaluate(
                targetless,
                snapshot=snapshot,
                records=records,
                market_state=scenario.context_snapshot,
                candle=decision_candle(),
                atr=ATR,
                context=healthy_context(),
            )


class TestDeterminism:
    """الحتمية — نفس المدخلات ⇒ نفس القرار بايت-بايت."""

    def test_same_inputs_same_decision_bytes(self) -> None:
        _s1, first = _evaluate()
        _s2, second = _evaluate()
        assert first.decision.model_dump_json() == second.decision.model_dump_json()
        assert first.transition_reason == second.transition_reason
        assert first.target_state is second.target_state

    def test_parameter_fingerprint_stamped(self) -> None:
        _scenario, evaluation = _evaluate()
        config = default_risk_config()
        assert evaluation.decision.parameter_fingerprint == config.fingerprint


class TestQualitySafety:
    """جودة البيانات غير الآمنة تحجب الدخول — التدهور الآمن §49."""

    def test_unsafe_quality_is_hard_block_not_blind_entry(self) -> None:
        _scenario, evaluation = _evaluate(
            context=healthy_context(data_quality=DataQuality.QUARANTINED)
        )
        decision = evaluation.decision
        assert not decision.approved
        assert decision.rejection_basis is RejectionBasis.HARD_BLOCK
        codes = [b.no_trade_code.value for b in decision.hard_blocks]
        assert "DATA_UNRELIABLE" in codes
