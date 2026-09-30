"""محرك حساب الدمج — c_i (§19.2 حرفيًا) ورياضيات D-03 كاملة.

الخطوات الحتمية لكل حساب:

1. **المساهمة الفردية** — ``c_i = prior_weight × direction_score ×
   raw_strength × quality × freshness × independence_discount ×
   context_modifier`` بترتيب عوامل §19.2 نفسه (ترتيب الضرب العائم مثبت
   لضمان حتمية البتات).
2. **العضوية المؤهلة** — العضو المؤهل |c_i| > 0؛ المجموعة الحاضرة لها
   عضو مؤهل واحد على الأقل («أعضائها المؤهلين» D-03-أ).
3. **إعادة التوزيع الحتمية عند الخلو (D-03-ب)** — حصص المجموعات
   الغائبة تُعاد تناسبيًا إلى الحاضرات: ``share'_g = share_g / Σ_present``
   — لا تضخيم بالمجموعات الحاضرة ولا صمت؛ التوقيع يوثق كل شيء.
4. **سقف المجموعة بتشبع tanh (D-03-أ)** — ``score_g = share'_g ×
   tanh(S_g / share'_g)`` حيث S_g مجموع مساهمات الأعضاء المؤهلين
   الموقعة: الدرجة داخل (−share', +share') حتمًا مهما كثر الأعضاء.
5. **الدرجة الخام** — مجموع درجات المجموعات الحاضرة بترتيب §19.3،
   داخل (−1, +1) — «ليست احتمالًا» (§2.6/§19.6).
6. **التناقض (§19.5)** — يسري بإشارة direction_score نفسها: سجل معاكس
   يساهم سالبًا فيخفض الدرجة ولا يلغيها («not a binary cancel»)؛ قائمة
   المعارضة الصريحة تُستخرج للّقطة والتفسير.
7. **الـveto خارج الحساب كليًا (D-03-د)** — أسباب الحجب مدخل بولياني
   مستقل يُعلن في اللقطة ولا يمس أي رقم أعلاه؛ الاستهلاك (منع الترخيص)
   مسؤولية المراحل 7/8.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import tanh

from schemas import (
    CALIBRATION_DEFERRAL_REASON,
    AvailabilitySignature,
    CalibrationReport,
    Direction,
    EvidenceGroup,
    EvidenceRecord,
    FusionSnapshot,
    GroupScore,
)

from .mapping import EVENT_EVIDENCE_GROUPS, GROUP_ORDER, HARD_BLOCK_EVENT_TYPES
from .parameter_sets import FusionConfig

__all__ = ["FusionEngine", "contribution"]


def contribution(record: EvidenceRecord) -> float:
    """c_i — معادلة §19.2 حرفيًا بترتيب عواملها نفسه.

    دالة صرفة معلنة: يعاد استخدامها في الاختبارات والتحقق كمرجع
    للاستقلال عن المحرك (حساب يدوي مقابل حساب المحرك).
    """
    return (
        record.prior_weight
        * record.direction_score
        * record.raw_strength
        * record.quality
        * record.freshness
        * record.independence_discount
        * record.context_modifier
    )


class FusionEngine:
    """محرك الدمج النقي — لا ساعة ولا حالة: نفس المدخلات ⇒ نفس اللقطة.

    الاستخدام: بنِ السجل (``ledger.EvidenceLedgerBuilder``) ثم احسب
    اللقطة عند لحظة قرار صريحة ``fusion_time`` تمرر من المستدعي —
    الطراوة تُختم عند البناء لا هنا (§19.1 حقول المدخلات).
    """

    def __init__(self, config: FusionConfig | None = None) -> None:
        self._config = config if config is not None else FusionConfig()

    @property
    def config(self) -> FusionConfig:
        """الإعداد المجمّد — للقراءة والبصمة والتوثيق."""
        return self._config

    def compute(
        self,
        records: Sequence[EvidenceRecord],
        *,
        scenario_id: str,
        direction: Direction,
        fusion_time: datetime,
        veto_reasons: Sequence[str] = (),
    ) -> FusionSnapshot:
        """لقطة دمج واحدة من سجل دليل كامل.

        :param records: سجلات الدليل بترتيب الإدخال (هوية السلسلة).
        :param scenario_id: هوية السيناريو — تُختم في اللقطة لا تؤثر على
            الحساب (المحرك سيناريو-محايد).
        :param direction: اتجاه السيناريو — موثق في اللقطة (الاصطفاف حدث
            عند البناء عبر إشارة direction_score).
        :param fusion_time: لحظة القرار المرجعية (من المستدعي — لا ساعة
            داخلية).
        :param veto_reasons: أسباب الحجب الصلب — منطق بولياني خارج الحساب
            كليًا (D-03-د): تُعلن ولا تعدل رقمًا.
        """
        self._validate_records(records)

        # ── 1) المساهمات الفردية c_i بترتيب الإدخال ──
        contributions = [contribution(record) for record in records]

        # ── 2) العضوية المؤهلة والإتاحة ──
        qualified: dict[EvidenceGroup, list[float]] = {}
        for record, c_i in zip(records, contributions, strict=True):
            if abs(c_i) > 0.0:
                qualified.setdefault(record.group, []).append(c_i)
        present = tuple(group for group in GROUP_ORDER if group in qualified)
        absent = tuple(group for group in GROUP_ORDER if group not in qualified)

        shares = self._config.group_shares
        default_shares = {group: shares[group] for group in GROUP_ORDER}
        redistributed = sum(shares[group] for group in absent)

        # ── 3) إعادة التوزيع التناسبي الحتمية على الحاضرات (D-03-ب) ──
        total_present = sum(shares[group] for group in present)
        if present and total_present > 0.0:
            effective = {group: shares[group] / total_present for group in present}
        else:
            effective = {}

        # ── 4) سقف كل مجموعة بتشبع tanh (D-03-أ) ──
        group_scores: list[GroupScore] = []
        for group in present:
            share_g = effective[group]
            raw_sum = sum(qualified[group])
            score = share_g * tanh(raw_sum / share_g)
            group_scores.append(
                GroupScore(
                    group=group,
                    qualified_count=len(qualified[group]),
                    raw_sum=raw_sum,
                    effective_share=share_g,
                    score=score,
                )
            )

        # ── 5) الدرجة الخام — مجموع الحاضرات داخل (−1, +1) ──
        raw_evidence_score = sum(item.score for item in group_scores)

        # ── 6) الشفافية الخام والمعارضة الصريحة (§19.5) ──
        support_total = 0.0
        opposition_total = 0.0
        opposition_ids: list[str] = []
        for record, c_i in zip(records, contributions, strict=True):
            if record.opposition:
                opposition_total += abs(c_i)
                opposition_ids.append(record.evidence_id)
            else:
                support_total += abs(c_i)

        signature = AvailabilitySignature(
            present_groups=present,
            absent_groups=absent,
            default_shares=default_shares,
            effective_shares=effective,
            redistributed_share=redistributed,
        )
        return FusionSnapshot(
            scenario_id=scenario_id,
            direction=direction,
            fusion_time=fusion_time,
            group_scores=tuple(group_scores),
            raw_evidence_score=raw_evidence_score,
            support_contribution=support_total,
            opposition_contribution=opposition_total,
            opposition_evidence_ids=tuple(opposition_ids),
            evidence_ids=tuple(record.evidence_id for record in records),
            availability=signature,
            vetoed=bool(veto_reasons),
            veto_reasons=tuple(veto_reasons),
            calibration=CalibrationReport(deferral_reason=CALIBRATION_DEFERRAL_REASON),
        )

    @staticmethod
    def _validate_records(records: Sequence[EvidenceRecord]) -> None:
        """حرس العقود: لا حجب صلب في السجل ومواطن المجموعات متسقة.

        رفض صاخب لا صمت موافقة: دليلٌ لحدث حجب صلب خطأ معماري (D-03-د)،
        وسجلٌ مجموعته تخالف خريطة §19.3 دليل خلل في الباني يُكتشف هنا
        لا في النتائج.
        """
        seen: set[str] = set()
        for record in records:
            if record.event_type in HARD_BLOCK_EVENT_TYPES:
                raise ValueError(
                    f"سجل دليل لحدث حجب صلب {record.event_type} — الحجب "
                    "منطق بولياني خارج الحساب كليًا (D-03-د) ولا يدخل السجل أبدًا"
                )
            expected = EVENT_EVIDENCE_GROUPS[record.event_type]
            if record.group is not expected:
                raise ValueError(
                    f"مجموعة السجل {record.group.name} تخالف خريطة §19.3 "
                    f"({record.event_type.value} ⇒ {expected.name}) — خلل باني السجل"
                )
            if record.evidence_id in seen:
                raise ValueError(f"معرف دليل مكرر في المدخلات: {record.evidence_id}")
            seen.add(record.evidence_id)
