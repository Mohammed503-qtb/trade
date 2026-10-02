"""اختبارات محرك الوسم (§30) — الحالات الخمس والترتيب المتحفظ وانضباط الأفق.

«Each candidate scenario receives a label only after its defined
evaluation horizon ends» — الترجمة من المخرج إلى الدلالة بلا اختلاق.
"""

from __future__ import annotations

import pytest
from backtest import label_for
from schemas import ExitReason, LabelState


def test_target_first() -> None:
    result = label_for(exit_reason=ExitReason.TARGET, net_realized_edge=1.5)
    assert result is LabelState.TARGET_FIRST


def test_invalidation_first() -> None:
    result = label_for(exit_reason=ExitReason.STOP, net_realized_edge=-1.0)
    assert result is LabelState.INVALIDATION_FIRST


def test_not_executable_unfilled() -> None:
    assert (
        label_for(exit_reason=ExitReason.UNFILLED, net_realized_edge=None)
        is LabelState.NOT_EXECUTABLE
    )


def test_timeout_profit_is_net_of_costs() -> None:
    """عتبة الربح صافيةً بعد تكاليف REALISTIC — لا إجمالي (§30 حرفيًا)."""
    assert (
        label_for(exit_reason=ExitReason.TIMEOUT, net_realized_edge=0.01)
        is LabelState.TIMEOUT_WITH_PROFIT
    )
    assert (
        label_for(exit_reason=ExitReason.TIMEOUT, net_realized_edge=0.0)
        is LabelState.TIMEOUT_WITH_LOSS
    )
    assert (
        label_for(exit_reason=ExitReason.TIMEOUT, net_realized_edge=-0.5)
        is LabelState.TIMEOUT_WITH_LOSS
    )


def test_entry_expiry_labels_by_net() -> None:
    """دخول ناقص قطعته المهلة يوسم بعتبة الصافي نفسها."""
    assert (
        label_for(exit_reason=ExitReason.ENTRY_EXPIRY, net_realized_edge=0.2)
        is LabelState.TIMEOUT_WITH_PROFIT
    )
    assert (
        label_for(exit_reason=ExitReason.ENTRY_EXPIRY, net_realized_edge=-0.2)
        is LabelState.TIMEOUT_WITH_LOSS
    )


def test_unresolved_returns_none() -> None:
    """بيانات أقصر من الأفق ⇒ بلا وسم — لا يُختلق حكم لم يقع (§30)."""
    assert label_for(exit_reason=None, net_realized_edge=None) is None


def test_timeout_without_net_rejected() -> None:
    """وسم مهلة بلا صافٍ رفض صريح — لا عتبة ربح بلا تكاليف."""
    with pytest.raises(ValueError, match="يتطلب الصافي"):
        label_for(exit_reason=ExitReason.TIMEOUT, net_realized_edge=None)
