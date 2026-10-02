"""اختبارات التكاليف المحققة (§25.2) — التحلل السداسي بلا ازدواج.

المتطابقة محقاة في العقد نفسه؛ هنا نثبت القيم المحسوبة يدويًا للأنماط
الثلاثة وأن REALISTIC وحده نمط القبول.
"""

from __future__ import annotations

import pytest
from backtest import BacktestConfig, realize_costs
from schemas import CostMode, Direction, RealizedCosts


def _config() -> BacktestConfig:
    return BacktestConfig()


def test_realistic_decomposition_hand_computed() -> None:
    """ذهبي: شراء 100.5 ومخرج 102.0 — كل مكون محسوب باليد."""
    costs = realize_costs(
        side=Direction.LONG,
        entry_price=100.5,
        exit_price=102.0,
        config=_config(),
        holding_s=3600.0,
    )
    assert costs.cost_mode is CostMode.REALISTIC
    assert costs.gross_realized_edge == pytest.approx(1.5)
    assert costs.spread == pytest.approx(1.0)  # 2 × 0.5
    assert costs.slippage == pytest.approx(0.6)  # 2 × 0.3
    assert costs.commission == pytest.approx(2.0 * 1e-4 * 202.5)
    assert costs.funding_financing == pytest.approx(0.0)  # سبوت MVP موثق
    assert costs.other_execution_costs == pytest.approx(0.0)  # موثق MVP
    total = 1.0 + 0.6 + 2.0 * 1e-4 * 202.5
    assert costs.net_realized_edge == pytest.approx(1.5 - total)


def test_short_gross_sign() -> None:
    """بيع: الإجمالي (مخرج − دخول) × (−1) — الخسارة سالبة قبل التكاليف."""
    costs = realize_costs(
        side=Direction.SHORT,
        entry_price=99.5,
        exit_price=98.0,
        config=_config(),
    )
    assert costs.gross_realized_edge == pytest.approx(1.5)


def test_three_modes_differ_and_stress_is_worst() -> None:
    """الأنماط الثلاثة متمايزة وSTRESS أثقلها وOPTIMISTIC أخفها (§25.1)."""
    results = {
        mode: realize_costs(
            side=Direction.LONG,
            entry_price=100.5,
            exit_price=102.0,
            config=_config(),
            mode=mode,
        )
        for mode in CostMode
    }
    optimistic = results[CostMode.OPTIMISTIC].net_realized_edge
    realistic = results[CostMode.REALISTIC].net_realized_edge
    stress = results[CostMode.STRESS].net_realized_edge
    assert optimistic > realistic > stress


def test_mode_schedules_required_complete() -> None:
    """إعداد بلا الأنماط الثلاثة رفض صريح — لا قبول بنمط مفقود."""
    realistic_only = BacktestConfig().schedule_for(CostMode.REALISTIC)
    incomplete = {"cost_schedules": {CostMode.REALISTIC: realistic_only}}
    with pytest.raises(ValueError, match="ناقصة الأنماط"):
        BacktestConfig(**incomplete)  # type: ignore[arg-type]


def test_missing_exit_rejected() -> None:
    """لا تحلل محقق بلا مخرج وقع — المفتوح عند نهاية البيانات بلا تكاليف."""
    with pytest.raises(ValueError, match="يتطلب مخرجًا"):
        realize_costs(
            side=Direction.LONG,
            entry_price=100.5,
            exit_price=None,
            config=_config(),
        )


def test_identity_enforced_by_contract() -> None:
    """العقد يرفض تحللًا غير متطابق — صاخب لا تقريب صامت."""
    with pytest.raises(ValueError, match="غير متطابق"):
        RealizedCosts(
            cost_mode=CostMode.REALISTIC,
            gross_realized_edge=1.5,
            spread=1.0,
            commission=0.1,
            slippage=0.6,
            funding_financing=0.0,
            other_execution_costs=0.0,
            net_realized_edge=0.5,  # متعمد كسر المتطابقة
        )


def test_funding_formula_armed() -> None:
    """معادلة التمويل مسلحة وجاهزة — صفر MVP من الجدول لا من الصيغة."""
    custom = BacktestConfig(
        cost_schedules={
            mode: (
                _config().schedule_for(mode).model_copy(update={"funding_per_holding_h": 0.01})
                if mode is CostMode.REALISTIC
                else _config().schedule_for(mode)
            )
            for mode in CostMode
        }
    )
    costs = realize_costs(
        side=Direction.LONG,
        entry_price=100.5,
        exit_price=102.0,
        config=custom,
        holding_s=7200.0,
    )
    assert costs.funding_financing == pytest.approx(0.01 * 2.0)
