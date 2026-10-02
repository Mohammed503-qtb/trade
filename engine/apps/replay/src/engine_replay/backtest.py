"""خط أنابيب الإعادة (ميكانيكا §26) — من نوايا معتمدة إلى تقرير موثق.

«المحرك الفعلي يُبنى في المرحلة 9» (وعد ``__main__`` من المرحلة 0):
هذا الموديول هو ذلك المحرك — التركيب القابل لإعادة الاستخدام فوق
مكتبة ``backtest``: نوايا دخول معتمدة + شموع إطار التنفيذ ⇒ تعبئات
محاكاة ⇒ وسم §30 ⇒ مقاييس §29.2 ⇒ تقرير §26.2 مختوم الهوية.

حدود موثقة: هذا خط ميكانيكا التنفيذ (ما بعد قرار المخاطرة)؛ التركيب
الكامل (كواشف ← دمج ← سيناريوهات ← مخاطرة ← تنفيذ) يعمل في سلسلة
بوابات المراحل (verify_phase7/8/9) — لا ازدواج تركيب.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from backtest import (
    BacktestConfig,
    ReplayWindow,
    SimulatedExecutor,
    build_report,
    default_backtest_config,
)
from schemas import BacktestIdentity, BacktestReport, Candle, EntrySpec, SimulatedTrade

__all__ = ["run_backtest", "sort_specs"]

#: إطار التنفيذ — 1m حصرًا في MVP (يطابق عقد المنفّذ).
_EXECUTION_TIMEFRAME_S = 60.0


def sort_specs(specs: Sequence[EntrySpec]) -> tuple[EntrySpec, ...]:
    """ترتيب حتمي للمواصفات: لحظة القرار ثم معرف السيناريو.

    ترتيب المواصفات هو ترتيب الصفقات في التقرير — حتمي دائمًا.
    """
    return tuple(sorted(specs, key=lambda s: (s.decision_time, s.scenario_id)))


def run_backtest(
    *,
    specs: Sequence[EntrySpec],
    candles: Sequence[Candle],
    identity: BacktestIdentity,
    config: BacktestConfig | None = None,
    now: Callable[[], datetime] | None = None,
) -> tuple[BacktestReport, tuple[SimulatedTrade, ...]]:
    """تشغيل الإعادة الميكانيكية — كل نية فوق مسار الشموع نفسه.

    النافذة (§26.3) تُبنى مرة فوق السلسلة الكاملة (ترتيب زمني محقق
    بنيويًا) والمنفّذ يستهلك من كل نية ما بعد شمعة قرارها حصرًا —
    القرار لا يرى المستقبل والتنفيذ لا يرى غير أمامه.

    :returns: (التقرير المختوم، الصفقات بترتيب المواصفات الحتمي).
    """
    if not specs:
        raise ValueError("لا إعادة بلا نوايا — خط الأنابيب يحتاج مواصفة واحدة على الأقل")
    execution_config = config or default_backtest_config()
    window = ReplayWindow(
        candles=tuple(candles),
        timeframe_s=_EXECUTION_TIMEFRAME_S,
    )
    executor = SimulatedExecutor(execution_config)
    ordered = sort_specs(specs)
    trades = tuple(executor.execute(spec, window.candles) for spec in ordered)
    report = build_report(
        identity=identity,
        trades=trades,
        config=execution_config,
        now=now,
    )
    return report, trades
