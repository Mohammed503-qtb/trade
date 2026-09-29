"""مغلف الأحداث الموحد (§32) — عقد كل رسالة داخلية على الناقل.

كل الرسائل الداخلية تستخدم عقودًا مُدارة إصداريًا؛ «عقد الإنتاج الفعلي يجب
أن يولَّد/يُتحقق منه من مخططات مطبوعة لا سلاسل يدوية» (§32).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ._types import UTCDatetime
from .enums import EventType
from .liquidity import BreakAcceptEventPayload, SweepEventPayload
from .orderflow import (
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    ImbalanceClusterEventPayload,
)
from .patterns import (
    CandlePatternEventPayload,
    ClassicalPatternEventPayload,
)
from .structure import (
    DisplacementEventPayload,
    FvgEventPayload,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    StructureBreakPayload,
)


class EventEnvelope(BaseModel):
    """المغلف القياسي ذو الحقول التسعة (§32 حرفيًا).

    مجمّد ويمنع الحقول الغريبة: الرسالة عقد غير قابل للعبث بعد البثّ.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    schema_version: str
    event_type: EventType
    event_time: UTCDatetime
    receive_time: UTCDatetime
    source: str
    trace_id: str
    correlation_id: str | None
    payload: dict[str, Any]


#: سجل حمولات الأحداث (§20+§32): نوع الحدث → نموذج الحمولة الموثق
#: الذي يملأ ``payload`` داخل EventEnvelope ويُتحقق ضد مخططه المُصدَّر.
#:
#: **المرحلة 3 تغطي الأحداث البنيوية/السيولية الخمسة عشر والمرحلة 4
#: تضيف أحداث التدفق الثمانية والمرحلة 5a تضيف أحداث الأنماط الستة**؛
#: الطور اللاحق يوسع الخريطة (sessions/...) — أي نوع خارج الخريطة بلا
#: حمولة موثقة بعد، و``payload_model_for`` تعيد له None: غياب الحمولة
#: إعلان صريح لا صمت موافقة.
EVENT_PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    # كسور البنية (§11.2-3)
    EventType.INTERNAL_BOS: StructureBreakPayload,
    EventType.EXTERNAL_BOS: StructureBreakPayload,
    EventType.CHOCH: StructureBreakPayload,
    # الإزاحة (§11.4)
    EventType.DISPLACEMENT_UP: DisplacementEventPayload,
    EventType.DISPLACEMENT_DOWN: DisplacementEventPayload,
    # السيولة: الاجتياح والقبول (§10.4)
    EventType.LIQUIDITY_SWEEP_HIGH: SweepEventPayload,
    EventType.LIQUIDITY_SWEEP_LOW: SweepEventPayload,
    EventType.BREAK_AND_ACCEPT_HIGH: BreakAcceptEventPayload,
    EventType.BREAK_AND_ACCEPT_LOW: BreakAcceptEventPayload,
    # البنية المشتقة: FVG وOB والموقع (§11.5-7)
    EventType.FVG_BULLISH: FvgEventPayload,
    EventType.FVG_BEARISH: FvgEventPayload,
    EventType.ORDER_BLOCK_BULLISH: OrderBlockEventPayload,
    EventType.ORDER_BLOCK_BEARISH: OrderBlockEventPayload,
    EventType.PREMIUM_LOCATION: PremiumDiscountEventPayload,
    EventType.DISCOUNT_LOCATION: PremiumDiscountEventPayload,
    # التدفق: الامتصاص والاستمرار والإنهاك وعناقيد الاختلال (§12)
    EventType.ABSORPTION_BUY: AbsorptionEventPayload,
    EventType.ABSORPTION_SELL: AbsorptionEventPayload,
    EventType.FLOW_CONTINUATION_UP: FlowContinuationEventPayload,
    EventType.FLOW_CONTINUATION_DOWN: FlowContinuationEventPayload,
    EventType.EXHAUSTION_UP: ExhaustionEventPayload,
    EventType.EXHAUSTION_DOWN: ExhaustionEventPayload,
    EventType.BUY_IMBALANCE_CLUSTER: ImbalanceClusterEventPayload,
    EventType.SELL_IMBALANCE_CLUSTER: ImbalanceClusterEventPayload,
    # الأنماط: الشموعي والكلاسيكي (§13)
    EventType.BULLISH_ENGULFING: CandlePatternEventPayload,
    EventType.BEARISH_ENGULFING: CandlePatternEventPayload,
    EventType.REJECTION_CANDLE: CandlePatternEventPayload,
    EventType.INSIDE_BAR_BREAK: CandlePatternEventPayload,
    EventType.CLASSICAL_BREAKOUT: ClassicalPatternEventPayload,
    EventType.CLASSICAL_FAILED_BREAKOUT: ClassicalPatternEventPayload,
}


def payload_model_for(event_type: EventType) -> type[BaseModel] | None:
    """نموذج الحمولة الموثق لنوع الحدث — None إذا لم يوثَّق بعد.

    حرس الحمولات: من يبني EventEnvelope لنوع من الخريطة يستدعي النموذج
    من هنا لا يخترع dictًا يدويًا؛ وNone تعني «لا تبنَ حمولة لهذا النوع
    بعد» — لا «أي dict يمر».
    """
    return EVENT_PAYLOAD_MODELS.get(event_type)
