"""المنفّذ المحاكي (§26.1) — تعبئة حتمية بلا-نظرة بترتيب متحفظ داخل الشمعة.

«Costs included. Latency simulated. Partial fills modeled.» — المنفّذ يبني
العالم المحاكى لنية أمر واحدة فوق مسار شموع إطار التنفيذ، بقواعد
حتمية معلنة لا عشوائية (البذرة تُسجل لهوية الاستنساخ §26.2 وتبقى غير
مستهلكة ما دام كل مكون حتميًا — موثق).

**زمن الحدث (§26.1)**: كل تعبئة/مخرج يؤرَّخ عند **إغلاق** شمعة الحدث
(``bar_time + الإطار``) — اللمس لا يُعلم إلا بإغلاق الشمعة (لا-نظرة
داخل الشمعة)، والكمون يُسجل حقلًا للفحص §24.5.

**الترتيب المتحفظ داخل الشمعة (§30 حرفيًا)** — «it must never choose
the favorable outcome merely because it makes the backtest prettier»:

1. الدخول أولًا: لمس المنطقة يعبئ عند الحافة المعاكسة (أسوأ تعبئة
   قانونية) بنسبة إعدادية لكل شمعة (تعبئة جزئية §26.1).
2. ثم **الوقف قبل الهدف** للمركز القائم: شمعة لمست كليهما ⇒ الوقف
   (أسوأ حالة — ``ambiguity_resolved_conservatively``).
3. شمعة لمست منطقة الدخول والوقف معًا ⇒ تعبئةٌ ثم وقفٌ (أسوأ حالة).
4. شمعة لمست منطقة الدخول والهدف دون الوقف ⇒ تعبئةٌ ثم هدفٌ — الترتيب
   السببي الوحيد (لا مركز قبل الدخول) ولا غموض يُحتاج تحفظه.

**شريط المهلة العابر** (يبدأ قبل انقضاء النية ويغلق بعده): الدخول لا
يعبأ عليه (لحظة اللمس لا تُعلم — تحفظًا)؛ والمركز القائم يُفحص وقفه
(اللمس قد سبق المهلة — فرضية الضرر) فإن لم يُلمس خرج عند **إغلاق آخر
شمعة مؤكدة ≤ المهلة** (آخر سعر معلوم عند الانقضاء) — لا يُدّعى هدفٌ
وقع بعد المهلة أبدًا.

**حدود موثقة (MVP — ADR-027)**: هدف أول وحيد (التدرج §24.6 بعد MVP)؛
التعبئة عند مستويات نظيفة والتكاليف تحللًا محققًا واحدًا في
:mod:`backtest.costs` (لا ازدواج حساب)؛ حارس الانزلاق الأقصى سلوك
المحرك الحي (§24) لا المحاكي؛ إطار التنفيذ 1m حصرًا.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from schemas import (
    Candle,
    Direction,
    EntrySpec,
    ExitReason,
    SimulatedFill,
    SimulatedTrade,
)

from .costs import realize_costs
from .labeling import label_for
from .parameter_sets import BacktestConfig

__all__ = ["ExecutionPlan", "SimulatedExecutor"]

#: إطار التنفيذ المدعوم في MVP — إطار العينة القانونية.
_EXECUTION_TIMEFRAME_S: dict[str, float] = {"1m": 60.0}

#: هامش ضبط الجمع العائم — أقل من أي كمية معنية عمليًا.
_QTY_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """خطة التنفيذ الداخلية المستقيمة من المواصفة — مسافات وحدود موحدة."""

    spec: EntrySpec
    #: مسافة وحدة R (|الدخول − الوقف|) — موجبة ببنية EntrySpec.
    stop_distance: float
    zone_top: float
    zone_bottom: float
    #: الحافة المعاكسة (أسوأ تعبئة قانونية) — جهة-محيّدة.
    fill_price: float

    @classmethod
    def from_spec(cls, spec: EntrySpec) -> ExecutionPlan:
        stop_distance = abs(spec.entry_price - spec.stop_price)
        if stop_distance <= 0.0:
            raise ValueError(
                f"مسافة وقف معدومة للمواصفة {spec.trade_intent_id} — وحدة R مبنية عليها"
            )
        return cls(
            spec=spec,
            stop_distance=stop_distance,
            zone_top=max(spec.entry_price, spec.zone_opposite_price),
            zone_bottom=min(spec.entry_price, spec.zone_opposite_price),
            fill_price=spec.entry_price,
        )


def _bar_seconds(bar: Candle) -> float:
    """عرض الشمعة بالثواني — 1m حصرًا في MVP (إطار التنفيذ)."""
    seconds = _EXECUTION_TIMEFRAME_S.get(bar.timeframe)
    if seconds is None:
        raise ValueError(
            f"إطار غير مدعوم في المحاكي: {bar.timeframe!r} — 1m حصرًا في MVP (إطار التنفيذ §26.1)"
        )
    return seconds


def _close_time(bar: Candle) -> datetime:
    """لحظة إغلاق الشمعة — زمن الحدث القانوني للمحاكي."""
    return bar.bar_time + timedelta(seconds=_bar_seconds(bar))


def _zone_touched(bar: Candle, plan: ExecutionPlan) -> bool:
    """تقاطع مدى الشمعة مع منطقة الدخول."""
    return bar.low <= plan.zone_top and bar.high >= plan.zone_bottom


class SimulatedExecutor:
    """منفّذ نوايا محاكٍ — حتمي تمامًا (لا حالة بين الاستدعاءات)."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def execute(self, spec: EntrySpec, path: Sequence[Candle]) -> SimulatedTrade:
        """تنفيذ نية واحدة فوق مسار الشموع — القرار لا يرى إلا أمامه.

        ``path`` شموع إطار التنفيذ (المسار الكامل مسموح؛ المنفّذ يستهلك
        ما بعد شمعة القرار حصرًا: ``bar_time > decision_time``).
        """
        plan = ExecutionPlan.from_spec(spec)
        long = spec.side is Direction.LONG
        latency = self.config.latency_ms
        per_bar = spec.planned_quantity * self.config.fill_fraction_per_bar

        entry_fills: list[SimulatedFill] = []
        remaining = spec.planned_quantity
        ambiguity = False
        exit_fill: SimulatedFill | None = None
        exit_reason: ExitReason | None = None
        mfe = 0.0
        mae = 0.0
        first_fill_at: int | None = None

        forward = [c for c in path if c.bar_time > spec.decision_time]

        for position_index, bar in enumerate(forward):
            close_time = _close_time(bar)
            in_window = close_time <= spec.expiry

            # (1) الدخول — على شموع النافذة المؤكدة حصرًا
            if remaining > _QTY_EPS and in_window and _zone_touched(bar, plan):
                quantity = min(remaining, per_bar)
                entry_fills.append(
                    SimulatedFill(
                        fill_time=close_time,
                        price=plan.fill_price,
                        quantity=quantity,
                        latency_ms=latency,
                    )
                )
                remaining -= quantity
                if first_fill_at is None:
                    first_fill_at = position_index

            filled = sum(f.quantity for f in entry_fills)
            if filled <= _QTY_EPS:
                if not in_window:
                    # نافذة الدخول انقضت بلا أي تعبئة — لم تقم صفقة أصلاً
                    exit_reason = ExitReason.UNFILLED
                    break
                continue  # لا مركز بعد — الشمعة داخل النافذة، تُستأنف لاحقًا

            # غلاف المسار: شمعة الدخول الأولى وشريط المهلة العابر —
            # المعاكس يُحتسب (قد يلي الحدث) والمواتي لا يُحتسب (قد يسبقه).
            ambiguous_bar = position_index == first_fill_at or not in_window
            favorable = (bar.high - plan.fill_price) if long else (plan.fill_price - bar.low)
            adverse = (plan.fill_price - bar.low) if long else (bar.high - plan.fill_price)
            mae = max(mae, max(0.0, adverse) / plan.stop_distance)
            if not ambiguous_bar:
                mfe = max(mfe, max(0.0, favorable) / plan.stop_distance)

            # (2) الوقف قبل الهدف — تحفظًا §30
            stop_touched = bar.low <= spec.stop_price if long else bar.high >= spec.stop_price
            target_touched = bar.high >= spec.target_price if long else bar.low <= spec.target_price
            if in_window:
                if stop_touched:
                    if target_touched:
                        ambiguity = True  # لمسهما معًا ⇒ الوقف (أسوأ حالة)
                    exit_fill = _fill(spec.stop_price, filled, close_time, latency)
                    exit_reason = ExitReason.STOP
                    break
                if target_touched:
                    exit_fill = _fill(spec.target_price, filled, close_time, latency)
                    exit_reason = ExitReason.TARGET
                    break
                continue  # النية حية والشريط مؤكد — التالي

            # (4) شريط المهلة العابر: الوقف فرضية الضرر، والهدف لا يُدّعى
            if stop_touched:
                exit_fill = _fill(spec.stop_price, filled, close_time, latency)
                exit_reason = ExitReason.STOP
                break
            # الخروج عند آخر سعر معلوم عند الانقضاء: إغلاق آخر شمعة مؤكدة
            certain_index = position_index - 1
            if certain_index >= 0:
                certain_bar = forward[certain_index]
                exit_price = certain_bar.close
                exit_time: datetime = _close_time(certain_bar)
            else:
                exit_price = bar.open  # لا شمعة مؤكدة سابقة — أول سعر معلوم
                exit_time = close_time
            exit_fill = _fill(exit_price, filled, exit_time, latency)
            exit_reason = ExitReason.ENTRY_EXPIRY if remaining > _QTY_EPS else ExitReason.TIMEOUT
            break

        filled_total = sum(f.quantity for f in entry_fills)
        if filled_total <= _QTY_EPS:
            exit_fill = None  # لا مخرج بلا كمية — النافذة لم تعبأ شيئًا
            if exit_reason is not ExitReason.UNFILLED:
                exit_reason = None  # البيانات انتهت والنافذة لم تُحسم بعد

        costs = (
            realize_costs(
                side=spec.side,
                entry_price=plan.fill_price,
                exit_price=(exit_fill.price if exit_fill is not None else None),
                config=self.config,
                holding_s=(
                    (exit_fill.fill_time - entry_fills[0].fill_time).total_seconds()
                    if exit_fill is not None and entry_fills
                    else 0.0
                ),
            )
            if filled_total > _QTY_EPS and exit_fill is not None
            else None
        )
        label = label_for(
            exit_reason=exit_reason,
            net_realized_edge=(costs.net_realized_edge if costs is not None else None),
        )
        return SimulatedTrade(
            trade_intent_id=spec.trade_intent_id,
            scenario_id=spec.scenario_id,
            decision_id=spec.decision_id,
            symbol=spec.symbol,
            side=spec.side,
            planned_quantity=spec.planned_quantity,
            filled_quantity=filled_total,
            entry_fills=tuple(entry_fills),
            exit_fill=exit_fill,
            exit_reason=exit_reason,
            stop_price=spec.stop_price,
            target_price=spec.target_price,
            ambiguity_resolved_conservatively=ambiguity,
            mfe_r=mfe,
            mae_r=mae,
            stop_distance=plan.stop_distance,
            costs=costs,
            label=label,
            regime=spec.regime,
        )


def _fill(price: float, quantity: float, fill_time: datetime, latency_ms: float) -> SimulatedFill:
    """تعبئة عند مستوى نظيف وزمن إغلاق الشمعة المعنية."""
    return SimulatedFill(
        fill_time=fill_time,
        price=price,
        quantity=quantity,
        latency_ms=latency_ms,
    )
