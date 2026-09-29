"""اختبارات كاشف الامتصاص — المهمتان 4.3 و§12.3 (تكملة 4-d بعد انقطاع الوكيل).

السناريوهات (fixtures هندسية مبنية يدويًا — بوابة المرحلة و§38.1
«absorption candidate/invalid case»):

- **المرشح الكامل**: عدوانية بيعية مرتفعة + امتداد محدود (عتبة تطبيعية)
  + تكرار فشل المواصلة ⇒ ‏ABSORPTION_BUY (الضغط البيعي امتُص §20) بمرشح
  غير مؤكد (``confirmed=False`` — «فرضيات تؤكدها الاستجابة اللاحقة» §12.2).
- **كل شرط مانع مستقلًا يمنع**: بلا ارتفاع، بامتداد واسع، بمواصلة ناجحة.
- **قاعدة عدم التكرار**: القفل حتى انكسار الشرط 1 ثم عودته.
- **إيجابية الحمولة**: الامتداد المعدوم/المعاكس لا يُبث (``PositiveFloat``).
- **لا مرشح بلا تقلب (§16)** وحقنا zone_resolver/displacement_watcher.
- **الحتمية واللا-نظرة-المستقبلية (§26.3)**: بادئة حتى k ⇒ أحداث البادئة
  نفسها في التشغيل الكامل — الإعلان عند شريط التأكيد حصرًا.

القيم الافتراضية للإعداد مع ``atr=1.0``: عتبة الامتداد
ABSORPTION_EXTENSION_MAX = 0.5 وعتبة المواصلة FLOW_RESPONSE_MIN = 0.5
(عتبات تطبيعية atr × معامل — كلها تتحجج مع ATR).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from market_state.volatility import VolatilityState
from orderflow.absorption import AbsorptionConfig, AbsorptionDetector
from orderflow.events import EmittedEvent
from orderflow.rows import METHODOLOGY_AGGTRADE_TAKER
from schemas import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
    Candle,
    DataQuality,
    EventType,
    FootprintBar,
)

# ═══════════ المصغّرات — نفس عقد test_effort_result ═══════════

BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def make_candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    """شمعة مكتملة كاملة الحقول من OHLC متسق (عقد §8.1)."""
    if high < max(open_, close) or low > min(open_, close):
        raise ValueError(f"أطراف خارج المدى: OHLC=({open_}, {high}, {low}, {close})")
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span if span > 0.0 else 0.0,
        close_location_value=(close - low) / span if span > 0.0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def make_fp_bar(
    index: int,
    buy: float,
    sell: float,
    *,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> FootprintBar:
    """شريط فوتبرنت متسق: delta = buy−sell وtotal = buy+sell (عقد البنّاء)."""
    total = buy + sell
    return FootprintBar(
        instrument_id=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        source_feed="binance-aggTrades",
        methodology=METHODOLOGY_AGGTRADE_TAKER,
        buy_volume=buy,
        sell_volume=sell,
        total_volume=total,
        delta=buy - sell,
        buy_share=buy / total if total > 0.0 else 0.0,
        sell_share=sell / total if total > 0.0 else 0.0,
        poc=100.0,
        vah=101.0,
        val=99.0,
        row_count=3,
        buy_imbalance_count=0,
        sell_imbalance_count=0,
    )


def make_vol(atr: float | None) -> VolatilityState:
    """حالة تقلب — ما يقرؤه الكاشف: atr والعتبات التطبيعية منه."""
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=0.001,
        range_expansion_percentile=0.5,
        vol_of_vol=0.1,
        gap_shock=0.0,
        spread_to_range=0.5,
        expected_holding_vol_1h=0.001,
        bar_time=None,
    )


def _feed(
    detector: AbsorptionDetector,
    specs: list[tuple[tuple[float, float], tuple[float, float, float, float]]],
    vol: VolatilityState | None,
) -> list[tuple[int, EmittedEvent]]:
    """تغذية (شريط، شمعة) ثنائيات وجمع الأحداث مع فهرس شريطها."""
    out: list[tuple[int, EmittedEvent]] = []
    for i, ((buy, sell), (o, h, low, c)) in enumerate(specs):
        events = detector.update(make_fp_bar(i, buy, sell), make_candle(i, o, h, low, c), vol)
        out.extend((i, e) for e in events)
    return out


#: شريطان تحضيريان محيدان + شريط حكم بيعي مرتفعًا بامتداد محدود
#: (شراء 20/بيع 80 ⇒ share=−0.6؛ open−close=0.2 ≤ 0.5 وعتبات atr=1.0).
_CANDIDATE_SELL_ABSORBED: list[tuple[tuple[float, float], tuple[float, float, float, float]]] = [
    ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),  # فشل مواصلة هابط (0 < 0.5)
    ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),  # فشل مواصلة هابط (العد 2)
    ((20.0, 80.0), (100.0, 100.3, 99.7, 99.8)),  # الحكم: امتداد 0.2 محدود
]


class TestAbsorptionCandidate:
    def test_full_candidate_emits_absorption_buy(self) -> None:
        """الشروط الثلاثة مكتملة ⇒ ABSORPTION_BUY بضغط بيعي ممتص (§20)."""
        det = AbsorptionDetector()
        events = _feed(det, _CANDIDATE_SELL_ABSORBED, make_vol(1.0))
        assert len(events) == 1
        idx, event = events[0]
        assert idx == 2  # الإعلان عند شريط الحكم حصرًا (لا-نظرة §26.3)
        assert event.event_type is EventType.ABSORPTION_BUY
        p = event.payload
        assert isinstance(p, AbsorptionEventPayload)
        assert p.absorbed_pressure is AbsorbedPressure.SELL
        assert p.confirmed is False  # مرشح قابل للتأكيد (§12.2)
        assert p.delta == pytest.approx(-60.0)
        assert p.delta_share == pytest.approx(-0.6)
        assert p.excursion_atr == pytest.approx(0.2)  # 0.2 / atr=1.0
        assert p.conditions == AbsorptionConditions(
            elevated_delta=True,
            limited_extension=True,
            repeated_response=True,
            opposite_displacement=None,
        )
        assert p.zone_id is None
        assert event.event_time == BASE_TIME + timedelta(minutes=2)

    def test_mirror_buy_pressure_absorbed_emits_absorption_sell(self) -> None:
        """المرآة: عدوانية شرائية كبيرة بردّ محدود ⇒ ABSORPTION_SELL."""
        specs = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((80.0, 20.0), (100.0, 100.3, 99.7, 100.2)),  # امتداد صاعد 0.2
        ]
        det = AbsorptionDetector()
        events = _feed(det, specs, make_vol(1.0))
        assert len(events) == 1
        _, event = events[0]
        assert event.event_type is EventType.ABSORPTION_SELL
        p = event.payload
        assert isinstance(p, AbsorptionEventPayload)
        assert p.absorbed_pressure is AbsorbedPressure.BUY
        assert p.delta_share == pytest.approx(0.6)


class TestBlockingConditions:
    """كل شرط مانع مستقلًا يمنع المرشح — «absorption invalid case» §38.1."""

    def test_no_elevation_blocks(self) -> None:
        """الشرط 1 غائب: حصة دلتا دون الحد (‎|−0.2| < 0.5)."""
        specs = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((40.0, 60.0), (100.0, 100.3, 99.7, 99.8)),
        ]
        det = AbsorptionDetector()
        assert _feed(det, specs, make_vol(1.0)) == []

    def test_wide_extension_blocks(self) -> None:
        """الشرط 2 غائب: امتداد 1.0 يتجاوز العتبة التطبيعية 0.5 —
        والمواصلة الناجحة تصفّر عداء الفشل فلا اكتمال أصلًا."""
        specs = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((20.0, 80.0), (100.0, 100.1, 98.5, 99.0)),  # هبوط 1.0 ≥ 0.5
        ]
        det = AbsorptionDetector()
        assert _feed(det, specs, make_vol(1.0)) == []

    def test_successful_continuation_blocks(self) -> None:
        """الشرط 3 غائب: مواصلة هابطة ناجحة مرتين تصفّر العداء قبل الحكم."""
        specs = [
            ((50.0, 50.0), (100.0, 100.1, 98.8, 99.0)),  # هبوط 1.0 ⇒ نجاح
            ((50.0, 50.0), (100.0, 100.1, 98.8, 99.0)),  # هبوط 1.0 ⇒ نجاح
            ((20.0, 80.0), (100.0, 100.3, 99.7, 99.8)),  # فشل واحد فقط
        ]
        det = AbsorptionDetector()
        assert _feed(det, specs, make_vol(1.0)) == []

    def test_zero_or_adverse_extension_not_emitted(self) -> None:
        """إيجابية الحمولة (عقد 4-a): الامتداد المعدوم/المعاكس لا يُبث —
        الحالة تبقى مسلحة بلا قفل (موثق في رأس الوحدة)."""
        flat = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((20.0, 80.0), (100.0, 100.4, 99.6, 100.0)),  # امتداد معدوم
        ]
        assert _feed(AbsorptionDetector(), flat, make_vol(1.0)) == []
        adverse = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((20.0, 80.0), (100.0, 100.6, 99.6, 100.5)),  # إغلاق معاكس
        ]
        det = AbsorptionDetector()
        assert _feed(det, adverse, make_vol(1.0)) == []
        # الحالة مسلحة: شريط لاحق مكتمل بامتداد موجب يبث
        armed = det.update(
            make_fp_bar(3, 20.0, 80.0), make_candle(3, 100.0, 100.3, 99.7, 99.8), make_vol(1.0)
        )
        assert len(armed) == 1
        assert armed[0].event_type is EventType.ABSORPTION_BUY

    def test_no_volatility_no_candidate(self) -> None:
        """لا مرشح بلا تقلب (§16): الشرط 2 عتبة تطبيعية حصرية."""
        det = AbsorptionDetector()
        assert _feed(det, _CANDIDATE_SELL_ABSORBED, None) == []


class TestNoRepeatLock:
    def test_lock_until_condition_one_breaks_then_returns(self) -> None:
        """بث واحد لنفس الحالة المستمرة؛ الشريط غير المرتفع يفك القفل
        والحكم التالي المكتمل يبث من جديد (تباعد الأحداث موثق)."""
        det = AbsorptionDetector()
        judgment = (20.0, 80.0), (100.0, 100.3, 99.7, 99.8)
        specs = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            judgment,  # بث 1 + قفل ABSORPTION_BUY
            judgment,  # مقفلة ⇒ لا تكرار
            judgment,  # مقفلة ⇒ لا تكرار
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),  # فك القفل
            judgment,  # بث 2
        ]
        events = _feed(det, specs, make_vol(1.0))
        assert [i for i, _ in events] == [2, 6]
        assert all(e.event_type is EventType.ABSORPTION_BUY for _, e in events)

    def test_sides_lock_independently(self) -> None:
        """قفل الجهة لا يمنع الجهة المقابلة عند اكتمال شروطها."""
        det = AbsorptionDetector()
        specs = [
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((50.0, 50.0), (100.0, 100.4, 99.6, 100.0)),
            ((20.0, 80.0), (100.0, 100.3, 99.7, 99.8)),  # ABSORPTION_BUY
            # جهة معاكسة مكتملة فورًا: عداء الفشل الصاعد اكتمل عبر الشممس
            # المحايدة الثلاث (فشل بالاتجاهين معًا — «السوق لم يواصل شيئًا»)
            ((80.0, 20.0), (100.0, 100.3, 99.7, 100.2)),  # ABSORPTION_SELL
        ]
        events = _feed(det, specs, make_vol(1.0))
        assert [e.event_type for _, e in events] == [
            EventType.ABSORPTION_BUY,
            EventType.ABSORPTION_SELL,
        ]


class TestInjections:
    def test_zone_resolver_and_displacement_watcher_wired(self) -> None:
        """الحقنان يوصَّلان من بوابة المرحلة (عقود الطبقات تمنع الاستيراد):
        zone_id وopposite_displacement يظهران في الحمولة."""
        det = AbsorptionDetector(
            AbsorptionConfig(
                zone_resolver=lambda candle: "zone-abc",
                displacement_watcher=lambda candle: True,
            )
        )
        events = _feed(det, _CANDIDATE_SELL_ABSORBED, make_vol(1.0))
        assert len(events) == 1
        p = events[0][1].payload
        assert isinstance(p, AbsorptionEventPayload)
        assert p.zone_id == "zone-abc"
        assert p.conditions.opposite_displacement is True


class TestDeterminismAndNoLookahead:
    def test_same_feed_same_events(self) -> None:
        """الحتمية الصرفة: نفس التدفق مرتين ⇒ نفس الأحداث بالتطابق."""
        run1 = _feed(AbsorptionDetector(), _CANDIDATE_SELL_ABSORBED, make_vol(1.0))
        run2 = _feed(AbsorptionDetector(), _CANDIDATE_SELL_ABSORBED, make_vol(1.0))
        assert run1 == run2

    def test_prefix_events_match_full_run(self) -> None:
        """لا-نظرة (§26.3): أحداث البادئة [0..k] نفسها في التشغيل الكامل —
        إضافة الذيل لا تعدل شيئًا مما أُعلن."""
        tail = [
            ((90.0, 10.0), (100.0, 101.0, 99.5, 100.8)),
            ((10.0, 90.0), (100.0, 100.5, 99.0, 99.2)),
        ]
        full = _CANDIDATE_SELL_ABSORBED + tail
        full_events = _feed(AbsorptionDetector(), full, make_vol(1.0))
        prefix_events = _feed(AbsorptionDetector(), _CANDIDATE_SELL_ABSORBED, make_vol(1.0))
        prefix_flags = [(i, e.event_type) for i, e in full_events if i <= 2]
        assert prefix_flags == [(i, e.event_type) for i, e in prefix_events]


class TestThresholdScaling:
    def test_lambda_two_atr_scales_thresholds_exactly(self) -> None:
        """التحجيج (بوابة المرحلة): مضاعفة ATR مع مضاعفة الامتداد بالنسبة
        نفسها ⇒ نفس القرار — كل عتبة سعرية اشتقت من atr×المعامل."""
        det1 = AbsorptionDetector()
        events1 = _feed(
            det1,
            [
                ((50.0, 50.0), (100.0, 100.8, 99.2, 100.0)),
                ((50.0, 50.0), (100.0, 100.8, 99.2, 100.0)),
                ((20.0, 80.0), (100.0, 100.6, 99.4, 99.6)),  # امتداد 0.4
            ],
            make_vol(1.0),
        )
        det2 = AbsorptionDetector()
        events2 = _feed(
            det2,
            [
                ((50.0, 50.0), (100.0, 101.6, 98.4, 100.0)),
                ((50.0, 50.0), (100.0, 101.6, 98.4, 100.0)),
                ((20.0, 80.0), (100.0, 101.2, 98.8, 99.2)),  # امتداد 0.8
            ],
            make_vol(2.0),  # العتبات تتضاعف: 1.0 و1.0
        )
        assert len(events1) == 1 and len(events2) == 1
        p1, p2 = events1[0][1].payload, events2[0][1].payload
        assert isinstance(p1, AbsorptionEventPayload) and isinstance(p2, AbsorptionEventPayload)
        assert p1.excursion_atr == pytest.approx(p2.excursion_atr)  # 0.4 كلاهما
        assert p1.delta_share == p2.delta_share


class TestConfigValidation:
    def test_invalid_elevated_share_rejected(self) -> None:
        with pytest.raises(ValueError, match="elevated_share_min"):
            AbsorptionConfig(elevated_share_min=0.0)
        with pytest.raises(ValueError, match="elevated_share_min"):
            AbsorptionConfig(elevated_share_min=1.5)

    def test_invalid_repeated_response_bars_rejected(self) -> None:
        with pytest.raises(ValueError, match="repeated_response_bars"):
            AbsorptionConfig(repeated_response_bars=0)

    def test_invalid_threshold_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="extension_max_key"):
            AbsorptionConfig(extension_max_key="NOT_A_KEY")  # type: ignore[arg-type]
