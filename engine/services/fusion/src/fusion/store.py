"""مخزن الدمج — كتابة سجل الدليل ولقطاته وقراءة السلسلة الكاملة.

العقود (نمط 0005/بنية مخازن المراحل 3-5a نفسها):

- **upsert idempotent**: الأدلة على ``evidence_id`` الحتمي واللقطات على
  (scenario_id, fusion_time) — إعادة الإرسال/إعادة الحساب تحدّث ولا
  تكرر أبدًا (روح D-07)؛ عمود المساهمة ``contribution`` يحسبه المخزن
  بالمعادلة الرسمية (compute.contribution) فيبقى السجل واللقطة
  والعمود متسقين حتميًا.
- **السلسلة باستعلام واحد** (بوابة الخروج 6): ``read_chain`` جولة SQL
  واحدة تجمع أدلة السيناريو كاملة بترتيب حتمي وأحدث لقطة له — لا
  استعلامين ولا تجميع تطبيقي.
- **الترميز القانوني**: كل JSONB بالترميز المصدَّر للنماذج
  (``model_dump_json``) والإعادة بناء عبر pydantic — لا dict خام.

ترتيب السلسلة من القاعدة (event_time, evidence_id) حتمي تمامًا؛ ترتيب
التأليف الأصلي (حالة أولًا ثم أحداث بالوصول) تحمله ``evidence_ids``
داخل اللقطة نفسها.
"""

from __future__ import annotations

import json
import uuid as uuid_module
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import asyncpg
from schemas import EvidenceRecord, FusionSnapshot

from .compute import contribution

__all__ = [
    "FusionStore",
    "FusionStoreError",
    "fusion_snapshot_id",
]

#: مساحة اسم معرف اللقطة الحتمي — uuid5 فوق (السيناريو، لحظة القرار).
_SNAPSHOT_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/fusion-snapshot"
)


class FusionStoreError(RuntimeError):
    """خلل في كتابة/قراءة بيانات الدمج — خطأ تشغيلي صريح."""


def fusion_snapshot_id(scenario_id: str, fusion_time: datetime) -> uuid_module.UUID:
    """معرف لقطة حتمي — نفس (السيناريو، اللحظة) ⇒ نفس المعرف."""
    return uuid_module.uuid5(
        _SNAPSHOT_NAMESPACE, f"snapshot|{scenario_id}|{fusion_time.isoformat()}"
    )


class FusionStore:
    """كتابة وقراءة سجل الدليل ولقطات الدمج — على اتصال المستدعي.

    لا يملك المخزن اتصالًا ولا معاملة: يُمرر ``asyncpg.Connection`` لكل
    عملية (نمط مخازن المراحل السابقة) — إدارة المعاملات مسؤولية
    المستدعي.
    """

    async def upsert_evidence(
        self,
        conn: asyncpg.Connection,
        records: Sequence[EvidenceRecord],
        *,
        scenario_id: str,
    ) -> None:
        """كتابة سجلات الدليل idempotent على ``evidence_id`` (DO UPDATE).

        ``scenario_id`` إلزامي صريح من المستدعي — عمود الفهرسة
        والسلسلة، والدليل ملك سيناريوه لا يتسرب بينها.
        """
        if not records:
            return
        rows = []
        for record in records:
            rows.append(
                (
                    uuid_module.UUID(record.evidence_id),
                    scenario_id,
                    uuid_module.UUID(record.event_id) if record.event_id is not None else None,
                    record.event_type.value,
                    record.group.value,
                    record.event_time,
                    record.direction_score,
                    record.raw_strength,
                    record.quality,
                    record.freshness,
                    record.independence_discount,
                    record.prior_weight,
                    record.context_modifier,
                    contribution(record),
                    record.opposition,
                    record.correlation_group_id,
                    record.source,
                    record.model_dump_json(),
                )
            )
        try:
            await conn.executemany(
                """
                INSERT INTO evidence_items (
                    evidence_id, scenario_id, event_id, event_type, evidence_group,
                    event_time, direction_score, raw_strength, quality, freshness,
                    independence_discount, prior_weight, context_modifier,
                    contribution, opposition, correlation_group_id, source, payload
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18::jsonb
                )
                ON CONFLICT (evidence_id) DO UPDATE SET
                    direction_score = EXCLUDED.direction_score,
                    raw_strength = EXCLUDED.raw_strength,
                    quality = EXCLUDED.quality,
                    freshness = EXCLUDED.freshness,
                    independence_discount = EXCLUDED.independence_discount,
                    prior_weight = EXCLUDED.prior_weight,
                    context_modifier = EXCLUDED.context_modifier,
                    contribution = EXCLUDED.contribution,
                    opposition = EXCLUDED.opposition,
                    correlation_group_id = EXCLUDED.correlation_group_id,
                    payload = EXCLUDED.payload
                """,
                rows,
            )
        except Exception as exc:
            raise FusionStoreError(f"فشل upsert سجل الدليل: {exc}") from exc

    async def upsert_snapshot(self, conn: asyncpg.Connection, snapshot: FusionSnapshot) -> None:
        """كتابة لقطة دمج idempotent على (السيناريو، لحظة القرار)."""
        snapshot_id = fusion_snapshot_id(snapshot.scenario_id, snapshot.fusion_time)
        try:
            await conn.execute(
                """
                INSERT INTO fusion_snapshots (
                    snapshot_id, scenario_id, fusion_time, direction,
                    raw_evidence_score, vetoed, evidence_count, snapshot
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                ON CONFLICT (scenario_id, fusion_time) DO UPDATE SET
                    raw_evidence_score = EXCLUDED.raw_evidence_score,
                    vetoed = EXCLUDED.vetoed,
                    evidence_count = EXCLUDED.evidence_count,
                    snapshot = EXCLUDED.snapshot
                """,
                snapshot_id,
                snapshot.scenario_id,
                snapshot.fusion_time,
                snapshot.direction.value,
                snapshot.raw_evidence_score,
                snapshot.vetoed,
                len(snapshot.evidence_ids),
                snapshot.model_dump_json(),
            )
        except Exception as exc:
            raise FusionStoreError(
                f"فشل upsert لقطة الدمج للسيناريو {snapshot.scenario_id}: {exc}"
            ) from exc

    async def read_chain(
        self,
        conn: asyncpg.Connection,
        scenario_id: str,
    ) -> tuple[list[EvidenceRecord], FusionSnapshot | None]:
        """سلسلة الدليل الكاملة **باستعلام واحد** (بوابة الخروج 6).

        جولة SQL واحدة تجمع: كل أدلة السيناريو بترتيب حتمي
        (event_time ثم evidence_id) وأحدث لقطة له (fusion_time تنازليًا)
        — دفعة واحدة تُعاد بناؤها عبر النماذج القانونية.
        """
        query = """
            SELECT
                (SELECT json_agg(row_to_json(e) ORDER BY e.event_time ASC, e.evidence_id ASC)
                 FROM evidence_items e WHERE e.scenario_id = $1) AS evidence,
                (SELECT row_to_json(s)
                 FROM (
                     SELECT snapshot FROM fusion_snapshots
                     WHERE scenario_id = $1
                     ORDER BY fusion_time DESC LIMIT 1
                 ) s) AS latest_snapshot
        """
        try:
            row = await conn.fetchrow(query, scenario_id)
        except Exception as exc:
            raise FusionStoreError(
                f"فشل قراءة سلسلة الدليل للسيناريو {scenario_id}: {exc}"
            ) from exc
        if row is None:
            return [], None
        records = self._records_from_json(row["evidence"])
        snapshot = self._snapshot_from_json(row["latest_snapshot"])
        return records, snapshot

    async def read_snapshots(
        self,
        conn: asyncpg.Connection,
        scenario_id: str,
        *,
        limit: int = 10,
    ) -> list[FusionSnapshot]:
        """تاريخ لقطات السيناريو (الأحدث أولًا) — لعرض أثر الاستدلال."""
        try:
            rows = await conn.fetch(
                """
                SELECT snapshot FROM fusion_snapshots
                WHERE scenario_id = $1
                ORDER BY fusion_time DESC LIMIT $2
                """,
                scenario_id,
                limit,
            )
        except Exception as exc:
            raise FusionStoreError(f"فشل قراءة لقطات السيناريو {scenario_id}: {exc}") from exc
        snapshots = []
        for row in rows:
            parsed = self._snapshot_from_json(row["snapshot"])
            if parsed is not None:
                snapshots.append(parsed)
        return snapshots

    # ── أدوات داخلية ──

    @staticmethod
    def _records_from_json(raw: Any) -> list[EvidenceRecord]:
        """إعادة بناء السجلات من JSONB القاعدة عبر النموذج القانوني."""
        if raw is None:
            return []
        data = json.loads(raw) if isinstance(raw, str) else raw
        return [EvidenceRecord.model_validate(entry["payload"]) for entry in data]

    @staticmethod
    def _snapshot_from_json(raw: Any) -> FusionSnapshot | None:
        """إعادة بناء اللقطة من JSONB القاعدة — None عند غيابها."""
        if raw is None:
            return None
        decoded = json.loads(raw) if isinstance(raw, str) else raw
        # row_to_json يغلّف عمود snapshot: {"snapshot": {...}}
        inner = (
            decoded["snapshot"] if isinstance(decoded, dict) and "snapshot" in decoded else decoded
        )
        return FusionSnapshot.model_validate(inner)
