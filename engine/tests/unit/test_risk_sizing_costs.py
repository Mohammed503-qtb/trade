"""اختبارات وقف/تحجيم/تكاليف المرحلة 8 — §23.2/§23.4/§25.2.

الخاصية المركزية (بوابة الخروج 8): «الخطر الناتج ≤ السقف دائمًا» —
تثبت هنا بنيويًا على الحالات اليدوية وبـhypothesis في ملف الخصائص.
"""

from __future__ import annotations

import pytest
from _risk_fixtures import (
    ATR,
    DECISION_TIME,
    healthy_context,
    triggered_scenario,
)
from risk.costs import estimate_reward_risk, round_trip_cost
from risk.parameter_sets import RiskConfig, default_risk_config
from risk.sizing import compute_sizing, risk_budget_for
from risk.stop import compute_structural_stop
from schemas import (
    CostMode,
    Direction,
    LiquidityZone,
    MacroEventWindow,
    RewardRiskEstimate,
    Scenario,
    SizingCapBasis,
    SizingModifierName,
    SizingResult,
    StructuralStop,
)


class TestStructuralStop:
    """الوقف البنيوي §23.4 — الثلاثي الحرفي والاتجاه والمرجع المحافظ."""

    def test_decomposition_is_structural_plus_buffer_plus_uncertainty(self) -> None:
        scenario = triggered_scenario()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        # عدم اليقين = 0.25s × (200/60) × 0.5
        expected_uncertainty = 0.25 * (ATR / config.execution_bar_seconds) * 0.5
        assert stop.execution_uncertainty == pytest.approx(expected_uncertainty)
        assert stop.stop_price == pytest.approx(
            stop.structural_level - (stop.volatility_buffer + stop.execution_uncertainty)
        )
        assert stop.stop_distance == pytest.approx(stop.entry_reference - stop.stop_price)
        # المرجع المحافظ: حافة المنطقة العليا لإبطال LONG التحت
        assert stop.entry_reference == scenario.entry_zone.price_high

    def test_short_orientation_mirrored(self) -> None:
        from _risk_fixtures import fusion_snapshot_for, risk_target_map  # noqa: F401
        from _scenario_fixtures import make_market_state, make_sweep_payload
        from scenarios.proposer import AnchorEvent, ScenarioProposer
        from schemas import EventType, ScenarioTemplate

        proposer = ScenarioProposer()
        outcome = proposer.propose(
            AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, DECISION_TIME, make_sweep_payload()),
            zone=_short_zone(),
            targets=risk_target_map(),
            state=make_market_state(),
            atr=ATR,
        )
        breakout = next(s for s in outcome.proposals if s.template is ScenarioTemplate.BREAKOUT)
        assert breakout.direction is Direction.SHORT
        stop = compute_structural_stop(
            breakout, atr=ATR, config=default_risk_config(), latency_ms=250.0
        )
        assert stop is not None
        # إبطال SHORT فوق البنية: الوقف أعلى والمرجع الحافة الدنيا
        assert stop.stop_price > stop.structural_level
        assert stop.entry_reference == breakout.entry_zone.price_low

    def test_degenerate_geometry_returns_none(self) -> None:
        scenario = triggered_scenario()
        # مستوى بنية صفري — هندسة فاقدة الصلاحية (يلتقطها الحاجب 8)
        dead = scenario.model_copy(
            update={
                "invalidation": scenario.invalidation.model_copy(update={"structural_level": 0.0})
            }
        )
        stop = compute_structural_stop(
            dead, atr=ATR, config=default_risk_config(), latency_ms=250.0
        )
        assert stop is None


def _short_zone() -> LiquidityZone:
    """منطقة بيعية مرجعية — نفس منطقة الاختبارات البنيوية."""
    from _scenario_fixtures import make_zone

    return make_zone()


class TestSizing:
    """التحجيم §23.2 — المعادلة والمعدلات الستة والسقوف."""

    def _reference_sizing(
        self, config: RiskConfig | None = None
    ) -> tuple[Scenario, StructuralStop, SizingResult]:
        from _scenario_fixtures import make_market_state

        scenario = triggered_scenario()
        config = config or default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        sizing = compute_sizing(
            scenario,
            stop,
            config=config,
            context=healthy_context(),
            market_state=make_market_state(),
            decision_time=DECISION_TIME,
        )
        return scenario, stop, sizing

    def test_base_formula_literal(self) -> None:
        _s, _stop, sizing = self._reference_sizing()
        assert sizing.base_position_size == pytest.approx(
            sizing.risk_budget / sizing.stop_distance_value
        )
        assert sizing.risk_budget == pytest.approx(default_risk_config().per_trade_risk_cap)

    def test_six_modifiers_in_plan_order(self) -> None:
        _s, _stop, sizing = self._reference_sizing()
        assert [m.name for m in sizing.modifiers] == [
            SizingModifierName.VOLATILITY,
            SizingModifierName.LIQUIDITY,
            SizingModifierName.EXECUTION_QUALITY,
            SizingModifierName.CORRELATION,
            SizingModifierName.DAILY_DRAWDOWN,
            SizingModifierName.SCENARIO_QUALITY,
        ]
        for modifier in sizing.modifiers:
            assert 0.0 < modifier.multiplier <= 1.0
            assert modifier.rationale.strip()

    def test_scenario_quality_modifier_neutral_with_documented_deferral(self) -> None:
        _s, _stop, sizing = self._reference_sizing()
        quality = sizing.modifiers[5]
        assert quality.multiplier == 1.0
        assert "المعايرة" in quality.rationale  # تأجيل معلن لا صمت

    def test_resulting_risk_never_exceeds_budget(self) -> None:
        _s, _stop, sizing = self._reference_sizing()
        assert sizing.resulting_risk_money <= sizing.risk_budget + 1e-9
        assert sizing.resulting_risk_money == pytest.approx(
            sizing.position_size * sizing.stop_distance_value
        )

    def test_instrument_cap_binds(self) -> None:
        # سقف أداة ضيق: الحجم يقيد والخطر الناتج يهبط تحت الميزانية
        config = default_risk_config().model_copy(update={"instrument_position_cap": 0.05})
        _s, _stop, sizing = self._reference_sizing(config)
        assert sizing.capped_by is SizingCapBasis.INSTRUMENT
        assert sizing.position_size == pytest.approx(0.05)
        assert sizing.resulting_risk_money < sizing.risk_budget

    def test_portfolio_cap_binds(self) -> None:
        from _scenario_fixtures import make_market_state

        scenario = triggered_scenario()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        sizing = compute_sizing(
            scenario,
            stop,
            config=config,
            context=healthy_context(),
            market_state=make_market_state(),
            decision_time=DECISION_TIME,
            portfolio_cap_remaining=0.01,
        )
        assert sizing.capped_by is SizingCapBasis.PORTFOLIO
        assert sizing.position_size == pytest.approx(0.01)

    def test_drawdown_modifier_scales_linearly(self) -> None:
        from _scenario_fixtures import make_market_state

        scenario = triggered_scenario()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        sizing_half = compute_sizing(
            scenario,
            stop,
            config=config,
            context=healthy_context(risk_used_today=config.daily_loss_cap * 0.5),
            market_state=make_market_state(),
            decision_time=DECISION_TIME,
        )
        drawdown = sizing_half.modifiers[4]
        assert drawdown.multiplier == pytest.approx(0.5)

    def test_event_risk_cap_shrinks_budget(self) -> None:
        window = MacroEventWindow(
            event_time=DECISION_TIME,
            asset_scope="*",
            importance="MEDIUM",  # غير عالية الأثر: تقلص الميزانية ولا تحجب
            title="بيان مخزونات",
            pre_event_window_s=600.0,
            post_event_window_s=300.0,
        )
        config = default_risk_config()
        context = healthy_context(embargo_windows=(window,))
        budget = risk_budget_for(config, context, DECISION_TIME)
        assert budget == pytest.approx(config.event_risk_cap)
        # خارج النافذة: الميزانية كاملة
        from datetime import timedelta

        later = DECISION_TIME + timedelta(hours=2)
        assert risk_budget_for(config, context, later) == pytest.approx(config.per_trade_risk_cap)


class TestCosts:
    """التكاليف §25.2/§23.5 — التحلل والأنماط الثلاثة وR الصافية."""

    def _reference_reward(self, mode: CostMode = CostMode.REALISTIC) -> RewardRiskEstimate:
        scenario = triggered_scenario()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        return estimate_reward_risk(
            stop,
            target_level=scenario.primary_targets[0].price_level,
            direction=scenario.direction,
            config=config,
            cost_mode=mode,
        )

    def test_decomposition_identity_holds(self) -> None:
        reward = self._reference_reward()
        breakdown = reward.breakdown
        total = (
            breakdown.spread
            + breakdown.commission
            + breakdown.slippage
            + breakdown.funding_financing
            + breakdown.other_execution_costs
        )
        assert breakdown.net_trading_edge == pytest.approx(breakdown.gross_price_edge - total)

    def test_three_modes_differ_and_stress_is_harshest(self) -> None:
        optimistic = self._reference_reward(CostMode.OPTIMISTIC)
        realistic = self._reference_reward(CostMode.REALISTIC)
        stress = self._reference_reward(CostMode.STRESS)
        assert optimistic.estimated_net_r > realistic.estimated_net_r > stress.estimated_net_r
        # العمولة تعاقدية لا تقيّس بالنمط
        assert optimistic.commission_fee == realistic.commission_fee == stress.commission_fee

    def test_net_r_is_edge_over_stop(self) -> None:
        reward = self._reference_reward()
        assert reward.estimated_net_r == pytest.approx(
            reward.breakdown.net_trading_edge / reward.stop_distance
        )
        assert reward.gross_r == pytest.approx(reward.gross_target_distance / reward.stop_distance)

    def test_round_trip_cost_scales_with_mode(self) -> None:
        config = default_risk_config()
        optimistic = round_trip_cost(config, CostMode.OPTIMISTIC)
        realistic = round_trip_cost(config, CostMode.REALISTIC)
        stress = round_trip_cost(config, CostMode.STRESS)
        assert optimistic < realistic < stress

    def test_reference_setup_clears_min_net_r(self) -> None:
        """المرجع السليم يعبر الحد الأدنى — الرفض للفاسد لا للسليم."""
        reward = self._reference_reward()
        assert reward.estimated_net_r >= default_risk_config().min_net_r
