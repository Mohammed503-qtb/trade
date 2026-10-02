"""اختبارات المقاييس (§29.2/§39.2) — توقع صافٍ وعامل ربح وتوزيع R حسب النظام.

الصفقات تُبنى بالمنفّذ نفسه على مسارات معلنة — لا صفقات مختلقة يدويًا
تتجاوز عقود المحاكي.
"""

from __future__ import annotations

import pytest
from _backtest_fixtures import candle_at, entry_spec
from backtest import SimulatedExecutor, compute_metrics, net_r_of
from schemas import BacktestMetrics, Direction, EntrySpec, LabelState, SimulatedTrade


def _trade(
    executor: SimulatedExecutor,
    *,
    side: Direction = Direction.LONG,
    regime: str = "TREND",
    scenario_index: int = 0,
) -> SimulatedTrade:
    """صفقة منفذة على مسار معلن — هدف بعيد يكسب بعد التكاليف (مقياس واقعي)."""
    spec = _winning_spec(side=side, regime=regime, scenario_index=scenario_index)
    if side is Direction.LONG:
        path = (
            candle_at(0, 100.6, 100.7, 100.5, 100.6),
            candle_at(1, 100.4, 100.45, 100.1, 100.3),  # تعبئة
            candle_at(2, 100.5, 105.4, 100.4, 105.2),  # هدف بعيد
        )
    else:
        path = (
            candle_at(0, 99.4, 99.5, 99.3, 99.45),
            candle_at(1, 99.7, 99.9, 99.55, 99.8),  # تعبئة
            candle_at(2, 95.5, 99.4, 94.9, 95.3),  # هدف بعيد
        )
    return executor.execute(spec, path)


def _winning_spec(
    *,
    side: Direction = Direction.LONG,
    regime: str = "TREND",
    scenario_index: int = 0,
) -> EntrySpec:
    """مواصفة دخول رابحة بعد التكاليف — الهدف بعيد (4.5 وحدات مقابل 1.64 تكاليف)."""
    return entry_spec(
        side=side,
        regime=regime,
        target_price=105.0 if side is Direction.LONG else 95.0,
        trade_intent_id=f"ti-{scenario_index}",
        scenario_id=f"sc-{scenario_index}",
        decision_id=f"dc-{scenario_index}",
    )


def _portfolio() -> list[SimulatedTrade]:
    """محفظة صغيرة متنوعة الوسوم والأنظمة — أساس الإحصاءات."""
    executor = SimulatedExecutor()
    trades = [
        _trade(executor, regime="TREND", scenario_index=1),  # TARGET_FIRST رابح
        _trade(executor, regime="RANGE", scenario_index=2),  # TARGET_FIRST رابح
    ]
    # خاسر: وقف بعد تعبئة
    spec = entry_spec(
        regime="TREND",
        trade_intent_id="ti-3",
        scenario_id="sc-3",
        decision_id="dc-3",
    )
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.2, 100.5, 99.4, 99.6),  # وقف
    )
    trades.append(executor.execute(spec, path))
    # غير منفذ: نافذة انقضت بلا لمس
    spec_unfilled = entry_spec(
        horizon_minutes=10,
        trade_intent_id="ti-4",
        scenario_id="sc-4",
        decision_id="dc-4",
    )
    far = tuple(candle_at(m, 105.0, 105.5, 104.8, 105.1) for m in range(15))
    trades.append(executor.execute(spec_unfilled, far))
    return trades


def test_metrics_over_portfolio() -> None:
    """الإحصاءات الكاملة: توقع/عامل ربح/توزيع/معدل ربح حسب النظام."""
    trades = _portfolio()
    metrics = compute_metrics(trades)
    assert metrics.labeled_trades == 4
    assert metrics.not_executable == 1
    assert metrics.open_at_data_end == 0
    assert metrics.label_counts["TARGET_FIRST"] == 2
    assert metrics.label_counts["INVALIDATION_FIRST"] == 1
    assert metrics.label_counts["NOT_EXECUTABLE"] == 1
    # ثلاث صفقات قامت: رابحتان وخاسر واحد — معدل الربح 2/3
    assert metrics.win_rate == pytest.approx(2.0 / 3.0)
    # عامل الربح = مجموع الرابح ÷ |مجموع الخاسر|
    winners = [t for t in trades if t.label is LabelState.TARGET_FIRST]
    losers = [t for t in trades if t.label is LabelState.INVALIDATION_FIRST]
    traded = [*winners, *losers]
    expected_pf = sum(net_r_of(t) for t in winners) / abs(net_r_of(losers[0]))
    assert metrics.profit_factor == pytest.approx(expected_pf)
    # التوقع متوسط الرابحين والخاسر
    expected_mean = sum(net_r_of(t) for t in traded) / 3
    assert metrics.net_expectancy_r == pytest.approx(expected_mean)
    # التوزيع
    assert metrics.r_distribution.max_r == pytest.approx(max(net_r_of(t) for t in traded))
    assert metrics.r_distribution.min_r == pytest.approx(min(net_r_of(t) for t in traded))
    # حسب النظام: TREND صفقتان (رابحة وخاسرة) وRANGE صفقة رابحة
    by_regime = {r.regime: r for r in metrics.by_regime}
    assert set(by_regime) == {"TREND", "RANGE"}
    assert by_regime["TREND"].trades_count == 2
    assert by_regime["RANGE"].trades_count == 1
    assert by_regime["RANGE"].profit_factor is None  # لا خاسرين في RANGE — غياب معلن


def test_no_losers_profit_factor_none() -> None:
    """انعدام الخاسرين ⇒ عامل الربح None معلن — لا اختلاق ∞."""
    executor = SimulatedExecutor()
    trades = [
        _trade(executor, regime="TREND", scenario_index=1),
        _trade(executor, regime="RANGE", scenario_index=2),
    ]
    metrics = compute_metrics(trades)
    assert metrics.profit_factor is None
    assert metrics.win_rate == pytest.approx(1.0)


def test_all_losers_profit_factor_zero() -> None:
    """كلها خاسرة ⇒ عامل الربح صفرًا قانونيًا معلنًا (لا رابحين)."""
    executor = SimulatedExecutor()
    # وقفان: خسارة إجمالية مع تكاليفها — لا رابح في المجموعة
    loser = executor.execute(
        entry_spec(trade_intent_id="ti-l", scenario_id="sc-l", decision_id="dc-l"),
        (
            candle_at(0, 100.6, 100.7, 100.5, 100.6),
            candle_at(1, 100.4, 100.45, 100.1, 100.3),
            candle_at(2, 100.2, 100.5, 99.4, 99.6),  # وقف
        ),
    )
    metrics = compute_metrics([loser])
    assert metrics.profit_factor == pytest.approx(0.0)
    assert metrics.win_rate == pytest.approx(0.0)
    assert metrics.by_regime[0].profit_factor == pytest.approx(0.0)


def test_no_trades_rejected() -> None:
    """لا صفقة قامت ⇒ رفض صريح — المقاييس تحتاج أساسًا."""
    executor = SimulatedExecutor()
    unfilled_spec = entry_spec(
        horizon_minutes=5, trade_intent_id="ti-x", scenario_id="sc-x", decision_id="dc-x"
    )
    far = tuple(candle_at(m, 105.0, 105.5, 104.8, 105.1) for m in range(10))
    trades = [executor.execute(unfilled_spec, far)]
    with pytest.raises(ValueError, match="لا صفقة منتهية"):
        compute_metrics(trades)


def test_metrics_schema_legality() -> None:
    """المقاييس تمر عقد schemas — عدادات الوسم متطابقة والأنظمة بلا تكرار."""
    metrics = compute_metrics(_portfolio())
    validated = BacktestMetrics.model_validate(metrics.model_dump())
    assert validated == metrics
