"""سجل الدليل (§19.1) — وحدة الإدخال إلى محرك دمج الدليل.

الحدود حرفية من §19.1: direction_score ∈ [-1, +1] وraw_strength/quality/
freshness/independence_discount ∈ [0, 1]. prior_weight وcontext_modifier
مضاعفان تركهما النص بلا حد (§19.2) فبقيا float منتهيًا.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ._types import FiniteFloat, SignedUnit, UnitInterval
from .enums import EventType, EvidenceGroup


class EvidenceRecord(BaseModel):
    """سجل دليل واحد — مجمّد ويمنع الحقول الغريبة (عقد §19.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    group: EvidenceGroup
    event_type: EventType
    direction_score: SignedUnit
    raw_strength: UnitInterval
    quality: UnitInterval
    freshness: UnitInterval
    independence_discount: UnitInterval
    prior_weight: FiniteFloat
    context_modifier: FiniteFloat
    opposition: bool
    source: str
    # مجموعة الارتباط (§19.4): الأحداث المنبثقة من الدفعة نفسها تُخصم
    # استقلاليتها فلا تُعد تأكيدات مستقلة (§2.3).
    correlation_group_id: str | None = None
