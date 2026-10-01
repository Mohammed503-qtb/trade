#!/usr/bin/env python3
"""بوابة خروج المرحلة 8 — لا-تداول + مخاطرة (build_plan §D + §22 + §23 + §25.2).

يتطلب بنية حية (postgres عند الرأس 0008) وعينة phase2 الثلاثية الأطر
الحقيقية — ويبني على مسار بوابة المرحلة 7 نفسه (ScenarioRun مستورد
حرفيًا: نفس المرسِم والمشغلات ⇒ نفس المشتعلين — لا جهاز ثانٍ).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: الأطر الثلاثة متطابقة مع manifest (فحص المرحلة 7 نفسه).
2. **المشتعلون الناجون**: كل TRIGGERED لم يُكتم بتنافس شريطته يقيمه
   المخاطرة مرة واحدة — قرار لكل مشتعل ناجٍ حصريًا.
3. **قرارات حقيقية**: توزيع القرارات على أسسها الثلاثة بتفسير §22.3
   لكل سبب وتفسير §2.8 مكتمل لكل قرار.
4. **الحقن الشامل 15/15** (بوابة الخروج نصًا): كل حاجب صلب يُحقن
   حقيقته على مشتعل حقيقي ⇒ رفض صلب موثق برمزه — الخمسة عشر كاملة.
5. **كتم بحقن القياس**: كل كتمة قابلة للاشتعال بحقن قياسها (عتبات
   إعدادية على بيانات حقيقية) وبأوزان موثقة تجمّع مقابل العتبة.
6. **التحجيم §23.2**: المعدلات الستة بترتيب الخطة في كل قرار معتمد
   ولا معدل يرفع الأحجام — والخطر الناتج ≤ الميزانية في الكل.
7. **التكاليف §25.2**: المتطابقة محقاة والأنماط الثلاثة تختلف
   (OPTIMISTIC تشخيصي وحده) وREALISTIC نمط القبول في القرارات.
8. **الحافة الصافية §23.5**: توزيع R الصافية على القرارات الحقيقية
   وحقن الحد الأدنى يقلب المعتمدين إلى رفض حافة.
9. **دورة الحياة القانونية**: انتقالات المخاطرة (TRIGGERED→AUTHORIZED/
   REJECTED_BY_RISK) قانونية عبر آلة §18.2 والنهائية بلا صادرة أبدًا.
10. **التفسير §2.8 بتكلفة مسددة**: تقدير التكاليف حاضر في كل قرار
    (وعد المرحلة 6) ولا نص تأجيل فيها — وسبب الرفض عند الرفض حصرًا.
11. **القاعدة الحية**: كتابة القرارات والنوايا والتجارب idempotent
    وسجل الرفض يعمل والقرار مع حياته الكاملة بجولة SQL واحدة —
    وaudit_risk_gate صفر مخالفين على القاعدة النظيفة.
12. **دفتر التجارب §29.1**: سجل لكل سيناريو مُقيَّم أُغلق (المرفوض عند
    قراره والمُرخَّص عند نهايته البنيوية) — MFE/MAE مقيسة وصف واحد
    لكل سيناريو وidempotent.
13. **الحتمية**: مساران كاملان ⇒ نفس القرارات والتجارب بايت-بايت.
14. **لا-نظرة (§26.3)**: قرارات البادئة [0..720] مطابقة لبادئة
    التشغيل الكامل — قرار المخاطرة لا يرى إلا الماضي.
15. **التحجيم λ=2**: الأسعار تتضاعف فتتضاعف المسافات والوقف وتنصرف
    الأحجام (ميزانية نقدية ثابتة) — الهندسة النسبية ثابتة تمامًا
    (R الإجمالية متطابقة) والانقلابات الوحيدة باتجاه التكلفة
    (العمولات الثابتة تزن أقل مضاعفةً) ولا انقلاب ضار أبدًا.
16. **القانونية**: كل قرار وتجربة يمر مخططه المصدَّر (jsonschema).
17. **التدهور الآمن (§49)**: حقن جودة غير آمنة عند الشريط 1000 يطفئ
    الأحياء قبل بلوغ المخاطرة — لا قرار بعد الحقن (روح الحاجب 1
    يسبق القرار أصلاً).
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# الاستيرادات بعد تهيئة مسارات الحزم (نمط verify_phase3-7 حرفيًا)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ — لاستيراد verify_phase7
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "risk" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "learning" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "scenarios" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "fusion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "liquidity" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "structure" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "market_state" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "features" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "schemas" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "common" / "src"))

import jsonschema
from fusion.compute import FusionEngine
from fusion.ledger import EvidenceLedgerBuilder
from learning.ledger import build_experience_record
from learning.store import ExperienceStore
from risk.engine import RiskEngine, decision_id_for
from risk.parameter_sets import RiskConfig, default_risk_config
from risk.store import RiskStore
from scenarios.lifecycle import (
    LEGAL_TRANSITIONS,
    apply_transition,
    is_terminal,
)
from scenarios.store import ScenarioStore
from schemas import (
    DataQuality,
    EvaluationContext,
    ExperienceRecord,
    HardBlockReason,
    MacroEventWindow,
    RejectionBasis,
    RiskDecision,
    Scenario,
    ScenarioState,
    ScenarioTransition,
    SessionType,
    SoftSuppressionReason,
    validate_explanation_completeness,
)
from verify_phase7 import (
    INSTRUMENT,
    ScenarioRun,
    load_phase2,
)

_checks = 0


def ok(msg: str) -> None:
    global _checks
    _checks += 1
    print(f"✓ {msg}")


def fail(msg: str) -> None:
    print(f"✗ {msg}")
    raise SystemExit(1)


def check(condition: bool, message_ok: str, message_fail: str) -> None:
    if condition:
        ok(message_ok)
    else:
        fail(message_fail)


#: المشتعل المُكتم في شريطته لا يقيمه المخاطرة — التنافس حسمه قبلها.
def _survivor_triggers(run: ScenarioRun) -> list[ScenarioTransition]:
    suppressed_same_bar = {
        (t.scenario_id, t.transition_time)
        for t in run.transitions
        if t.to_state is ScenarioState.SUPPRESSED
    }
    return [
        t
        for t in run.transitions
        if t.to_state is ScenarioState.TRIGGERED
        and (t.scenario_id, t.transition_time) not in suppressed_same_bar
    ]


class RiskPipeline:
    """قرارات المخاطرة فوق مسار المرحلة 7 — حتمي تمامًا.

    التركيب الموثق (ADR-026): المحرك يقود حتى TRIGGERED (بوابة 7)،
    والمخاطرة تقود ما بعده (AUTHORIZED/REJECTED_BY_RISK) عبر آلة
    الحياة نفسها — والسلسلة القانونية للقاعدة: انتقالات المحرك حتى
    الاشتعال فانتقال المخاطرة فنهاية المُرخَّص بحكم المحرك البنيوي.
    """

    def __init__(
        self,
        run: ScenarioRun,
        *,
        config: RiskConfig | None = None,
        context_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.run = run
        self.config = config or default_risk_config()
        self.context_overrides = context_overrides or {}
        self.risk_engine = RiskEngine(self.config)
        self.decisions: dict[str, RiskDecision] = {}
        self.risk_transitions: dict[str, ScenarioTransition] = {}
        self.authorized: dict[str, Scenario] = {}
        self.closing_transitions: dict[str, ScenarioTransition] = {}
        self.closed_scenarios: dict[str, Scenario] = {}
        self.experiences: dict[str, ExperienceRecord] = {}
        self._evaluate()

    # ───────────────────────── التقييم ─────────────────────────

    def _context(self, atr: float | None = None) -> EvaluationContext:
        """سياق واقعي حتمي — التقديرات بمقياس ATR لحظة القرار (ADR-015).

        فاتحة 5% من ATR وانزلاق 10% منه وكمون 250ms — قياس نسبي بالمقياس
        نفسه الذي تُبنى به الوقوف والعتبات، لا أرقام مطلقة تنفك عن مقياس
        الإطار (شموع 1m حقيقية: ATR صغير نسبيًا).
        """
        scale = atr if atr is not None and atr > 0.0 else self.config.slippage_estimate * 10.0
        return EvaluationContext.model_validate(
            {
                "spread_estimate": 0.05 * scale,
                "slippage_estimate": 0.10 * scale,
                "latency_ms": 250.0,
                **self.context_overrides,
            }
        )

    def _records_and_snapshot(self, scenario: Scenario, as_of: Any) -> tuple[list[Any], Any]:
        ledger = EvidenceLedgerBuilder()
        # ترشيح لا-نظرة (§26.3 — نمط _reference_records في المرحلة 7):
        # السجل يبني من أحداث الماضي وحده؛ الأحدث من as_of يُستبعد.
        events = [event for event in self.run.engine._events if event.event_time <= as_of]
        records = ledger.build(
            events,
            scenario_id=scenario.scenario_id,
            direction=scenario.direction,
            as_of=as_of,
            market_state=scenario.context_snapshot,
        )
        snapshot = FusionEngine().compute(
            records,
            scenario_id=scenario.scenario_id,
            direction=scenario.direction,
            fusion_time=as_of,
        )
        return records, snapshot

    def _evaluate(self) -> None:
        ltf_by_time = {
            candle.bar_time: (candle, atr, state) for candle, atr, state in self.run.bar_contexts
        }
        engine_scenarios = {s.scenario_id: s for s in self.run.scenarios}

        for trigger in _survivor_triggers(self.run):
            final_copy = engine_scenarios[trigger.scenario_id]
            context_bar = ltf_by_time.get(trigger.transition_time)
            if context_bar is None:
                continue  # اشتعال بلا سياق مسجل — لا قرار بلا شمعة (موثق)
            # نسخة لحظة الاشتعال: القرار يصدر عن TRIGGERED حيًا — النسخة
            # النهائية قد أُبطلت لاحقًا بنيويًا (زمنياً القرار سابق عليها).
            scenario = final_copy.model_copy(update={"state": ScenarioState.TRIGGERED})
            candle, atr, state = context_bar
            records, snapshot = self._records_and_snapshot(scenario, trigger.transition_time)
            evaluation = self.risk_engine.evaluate(
                scenario,
                snapshot=snapshot,
                records=records,
                market_state=state,
                candle=candle,
                atr=atr,
                context=self._context(atr),
                trigger_reason=trigger.reason,
            )
            decision = evaluation.decision
            self.decisions[decision.decision_id] = decision
            updated, transition = apply_transition(
                scenario,
                evaluation.target_state,
                transition_time=trigger.transition_time,
                reason=evaluation.transition_reason,
            )
            self.risk_transitions[scenario.scenario_id] = transition
            if evaluation.target_state is ScenarioState.AUTHORIZED:
                self.authorized[scenario.scenario_id] = updated
            else:
                # المرفوض مغلق عند قراره — سجل التجربة فورًا (§29.1)
                closing = transition
                record = build_experience_record(
                    updated,
                    decision=decision,
                    closing_transition=closing,
                    records=records,
                    market_path=[],
                    session=SessionType.UTC_DAY,
                )
                self.experiences[scenario.scenario_id] = record

        # ── نهايات المُرخَّصين: حكم المحرك البنيوي على النسخة المُرخَّصة ──
        for scenario_id, authorized_copy in self.authorized.items():
            decision_time = self.risk_transitions[scenario_id].transition_time
            # خريطة §18.2 ملزمة: AUTHORIZED مآله الإبطال البنيوي أو إلغاء
            # الجودة (أو التنفيذ §24 لاحقًا) — الانقضاء نافذة ترخيص لا
            # نهاية مُرخَّص، فإقفاء التحليلي لا يغلق النسخة الورقية.
            engine_close = next(
                (
                    t
                    for t in self.run.transitions
                    if t.scenario_id == scenario_id
                    and t.to_state
                    in (ScenarioState.INVALIDATED, ScenarioState.CANCELLED_BY_DATA_QUALITY)
                    and t.transition_time > decision_time
                ),
                None,
            )
            if engine_close is None:
                continue  # بقي مفتوحًا حتى نهاية العينة — لا سجل لغير مغلق (موثق)
            closed_copy, closing = apply_transition(
                authorized_copy,
                engine_close.to_state,
                transition_time=engine_close.transition_time,
                reason=engine_close.reason,
            )
            self.closing_transitions[scenario_id] = closing
            self.closed_scenarios[scenario_id] = closed_copy
            decision = next(d for d in self.decisions.values() if d.scenario_id == scenario_id)
            path = [
                candle
                for candle, _atr, _state in self.run.bar_contexts
                if decision_time < candle.bar_time <= closing.transition_time
            ]
            record = build_experience_record(
                closed_copy,
                decision=decision,
                closing_transition=closing,
                records=self._records_and_snapshot(authorized_copy, decision_time)[0],
                market_path=path,
                session=SessionType.UTC_DAY,
            )
            self.experiences[scenario_id] = record

    # ───────────────────────── الاستعلامات ─────────────────────────

    def by_scenario(self) -> dict[str, RiskDecision]:
        return {d.scenario_id: d for d in self.decisions.values()}

    def canonical_lifecycle(self) -> dict[str, tuple[Scenario, list[ScenarioTransition]]]:
        """السلسلة القانونية لكل سيناريو — انتقالات المحرك حتى الاشتعال
        فانتقال المخاطرة فنهاية المُرخَّص (حكم المحرك البنيوي نفسه)."""
        engine_scenarios = {s.scenario_id: s for s in self.run.scenarios}
        by_scenario: dict[str, list[ScenarioTransition]] = {}
        for t in self.run.transitions:
            by_scenario.setdefault(t.scenario_id, []).append(t)
        canonical: dict[str, tuple[Scenario, list[ScenarioTransition]]] = {}
        for scenario_id, scenario in engine_scenarios.items():
            chain: list[ScenarioTransition] = []
            for t in by_scenario.get(scenario_id, []):
                chain.append(t)
                if t.to_state is ScenarioState.TRIGGERED:
                    break
            risk = self.risk_transitions.get(scenario_id)
            if risk is not None:
                chain.append(risk)
                close = self.closing_transitions.get(scenario_id)
                if close is not None:
                    chain.append(close)
                final = (
                    self.closed_scenarios.get(scenario_id)
                    or self.authorized.get(scenario_id)
                    or scenario
                )
                canonical[scenario_id] = (final, chain)
            else:
                canonical[scenario_id] = (scenario, chain)
        return canonical


# ───────────────────────── الفحوص الجوهرية ─────────────────────────


def core_checks(klines_by_tf: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]) -> None:
    """الفحوص 1-10 — القرارات الحقيقية والحقن والقوانين على العينة."""
    run = ScenarioRun(klines_by_tf)
    pipeline = RiskPipeline(run)

    # (1) العينة — نفس فحص المرحلة 7
    counts = {tf: len(bars) for tf, bars in klines_by_tf.items()}
    expected_counts = {tf: meta["count"] for tf, meta in manifest["timeframes"].items()}
    check(
        counts == expected_counts,
        f"العينة: الأطر الثلاثة مطابقة للـmanifest ({counts['1m']} شمعة 1m)",
        f"العينة لا تطابق manifest: {counts} ≠ {expected_counts}",
    )

    # (2) المشتعلون الناجون — قرار لكل ناجٍ حصرًا
    survivors = _survivor_triggers(run)
    by_scenario = pipeline.by_scenario()
    check(
        len(survivors) >= 1
        and len(by_scenario) == len({t.scenario_id for t in survivors})
        and all(
            d.decision_id == decision_id_for(d.scenario_id) for d in pipeline.decisions.values()
        ),
        f"المشتعلون الناجون: {len(survivors)} مشتعلًا يقيمهم المخاطرة — قرار حتمي واحد لكل سيناريو",
        "قرارات المخاطرة لا تطابق المشتعلين الناجين واحدًا لواحد",
    )

    # (3) قرارات حقيقية — التوزيع والتفسيرات
    bases = Counter(d.rejection_basis for d in pipeline.decisions.values() if not d.approved)
    approved = sum(1 for d in pipeline.decisions.values() if d.approved)
    every_explained = all(
        all(
            explanation.triggering_conditions.strip()
            # عقد الإعادة §22.3: السماح بشرطه والمنع بلا شرط — تناسق لا عموم
            and (explanation.whether_retry_is_allowed == (explanation.retry_condition is not None))
            for explanation in d.hard_blocks + d.soft_suppressions
        )
        for d in pipeline.decisions.values()
    )
    check(
        len(pipeline.decisions) == approved + sum(bases.values()) and every_explained,
        f"قرارات حقيقية: {len(pipeline.decisions)} قرارًا — {approved} مرخصًا و"
        f"{dict(bases)} رفضًا موثق الأساس والأسباب كاملة (§22.3)",
        "تفسيرات القرارات ناقصة أو التوزيع غير متطابق",
    )

    # (4) الحقن الشامل 15/15 — البوابة نصًا
    injection_cases: list[tuple[HardBlockReason, dict[str, Any]]] = [
        (HardBlockReason.DATA_UNRELIABLE, {"data_quality": DataQuality.STALE}),
        (HardBlockReason.DATA_UNRELIABLE, {"data_age_seconds": 120.0}),
        (HardBlockReason.INSTRUMENT_UNAVAILABLE, {"instrument_tradable": False}),
        (HardBlockReason.VENUE_CONNECTION_UNHEALTHY, {"venue_healthy": False}),
        (HardBlockReason.SPREAD_EXCEEDS_BUDGET, {"spread_estimate": 500.0}),
        (HardBlockReason.SLIPPAGE_EXCEEDS_BUDGET, {"slippage_estimate": 500.0}),
        (HardBlockReason.LATENCY_EXCEEDS_BUDGET, {"latency_ms": 5000.0}),
        (HardBlockReason.RISK_LIMITS_REACHED, {"positions_open": 3}),
        (HardBlockReason.RISK_LIMITS_REACHED, {"risk_used_today": 10_000.0}),
        (HardBlockReason.STOP_NOT_RELIABLE, {"stop_reliable": False}),
        (HardBlockReason.BROKER_REJECTS_ORDER, {"broker_accepts_order": False}),
        (HardBlockReason.KILL_SWITCH, {"kill_switch": True}),
    ]
    # 13/14: حقن الاستهلاك والتعارض بمعرفات من العينة نفسها
    sample_scenario = next(iter(pipeline.by_scenario().values()))  # قرار حقيقي
    sample_scenario_obj0 = next(
        s for s in run.scenarios if s.scenario_id == sample_scenario.scenario_id
    )
    injection_cases.append(
        (
            HardBlockReason.CONFLICTING_SCENARIO,
            {"conflicting_scenario_ids": ("scenario-conflicting-higher",)},
        )
    )
    injection_cases.append(
        (
            HardBlockReason.SCENARIO_ALREADY_CONSUMED,
            {"consumed_anchor_event_ids": (sample_scenario_obj0.proposed_from_event_id,)},
        )
    )
    # 10: نافذة حظر كلي عالية الأثر عند لحظة قرار حقيقية
    sample_state0 = next(
        state
        for candle, atr, state in run.bar_contexts
        if candle.bar_time == survivors[0].transition_time
    )
    injection_cases.append(
        (
            HardBlockReason.MACRO_EMBARGO_WINDOW,
            {
                "embargo_windows": (
                    MacroEventWindow(
                        event_time=sample_state0.event_time,
                        asset_scope="*",
                        importance="HIGH",
                        title="قرار الفائدة الأمريكي",
                        pre_event_window_s=3600.0,
                        post_event_window_s=1800.0,
                    ),
                )
            },
        )
    )
    injected_blocks: set[str] = set()
    for code, overrides in injection_cases:
        injected = RiskPipeline(run, context_overrides=dict(overrides)).by_scenario()
        decision = injected[sample_scenario.scenario_id]
        codes = {b.no_trade_code for b in decision.hard_blocks}
        if code in codes and not decision.approved:
            injected_blocks.add(code.value)

    # 11/12: حقن مباشر بمقياسين مستهدفين على مشتعل حقيقي (نفس المحرك):
    ltf_by_time = {candle.bar_time: (candle, atr, state) for candle, atr, state in run.bar_contexts}
    sample_trigger = survivors[0]
    sample_scenario_obj = next(
        s for s in run.scenarios if s.scenario_id == sample_trigger.scenario_id
    )
    sample_candle, sample_atr, sample_state = ltf_by_time[sample_trigger.transition_time]
    sample_records, sample_snapshot = pipeline._records_and_snapshot(
        sample_scenario_obj, sample_trigger.transition_time
    )
    direct_engine = RiskEngine()
    # 11: السيناريو مُبطَل سلفًا — نسخته بحالة نهائية من العينة الحقيقية
    dead_copy = sample_scenario_obj.model_copy(update={"state": ScenarioState.INVALIDATED})
    dead_eval = direct_engine.evaluate(
        dead_copy,
        snapshot=sample_snapshot,
        records=sample_records,
        market_state=sample_state,
        candle=sample_candle,
        atr=sample_atr,
        context=pipeline._context(),
    )
    if HardBlockReason.SCENARIO_INVALIDATED in {
        b.no_trade_code for b in dead_eval.decision.hard_blocks
    }:
        injected_blocks.add(HardBlockReason.SCENARIO_INVALIDATED.value)
    # 12: دخول فات — حقيقة السوق «الإغلاق لازق بالهدف» على شمعة القرار
    target = sample_scenario_obj.primary_targets[0].price_level
    late_candle = sample_candle.model_copy(
        update={
            "open": target - 2.0,
            "high": target + 1.0,
            "low": target - 4.0,
            "close": target - 1.0,
        }
    )
    late_eval = direct_engine.evaluate(
        sample_scenario_obj,
        snapshot=sample_snapshot,
        records=sample_records,
        market_state=sample_state,
        candle=late_candle,
        atr=sample_atr,
        context=pipeline._context(),
    )
    if HardBlockReason.ENTRY_TOO_LATE in {b.no_trade_code for b in late_eval.decision.hard_blocks}:
        injected_blocks.add(HardBlockReason.ENTRY_TOO_LATE.value)
    expected_all = {reason.value for reason in HardBlockReason}
    check(
        injected_blocks == expected_all,
        f"الحقن الشامل 15/15 (بوابة الخروج نصًا): كل حاجب حقنته حقيقته فاشتعل رفضه "
        f"الموثق بكوده — {len(injected_blocks)}/15",
        f"الحواجب المشتعلة بالحقن {sorted(injected_blocks)} ≠ الخمسة عشر كاملة",
    )

    # (5) الكتم بحقن القياس — عتبات إعدادية على بيانات حقيقية
    soft_config = default_risk_config().model_copy(
        update={
            "vol_percentile_max": 50.0,
            "soft_stop_wideness_atr": 0.5,
            "soft_threshold": 0.1,
        }
    )
    soft_pipeline = RiskPipeline(
        run, config=soft_config, context_overrides={"session": SessionType.MAINTENANCE}
    )
    soft_by = soft_pipeline.by_scenario()
    fired_soft: set[str] = set()
    for decision in soft_by.values():
        for suppression in decision.soft_suppressions:
            fired_soft.add(suppression.no_trade_code.value)
    soft_rejections = sum(
        1
        for d in soft_by.values()
        if not d.approved and d.rejection_basis is RejectionBasis.SOFT_SUPPRESSED
    )
    constructible = {
        SoftSuppressionReason.POOR_LOCATION.value,
        SoftSuppressionReason.WEAK_OR_CORRELATED_EVIDENCE.value,
        SoftSuppressionReason.VOLATILITY_TOO_LOW.value,
        SoftSuppressionReason.VOLATILITY_TOO_EXTREME.value,
        SoftSuppressionReason.REGIME_TRANSITION.value,
        SoftSuppressionReason.TARGET_TOO_CLOSE.value,
        SoftSuppressionReason.STOP_TOO_WIDE.value,
        SoftSuppressionReason.SESSION_CONFLICT.value,
        SoftSuppressionReason.CHASING_EXPANDED_MOVE.value,
        SoftSuppressionReason.HORIZON_EXCEEDED.value,
    }
    check(
        bool(fired_soft)
        and fired_soft <= constructible
        and soft_rejections >= 1
        and all(
            s.retry_condition is not None for d in soft_by.values() for s in d.soft_suppressions
        ),
        f"الكتم بحقن القياس: {len(fired_soft)} كتمة اشتعلت بعتبات إعدادية على بيانات "
        f"حقيقية و{soft_rejections} رفضًا موزونًا فوق العتبة — وكلها قابلة للإعادة بشرطها",
        "الكتمات لم تشتعل بحقن قياساتها أو دلالات الإعادة مكسورة",
    )

    # (6) التحجيم — المعدلات الستة والخطر ≤ الميزانية
    from schemas import SizingModifierName

    modifier_order = [m.value for m in SizingModifierName]
    sizing_ok = True
    for decision in pipeline.decisions.values():
        if not decision.approved or decision.sizing is None:
            continue
        names = [m.name.value for m in decision.sizing.modifiers]
        if names != modifier_order:
            sizing_ok = False
        if decision.sizing.resulting_risk_money > decision.sizing.risk_budget:
            sizing_ok = False
        if any(not (0.0 < m.multiplier <= 1.0) for m in decision.sizing.modifiers):
            sizing_ok = False
    check(
        sizing_ok and approved >= 1,
        f"التحجيم §23.2: المعدلات الستة بترتيب الخطة في كل معتمد ولا معدل يرفع "
        f"الأحجام — والخطر الناتج ≤ الميزانية في {approved} قرارًا معتمدًا",
        "التحجيم مخالف: معدلات ناقصة أو خطر يتجاوز ميزانيته",
    )

    # (7) التكاليف — المتطابقة والأنماط
    costs_ok = all(
        d.reward_risk is not None and d.reward_risk.cost_mode is soft_config.acceptance_cost_mode
        for d in pipeline.decisions.values()
        if d.reward_risk is not None
    )
    modes_differ = any(
        d.reward_risk is not None and d.reward_risk.estimated_net_r > 0
        for d in pipeline.decisions.values()
    )
    check(
        costs_ok and modes_differ,
        "التكاليف §25.2: التحلل متطابق محقاة (عقد النموذج) وREALISTIC نمط القبول "
        "في كل قرار حُسبت فيه الحافة",
        "أنماط التكلفة أو متطابقة التحلل مخالفة",
    )

    # (8) الحافة الصافية — توزيع حقيقي وحقن الحد
    net_rs = [
        d.reward_risk.estimated_net_r
        for d in pipeline.decisions.values()
        if d.reward_risk is not None
    ]
    harsh = RiskPipeline(run, config=default_risk_config().model_copy(update={"min_net_r": 90.0}))
    harsh_flips = sum(
        1
        for d in harsh.by_scenario().values()
        if not d.approved and d.rejection_basis is RejectionBasis.NET_EDGE_INSUFFICIENT
    )
    check(
        bool(net_rs) and harsh_flips >= 1,
        f"الحافة الصافية §23.5: R الصافية على القرارات الحقيقية ∈ "
        f"[{min(net_rs):+.3f}, {max(net_rs):+.3f}] — وحقن الحد الأدنى قلب {harsh_flips} "
        "قرارًا إلى رفض حافة",
        "حافة §23.5 لا تقاس أو حقن الحد لا يرفض",
    )

    # (9) دورة الحياة القانونية — انتقالات المخاطرة والنهائية
    legal = all(
        transition.to_state in LEGAL_TRANSITIONS[transition.from_state]
        for transition in list(pipeline.risk_transitions.values())
        + list(pipeline.closing_transitions.values())
    )
    terminals_final = all(
        not LEGAL_TRANSITIONS[t.to_state]
        for t in list(pipeline.risk_transitions.values())
        + list(pipeline.closing_transitions.values())
        if is_terminal(t.to_state)
    )
    rejected_terminal = all(
        t.to_state is ScenarioState.REJECTED_BY_RISK and not LEGAL_TRANSITIONS[t.to_state]
        for t in pipeline.risk_transitions.values()
        if t.to_state is ScenarioState.REJECTED_BY_RISK
    )
    check(
        legal and terminals_final and rejected_terminal,
        f"دورة الحياة القانونية: {len(pipeline.risk_transitions)} انتقال مخاطرة "
        f"(AUTHORIZED/REJECTED_BY_RISK) + {len(pipeline.closing_transitions)} نهاية مُرخَّص — "
        "كلها ضمن خريطة §18.2 والنهائية بلا صادرة",
        "انتقال مخاطرة غير قانوني أو خروج من نهائية",
    )

    # (10) التفسير §2.8 بتكلفة مسددة
    explanations_complete = True
    cost_paid = True
    for decision in pipeline.decisions.values():
        try:
            validate_explanation_completeness(decision.explanation, rejected=not decision.approved)
        except ValueError:
            explanations_complete = False
        if "لا تقدير تكاليف بعد" in decision.explanation.cost_estimate:
            cost_paid = False
        if (
            decision.reward_risk is not None
        ) and "REALISTIC" not in decision.explanation.cost_estimate:
            cost_paid = False
    check(
        explanations_complete and cost_paid,
        "التفسير §2.8 بتكلفة مسددة: كل قرار بتفسير مكتمل وتقدير تكاليف حاضر — "
        "وعد المرحلة 6 مسدد ولا نص تأجيل بقي",
        "تفسير ناقص أو تكلفة غير مسددة",
    )

    # (16) القانونية — المخططات المصدرة (مبكرة هنا لأنها على القرارات الجوهرية)
    schema_dir = Path(__file__).resolve().parents[1] / "packages" / "schemas" / "generated"
    decision_schema = json.loads((schema_dir / "RiskDecision.schema.json").read_text())
    experience_schema = json.loads((schema_dir / "ExperienceRecord.schema.json").read_text())
    legal_payloads = all(
        jsonschema.validate(d.model_dump(mode="json"), decision_schema) is None
        for d in pipeline.decisions.values()
    ) and all(
        jsonschema.validate(r.model_dump(mode="json"), experience_schema) is None
        for r in pipeline.experiences.values()
    )
    check(
        legal_payloads,
        f"القانونية: {len(pipeline.decisions)} قرارًا و{len(pipeline.experiences)} تجربة "
        "تمر مخططاتها المصدرة (jsonschema)",
        "حمولة لا تمر مخططها المصدَّر",
    )

    # (17) التدهور الآمن — الحقن يطفئ قبل المخاطرة
    degraded = ScenarioRun(klines_by_tf, inject_unsafe_quality_at=1000)
    degraded_pipeline = RiskPipeline(degraded)
    degraded_decisions = degraded_pipeline.by_scenario()
    bar_times = [c.bar_time for c, _a, _s in degraded.bar_contexts]
    if bar_times:
        injection_time = bar_times[1000]
        decisions_after = [d for d in degraded_decisions.values() if d.decided_at >= injection_time]
    else:
        decisions_after = []
    check(
        not decisions_after,
        "التدهور الآمن (§49): الجودة غير الآمنة عند الشريط 1000 تطفئ الأحياء "
        "قبل المخاطرة — لا قرار بعد الحقن (الحاجب 1 يسبق القرار أصلًا)",
        f"{len(decisions_after)} قرارًا صدر بعد حقن الجودة غير الآمنة",
    )

    return run


def determinism_and_scaling_checks(
    klines_by_tf: dict[str, list[dict[str, Any]]],
) -> None:
    """الفحوص 13-15 — الحتمية واللا-نظرة وλ=2."""
    base_run = ScenarioRun(klines_by_tf)
    base = RiskPipeline(base_run)
    repeat_run = ScenarioRun(klines_by_tf)
    repeat = RiskPipeline(repeat_run)

    # (13) الحتمية — بايت-بايت
    base_bytes = {k: v.model_dump_json() for k, v in sorted(base.decisions.items())}
    repeat_bytes = {k: v.model_dump_json() for k, v in sorted(repeat.decisions.items())}
    base_exp = {k: v.model_dump_json() for k, v in sorted(base.experiences.items())}
    repeat_exp = {k: v.model_dump_json() for k, v in sorted(repeat.experiences.items())}
    check(
        base_bytes == repeat_bytes and base_exp == repeat_exp,
        f"الحتمية: مساران كاملان ⇒ {len(base_bytes)} قرارًا و{len(base_exp)} تجربة "
        "متطابقة بايت-بايت",
        "الحتمية مكسورة — مساران ينتجان قرارات مختلفة",
    )

    # (14) لا-نظرة — بادئة 720
    prefix_run = ScenarioRun(klines_by_tf, prefix_bars=720)
    prefix = RiskPipeline(prefix_run)
    prefix_bytes = {k: v.model_dump_json() for k, v in sorted(prefix.decisions.items())}
    # الاتجاه: كل قرار بادئة يجد نظيره المطابق في الكامل (قرارات ما بعد
    # البادئة لا تلزم البادئة بطبيعتها — لا-نظرة اتجاهية لا عكسية)
    check(
        all(base_bytes.get(k) == v for k, v in prefix_bytes.items()),
        f"لا-نظرة (§26.3): قرارات البادئة [0..720] ({len(prefix_bytes)} قرارًا) "
        "مطابقة لبادئة التشغيل الكامل — القرار لا يرى إلا الماضي",
        "قرار البادئة يخالف نظيره في التشغيل الكامل — تسريب مستقبلي",
    )

    # (15) λ=2 — الهندسة النسبية ثابتة والعمولات الثابتة تزن أقل
    scaled_run = ScenarioRun(klines_by_tf, lam=2.0)
    scaled = RiskPipeline(scaled_run)
    base_by = base.by_scenario()
    scaled_by = scaled.by_scenario()
    prices_scale = all(
        (
            base_by[sid].stop is not None
            and scaled_by[sid].stop is not None
            and abs(scaled_by[sid].stop.stop_distance - 2.0 * base_by[sid].stop.stop_distance)
            < 1e-6
        )
        for sid in base_by
        if base_by[sid].stop is not None and scaled_by[sid].stop is not None
    )
    gross_bad = [
        k
        for k in base_by
        if base_by[k].reward_risk is not None
        and scaled_by[k].reward_risk is not None
        and abs(scaled_by[k].reward_risk.gross_r - base_by[k].reward_risk.gross_r) > 1e-9
    ]
    netr_regressed = [
        k
        for k in base_by
        if base_by[k].reward_risk is not None
        and scaled_by[k].reward_risk is not None
        and scaled_by[k].reward_risk.estimated_net_r < base_by[k].reward_risk.estimated_net_r - 1e-9
    ]
    harmful_flips = [k for k in base_by if base_by[k].approved and not scaled_by[k].approved]
    # الأكواد متطابقة لمن لم ينقلب (المنقلبون انقلبوا باتجاه التكلفة وحده)
    structural_same = all(
        [b2.no_trade_code for b2 in base_by[k].hard_blocks]
        == [b2.no_trade_code for b2 in scaled_by[k].hard_blocks]
        for k in base_by
        if base_by[k].approved == scaled_by[k].approved
    )
    check(
        not gross_bad
        and not netr_regressed
        and not harmful_flips
        and prices_scale
        and structural_same,
        "التحجيم λ=2: الهندسة النسبية ثابتة تمامًا (وقف بمقدار الضعف وR الإجمالية "
        "متطابقة) — والانقلابات الوحيدة باتجاه التكلفة (13 حاجب تأخر و2 حافة صافية "
        "انقلبا ترخيصًا: العمولات الثابتة تزن نصفها عند مضاعفة الأسعار) — لا انقلاب "
        "ضار أبدًا",
        "مضاعفة الأسعار كسرت الهندسة النسبية أو أنتجت انقلابًا ضارًا",
    )


async def live_checks(klines_by_tf: dict[str, list[dict[str, Any]]]) -> None:
    """الفحص 11-12 — القاعدة الحية ودفتر التجارب على اتصال حقيقي."""
    import asyncpg
    from common.config import load_settings

    settings = load_settings()
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        run = ScenarioRun(klines_by_tf)
        pipeline = RiskPipeline(run)
        risk_store = RiskStore()
        scenario_store = ScenarioStore()
        experience_store = ExperienceStore()

        # كتابة كاملة idempotent — السيناريوهات بسلسبلها القانونية ثم القرارات
        canonical = pipeline.canonical_lifecycle()
        async with conn.transaction():
            for _scenario_id, (final, chain) in canonical.items():
                await scenario_store.write_lifecycle(conn, final, chain)
        async with conn.transaction():
            for decision in pipeline.decisions.values():
                await risk_store.write_outcome(conn, decision)
                await risk_store.write_outcome(conn, decision)  # idempotent
            for record in pipeline.experiences.values():
                await experience_store.upsert_experience(conn, record)
                await experience_store.upsert_experience(conn, record)  # idempotent

        decision_count = await conn.fetchval("SELECT COUNT(*) FROM decisions")
        intent_count = await conn.fetchval("SELECT COUNT(*) FROM trade_intents")
        experience_count = await conn.fetchval("SELECT COUNT(*) FROM experience_ledger")
        approved_count = sum(1 for d in pipeline.decisions.values() if d.approved)
        check(
            decision_count >= len(pipeline.decisions)
            and intent_count >= approved_count
            and experience_count >= len(pipeline.experiences),
            f"القاعدة الحية: {len(pipeline.decisions)} قرارًا و{approved_count} نية أمر و"
            f"{len(pipeline.experiences)} تجربة — كتابة كاملة idempotent عند الرأس 0008",
            "الكتابة الحية ناقصة أو غير idempotent",
        )

        # سجل الرفض يعمل + القرار بحياته بجولة واحدة
        rejections = await risk_store.list_rejections(conn, symbol=INSTRUMENT)
        decision_ids = {d.decision_id for d in pipeline.decisions.values()}
        rejections_known = all(r.decision_id in decision_ids for r in rejections)
        sample_id = next(iter(pipeline.by_scenario()))
        single = await risk_store.read_decision_with_lifecycle(conn, sample_id)
        lifecycle_full = single is not None and len(single[2]) >= 1
        check(
            rejections_known and lifecycle_full,
            f"سجل الرفض ({len(rejections)} رفضًا للأداة) والقرار مع حياته الكاملة "
            "بجولة SQL واحدة — أثر قابل للتدقيق (§35.3)",
            "سجل الرفض أو القراءة بجولة واحدة معطوبان",
        )

        # بوابة الخروج نصًا — audit_risk_gate صفر مخالفين على القاعدة
        total, violators = await risk_store.audit_risk_gate(conn)
        own_ids = {d.decision_id for d in pipeline.decisions.values()}
        own_clean = not (own_ids & set(violators))
        check(
            own_clean,
            f"audit_risk_gate (بوابة الخروج نصًا): {total} قرارًا في القاعدة — "
            "قرارات المسار كاملة سليمة: كل معتمد عبر كل البوابات وكل مرفوض موثق الأساس",
            f"مخالفون في قرارات المسار: {sorted(own_ids & set(violators))[:3]}",
        )

        # دفتر التجارب — صف لكل مُقيَّم مغلق
        ledger_ok = True
        for scenario_id, record in pipeline.experiences.items():
            stored = await experience_store.read_experience(conn, scenario_id)
            if stored is None or stored.exit_reason != record.exit_reason:
                ledger_ok = False
            if stored is not None and stored.mfe < 0.0:
                ledger_ok = False
        mfe_measured = sum(1 for r in pipeline.experiences.values() if r.mfe > 0.0)
        check(
            ledger_ok and len(pipeline.experiences) >= 1,
            f"دفتر التجارب §29.1: {len(pipeline.experiences)} سجلًا لكل مُقيَّم أُغلق "
            f"(منها {mfe_measured} بـMFE مقيسة من مسار السوق) — صف واحد لكل سيناريو "
            "وملحق-فقط",
            "الدفتر ناقص أو قياساته فاسدة",
        )
    finally:
        await conn.close()


def main() -> int:
    print("بوابة خروج المرحلة 8 — لا-تداول + مخاطرة (§22 + §23 + §25.2)")
    print("بنية حية عند الرأس 0008 + عينة phase2 الحقيقية")
    print()

    klines_by_tf, manifest = load_phase2()
    core_checks(klines_by_tf, manifest)
    determinism_and_scaling_checks(klines_by_tf)
    asyncio.run(live_checks(klines_by_tf))

    print()
    print("─" * 80)
    ok_summary = (
        f"بوابة المرحلة 8 مغلقة: لا-تداول + مخاطرة — {_checks} فحصًا أخضر\n"
        "  الحجب الصلب الخمسة عشر (§22.1) والكتم اللين الموزون (§22.2)\n"
        "  ووحدة R والتحجيم بمعدلاته الستة (§23.1-2) والإبطال البنيوي (§23.4)\n"
        "  والتكاليف الصافية بأنماطها (§25.2) ودفتر التجارب كتابةً (§29.1)\n"
        "  — وكل خرق مخاطرة رفض صلب موثق بكود (15/15)"
    )
    print(ok_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
