"""اختبارات المُقترِح (D-04) — الاستنساخ الحتمي المعدّد عند المرسِم.

العقود المفحوصة:

- القوالب الثلاثة من الاجتياح: الانعكاس ضد الجهة والاختراق باتجاهها
  (القبول خلف القاع الحتمي) والاستمرار بالانحياز المؤكد — بمعرفات
  uuid5 حتمية (نفس المرسِم ⇒ نفس المعرفات: idempotent)؛
- القوالب من الكسر-القبول: الاختراق بصمود إعادة الاختبار والانعكاس
  بفشل القبول (ZONE_RECLAIM للحافة البعيدة المقابلة)؛
- الغيوب الموثقة: انحياز غير مؤكد ⇒ لا استمراح، ولا هدف في الجهة ⇒ لا
  استنساخ للقالب (§18.3 إلزامي)؛
- الهندسة: القاع الحتمي المعاد اشتقاقه (الحافة البعيدة ± excursion×ATR)،
  عازلة الإبطال من التقلب، نطاق الدخول، الأهداف حواف الدخول القريبة؛
- §18.3 كاملًا: السياق والموقع والآلية والمشغل والإبطال والمسار
  (هدف أساسي + ثانويان) والزعنفة الزمنية بحسب القالب والتناقضات
  (المعارضة من سجل الولادة)؛
- الحتمية بايت-بايت والتحجيم λ=2 (كل القياسات مطبَّعة)؛
- الحرس: مرسِم غير موقعي ومنطقة أجنبية وATR غير موجب — رفض صاخب.
"""

from __future__ import annotations

import pytest
from _scenario_fixtures import (
    ANCHOR_TIME,
    ATR,
    TIMEFRAME,
    make_break_accept_payload,
    make_market_state,
    make_sweep_payload,
    make_target_map,
    make_zone,
    sell_zone,
)
from liquidity.targets import TargetMap
from scenarios.parameter_sets import ScenarioConfig, default_scenario_config
from scenarios.proposer import (
    MIN_SUPPORTING_GROUPS,
    AnchorEvent,
    ProposalOutcome,
    ScenarioProposer,
    scenario_id_for,
    score_from_raw,
)
from schemas import (
    Direction,
    EventType,
    HTFBias,
    Scenario,
    ScenarioTemplate,
)

# ───────────────────────── من الاجتياح ─────────────────────────


class TestSweepProposal:
    """القوالب الثلاثة من اجتياح مؤكد عند موقع مرسوم."""

    def test_three_templates_from_sweep(self) -> None:
        outcome = _propose_sweep()
        templates = {s.template for s in outcome.proposals}
        assert templates == {
            ScenarioTemplate.REVERSAL,
            ScenarioTemplate.CONTINUATION,
            ScenarioTemplate.BREAKOUT,
        }
        assert not outcome.absences

    def test_reversal_against_swept_side(self) -> None:
        outcome = _propose_sweep()
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        # اجتياح بيعية (قيعان) ثم رفض ⇒ انعكاس صاعد
        assert reversal.direction is Direction.LONG
        # المشغل: إزاحة إطار التنفيذ بالاتجاه (مثال §18.3 حرفيًا)
        assert reversal.trigger_definition.condition_type == "DISPLACEMENT_CONFIRM"
        assert reversal.trigger_definition.params["direction"] == "LONG"
        assert reversal.trigger_definition.params["timeframe"] == TIMEFRAME

    def test_breakout_with_sweep_direction(self) -> None:
        outcome = _propose_sweep()
        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        # فشل الرفض ⇒ قبول خلف القاع الحتمي ⇒ اختراق هابط
        assert breakout.direction is Direction.SHORT
        assert breakout.trigger_definition.condition_type == "ACCEPTANCE_BEYOND"
        params = breakout.trigger_definition.params
        # القاع الحتمي = الحافة البعيدة − excursion×ATR (إعادة اشتقاق مضبوطة)
        assert params["level"] == pytest.approx(59_800.0 - 1.0 * ATR)
        assert params["window"] == default_scenario_config().acceptance_window_bars

    def test_continuation_with_confirmed_bias(self) -> None:
        outcome = _propose_sweep()
        continuation = _of(outcome, ScenarioTemplate.CONTINUATION)
        assert continuation.direction is Direction.LONG  # الانحياز صاعد مؤكد
        assert continuation.trigger_definition.condition_type == "INTERNAL_BOS"

    def test_geometry_is_atr_anchored(self) -> None:
        outcome = _propose_sweep()
        config = default_scenario_config()
        buffer = config.invalidation_buffer_atr * ATR

        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        # الإبطال خلف القاع الحتمي بعازلة تقلب (§23.4)
        assert reversal.invalidation.structural_level == pytest.approx(59_600.0)
        assert reversal.invalidation.volatility_buffer == pytest.approx(buffer)
        assert reversal.invalidation.accept_through is True
        # الدخول عند المنطقة المرسمة نفسها
        assert reversal.entry_zone.price_low == 59_800.0
        assert reversal.entry_zone.price_high == 59_900.0

        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        # إبطال الاختراق باسترجاع الحافة القريبة (الرفض تحقق فعليًا)
        assert breakout.invalidation.structural_level == pytest.approx(59_900.0)
        band = config.retest_band_atr * ATR
        assert breakout.entry_zone.price_low == pytest.approx(59_600.0 - band)
        assert breakout.entry_zone.price_high == pytest.approx(59_600.0 + band)

        continuation = _of(outcome, ScenarioTemplate.CONTINUATION)
        # فشل موقع الاستمرار: هبوط كامل خلف قاع المنطقة
        assert continuation.invalidation.structural_level == pytest.approx(59_800.0)

    def test_targets_are_entry_edges_of_map(self) -> None:
        outcome = _propose_sweep()
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        # هدف صاعد: أقرب هدف فوق — حافة الدخول القريبة (قاع منطقة شرائية)
        assert reversal.primary_targets[0].zone_id == "lz-buy-001"
        assert reversal.primary_targets[0].price_level == pytest.approx(60_500.0)
        assert [t.zone_id for t in reversal.secondary_targets] == ["lz-buy-002"]

        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        assert breakout.primary_targets[0].zone_id == "lz-sell-002"
        assert breakout.primary_targets[0].price_level == pytest.approx(59_500.0)

    def test_birth_evidence_support_and_opposition(self) -> None:
        outcome = _propose_sweep()
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        # حدث الاجتياح نفسه مساند للانعكاس (قطبية الرفض) + الانحياز مشتق
        assert len(reversal.supporting_evidence) == 2
        assert reversal.opposing_evidence == []

        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        # نفس الدليل يعارض الاختراق (الرفض المساند للانعكاس معاكس هنا)
        assert breakout.opposing_evidence  # §18.3 «Contradictions» صريح
        assert len(breakout.supporting_evidence) + len(breakout.opposing_evidence) == 2

    def test_scores_mirror_across_directions(self) -> None:
        """مرآة الدليل: الانعكاس والاختراق المتضادان درجتاهما تتكاملان."""
        outcome = _propose_sweep()
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        assert reversal.scenario_score + breakout.scenario_score == pytest.approx(1.0)

    def test_expiry_by_template(self) -> None:
        outcome = _propose_sweep()
        config = default_scenario_config()
        for scenario in outcome.proposals:
            bars = config.expiry_bars[scenario.template]
            expected = ANCHOR_TIME.timestamp() + bars * 60.0
            assert scenario.expiry_time.timestamp() == pytest.approx(expected)

    def test_ids_deterministic_and_idempotent(self) -> None:
        first = _propose_sweep()
        second = _propose_sweep()
        assert [s.scenario_id for s in first.proposals] == [s.scenario_id for s in second.proposals]
        assert [s.model_dump_json() for s in first.proposals] == [
            s.model_dump_json() for s in second.proposals
        ]

    def test_scenario_id_is_uuid5_of_identity(self) -> None:
        outcome = _propose_sweep()
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        anchor_id = reversal.proposed_from_event_id
        assert reversal.scenario_id == scenario_id_for(
            ScenarioTemplate.REVERSAL, anchor_id, "lz-sell-001", Direction.LONG
        )


# ───────────────────────── من الكسر-القبول ─────────────────────────


class TestBreakAcceptProposal:
    """الاختراق بصمود إعادة الاختبار والانعكاس بفشل القبول."""

    def test_breakout_retest_and_reversal_reclaim(self) -> None:
        proposer = ScenarioProposer()
        outcome = proposer.propose(
            AnchorEvent(EventType.BREAK_AND_ACCEPT_LOW, ANCHOR_TIME, make_break_accept_payload()),
            zone=sell_zone(),
            targets=make_target_map(),
            state=make_market_state(),  # صاعد — الاستمرار ممكن أيضًا
            atr=ATR,
        )
        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        assert breakout.direction is Direction.SHORT  # قبول بيعية ⇒ هابط
        assert breakout.trigger_definition.condition_type == "RETEST_HOLD"
        params = breakout.trigger_definition.params
        assert params["boundary"] == pytest.approx(59_800.0)  # الحافة المق布鲁قة
        # إبطال الاختراق: عودة كاملة خلف الحافة البعيدة
        assert breakout.invalidation.structural_level == pytest.approx(59_900.0)

        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        assert reversal.direction is Direction.LONG  # فرضية الفخ
        assert reversal.trigger_definition.condition_type == "ZONE_RECLAIM"
        # الاسترجاع: إغلاق فوق الحافة المقابلة (قمم المنطقة)
        assert reversal.trigger_definition.params["level"] == pytest.approx(59_900.0)
        # إبطال الفخ: فوق أقصى القبول المعاد اشتقاقه
        assert reversal.invalidation.structural_level == pytest.approx(59_600.0)

    def test_scores_favor_aligned_breakout(self) -> None:
        """بلا انحياز (NEUTRAL): القبول وحده يرجّح الاختراق المتحالف.

        مع انحياز صاعد مؤكد تخصم بنيةُ HTF الاختراقَ الهابط فعلا (مرآة
        الدليل) — ذلك سلوك الدمج الصحيح لا خللا؛ هنا نعزل أثر القبول.
        """
        proposer = ScenarioProposer()
        outcome = proposer.propose(
            AnchorEvent(EventType.BREAK_AND_ACCEPT_LOW, ANCHOR_TIME, make_break_accept_payload()),
            zone=sell_zone(),
            targets=make_target_map(),
            state=make_market_state(bias=HTFBias.NEUTRAL),
            atr=ATR,
        )
        breakout = _of(outcome, ScenarioTemplate.BREAKOUT)
        reversal = _of(outcome, ScenarioTemplate.REVERSAL)
        assert breakout.scenario_score > 0.5 > reversal.scenario_score
        # مرآة الدليل: المتضادان من المرسِم نفسه درجتاهما تتكاملان
        assert breakout.scenario_score + reversal.scenario_score == pytest.approx(1.0)


# ───────────────────────── الغيوب الموثقة ─────────────────────────


class TestDocumentedAbsences:
    """الغياب إعلان صريح لا صمت موافقة."""

    def test_neutral_bias_no_continuation(self) -> None:
        proposer = ScenarioProposer()
        outcome = proposer.propose(
            AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
            zone=sell_zone(),
            targets=make_target_map(),
            state=make_market_state(bias=HTFBias.NEUTRAL),
            atr=ATR,
        )
        templates = {s.template for s in outcome.proposals}
        assert ScenarioTemplate.CONTINUATION not in templates
        (absence,) = [a for a in outcome.absences if a.template is ScenarioTemplate.CONTINUATION]
        assert "غير مؤكد" in absence.reason

    def test_no_target_no_instantiation(self) -> None:
        """لا هدف في جهة القالب ⇒ لا استنساخ — §18.3 إلزامي."""
        proposer = ScenarioProposer()
        # خريطة بلا أهداف فوق: الانعكاس الصاعد والاستمرار الصاعد يسقطان
        outcome = proposer.propose(
            AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
            zone=sell_zone(),
            targets=make_target_map(above=()),
            state=make_market_state(),
            atr=ATR,
        )
        templates = {s.template for s in outcome.proposals}
        assert templates == {ScenarioTemplate.BREAKOUT}
        absent = {a.template for a in outcome.absences}
        assert absent == {ScenarioTemplate.REVERSAL, ScenarioTemplate.CONTINUATION}
        assert all("لا هدف سيولة" in a.reason for a in outcome.absences)


# ───────────────────────── الحتمية والتحجيم ─────────────────────────


class TestDeterminismAndScaling:
    """نفس المدخلات ⇒ نفس المقترحات؛ وλ=2 لا يغير الدلالة."""

    def test_lambda_two_semantic_equivalence(self) -> None:
        """مضاعفة كل الأسعار وATR ⇒ نفس السيناريوهات دلاليًا.

        كل القياسات مطبَّعة (excursion_atr نسبة والعوازل بـATR والأهداف
        حواف) فتتضاعف القيم المطلقة وحدها — المعرفات وحدها تتبع الأسعار
        (بصمة الحمولة تدخل uuid5 — درس بوابة 6).
        """
        first = _propose_sweep()
        scaled = ScenarioProposer().propose(
            AnchorEvent(
                EventType.LIQUIDITY_SWEEP_LOW,
                ANCHOR_TIME,
                make_sweep_payload(excursion_atr=1.0),
            ),
            zone=make_zone(price_low=2.0 * 59_800.0, price_high=2.0 * 59_900.0),
            targets=_scaled_targets(),
            state=make_market_state(),
            atr=2.0 * ATR,
        )
        # كل الأسعار تتضاعف بدقة
        for original, doubled in zip(first.proposals, scaled.proposals, strict=True):
            assert original.template is doubled.template
            assert original.direction is doubled.direction
            assert doubled.entry_zone.price_low == pytest.approx(
                2.0 * original.entry_zone.price_low
            )
            assert doubled.invalidation.structural_level == pytest.approx(
                2.0 * original.invalidation.structural_level
            )
            assert doubled.invalidation.volatility_buffer == pytest.approx(
                2.0 * original.invalidation.volatility_buffer
            )
            assert doubled.scenario_score == pytest.approx(original.scenario_score)
            assert doubled.trigger_definition.condition_type == (
                original.trigger_definition.condition_type
            )

    def test_execution_timeframe_validated(self) -> None:
        with pytest.raises(ValueError, match="إطار تنفيذ غير مدعوم"):
            ScenarioProposer(execution_timeframe="2h")


# ───────────────────────── الحرس ─────────────────────────


class TestGuards:
    """الرفض الصاخب للمدخلات الفاسدة — لا افتراض صامت."""

    def test_non_location_anchor_rejected(self) -> None:
        from _fusion_fixtures import make_structure_break

        proposer = ScenarioProposer()
        with pytest.raises(ValueError, match="مرسِم غير موقعي"):
            proposer.propose(
                AnchorEvent(EventType.INTERNAL_BOS, ANCHOR_TIME, make_structure_break()),
                zone=sell_zone(),
                targets=make_target_map(),
                state=make_market_state(),
                atr=ATR,
            )

    def test_foreign_zone_rejected(self) -> None:
        proposer = ScenarioProposer()
        with pytest.raises(ValueError, match="منطقة أجنبية"):
            proposer.propose(
                AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
                zone=make_zone(instrument="BINANCE_USDM:ETHUSDT"),
                targets=make_target_map(),
                state=make_market_state(),
                atr=ATR,
            )

    def test_mismatched_zone_id_rejected(self) -> None:
        proposer = ScenarioProposer()
        with pytest.raises(ValueError, match="منطقة غير المرسمة"):
            proposer.propose(
                AnchorEvent(
                    EventType.LIQUIDITY_SWEEP_LOW,
                    ANCHOR_TIME,
                    make_sweep_payload(zone_id="lz-other"),
                ),
                zone=sell_zone(),
                targets=make_target_map(),
                state=make_market_state(),
                atr=ATR,
            )

    def test_non_positive_atr_rejected(self) -> None:
        proposer = ScenarioProposer()
        with pytest.raises(ValueError, match="ATR غير موجب"):
            proposer.propose(
                AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
                zone=sell_zone(),
                targets=make_target_map(),
                state=make_market_state(),
                atr=0.0,
            )

    def test_min_supporting_groups_is_spec_constant(self) -> None:
        """«at least two» — ثابت مواصفة لا معامل إعدادي (§18.4)."""
        assert MIN_SUPPORTING_GROUPS == 2
        fields = ScenarioConfig.model_fields
        assert "min_supporting_groups" not in fields


# ───────────────────────── مساعدات ─────────────────────────


def _of(outcome: ProposalOutcome, template: ScenarioTemplate) -> Scenario:
    for scenario in outcome.proposals:
        if scenario.template is template:
            return scenario
    raise AssertionError(f"قالب غائب: {template}")


def _propose_sweep() -> ProposalOutcome:
    proposer = ScenarioProposer()
    return proposer.propose(
        AnchorEvent(EventType.LIQUIDITY_SWEEP_LOW, ANCHOR_TIME, make_sweep_payload()),
        zone=sell_zone(),
        targets=make_target_map(),
        state=make_market_state(),
        atr=ATR,
    )


def _scaled_targets() -> TargetMap:
    from _scenario_fixtures import make_target_map

    return make_target_map(
        above=(
            ("lz-buy-001", 121_000.0, 121_200.0, 1.2, 0.9),
            ("lz-buy-002", 122_000.0, 122_200.0, 2.5, 0.7),
        ),
        below=(
            ("lz-sell-002", 118_800.0, 119_000.0, 0.8, 0.8),
            ("lz-sell-003", 118_000.0, 118_200.0, 1.9, 0.6),
        ),
    )


def test_score_from_raw_mapping() -> None:
    """إعادة الإسقاط: −1→0 و0→0.5 و+1→1 — ليست احتمالًا (§2.6)."""
    assert score_from_raw(-1.0) == pytest.approx(0.0)
    assert score_from_raw(0.0) == pytest.approx(0.5)
    assert score_from_raw(1.0) == pytest.approx(1.0)
    assert score_from_raw(-0.6065) == pytest.approx(0.19675)
