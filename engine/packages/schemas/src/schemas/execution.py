"""عقود التنفيذ — نية الأمر (§24.1)، الانزلاق (§24.4)، الكمون (§24.5).

التنفيذ منفصل عن الاستدلال: هذه الكائنات هي الحدود بين طبقة القرار
ومحرك التنفيذ (§24).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ._types import NonNegativeFloat, PositiveFloat, Price, UTCDatetime
from .enums import Direction, OrderPolicy
from .scenario import PriceZone, TargetZone


class _ExecutionModel(BaseModel):
    """أساس موحد لعقود التنفيذ: مجمّدة وتمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class OrderIntent(_ExecutionModel):
    """نية أمر (§24.1 حرفيًا) — مواصفة تنفيذ معتمدة لا تحليلًا فنيًا.

    max_slippage بوحدات السعر، max_latency بالمللي ثانية، risk_budget
    هو المخاطرة النقدية المسموحة للنية (أساس §23.2).
    """

    trade_intent_id: str
    scenario_id: str
    symbol: str
    side: Direction
    entry_policy: OrderPolicy
    entry_zone: PriceZone
    stop: Price
    targets: list[TargetZone]
    max_slippage: NonNegativeFloat
    max_latency: NonNegativeFloat
    expiry: UTCDatetime
    # المخاطرة النقدية المسموحة للنية — موجبة صراحة (أساس التحجيم §23.2)
    risk_budget: PositiveFloat
    client_order_id: str


class SlippageRecord(_ExecutionModel):
    """سجل الانزلاق (§24.4) — الفعلي يخزن منفصلًا عن النموذجي.

    entry_slippage = actual_average_entry - modeled_entry (سالب = ملائم).
    """

    modeled_entry: Price
    actual_average_entry: Price
    modeled_exit: Price
    actual_average_exit: Price
    entry_slippage: float
    exit_slippage: float


class LatencyRecord(_ExecutionModel):
    """سجل الكمون (§24.5) — الطوابع الست من الإشارة حتى التنفيذ.

    يتيح لمحرك التعلم قياس الفرق بين الأفضلية التحليلية والقابلة للتنفيذ.
    """

    signal_time: UTCDatetime
    webhook_receive_time: UTCDatetime
    engine_decision_time: UTCDatetime
    broker_send_time: UTCDatetime
    exchange_ack_time: UTCDatetime
    fill_time: UTCDatetime
