"""نماذج Pydantic v2 — مصدر الحقيقة الوحيد لكل الرسائل (§32) وحقول JSONB (§31).

كل التعدادات والنماذج العلنية يعاد تصديرها من هنا بواجهة واحدة؛
المُصدّر ``schemas.export`` يولّد JSON Schema الحتمي إلى generated/،
وسجل ``EVENT_PAYLOAD_MODELS`` يربط كل نوع حدث بنيوي/سيولي (§20) بحمولته
الموثقة.
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
from .envelope import EVENT_PAYLOAD_MODELS, EventEnvelope, payload_model_for
from .evidence import EvidenceRecord
from .execution import LatencyRecord, OrderIntent, SlippageRecord
from .learning import ExperienceRecord
from .liquidity import (
    BreakAcceptEventPayload,
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    SweepEventPayload,
    ZoneState,
)
from .market import Candle, FootprintBar, MarketStateSnapshot, TradeEvent
from .orderflow import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    FlowDirection,
    ImbalanceClusterEventPayload,
    ImbalanceSide,
)
from .scenario import (
    InvalidationRule,
    PriceZone,
    Scenario,
    TargetZone,
    TriggerDefinition,
)
from .structure import (
    BreakDirection,
    DisplacementEventPayload,
    FvgDirection,
    FvgEventPayload,
    FvgState,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    PremiumDiscountSide,
    StructureBreakPayload,
    StructureConsequence,
    Swing,
    SwingDirection,
    SwingScope,
)

__version__ = "0.1.0"

# إصدار المخططات — يُرفع عند أي تغيير كسر في عقود الرسائل (§32: versioned contracts)
SCHEMA_VERSION = "1.0.0"

# الواجهة العلنية الكاملة — مرتبة ترتيبًا حتميًا (RUF022): الثوابت العليا
# ثم الفئات ثم الأسماء السفلية (__version__ قبل الدوال — ترتيب بايتات
# الشرطة السفلية). كل تعدادة ونموذج علني في الحزمة موجود هنا.
__all__ = [
    "DEFAULT_EVENT_WEIGHTS",
    "DEFAULT_GROUP_SHARES",
    "EVENT_PAYLOAD_MODELS",
    "SCHEMA_VERSION",
    "AbsorbedPressure",
    "AbsorptionConditions",
    "AbsorptionEventPayload",
    "BreakAcceptEventPayload",
    "BreakDirection",
    "Candle",
    "DataQuality",
    "Direction",
    "DisplacementEventPayload",
    "EventEnvelope",
    "EventType",
    "EvidenceGroup",
    "EvidenceRecord",
    "ExhaustionEventPayload",
    "ExperienceRecord",
    "FlowContinuationEventPayload",
    "FlowDirection",
    "FootprintBar",
    "FvgDirection",
    "FvgEventPayload",
    "FvgState",
    "HTFBias",
    "HardBlockReason",
    "ImbalanceClusterEventPayload",
    "ImbalanceSide",
    "InvalidationRule",
    "LatencyRecord",
    "LiquiditySide",
    "LiquiditySourceType",
    "LiquidityZone",
    "MarketRegime",
    "MarketStateSnapshot",
    "OrderBlockEventPayload",
    "OrderIntent",
    "OrderPolicy",
    "PremiumDiscountEventPayload",
    "PremiumDiscountSide",
    "PriceZone",
    "Scenario",
    "ScenarioState",
    "SessionType",
    "SignalState",
    "SlippageRecord",
    "StructureBreakPayload",
    "StructureConsequence",
    "SweepClassification",
    "SweepEventPayload",
    "Swing",
    "SwingDirection",
    "SwingScope",
    "TargetZone",
    "TradeEvent",
    "TriggerDefinition",
    "ZoneState",
    "__version__",
    "payload_model_for",
]
