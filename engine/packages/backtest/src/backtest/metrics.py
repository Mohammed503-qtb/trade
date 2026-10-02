"""المقاييس (§29.2/§39.2) — توقع صافٍ وعامل ربح وتوزيع R وMFE/MAE حسب النظام.

كل المقياسات على **R الصافية بعد تكاليف REALISTIC** («Net target
evaluation includes realistic costs» §30): صافي التحلل المحقق ÷ مسافة
وقف النية — وحدة القياس الموحدة عبر الصفقات.

قواعد الغياب المعلن (لا قيمة مختلقة):

- **عامل الربح ``None`` عند انعدام الخاسرين** — لا اختلاق ∞ (نمط
  مقيّم الاستئصال 5a.3 نفسه).
- الإحصاءات الرتبية (p05/p50/p95) باستيفاء خطي حتمي (numpy الافتراضي).
- NOT_EXECUTABLE لا يدخل إحصاءات R (لم تقم صفقة) — يُحصى عدًّا مستقلًا.
- الباقي مفتوحًا حتى نهاية البيانات لا يدخل شيئًا (لا وسم له — §30).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from schemas import (
    BacktestMetrics,
    LabelState,
    RDistribution,
    RegimeMetrics,
    SimulatedTrade,
)

__all__ = ["compute_metrics", "net_r_of"]

#: الحالات التي قامت فيها صفقة فعلًا — أساس إحصاءات R.
_TRADED_LABELS = frozenset(
    {
        LabelState.TARGET_FIRST,
        LabelState.INVALIDATION_FIRST,
        LabelState.TIMEOUT_WITH_PROFIT,
        LabelState.TIMEOUT_WITH_LOSS,
    }
)


def net_r_of(trade: SimulatedTrade) -> float:
    """R الصافية لصفقة منتهية — صافي التحلل المحقق ÷ مسافة الوقف.

    :raises ValueError: صفقة بلا تحلل (مفتوحة/غير منفذة) — لا R لما لم يقم.
    """
    if trade.costs is None:
        raise ValueError(
            f"لا R صافية لصفقة بلا تحلل محقق: {trade.trade_intent_id} "
            f"(exit_reason={trade.exit_reason})"
        )
    return trade.costs.net_realized_edge / trade.stop_distance


def compute_metrics(trades: Sequence[SimulatedTrade]) -> BacktestMetrics:
    """مقاييس الإعادة الكاملة من صفقات المحاكي.

    :raises ValueError: لا صفقة منتهية قامت — المقاييس بلا أساس.
    """
    label_counts: dict[str, int] = {}
    for trade in trades:
        if trade.label is None:
            continue
        label_counts[trade.label.value] = label_counts.get(trade.label.value, 0) + 1

    traded: list[SimulatedTrade] = []
    for trade in trades:
        if trade.label in _TRADED_LABELS:
            if trade.costs is None:
                raise ValueError(
                    f"صفقة موسومة {trade.label.value} بلا تحلل محقق: {trade.trade_intent_id}"
                )
            traded.append(trade)
    if not traded:
        raise ValueError(
            f"لا صفقة منتهية قامت بين {len(trades)} نية — المقاييس تحتاج أساسًا (§29.2)"
        )

    net_rs = np.array([net_r_of(t) for t in traded], dtype=float)
    gross_rs = np.array(
        [t.costs.gross_realized_edge / t.stop_distance for t in traded if t.costs is not None],
        dtype=float,
    )
    wins = net_rs[net_rs > 0.0]
    losses = net_rs[net_rs < 0.0]

    profit_factor: float | None = None
    if losses.size > 0:
        profit_factor = float(wins.sum() / abs(losses.sum()))

    by_regime: list[RegimeMetrics] = []
    for regime in sorted({t.regime for t in traded}):
        group = [t for t in traded if t.regime == regime]
        group_net = np.array([net_r_of(t) for t in group], dtype=float)
        group_wins = group_net[group_net > 0.0]
        group_losses = group_net[group_net < 0.0]
        group_pf: float | None = None
        if group_losses.size > 0:
            group_pf = float(group_wins.sum() / abs(group_losses.sum()))
        by_regime.append(
            RegimeMetrics(
                regime=regime,
                trades_count=len(group),
                net_expectancy_r=float(group_net.mean()),
                profit_factor=group_pf,
                win_rate=float(group_wins.size / group_net.size),
                total_net_r=float(group_net.sum()),
            )
        )

    return BacktestMetrics(
        labeled_trades=sum(label_counts.values()),
        open_at_data_end=sum(1 for t in trades if t.exit_reason is None),
        not_executable=sum(1 for t in trades if t.label is LabelState.NOT_EXECUTABLE),
        label_counts=dict(sorted(label_counts.items())),
        net_expectancy_r=float(net_rs.mean()),
        profit_factor=profit_factor,
        win_rate=float(wins.size / net_rs.size),
        total_gross_r=float(gross_rs.sum()),
        total_net_r=float(net_rs.sum()),
        r_distribution=RDistribution(
            mean_r=float(net_rs.mean()),
            std_r=float(net_rs.std()),
            min_r=float(net_rs.min()),
            p05_r=float(np.percentile(net_rs, 5)),
            p50_r=float(np.percentile(net_rs, 50)),
            p95_r=float(np.percentile(net_rs, 95)),
            max_r=float(net_rs.max()),
        ),
        mfe_mean_r=float(np.mean([t.mfe_r for t in traded])),
        mae_mean_r=float(np.mean([t.mae_r for t in traded])),
        by_regime=tuple(by_regime),
    )
