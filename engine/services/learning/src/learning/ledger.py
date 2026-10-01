"""دفتر التجارب — كتابة سجل التجربة عند إغلاق السيناريو المُقيَّم (§29.1).

«كتابة سجل التجربة عند إغلاق أي سيناريو مُقيَّم» (build_plan 8.6): كل
سيناريو خرج بقرار مخاطرة (رُخّص أو رُفض) ثم أُغلق (نهائية §18.2) يكتب
صفه المرجعي الواحد في ``experience_ledger`` — «Immutable one-row-per-
trade or one-row-per-scenario experience reference» (§31.5): صف-لكل-
سيناريو في MVP (لا تنفيذ بعد — §24 مرحلة 11).

أساس القياس موثق داخل السجل (لا صمت): MFE/MAE بوحدات R من الدخول
المخطط (الحافة المحافظة) عبر مسار السوق بعد لحظة القرار، وP&L ورقي
من الدخول المخطط إلى إغلاق شمعة النهاية بتكاليف قرار المخاطرة نفسه
(REALISTIC). السيناريو المرفوض لم تُؤخذ له صفقة أصلاً — الحقول
التنفيذية أصفار موثقة لا أرقام مختلقة، وقيمته الإسنادية في سلسلة
الدليل التي كادت ترخّصه.
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Sequence

from schemas import (
    Candle,
    Direction,
    EvidenceRecord,
    ExperienceRecord,
    RiskDecision,
    Scenario,
    ScenarioState,
    ScenarioTransition,
    SessionType,
)

__all__ = [
    "build_experience_record",
    "experience_id_for",
    "measure_excursions",
]

#: مساحة اسم معرف التجربة — صف واحد لكل سيناريو (idempotent).
_EXPERIENCE_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/experience"
)

#: الحالات النهائية التي لا صفقة قامت أصلاً — القياس الورقي لا يختلق.
_NO_POSITION_STATES: frozenset[ScenarioState] = frozenset(
    {
        ScenarioState.REJECTED_BY_RISK,
        ScenarioState.SUPPRESSED,
        ScenarioState.EXPIRED,
        ScenarioState.CANCELLED_BY_DATA_QUALITY,
    }
)


def experience_id_for(scenario_id: str) -> str:
    """معرف التجربة الحتمي — صف-لكل-سيناريو (uuid5 فوق السيناريو)."""
    return str(uuid_module.uuid5(_EXPERIENCE_NAMESPACE, scenario_id))


def measure_excursions(
    path_candles: Sequence[Candle],
    *,
    entry_reference: float,
    stop_distance: float,
    direction: Direction,
) -> tuple[float, float]:
    """MFE/MAE بوحدات R من الدخول المخطط عبر مسار السوق (§29.2).

    «measured from the actual entry path» — في MVP (لا تنفيذ) المسار
    الفعلي المتاح مسار السوق من لحظة القرار حتى الإغلاق، والقياس من
    الدخول المخطط بأساس موثق (يُستبدل بمسار التعبئة الفعلي في §24).

    :returns: (mfe, mae) — أعلى Excursion مواتٍ وأعلاه المعاكس بوحدات
        R؛ (0, 0) عند مسار فارغ (قرار وإغلاق على الشمعة نفسها).
    """
    if stop_distance <= 0.0:
        raise ValueError(f"مسافة وقق غير موجبة: {stop_distance} — وحدة R مبنية عليها")
    if not path_candles:
        return 0.0, 0.0
    sign = 1.0 if direction is Direction.LONG else -1.0
    mfe = 0.0
    mae = 0.0
    for candle in path_candles:
        favorable = (candle.high - entry_reference) * sign
        adverse = (entry_reference - candle.low) * sign
        mfe = max(mfe, favorable / stop_distance)
        mae = max(mae, adverse / stop_distance)
    return mfe, mae


def build_experience_record(
    scenario_at_close: Scenario,
    *,
    decision: RiskDecision,
    closing_transition: ScenarioTransition,
    records: Sequence[EvidenceRecord],
    market_path: Sequence[Candle],
    session: SessionType = SessionType.UTC_DAY,
) -> ExperienceRecord:
    """بناء سجل التجربة الكامل (§29.1 — 17 حقلاً) عند الإغلاق.

    :param scenario_at_close: السيناريو بحالته النهائية.
    :param decision: قرار المخاطرة الذي قُيِّم به (مشدود نموذجيًا).
    :param closing_transition: انتقال النهاية (سببه مصدر exit_reason
        حرفيًا — التوثيق الكثيف للمرحلة 7 يُعاد استهلاكه لا يُعاد صياغته).
    :param records: سلسلة الدليل وقت القرار — لقطة الإسناد §29.3.
    :param market_path: شموع إطار التنفيذ من شمعة القرار (بعدها) حتى
        شمعة الإغلاق — مسار القياس؛ الفارغ = إغلاق فوري.
    :param session: جلسة لحظة القرار — لا تحملها لقطة الحالة.
    """
    stop = decision.stop
    if stop is None:
        raise ValueError("قرار بلا وقف محسوب — السجل يقيس بوحدات R المبنية على §23.4")
    entry_reference = stop.entry_reference
    stop_distance = stop.stop_distance
    mfe, mae = measure_excursions(
        market_path,
        entry_reference=entry_reference,
        stop_distance=stop_distance,
        direction=scenario_at_close.direction,
    )
    holding_time = max(
        0.0,
        (closing_transition.transition_time - decision.decided_at).total_seconds(),
    )

    position_taken = scenario_at_close.state not in _NO_POSITION_STATES
    gross_pnl = 0.0
    costs = 0.0
    exit_price: float | None = None
    if position_taken and decision.approved and decision.sizing is not None:
        # قياس ورقي موثق: دخول عند المرجع المخطط وخروج عند إغلاق شمعة النهاية
        exit_price = float(market_path[-1].close) if market_path else entry_reference
        sign = 1.0 if scenario_at_close.direction is Direction.LONG else -1.0
        size = decision.sizing.position_size
        gross_pnl = (exit_price - entry_reference) * sign * size
        reward = decision.reward_risk
        if reward is not None:
            per_unit_costs = reward.breakdown.gross_price_edge - reward.breakdown.net_trading_edge
            costs = per_unit_costs * size
    net_pnl = gross_pnl - costs
    net_r = (
        net_pnl / (stop_distance * decision.sizing.position_size)
        if (position_taken and decision.approved and decision.sizing is not None)
        else 0.0
    )

    execution_snapshot: dict[str, object] = {
        "basis": "scenario_level_mvp",
        "deferral": "لا تنفيذ قبل المرحلة 11 (§24) — حقول التعبئة والمسار فارغة بعمد موثق",
        "position_taken": position_taken,
        "measurement": "planned_entry_market_path",
        "entry_reference": entry_reference,
        "stop_distance": stop_distance,
        "exit_price": exit_price,
        "path_bars": len(market_path),
        "session_at_decision": session.value,
    }

    return ExperienceRecord(
        market_state_snapshot=scenario_at_close.context_snapshot,
        scenario_snapshot=scenario_at_close,
        evidence_snapshot=list(records),
        risk_snapshot=decision,
        execution_snapshot=execution_snapshot,
        fill_sequence=[],  # لا تعبئات قبل §24 — موثق في execution_snapshot
        position_path=[],  # لا مسار مركز قبل §24 — القياس من مسار السوق
        mfe=mfe,
        mae=mae,
        holding_time=holding_time,
        exit_reason=closing_transition.reason,
        gross_pnl=gross_pnl,
        costs=costs,
        net_pnl=net_pnl,
        net_r=net_r,
        regime=scenario_at_close.regime,
        session=session,
    )
