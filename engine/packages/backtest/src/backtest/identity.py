"""هوية الإعادة والاستنساخ (§26.2) — ختم uuid5 حتمي فوق المعرّفات التسع.

«Every backtest creates: backtest_id, data_snapshot_id, code_version,
model_version, parameter_set_version, cost_model_version, random_seed,
start_time, end_time, instrument_set. The exact result must be
reproducible from those identifiers» — المعرف مشتق من المعرّفات ذاتها
فيتطابق التقريران المتطابقتان الهوية حتمًا (لا انفصام بين الهوية
والمضمون).
"""

from __future__ import annotations

import uuid as uuid_module

from schemas import BacktestIdentity

__all__ = ["BACKTEST_NAMESPACE", "backtest_id_for"]

#: مساحة اسم الإعادة — ثابتة عبر الإصدارات (تغييرها يكسر الاستنساخ).
BACKTEST_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/backtest"
)

#: ترتيب الحقول في الختم — حتمي (لا ترتيب وصول قاموس).
_IDENTITY_FIELDS: tuple[str, ...] = (
    "data_snapshot_id",
    "code_version",
    "model_version",
    "parameter_set_version",
    "cost_model_version",
    "random_seed",
    "start_time",
    "end_time",
    "instrument_set",
)


def backtest_id_for(identity: BacktestIdentity) -> str:
    """معرف الإعادة الحتمي — uuid5 فوق المعرّفات التسع غير المشتقة.

    ``backtest_id`` نفسه لا يدخل الختم (اكتفاء ذاتي)؛ ``instrument_set``
    تدخل مفصولةً بترتيبها المعلن (مجموعة أدوات هيية لا متعددة).
    """
    parts = [
        str(getattr(identity, field))
        if field != "instrument_set"
        else "|".join(identity.instrument_set)
        for field in _IDENTITY_FIELDS
    ]
    return str(uuid_module.uuid5(BACKTEST_NAMESPACE, "·".join(parts)))
