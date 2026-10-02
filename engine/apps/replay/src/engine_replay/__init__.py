"""مشغل الإعادة/الاختبارات CLI (§26)."""

from .ablation import (
    AblationReport,
    AblationResult,
    AblationSpec,
    AblationVariant,
    Dataset,
    FeatureSet,
    MetricEvaluator,
    VariantKind,
    placeholder_evaluator,
    run_ablation,
)
from .ablation_evaluator import (
    FEATURE_POLARITY,
    AblationEvaluatorConfig,
    DirectionalEvaluator,
    evaluate_directional,
)
from .backtest import run_backtest, sort_specs

__all__ = [
    "FEATURE_POLARITY",
    "AblationEvaluatorConfig",
    "AblationReport",
    "AblationResult",
    "AblationSpec",
    "AblationVariant",
    "Dataset",
    "DirectionalEvaluator",
    "FeatureSet",
    "MetricEvaluator",
    "VariantKind",
    "__version__",
    "evaluate_directional",
    "placeholder_evaluator",
    "run_ablation",
    "run_backtest",
    "sort_specs",
]

__version__ = "0.1.0"
