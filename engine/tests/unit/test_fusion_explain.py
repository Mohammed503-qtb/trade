"""اختبارات كائن التفسير (§2.8) — المشتق قبل الممرر والتأجيل المعلن.

العقود المفحوصة:

- الحقول العشرة حرفيًا بترتيب §2.8 (عقد المخطط نفسه)؛
- الاشتقاق من اللقطة والسجل: سلسلتا المساندة والمعارضة سطر لكل دليل
  بنوعه ومصدره ومساهمته الموقعة (تطابق compute.contribution رقمًا) —
  والمعارضة الصريحة §19.5 تظهر في الحقل المخصص لها؛
- السياق: من لقطة الحالة الممررة (نظام/تقلب/جودة/انحياز) وبغيابها
  إعلان صريح لا صمت؛
- التأجيلات المعلنة: المشغل والإبطال والمسار (المرحلة 7 — D-04)
  والتكاليف (المرحلة 8 — §25.2) نصوص موثقة لا فراغ؛ والممرر الصريح
  يتقدم الاشتقاق والتأجيل معًا؛
- الاكتمال الآلي (6.5): كل تفسير مبني يمر validate_explanation_completeness
  في وضعَي القبول والرفض، وrejection_reason يمرر كما هو؛
- الحتمية: تفسيران من المدخلات نفسها ⇒ JSON متطابق بايت-بايت.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fusion.compute import FusionEngine, contribution
from fusion.explain import build_explanation
from schemas import (
    DataQuality,
    Direction,
    EventType,
    EvidenceGroup,
    EvidenceRecord,
    FusionSnapshot,
    HTFBias,
    MarketRegime,
    MarketStateSnapshot,
    validate_explanation_completeness,
)

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"


def _record(
    evidence_id: str,
    *,
    direction_score: float = 1.0,
    opposition: bool = False,
    group: EvidenceGroup = EvidenceGroup.STRUCTURE,
    event_type: EventType = EventType.EXTERNAL_BOS,
    prior_weight: float = 1.0,
    raw_strength: float = 0.5,
    freshness: float = 0.8,
    event_time: datetime = T0,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        event_time=event_time,
        group=group,
        event_type=event_type,
        direction_score=direction_score,
        raw_strength=raw_strength,
        quality=1.0,
        freshness=freshness,
        independence_discount=1.0,
        prior_weight=prior_weight,
        context_modifier=1.0,
        opposition=opposition,
        source="unit-test",
    )


def _snapshot_and_records(
    *, with_opposition: bool = True
) -> tuple[FusionSnapshot, list[EvidenceRecord]]:
    """لقطة نموذجية: مساندة بنية وتدفق ومعارضة إنهاك (اختيارية)."""
    records = [
        _record("ev-bos"),
        _record(
            "ev-flow",
            group=EvidenceGroup.ORDER_FLOW,
            event_type=EventType.ABSORPTION_BUY,
            prior_weight=0.9,
            freshness=1.0,
        ),
    ]
    if with_opposition:
        records.append(
            _record(
                "ev-exhaustion",
                direction_score=-0.6,
                opposition=True,
                group=EvidenceGroup.ORDER_FLOW,
                event_type=EventType.EXHAUSTION_UP,
                prior_weight=0.65,
                raw_strength=0.4,
            )
        )
    snapshot = FusionEngine().compute(
        records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
    )
    return snapshot, records


def _state() -> MarketStateSnapshot:
    return MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe="1h",
        event_time=T0,
        regime=MarketRegime.TREND_PULLBACK,
        htf_bias=HTFBias.BULLISH,
        volatility_percentile=35.5,
        data_quality=DataQuality.HEALTHY,
    )


# ───────────────────── الاشتقاق من اللقطة والسجل ─────────────────────


class TestDerivedContent:
    """سلسلتا الدليل والسياق — مشتقة حتمية من المدخلات."""

    def test_evidence_lines_match_contributions(self) -> None:
        """كل سطر يحمل المساهمة الموقعة المطابقة لمعادلة §19.2."""
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records)
        by_prefix = {line.split(" [")[0]: line for line in explanation.supporting_evidence}
        assert "EXTERNAL_BOS" in by_prefix
        assert "ABSORPTION_BUY" in by_prefix
        bos = next(r for r in records if r.event_type is EventType.EXTERNAL_BOS)
        assert f"c_i={contribution(bos):+.4f}" in by_prefix["EXTERNAL_BOS"]

    def test_opposition_listed_explicitly(self) -> None:
        """قائمة المعارضة الصريحة (§19.5) في حقلها المخصص."""
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records)
        (opposing,) = explanation.opposing_evidence
        assert opposing.startswith("EXHAUSTION_UP")
        exhaustion = next(r for r in records if r.event_type is EventType.EXHAUSTION_UP)
        assert f"c_i={contribution(exhaustion):+.4f}" in opposing
        # والمساندة لا تختلط بها
        assert all(not line.startswith("EXHAUSTION") for line in explanation.supporting_evidence)

    def test_market_context_from_state(self) -> None:
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records, market_state=_state())
        assert "TREND_PULLBACK" in explanation.market_context
        assert "35.5" in explanation.market_context
        assert "BULLISH" in explanation.market_context

    def test_market_context_absence_is_explicit(self) -> None:
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records)
        assert "بلا لقطة حالة" in explanation.market_context

    def test_group_summaries_derived(self) -> None:
        """الحالة البنيوية وخريطة السيولة ملخصا مجموعتيهما من اللقطة."""
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records)
        assert "مجموعة البنية" in explanation.structural_state
        assert "مجموعة السيولة/الموقع" in explanation.liquidity_map
        # السيولة غائبة ⇒ الملخص يعلن الغياب وإعادة التوزيع
        assert "غائبة" in explanation.liquidity_map

    def test_empty_ledger_explanation(self) -> None:
        """سجل فارغ ⇒ سلسلتان فارغتان وسياقات غياب معلنة — يبقى مكتملاً."""
        snapshot = FusionEngine().compute(
            [], scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        explanation = build_explanation(snapshot, [])
        validate_explanation_completeness(explanation, rejected=False)
        assert explanation.supporting_evidence == ()
        assert explanation.opposing_evidence == ()


# ─────────────────── التأجيلات المعلنة والممرر الصريح ───────────────────


class TestDeferralsAndOverrides:
    """المشتق قبل الممرر — والتأجيل المعلن لا الفراغ الصامت."""

    def test_trigger_invalidation_path_cost_deferred_with_reason(self) -> None:
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(snapshot, records)
        assert "المرحلة 7" in explanation.trigger
        assert "المرحلة 7" in explanation.invalidation
        assert "المرحلة 7" in explanation.expected_path
        assert "المرحلة 8" in explanation.cost_estimate
        assert "§25.2" in explanation.cost_estimate

    def test_explicit_overrides_win(self) -> None:
        snapshot, records = _snapshot_and_records()
        explanation = build_explanation(
            snapshot,
            records,
            market_context="نطاق يومي متوازن",
            liquidity_map="قاع معبَّد 94.0 وقمة غير مختبرة 110.0",
            structural_state="بنية صاعدة مؤكدة",
            trigger="استرجاع 99.0 بإغلاق",
            invalidation="إغلاق دون 94.0",
            expected_path="نحو 110.0",
            cost_estimate="0.4R لكل صفقة",
        )
        assert explanation.market_context == "نطاق يومي متوازن"
        assert explanation.liquidity_map.startswith("قاع معبَّد")
        assert explanation.trigger == "استرجاع 99.0 بإغلاق"
        assert explanation.cost_estimate == "0.4R لكل صفقة"

    def test_rejection_reason_passthrough(self) -> None:
        snapshot, records = _snapshot_and_records()
        rejected = build_explanation(
            snapshot, records, rejection_reason="المشغل لم يتحقق قبل انتهاء الصلاحية"
        )
        assert rejected.rejection_reason == "المشغل لم يتحقق قبل انتهاء الصلاحية"


# ───────────────────── الاكتمال والحتمية ─────────────────────


class TestCompletenessAndDeterminism:
    """كل تفسير مبني مكمل — والبناء حتمي بايت-بايت."""

    @pytest.mark.parametrize("with_opposition", [True, False])
    @pytest.mark.parametrize("rejected", [True, False])
    def test_every_built_explanation_passes_completeness(
        self, with_opposition: bool, rejected: bool
    ) -> None:
        snapshot, records = _snapshot_and_records(with_opposition=with_opposition)
        explanation = build_explanation(
            snapshot,
            records,
            market_state=_state(),
            rejection_reason="مرفوض للفحص" if rejected else None,
        )
        validate_explanation_completeness(explanation, rejected=rejected)

    def test_determinism_byte_for_byte(self) -> None:
        snapshot, records = _snapshot_and_records()
        first = build_explanation(snapshot, records, market_state=_state())
        second = build_explanation(snapshot, records, market_state=_state())
        assert first.model_dump_json() == second.model_dump_json()

    def test_vetoed_snapshot_explanation_still_complete(self) -> None:
        """اللقطة الممسوسة بحجب تفسَّر كاملة — العلم في اللقطة لا يفرغ
        حقول الشرح (الرفض له سببه الخاص إن أُعطي)."""
        records = [_record("ev-bos")]
        snapshot = FusionEngine().compute(
            records,
            scenario_id="scn",
            direction=Direction.LONG,
            fusion_time=T0,
            veto_reasons=("DATA_STALE",),
        )
        explanation = build_explanation(snapshot, records, rejection_reason="حجب صلب: بيانات راكدة")
        validate_explanation_completeness(explanation, rejected=True)
        assert snapshot.vetoed is True
