"""محرك السيناريوهات — قائد دورة الحياة شريطًا فوق شريط (§33.4).

التدفق الحرفي من §33.4 «Evidence to scenario»:

    candidate location → generate scenarios → attach supporting evidence
    → attach opposing evidence → calculate raw scenario score → apply
    vetoes → create/update lifecycle state

المحرك يجمعه كله: ``on_anchor`` يولّد المقترحات عند حدث سيولة مؤكد فوق
موقع (D-04)، و``on_bar`` يقود الحياة بشريط إطار التنفيذ المغلق بترتيب
حتمي موثق:

1. **جودة البيانات** (§18.5 شرط 5): لقطة الحالة غير الآمنة تُلغي كل
   الحية بلا استثناء — التدهور الآمن لا التداول الأعمى (§49).
2. **الإبطال** (§18.5 كاملًا): الحارس الخمسة (انجراج/حدث معاكس/قبول
   سعري/انقضاء) لكل حي — المسودة تموت قبل ترقيتها كالنشيطة سواء.
3. **الترقية** (§18.4): إعادة بناء سجل الدليل من التاريخ المتراكم
   ولقطة الدمج — مجموعتان داعمتان على الأقل ولا veto ⇒ ACTIVE،
   وتحديث قائمتَي الدليل والدرجة كل شريط مسودة.
4. **المشغل** (§18.4): آلة المشغل تتقدم بالشريط — الاشتعال يعبر حارس
   الانجراف (§18.4 «moved too far») فإما TRIGGERED بتحديث صورة الدليل
   النهائية أو المنظّمة من نهايات §18.2 (الشرط 6 إبطال، والشرط 4
   انقضاء EXPIRED، والشرط 5 إلغاء بالجودة).
5. **التنافس** (7.4): المتضادان المتزامنان TRIGGERED يُحسمان بالأسبقية
   — الخاسر SUPPRESSED بسبب يسمي فائزه.

الحتمية: لا ساعة ولا عشوائية — الزمن من ``bar_time`` الشمعة المارة،
وما بعد TRIGGERED (AUTHORIZED فصاعدًا) تقوده المراحل 8+ (بوابة الخروج
7: لا ترخيص بلا مشغل وإبطال معرّفين — المحرك يقود حتى TRIGGERED).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from fusion.compute import FusionEngine
from fusion.ledger import EvidenceLedgerBuilder
from fusion.mapping import HARD_BLOCK_EVENT_TYPES
from liquidity.targets import TargetMap
from schemas import (
    Candle,
    DataQuality,
    EventType,
    LiquidityZone,
    MarketStateSnapshot,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
    ScenarioTransition,
    payload_digest,
)
from schemas.liquidity import BreakAcceptEventPayload, SweepEventPayload
from schemas.structure import DisplacementEventPayload, StructureBreakPayload

from .competition import CompetingScenario, resolve_conflicts
from .invalidation import InvalidationEvaluator, entry_drift_atr
from .lifecycle import TERMINAL_STATES, apply_transition
from .parameter_sets import ScenarioConfig
from .proposer import (
    MIN_SUPPORTING_GROUPS,
    AnchorEvent,
    ProposalAbsence,
    ProposalOutcome,
    ScenarioProposer,
    score_from_raw,
)
from .triggers import StructureEventRef, TriggerRuntime, advance

__all__ = ["ScenarioEngine"]

#: جودات البيانات التي تصل معالجة القرار (§7.4) — DELAYED بموافقة صريحة.
_DECISION_SAFE_QUALITIES: frozenset[DataQuality] = frozenset(
    {DataQuality.HEALTHY, DataQuality.DELAYED}
)


class AnalysisEvent(Protocol):
    """حدث تحليل مؤكد — عقد القراءة نفسه الذي تنتجه كواشف المراحل 3-5a."""

    @property
    def event_type(self) -> EventType: ...

    @property
    def event_time(self) -> datetime: ...

    @property
    def payload(self) -> Any: ...


class ScenarioEngine:
    """قائد دورة الحياة — حتمي: نفس المدخلات ⇒ نفس المقترحات والانتقالات.

    خدمة أداة واحدة: الرمز يُلتقط من أول مرسِم والأجنبي يُرفض صاخبًا —
    التنافس (7.4) وإدارة الأحداث متجانسة الأداة بلا خلط. إعادة المرسِم
    نفسه idempotent (معرفات uuid5 — الروح D-07): السيناريوهات القائمة
    لا تُستنسخ ثانية.
    """

    def __init__(
        self,
        config: ScenarioConfig | None = None,
        *,
        execution_timeframe: str = "1m",
        symbol: str | None = None,
    ) -> None:
        self._config = config if config is not None else ScenarioConfig()
        self._proposer = ScenarioProposer(self._config, execution_timeframe=execution_timeframe)
        self._ledger = EvidenceLedgerBuilder()
        self._fusion = FusionEngine()
        self._invalidator = InvalidationEvaluator(self._config.max_entry_drift_atr)
        self._symbol = symbol
        self._scenarios: dict[str, Scenario] = {}
        self._runtimes: dict[str, TriggerRuntime] = {}
        self._supporting_groups: dict[str, int] = {}
        self._events: list[AnalysisEvent] = []
        self._seen_events: set[tuple[EventType, datetime, str]] = set()
        self._state: MarketStateSnapshot | None = None
        self._veto_reasons: list[str] = []
        self._transitions: list[ScenarioTransition] = []

    # ───────────────────────── الخصائص ─────────────────────────

    @property
    def config(self) -> ScenarioConfig:
        """الإعداد المجمّد — للقراءة والبصمة."""
        return self._config

    @property
    def symbol(self) -> str | None:
        """رمز الأداة الخدمة — من أول مرسِم أو من البناء."""
        return self._symbol

    @property
    def veto_reasons(self) -> tuple[str, ...]:
        """أسباب الحجب الصلب المرصودة — منطق بولياني خارج الحساب (D-03-د)."""
        return tuple(self._veto_reasons)

    def scenarios(self) -> tuple[Scenario, ...]:
        """كل السيناريوهات الحالية بترتيب إنشائها (إدراج المعرف)."""
        return tuple(self._scenarios.values())

    def live_scenarios(self) -> tuple[Scenario, ...]:
        """الأحياء حصرًا — ما لم يبلغ حالة نهائية بعد."""
        return tuple(s for s in self._scenarios.values() if s.state not in TERMINAL_STATES)

    def transitions(self) -> tuple[ScenarioTransition, ...]:
        """سجل الانتقالات الكامل ملحق-فقط — §31.3 بترتيب الوقوع."""
        return tuple(self._transitions)

    # ───────────────────────── التوليد (D-04) ─────────────────────────

    def on_anchor(
        self,
        event_type: EventType,
        event_time: datetime,
        payload: SweepEventPayload | BreakAcceptEventPayload,
        *,
        zone: LiquidityZone,
        targets: TargetMap,
        state: MarketStateSnapshot,
        atr: float,
    ) -> ProposalOutcome:
        """استنساخ القوالب عند مرسِم — تسجيل المقترحات وتغذية التاريخ.

        المرسِم نفسه يدخل تاريخ الأحداث (دليل المقترحات اللاحقة يراه)
        ولقطة الحالة تُعتمد آخر حالة معروفة. إعادة الإرسال idempotent:
        المقترحات القائمة بمعرفاتها تُعاد كما هي بلا استنساخ مكرر.

        حرس الجودة (§7.4): فقط HEALTHY وDELAYED يصلان معالجة القرار —
        المرسِم فوق لقطة غير آمنة لا يُستنسخ أصلًا (غياب موثق كامل) فلا
        ولادة سيناريوهات في بيئة لا تُتخذ فيها قرارات.
        """
        if state.data_quality not in _DECISION_SAFE_QUALITIES:
            return ProposalOutcome(
                proposals=(),
                absences=tuple(
                    ProposalAbsence(
                        template=template,
                        reason=(
                            f"جودة بيانات غير آمنة عند المرسِم "
                            f"({state.data_quality.value}) — لا معالجة قرار "
                            "أثناء الجودة غير الآمنة (§7.4/§18.5 شرط 5)"
                        ),
                    )
                    for template in ScenarioTemplate
                ),
            )
        self._assert_symbol(payload.instrument)
        outcome = self._proposer.propose(
            AnchorEvent(event_type, event_time, payload),
            zone=zone,
            targets=targets,
            state=state,
            atr=atr,
        )
        for proposal in outcome.proposals:
            self._scenarios.setdefault(proposal.scenario_id, proposal)
            self._runtimes.setdefault(proposal.scenario_id, TriggerRuntime())
        self._feed(AnchorEvent(event_type, event_time, payload))
        self._adopt_state(state)
        return outcome

    # ───────────────────────── القيادة الشريطية ─────────────────────────

    def on_bar(
        self,
        candle: Candle,
        *,
        analysis_events: Sequence[AnalysisEvent] = (),
        state: MarketStateSnapshot | None = None,
        atr: float,
    ) -> tuple[ScenarioTransition, ...]:
        """تقييم شريطة إطار تنفيذ واحدة — الترتيب الحتمي الموثق أعلاه.

        :param candle: شمعة إطار التنفيذ **المغلقة** (لا-نظرة §26.3).
        :param analysis_events: أحداث التحليل المؤكدة عند الشمعة (كل
            الأطر) — الحجب الصلب يُوجَّه إلى أسباب الـveto لا السجل.
        :param state: لقطة الحالة عند الشمعة إن نُشرت (تصير المرجع).
        :param atr: ATR الشمعة — مقياس حارس الانجراف ونطاقات المشغلات؛
            إلزامي موجب (قبله لا سيناريوهات أصلًا — عقود الدافئ).
        :returns: انتقالات هذه الشريطة بترتيب وقوعها.
        """
        if atr <= 0.0:
            raise ValueError(f"ATR غير موجب: {atr} — شريط بلا مقياس لا يُقيَّم")
        self._assert_symbol(candle.instrument_id)
        now = candle.bar_time
        for event in analysis_events:
            self._feed(event)
        if state is not None:
            self._adopt_state(state)

        produced: list[ScenarioTransition] = []

        # (1) جودة البيانات — البيئة غير الآمنة تُطفئ كل الحية (§49).
        if self._state is not None and self._state.data_quality not in _DECISION_SAFE_QUALITIES:
            for scenario in self._live():
                reason = (
                    "جودة بيانات غير آمنة (§18.5 شرط 5): اللقطة تعلن "
                    f"{self._state.data_quality.value} — فقط HEALTHY/DELAYED "
                    "يصلان معالجة القرار (§7.4)"
                )
                produced.append(
                    self._transition(
                        scenario,
                        ScenarioState.CANCELLED_BY_DATA_QUALITY,
                        now,
                        reason,
                    )
                )
            # لا شيء حي بعدها — الشريطة تنتهي هنا.
            return tuple(produced)

        # (2) الإبطال الفوري — الحارس الخمسة لكل حي (المسودة كالنشيطة):
        # الحكم منظّم يحمل حالته الهدف من نهايات §18.2 البديلة الثلاث
        # (الإبطال البنيوي INVALIDATED والانقضاء EXPIRED والإلغاء بالجودة).
        for scenario in self._live():
            verdict = self._invalidator.check(
                scenario,
                candle=candle,
                events=self._bar_event_pairs(analysis_events),
                expired=now > scenario.expiry_time,
            )
            if verdict is not None:
                produced.append(self._transition(scenario, verdict.state, now, verdict.reason))

        # (3) الترقية — مجموعتان داعمتان ولا veto (§18.4 حرفيًا).
        for scenario in self._live():
            if scenario.state is not ScenarioState.DRAFT:
                continue
            refreshed, supporting, vetoed = self._refresh_evidence(scenario, now)
            if supporting >= MIN_SUPPORTING_GROUPS and not vetoed:
                reason = (
                    f"ترقية §18.4: {supporting} مجموعات دليل مستقلة داعمة "
                    f"(الحد {MIN_SUPPORTING_GROUPS}) ولا حجب صلب — الدرجة "
                    f"{refreshed.scenario_score:.4f} (ليست احتمالًا §2.6)"
                )
                produced.append(self._transition(refreshed, ScenarioState.ACTIVE, now, reason))

        # (4) المشغل — الاشتعال يعبر حارس الانجراف (§18.4).
        refs = self._structure_refs(analysis_events)
        for scenario in self._live():
            if scenario.state is not ScenarioState.ACTIVE:
                continue
            runtime = self._runtimes[scenario.scenario_id]
            fired = advance(
                scenario.trigger_definition,
                runtime,
                candle=candle,
                structure_events=refs,
                atr=atr,
            )
            if not fired:
                continue
            drift = entry_drift_atr(scenario, float(candle.close), atr)
            if drift > self._config.max_entry_drift_atr:
                verdict = self._invalidator.check(
                    scenario,
                    candle=candle,
                    events=(),
                    entry_drift_exceeded=True,
                )
                assert verdict is not None  # حارس الانجراف يعلل دائمًا
                produced.append(self._transition(scenario, verdict.state, now, verdict.reason))
                continue
            refreshed, supporting, _vetoed = self._refresh_evidence(scenario, now)
            self._supporting_groups[scenario.scenario_id] = supporting
            trigger_reason = (
                f"مشغل {scenario.trigger_definition.condition_type} رُصد فعليًا عند "
                f"{now.isoformat()} والانجراف {drift:.2f} ATR ضمن الحد "
                f"{self._config.max_entry_drift_atr:.2f} — صورة الدليل النهائية: "
                f"{supporting} مجموعة داعمة والدرجة "
                f"{refreshed.scenario_score:.4f}"
            )
            produced.append(
                self._transition(refreshed, ScenarioState.TRIGGERED, now, trigger_reason)
            )

        # (5) التنافس — المتضادان المتزامنان يُحسمان بالأسبقية (7.4).
        triggered = [
            CompetingScenario(
                scenario,
                self._supporting_groups.get(scenario.scenario_id, 0),
            )
            for scenario in self._live()
            if scenario.state is ScenarioState.TRIGGERED
        ]
        if triggered:
            outcome = resolve_conflicts(triggered)
            for loser, _winner, reason in outcome.suppressions:
                produced.append(self._transition(loser, ScenarioState.SUPPRESSED, now, reason))

        return tuple(produced)

    # ───────────────────────── الداخل ─────────────────────────

    def _live(self) -> list[Scenario]:
        """الأحياء بترتيب الإدراج الحتمي (إدراج المعرف)."""
        return [s for s in self._scenarios.values() if s.state not in TERMINAL_STATES]

    def _transition(
        self, scenario: Scenario, to_state: ScenarioState, when: datetime, reason: str
    ) -> ScenarioTransition:
        """انتقال موحد — تحديث النسخة الجارية وتسجيل السجل."""
        updated, record = apply_transition(scenario, to_state, transition_time=when, reason=reason)
        self._scenarios[scenario.scenario_id] = updated
        self._transitions.append(record)
        return record

    def _refresh_evidence(self, scenario: Scenario, as_of: datetime) -> tuple[Scenario, int, bool]:
        """إعادة بناء سجل الدليل والدرجة من التاريخ المتراكم — §33.4.

        :returns: (السيناريو محدث القائمتين والدرجة، عدد المجموعات
            الداعمة، هل هناك veto نشط).
        """
        records = self._ledger.build(
            list(self._events),
            scenario_id=scenario.scenario_id,
            direction=scenario.direction,
            as_of=as_of,
            market_state=self._state,
        )
        snapshot = self._fusion.compute(
            records,
            scenario_id=scenario.scenario_id,
            direction=scenario.direction,
            fusion_time=as_of,
            veto_reasons=self._veto_reasons,
        )
        supporting = sum(1 for group in snapshot.group_scores if group.score > 0.0)
        self._supporting_groups[scenario.scenario_id] = supporting
        refreshed = scenario.model_copy(
            update={
                "supporting_evidence": [r.evidence_id for r in records if not r.opposition],
                "opposing_evidence": [r.evidence_id for r in records if r.opposition],
                "scenario_score": score_from_raw(snapshot.raw_evidence_score),
            }
        )
        self._scenarios[scenario.scenario_id] = refreshed
        return refreshed, supporting, snapshot.vetoed

    def _feed(self, event: AnalysisEvent) -> None:
        """تغذية تاريخ الأحداث idempotent — الحجب الصلب يوجه إلى الـveto.

        التسليم at-least-once عقيدة الناقل (§5.3): الحدث نفسه (النوع
        والوقت والبصمة) لا يدخل السجل مرتين — إعادة الإرسال تحدّث ولا
        تكرر (روح D-07) وإلا صُدّ بانيُ السجل بمعرف مكرر.
        """
        if event.event_type in HARD_BLOCK_EVENT_TYPES:
            reason = f"hard-block:{event.event_type.value}"
            if reason not in self._veto_reasons:
                self._veto_reasons.append(reason)
            return
        key = (
            event.event_type,
            event.event_time,
            payload_digest(event.payload),
        )
        if key in self._seen_events:
            return
        self._seen_events.add(key)
        self._events.append(event)

    def _adopt_state(self, state: MarketStateSnapshot) -> None:
        """اعتماد لقطة الحالة المرجعية — آخر ما نُشر."""
        self._state = state

    def _assert_symbol(self, symbol: str) -> None:
        """حرس تجانس الأداة — الأولى تعلن الرمز والأجنبية تُرفض."""
        if self._symbol is None:
            self._symbol = symbol
        elif self._symbol != symbol:
            raise ValueError(
                f"حدث أداة أجنبية عن محرك السيناريوهات: {symbol} ≠ {self._symbol} — "
                "محرك لكل أداة (التنافس وإدارة التاريخ متجانسان)"
            )

    def _bar_event_pairs(
        self, analysis_events: Sequence[AnalysisEvent]
    ) -> tuple[tuple[EventType, Any], ...]:
        """أزواج (نوع، حمولة) لأحداث الشريطة — مدخل مقيّم الإبطال."""
        return tuple((event.event_type, event.payload) for event in analysis_events)

    def _structure_refs(
        self, analysis_events: Sequence[AnalysisEvent]
    ) -> tuple[StructureEventRef, ...]:
        """إحالات أحداث البنية من أحداث الشريطة — مسار المشغلات الموحد."""
        refs: list[StructureEventRef] = []
        for event in analysis_events:
            payload = event.payload
            if isinstance(payload, StructureBreakPayload):
                refs.append(
                    StructureEventRef(event.event_type, payload.timeframe, payload.break_direction)
                )
            elif isinstance(payload, DisplacementEventPayload):
                refs.append(
                    StructureEventRef(event.event_type, payload.timeframe, payload.direction)
                )
        return tuple(refs)
