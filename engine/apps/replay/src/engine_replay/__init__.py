"""مشغل الإعادة/الاختبارات CLI (§26)"""

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

__all__ = [
    "AblationReport",
    "AblationResult",
    "AblationSpec",
    "AblationVariant",
    "Dataset",
    "FeatureSet",
    "MetricEvaluator",
    "VariantKind",
    "__version__",
    "placeholder_evaluator",
    "run_ablation",
]

__version__ = "0.1.0"
