"""محمل عينة المرحلة 2 للاختبارات — نفس مصدر البوابات (سطر واحد)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_PHASE2_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "phase2"


def load_phase2_bars(timeframe: str = "1m") -> list[dict[str, Any]]:
    """الشموع الخام لإطار العينة المرجعية — كما هي في الملف."""
    loaded = json.loads((_PHASE2_DIR / f"klines_{timeframe}.json").read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], loaded)
