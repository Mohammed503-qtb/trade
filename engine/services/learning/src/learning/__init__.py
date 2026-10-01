"""دفتر التجارب (كتابة §29.1) — التحليلات مؤجلة بعد MVP.

التصدير الموحد: بناء سجل التجربة ومعرفه الحتمي ومخزنه — البوابة 8.6:
كتابة السجل عند إغلاق أي سيناريو مُقيَّم (صف-لكل-سيناريو §31.5).
"""

from __future__ import annotations

from .ledger import build_experience_record, experience_id_for, measure_excursions
from .store import ExperienceStore, ExperienceStoreError

__all__ = [
    "ExperienceStore",
    "ExperienceStoreError",
    "build_experience_record",
    "experience_id_for",
    "measure_excursions",
]

__version__ = "0.1.0"
