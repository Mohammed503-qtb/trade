"""دورة حياة السيناريو (§18.2) — آلة انتقالات غير قابلة للتخريب.

«Immutable lifecycle transitions» (§31.3) فوق خريطة الانتقالات القانونية
للحالات الاثنتي عشرة: الدرب الأساسي السبعي والنهايات الست البديلة.

الحصانة المعمارية للخصائص (§38.2):

- **لا عودة من حالة نهائية أبدًا** — الست النهائيات (COMPLETED و
  INVALIDATED وEXPIRED وSUPPRESSED وREJECTED_BY_RISK و
  CANCELLED_BY_DATA_QUALITY) بلا صادرة إطلاقًا: «The scenario cannot
  be "rescued" by inventing new evidence after invalidation. A new
  scenario must be opened» (§18.5) — لا إنقاذ، سيناريو جديد يُفتح.
- **كل انتقال غير قانوني يُرفض صاخبًا** — ValueError باسم الحالتين،
  لا تجاهل صامت ولا «أفضل جهد».
- **السجل ملحق-فقط**: كل تحوّل يُرجع نسخة سيناريو جديدة مجمّدة
  (الطفرة الصامتة مستحيلة — ``Scenario`` frozen) + سجل انتقال موثق
  السبب والوقت.

ما بعد TRIGGERED (AUTHORIZED فما فوق) تقودها المراحل 8+ (المخاطرة
فالتنفيذ) — الآلة تعرف خريطتها كاملة لكن محرك المرحلة 7 يقود حتى
TRIGGERED فالنهايات (بوابة الخروج 7: لا ترخيص بلا مشغل وإبطال
معرّفين).
"""

from __future__ import annotations

from datetime import datetime

from schemas import Scenario, ScenarioState, ScenarioTransition

__all__ = [
    "LEGAL_TRANSITIONS",
    "TERMINAL_STATES",
    "IllegalTransitionError",
    "apply_transition",
    "is_terminal",
    "validate_transition",
]


class IllegalTransitionError(ValueError):
    """انتقال دورة حياة غير قانوني — رفض صاخب لا تصحيح صامت (§38.2)."""

    def __init__(self, from_state: ScenarioState, to_state: ScenarioState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"انتقال غير قانوني لدورة الحياة: {from_state.value} → {to_state.value} — "
            "خريطة §18.2 ملزمة: القانونية من هذه الحالة حصرًا "
            f"{sorted(s.value for s in LEGAL_TRANSITIONS[from_state])}"
        )


#: الحالات النهائية الست — بلا صادرة أبدًا (§18.2 نهايات بديلة).
TERMINAL_STATES: frozenset[ScenarioState] = frozenset(
    {
        ScenarioState.COMPLETED,
        ScenarioState.INVALIDATED,
        ScenarioState.EXPIRED,
        ScenarioState.SUPPRESSED,
        ScenarioState.REJECTED_BY_RISK,
        ScenarioState.CANCELLED_BY_DATA_QUALITY,
    }
)


#: خريطة الانتقالات القانونية — الدرب الأساسي §18.2 + النهايات البديلة.
#: النطاق الدلالي الموثق:
#: - الإبطال/الانقضاء/جودة البيانات يصحان قبل الترخيص كافة (DRAFT
#:   وما بعده) — سيناريو مسودته ميتة قبل ترقيته يُطفأ لا يُنقذ.
#: - SUPPRESSED قرار تنافس (7.4) على الترخيص حصرًا: ما تجاوز
#:   TRIGGERED تجاوز خط الترخيص فلا يُكتم صامتًا.
#: - EXPIRED نافذة الترخيص (D-04 الزعنفة): حتى TRIGGERED بانتظار
#:   المخاطرة؛ ما بعد الترخيص يملك التنفيذ/الإدارة (§24/§34) مآله.
LEGAL_TRANSITIONS: dict[ScenarioState, frozenset[ScenarioState]] = {
    ScenarioState.DRAFT: frozenset(
        {
            ScenarioState.ACTIVE,
            ScenarioState.INVALIDATED,
            ScenarioState.EXPIRED,
            ScenarioState.SUPPRESSED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    ScenarioState.ACTIVE: frozenset(
        {
            ScenarioState.TRIGGERED,
            ScenarioState.INVALIDATED,
            ScenarioState.EXPIRED,
            ScenarioState.SUPPRESSED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    ScenarioState.TRIGGERED: frozenset(
        {
            ScenarioState.AUTHORIZED,
            ScenarioState.REJECTED_BY_RISK,
            ScenarioState.INVALIDATED,
            ScenarioState.EXPIRED,
            ScenarioState.SUPPRESSED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    ScenarioState.AUTHORIZED: frozenset(
        {
            ScenarioState.EXECUTING,
            ScenarioState.INVALIDATED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    ScenarioState.EXECUTING: frozenset(
        {
            ScenarioState.IN_TRADE,
            ScenarioState.INVALIDATED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    ScenarioState.IN_TRADE: frozenset(
        {
            ScenarioState.COMPLETED,
            ScenarioState.INVALIDATED,
            ScenarioState.CANCELLED_BY_DATA_QUALITY,
        }
    ),
    # ── النهائيات الست: لا صادرة أبدًا (لا إنقاذ — §18.5) ──
    ScenarioState.COMPLETED: frozenset(),
    ScenarioState.INVALIDATED: frozenset(),
    ScenarioState.EXPIRED: frozenset(),
    ScenarioState.SUPPRESSED: frozenset(),
    ScenarioState.REJECTED_BY_RISK: frozenset(),
    ScenarioState.CANCELLED_BY_DATA_QUALITY: frozenset(),
}


def is_terminal(state: ScenarioState) -> bool:
    """هل الحالة نهائية؟ — بلا صادرة بعدها أبدًا."""
    return state in TERMINAL_STATES


def validate_transition(from_state: ScenarioState, to_state: ScenarioState) -> None:
    """فحص قانونية انتقال — صاخب عند المخالفة (§38.2 حتمًا).

    :raises IllegalTransitionError: من نهائية (لا إنقاذ §18.5) أو إلى
        غير قانونية من الحالة الحالية.
    """
    if from_state in TERMINAL_STATES:
        raise IllegalTransitionError(from_state, to_state)
    if to_state not in LEGAL_TRANSITIONS[from_state]:
        raise IllegalTransitionError(from_state, to_state)


def apply_transition(
    scenario: Scenario,
    to_state: ScenarioState,
    *,
    transition_time: datetime,
    reason: str,
) -> tuple[Scenario, ScenarioTransition]:
    """تنفيذ انتقال واحد — نسخة جديدة مجمّدة + سجل موثق.

    النموذج مجمّد (``frozen=True``) فالتحديث نسخة ``model_copy`` معرفة
    الحالة الجديدة — الطفرة الصامتة مستحيلة معماريًا. السبب إلزامي
    غير فارغ: لا انتقال بلا توثيق (§31.3 «with timestamp and reason»).

    :returns: (السيناريو الجديد بالحالة الجديدة، سجل الانتقال).
    :raises IllegalTransitionError: انتقال غير قانوني.
    """
    if not reason.strip():
        raise ValueError("سبب الانتقال فارغ — لا انتقال بلا توثيق سبب (§31.3)")
    validate_transition(scenario.state, to_state)
    updated = scenario.model_copy(update={"state": to_state})
    record = ScenarioTransition(
        scenario_id=scenario.scenario_id,
        from_state=scenario.state,
        to_state=to_state,
        transition_time=transition_time,
        reason=reason,
    )
    return updated, record
