"""خصائص المخاطرة (hypothesis) — الخاصية المركزية للبوابة 8.

«تحقق: خاصية الخطر الناتج ≤ السقف دائمًا» (build_plan 8.3) — تثبت
على مدخلات عشوائية مقيدة: أياً كانت الميزانية ومسافة الوقف ووقائع
التشغيل والمعدلات، فالخطر الناتج لا يتجاوز الميزانية أبدًا والحجم
لا يتجاوز السقوف المطلقة أبدًا.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

_ROOT = Path(__file__).resolve().parents[2]
_PATHS = (
    "tests/unit",
    "services/risk/src",
    "services/scenarios/src",
    "services/fusion/src",
    "services/liquidity/src",
    "services/structure/src",
    "services/market_state/src",
    "packages/schemas/src",
    "packages/common/src",
    "packages/features/src",
)
for _relative in _PATHS:
    _candidate = _ROOT / _relative
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from _risk_fixtures import (  # noqa: E402
    ATR,
    DECISION_TIME,
    healthy_context,
    triggered_scenario,
)
from risk.parameter_sets import default_risk_config  # noqa: E402
from risk.sizing import compute_sizing  # noqa: E402
from risk.stop import compute_structural_stop  # noqa: E402
from schemas import InvalidationRule, SizingCapBasis  # noqa: E402

#: فترات مقيدة واقعية: ميزانية نقدي [10, 1000] ومسافة وقف [50, 5000].
_budgets = st.floats(min_value=10.0, max_value=1000.0, allow_nan=False)
_stop_distances = st.floats(min_value=50.0, max_value=5000.0, allow_nan=False)
_drawdown_fractions = st.floats(min_value=0.0, max_value=0.99, allow_nan=False)
_latency = st.floats(min_value=0.0, max_value=3000.0, allow_nan=False)


def _sized_scenario(stop_distance: float) -> Any:
    """سيناريو مرجعي بقاعدة إبطال مضبوطة على مسافة الوقف المطلوبة."""
    scenario = triggered_scenario()
    return scenario.model_copy(
        update={
            "invalidation": InvalidationRule(
                structural_level=scenario.invalidation.structural_level,
                volatility_buffer=max(
                    0.0,
                    (scenario.entry_zone.price_high - scenario.invalidation.structural_level)
                    - stop_distance,
                ),
                accept_through=scenario.invalidation.accept_through,
            )
        }
    )


class TestRiskNeverExceedsCap:
    """الخطر الناتج ≤ السقف دائمًا — فوق أي مدخلات عشوائية."""

    @given(
        budget=_budgets,
        stop_distance=_stop_distances,
        drawdown_fraction=_drawdown_fractions,
        latency=_latency,
    )
    def test_resulting_risk_within_budget_always(
        self,
        budget: float,
        stop_distance: float,
        drawdown_fraction: float,
        latency: float,
    ) -> None:
        config = default_risk_config().model_copy(update={"per_trade_risk_cap": budget})
        adjusted = _sized_scenario(stop_distance)
        stop = compute_structural_stop(adjusted, atr=ATR, config=config, latency_ms=latency)
        assert stop is not None
        context = healthy_context(
            risk_used_today=config.daily_loss_cap * drawdown_fraction,
            latency_ms=latency,
        )
        sizing = compute_sizing(
            adjusted,
            stop,
            config=config,
            context=context,
            market_state=adjusted.context_snapshot,
            decision_time=DECISION_TIME,
        )
        # الخاصية المركزية — بلا أي تسامح يتجاوز الحد:
        assert sizing.resulting_risk_money <= sizing.risk_budget
        assert sizing.position_size <= sizing.instrument_cap
        assert sizing.position_size <= sizing.portfolio_cap_remaining
        assert 0.0 < sizing.final_multiplier <= 1.0
        for modifier in sizing.modifiers:
            assert 0.0 < modifier.multiplier <= 1.0

    @given(budget=_budgets, stop_distance=_stop_distances)
    def test_caps_never_overshoot_positions(self, budget: float, stop_distance: float) -> None:
        """سقوف صغيرة جداً: الحجم يقيد والخطر يهبط — لا خرق أبدًا."""
        config = default_risk_config().model_copy(
            update={
                "per_trade_risk_cap": budget,
                "instrument_position_cap": 0.001,
                "portfolio_position_cap": 0.002,
            }
        )
        adjusted = _sized_scenario(stop_distance)
        stop = compute_structural_stop(adjusted, atr=ATR, config=config, latency_ms=250.0)
        assert stop is not None
        sizing = compute_sizing(
            adjusted,
            stop,
            config=config,
            context=healthy_context(),
            market_state=adjusted.context_snapshot,
            decision_time=DECISION_TIME,
        )
        assert sizing.capped_by in (SizingCapBasis.INSTRUMENT, SizingCapBasis.PORTFOLIO)
        assert sizing.position_size <= 0.001
        assert sizing.resulting_risk_money <= sizing.risk_budget
