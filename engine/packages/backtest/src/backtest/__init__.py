"""محرك الإعادة، التكاليف، الوسم، المقاييس (§26 + §30 + §29.2 + §39.3).

«الإعادة القانونية للقبول تعمل في محرك الإعادة الخارجي» (§28) — هذه
مكتبة الميكانيكا الصرفة تحت الكواشف (عقد الطبقات §47): نافذة القراءة
المتحركة (§26.3) والمنفّذ المحاكي (§26.1) والتكاليف المحققة (§25.2)
والوسم (§30) والمقاييس (§29.2) والتدحرج الأمامي (§39.3) وتقرير
الاستنساخ (§26.2).

التركيب فوق السيناريوهات والمخاطرة يعيش في الطبقات الأعلى
(engine_replay وسكربتات البوابات) — هذه الحزمة لا تعرف القرار، فقط
تنفّذه في عالم محاكى حتمي.
"""

from .costs import realize_costs
from .execution import ExecutionPlan, SimulatedExecutor
from .identity import BACKTEST_NAMESPACE, backtest_id_for
from .labeling import label_for
from .metrics import compute_metrics, net_r_of
from .parameter_sets import (
    DEFAULT_SAMPLE_WFO_PROTOCOL,
    BacktestConfig,
    CostSchedule,
    default_backtest_config,
)
from .report import BASE_NOTES, build_report
from .wfo import WFOProtocolError, research_protocol, split_windows
from .window import ReplayWindow, timed_event

__version__ = "0.1.0"

__all__ = [
    "BACKTEST_NAMESPACE",
    "BASE_NOTES",
    "DEFAULT_SAMPLE_WFO_PROTOCOL",
    "BacktestConfig",
    "CostSchedule",
    "ExecutionPlan",
    "ReplayWindow",
    "SimulatedExecutor",
    "WFOProtocolError",
    "backtest_id_for",
    "build_report",
    "compute_metrics",
    "default_backtest_config",
    "label_for",
    "net_r_of",
    "realize_costs",
    "research_protocol",
    "split_windows",
    "timed_event",
]
