"""خريطة السيولة والاجتياح والأهداف (§10) — كاشف مستقل فوق طبقة السياق.

الواجهة الموحدة: :class:`~liquidity.engine.LiquidityEngine` لكل (أداة، إطار)
تملك :class:`~liquidity.zones.LiquidityMapEngine` (المصادر ودورة الحياة
والدرجات §10.1-3) و:class:`~liquidity.sweep.SweepDetector` (التسلسل الخمسي
الشروط بتصنيفه الخمسي §10.4) و:class:`~liquidity.targets.TargetMapBuilder`
(الأهداف مناطق لا نقاط على الجانبين §10.5). المتطرفات تصل كقيم
``schemas.Swing`` من المستدعي — لا استيراد لكاشف آخر (عقد الاستقلال).
"""

from liquidity.engine import LiquidityConfig, LiquidityEngine
from liquidity.sweep import EmittedEvent, SweepConfig, SweepDetector
from liquidity.targets import TargetEntry, TargetMap, TargetMapBuilder
from liquidity.zones import ImportanceWeights, LiquidityMapEngine, ZoneBand, ZoneConfig

__version__ = "0.1.0"

__all__ = [
    "EmittedEvent",
    "ImportanceWeights",
    "LiquidityConfig",
    "LiquidityEngine",
    "LiquidityMapEngine",
    "SweepConfig",
    "SweepDetector",
    "TargetEntry",
    "TargetMap",
    "TargetMapBuilder",
    "ZoneBand",
    "ZoneConfig",
    "__version__",
]
