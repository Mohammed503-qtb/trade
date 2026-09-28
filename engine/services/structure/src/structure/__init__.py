"""كواشف البنية (§11): متطرفات مؤكدة بتأخير، BOS/CHoCH، وإزاحة — عبر StructureEngine.

التركيب: :class:`StructureEngine` يملك الكواشف الثلاثة لزوج (أداة، إطار)
واحد ويخرج :class:`EmittedEvent` المُصنَّفة — تجميع المغلف (§32) مسؤولية
الناشر اللاحق (3-f). كل العتبات السعرية من ``VolatilityState.threshold``
حصرًا (§16) — لا ثابت ticks/pips مطلق في الحزمة.
"""

from __future__ import annotations

from structure.bos import BosConfig, StructureBreakEngine
from structure.displacement import DisplacementConfig, DisplacementDetector
from structure.engine import StructureConfig, StructureEngine
from structure.events import EmittedEvent
from structure.swings import SwingConfig, SwingDetector

__version__ = "0.1.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022)
__all__ = [
    "BosConfig",
    "DisplacementConfig",
    "DisplacementDetector",
    "EmittedEvent",
    "StructureBreakEngine",
    "StructureConfig",
    "StructureEngine",
    "SwingConfig",
    "SwingDetector",
    "__version__",
]
