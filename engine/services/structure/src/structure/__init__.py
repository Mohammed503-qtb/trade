"""كواشف البنية (§11): متطرفات مؤكدة بتأخير، BOS/CHoCH، إزاحة، فجوات
قيمة عادلة، كتل أوامر، وموقع premium/discount — عبر StructureEngine.

التركيب: :class:`StructureEngine` يملك الكواشف الستة لزوج (أداة، إطار)
واحد ويخرج :class:`EmittedEvent` المُصنَّفة — تجميع المغلف (§32) مسؤولية
الناشر اللاحق (3-f). كل العتبات السعرية من ``VolatilityState.threshold``
حصرًا (§16) — لا ثابت ticks/pips مطلق في الحزمة.
"""

from __future__ import annotations

from structure.bos import BosConfig, StructureBreakEngine
from structure.displacement import DisplacementConfig, DisplacementDetector
from structure.engine import StructureConfig, StructureEngine
from structure.events import EmittedEvent
from structure.fvg import FvgConfig, FvgLifecycle, FvgSnapshot, FvgTracker
from structure.order_blocks import (
    OrderBlockConfig,
    OrderBlockQualityWeights,
    OrderBlockSnapshot,
    OrderBlockTracker,
    displacement_event_id,
)
from structure.premium_discount import (
    RANGE_NAME,
    PremiumDiscountConfig,
    PremiumDiscountEngine,
    PremiumDiscountLocation,
    PremiumDiscountSnapshot,
)
from structure.swings import SwingConfig, SwingDetector

__version__ = "0.1.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022)
__all__ = [
    "RANGE_NAME",
    "BosConfig",
    "DisplacementConfig",
    "DisplacementDetector",
    "EmittedEvent",
    "FvgConfig",
    "FvgLifecycle",
    "FvgSnapshot",
    "FvgTracker",
    "OrderBlockConfig",
    "OrderBlockQualityWeights",
    "OrderBlockSnapshot",
    "OrderBlockTracker",
    "PremiumDiscountConfig",
    "PremiumDiscountEngine",
    "PremiumDiscountLocation",
    "PremiumDiscountSnapshot",
    "StructureBreakEngine",
    "StructureConfig",
    "StructureEngine",
    "SwingConfig",
    "SwingDetector",
    "__version__",
    "displacement_event_id",
]
