"""مخزن السيناريوهات — كتابة السيناريوهات وانتقالاتها وقراءة الحياة كاملة.

العقود (نمط fusion.store نفسه):

- **على اتصال المستدعي**: المخزن لا يملك اتصالًا ولا معاملة —
  ``asyncpg.Connection`` يُمرر لكل عملية وإدارة المعاملات مسؤولية
  المستدعي (نمط مخازن المراحل 3-6).
- **upsert idempotent**: السيناريو على ``scenario_id`` الحتمي
  (uuid5 — D-04) والانتقالات على هويتها الفريدة (السيناريو، من، إلى،
  وقت) بإلحاق-فقط (DO NOTHING) — إعادة الإرسال تحدّث الأصل ولا تكرر
  التاريخ أبدًا (روح D-07).
- **دورة الحياة باستعلام واحد**: ``read_lifecycle`` جولة SQL واحدة
  تجمع السيناريو وكل انتقالاته بترتيب الوقوع — سجل قابل للتدقيق
  (§31.3) بلا استعلامين ولا تجميع تطبيقي.
- **بوابة الخروج 7 صراحةً**: ``audit_licensing_readiness`` فحص آلي أن
  كل سيناريو بلغ TRIGGERED فما فوق (المرخِّص للصفقة) يحمل مشغلًا
  معرّفًا وإبطالًا معرّفًا — «لا سيناريو يُرخّص صفقة بلا مشغل وإبطال
  معرّفين».
- **الترميز القانوني**: كل JSONB بالترميز المصدَّر للنماذج
  (``model_dump_json``) والإعادة بناء عبر pydantic — لا dict خام.
"""

from __future__ import annotations

import json
import uuid as uuid_module
from collections.abc import Sequence

import asyncpg
from schemas import Scenario, ScenarioState, ScenarioTemplate, ScenarioTransition

from .lifecycle import TERMINAL_STATES
from .triggers import SUPPORTED_CONDITION_TYPES

__all__ = [
    "ScenarioStore",
    "ScenarioStoreError",
    "licensing_state_names",
    "template_names",
    "terminal_state_names",
    "transition_id_for",
]

#: الحالات المرخِّصة للصفقة — بلغتها صار للمشغل والإبطال معنى ترخيصي:
#: TRIGGERED فما فوق (ما بعد الترخيص ظلُّ المشغل والإبطال لازمًا له).
_LICENSING_STATES: frozenset[ScenarioState] = frozenset(
    {
        ScenarioState.TRIGGERED,
        ScenarioState.AUTHORIZED,
        ScenarioState.EXECUTING,
        ScenarioState.IN_TRADE,
        ScenarioState.COMPLETED,
    }
)

_LICENSING_STATE_NAMES = frozenset(state.value for state in _LICENSING_STATES)

#: مساحة اسم معرف الانتقال الحتمي — uuid5 فوق هوية الانتقال الكاملة.
_TRANSITION_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/scenario-transition"
)


class ScenarioStoreError(RuntimeError):
    """خلل في كتابة/قراءة بيانات السيناريوهات — خطأ تشغيلي صريح."""


def transition_id_for(transition: ScenarioTransition) -> uuid_module.UUID:
    """معرف الانتقال الحتمي — uuid5 فوق (السيناريو، من، إلى، الوقت)."""
    key = (
        f"{transition.scenario_id}|{transition.from_state.value}|"
        f"{transition.to_state.value}|{transition.transition_time.isoformat()}"
    )
    return uuid_module.uuid5(_TRANSITION_NAMESPACE, key)


def licensing_state_names() -> frozenset[str]:
    """أسماء الحالات المرخِّصة — للاستعلامات الخام المصدَّرة."""
    return _LICENSING_STATE_NAMES


def terminal_state_names() -> frozenset[str]:
    """أسماء الحالات النهائية — لا صادرة منها أبدًا (§38.2)."""
    return frozenset(state.value for state in TERMINAL_STATES)


def template_names() -> tuple[str, ...]:
    """أسماء القوالب الثلاثة §21.2 — للتحقق من الاكتمال في البوابات."""
    return tuple(member.value for member in ScenarioTemplate)


_UPSERT_SCENARIO_SQL = """
    INSERT INTO scenarios (
        scenario_id, symbol, direction, template, state, regime,
        proposed_from_event_id, scenario_score, expiry_time, payload,
        created_at, updated_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, now(), now())
    ON CONFLICT (scenario_id) DO UPDATE SET
        state = EXCLUDED.state,
        scenario_score = EXCLUDED.scenario_score,
        payload = EXCLUDED.payload,
        updated_at = now()
"""

_APPEND_TRANSITION_SQL = """
    INSERT INTO scenario_transitions (
        scenario_id, from_state, to_state, transition_time, reason, payload
    )
    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
    ON CONFLICT (scenario_id, from_state, to_state, transition_time)
    DO NOTHING
"""


class ScenarioStore:
    """مخزن السيناريوهات — كتابة وقراءة idempotent على اتصال المستدعي."""

    async def upsert_scenario(self, conn: asyncpg.Connection, scenario: Scenario) -> None:
        """كتابة/تحديث سيناريو — idempotent على المعرف الحتمي."""
        try:
            await conn.execute(
                _UPSERT_SCENARIO_SQL,
                scenario.scenario_id,
                scenario.symbol,
                scenario.direction.value,
                scenario.template.value,
                scenario.state.value,
                scenario.regime.value,
                uuid_module.UUID(scenario.proposed_from_event_id),
                float(scenario.scenario_score),
                scenario.expiry_time,
                scenario.model_dump_json(),
            )
        except Exception as exc:
            raise ScenarioStoreError(f"فشلت كتابة السيناريو {scenario.scenario_id}") from exc

    async def append_transition(
        self, conn: asyncpg.Connection, transition: ScenarioTransition
    ) -> None:
        """إلحاق انتقال واحد — idempotent على هويته الفريدة.

        الانتقال سجل تاريخي ملحق-فقط: إعادة الإرسال لا تفعل شيئًا
        (DO NOTHING) — التاريخ لا يُعاد كتابته أبدًا.
        """
        try:
            await conn.execute(
                _APPEND_TRANSITION_SQL,
                transition.scenario_id,
                transition.from_state.value,
                transition.to_state.value,
                transition.transition_time,
                transition.reason,
                transition.model_dump_json(),
            )
        except Exception as exc:
            raise ScenarioStoreError(
                f"فشل إلحاق انتقال {transition.scenario_id} "
                f"{transition.from_state.value}→{transition.to_state.value}"
            ) from exc

    async def write_lifecycle(
        self,
        conn: asyncpg.Connection,
        scenario: Scenario,
        transitions: Sequence[ScenarioTransition],
    ) -> None:
        """كتابة سيناريو وانتقالاته معًا — ذرية معاملة واحدة."""
        async with conn.transaction():
            await self.upsert_scenario(conn, scenario)
            for transition in transitions:
                await self.append_transition(conn, transition)

    # ───────────────────────── القراءة ─────────────────────────

    async def read_scenario(self, conn: asyncpg.Connection, scenario_id: str) -> Scenario | None:
        """قراءة سيناريو واحد — None عند الغياب."""
        query = "SELECT payload FROM scenarios WHERE scenario_id = $1"
        try:
            raw = await conn.fetchval(query, scenario_id)
        except Exception as exc:
            raise ScenarioStoreError(f"فشلت قراءة السيناريو {scenario_id}") from exc
        if raw is None:
            return None
        return Scenario.model_validate_json(raw)

    async def read_lifecycle(
        self, conn: asyncpg.Connection, scenario_id: str
    ) -> tuple[Scenario, tuple[ScenarioTransition, ...]] | None:
        """دورة الحياة كاملة باستعلام واحد — السيناريو وانتقالاته.

        جولة SQL واحدة: الصف الحالي + json_agg للانتقالات بترتيب الوقوع
        — لا استعلامين ولا تجميع تطبيقي (نمط read_chain في fusion).
        """
        query = """
            SELECT
                s.payload AS scenario_payload,
                COALESCE(
                    json_agg(
                        t.payload ORDER BY t.transition_time, t.id
                    ) FILTER (WHERE t.id IS NOT NULL),
                    '[]'::json
                ) AS transitions_payload
            FROM scenarios s
            LEFT JOIN scenario_transitions t
                ON t.scenario_id = s.scenario_id
            WHERE s.scenario_id = $1
            GROUP BY s.payload
        """
        try:
            row = await conn.fetchrow(query, scenario_id)
        except Exception as exc:
            raise ScenarioStoreError(f"فشلت قراءة حياة {scenario_id}") from exc
        if row is None:
            return None
        raw_scenario = row["scenario_payload"]
        scenario = (
            Scenario.model_validate_json(raw_scenario)
            if isinstance(raw_scenario, str)
            else Scenario.model_validate(raw_scenario)
        )
        raw_transitions = row["transitions_payload"]
        decoded = (
            json.loads(raw_transitions) if isinstance(raw_transitions, str) else raw_transitions
        )
        transitions = tuple(ScenarioTransition.model_validate(item) for item in decoded)
        return scenario, transitions

    async def list_by_state(
        self, conn: asyncpg.Connection, state: ScenarioState
    ) -> tuple[Scenario, ...]:
        """السيناريوهات بحالة واحدة بترتيب معرف حتمي."""
        query = "SELECT payload FROM scenarios WHERE state = $1 ORDER BY scenario_id"
        try:
            rows = await conn.fetch(query, state.value)
        except Exception as exc:
            raise ScenarioStoreError(f"فشل عدّ السيناريوهات بحالة {state.value}") from exc
        return tuple(Scenario.model_validate_json(row["payload"]) for row in rows)

    # ───────────────────────── بوابة الخروج 7 ─────────────────────────

    async def audit_licensing_readiness(
        self, conn: asyncpg.Connection
    ) -> tuple[int, tuple[str, ...]]:
        """الفحص الآلي للبوابة: كل مرخِّص يحمل مشغلًا وإبطالًا معرّفين.

        «لا سيناريو يُرخّص صفقة بلا مشغل وإبطال معرّفين (اختبار آلي
        يفحص كل TRIGGERED)» — الفحص على الحالات المرخِّصة كلها.

        :returns: (عدد المرخِّصين المفحوصين، معرفات المخالفين).
        """
        query = """
            SELECT scenario_id, payload FROM scenarios
            WHERE state = ANY($1::text[])
            ORDER BY scenario_id
        """
        try:
            rows = await conn.fetch(query, sorted(_LICENSING_STATE_NAMES))
        except Exception as exc:
            raise ScenarioStoreError("فشل فحص بوابة الترخيص") from exc
        violators: list[str] = []
        for row in rows:
            scenario = Scenario.model_validate_json(row["payload"])
            if not licensing_definition_complete(scenario):
                violators.append(row["scenario_id"])
        return len(rows), tuple(violators)


def licensing_definition_complete(scenario: Scenario) -> bool:
    """اكتمال المشغل والإبطال تعريفًا — فحص هيكلي صرف لا نص غامض.

    المشغل: نوع معروف من الأنواع الخمسة المدعومة بمعاملاته، والإبطال:
    مستوى بنيوي موجب بعازلة معلنة — كلاهما ينتجه المُقترِح حتميًا فأي
    نقص يعني عبثًا خارج المسار الموثق.
    """
    trigger = scenario.trigger_definition
    if trigger.condition_type not in SUPPORTED_CONDITION_TYPES:
        return False
    if not trigger.params:
        return False
    invalidation = scenario.invalidation
    if float(invalidation.structural_level) <= 0.0:
        return False
    return float(invalidation.volatility_buffer) >= 0.0
