"""سجل التجربة (§29.1) — وحدة إسناد التعلم في دفتر التجارب غير القابل للعبث.

«التعلم محكوم لا مفسدٌ ذاته» (§2.7): السجل مرجع جامد صفيّ لكل تجارة،
والتحسين يمر عبر إعادة تقدير بلا اتصال وبوابات ترقية — لا إعادة كتابة
ذاتية من تجربة واحدة.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ._types import FiniteFloat, NonNegativeFloat
from .enums import MarketRegime, SessionType
from .evidence import EvidenceRecord
from .market import MarketStateSnapshot
from .scenario import Scenario


class ExperienceRecord(BaseModel):
    """سجل تجربة واحدة بعد إغلاق الصفقة (§29.1 حرفيًا — 17 حقلًا).

    اللقطات الأربع الأولى تلتقط الحالة وقت القرار: حالة السوق والسيناريو
    والدليل مكتوبة النموذج؛ أما risk_snapshot وexecution_snapshot و
    fill_sequence وposition_path فحقول JSONB تُشدَّد نماذجها في مرحلتي
    المخاطرة والتنفيذ (§23/§24) — عمدًا لا فجوة.
    mfe/mae بمضاعفات R من مسار الدخول الفعلي (§23.1، §29.2).
    holding_time بالثواني.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    market_state_snapshot: MarketStateSnapshot
    scenario_snapshot: Scenario
    evidence_snapshot: list[EvidenceRecord]
    risk_snapshot: dict[str, Any]
    execution_snapshot: dict[str, Any]
    fill_sequence: list[dict[str, Any]]
    position_path: list[dict[str, Any]]

    mfe: FiniteFloat
    mae: FiniteFloat
    holding_time: NonNegativeFloat
    exit_reason: str
    gross_pnl: FiniteFloat
    costs: NonNegativeFloat
    net_pnl: FiniteFloat
    net_r: FiniteFloat
    regime: MarketRegime
    session: SessionType
