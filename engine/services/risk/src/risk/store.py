"""مخزن المخاطرة — كتابة القرارات والنوايا وقراءتها وفحص البوابة.

العقود (نمط scenarios.store نفسه):

- **على اتصال المستدعي**: المخزن لا يملك اتصالًا ولا معاملة —
  ``asyncpg.Connection`` يُمرر لكل عملية (نمط مخازن المراحل 3-7).
- **upsert idempotent**: القرار على ``decision_id`` الحتمي (uuid5 فوق
  السيناريو) والنية على ``trade_intent_id`` — إعادة الإرسال تحدّث
  الأصل ولا تكرر أبدًا (روح D-07).
- **القراءة بجولة واحدة**: ``read_decision_with_scenario`` تربط القرار
  بسيناريوه وانتقالات حياته بجولة SQL واحدة — أثر الاستدلال الكامل
  (§35.3) من قراره.
- **بوابة الخروج 8 نصًا**: ``audit_risk_gate`` الفحص الآلي أن كل خرق
  مخاطرة = رفض صلب موثق بكود — كل قرار معتمد عبر كل البوابات، وكل
  مرفوض بأساس موثق، وكل تفسير مكتمل (§2.8/§22.3).
- **الترميز القانوني**: كل JSONB بـ``model_dump_json`` والإعادة بناء
  عبر pydantic (قرار ADR-021).
"""

from __future__ import annotations

import json

import asyncpg
from schemas import (
    OrderIntent,
    RiskDecision,
    Scenario,
    ScenarioTransition,
    validate_explanation_completeness,
)

__all__ = [
    "RiskStore",
    "RiskStoreError",
]


class RiskStoreError(RuntimeError):
    """خلل في كتابة/قراءة بيانات المخاطرة — خطأ تشغيلي صريح."""


_UPSERT_DECISION_SQL = """
    INSERT INTO decisions (
        decision_id, scenario_id, symbol, direction, decided_at,
        approved, rejection_basis, hard_block_count, soft_suppression_count,
        estimated_net_r, parameter_fingerprint, payload, created_at, updated_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, now(), now())
    ON CONFLICT (decision_id) DO UPDATE SET
        approved = EXCLUDED.approved,
        rejection_basis = EXCLUDED.rejection_basis,
        hard_block_count = EXCLUDED.hard_block_count,
        soft_suppression_count = EXCLUDED.soft_suppression_count,
        estimated_net_r = EXCLUDED.estimated_net_r,
        parameter_fingerprint = EXCLUDED.parameter_fingerprint,
        payload = EXCLUDED.payload,
        updated_at = now()
"""

_UPSERT_INTENT_SQL = """
    INSERT INTO trade_intents (
        trade_intent_id, decision_id, scenario_id, symbol, side,
        entry_policy, stop, max_slippage, max_latency, expiry,
        risk_budget, payload, created_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, now())
    ON CONFLICT (trade_intent_id) DO UPDATE SET
        stop = EXCLUDED.stop,
        risk_budget = EXCLUDED.risk_budget,
        expiry = EXCLUDED.expiry,
        payload = EXCLUDED.payload
"""


class RiskStore:
    """مخزن القرارات والنوايا — كتابة وقراءة idempotent على اتصال المستدعي."""

    async def upsert_decision(self, conn: asyncpg.Connection, decision: RiskDecision) -> None:
        """كتابة/تحديث قرار — idempotent على المعرف الحتمي."""
        reward = decision.reward_risk
        try:
            await conn.execute(
                _UPSERT_DECISION_SQL,
                decision.decision_id,
                decision.scenario_id,
                decision.symbol,
                decision.direction.value,
                decision.decided_at,
                decision.approved,
                decision.rejection_basis.value if decision.rejection_basis else None,
                len(decision.hard_blocks),
                len(decision.soft_suppressions),
                float(reward.estimated_net_r) if reward is not None else None,
                decision.parameter_fingerprint,
                decision.model_dump_json(),
            )
        except Exception as exc:
            raise RiskStoreError(f"فشلت كتابة القرار {decision.decision_id}") from exc

    async def upsert_intent(
        self, conn: asyncpg.Connection, intent: OrderIntent, *, decision_id: str
    ) -> None:
        """كتابة نية أمر مرخَّصة — نيّة لقرار معتمد حصرًا (FK)."""
        try:
            await conn.execute(
                _UPSERT_INTENT_SQL,
                intent.trade_intent_id,
                decision_id,
                intent.scenario_id,
                intent.symbol,
                intent.side.value,
                intent.entry_policy.value,
                float(intent.stop),
                float(intent.max_slippage),
                float(intent.max_latency),
                intent.expiry,
                float(intent.risk_budget),
                intent.model_dump_json(),
            )
        except Exception as exc:
            raise RiskStoreError(f"فشلت كتابة النية {intent.trade_intent_id}") from exc

    async def write_outcome(self, conn: asyncpg.Connection, decision: RiskDecision) -> None:
        """كتابة حصيلة قرار واحدة — القرار ونيته بمعاملة ذرية.

        النية تكتب للمرخَّصين حصرًا: المرفوض لا نية له أصلاً (عقد
        RiskDecision) — وإعادة كتابة قرار برفض تمحو أية نية راكدة له
        (اتساق دفاعي: قرار السيناريو واحد ونيته تابعة له لا للتاريخ).
        """
        async with conn.transaction():
            await self.upsert_decision(conn, decision)
            if decision.approved and decision.order_intent is not None:
                await self.upsert_intent(
                    conn, decision.order_intent, decision_id=decision.decision_id
                )
            else:
                await conn.execute(
                    "DELETE FROM trade_intents WHERE decision_id = $1",
                    decision.decision_id,
                )

    # ───────────────────────── القراءة ─────────────────────────

    async def read_decision(
        self, conn: asyncpg.Connection, decision_id: str
    ) -> RiskDecision | None:
        """قراءة قرار واحد — None عند الغياب."""
        query = "SELECT payload FROM decisions WHERE decision_id = $1"
        try:
            raw = await conn.fetchval(query, decision_id)
        except Exception as exc:
            raise RiskStoreError(f"فشلت قراءة القرار {decision_id}") from exc
        if raw is None:
            return None
        return RiskDecision.model_validate_json(raw)

    async def read_decision_with_lifecycle(
        self, conn: asyncpg.Connection, scenario_id: str
    ) -> tuple[RiskDecision, Scenario, tuple[ScenarioTransition, ...]] | None:
        """القرار وسيناريوه وانتقالاته بجولة SQL واحدة — أثر كامل قابل للتدقيق."""
        query = """
            SELECT
                d.payload AS decision_payload,
                s.payload AS scenario_payload,
                COALESCE(
                    json_agg(
                        t.payload ORDER BY t.transition_time, t.id
                    ) FILTER (WHERE t.id IS NOT NULL),
                    '[]'::json
                ) AS transitions_payload
            FROM decisions d
            JOIN scenarios s ON s.scenario_id = d.scenario_id
            LEFT JOIN scenario_transitions t ON t.scenario_id = d.scenario_id
            WHERE d.scenario_id = $1
            GROUP BY d.payload, s.payload
        """
        try:
            row = await conn.fetchrow(query, scenario_id)
        except Exception as exc:
            raise RiskStoreError(f"فشلت قراءة قرار وحياة {scenario_id}") from exc
        if row is None:
            return None
        decision = RiskDecision.model_validate_json(row["decision_payload"])
        scenario = Scenario.model_validate_json(row["scenario_payload"])
        raw_transitions = row["transitions_payload"]
        decoded = (
            json.loads(raw_transitions) if isinstance(raw_transitions, str) else raw_transitions
        )
        transitions = tuple(ScenarioTransition.model_validate(item) for item in decoded)
        return decision, scenario, transitions

    async def list_rejections(
        self, conn: asyncpg.Connection, *, symbol: str | None = None
    ) -> tuple[RiskDecision, ...]:
        """سجل الرفض — وقود لوحة §35.3 (قرارات بلا ترخيص بترتيب القرار)."""
        if symbol is None:
            query = (
                "SELECT payload FROM decisions WHERE approved = false "
                "ORDER BY decided_at, decision_id"
            )
            rows = await conn.fetch(query)
        else:
            query = (
                "SELECT payload FROM decisions WHERE approved = false AND symbol = $1 "
                "ORDER BY decided_at, decision_id"
            )
            rows = await conn.fetch(query, symbol)
        return tuple(RiskDecision.model_validate_json(row["payload"]) for row in rows)

    # ───────────────────────── بوابة الخروج 8 ─────────────────────────

    async def audit_risk_gate(self, conn: asyncpg.Connection) -> tuple[int, tuple[str, ...]]:
        """الفحص الآلي للبوابة نصًا: كل خرق مخاطرة = رفض صلب موثق بكود.

        يفحص كل قرار في القاعدة:

        1. **كل معتمد اكتمل**: لا حواجب صلبة، وله وقف وتحجيم وحافة
           (وقد كتبت نيته في trade_intents).
        2. **كل مرفوض موثق**: أساس معلن، ولا نية أمر له.
        3. **كل تفسير مكتمل** (§2.8): كل الحقول حاضرة، وسبب الرفض
           عند الرفض حصرًا.
        4. **كل تفسير رفض مكتمل** (§22.3): الشروط المشعلة واضحة.

        :returns: (عدد القرارات المفحوصة، معرفات المخالفين).
        """
        query = "SELECT decision_id, payload FROM decisions ORDER BY decision_id"
        try:
            rows = await conn.fetch(query)
        except Exception as exc:
            raise RiskStoreError("فشل فحص بوابة المخاطرة") from exc

        violators: list[str] = []
        for row in rows:
            try:
                decision = RiskDecision.model_validate_json(row["payload"])
            except ValueError:
                # صف لا يحقق عقد القرار أصلاً — عبث خارج المسار = مخالفة
                violators.append(row["decision_id"])
                continue
            if _risk_gate_violations(decision):
                violators.append(row["decision_id"])
        # كل مرخَّص له نيته في trade_intents (اكتمال الترخيص تخزينًا أيضًا)
        approved_ids = {
            row["decision_id"]
            for row in await conn.fetch("SELECT decision_id FROM decisions WHERE approved = true")
        }
        intent_decisions = {
            row["decision_id"] for row in await conn.fetch("SELECT decision_id FROM trade_intents")
        }
        missing_intents = approved_ids - intent_decisions
        violators.extend(sorted(missing_intents))
        return len(rows), tuple(sorted(set(violators)))


def _risk_gate_violations(decision: RiskDecision) -> bool:
    """هل القرار يخالف عقد بوابة المخاطرة؟ — فحص صرف بلا قاعدة."""
    # التفسير §2.8 مكتمل — استثناء داخلي يعني خللاً جوهرياً
    try:
        validate_explanation_completeness(decision.explanation, rejected=not decision.approved)
    except ValueError:
        return True
    if decision.approved:
        # المعتمد عبر كل البوابات: لا حواجب ولا أساس رفض وكل الأجزاء
        if decision.hard_blocks or decision.rejection_basis is not None:
            return True
        return decision.stop is None or decision.sizing is None or decision.reward_risk is None
    # المرفوض موثق الأساس ولا نية له
    if decision.rejection_basis is None or decision.order_intent is not None:
        return True
    if decision.rejection_basis.value == "HARD_BLOCK" and not decision.hard_blocks:
        return True
    return decision.rejection_basis.value == "SOFT_SUPPRESSED" and not decision.soft_suppressions
