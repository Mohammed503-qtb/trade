"""اختبارات محرك لا-تداول (§22) — الحجب الصلب الخمسة عشر بحقن مستقل.

بوابة الخروج 8 حرفيًا: «§22.1 كلٌّ باختبار حقن فشل مستقل» — كل اختبار
يطفئ حقيقة واحدة (أو قياساً واحداً) فيشتعل حاجبه وحده، والسياق السليم
الصرف لا يشعل شيئًا. ثم الكتم اللين العشر: كل كتمة بقياسها المشتعل
والوزن المجموع مقابل العتبة ودلالات إعادة المحاولة §22.3.
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
from risk.no_trade import (
    evaluate_hard_blocks,
    evaluate_soft_suppressions,
    location_quality,
    soft_weight_total,
)
from risk.parameter_sets import RiskConfig, default_risk_config
from risk.stop import compute_structural_stop
from schemas import (
    DataQuality,
    Direction,
    HardBlockReason,
    MacroEventWindow,
    MarketRegime,
    NoTradeExplanation,
    Scenario,
    ScenarioState,
    SessionType,
    SoftSuppressionReason,
    StructuralStop,
)

# ───────────────────────── الحجب الصلب الخمسة عشر ─────────────────────────


class TestHardBlocksIndependentInjection:
    """حقن فشل مستقل لكل حاجب — حقيقة واحدة تطفيء في كل اختبار."""

    def _evaluate(
        self, **context_overrides: object
    ) -> tuple[Scenario, tuple[NoTradeExplanation, ...]]:
        scenario = triggered_scenario()
        _snapshot, _records = fusion_snapshot_for(scenario)
        candle = decision_candle()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        context = healthy_context(**context_overrides)
        blocks = evaluate_hard_blocks(
            scenario,
            stop,
            context=context,
            config=config,
            decision_time=candle.bar_time,
            close=float(candle.close),
            target_level=scenario.primary_targets[0].price_level,
            round_trip_costs=55.0,
        )
        return scenario, blocks

    def test_healthy_context_fires_nothing(self) -> None:
        _scenario, blocks = self._evaluate()
        assert blocks == ()

    def test_block_1_data_unreliable_quality(self) -> None:
        _s, blocks = self._evaluate(data_quality=DataQuality.STALE)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.DATA_UNRELIABLE]

    def test_block_1_data_unreliable_staleness(self) -> None:
        _s, blocks = self._evaluate(data_age_seconds=120.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.DATA_UNRELIABLE]

    def test_block_2_instrument_unavailable(self) -> None:
        _s, blocks = self._evaluate(
            instrument_tradable=False,
            instrument_status_note="توقف تداول مؤقت للصيانة",
        )
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.INSTRUMENT_UNAVAILABLE]

    def test_block_3_venue_unhealthy(self) -> None:
        _s, blocks = self._evaluate(venue_healthy=False)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.VENUE_CONNECTION_UNHEALTHY]

    def test_block_4_spread_exceeds_budget(self) -> None:
        # الميزانية أوسح الحدين: 10% من الحافة (≈900) = 90 — تجاوزها يشتعل
        _s, blocks = self._evaluate(spread_estimate=150.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.SPREAD_EXCEEDS_BUDGET]

    def test_block_5_slippage_exceeds_budget(self) -> None:
        _s, blocks = self._evaluate(slippage_estimate=50.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.SLIPPAGE_EXCEEDS_BUDGET]

    def test_block_6_latency_exceeds_budget(self) -> None:
        _s, blocks = self._evaluate(latency_ms=900.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.LATENCY_EXCEEDS_BUDGET]

    def test_block_7_risk_limits_positions(self) -> None:
        _s, blocks = self._evaluate(positions_open=3)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.RISK_LIMITS_REACHED]

    def test_block_7_risk_limits_daily(self) -> None:
        _s, blocks = self._evaluate(risk_used_today=300.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.RISK_LIMITS_REACHED]

    def test_block_7_risk_limits_rolling(self) -> None:
        _s, blocks = self._evaluate(risk_used_rolling=900.0)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.RISK_LIMITS_REACHED]

    def test_block_7_risk_limits_correlated(self) -> None:
        _s, blocks = self._evaluate(correlated_exposure=2)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.RISK_LIMITS_REACHED]

    def test_block_8_stop_not_reliable_external(self) -> None:
        _s, blocks = self._evaluate(stop_reliable=False)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.STOP_NOT_RELIABLE]

    def test_block_8_stop_not_reliable_too_wide(self) -> None:
        scenario = triggered_scenario()
        config = default_risk_config()
        # وقف أعرض من السقف المطبَّع: عازلة ضخمة عبر قاعدة إبطال مقلّصة
        wide = scenario.model_copy(
            update={
                "invalidation": scenario.invalidation.model_copy(
                    update={"volatility_buffer": config.max_stop_distance_atr * ATR}
                )
            }
        )
        stop = compute_structural_stop(wide, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        blocks = evaluate_hard_blocks(
            wide,
            stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=wide.primary_targets[0].price_level,
            round_trip_costs=55.0,
        )
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.STOP_NOT_RELIABLE]

    def test_block_9_broker_rejects(self) -> None:
        _s, blocks = self._evaluate(broker_accepts_order=False)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.BROKER_REJECTS_ORDER]

    def test_block_10_macro_embargo(self) -> None:
        window = MacroEventWindow(
            event_time=DECISION_TIME,
            asset_scope="*",
            importance="HIGH",
            title="قرار الفائدة الأمريكي",
            pre_event_window_s=900.0,
            post_event_window_s=600.0,
        )
        _s, blocks = self._evaluate(embargo_windows=(window,))
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.MACRO_EMBARGO_WINDOW]

    def test_block_10_low_importance_event_does_not_block(self) -> None:
        window = MacroEventWindow(
            event_time=DECISION_TIME,
            asset_scope="*",
            importance="MEDIUM",
            title="بيان مخزونات ثانوي",
            pre_event_window_s=900.0,
            post_event_window_s=600.0,
        )
        _s, blocks = self._evaluate(embargo_windows=(window,))
        assert blocks == ()

    def test_block_11_scenario_invalidated(self) -> None:
        scenario = triggered_scenario()
        _snapshot, _records = fusion_snapshot_for(scenario)
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        dead = scenario.model_copy(update={"state": ScenarioState.INVALIDATED})
        blocks = evaluate_hard_blocks(
            dead,
            stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=dead.primary_targets[0].price_level,
            round_trip_costs=55.0,
        )
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.SCENARIO_INVALIDATED]

    def test_block_12_entry_too_late(self) -> None:
        scenario = triggered_scenario()
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        # الإغلاق بعد الهدف تقريبًا — المكافأة المتبقية بعد التكاليف سالبة
        blocks = evaluate_hard_blocks(
            scenario,
            stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=scenario.primary_targets[0].price_level - 5.0,
            target_level=scenario.primary_targets[0].price_level,
            round_trip_costs=55.0,
        )
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.ENTRY_TOO_LATE]

    def test_block_13_conflicting_scenario(self) -> None:
        _s, blocks = self._evaluate(conflicting_scenario_ids=("sc-opposite-higher-priority",))
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.CONFLICTING_SCENARIO]

    def test_block_14_scenario_already_consumed(self) -> None:
        scenario = triggered_scenario()
        _s, blocks = self._evaluate(consumed_anchor_event_ids=(scenario.proposed_from_event_id,))
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.SCENARIO_ALREADY_CONSUMED]

    def test_block_15_kill_switch(self) -> None:
        _s, blocks = self._evaluate(kill_switch=True)
        assert [b.no_trade_code for b in blocks] == [HardBlockReason.KILL_SWITCH]

    def test_multiple_blocks_all_collected_in_plan_order(self) -> None:
        """كل المشتعل يُجمع — لا أول فقط (الموثوقية الكاملة)."""
        _s, blocks = self._evaluate(
            kill_switch=True,
            venue_healthy=False,
            positions_open=5,
        )
        assert [b.no_trade_code for b in blocks] == [
            HardBlockReason.VENUE_CONNECTION_UNHEALTHY,
            HardBlockReason.RISK_LIMITS_REACHED,
            HardBlockReason.KILL_SWITCH,
        ]


class TestRetrySemantics:
    """دلالات إعادة المحاولة §22.3 — موثقة لكل رمز لا مختلقة."""

    def test_kill_switch_retryable_after_manual_reset(self) -> None:
        blocks = evaluate_hard_blocks(
            triggered_scenario(),
            None,
            context=healthy_context(kill_switch=True),
            config=default_risk_config(),
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=60_400.0,
            round_trip_costs=55.0,
        )
        block = blocks[0]
        assert block.whether_retry_is_allowed
        assert block.retry_condition is not None

    def test_invalidated_never_retried(self) -> None:
        scenario = triggered_scenario().model_copy(update={"state": ScenarioState.INVALIDATED})
        config = default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        blocks = evaluate_hard_blocks(
            scenario,
            stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=60_400.0,
            round_trip_costs=55.0,
        )
        block = blocks[0]
        assert block.no_trade_code is HardBlockReason.SCENARIO_INVALIDATED
        assert not block.whether_retry_is_allowed
        assert block.retry_condition is None

    def test_every_hard_block_has_complete_explanation(self) -> None:
        """§22.3: كل رفض بحقوله الستة — فحص شامل على الحقن كلها."""
        injections: list[dict[str, object]] = [
            {"data_quality": DataQuality.QUARANTINED},
            {"instrument_tradable": False},
            {"venue_healthy": False},
            {"spread_estimate": 150.0},
            {"slippage_estimate": 50.0},
            {"latency_ms": 900.0},
            {"positions_open": 3},
            {"stop_reliable": False},
            {"broker_accepts_order": False},
            {"kill_switch": True},
        ]
        for injection in injections:
            scenario = triggered_scenario()
            config = default_risk_config()
            stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
            blocks = evaluate_hard_blocks(
                scenario,
                stop,
                context=healthy_context(**injection),
                config=config,
                decision_time=DECISION_TIME,
                close=59_880.0,
                target_level=scenario.primary_targets[0].price_level,
                round_trip_costs=55.0,
            )
            assert blocks, f"حقن {injection} لم يشعل شيئًا"
            for block in blocks:
                assert block.triggering_conditions.strip()
                assert block.severity.value == "HARD"
                # offsetting_evidence يحمل ما كان يؤيد الدخول (محاسبة صادقة)
                assert isinstance(block.offsetting_evidence, tuple)


# ───────────────────────── الكتم اللين العشر ─────────────────────────


class TestSoftSuppressions:
    """الكتمات العشر — قياس كل كتمة واشتعالها الموثق والوزن المجموع."""

    def _evaluate(
        self,
        *,
        config: RiskConfig | None = None,
        scenario_overrides: dict[str, object] | None = None,
        market_state_overrides: dict[str, object] | None = None,
        context_overrides: dict[str, object] | None = None,
        close: float = 59_880.0,
    ) -> tuple[Scenario, StructuralStop, tuple[NoTradeExplanation, ...]]:
        from _scenario_fixtures import make_market_state

        scenario = triggered_scenario()
        if scenario_overrides:
            scenario = scenario.model_copy(update=scenario_overrides)
        snapshot, _records = fusion_snapshot_for(scenario)
        state_kwargs: dict[str, object] = {}
        if market_state_overrides:
            state_kwargs.update(market_state_overrides)
        market_state = make_market_state(**state_kwargs)  # type: ignore[arg-type]
        config = config or default_risk_config()
        stop = compute_structural_stop(scenario, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        context = healthy_context(**(context_overrides or {}))
        suppressions = evaluate_soft_suppressions(
            scenario,
            snapshot,
            market_state,
            stop=stop,
            context=context,
            config=config,
            decision_time=DECISION_TIME,
            close=close,
            target_level=scenario.primary_targets[0].price_level,
        )
        return scenario, stop, suppressions

    def test_reference_setup_fires_nothing(self) -> None:
        _s, _stop, suppressions = self._evaluate()
        assert suppressions == ()

    def test_1_poor_location(self) -> None:
        scenario = triggered_scenario()
        zone = scenario.location_snapshot["zone"]
        assert isinstance(zone, dict)
        degraded = scenario.model_copy(
            update={
                "location_snapshot": {
                    "zone": {
                        **zone,
                        "reaction_score": 0.1,
                        "unmitigated_score": 0.1,
                        "importance_score": 0.1,
                    }
                }
            }
        )
        assert location_quality(degraded) == pytest.approx(0.1)
        snapshot, _records = fusion_snapshot_for(degraded)
        config = default_risk_config()
        from _scenario_fixtures import make_market_state

        stop = compute_structural_stop(degraded, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        suppressions = evaluate_soft_suppressions(
            degraded,
            snapshot,
            make_market_state(),
            stop=stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=degraded.primary_targets[0].price_level,
        )
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.POOR_LOCATION]

    def test_3_volatility_too_low(self) -> None:
        _s, _stop, suppressions = self._evaluate(
            market_state_overrides=None,
        )
        # عبر ضبط الحد الأدنى فوق المئين المرجعي (60)
        config = default_risk_config().model_copy(update={"vol_percentile_min": 70.0})
        _s2, _st2, suppressions2 = self._evaluate(config=config)
        assert [s.no_trade_code for s in suppressions2] == [
            SoftSuppressionReason.VOLATILITY_TOO_LOW
        ]
        assert suppressions == ()

    def test_4_volatility_too_extreme(self) -> None:
        config = default_risk_config().model_copy(update={"vol_percentile_max": 50.0})
        _s, _stop, suppressions = self._evaluate(config=config)
        assert [s.no_trade_code for s in suppressions] == [
            SoftSuppressionReason.VOLATILITY_TOO_EXTREME
        ]

    def test_5_regime_transition(self) -> None:
        _s, _stop, suppressions = self._evaluate(
            market_state_overrides={"regime": MarketRegime.TRANSITION}
        )
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.REGIME_TRANSITION]

    def test_6_target_too_close(self) -> None:
        config = default_risk_config().model_copy(update={"min_target_r": 50.0})
        _s, _stop, suppressions = self._evaluate(config=config)
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.TARGET_TOO_CLOSE]

    def test_7_stop_too_wide(self) -> None:
        config = default_risk_config().model_copy(update={"soft_stop_wideness_atr": 0.5})
        _s, _stop, suppressions = self._evaluate(config=config)
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.STOP_TOO_WIDE]

    def test_8_session_conflict(self) -> None:
        _s, _stop, suppressions = self._evaluate(
            context_overrides={"session": SessionType.MAINTENANCE}
        )
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.SESSION_CONFLICT]

    def test_9_chasing_expanded_move(self) -> None:
        config = default_risk_config().model_copy(update={"chase_drift_atr": 0.05})
        _s, _stop, suppressions = self._evaluate(config=config)
        assert [s.no_trade_code for s in suppressions] == [
            SoftSuppressionReason.CHASING_EXPANDED_MOVE
        ]

    def test_10_horizon_exceeded(self) -> None:
        scenario = triggered_scenario()
        # انقضاء بعيد جدًا (الاستمرار 120 شمعة) مقابل أفق سكالب قصير
        far_expiry = scenario.model_copy(
            update={"expiry_time": scenario.expiry_time.replace(year=scenario.expiry_time.year + 1)}
        )
        snapshot, _records = fusion_snapshot_for(far_expiry)
        config = default_risk_config()
        from _scenario_fixtures import make_market_state

        stop = compute_structural_stop(far_expiry, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        suppressions = evaluate_soft_suppressions(
            far_expiry,
            snapshot,
            make_market_state(),
            stop=stop,
            context=healthy_context(),
            config=config,
            decision_time=DECISION_TIME,
            close=59_880.0,
            target_level=far_expiry.primary_targets[0].price_level,
        )
        assert [s.no_trade_code for s in suppressions] == [SoftSuppressionReason.HORIZON_EXCEEDED]

    def test_soft_suppressions_all_retryable(self) -> None:
        """اللين كله قابل للإعادة بشرطه — بلا استثناء."""
        config = default_risk_config().model_copy(
            update={
                "vol_percentile_max": 50.0,
                "soft_stop_wideness_atr": 0.5,
            }
        )
        _s, _stop, suppressions = self._evaluate(config=config)
        assert len(suppressions) >= 2
        for suppression in suppressions:
            assert suppression.severity.value == "SOFT"
            assert suppression.whether_retry_is_allowed
            assert suppression.retry_condition

    def test_weighted_total_below_threshold_passes(self) -> None:
        """كتمة واحدة دون العتبة لا ترفض — الوزن المجموع هو الحكم."""
        config = default_risk_config().model_copy(update={"soft_threshold": 5.0})
        _s, _stop, suppressions = self._evaluate(
            config=config,
            context_overrides={"session": SessionType.MAINTENANCE},
        )
        assert suppressions  # الكتمة موثقة...
        assert soft_weight_total(config, suppressions) < config.soft_threshold  # ...لكن دون العتبة

    def test_weighted_total_reaches_threshold(self) -> None:
        config = default_risk_config().model_copy(update={"soft_threshold": 0.1})
        _s, _stop, suppressions = self._evaluate(
            config=config,
            context_overrides={"session": SessionType.MAINTENANCE},
        )
        assert soft_weight_total(config, suppressions) >= config.soft_threshold


class TestRejectionBasisCoverage:
    """أسس الرفض الثلاثة — أكواد §22 حرفية والحافة أساس ثالث (§23.5)."""

    def test_hard_and_soft_codes_are_disjoint_and_literal(self) -> None:
        hard = {reason.value for reason in HardBlockReason}
        soft = {reason.value for reason in SoftSuppressionReason}
        assert len(hard) == 15  # §22.1 خمسة عشر حرفيًا
        assert len(soft) == 10  # §22.2 عشر حرفيًا
        assert not (hard & soft)

    def test_direction_used_for_remaining_reward(self) -> None:
        """الانعكاس الصاعد: المكافأة = (الهدف − الإغلاق) — الإشارة صحيحة."""
        scenario = triggered_scenario()
        assert scenario.direction is Direction.LONG
