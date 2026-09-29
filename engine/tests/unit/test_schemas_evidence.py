"""اختبارات عقود مخرجات الدمج (§19.2-6 + D-03) وكائن التفسير (§2.8).

العقود المفحوصة:

- round-trip JSON كامل للقطة الدمج بشجرتها المتداخلة (توقيع الإتاحة
  ودرجات المجموعات وتقرير المعايرة)؛
- الجمود (frozen) ومنع الحقول الغريبة (extra="forbid") لكل النماذج
  الخمسة الجديدة؛
- حدود الأنواع: raw_evidence_score وeffective_share داخل الوحدة؛
- تقرير المعايرة §19.6: البنية الافتراضية (غير مؤهل + سبب موثق) والحقول
  الرقمية صفرية والاحتمال غائب — «الدرجة الخام ليست احتمالًا»؛
- كائن التفسير §2.8: الحقول العشرة حرفيًا والفحص الآلي للاكتمال
  (الحقول الفارغة تُرفض، وrejection_reason إلزامي عند الرفض وممنوع
  بلا رفض)؛
- التسجيل في المُصدّر: النماذج الخمسة في ALL_MODELS وgenerated/ بفهارسها
  ومراجع خطتها.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from schemas import (
    CALIBRATION_DEFERRAL_REASON,
    AvailabilitySignature,
    CalibrationReport,
    Direction,
    EventType,
    EvidenceGroup,
    EvidenceRecord,
    ExplanationObject,
    FusionSnapshot,
    GroupScore,
    validate_explanation_completeness,
)
from schemas.export import ALL_MODELS, GENERATED_DIR, MODEL_PLAN_REFS

# ───────────────────────── أدوات البناء ─────────────────────────


T0 = datetime(2026, 1, 5, tzinfo=UTC)


def _signature(*, single: bool = True) -> AvailabilitySignature:
    """توقيع إتاحة نموذجي — بنية واحدة حاضرة أو مجموعتان."""
    if single:
        present: tuple[EvidenceGroup, ...] = (EvidenceGroup.ORDER_FLOW,)
        absent = tuple(g for g in EvidenceGroup if g not in present)
        default = {EvidenceGroup.ORDER_FLOW: 0.30}
        default.update(dict.fromkeys(absent, 0.14))
        effective = {EvidenceGroup.ORDER_FLOW: 1.0}
        return AvailabilitySignature(
            present_groups=present,
            absent_groups=absent,
            default_shares=default,
            effective_shares=effective,
            redistributed_share=0.70,
        )
    present = (EvidenceGroup.STRUCTURE, EvidenceGroup.ORDER_FLOW)
    absent = tuple(g for g in EvidenceGroup if g not in present)
    shares = dict.fromkeys(EvidenceGroup, 1.0 / 6.0)
    return AvailabilitySignature(
        present_groups=present,
        absent_groups=absent,
        default_shares=shares,
        effective_shares={
            EvidenceGroup.STRUCTURE: 0.45454545454545453,
            EvidenceGroup.ORDER_FLOW: 0.5454545454545454,
        },
        redistributed_share=4.0 / 6.0,
    )


def _group_score(share: float = 1.0) -> GroupScore:
    return GroupScore(
        group=EvidenceGroup.ORDER_FLOW,
        qualified_count=2,
        raw_sum=1.4,
        effective_share=share,
        score=share * 0.8853514824212007,
    )


def _snapshot(**overrides: object) -> FusionSnapshot:
    snapshot: dict[str, object] = {
        "scenario_id": "scn-verify",
        "direction": Direction.LONG,
        "fusion_time": T0,
        "group_scores": (_group_score(),),
        "raw_evidence_score": 0.8853514824212007,
        "support_contribution": 1.4,
        "opposition_contribution": 0.0,
        "opposition_evidence_ids": (),
        "evidence_ids": ("ev-1", "ev-2"),
        "availability": _signature(),
        "vetoed": False,
        "veto_reasons": (),
        "calibration": CalibrationReport(deferral_reason=CALIBRATION_DEFERRAL_REASON),
    }
    snapshot.update(overrides)
    return FusionSnapshot(**snapshot)  # type: ignore[arg-type]


def _explanation(**overrides: object) -> ExplanationObject:
    explanation: dict[str, object] = {
        "market_context": "نطاق متوازن، تقلب مئينه 42",
        "liquidity_map": "قاع الدفاع 94.0 معبَّد، قمة 110.0 غير مختبرة",
        "structural_state": "بنية صاعدة بكسر خارجي مؤكد",
        "supporting_evidence": ("EXTERNAL_BOS c_i=+0.42",),
        "opposing_evidence": ("EXHAUSTION_UP c_i=-0.10",),
        "trigger": "استرجاع منطقة 99.0-100.0 وإغلاق فوقها",
        "invalidation": "إغلاق دون 94.0 بهامش تقلب",
        "expected_path": "نحو 110.0 ثم التمدد 115.0",
        "cost_estimate": "مؤجل حتى المرحلة 8 (§25.2) — لا تقدير تكاليف بعد",
        "rejection_reason": None,
    }
    explanation.update(overrides)
    return ExplanationObject(**explanation)  # type: ignore[arg-type]


# ───────────────────────── العقود ─────────────────────────


class TestFusionSnapshotContract:
    """اللقطة الجميلة: شجرة كاملة، جمود، حدود، وتوقيع إتاحة صادق."""

    def test_round_trip_json_full_tree(self) -> None:
        snapshot = _snapshot()
        restored = FusionSnapshot.model_validate_json(snapshot.model_dump_json())
        assert restored == snapshot
        assert restored.availability.effective_shares[EvidenceGroup.ORDER_FLOW] == 1.0
        assert restored.group_scores[0].group is EvidenceGroup.ORDER_FLOW

    def test_frozen_and_forbid_extra(self) -> None:
        snapshot = _snapshot()
        with pytest.raises(ValidationError, match="frozen"):
            snapshot.raw_evidence_score = 0.5  # type: ignore[misc]
        with pytest.raises(ValidationError, match="extra_forbidden"):
            FusionSnapshot.model_validate({**snapshot.model_dump(), "magic_boost": 0.9})

    def test_signed_unit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            _snapshot(raw_evidence_score=1.5)
        with pytest.raises(ValidationError):
            _snapshot(raw_evidence_score=-1.5)
        # الحدود المغلقة جائزة: ±1 داخل العقد
        assert _snapshot(raw_evidence_score=1.0).raw_evidence_score == 1.0

    def test_non_negative_contribution_totals(self) -> None:
        with pytest.raises(ValidationError):
            _snapshot(support_contribution=-0.1)
        with pytest.raises(ValidationError):
            _snapshot(opposition_contribution=-0.001)

    def test_evidence_chain_order_preserved(self) -> None:
        """ترتيب السلسلة والمعارضة مصفوفتان — ترتيب الوصول هو هوية اللقطة."""
        snapshot = _snapshot(evidence_ids=("a", "b", "c"), opposition_evidence_ids=("b",))
        assert tuple(snapshot.evidence_ids) == ("a", "b", "c")
        assert tuple(snapshot.opposition_evidence_ids) == ("b",)


class TestAvailabilityAndGroupScore:
    """توقيع الإتاحة ودرجة المجموعة — D-03 بشفافية رقمية كاملة."""

    def test_signature_round_trip_and_fields(self) -> None:
        signature = _signature(single=False)
        restored = AvailabilitySignature.model_validate_json(signature.model_dump_json())
        assert restored == signature
        assert set(restored.effective_shares) == set(restored.present_groups)
        assert set(restored.default_shares) == set(EvidenceGroup)

    def test_group_score_share_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GroupScore(
                group=EvidenceGroup.STRUCTURE,
                qualified_count=1,
                raw_sum=0.5,
                effective_share=1.2,
                score=0.5,
            )

    def test_group_score_frozen(self) -> None:
        score = _group_score()
        with pytest.raises(ValidationError, match="frozen"):
            score.raw_sum = 2.0  # type: ignore[misc]


class TestCalibrationReport:
    """§19.6 — البنية الآن، والملء مشروط ببيانات OOS كافية (المرحلة 9)."""

    def test_defaults_are_deferred_not_silent(self) -> None:
        report = CalibrationReport(deferral_reason=CALIBRATION_DEFERRAL_REASON)
        assert report.eligible is False
        assert report.calibrated_probability is None
        assert report.calibration_sample_size == 0
        assert report.calibration_regime is None
        assert "المرحلة 9" in report.deferral_reason

    def test_deferral_reason_required(self) -> None:
        with pytest.raises(ValidationError):
            CalibrationReport()  # type: ignore[call-arg]

    def test_deferral_constant_documents_reason(self) -> None:
        """الثابت القانوني يمنع تفرق الصياغات — ويذكر شرط §19.6 صريحًا."""
        assert "خارج العينة" in CALIBRATION_DEFERRAL_REASON
        assert len(CALIBRATION_DEFERRAL_REASON.strip()) > 20


class TestExplanationObject:
    """§2.8 حرفيًا — عشرة حقول بترتيب النص والفحص الآلي للاكتمال."""

    def test_ten_fields_literal(self) -> None:
        explanation = _explanation()
        expected = (
            "market_context",
            "liquidity_map",
            "structural_state",
            "supporting_evidence",
            "opposing_evidence",
            "trigger",
            "invalidation",
            "expected_path",
            "cost_estimate",
            "rejection_reason",
        )
        assert tuple(type(explanation).model_fields) == expected

    def test_completeness_passes_when_full(self) -> None:
        validate_explanation_completeness(_explanation(), rejected=False)
        validate_explanation_completeness(
            _explanation(rejection_reason="مشغل لم يتحقق قبل انتهاء الصلاحية"),
            rejected=True,
        )

    def test_empty_text_field_rejected(self) -> None:
        with pytest.raises(ValueError, match="market_context"):
            validate_explanation_completeness(_explanation(market_context="  "), rejected=False)

    @pytest.mark.parametrize(
        "field",
        [
            "liquidity_map",
            "structural_state",
            "trigger",
            "invalidation",
            "expected_path",
            "cost_estimate",
        ],
    )
    def test_any_empty_field_rejected(self, field: str) -> None:
        with pytest.raises(ValueError, match=field):
            validate_explanation_completeness(_explanation(**{field: ""}), rejected=False)

    def test_rejection_requires_reason(self) -> None:
        with pytest.raises(ValueError, match="rejection_reason"):
            validate_explanation_completeness(_explanation(), rejected=True)

    def test_reason_without_rejection_rejected(self) -> None:
        """التوثيق الصادق لا يخترع رفضًا — السبب بلا رفض تلوث."""
        with pytest.raises(ValueError, match="بلا رفض"):
            validate_explanation_completeness(
                _explanation(rejection_reason="رفض غير موجود"), rejected=False
            )

    def test_round_trip_and_frozen(self) -> None:
        explanation = _explanation()
        restored = ExplanationObject.model_validate_json(explanation.model_dump_json())
        assert restored == explanation
        with pytest.raises(ValidationError, match="frozen"):
            explanation.trigger = "آخر"  # type: ignore[misc]


class TestExportRegistration:
    """«لا رسالة بلا مخطط مُصدَّر» — النماذج الخمسة مسجلة ومولدة."""

    @pytest.mark.parametrize(
        ("model_name", "plan_ref"),
        [
            ("AvailabilitySignature", "D-03"),
            ("GroupScore", "D-03"),
            ("CalibrationReport", "§19.6"),
            ("FusionSnapshot", "§19.2-5 + D-03"),
            ("ExplanationObject", "§2.8"),
        ],
    )
    def test_registered_with_plan_ref(self, model_name: str, plan_ref: str) -> None:
        assert model_name in ALL_MODELS
        assert plan_ref in MODEL_PLAN_REFS[model_name]
        assert (GENERATED_DIR / f"{model_name}.schema.json").is_file()

    def test_index_lists_all_five(self) -> None:
        index = json.loads((GENERATED_DIR / "index.json").read_text(encoding="utf-8"))
        for model_name in (
            "AvailabilitySignature",
            "GroupScore",
            "CalibrationReport",
            "FusionSnapshot",
            "ExplanationObject",
        ):
            assert model_name in index

    def test_evidence_record_untouched(self) -> None:
        """§19.1 لم يُمس — الحقول الأربعة عشر كما كانت في المرحلة 0."""
        record = EvidenceRecord(
            evidence_id="ev-x",
            group=EvidenceGroup.MACRO,
            event_type=EventType.MACRO_HIGH_IMPACT_NEAR,
            direction_score=0.0,
            raw_strength=0.5,
            quality=1.0,
            freshness=1.0,
            independence_discount=1.0,
            prior_weight=0.0,
            context_modifier=1.0,
            opposition=False,
            source="test",
        )
        assert record.correlation_group_id is None
