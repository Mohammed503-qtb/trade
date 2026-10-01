"""لا-تداول (§22)، R، تحجيم، قيود (§23) — وحدة المخاطرة والقرار.

التصدير الموحد: كل ما تحتاجه طبقات ما فوق (الإعادة/العامل/اللوحة)
من قرار المخاطرة عبر واجهة واحدة — البوابة الخروج 8: «كل خرق مخاطرة
= رفض صلب موثق بكود».
"""

from __future__ import annotations

from .costs import estimate_reward_risk, round_trip_cost
from .engine import (
    RiskEngine,
    RiskEvaluation,
    decision_id_for,
    trade_intent_id_for,
)
from .no_trade import (
    evaluate_hard_blocks,
    evaluate_soft_suppressions,
    location_quality,
    soft_weight_total,
)
from .parameter_sets import SCENARIO_QUALITY_DEFERRAL, RiskConfig, default_risk_config
from .sizing import compute_sizing, risk_budget_for
from .stop import compute_structural_stop
from .store import RiskStore, RiskStoreError

__all__ = [
    "SCENARIO_QUALITY_DEFERRAL",
    "RiskConfig",
    "RiskEngine",
    "RiskEvaluation",
    "RiskStore",
    "RiskStoreError",
    "compute_sizing",
    "compute_structural_stop",
    "decision_id_for",
    "default_risk_config",
    "estimate_reward_risk",
    "evaluate_hard_blocks",
    "evaluate_soft_suppressions",
    "location_quality",
    "risk_budget_for",
    "round_trip_cost",
    "soft_weight_total",
    "trade_intent_id_for",
]

__version__ = "0.1.0"
