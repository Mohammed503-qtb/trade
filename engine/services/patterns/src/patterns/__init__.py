"""الأنماط — الشموعي والكلاسيكي (§13) — الهارمونيك (§14) مؤجل صراحة بعد MVP.

- :mod:`patterns.candle_patterns` — العائلات الثماني §13.1 مستعارات لتركيبات
  السمات الست + كاشف أحداث §20 الثلاثة الشموعية (المهمة 5-b).
- :mod:`patterns.classical` — البُنى الكلاسيكية الثماني §13.2 بمخرجاتها
  الثمانية + كسر وفشل (المهمة 5-c).
"""

from .candle_patterns import (
    CandleClassification,
    CandlePatternConfig,
    CandlePatternDetector,
    classify_doji,
    classify_engulfing,
    classify_expansion,
    classify_hammer_shooting_star,
    classify_inside_bar,
    classify_inside_bar_break,
    classify_last_candle,
    classify_morning_evening_star,
    classify_rejection,
    classify_strong_closing,
)
from .candle_patterns import (
    EmittedEvent as CandleEmittedEvent,
)
from .classical import (
    ClassicalConfig,
    ClassicalPatternDetector,
    EmittedEvent,
    Pivot,
    PivotKind,
    find_pivots,
)

__version__ = "0.1.0"

__all__ = [
    "CandleClassification",
    "CandleEmittedEvent",
    "CandlePatternConfig",
    "CandlePatternDetector",
    "ClassicalConfig",
    "ClassicalPatternDetector",
    "EmittedEvent",
    "Pivot",
    "PivotKind",
    "__version__",
    "classify_doji",
    "classify_engulfing",
    "classify_expansion",
    "classify_hammer_shooting_star",
    "classify_inside_bar",
    "classify_inside_bar_break",
    "classify_last_candle",
    "classify_morning_evening_star",
    "classify_rejection",
    "classify_strong_closing",
    "find_pivots",
]
