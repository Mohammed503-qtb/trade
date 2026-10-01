"""المُقترِح الحتمي المعدَّد (D-04) — القوالب الثلاثة عند حدث مؤكد فوق موقع.

«انطلاقًا من حدث مؤكد عند موقع سيولة مرسوم، تُستنسخ القوالب الثلاثة
كمقترحات DRAFT مرفقة بتعريفات الهدف (§10.5) والإبطال والزعنفة
الزمنية. لا سيناريو بلا موقع + آلية + مُطلق + إبطال (تحقيق §18.3
إلزاميًا)» — D-04 حرفيًا.

قواعد الاستنساخ الحتمية القابلة للعد (كل غياب إعلان صريح لا صمت):

1. **المرسِم**: حدثان سيوليان موقعيان حصرًا — اجتياح مؤكد أو كسر-قبول،
   كلاهما يحمل ``zone_id`` (§10.4 شرط 5). أي حدث آخر يُرفض صاخبًا.
2. **REVERSAL**: من الاجتياح ضد جهته (الرفض المعاكس) ومن الكسر-القبول
   ضد اتجاهه (فشل القبول/الفخ).
3. **BREAKOUT**: من الاجتياح باتجاهه (فشل الرفض ⇒ قبول خلف القاع
   الحتمي المعاد اشتقاقه) ومن الكسر-القبول باتجاهه (صمود إعادة
   الاختبار).
4. **CONTINUATION**: باتجاه انحياز الإطار الأعلى المؤكد حصرًا —
   الانحياز غير المؤكد غياب موثق (§21.2 «HTF structure aligned»).
5. **الهدف شرط وجود**: لا استنساخ لقالب باتجاه بلا هدف سيولة §10.5 في
   جهته («Target: nearest meaningful ... liquidity» §18.3) — غياب موثق.
6. **القاع الحتمي المعاد اشتقاقه**: ``excursion_atr`` مقاسة خلف الحافة
   البعيدة حرفيًا في الكاشف (سطر القياس نفسه) فالقاع = الحافة البعيدة
   ± ``excursion_atr × ATR`` لحظة الحدث — إعادة اشتقاق مضبوطة لا تقريب.

كل مقترح يولد بكامل عناصر §18.3 التسعة: السياق (لقطة الحالة) والموقع
(المنطقة) والآلية (سلسلة §21.2) والمشغل والإبطال والمسار المتوقع
(الأهداف) والتقدير البنيوي للمكافأة/المخاطرة (المسافات المعيارية —
جزء التكاليف §25.2 موثق مؤجل للمرحلة 8) والأفق الزمني (الزعنفة)
والتناقضات (قائمة المعارضة من سجل الدليل عند الولادة).
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from datetime import datetime, timedelta

from fusion.compute import FusionEngine
from fusion.ledger import EvidenceLedgerBuilder
from liquidity.targets import TargetEntry, TargetMap
from pydantic import BaseModel
from schemas import (
    Direction,
    EventType,
    InvalidationRule,
    LiquidityZone,
    MarketStateSnapshot,
    PriceZone,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
    TargetZone,
    TriggerDefinition,
    payload_digest,
)
from schemas.liquidity import BreakAcceptEventPayload, LiquiditySide, SweepEventPayload
from structure.store import deterministic_event_id

from .parameter_sets import ScenarioConfig
from .templates import (
    anchor_event_types,
    breakout_direction_for_break_accept,
    breakout_direction_for_sweep,
    continuation_direction_for_bias,
    reversal_direction_for_break_accept,
    reversal_direction_for_sweep,
    thesis_for,
)

__all__ = [
    "AnchorEvent",
    "ProposalAbsence",
    "ProposalOutcome",
    "ScenarioProposer",
    "scenario_id_for",
    "score_from_raw",
]

#: مساحة اسم السيناريو الحتمي — uuid5 فوق NAMESPACE_URL بمفتاح نطاق.
_SCENARIO_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/scenario"
)

#: ثابت مواصفة لا معامل إعدادي: «at least two independent evidence
#: groups» (§18.4) — العدد اثنان حرفيًا؛ جعله قابلًا للضبط دعوة لتخريب
#: بوابة الترقية.
MIN_SUPPORTING_GROUPS = 2

#: طول شمعة إطار التنفيذ بالثواني — الزعنفة الزمنية (D-04) بأشرطة
#: إطار التنفيذ (D-05: 1m افتراضيًا). مرآة عقد الأطر في ledger نفسه.
_TIMEFRAME_SECONDS: dict[str, float] = {
    "1m": 60.0,
    "5m": 300.0,
    "15m": 900.0,
    "1h": 3600.0,
    "4h": 14400.0,
    "1d": 86400.0,
}


def score_from_raw(raw_evidence_score: float) -> float:
    """إعادة إسقاط حتمية موثقة: الدرجة الخام الموقعة → ``[0, 1]``.

    حقل ``scenario_score`` (§18.1) من نوع ``UnitInterval`` منذ المرحلة 0؛
    الدمج يخرج درجة موقعة (−1, +1) فتُسقط خطيًا: 0.5 = دليل متعادل
    صافٍ، وفوقها مساندة صافية وتحتها معارضة صافية — **ليست احتمالًا
    أبدًا** (§2.6/§19.6) والمعايرة شأن المرحلة 9.
    """
    return (raw_evidence_score + 1.0) / 2.0


def scenario_id_for(
    template: ScenarioTemplate,
    anchor_event_id: str,
    zone_id: str,
    direction: Direction,
) -> str:
    """معرف السيناريو الحتمي — uuid5 فوق (القالب، الحدث، الموقع، الاتجاه).

    نفس المرسِم والموقع والاتجاه ⇒ نفس المعرف دائمًا: إعادة اقتراح
    الحدث نفسه idempotent (روح D-07) — كل اتجاه وكل قالب مقترحان
    مميزان لأنهما تفسيران منافسان لا نسخة واحدة.
    """
    key = f"{template.value}|{anchor_event_id}|{zone_id}|{direction.value}"
    return str(uuid_module.uuid5(_SCENARIO_NAMESPACE, key))


@dataclass(frozen=True)
class AnchorEvent:
    """الحدث المرسي بثوب بروتوكول باني السجل — بلا حالة ولا ساعة.

    نفس عقد ``EmittedAnalysisEvent`` (بنية القراءة فقط): النوع §20 ووقت
    تأكيد الشمعة والحمولة الموثقة النموذج.
    """

    event_type: EventType
    event_time: datetime
    payload: BaseModel


@dataclass(frozen=True)
class ProposalAbsence:
    """غياب موثق — قالب لم يُستنسخ من مرسِم والسبب معلن.

    «الغياب إعلان صريح لا صمت موافقة» (نمط خريطة الدليل نفسه): كل غياب
    يحمل قالبَه وسببَه فيُعدّ ويُدقَّق بدل أن يمر كأن شيئًا لم يكن.
    """

    template: ScenarioTemplate
    reason: str


@dataclass(frozen=True)
class ProposalOutcome:
    """حصيلة اقتراح مرسِم واحد — مقترحاته وغيوبه الموثقة معًا."""

    proposals: tuple[Scenario, ...]
    absences: tuple[ProposalAbsence, ...]


class ScenarioProposer:
    """مُقترِح حتمي — نفس المدخلات ⇒ نفس المقترحات بايت-بايت.

    لا ساعة ولا عشوائية: الهندسة كلها من الحمولة والمنطقة والأهداف
    المارة، والدليل عند الولادة يبنى بسجل الدمج من المرسِم نفسه + لقطة
    الحالة فيولد المقترح بدرجته وقائمتي مساندته ومعارضته (§18.3
    «Contradictions» إلزامي).
    """

    def __init__(
        self,
        config: ScenarioConfig | None = None,
        *,
        execution_timeframe: str = "1m",
    ) -> None:
        if execution_timeframe not in _TIMEFRAME_SECONDS:
            supported = ", ".join(_TIMEFRAME_SECONDS)
            raise ValueError(
                f"إطار تنفيذ غير مدعوم: {execution_timeframe!r} — المعتمد: {supported} (D-05)"
            )
        self._config = config if config is not None else ScenarioConfig()
        self._execution_timeframe = execution_timeframe
        self._ledger = EvidenceLedgerBuilder()
        self._fusion = FusionEngine()

    @property
    def config(self) -> ScenarioConfig:
        """الإعداد المجمّد — للقراءة والبصمة."""
        return self._config

    @property
    def execution_timeframe(self) -> str:
        """إطار التنفيذ (D-05) — مرجع الزعنفة الزمنية ومشغلات البنية."""
        return self._execution_timeframe

    # ───────────────────────── الواجهة ─────────────────────────

    def propose(
        self,
        event: AnchorEvent,
        *,
        zone: LiquidityZone,
        targets: TargetMap,
        state: MarketStateSnapshot,
        atr: float,
    ) -> ProposalOutcome:
        """استنساخ القوالب الثلاثة من مرسِم مؤكد — D-04.

        :param event: المرسِم السيولي الموقعي (اجتياح/كسر-قبول بـzone_id).
        :param zone: لقطة المنطقة المرسمة لحظة الحدث (§10.2).
        :param targets: خريطة أهداف §10.5 عند سعر الحدث (بعد استبعاد
            المرسِم نفسه — المستهلَك/المجتاح ليس هدفًا).
        :param state: لقطة حالة السوق عند الشمعة (السياق — عنصر §18.3 الأول).
        :param atr: ATR لحظة الحدث — مقياس إعادة اشتقاق القاع والعوازل
            (نفس ATR الذي طبَّع به الكاشف ``excursion_atr``).
        :raises ValueError: مرسِم غير موقعي، منطقة أجنبية، أو ATR غير موجب.
        """
        event_type = event.event_type
        payload = event.payload
        if event_type not in anchor_event_types:
            raise ValueError(
                f"مرسِم غير موقعي: {event_type} — الاستنساخ من أحداث السيولة "
                "المؤكدة ذات zone_id حصرًا (D-04)"
            )
        if not isinstance(payload, SweepEventPayload | BreakAcceptEventPayload):
            raise ValueError(
                f"حمولة مرسِم غير موثقة: {type(payload).__name__} — عقد D-04 "
                "SweepEventPayload/BreakAcceptEventPayload حصرًا"
            )
        if atr <= 0.0:
            raise ValueError(f"ATR غير موجب: {atr} — مقياس الهندسة النسبية كله")
        if payload.instrument != zone.instrument or payload.timeframe != zone.timeframe:
            raise ValueError(
                "منطقة أجنبية عن المرسِم: "
                f"{zone.instrument}/{zone.timeframe} ≠ {payload.instrument}/{payload.timeframe}"
            )
        if payload.zone_id != zone.zone_id:
            raise ValueError(f"منطقة غير المرسمة: {payload.zone_id} ≠ {zone.zone_id} (§10.4 شرط 5)")

        anchor_event_id = str(
            deterministic_event_id(
                event_type.value,
                payload.instrument,
                payload.timeframe,
                event.event_time,
                payload_digest(payload),
            )
        )
        location: dict[str, object] = {
            "zone": zone.model_dump(mode="json"),
            "anchor_event_id": anchor_event_id,
            "anchor_event_type": event_type.value,
            "anchor_timeframe": payload.timeframe,
            "atr_at_anchor": float(atr),
        }

        is_sweep = isinstance(payload, SweepEventPayload)
        buffer = self._config.invalidation_buffer_atr * atr
        expiry_unit = _TIMEFRAME_SECONDS[self._execution_timeframe]

        proposals: list[Scenario] = []
        absences: list[ProposalAbsence] = []

        # ── REVERSAL: ضد جهة الاجتياح / ضد اتجاه القبول ──
        if is_sweep:
            assert isinstance(payload, SweepEventPayload)
            direction = reversal_direction_for_sweep(payload)
            extreme = self._excursion_extreme(payload, zone, atr)
            self._try_instantiate(
                proposals,
                absences,
                template=ScenarioTemplate.REVERSAL,
                direction=direction,
                event=event,
                anchor_event_id=anchor_event_id,
                zone=zone,
                targets=targets,
                state=state,
                location=location,
                entry_zone=PriceZone(price_low=zone.price_low, price_high=zone.price_high),
                invalidation=InvalidationRule(
                    structural_level=extreme,
                    volatility_buffer=buffer,
                    accept_through=True,
                ),
                trigger=TriggerDefinition(
                    condition_type="DISPLACEMENT_CONFIRM",
                    params={"direction": direction.value, "timeframe": self._execution_timeframe},
                ),
                detail=(
                    f"اجتياح {payload.zone_side.value} عند {zone.zone_id} بعمق "
                    f"{payload.excursion_atr:.2f} ATR ورفض خلال {payload.reclaim_bars} شموع — "
                    f"الإبطال خلف القاع {extreme:.2f} بعازلة {buffer:.2f}"
                ),
                expiry_unit=expiry_unit,
            )
        else:
            assert isinstance(payload, BreakAcceptEventPayload)
            direction = reversal_direction_for_break_accept(payload)
            extreme = self._accept_extreme(payload, zone, atr)
            reclaim_level = (
                zone.price_low if payload.zone_side is LiquiditySide.BUY_SIDE else zone.price_high
            )
            self._try_instantiate(
                proposals,
                absences,
                template=ScenarioTemplate.REVERSAL,
                direction=direction,
                event=event,
                anchor_event_id=anchor_event_id,
                zone=zone,
                targets=targets,
                state=state,
                location=location,
                entry_zone=PriceZone(price_low=zone.price_low, price_high=zone.price_high),
                invalidation=InvalidationRule(
                    structural_level=extreme,
                    volatility_buffer=buffer,
                    accept_through=True,
                ),
                trigger=TriggerDefinition(
                    condition_type="ZONE_RECLAIM",
                    params={"level": float(reclaim_level), "direction": direction.value},
                ),
                detail=(
                    f"كسر-قبول {payload.zone_side.value} عند {zone.zone_id} بنسبة قبول "
                    f"{payload.acceptance_ratio:.2f} — فرضية الفخ: عودة كاملة خلف "
                    f"{reclaim_level:.2f} والإبطال فوق القبول {extreme:.2f}"
                ),
                expiry_unit=expiry_unit,
            )

        # ── CONTINUATION: باتجاه الانحياز المؤكد حصرًا ──
        cont_direction = continuation_direction_for_bias(state.htf_bias)
        if cont_direction is None:
            absences.append(
                ProposalAbsence(
                    template=ScenarioTemplate.CONTINUATION,
                    reason=(
                        f"انحياز الإطار الأعلى {state.htf_bias.value} غير مؤكد — "
                        "لا اصطفاف بنية يوجب الاستمرار (§21.2 «HTF structure aligned»)"
                    ),
                )
            )
        else:
            entry: PriceZone
            invalidation: InvalidationRule
            if is_sweep:
                assert isinstance(payload, SweepEventPayload)
                entry = PriceZone(price_low=zone.price_low, price_high=zone.price_high)
                detail = (
                    f"ارتداد إلى موقع الاجتياح {zone.zone_id} ({payload.zone_side.value}) "
                    f"مع انحياز {state.htf_bias.value} — BOS داخلي بالاتجاه مشغله"
                )
            else:
                assert isinstance(payload, BreakAcceptEventPayload)
                boundary = self._accept_boundary(payload, zone)
                band = self._config.retest_band_atr * atr
                entry = PriceZone(price_low=boundary - band, price_high=boundary + band)
                detail = (
                    f"إعادة اختبار حافة القبول {boundary:.2f} مع انحياز "
                    f"{state.htf_bias.value} — BOS داخلي بالاتجاه مشغله"
                )
            invalidation = self._location_failure_rule(zone, cont_direction, buffer)
            self._try_instantiate(
                proposals,
                absences,
                template=ScenarioTemplate.CONTINUATION,
                direction=cont_direction,
                event=event,
                anchor_event_id=anchor_event_id,
                zone=zone,
                targets=targets,
                state=state,
                location=location,
                entry_zone=entry,
                invalidation=invalidation,
                trigger=TriggerDefinition(
                    condition_type="INTERNAL_BOS",
                    params={
                        "direction": cont_direction.value,
                        "timeframe": self._execution_timeframe,
                    },
                ),
                detail=detail,
                expiry_unit=expiry_unit,
            )

        # ── BREAKOUT: باتجاه الاختراق بحسب مصدر الاستنساخ ──
        if is_sweep:
            assert isinstance(payload, SweepEventPayload)
            direction = breakout_direction_for_sweep(payload)
            extreme = self._excursion_extreme(payload, zone, atr)
            near_edge = (
                zone.price_high if payload.zone_side is LiquiditySide.SELL_SIDE else zone.price_low
            )
            band = self._config.retest_band_atr * atr
            self._try_instantiate(
                proposals,
                absences,
                template=ScenarioTemplate.BREAKOUT,
                direction=direction,
                event=event,
                anchor_event_id=anchor_event_id,
                zone=zone,
                targets=targets,
                state=state,
                location=location,
                entry_zone=PriceZone(price_low=extreme - band, price_high=extreme + band),
                invalidation=InvalidationRule(
                    structural_level=near_edge,
                    volatility_buffer=buffer,
                    accept_through=True,
                ),
                trigger=TriggerDefinition(
                    condition_type="ACCEPTANCE_BEYOND",
                    params={
                        "level": float(extreme),
                        "direction": direction.value,
                        "window": self._config.acceptance_window_bars,
                    },
                ),
                detail=(
                    f"فشل رفض الاجتياح {payload.zone_side.value} عند {zone.zone_id}: قبول "
                    f"{self._config.acceptance_window_bars} إغلاقات خلف القاع {extreme:.2f} "
                    f"ثم دخول عند نطاقه — الإبطال باسترجاع {near_edge:.2f}"
                ),
                expiry_unit=expiry_unit,
            )
        else:
            assert isinstance(payload, BreakAcceptEventPayload)
            direction = breakout_direction_for_break_accept(payload)
            boundary = self._accept_boundary(payload, zone)
            far_edge = (
                zone.price_low if payload.zone_side is LiquiditySide.BUY_SIDE else zone.price_high
            )
            band = self._config.retest_band_atr * atr
            self._try_instantiate(
                proposals,
                absences,
                template=ScenarioTemplate.BREAKOUT,
                direction=direction,
                event=event,
                anchor_event_id=anchor_event_id,
                zone=zone,
                targets=targets,
                state=state,
                location=location,
                entry_zone=PriceZone(price_low=boundary - band, price_high=boundary + band),
                invalidation=InvalidationRule(
                    structural_level=far_edge,
                    volatility_buffer=buffer,
                    accept_through=True,
                ),
                trigger=TriggerDefinition(
                    condition_type="RETEST_HOLD",
                    params={
                        "boundary": float(boundary),
                        "direction": direction.value,
                        "band_atr": self._config.retest_band_atr,
                    },
                ),
                detail=(
                    f"قبول {payload.zone_side.value} عند {zone.zone_id} بنسبة "
                    f"{payload.acceptance_ratio:.2f} — الدخول عند إعادة اختبار "
                    f"{boundary:.2f} الصامدة، والإبطال بعودة كاملة خلف {far_edge:.2f}"
                ),
                expiry_unit=expiry_unit,
            )

        return ProposalOutcome(proposals=tuple(proposals), absences=tuple(absences))

    # ───────────────────────── البناء الداخلي ─────────────────────────

    def _try_instantiate(
        self,
        proposals: list[Scenario],
        absences: list[ProposalAbsence],
        *,
        template: ScenarioTemplate,
        direction: Direction,
        event: AnchorEvent,
        anchor_event_id: str,
        zone: LiquidityZone,
        targets: TargetMap,
        state: MarketStateSnapshot,
        location: dict[str, object],
        entry_zone: PriceZone,
        invalidation: InvalidationRule,
        trigger: TriggerDefinition,
        detail: str,
        expiry_unit: float,
    ) -> None:
        """محاولة استنساخ قالب واحد — غياب الهدف غياب موثق لا صمت.

        عنصرا «المسار المتوقع» و«المكافأة/المخاطرة» (§18.3) يشترطان هدفًا
        في جهة السيناريو: أقرب هدف هو الأساسي والبقية ثانويون (ترتيب
        §10.5 الحتمي)، ومستوى الهدف حافة الدخول القريبة (أول لمس).
        """
        side = targets.above if direction is Direction.LONG else targets.below
        if not side:
            side_name = "فوق" if direction is Direction.LONG else "تحت"
            absences.append(
                ProposalAbsence(
                    template=template,
                    reason=(
                        f"لا هدف سيولة §10.5 {side_name} السعر عند {zone.zone_id} — "
                        "بلا هدف لا مسار متوقع ولا تقدير مكافأة/مخاطرة (§18.3 إلزامي)"
                    ),
                )
            )
            return

        primary, *secondary = side
        scenario_id = scenario_id_for(template, anchor_event_id, zone.zone_id, direction)

        # دليل الولادة: المرسِم + الحالة عند شمعة التأكيد (الاصطفاف نسبي)
        records = self._ledger.build(
            [event],
            scenario_id=scenario_id,
            direction=direction,
            as_of=event.event_time,
            market_state=state,
        )
        snapshot = self._fusion.compute(
            records,
            scenario_id=scenario_id,
            direction=direction,
            fusion_time=event.event_time,
        )
        supporting = [r.evidence_id for r in records if not r.opposition]
        opposing = [r.evidence_id for r in records if r.opposition]

        expiry_time = event.event_time + timedelta(
            seconds=expiry_unit * self._config.expiry_bars[template]
        )
        proposals.append(
            Scenario(
                scenario_id=scenario_id,
                symbol=zone.instrument,
                direction=direction,
                regime=state.regime,
                context_snapshot=state,
                location_snapshot=dict(location),
                thesis=thesis_for(template, zone_id=zone.zone_id, detail=detail),
                supporting_evidence=supporting,
                opposing_evidence=opposing,
                trigger_definition=trigger,
                entry_zone=entry_zone,
                invalidation=invalidation,
                primary_targets=[self._target_zone(primary)],
                secondary_targets=[self._target_zone(t) for t in secondary],
                expiry_time=expiry_time,
                state=ScenarioState.DRAFT,
                scenario_score=score_from_raw(snapshot.raw_evidence_score),
                template=template,
                proposed_from_event_id=anchor_event_id,
            )
        )

    # ───────────────────────── هندسات مساعدة ─────────────────────────

    @staticmethod
    def _excursion_extreme(payload: SweepEventPayload, zone: LiquidityZone, atr: float) -> float:
        """القاع الحتمي المعاد اشتقاقه — الحافة البعيدة ± العمق المقيس.

        ``excursion_atr = max_excursion / ATR`` والقياس خلف الحافة البعيدة
        حرفيًا في الكاشف (BUY_SIDE: ``high − price_high``؛ SELL_SIDE:
        ``price_low − low``) — فالقاع المعاد = الحافة البعيدة ±
        ``excursion_atr × ATR`` بلا تقريب.
        """
        if payload.zone_side is LiquiditySide.BUY_SIDE:
            return float(zone.price_high) + payload.excursion_atr * atr
        return float(zone.price_low) - payload.excursion_atr * atr

    @staticmethod
    def _accept_extreme(payload: BreakAcceptEventPayload, zone: LiquidityZone, atr: float) -> float:
        """أقصى القبول المعاد اشتقاقه — نفس اشتقاق الاجتياح للحمولة الأخت."""
        if payload.zone_side is LiquiditySide.BUY_SIDE:
            return float(zone.price_high) + payload.excursion_atr * atr
        return float(zone.price_low) - payload.excursion_atr * atr

    @staticmethod
    def _accept_boundary(payload: BreakAcceptEventPayload, zone: LiquidityZone) -> float:
        """حافة القبول — الحافة البعيدة التي قُبل خلفها (إعادة اختبارها المشغل)."""
        if payload.zone_side is LiquiditySide.BUY_SIDE:
            return float(zone.price_high)
        return float(zone.price_low)

    @staticmethod
    def _location_failure_rule(
        zone: LiquidityZone, direction: Direction, buffer: float
    ) -> InvalidationRule:
        """إبطال فشل الموقع — الحافة البعيدة في الجهة المعاكسة للاتجاه.

        LONG: الموقع يفشل بهبوط كامل خلف قاع المنطقة؛ SHORT: خلف قمتها.
        """
        if direction is Direction.LONG:
            return InvalidationRule(
                structural_level=float(zone.price_low),
                volatility_buffer=buffer,
                accept_through=True,
            )
        return InvalidationRule(
            structural_level=float(zone.price_high),
            volatility_buffer=buffer,
            accept_through=True,
        )

    @staticmethod
    def _target_zone(entry: TargetEntry) -> TargetZone:
        """هدف §10.5 → عقد الهدف — مستوى حافة الدخول القريبة (أول لمس)."""
        if entry.zone.side is LiquiditySide.BUY_SIDE:
            return TargetZone(price_level=float(entry.zone.price_low), zone_id=entry.zone.zone_id)
        return TargetZone(price_level=float(entry.zone.price_high), zone_id=entry.zone.zone_id)
