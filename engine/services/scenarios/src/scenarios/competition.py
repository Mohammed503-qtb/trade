"""التنافس (7.4) — الحسم بالأسبقية الحتمية لا الإلغاء الصامت.

«Scenario-first reasoning» (§2.5) يعني أن تفسيرات منافسة تتعايش حتى
يلزم القرار؛ وعندما يشتغل اثنان متضادا الاتجاه معًا (كلاهما TRIGGERED
لنفس الأداة — كلاهما يريد الترخيص الآن) يُحسم التنافس بأسبقية معلنة
لا بإسكات طرف:

- **مفتاح الأسبقية** (ترتيب كلي حتمي): عدد المجموعات الداعمة تنازليًا،
  ثم الدرجة تنازليًا، ثم ``scenario_id`` تصاعديًا (كسر التعادل
  المعجمي — نفس مفتاح ترتيب أهداف §10.5).
- **الخاسر يعلن لا يُسكَت**: ينتقل إلى ``SUPPRESSED`` بسبب صريح يسمي
  الفائزَ ومفتاحَ الأسبقية — سجل قابل للتدقيق (§31.3) لا اختفاء.
- **الناجي شرط غياب الأعلى**: سيناريو يُكتم إذا وفقط إذا وُجد معارض
  أدنى مفتاحًا — القرار في أزواج فموضوعي تمامًا.

السؤال «من يقود الصفقة» يظل ملك المرحلة 8 (المخاطرة قد ترفض الناجي
أصلًا)؛ هنا يُحسم أي التفسيرين يملك أولوية الترخيص فقط.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from schemas import Scenario

__all__ = ["CompetingScenario", "CompetitionOutcome", "precedence_key", "resolve_conflicts"]


@dataclass(frozen=True)
class CompetingScenario:
    """سيناريو متنافس بمفتاح أسبقيته — المجموعات الداعمة من لقطة دمجه.

    ``supporting_groups`` عدد مجموعات الدليل الداعمة (درجتها الصافية
    موجبة) عند لحظة القرار — من ``group_scores`` اللقطة لا من عدّ
    السجلات (الاستقلالية شأن الدمج §19.4).
    """

    scenario: Scenario
    supporting_groups: int

    @property
    def score(self) -> float:
        """درجة السيناريو الموثقة (§18.1 — ليست احتمالًا §2.6)."""
        return float(self.scenario.scenario_score)


def precedence_key(competing: CompetingScenario) -> tuple[int, float, str]:
    """مفتاح الأسبقية الكلي — الأصغر يفوز.

    (−المجموعات الداعمة، −الدرجة، المعرف المعجمي): الأكثر تأييدًا
    بالنوع المستقل أولًا، ثم الأعلى درجة، ثم المعرف الأصغر حتمًا —
    لا قرعة ولا ترتيب وصول.
    """
    return (-competing.supporting_groups, -competing.score, competing.scenario.scenario_id)


@dataclass(frozen=True)
class CompetitionOutcome:
    """حصيلة حل تنافس واحد — المكتيتون بأسبابهم المعلنة."""

    #: (الخاسر، الفائز، السبب الصريح) — الخاسر يعلن فائزه ومفتاحه.
    suppressions: tuple[tuple[Scenario, Scenario, str], ...]
    #: الناجون (لم يقهرهم معارض أعلى أسبقية).
    survivors: tuple[Scenario, ...]


def resolve_conflicts(triggered: Sequence[CompetingScenario]) -> CompetitionOutcome:
    """حسم تنافسات المتضادات المتزامنة — TRIGGERED حصرًا مسؤولية المحرك.

    التجميع بالأداة (رمز التداول) ثم الأزواج المتضادة الاتجاه؛ كل عضو
    يُكتم إذا وفقط إذا وُجد معارض أدنى مفتاحًا منه. السبب يسمي الفائز
    وعدديّ المفتاح كاملة — «لا إلغاء صامت» قابلة للتدقيق سجلًا.
    """
    by_symbol: dict[str, list[CompetingScenario]] = {}
    for competing in triggered:
        by_symbol.setdefault(competing.scenario.symbol, []).append(competing)

    suppressions: list[tuple[Scenario, Scenario, str]] = []
    survivors: list[Scenario] = []

    for symbol in sorted(by_symbol):
        group = by_symbol[symbol]
        for competing in group:
            conqueror = _conqueror_of(competing, group)
            if conqueror is None:
                survivors.append(competing.scenario)
            else:
                suppressions.append(
                    (
                        competing.scenario,
                        conqueror.scenario,
                        _suppression_reason(competing, conqueror),
                    )
                )

    return CompetitionOutcome(
        suppressions=tuple(suppressions),
        survivors=tuple(survivors),
    )


def _conqueror_of(
    competing: CompetingScenario, group: Sequence[CompetingScenario]
) -> CompetingScenario | None:
    """أدنى معارضٍ أسبقيةً للسيناريو — None إن لم يقهره أحد.

    المعارضة = الاتجاه المضاد لنفس الأداة فقط؛ الاتجاه الواحد لا
    يتنافس على الترخيص (التعرض محسوب لاحقًا في المخاطرة §23.3).
    """
    best: CompetingScenario | None = None
    for other in group:
        if other is competing:
            continue
        if other.scenario.direction is competing.scenario.direction:
            continue
        if precedence_key(other) < precedence_key(competing) and (
            best is None or precedence_key(other) < precedence_key(best)
        ):
            best = other
    return best


def _suppression_reason(loser: CompetingScenario, winner: CompetingScenario) -> str:
    """سبب الكتم الصريح — يسمي الفائز ومفتاح الأسبقية كاملًا."""
    return (
        "تنافس الترخيص حُسم بالأسبقية (7.4): المعارض "
        f"{winner.scenario.scenario_id} ({winner.scenario.template.value} "
        f"{winner.scenario.direction.value}) أدنى مفتاحًا — مجموعات داعمة "
        f"{winner.supporting_groups} مقابل {loser.supporting_groups} ودرجة "
        f"{winner.score:.4f} مقابل {loser.score:.4f} — لا إلغاء صامت"
    )
