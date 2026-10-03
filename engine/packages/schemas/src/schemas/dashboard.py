"""عقود اللوحة الدنيا — لوحة المعلومات (§35.2) وأثر الاستدلال (§35.3).

هذه عقود العبور بين composition في apps/api وواجهة Next: كل ما تراه
اللوحة يمر من هنا (لا سلاسل يدوية) — والمخرجات حتمية قابلة للمطابقة
مع أرقام البوابات الموثقة.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ._types import NonNegativeInt, UnitInterval, UTCDatetime


class _DashboardModel(BaseModel):
    """أساس موحد لعقود اللوحة: مجمّدة وتمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PanelField(_DashboardModel):
    """حقل واحد من لوحة المعلومات الدنيا (§35.2).

    ``key`` معرف الحقل الثابت (يستقرئه الفحص الآلي — ثلاثة عشر حقلًا)،
    و``value``/``detail`` عرض اللوحة (قد يتغير نصه دون كسر العقد).
    """

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    detail: str | None = None


class ReasoningTraceView(_DashboardModel):
    """أثر الاستدلال القابل للطي لسيناريو واحد (§35.3 حرفيًا).

    «لماذا نشط؟» و«ماذا ضده؟» و«لماذا الانتظار؟» — ثلاث قوائم نصية
    صريحة من سجل الدليل المدمج؛ أثمن من ملصق نسبة شرائية (§35.3).
    """

    scenario_id: str = Field(min_length=1)
    template: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    why_active: tuple[str, ...] = ()
    what_against: tuple[str, ...] = ()
    why_wait: tuple[str, ...] = ()


class ScenarioView(_DashboardModel):
    """عرض سيناريو نشط في اللوحة (الطبقة 4-5 من §35.1)."""

    scenario_id: str = Field(min_length=1)
    template: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    state: str = Field(min_length=1)
    created_time: UTCDatetime
    trigger_status: str = Field(min_length=1)
    entry_price_low: float
    entry_price_high: float
    stop: float
    target_price: float
    evidence_count: NonNegativeInt
    score: UnitInterval


class RejectionView(_DashboardModel):
    """سجل رفض واحد (لا-تداول §22 أو كتم §22.2 أو رفض webhook)."""

    decision_id: str = Field(min_length=1)
    scenario_id: str | None = None
    reason_code: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    as_of: UTCDatetime


class ExecutionView(_DashboardModel):
    """حالة التنفيذ في اللوحة — وضع MVP معلن بلا لبس.

    ``mode = "SIMULATION_ONLY"``: القبول القانوني في محرك الإعادة
    الخارجي (§28) والتنفيذ الحي مؤجل للمرحلة 11 (خارطة ما بعد MVP) —
    اللوحة تعلن ذلك ولا تدّعي تداولًا حيًا أبدًا.
    """

    mode: str = Field(min_length=1)
    trades_count: NonNegativeInt
    net_expectancy_r: float
    profit_factor: float | None
    win_rate: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    report_ref: str = Field(min_length=1)


class WebhookEventView(_DashboardModel):
    """تنبيه TradingView حديث كما تعرضه اللوحة (سجل التسليم §31.6)."""

    alert_key: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    event: str = Field(min_length=1)
    status: str = Field(min_length=1)
    received_at: UTCDatetime


class DashboardCounts(_DashboardModel):
    """خلاصة مطابقة اللوحة مع أرقام البوابات الموثقة (فحص البوابة)."""

    risk_decisions: NonNegativeInt
    authorized: NonNegativeInt
    rejected: NonNegativeInt
    simulated_trades: NonNegativeInt
    active_scenarios: NonNegativeInt


class DashboardOverview(_DashboardModel):
    """اللقطة الكاملة للوحة الدنيا — عقود §35.2 + §35.3 معًا.

    ``panel`` ثلاثة عشر حقلًا حرفيًا (§35.2)، و``counts`` خلاصة التحقق
    الآلي (تطابق أرقام البوابات: 103 قرارات/58 ترخيصًا/45 رفضًا/58
    صفقة محاكاة)، و``composition_ref`` هوية التوليف الحتمي الذي بُنيت
    منه اللقطة.
    """

    panel: tuple[PanelField, ...]
    traces: tuple[ReasoningTraceView, ...]
    scenarios: tuple[ScenarioView, ...]
    rejections: tuple[RejectionView, ...]
    execution: ExecutionView
    alerts: tuple[WebhookEventView, ...]
    counts: DashboardCounts
    composition_ref: str = Field(min_length=1)
