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
from .risk import RiskDecision
from .scenario import Scenario


class ExperienceRecord(BaseModel):
    """سجل تجربة واحدة بعد إغلاق الصفقة (§29.1 حرفيًا — 17 حقلًا).

    اللقطات الأربع الأولى تلتقط الحالة وقت القرار: حالة السوق والسيناريو
    والدليل مكتوبة النموذج؛ ``risk_snapshot`` شُدّد إلى ``RiskDecision``
    في المرحلة 8 (الوعد الموثق أعلاه — لا فجوة)، فيما تبقى
    ``execution_snapshot`` و``fill_sequence`` و``position_path`` حقول
    JSONB حتى مرحلة التنفيذ (§24 — المرحلة 11) عمدًا موثقًا.
    ``mfe/mae`` بمضاعفات R من مسار الدخول الفعلي (§23.1، §29.2)؛ في سجلات
    السيناريو (MVP — صف-لكل-سيناريو §31.5) تُقاس من الدخول المخطط عبر
    مسار السوق بعد الاشتعال بأساس موثق داخل ``execution_snapshot``.
    ``holding_time`` بالثواني.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    market_state_snapshot: MarketStateSnapshot
    scenario_snapshot: Scenario
    evidence_snapshot: list[EvidenceRecord]
    #: قرار المخاطرة وقت الترخيص — مشدود نموذجيًا (المرحلة 8).
    risk_snapshot: RiskDecision
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
