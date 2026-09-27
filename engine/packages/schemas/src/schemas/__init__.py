"""نماذج Pydantic v2 — مصدر الحقيقة الوحيد لكل الرسائل (§32) وحقول JSONB (§31).

كل التعدادات والنماذج العلنية يعاد تصديرها من هنا بواجهة واحدة؛
المُصدّر ``schemas.export`` يولّد JSON Schema الحتمي إلى generated/.
"""

from __future__ import annotations

from .enums import (
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_GROUP_SHARES,
    DataQuality,
    Direction,
    EventType,
    EvidenceGroup,
    HardBlockReason,
    HTFBias,
    MarketRegime,
    OrderPolicy,
    ScenarioState,
    SessionType,
    SignalState,
    SweepClassification,
)
from .envelope import EventEnvelope
from .evidence import EvidenceRecord
from .execution import LatencyRecord, OrderIntent, SlippageRecord
from .learning import ExperienceRecord
from .market import Candle, FootprintBar, MarketStateSnapshot, TradeEvent
from .scenario import (
    InvalidationRule,
    PriceZone,
    Scenario,
    TargetZone,
    TriggerDefinition,
)

__version__ = "0.1.0"

# إصدار المخططات — يُرفع عند أي تغيير كسر في عقود الرسائل (§32: versioned contracts)
SCHEMA_VERSION = "1.0.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022): الثوابت ثم
# الفئات ثم __version__. كل تعدادة ونموذج علني في الحزمة موجود هنا.
__all__ = [
    "DEFAULT_EVENT_WEIGHTS",
    "DEFAULT_GROUP_SHARES",
    "SCHEMA_VERSION",
    "Candle",
    "DataQuality",
    "Direction",
    "EventEnvelope",
    "EventType",
    "EvidenceGroup",
    "EvidenceRecord",
    "ExperienceRecord",
    "FootprintBar",
    "HTFBias",
    "HardBlockReason",
    "InvalidationRule",
    "LatencyRecord",
    "MarketRegime",
    "MarketStateSnapshot",
    "OrderIntent",
    "OrderPolicy",
    "PriceZone",
    "Scenario",
    "ScenarioState",
    "SessionType",
    "SignalState",
    "SlippageRecord",
    "SweepClassification",
    "TargetZone",
    "TradeEvent",
    "TriggerDefinition",
    "__version__",
]
