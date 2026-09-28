"""كاشف الاجتياح — التسلسل الخمسي الشروط وتصنيفه الخمسي (§10.4).

المصدر: §10.4 («الاجتياح تسلسل لا فتيل واحد» — الشروط الخمسة والتصنيف
الخمسي)، §20 (صفوف LIQUIDITY_SWEEP_HIGH/LOW بوزن 0.95 وBREAK_AND_ACCEPT_
HIGH/LOW بوزن 0.85 وقياساتهما)، §26.3 (لا-نظرة-مستقبلية)، §38.1 (fixtures
الاجتياح التام والفاشل)، §31.3 (دورة حياة المنطقة).

العقود الموثقة في هذه الوحدة (تُختبر حرفيًا في tests/unit/test_sweep.py):

- **الشروط الخمسة (§10.4) كلها ضرورية**: (1) منطقة سيولة قائمة مسبقًا —
  الكاشف يقيّم الشمعة t ضد خريطة [0..t−1] قبل تحديثها بالشمعة t نفسها
  (ترتيب الواجهة :class:`~liquidity.engine.LiquidityEngine`)، فلا تُجتاح
  منطقةٌ بشمعة تأسيسها أبدًا؛ (2) السعر يتداول عبر المنطقة (اختراق الحافة
  البعيدة)؛ (3) التجاوز يبلغ عتبة نسبةً إلى التقلب المحلي **وعرض المنطقة**؛
  (4) السعر إما يسترجع المنطقة أو يُظهر استجابة استمرار تميز الاجتياح من
  الكسر الحقيقي؛ (5) كل حمولة مبثوثة موقوتة ومربوطة بمنطقتها المستهلَكة
  (``zone_id`` + ``bar_time`` + ``test_count_at_event``). سقوط أي شرط ⇒ لا
  بث (مختبر شرطًا شرطًا).

- **العتبة المطلوبة (شرط 3) — الصيغة المعتمدة الموثقة**:

    ``required = max(atr × SWEEP_TOLERANCE, عرض_المنطقة × width_fraction)``

  الجزء الأول عتبة تطبيعية صرفة من
  :class:`~market_state.volatility.VolatilityState` (لا مسار آخر لأي عتبة
  سعرية)، والجزء الثاني إدماج «relative to … zone width» من نص §10.4 —
  ``width_fraction`` نقطة انطلاق إعدادية معلنة (0.5) قابلة للمعايرة.
  المنطقة صفرية العرض يكفيها جزء التقلب وحده. العتبة تقاس بالتقلب الحي
  للشمعة الجارية مقابل أقصى تجاوز مراكم، والراية (``penetration_reached``)
  لاصقة متى ما تحققت.

- **الحتمية الصرفة**: نفس الشموع والخريطة ⇒ نفس الأحداث بالتطابق التام —
  مسح المناطق بترتيب إنشائها في الخريطة، وحلقة تفاعل واحدة لكل منطقة في
  كل لحظة، ولا عشوائية ولا ساعة.

- **لا-نظرة-مستقبلية (§26.3)**: كل حسم يقع على شمعة مقفلة ويحمل
  ``bar_time`` تلك الشمعة (شرط 5) — البث لا يسبق اكتمال التسلسل (§27).

- **الصخب في التحقق**: يعمل الكاشف خلف تحقق الخريطة
  (:meth:`~liquidity.zones.LiquidityMapEngine.validate_bar`) — الواجهة
  تستدعي التحقق قبل الكاشف فلا طفرة قبل رفض شمعة فاسدة؛ استخدام الكاشف
  المستقل يتطلب احترام العقد نفسه من المستدعي.

آلة التفاعل لكل منطقة (توثيق شامل — التصنيفات الخمسة §10.4):

1. **IDLE → APPROACHED (لمس)**: تقاطع مدى الشمعة ``[low, high]`` مع فاصل
   المنطقة (حواف مغلقة) — التفاعل متماثل أياً كانت جهة الوصول (الحسم
   لغته اجتياحية والحساب واحد). عند اللمس: تُحصى الاختبار في الخريطة
   (test_count+1 وlast_test_time) ويُلتقط نطاق المنطقة **لحظة البدء** —
   التفاعل يقيس على النطاق الملتقط طوال التسلسل ولا يتابع تحريك الخريطة
   أثناءه (عقد موثق: مناطق الجلسة المتحركة والحدود لا تفسد التسلسل).
2. **رصد التغلغل (شرط 2)**: أي اختراق للحافة البعيدة (BUY: ``high ≥
   price_high`` / SELL: ``low ≤ price_low``) يحدّث أقصى تجاوز ويُسجل في
   الخريطة (كسر الامتلاء)، وتُفتح **نافذة التقييم** (``eval_window`` شموع)
   عند أول تغلغل متاح المقياس — من ذلك البار فصاعدًا.
3. **الحسم داخل النافذة (شرط 4)** بفحص الإغلاق كل شمعة نافذة:
   - **استرجاع** (إغلاق صراحةً خلف الحافة القريبة: BUY ``close <
     price_low`` / SELL ``close > price_high``): مع ``penetration_reached``
     ⇒ **CONFIRMED_SWEEP** وبث ``LIQUIDITY_SWEEP_HIGH/LOW`` (‏``reclaim_bars``
     = شموع من أول تغلغل حتى شمعة الاسترجاع؛ صفر = اجتياح بفتيل شمعة
     واحدة) والمنطقة → SWEPT؛ بدونه ⇒ **FAILED_SWEEP** بلا بث. كلاهما يسجل
     جودة الرفض في الخريطة (عمق الرفض المعياري).
   - **قبول** (عدد الإغلاقات المؤهلة — إغلاق صراحةً وراء الحافة البعيدة —
     يبلغ ``accept_min_closes`` مع ``penetration_reached``) ⇒
     **BREAK_AND_ACCEPT** وبث ``BREAK_AND_ACCEPT_HIGH/LOW`` بـ``acceptance_ratio``
     = المؤهلة ÷ إغلاقات النافذة، والمنطقة → CONSUMED.
   - **انقضاء النافذة بلا حسم**: الإغلاق وراء الحافة البعيدة ⇒
     **UNKNOWN**؛ داخله ⇒ **PARTIAL_SWEEP** — كلاهما بلا بث البتة (ليسا في
     قاموس §20؛ يخزَّن في ``sweep_status`` للمنطقة فقط) والمنطقة تبقى
     ACTIVE بحصيلة اختبارها محفوظة.
4. **تفاعل بلا نافذة بعد** (لم يخترق الحافة البعيدة): مغادرة جهة القرب
   بإغلاق ⇒ **FAILED_SWEEP** (اجتياح قارب فأخفق — fixture «near-miss»
   §38.1) بلا بث والمنطقة تبقى ACTIVE؛ وإلا يبقى التفاعل مفتوحًا.
5. **العبور القافز الحاسم (إبطال)**: منطقة بلا تفاعل لم تُلمس شمعةً مداها
   كله وراء الحافة البعيدة، وأغلقت بهامش ``STRUCTURAL_LEVEL_BUFFER`` وراءها
   ⇒ المنطقة → INVALIDATED بلا بث (عبور بلا تسلسل §20 — توثيق جدول
   انتقالات الخريطة (أ)).
6. مناطق متعددة تتفاعل في الشمعة نفسها بترتيب إنشائها في الخريطة؛ منطقة
   في تفاعل لا تبدأ ثانيًا (تقييم واحد في كل مرة)؛ وموت المنطقة (خروجها من
   ACTIVE) يطوي تفاعلها المعلق فورًا.
7. **قبل توفر ATR موجب** (أو عند انعدامه لسوق مسطح): تُحصى الاختبارات
   ويُتابع التغلغل السعري فقط — لا نوافذ ولا تصنيف ولا بث (العتبة
   التطبيعية شرط التقييم كله؛ لا عتبة مطلقة بديلة)، ويُطوى التفاعل بلا
   تصنيف إذا غادر السعر جهة القرب قبل توفر المقياس.

**ملاحظة لـ3-f (تجميع المغلفات)**: :class:`EmittedEvent` خرج هذا الكاشف —
حمولتها نماذج ``schemas`` معتمدة جاهزة للإدخال في ``EventEnvelope``
``payload`` (تجميع المغلف وإضافة event_id/receive_time/source/trace_id/
correlation_id مسؤولية 3-f حصرًا)، و``event_time == payload.bar_time`` ==
وقت شمعة الحسم. تسمية الجانب من لغة §10.1/§20: مناطق BUY_SIDE (سيولة عند
القمم) تبث ``*_HIGH`` ومناطق SELL_SIDE (سيولة عند القعور) تبث ``*_LOW``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    BreakAcceptEventPayload,
    Candle,
    EventType,
    LiquiditySide,
    SweepClassification,
    SweepEventPayload,
)

from liquidity.zones import LiquidityMapEngine, ZoneBand

__all__ = [
    "EmittedEvent",
    "SweepConfig",
    "SweepDetector",
]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class SweepConfig:
    """إعداد كاشف الاجتياح — نقاط انطلاق إعدادية للتقييم والمعايرة.

    لا ثابت سعري هنا: ``width_fraction`` نسبة بلا وحدة من عرض المنطقة،
    وجزء التقلب يأتي عتبةً تطبيعية من حالة التقلب عند كل شمعة.
    """

    #: نافذة التقييم بالشموع من أول تغلغل وراء الحافة البعيدة (§10.4 شرط 4).
    eval_window: int = 3
    #: عدد الإغلاقات المؤهلة (وراء الحافة البعيدة صراحةً) اللازم للقبول.
    accept_min_closes: int = 2
    #: حصة عرض المنطقة من العتبة المطلوبة (§10.4 «relative to … zone width»).
    width_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.eval_window < 1:
            raise ValueError(f"eval_window يجب أن يكون ≥ 1؛ وُجد {self.eval_window}")
        if self.accept_min_closes < 1:
            raise ValueError(f"accept_min_closes يجب أن يكون ≥ 1؛ وُجد {self.accept_min_closes}")
        if not isfinite(self.width_fraction) or self.width_fraction <= 0.0:
            raise ValueError(
                f"width_fraction يجب أن تكون نسبة محدودة موجبة؛ وُجدت {self.width_fraction!r}"
            )


# ═════════════════════════════ الخرج ═════════════════════════════


@dataclass(frozen=True)
class EmittedEvent:
    """حدث مبثوث من كاشف الاجتياح — حمولة معتمدة جاهزة للمغلف (3-f).

    ``event_time == payload.bar_time`` == وقت شمعة الحسم (شرط 5 §10.4) —
    البث لا يسبق اكتمال التسلسل على شمعة مقفلة (§27). الحمولة نموذج
    ``schemas`` مجمّد مكتفٍ ذاتيًا (تمركز ذاتي §32): يبني 3-f حقل ``payload``
    في ``EventEnvelope`` من ``payload.model_dump()`` ويضيف حقول التوصيل.
    """

    event_type: EventType
    event_time: datetime
    payload: SweepEventPayload | BreakAcceptEventPayload


# ═════════════════ حالة التفاعل (خاصة بالكاشف) ═════════════════


@dataclass
class _Interaction:
    """حلقة تفاعل واحدة مع منطقة — تقيس على النطاق الملتقط عند بدئها."""

    zone_id: str
    side: LiquiditySide
    #: النطاق الملتقط لحظة اللمس — المرجع الثابت لكل حسم التسلسل.
    price_low: float
    price_high: float
    start_bar: int
    #: أول بار تغلغل متاح المقياس — None ما لم تُفتح النافذة.
    window_start: int | None = None
    closes_in_window: int = 0
    qualifying_closes: int = 0
    max_excursion: float = 0.0
    penetrated_ever: bool = False
    penetration_reached: bool = False


def _touched(price_low: float, price_high: float, candle: Candle) -> bool:
    """لمس = تقاطع مدى الشمعة مع فاصل المنطقة (حواف مغلقة) — متماثل الجهتين."""
    return candle.high >= price_low and candle.low <= price_high


def _decisive_traversal(
    side: LiquiditySide,
    price_low: float,
    price_high: float,
    candle: Candle,
    buffer: float,
) -> bool:
    """عبور قافز حاسم: مدى الشمعة كله وراء الحافة البعيدة وإغلاق بهامش وراءها.

    BUY_SIDE: ``low > price_high`` و``close − price_high ≥ buffer``؛
    SELL_SIDE: ``high < price_low`` و``price_low − close ≥ buffer``.
    """
    if side is LiquiditySide.BUY_SIDE:
        return candle.low > price_high and (candle.close - price_high) >= buffer
    return candle.high < price_low and (price_low - candle.close) >= buffer


def _reclaimed(side: LiquiditySide, price_low: float, price_high: float, close: float) -> bool:
    """استرجاع = إغلاق صراحةً خلف الحافة القريبة (BUY: دونها / SELL: فوقها)."""
    if side is LiquiditySide.BUY_SIDE:
        return close < price_low
    return close > price_high


def _closed_beyond_far(
    side: LiquiditySide,
    price_low: float,
    price_high: float,
    close: float,
) -> bool:
    """إغلاق مؤهل للقبول = إغلاق صراحةً وراء الحافة البعيدة."""
    if side is LiquiditySide.BUY_SIDE:
        return close > price_high
    return close < price_low


def _rejection_depth_atr(
    side: LiquiditySide,
    price_low: float,
    price_high: float,
    close: float,
    atr: float,
) -> float:
    """عمق الرفض المعياري عند شمعة الحسم الرافض — موجب في وجهة الرفض."""
    if side is LiquiditySide.BUY_SIDE:
        return (price_low - close) / atr
    return (close - price_high) / atr


# ═════════════════════════════ الكاشف ═════════════════════════════


class SweepDetector:
    """كاشف الاجتياح الموضعي — يستهلك خريطة السيولة وشمعة مغلقة لكل نداء.

    البناء: يُربط بخريطة (:class:`~liquidity.zones.LiquidityMapEngine`)
    واحدة ويستدعى **بعد** تحقق الخريطة من الشمعة وقبل تحديث الخريطة بها —
    الترتيب الذي تجسده الواجهة :class:`~liquidity.engine.LiquidityEngine`
    (شرط 1 §10.4: منطقة «قائمة مسبقًا» لا منطقة الشمعة الجارية).
    """

    def __init__(
        self,
        zone_map: LiquidityMapEngine,
        config: SweepConfig | None = None,
    ) -> None:
        self._map = zone_map
        self._config = config if config is not None else SweepConfig()
        self._interactions: dict[str, _Interaction] = {}
        self._bar = 0

    @property
    def config(self) -> SweepConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """تقييم شمعة مغلقة ضد الخريطة القائمة — يرجع أحداث هذا الشريط فقط.

        ترتيب المعالجة: طي تفاعلات المناطق الميتة أولًا، ثم مسح المناطق
        النشطة بترتيب إنشائها في الخريطة (الحتمية عند تعدد التفاعلات).
        ``vol = None`` (قبيل أول شمعة عند محرك التقلب الموازي) يُعامل كغياب
        ATR: لمس بلا بدء نافذة ولا عتبات — نفس عقد حزمة البنية.
        """
        self._bar += 1
        live = self._map.live_bands()
        live_ids = {band.zone_id for band in live}
        for zone_id in list(self._interactions):
            if zone_id not in live_ids:
                del self._interactions[zone_id]
        events: list[EmittedEvent] = []
        for band in live:
            events.extend(self._process_zone(band, candle, vol))
        return events

    # ── الداخلية ──

    def _process_zone(
        self,
        band: ZoneBand,
        candle: Candle,
        vol: VolatilityState | None,
    ) -> list[EmittedEvent]:
        """معالجة منطقة نشطة واحدة — آلة التفاعل الموثقة في رأس الوحدة."""
        cfg = self._config
        atr = vol.atr if vol is not None else None
        atr_ok = atr is not None and atr > 0.0
        interaction = self._interactions.get(band.zone_id)
        if interaction is None:
            # (هـ) منطقة بلا تفاعل: فحص العبور القافز ثم بدء التفاعل عند اللمس.
            if not _touched(band.price_low, band.price_high, candle):
                if atr_ok:
                    assert atr is not None and vol is not None
                    buffer = vol.threshold(ThresholdKey.STRUCTURAL_LEVEL_BUFFER)
                    if buffer is not None and _decisive_traversal(
                        band.side, band.price_low, band.price_high, candle, buffer
                    ):
                        self._map.invalidate_traversed(band.zone_id)
                return []
            interaction = _Interaction(
                zone_id=band.zone_id,
                side=band.side,
                price_low=band.price_low,
                price_high=band.price_high,
                start_bar=self._bar,
            )
            self._interactions[band.zone_id] = interaction
            self._map.record_test(band.zone_id, candle.bar_time)
        # (ب) رصد التغلغل وراء الحافة البعيدة (شرط 2) — يُتابع دومًا ولو غاب المقياس.
        if band.side is LiquiditySide.BUY_SIDE:
            if candle.high >= interaction.price_high:
                interaction.max_excursion = max(
                    interaction.max_excursion, candle.high - interaction.price_high
                )
                interaction.penetrated_ever = True
                self._map.record_penetration(band.zone_id, candle.high)
        else:
            if candle.low <= interaction.price_low:
                interaction.max_excursion = max(
                    interaction.max_excursion, interaction.price_low - candle.low
                )
                interaction.penetrated_ever = True
                self._map.record_penetration(band.zone_id, candle.low)
        # (ج) العتبة المطلوبة (شرط 3) بالنطاق الملتقط والتقلب الحي — والنافذة.
        if atr_ok:
            assert atr is not None and vol is not None
            vol_part = vol.threshold(ThresholdKey.SWEEP_TOLERANCE)
            assert vol_part is not None  # atr موجب ⇒ العتبة تطبيعية محسوبة
            width = interaction.price_high - interaction.price_low
            required = max(vol_part, width * cfg.width_fraction)
            if interaction.max_excursion >= required:
                interaction.penetration_reached = True
            if interaction.penetrated_ever and interaction.window_start is None:
                interaction.window_start = self._bar
                interaction.closes_in_window = 0
                interaction.qualifying_closes = 0
        # (د) الحسم داخل النافذة.
        if interaction.window_start is not None:
            return self._resolve_in_window(interaction, candle, atr)
        # (د-مكمل) تفاعل بلا نافذة: المغادرة خلف الحافة القريبة تفشل الاجتياح.
        if _reclaimed(
            interaction.side, interaction.price_low, interaction.price_high, candle.close
        ):
            if atr_ok:
                assert atr is not None
                depth = _rejection_depth_atr(
                    interaction.side,
                    interaction.price_low,
                    interaction.price_high,
                    candle.close,
                    atr,
                )
                self._map.record_reaction(interaction.zone_id, depth)
                self._map.set_sweep_status(interaction.zone_id, SweepClassification.FAILED_SWEEP)
            del self._interactions[interaction.zone_id]
        return []

    def _resolve_in_window(
        self,
        interaction: _Interaction,
        candle: Candle,
        atr: float | None,
    ) -> list[EmittedEvent]:
        """الحسم داخل نافذة التقييم — استرجاع/قبول/انقضاء (شرط 4)."""
        cfg = self._config
        window_start = interaction.window_start
        assert window_start is not None
        interaction.closes_in_window += 1
        beyond_far = _closed_beyond_far(
            interaction.side, interaction.price_low, interaction.price_high, candle.close
        )
        if beyond_far:
            interaction.qualifying_closes += 1
        # 4أ — الاسترجاع (حاسم فوري).
        if _reclaimed(
            interaction.side, interaction.price_low, interaction.price_high, candle.close
        ):
            events: list[EmittedEvent] = []
            if atr is not None and atr > 0.0:
                depth = _rejection_depth_atr(
                    interaction.side,
                    interaction.price_low,
                    interaction.price_high,
                    candle.close,
                    atr,
                )
                self._map.record_reaction(interaction.zone_id, depth)
            if interaction.penetration_reached:
                assert atr is not None and atr > 0.0  # penetration_reached يستلزمه
                events.append(self._emit_sweep(interaction, candle, atr))
                self._map.finalize_sweep(interaction.zone_id)
            else:
                self._map.set_sweep_status(interaction.zone_id, SweepClassification.FAILED_SWEEP)
            del self._interactions[interaction.zone_id]
            return events
        # 4ب — القبول (حاسم فوري متى اكتملت الشروط).
        if (
            interaction.qualifying_closes >= cfg.accept_min_closes
            and interaction.penetration_reached
        ):
            assert atr is not None and atr > 0.0  # penetration_reached يستلزمه
            event = self._emit_accept(interaction, candle, atr)
            self._map.finalize_accept(interaction.zone_id)
            del self._interactions[interaction.zone_id]
            return [event]
        # 4ج — انقضاء النافذة بلا حسم: UNKNOWN وراء الحافة البعيدة، PARTIAL داخله.
        if self._bar - window_start >= cfg.eval_window - 1:
            status = (
                SweepClassification.UNKNOWN if beyond_far else SweepClassification.PARTIAL_SWEEP
            )
            self._map.set_sweep_status(interaction.zone_id, status)
            del self._interactions[interaction.zone_id]
        return []

    # ── البث (شرط 5 — حمولات موقوتة مربوطة) ──

    def _emit_sweep(
        self,
        interaction: _Interaction,
        candle: Candle,
        atr: float,
    ) -> EmittedEvent:
        """بناء حدث اجتياح مؤكد — LIQUIDITY_SWEEP_HIGH للـBUY_SIDE وإلا _LOW."""
        window_start = interaction.window_start
        assert window_start is not None
        payload = SweepEventPayload(
            instrument=self._map.instrument_id if self._map.instrument_id else "",
            timeframe=self._map.timeframe if self._map.timeframe else "",
            bar_time=candle.bar_time,
            zone_id=interaction.zone_id,
            zone_side=interaction.side,
            classification=SweepClassification.CONFIRMED_SWEEP,
            excursion_atr=interaction.max_excursion / atr,
            penetration_reached=True,
            reclaim_bars=self._bar - window_start,
            test_count_at_event=self._map.zone_test_count(interaction.zone_id),
        )
        event_type = (
            EventType.LIQUIDITY_SWEEP_HIGH
            if interaction.side is LiquiditySide.BUY_SIDE
            else EventType.LIQUIDITY_SWEEP_LOW
        )
        return EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)

    def _emit_accept(
        self,
        interaction: _Interaction,
        candle: Candle,
        atr: float,
    ) -> EmittedEvent:
        """بناء حدث كسر بالقبول — BREAK_AND_ACCEPT_HIGH للـBUY_SIDE وإلا _LOW."""
        payload = BreakAcceptEventPayload(
            instrument=self._map.instrument_id if self._map.instrument_id else "",
            timeframe=self._map.timeframe if self._map.timeframe else "",
            bar_time=candle.bar_time,
            zone_id=interaction.zone_id,
            zone_side=interaction.side,
            excursion_atr=interaction.max_excursion / atr,
            acceptance_ratio=interaction.qualifying_closes / interaction.closes_in_window,
            window_bars=interaction.closes_in_window,
        )
        event_type = (
            EventType.BREAK_AND_ACCEPT_HIGH
            if interaction.side is LiquiditySide.BUY_SIDE
            else EventType.BREAK_AND_ACCEPT_LOW
        )
        return EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)
