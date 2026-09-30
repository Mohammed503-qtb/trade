"""اختبارات محرك حساب الدمج — c_i (§19.2) ورياضيات D-03 كاملة.

العقود المفحوصة:

- c_i حرفيًا: دالة المساهمة المستقلة تحسب بترتيب عوامل §19.2 نفسه بقيمة
  يدوية (0.05 من معاملات مميزة)؛
- سقف tanh (D-03-أ): خمسون مساهمة كاملة في مجموعة واحدة لا ترفع
  درجتها فوق حصتها أبدًا — والدرجة الخام داخل (−1, +1) دائمًا؛
- إعادة التوزيع الحتمية (D-03-ب): الخلو يوزع الحصة تناسبيًا على
  الحاضرات (واحدة ⇒ 1.0، اثنتان ⇒ نسبتَي 0.25/0.30) والتوقيع يوثق
  الحاضرات والغائبات والمُعاد توزيعه؛
- حقنة الدفعة الواحدة (§19.4): أربعة أدلة مترابطة بخصم γ الهندسي
  ترفع المجموعة أقل من رفعها بلا خصم — والسقف محتوم دونهما؛
- التناقض (§19.5): يخفض ولا يلغي — سجل معاكس يقلب جزءًا من المجموع
  ويُدرج في قائمة المعارضة الصريحة، والمعارضة الساحقة تقلب الدرجة
  سالبة لا تصفرها؛
- الـveto خارج الحساب (D-03-د): اللقطة الممسوسة بالحجب تطابق أختها
  الخالية منه رقمًا برقم وتختلف في العلم البولياني وحده؛
- الحتمية: حسابان من المدخلات نفسها ⇒ JSON متطابق بايت-بايت؛
- الحرس: حدث الحجب الصلب في السجل يُرفض، ومجموعة تخالف خريطة §19.3
  تُرفض، والمعرف المكرر يُرفض؛
- إعداد D-03 المُصدَّر: الحصص الست حرفية من §19.3 والمدقق يرفض الناقص
  والمنحرف، والبصمة حتمية تتغير بأي قيمة تدخل الحساب.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from fusion.compute import FusionEngine, contribution
from fusion.parameter_sets import FusionConfig
from pydantic import ValidationError
from schemas import (
    CALIBRATION_DEFERRAL_REASON,
    Direction,
    EventType,
    EvidenceGroup,
    EvidenceRecord,
)

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _record(
    evidence_id: str,
    *,
    group: EvidenceGroup = EvidenceGroup.STRUCTURE,
    event_type: EventType = EventType.EXTERNAL_BOS,
    direction_score: float = 1.0,
    raw_strength: float = 1.0,
    quality: float = 1.0,
    freshness: float = 1.0,
    independence_discount: float = 1.0,
    prior_weight: float = 1.0,
    context_modifier: float = 1.0,
    opposition: bool = False,
) -> EvidenceRecord:
    """سجل دليل مباشر — معاملات مميزة القيم لحساب يدوي نظيف."""
    return EvidenceRecord(
        evidence_id=evidence_id,
        group=group,
        event_type=event_type,
        direction_score=direction_score,
        raw_strength=raw_strength,
        quality=quality,
        freshness=freshness,
        independence_discount=independence_discount,
        prior_weight=prior_weight,
        context_modifier=context_modifier,
        opposition=opposition,
        source="unit-test",
    )


def _flow_record(evidence_id: str, **kwargs: object) -> EvidenceRecord:
    """سجل في مجموعة التدفق (النوع الموافق للخريطة)."""
    kwargs.setdefault("event_type", EventType.ABSORPTION_BUY)
    return _record(evidence_id, group=EvidenceGroup.ORDER_FLOW, **kwargs)  # type: ignore[arg-type]


# ───────────────────────── c_i — §19.2 حرفيًا ─────────────────────────


class TestContributionFormula:
    """المعادلة حرفية بترتيب عواملها — قيمة يدوية مميزة."""

    def test_literal_formula_hand_value(self) -> None:
        record = _record(
            "ev-math",
            prior_weight=0.8,
            direction_score=1.0,
            raw_strength=0.5,
            quality=0.5,
            freshness=0.5,
            independence_discount=0.5,
            context_modifier=1.0,
        )
        # 0.8 × 1 × 0.5 × 0.5 × 0.5 × 0.5 × 1 = 0.05 بالضبط
        assert contribution(record) == pytest.approx(0.05)
        assert pytest.approx(contribution(record)) == 0.8 * 1.0 * 0.5 * 0.5 * 0.5 * 0.5 * 1.0

    def test_zero_factor_zeroes_contribution(self) -> None:
        """أي عامل صفري (وزن كلي، اتجاه محايد، طراوة ميتة) يقتل المساهمة."""
        record = _record("ev-zero-prior", prior_weight=0.0)
        assert contribution(record) == 0.0
        record = _record("ev-zero-direction", direction_score=0.0)
        assert contribution(record) == 0.0
        record = _record("ev-zero-strength", raw_strength=0.0)
        assert contribution(record) == 0.0
        record = _record("ev-zero-freshness", freshness=0.0)
        assert contribution(record) == 0.0

    def test_negative_direction_negative_contribution(self) -> None:
        """سجل معاكس (direction_score سالب) يساهم سالبًا — إشارة §19.5."""
        record = _record("ev-opp", direction_score=-0.5, prior_weight=0.8, raw_strength=0.5)
        assert contribution(record) == pytest.approx(-0.2)


# ───────────────────────── سقف tanh — D-03-أ ─────────────────────────


class TestTanhGroupCap:
    """درجة المجموعة داخل حصتها مهما كثر الأعضاء أو ضخمت مساهماتهم."""

    def test_fifty_full_contributions_capped(self) -> None:
        """خمسون مساهمة كاملة: المجموعة الوحيدة الحاضرة يرتفع سقفها إلى 1.0
        بإعادة التوزيع (D-03-ب) والتشبع يحميه دونها (tanh < 1 دائمًا)."""
        engine = FusionEngine()
        records = [_flow_record(f"ev-{i}") for i in range(50)]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        (flow,) = snapshot.group_scores
        assert flow.group is EvidenceGroup.ORDER_FLOW
        assert flow.raw_sum == pytest.approx(50.0)
        # المجموعة الوحيدة ⇒ سقفها الفعلي 1.0 بعد إعادة التوزيع
        assert flow.effective_share == pytest.approx(1.0)
        assert flow.score == pytest.approx(1.0 * math.tanh(50.0 / 1.0))
        # tanh < 1 رياضيًا لكنه يتشبع إلى 1.0 بالضبط في float64 عند هذا
        # الحجم — فالعقد «لا تجاوز للسقف» (≤) لا «دون السقء صارمة»
        assert flow.score <= 1.0
        assert snapshot.raw_evidence_score == pytest.approx(flow.score)
        assert snapshot.raw_evidence_score <= 1.0

    def test_cap_is_default_share_when_all_present(self) -> None:
        """المجموعات كلها حاضرة ⇒ سقف كل مجموعة حصتها الافتراضية §19.3:
        خمسون مساهمة تدفقية لا تبلغ 0.30 أبدًا."""
        engine = FusionEngine()
        others = [
            _record("s-1"),
            _record(
                "l-1", group=EvidenceGroup.LIQUIDITY_LOCATION, event_type=EventType.FVG_BULLISH
            ),
            _record(
                "p-1", group=EvidenceGroup.PRICE_ACTION, event_type=EventType.BULLISH_ENGULFING
            ),
            _record(
                "v-1", group=EvidenceGroup.VOLATILITY_SESSION, event_type=EventType.RANGE_EXPANSION
            ),
            _record(
                "m-1",
                group=EvidenceGroup.MACRO,
                event_type=EventType.MACRO_HIGH_IMPACT_NEAR,
                prior_weight=1.0,
            ),
        ]
        records = others + [_flow_record(f"f-{i}") for i in range(50)]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        by_group = {item.group: item for item in snapshot.group_scores}
        flow = by_group[EvidenceGroup.ORDER_FLOW]
        assert flow.effective_share == pytest.approx(0.30)
        assert flow.score == pytest.approx(0.30 * math.tanh(50.0 / 0.30))
        assert flow.score <= 0.30  # التشبع الطافي يبلغ السقف لا يتجاوزه

    def test_cap_is_group_local_not_global(self) -> None:
        """سقف كل مجموعة مستقل: مجموعتان مشبعتان ⇒ الدرجة تقارب مجموع
        سقفيهما الفعالين (0.55 من أصل 1.0) لا تتجاوزه."""
        engine = FusionEngine()
        records = [_record(f"s-{i}") for i in range(20)] + [
            _flow_record(f"f-{i}") for i in range(20)
        ]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        # الحصتان الفعالتان بعد إعادة التوزيع: 0.25/0.55 و0.30/0.55
        by_group = {item.group: item for item in snapshot.group_scores}
        structure = by_group[EvidenceGroup.STRUCTURE]
        flow = by_group[EvidenceGroup.ORDER_FLOW]
        assert structure.effective_share == pytest.approx(0.25 / 0.55)
        assert flow.effective_share == pytest.approx(0.30 / 0.55)
        # مدخلات بهذا الحجم تتشبع tanh إلى 1.0 بالضبط (float64) فتبلغ
        # الدرجة سقفها دون تجاوزه — العقد «لا تجاوز»
        assert structure.score <= structure.effective_share
        assert flow.score <= flow.effective_share
        total = structure.score + flow.score
        assert total == pytest.approx(snapshot.raw_evidence_score)
        assert total <= structure.effective_share + flow.effective_share
        assert total > 0.99  # مجموعتان مشبعتان تقارب سقفيهما

    def test_group_scores_follow_plan_order(self) -> None:
        """ترتيب درجات المجموعات = ترتيب جدول §19.3 لا ترتيب الوصول."""
        engine = FusionEngine()
        records = [
            _flow_record("f-first"),
            _record("s-second"),
        ]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert [item.group for item in snapshot.group_scores] == [
            EvidenceGroup.STRUCTURE,
            EvidenceGroup.ORDER_FLOW,
        ]


# ─────────────────── إعادة التوزيع الحتمية — D-03-ب ───────────────────


class TestDeterministicRedistribution:
    """خلوّ مجموعة يوزع حصتها تناسبيًا — والتوقيع يوثق كل شيء."""

    def test_single_present_group_takes_all(self) -> None:
        engine = FusionEngine()
        snapshot = engine.compute(
            [_flow_record("f-1")],
            scenario_id="scn",
            direction=Direction.LONG,
            fusion_time=T0,
        )
        assert snapshot.availability.present_groups == (EvidenceGroup.ORDER_FLOW,)
        assert len(snapshot.availability.absent_groups) == 5
        assert EvidenceGroup.ORDER_FLOW not in snapshot.availability.absent_groups
        assert snapshot.availability.effective_shares == {
            EvidenceGroup.ORDER_FLOW: pytest.approx(1.0)
        }
        # 0.70 = مجموع حصص الخمس الغائبات (0.25+0.20+0.10+0.10+0.05)
        assert snapshot.availability.redistributed_share == pytest.approx(0.70)
        # الحصص الافتراضية كلها موثقة في التوقيع
        assert snapshot.availability.default_shares[EvidenceGroup.STRUCTURE] == pytest.approx(0.25)

    def test_two_present_groups_proportional(self) -> None:
        engine = FusionEngine()
        snapshot = engine.compute(
            [_record("s-1"), _flow_record("f-1")],
            scenario_id="scn",
            direction=Direction.LONG,
            fusion_time=T0,
        )
        effective = snapshot.availability.effective_shares
        assert effective[EvidenceGroup.STRUCTURE] == pytest.approx(0.25 / 0.55)
        assert effective[EvidenceGroup.ORDER_FLOW] == pytest.approx(0.30 / 0.55)
        assert sum(effective.values()) == pytest.approx(1.0)

    def test_all_present_no_redistribution(self) -> None:
        """المجموعات الست كلها حاضرة ⇒ الفعالة = الافتراضية وصفر معاد توزيعه."""
        engine = FusionEngine()
        records = [
            _record("s-1"),
            _record(
                "l-1",
                group=EvidenceGroup.LIQUIDITY_LOCATION,
                event_type=EventType.FVG_BULLISH,
            ),
            _flow_record("f-1"),
            _record(
                "p-1",
                group=EvidenceGroup.PRICE_ACTION,
                event_type=EventType.BULLISH_ENGULFING,
            ),
            _record(
                "v-1",
                group=EvidenceGroup.VOLATILITY_SESSION,
                event_type=EventType.RANGE_EXPANSION,
            ),
            _record(
                "m-1",
                group=EvidenceGroup.MACRO,
                event_type=EventType.MACRO_HIGH_IMPACT_NEAR,
                prior_weight=1.0,  # نتجاوز وزن §20 الصفري لاختبار الإتاحة
            ),
        ]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert len(snapshot.availability.present_groups) == 6
        assert snapshot.availability.absent_groups == ()
        assert snapshot.availability.redistributed_share == 0.0
        assert snapshot.availability.effective_shares == snapshot.availability.default_shares

    def test_empty_ledger_degenerate_snapshot(self) -> None:
        """سجل فارغ ⇒ درجة صفر وتوقيع كامل الغياب — لا استثناء ولا صمت."""
        engine = FusionEngine()
        snapshot = engine.compute([], scenario_id="scn", direction=Direction.LONG, fusion_time=T0)
        assert snapshot.raw_evidence_score == 0.0
        assert snapshot.group_scores == ()
        assert snapshot.availability.present_groups == ()
        assert len(snapshot.availability.absent_groups) == 6
        assert snapshot.availability.effective_shares == {}
        assert snapshot.availability.redistributed_share == pytest.approx(1.0)
        assert snapshot.evidence_ids == ()

    def test_unqualified_evidence_does_not_mark_availability(self) -> None:
        """دليل صفري المساهمة (وزن كلي 0 أو اتجاه محايد) يسجَّل ولا يُحسب
        حاضرًا — «الأعضاء المؤهلين» D-03-أ."""
        engine = FusionEngine()
        macro = _record(
            "m-zero",
            group=EvidenceGroup.MACRO,
            event_type=EventType.MACRO_HIGH_IMPACT_NEAR,
            prior_weight=0.0,  # §20: الكلي ليس درجة اتجاهية
        )
        snapshot = engine.compute(
            [macro, _flow_record("f-1")],
            scenario_id="scn",
            direction=Direction.LONG,
            fusion_time=T0,
        )
        assert snapshot.availability.present_groups == (EvidenceGroup.ORDER_FLOW,)
        assert EvidenceGroup.MACRO in snapshot.availability.absent_groups
        # السلسلة توثق الدليل كاملًا رغم عدم تأهيله
        assert snapshot.evidence_ids == ("m-zero", "f-1")


# ──────────────────── حقنة الدفعة الواحدة — §19.4 ────────────────────


class TestBatchIndependenceInjection:
    """«دفعة واحدة تنتج 4 أحداث» لا ترفع الدرجة فوق سقف المجموعة."""

    def test_four_correlated_events_discounted_and_capped(self) -> None:
        """أربعة أدلة مترابطة (خصم γ=0.5 الهندسي: 1، ½، ¼، ⅛) بقوة 0.5
        لكل منها: المجموع الخام 0.9375 والدرجة تحت السقف الفعلي حتمًا —
        وبلا خصم أعلى منها (الخصم يفعل شيئًا والسقف يحمي دائمًا)."""
        engine = FusionEngine()
        potentials = 0.5
        discounts = (1.0, 0.5, 0.25, 0.125)
        discounted = [
            _record(f"ev-{i}", raw_strength=potentials, independence_discount=discount)
            for i, discount in enumerate(discounts)
        ]
        snapshot = engine.compute(
            discounted, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        (structure,) = snapshot.group_scores
        assert structure.raw_sum == pytest.approx(0.5 * (1.0 + 0.5 + 0.25 + 0.125))
        assert structure.raw_sum == pytest.approx(0.9375)
        # البنية وحدها حاضرة ⇒ سقفها الفعلي 1.0 بعد إعادة التوزيع (D-03-ب)
        assert structure.score == pytest.approx(1.0 * math.tanh(0.9375 / 1.0))
        assert structure.score < structure.effective_share

        # بلا خصم (أدلة مستقلة فعلاً) — أعلى لكن ما زال تحت السقف
        undiscounted = [_record(f"ev-free-{i}", raw_strength=potentials) for i in range(4)]
        snapshot_free = engine.compute(
            undiscounted, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        (structure_free,) = snapshot_free.group_scores
        assert structure_free.raw_sum == pytest.approx(2.0)
        assert structure_free.score < structure_free.effective_share
        assert structure_free.score > structure.score

    def test_four_correlated_under_default_cap(self) -> None:
        """الحقنة والمجموعات كلها حاضرة: سقف البنية يبقى حصتها 0.25
        الافتراضية — «لا ترفع الدرجة فوق سقف المجموعة» بحرفية البوابة."""
        engine = FusionEngine()
        others = [
            _record(
                "l-1", group=EvidenceGroup.LIQUIDITY_LOCATION, event_type=EventType.FVG_BULLISH
            ),
            _flow_record("f-1"),
            _record(
                "p-1", group=EvidenceGroup.PRICE_ACTION, event_type=EventType.BULLISH_ENGULFING
            ),
            _record(
                "v-1", group=EvidenceGroup.VOLATILITY_SESSION, event_type=EventType.RANGE_EXPANSION
            ),
            _record(
                "m-1",
                group=EvidenceGroup.MACRO,
                event_type=EventType.MACRO_HIGH_IMPACT_NEAR,
                prior_weight=1.0,
            ),
        ]
        batch = [
            _record(f"ev-{i}", raw_strength=0.5, independence_discount=discount)
            for i, discount in enumerate((1.0, 0.5, 0.25, 0.125))
        ]
        snapshot = engine.compute(
            others + batch, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        by_group = {item.group: item for item in snapshot.group_scores}
        structure = by_group[EvidenceGroup.STRUCTURE]
        assert structure.effective_share == pytest.approx(0.25)
        assert structure.score == pytest.approx(0.25 * math.tanh(0.9375 / 0.25))
        assert structure.score < 0.25


# ───────────────────────── التناقض — §19.5 ─────────────────────────


class TestContradictionModel:
    """التناقض يخفض ولا يلغي إلا veto — والمعارضة صريحة في اللقطة."""

    def test_opposition_reduces_but_never_cancels(self) -> None:
        engine = FusionEngine()
        support_only = [_record("s-1", raw_strength=0.5)]
        with_opposition = [
            _record("s-1", raw_strength=0.5),
            _record("o-1", raw_strength=0.2, direction_score=-1.0, opposition=True),
        ]
        clean = engine.compute(
            support_only, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        contested = engine.compute(
            with_opposition, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert contested.raw_evidence_score < clean.raw_evidence_score
        assert contested.raw_evidence_score > 0.0  # خفض لا إلغاء
        assert contested.opposition_evidence_ids == ("o-1",)
        assert contested.support_contribution == pytest.approx(0.5)
        assert contested.opposition_contribution == pytest.approx(0.2)

    def test_overwhelming_opposition_flips_sign(self) -> None:
        """معارضة ساحقة تقلب الدرجة سالبة — رقم صريح لا تصفير بولياني."""
        engine = FusionEngine()
        records = [
            _record("s-weak", raw_strength=0.1),
            _record("o-strong-1", raw_strength=0.9, direction_score=-1.0, opposition=True),
            _record("o-strong-2", raw_strength=0.9, direction_score=-1.0, opposition=True),
        ]
        snapshot = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert snapshot.raw_evidence_score < 0.0
        assert len(snapshot.opposition_evidence_ids) == 2
        assert snapshot.support_contribution == pytest.approx(0.1)
        assert snapshot.opposition_contribution == pytest.approx(1.8)


# ────────────────────── الـveto خارج الحساب — D-03-د ──────────────────────


class TestVetoOutsideComputation:
    """الحجب منطق بولياني معلن لا يمس رقمًا واحدًا من الحساب."""

    def test_veto_flags_without_touching_numbers(self) -> None:
        engine = FusionEngine()
        records = [_record("s-1", raw_strength=0.5), _flow_record("f-1")]
        clean = engine.compute(records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0)
        blocked = engine.compute(
            records,
            scenario_id="scn",
            direction=Direction.LONG,
            fusion_time=T0,
            veto_reasons=("DATA_STALE", "SPREAD_EXTREME"),
        )
        assert blocked.vetoed is True
        assert blocked.veto_reasons == ("DATA_STALE", "SPREAD_EXTREME")
        assert clean.vetoed is False
        # الأرقام مطابقة تمامًا — العلم وحده اختلف
        assert blocked.raw_evidence_score == clean.raw_evidence_score
        assert blocked.group_scores == clean.group_scores
        assert blocked.support_contribution == clean.support_contribution
        assert blocked.opposition_contribution == clean.opposition_contribution
        assert blocked.availability == clean.availability


# ───────────────────────── الحتمية والمعايرة ─────────────────────────


class TestDeterminismAndCalibration:
    """نفس المدخلات ⇒ نفس اللقطة بايت-بايت، والمعايرة مؤجلة لا صامتة."""

    def test_byte_for_byte_determinism(self) -> None:
        engine = FusionEngine()
        records = [_record("s-1", raw_strength=0.5), _flow_record("f-1", freshness=0.7)]
        first = engine.compute(records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0)
        second = engine.compute(
            records, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert first.model_dump_json() == second.model_dump_json()

    def test_calibration_report_deferred(self) -> None:
        engine = FusionEngine()
        snapshot = engine.compute(
            [_record("s-1")], scenario_id="scn", direction=Direction.LONG, fusion_time=T0
        )
        assert snapshot.calibration.eligible is False
        assert snapshot.calibration.calibrated_probability is None
        assert snapshot.calibration.calibration_sample_size == 0
        assert snapshot.calibration.deferral_reason == CALIBRATION_DEFERRAL_REASON


# ───────────────────────── حرس العقود ─────────────────────────


class TestComputeGuards:
    """رفض صاخب لكسر العقود — لا صمت موافقة."""

    def test_hard_block_event_rejected(self) -> None:
        stale = _record(
            "ev-stale",
            group=EvidenceGroup.MACRO,
            event_type=EventType.DATA_STALE,
        )
        with pytest.raises(ValueError, match="حجب صلب"):
            FusionEngine().compute(
                [stale], scenario_id="scn", direction=Direction.LONG, fusion_time=T0
            )

    def test_group_mapping_mismatch_rejected(self) -> None:
        """سجل مجموعته تخالف خريطة §19.3 ⇒ خلل باني يُكشف هنا."""
        mismatched = _record(
            "ev-mis",
            group=EvidenceGroup.ORDER_FLOW,  # EXTERNAL_BOS بنوي لا تدفقي
        )
        with pytest.raises(ValueError, match="تخالف خريطة"):
            FusionEngine().compute(
                [mismatched], scenario_id="scn", direction=Direction.LONG, fusion_time=T0
            )

    def test_duplicate_evidence_id_rejected(self) -> None:
        duplicate = [_record("ev-dup"), _record("ev-dup", raw_strength=0.3)]
        with pytest.raises(ValueError, match="مكرر"):
            FusionEngine().compute(
                duplicate, scenario_id="scn", direction=Direction.LONG, fusion_time=T0
            )


# ───────────────────── إعداد D-03 المُصدَّر ─────────────────────


class TestFusionConfig:
    """الحصص §19.3 حرفية والمدقق صارم والبصمة حتمية حساسة."""

    def test_default_shares_literal(self) -> None:
        config = FusionConfig()
        assert config.group_shares[EvidenceGroup.STRUCTURE] == 0.25
        assert config.group_shares[EvidenceGroup.LIQUIDITY_LOCATION] == 0.20
        assert config.group_shares[EvidenceGroup.ORDER_FLOW] == 0.30
        assert config.group_shares[EvidenceGroup.PRICE_ACTION] == 0.10
        assert config.group_shares[EvidenceGroup.VOLATILITY_SESSION] == 0.10
        assert config.group_shares[EvidenceGroup.MACRO] == 0.05
        assert config.independence_decay == 0.5
        assert config.freshness_ttl_bars == 60.0
        assert config.default_context_modifier == 1.0
        assert config.default_quality == 1.0

    def test_missing_group_rejected(self) -> None:
        shares = dict(FusionConfig().group_shares)
        del shares[EvidenceGroup.MACRO]
        with pytest.raises(ValidationError, match="ناقصة"):
            FusionConfig(group_shares=shares)

    def test_unnormalized_sum_rejected(self) -> None:
        shares = dict(FusionConfig().group_shares)
        shares[EvidenceGroup.STRUCTURE] = 0.30  # المجموع 1.10
        with pytest.raises(ValidationError, match=r"≠ 1\.0"):
            FusionConfig(group_shares=shares)

    def test_zero_share_rejected(self) -> None:
        shares = dict(FusionConfig().group_shares)
        shares[EvidenceGroup.STRUCTURE] = 0.0
        shares[EvidenceGroup.ORDER_FLOW] = 0.55
        with pytest.raises(ValidationError, match="موجبة"):
            FusionConfig(group_shares=shares)

    def test_decay_bounds(self) -> None:
        with pytest.raises(ValidationError):
            FusionConfig(independence_decay=0.0)
        with pytest.raises(ValidationError):
            FusionConfig(independence_decay=1.5)

    def test_frozen_and_fingerprint(self) -> None:
        config = FusionConfig()
        with pytest.raises(ValidationError, match="frozen"):
            config.independence_decay = 0.7  # type: ignore[misc]
        # البصمة حتمية
        assert config.fingerprint == FusionConfig().fingerprint
        # وحساسة لأي قيمة تدخل الحساب
        tweaked = FusionConfig(independence_decay=0.6)
        assert tweaked.fingerprint != config.fingerprint
        retuned = FusionConfig(freshness_ttl_bars=30.0)
        assert retuned.fingerprint != config.fingerprint
