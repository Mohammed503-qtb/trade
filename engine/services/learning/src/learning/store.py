"""مخزن دفتر التجارب — صف واحد لكل سيناريو مُقيَّم (§31.5).

«Immutable one-row-per-trade or one-row-per-scenario experience
reference» — الصف يكتب مرة (upsert بـDO NOTHING على سيناريوه) ولا
يُحدّث أبدًا: الدفتر مرجع جامد والتعلم يمر عبر إعادة تقدير بلا اتصال
وبوابات ترقية (§2.7 «التعلم محكوم لا مفسدٌ ذاته»).

نمط ``risk.store`` و``scenarios.store`` نفسه: على اتصال المستدعي،
idempotent على المعرف الحتمي (uuid5 فوق السيناريو — ``experience_id_for``)،
والترميز القانوني للنموذج كاملاً في JSONB (ADR-021).
"""

from __future__ import annotations

import asyncpg
from schemas import ExperienceRecord

from .ledger import experience_id_for

__all__ = ["ExperienceStore", "ExperienceStoreError"]


class ExperienceStoreError(RuntimeError):
    """خلل في كتابة/قراءة دفتر التجارب — خطأ تشغيلي صريح."""


_UPSERT_EXPERIENCE_SQL = """
    INSERT INTO experience_ledger (
        experience_id, scenario_id, symbol, direction, exit_state,
        exit_reason, approved, mfe, mae, holding_time, net_r,
        regime, session, payload, created_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, now())
    ON CONFLICT (scenario_id) DO NOTHING
"""


class ExperienceStore:
    """مخزن دفتر التجارب — كتابة وقراءة على اتصال المستدعي."""

    async def upsert_experience(self, conn: asyncpg.Connection, record: ExperienceRecord) -> None:
        """كتابة سجل تجربة — idempotent على السيناريو (DO NOTHING).

        الدفتر ملحق-فقط: إعادة الإرسال لا تفعل شيئًا ولا تحرف — الصف
        المرجعي يُكتب مرة عند الإغلاق ويبقى جامدًا (§31.5).
        """
        scenario = record.scenario_snapshot
        try:
            await conn.execute(
                _UPSERT_EXPERIENCE_SQL,
                experience_id_for(scenario.scenario_id),
                scenario.scenario_id,
                scenario.symbol,
                scenario.direction.value,
                scenario.state.value,
                record.exit_reason,
                record.risk_snapshot.approved,
                float(record.mfe),
                float(record.mae),
                float(record.holding_time),
                float(record.net_r),
                record.regime.value,
                record.session.value,
                record.model_dump_json(),
            )
        except Exception as exc:
            raise ExperienceStoreError(f"فشلت كتابة تجربة {scenario.scenario_id}") from exc

    async def read_experience(
        self, conn: asyncpg.Connection, scenario_id: str
    ) -> ExperienceRecord | None:
        """قراءة سجل تجربة سيناريو — None عند الغياب."""
        query = "SELECT payload FROM experience_ledger WHERE scenario_id = $1"
        try:
            raw = await conn.fetchval(query, scenario_id)
        except Exception as exc:
            raise ExperienceStoreError(f"فشلت قراءة تجربة {scenario_id}") from exc
        if raw is None:
            return None
        return ExperienceRecord.model_validate_json(raw)

    async def list_by_symbol(
        self, conn: asyncpg.Connection, symbol: str
    ) -> tuple[ExperienceRecord, ...]:
        """تجارب أداة بترتيب الكتابة — تصفح الدفتر."""
        query = (
            "SELECT payload FROM experience_ledger WHERE symbol = $1 "
            "ORDER BY created_at, experience_id"
        )
        try:
            rows = await conn.fetch(query, symbol)
        except Exception as exc:
            raise ExperienceStoreError(f"فشل عدّ تجارب {symbol}") from exc
        return tuple(ExperienceRecord.model_validate_json(row["payload"]) for row in rows)
