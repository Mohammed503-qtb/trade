"""السيناريو ومكوناته — مركز نموذج الاستدلال (§18) وأهداف السيولة (§10.5).

المصدر: §18.1 (كائن السيناريو)، §18.5+§23.4 (قاعدة الإبطال)، §10.5 (الأهداف)،
§19.6 (الاحتمال المعاير). الدرجة الخام scenario_score ليست احتمالًا (§2.6).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ._types import NonNegativeFloat, Price, UnitInterval, UTCDatetime
from .enums import Direction, MarketRegime, ScenarioState
from .market import MarketStateSnapshot


class _ScenarioModel(BaseModel):
    """أساس موحد لمكونات السيناريو: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PriceZone(_ScenarioModel):
    """نطاق سعري [price_low, price_high] — تمثيل مناطق الدخول."""

    price_low: Price
    price_high: Price


class TriggerDefinition(_ScenarioModel):
    """مشغل قابل للرصد — وصف هيكلي (condition_type + params) يفحصه المحرك.

    مثال: condition_type="ZONE_RECLAIM"، params={"zone_id": ..., "timeframe": "1m"}.
    السيناريو لا يصبح TRIGGERED إلا برصد هذا المشغل فعليًا (§18.4).
    """

    condition_type: str
    params: dict[str, Any]


class InvalidationRule(_ScenarioModel):
    """قاعدة الإبطال (§18.5 و§23.4): مستوى بنية + عازلة تقلب + شرط القبول.

    accept_through=True يعني أن الإبطال يتطلب قبولًا عبر المستوى (إغلاقًا)
    لا مجرد اختراق بفتيل؛ العازلة من بنية التقلب لا من رقم نقاط كوني (§23.4).
    """

    structural_level: Price
    volatility_buffer: NonNegativeFloat
    accept_through: bool


class TargetZone(_ScenarioModel):
    """هدف مرتبط بمنطقة سيولة (§10.5): مستوى سعر + مرجع المنطقة."""

    price_level: Price
    zone_id: str


class Scenario(_ScenarioModel):
    """السيناريو (§18.1 حرفيًا) — تفسير منافس لحالة السوق لا اتجاهًا مفروضًا.

    scenario_score درجة دليل خام بنطاق [0, 1] وليست احتمالًا (§2.6)؛
    calibrated_probability لا تظهر إلا بعد معاير صريح على بيانات خارج
    العينة (§19.6) وتتبَّع بالنظام.
    """

    scenario_id: str
    symbol: str
    direction: Direction
    regime: MarketRegime

    # لقطتا لحظة الإنشاء: الحالة الكلية مكتوبة النموذج، والموقع (خريطة
    # السيولة ذات الصلة) JSONB يُشدَّد نموذجه في مرحلة السيولة.
    context_snapshot: MarketStateSnapshot
    location_snapshot: dict[str, Any]

    thesis: str
    supporting_evidence: list[str]
    opposing_evidence: list[str]

    trigger_definition: TriggerDefinition
    entry_zone: PriceZone
    invalidation: InvalidationRule
    primary_targets: list[TargetZone]
    secondary_targets: list[TargetZone]
    expiry_time: UTCDatetime
    state: ScenarioState

    scenario_score: UnitInterval
    calibrated_probability: UnitInterval | None = None
