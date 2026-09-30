"""باني سجل الدليل — أحداث التحليل المكتشفة → سجلات §19.1 قابلة للدمج.

المسؤوليات (قلب المهمتين 6.1 توصيلاً و6.3 ارتباطًا):

- **الاصطفاف النسبي للسيناريو**: القطبية الذاتية للحدث (من حمولته) تُضرب
  في إشارة اتجاه السيناريو فتصير ``direction_score`` نسبيًا ±1 — المتحالف
  يساند (+1) والمعاكس يدخل قائمة المعارضة صريحًا (§19.5) بإشارته
  السالبة التي تخفض ولا تلغي.
- **مجموعات الارتباط (§19.4)**: الأحداث المؤكَّدة عند الشمعة نفسها على
  الإطار نفسه للأداة نفسها دفعةٌ واحدة منبثقة غالبًا عن الاندفاع نفسه
  (مثال §19.4: BOS + إزاحة + إغلاق قوي + جسم كبير) — فتشارك
  ``correlation_group_id`` ويُرتب أفرادها بإمكانات مساهمتهم (c_i بخصم
  1) تنازليًا: الأول كامل الاستقلالية وكل تالٍ يُخصم γ^k هندسيًا.
- **الطراوة (§19.1)**: اضمحلال خطي من 1 عند شمعة التأكيد إلى 0 بعد
  ``freshness_ttl_bars`` من أشرطة إطار الحدث نفسه — قياس زمني بمقياس
  الحدث لا عتبة كونية؛ و``as_of`` بعد أي حدث مستقبلي يُرفض صاخبًا
  (حرس اللا-نظرة-مستقبلية §26.3).
- **الدليل المشتق من الحالة**: انحياز الإطار الأعلى المنشور في لقطة
  الحالة يدخل دليلًا موثق المصدر ``market_state.htf_bias`` (§9.2 يسميه
  «contextual evidence» حرفيًا) — لا يُختلق حدث بث، بل سجل §19.1
  بمصدر معلن.
- **الحتمية**: لا ساعة ولا عشوائية — المعرفات uuid5 فوق هوية كاملة
  (روح D-07) وإعادة البناء من المدخلات نفسها تعطي السجل نفسه بايت-بايت.

الحجب الصلب (وزن None §20) ليس دليلًا أبدًا (D-03-د): يصل إليه الباني
يرفض صاخبًا — توجيهه إلى ``veto_reasons`` مسؤولية المستدعي.
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel
from schemas import (
    Direction,
    EventType,
    EvidenceRecord,
    MarketStateSnapshot,
)

from .compute import contribution
from .mapping import (
    EVENT_EVIDENCE_GROUPS,
    HARD_BLOCK_EVENT_TYPES,
    extract_polarity,
    extract_raw_strength,
    htf_event_for_bias,
    prior_weight_for,
)
from .parameter_sets import FusionConfig

__all__ = ["EvidenceLedgerBuilder", "evidence_id_for"]

#: مساحة اسم دليل الدمج — uuid5 فوق NAMESPACE_URL بمفتاح نطاق معلن.
_EVIDENCE_NAMESPACE: uuid_module.UUID = uuid_module.uuid5(
    uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/fusion-evidence"
)

#: الأطر الستة المدعومة → طول الشمعة بالثواني — مرآة عقد الأطر في
#: ingestion (D-05: 1H/15m/1m افتراضيًا و4H/5m بديلًا و1d) — الإطار
#: خارجها يُرفض صاخبًا لا يُخمَّن.
_TIMEFRAME_SECONDS: dict[str, float] = {
    "1m": 60.0,
    "5m": 300.0,
    "15m": 900.0,
    "1h": 3600.0,
    "4h": 14400.0,
    "1d": 86400.0,
}

#: مصدر دليل الانحياز المشتق من الحالة — معلن في كل سجل ينتجه.
_HTF_SOURCE = "market_state.htf_bias"


class EmittedAnalysisEvent(Protocol):
    """حدث تحليل مكشوف — عقد البنية نفسه الذي تنتجه كواشف المراحل 3-5a.

    خصائص قراءة فقط (نمط ``analysis_publisher``): النوع §20 ووقت التأكيد
    (شمعة القرار — لا-نظرة §26.3) والحمولة الموثقة النموذج.
    """

    @property
    def event_type(self) -> EventType: ...

    @property
    def event_time(self) -> datetime: ...

    @property
    def payload(self) -> BaseModel: ...


def _timeframe_seconds(timeframe: str) -> float:
    """طول شمعة الإطار بالثواني — رفض صاخب للأطر غير المدعومة."""
    try:
        return _TIMEFRAME_SECONDS[timeframe]
    except KeyError as exc:
        supported = ", ".join(_TIMEFRAME_SECONDS)
        raise ValueError(
            f"إطار غير مدعوم: {timeframe!r} — الأطر المعتمدة حصرًا: {supported} (D-05)"
        ) from exc


def _scenario_sign(direction: Direction) -> float:
    """إشارة اتجاه السيناريو — LONG موجبة وSHORT سالبة وFLAT مرفوض."""
    if direction is Direction.LONG:
        return 1.0
    if direction is Direction.SHORT:
        return -1.0
    raise ValueError(f"اتجاه سيناريو غير اتجاهي: {direction} — الدمج يقيّم LONG/SHORT حصرًا")


def evidence_id_for(scenario_id: str, event_key: str) -> str:
    """معرف سجل دليل حتمي — uuid5 فوق هوية السيناريو والحدث معًا.

    نفس (السيناريو، الحدث) ⇒ نفس المعرف دائمًا فإعادة البناء idempotent
    والإرسال المتكرر يحدّث صفه (روح D-07).
    """
    return str(uuid_module.uuid5(_EVIDENCE_NAMESPACE, f"evidence|{scenario_id}|{event_key}"))


def _freshness(event_time: datetime, as_of: datetime, ttl_seconds: float) -> float:
    """اضمحلال خطي [0, 1] — كامل عند التأكيد، صفر بعد العمر النامي.

    الحرس: حدث أحدث من لحظة القرار ``as_of`` خرق اللا-نظرة-المستقبلية
    (§26.3) فيُرفض صاخبًا لا يُمرر بطراوة قصوى صامتة.
    """
    age = (as_of - event_time).total_seconds()
    if age < 0.0:
        raise ValueError(
            f"حدث أحدث من لحظة القرار: {event_time.isoformat()} > {as_of.isoformat()} — "
            "خرق لا-نظرة-مستقبلية §26.3 يُرفض صاخبًا"
        )
    if ttl_seconds <= 0.0:
        raise ValueError(f"عمر طراوة غير موجب: {ttl_seconds}")
    return max(0.0, 1.0 - age / ttl_seconds)


class EvidenceLedgerBuilder:
    """باني سجل الدليل — نقي وحتمي: نفس المدخلات ⇒ نفس السجل.

    الاستخدام: جمّع أحداث الكواشف المؤكدة (بترتيب الوصول) ولقطة الحالة
    إن وُجدت، ثم ابنِ السجل عند لحظة قرار ``as_of`` صريحة، ومرره إلى
    ``FusionEngine.compute``.
    """

    def __init__(self, config: FusionConfig | None = None) -> None:
        self._config = config if config is not None else FusionConfig()

    @property
    def config(self) -> FusionConfig:
        """الإعداد المجمّد — للقراءة والبصمة."""
        return self._config

    def build(
        self,
        events: Sequence[EmittedAnalysisEvent],
        *,
        scenario_id: str,
        direction: Direction,
        as_of: datetime,
        market_state: MarketStateSnapshot | None = None,
    ) -> list[EvidenceRecord]:
        """سجل الدليل الكامل لسيناريو واحد عند لحظة قرار واحدة.

        :param events: أحداث الكواشف بترتيب الوصول — الدفعة الواحدة
            (نفس الأداة/الإطار/شريطة التأكيد) تُخصم استقلاليتها داخليًا.
        :param scenario_id: هوية السيناريو — تدخل معرف كل سجل فلا يتسرب
            دليل سيناريو إلى آخر.
        :param direction: اتجاه السيناريو (LONG/SHORT) — الاصطفاف نسبي
            له.
        :param as_of: لحظة القرار — الطراوة تُقاس إليها وأي حدث أحدث
            منها يُرفض (لا-نظرة).
        :param market_state: لقطة الحالة المنشورة لحظة القرار — انحيازها
            المؤكد يدخل دليل بنية مشتقًا من الحالة بمصدر معلن.
        """
        sign = _scenario_sign(direction)
        records: list[EvidenceRecord] = []

        # ── الدليل المشتق من الحالة أولًا: السياق يسبق الأحداث ──
        if market_state is not None:
            htf = self._htf_record(market_state, scenario_id=scenario_id, sign=sign, as_of=as_of)
            if htf is not None:
                records.append(htf)

        # ── أحداث الكواشف بترتيب الوصول ──
        pending: list[EvidenceRecord] = []
        for event in events:
            pending.append(
                self._event_record(event, scenario_id=scenario_id, sign=sign, as_of=as_of)
            )

        # ── مجموعات الارتباط والخصم الهندسي (§19.4) ثم التسلسل النهائي ──
        records.extend(self._apply_independence_discount(pending))
        return records

    # ── بناء السجلات ──

    def _event_record(
        self,
        event: EmittedAnalysisEvent,
        *,
        scenario_id: str,
        sign: float,
        as_of: datetime,
    ) -> EvidenceRecord:
        """سجل دليل واحد من حدث مكشوف — كل الحقول من الحمولة والإعداد."""
        event_type = event.event_type
        if event_type in HARD_BLOCK_EVENT_TYPES:
            raise ValueError(
                f"حدث حجب صلب وصل باني السجل: {event_type} — الحجب ليس دليلًا "
                "اتجاهيًا (وزن None §20) ويوجه إلى veto_reasons (D-03-د)"
            )
        payload = event.payload
        data = payload.model_dump()
        instrument = str(data["instrument"])
        timeframe = str(data["timeframe"])

        polarity = extract_polarity(event_type, payload)
        direction_score = polarity * sign
        ttl = self._config.freshness_ttl_bars * _timeframe_seconds(timeframe)
        event_key = f"{event_type.value}|{instrument}|{timeframe}|{event.event_time.isoformat()}"
        return EvidenceRecord(
            evidence_id=evidence_id_for(scenario_id, event_key),
            group=EVENT_EVIDENCE_GROUPS[event_type],
            event_type=event_type,
            direction_score=direction_score,
            raw_strength=extract_raw_strength(event_type, payload),
            quality=self._config.default_quality,
            freshness=_freshness(event.event_time, as_of, ttl),
            independence_discount=1.0,  # يُستبدل بالخصم بعد الترتيب
            prior_weight=prior_weight_for(event_type),
            context_modifier=self._config.default_context_modifier,
            opposition=direction_score < 0.0,
            source=f"analysis-event:{event_type.value}",
            correlation_group_id=f"{instrument}|{timeframe}|{event.event_time.isoformat()}",
        )

    def _htf_record(
        self,
        market_state: MarketStateSnapshot,
        *,
        scenario_id: str,
        sign: float,
        as_of: datetime,
    ) -> EvidenceRecord | None:
        """دليل الانحياز المشتق من الحالة — None للانحياز غير المؤكد.

        القوة 1.0 موثقة: الانحياز المنشور حالة مؤكدة ثنائية عند هذا الطور
        (§9.2) — الوزن الابتدائي 0.90 من §20 هو الذي يحمل المقدار.
        """
        htf_type = htf_event_for_bias(market_state.htf_bias)
        if htf_type is None:
            return None
        bias_sign = 1.0 if htf_type is EventType.HTF_BULLISH else -1.0
        direction_score = bias_sign * sign
        ttl = self._config.freshness_ttl_bars * _timeframe_seconds(market_state.timeframe)
        state_key = f"htf|{market_state.htf_bias.value}|{market_state.event_time.isoformat()}"
        return EvidenceRecord(
            evidence_id=evidence_id_for(scenario_id, state_key),
            group=EVENT_EVIDENCE_GROUPS[htf_type],
            event_type=htf_type,
            direction_score=direction_score,
            raw_strength=1.0,
            quality=self._config.default_quality,
            freshness=_freshness(market_state.event_time, as_of, ttl),
            independence_discount=1.0,  # دليل الحالة خارج دفعات الأحداث
            prior_weight=prior_weight_for(htf_type),
            context_modifier=self._config.default_context_modifier,
            opposition=direction_score < 0.0,
            source=_HTF_SOURCE,
            correlation_group_id=None,
        )

    # ── مجموعات الارتباط وخصم الاستقلالية (§19.4) ──

    def _apply_independence_discount(self, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """الخصم الهندسي داخل كل دفعة — الترتيب بإمكان المساهمة.

        داخل مجموعة الارتباط نفسها يُرتب الأفراد بإمكان مساهمتهم (|c_i|
        بخصم 1 — الترتيب قبل الخصم وإلا دار) تنازليًا، وكسر التعادل
        بمعرف السجل (حتمية تامة): الأول يبقى 1.0 وكل تالٍ γ^k.

        دفعات الارتباط لا تمتد عبر الشموع (مجموعة الارتباط هي الشمعة
        نفسها) فالبناء التزايدي والكامل يعطيان الخصم نفسه — خصيصة
        لا-نظرة إضافية يفحصها verify-phase6.
        """
        by_batch: dict[str, list[EvidenceRecord]] = {}
        for record in records:
            if record.correlation_group_id is None:
                continue
            by_batch.setdefault(record.correlation_group_id, []).append(record)

        decay = self._config.independence_decay
        discounted: dict[str, float] = {}
        for batch in by_batch.values():
            ranked = sorted(
                batch,
                key=lambda item: (-abs(_potential(item)), item.evidence_id),
            )
            for rank, record in enumerate(ranked):
                discounted[record.evidence_id] = decay**rank

        return [
            record.model_copy(
                update={"independence_discount": discounted.get(record.evidence_id, 1.0)}
            )
            for record in records
        ]


def _potential(record: EvidenceRecord) -> float:
    """إمكانية المساهمة — c_i بافتراض استقلالية كاملة (خصم 1).

    أساس ترتيب الخصم: لا دورية (الترتيب قبل الخصم) ومستقل عن تركيب
    الدفعة خارج مجموعتها.
    """
    return contribution(record.model_copy(update={"independence_discount": 1.0}))
