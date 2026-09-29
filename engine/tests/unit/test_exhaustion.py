"""اختبارات كاشف الإنهاك — المهمة 4.3 و§12.4 (تكملة 4-d بعد انقطاع الوكيل).

السناريوهات (fixtures هندسية مبنية يدويًا — إيجابي/سلبي):

- **الإنهاك الصاعد الكامل**: كفاءة نصف النافذة الأحدث تنهار أمام الأقدم
  (decay ≤ الحد) + قمم فاشلة متكررة + متابعة منخفضة ⇒ ‏EXHAUSTION_UP
  قياسًا لا توصية («الإنهاك وحده ليس إشارة انعكاس» §12.4).
- **كل عنصر مانع مستقلًا يمنع**: كفاءة مستقرة، قمم فاشلة دون الحد،
  متابعة مرتفعة.
- **المرآة الهابطة**: EXHAUSTION_DOWN بقيعان فاشلة.
- **لا إنهاك بلا تقلب (§16)**: عينات الكفاءة تحتاج atr.
- **الحتمية واللا-نظرة (§26.3)**: أحداث البادئة نفسها في التشغيل الكامل.

الإعداد المصغر للسرعة: ``window=6`` (نصفان × 3) و``atr=1.0`` فالعتبات
التطبيعية: المواصلة FLOW_RESPONSE_MIN = 0.5. هندسة الكفاءات:
``efficiency = (الاستجابة/atr) / |share|`` — الجهد الصغير نسبيًا مع
استجابة دون عتبة المواصلة يصنع كفاءة عالية بلا علامة مواصلة (resp=0.49
مع share=0.05 ⇒ ‏9.8)، والجهد الكبير بردّ ضعيف يصنعها منخفضة (resp=0.2
مع share=0.5 ⇒ ‏0.4).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from market_state.volatility import VolatilityState
from orderflow.events import EmittedEvent
from orderflow.exhaustion import ExhaustionConfig, ExhaustionDetector
from orderflow.rows import METHODOLOGY_AGGTRADE_TAKER
from schemas import (
    Candle,
    DataQuality,
    EventType,
    ExhaustionEventPayload,
    FlowDirection,
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
) -> Candle:
    """شمعة مكتملة كاملة الحقول من OHLC متسق (عقد §8.1)."""
    if high < max(open_, close) or low > min(open_, close):
        raise ValueError(f"أطراف خارج المدى: OHLC=({open_}, {high}, {low}, {close})")
    span = high - low
    body = abs(close - open_)
    return Candle(
        instrument_id=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=True,
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


def make_fp_bar(index: int, buy: float, sell: float) -> FootprintBar:
    """شريط فوتبرنت متسق: delta = buy−sell وtotal = buy+sell (عقد البنّاء)."""
    total = buy + sell
    return FootprintBar(
        instrument_id=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=BASE_TIME + timedelta(minutes=index),
        quality=DataQuality.HEALTHY,
        is_closed=True,
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


_CFG = ExhaustionConfig(window=6, decay_max=0.6, failed_extremes_min=2, follow_through_max=0.3)


def _feed(
    specs: list[tuple[tuple[float, float], tuple[float, float, float, float]]],
    vol: VolatilityState | None,
    config: ExhaustionConfig = _CFG,
) -> list[tuple[int, EmittedEvent]]:
    """تغذية (شريط، شمعة) ثنائيات وجمع الأحداث مع فهرس شريطها."""
    det = ExhaustionDetector(config)
    out: list[tuple[int, EmittedEvent]] = []
    for i, ((buy, sell), (o, h, low, c)) in enumerate(specs):
        events = det.update(make_fp_bar(i, buy, sell), make_candle(i, o, h, low, c), vol)
        out.extend((i, e) for e in events)
    return out


#: جهد صاعد صغير النسبة باستجابة دون عتبة المواصلة — كفاءة 9.8 بلا علامة.
_HI_EFF = (52.5, 47.5), (100.0, 101.0, 99.5, 100.49)  # share=0.05، resp=0.49
#: جهد صاعد كبير النسبة بردّ ضعيف — كفاءة 0.4.
_LO_EFF = (75.0, 25.0), (100.0, 101.0, 99.5, 100.2)  # share=0.5، resp=0.2

#: السناريو الكامل: نصف أقدم عالي الكفاءة ثم نصف أحدث منهار مع قمتين
#: فاشلتين عند الشريطين 6 و7 (مرجع القمم: max_HIGH نافذة 6 أشرطة).
_EXHAUSTION_UP_SEQ = [
    _HI_EFF,  # 0 — تعبئة
    _HI_EFF,  # 1
    _HI_EFF,  # 2
    _HI_EFF,  # 3
    _LO_EFF,  # 4
    _LO_EFF,  # 5 — النافذة تمتلئ: decay يمر لكن failed=0 ⇒ لا إعلان
    ((75.0, 25.0), (100.5, 103.0, 100.4, 100.7)),  # 6 — قمة فاشلة 1
    ((75.0, 25.0), (101.0, 104.0, 100.9, 101.2)),  # 7 — قمة فاشلة 2 ⇒ إعلان
]


class TestExhaustionUp:
    def test_full_scenario_emits_once_at_judgment_bar(self) -> None:
        """إعلان واحد عند الشريط 7 حصرًا (لا إعلان عند 5/6 — مانع الفشل)."""
        events = _feed(_EXHAUSTION_UP_SEQ, make_vol(1.0))
        assert [i for i, _ in events] == [7]
        _, event = events[0]
        assert event.event_type is EventType.EXHAUSTION_UP
        assert event.event_time == BASE_TIME + timedelta(minutes=7)
        p = event.payload
        assert isinstance(p, ExhaustionEventPayload)
        assert p.direction is FlowDirection.UP
        assert p.efficiency == pytest.approx(0.4)  # متوسط النصف الأحدث
        assert p.efficiency_prev == pytest.approx((9.8 + 9.8 + 0.4) / 3.0)  # bars 2-4
        assert p.decay_ratio == pytest.approx(0.4 / ((9.8 + 9.8 + 0.4) / 3.0))
        assert p.failed_extremes == 2
        assert p.follow_through == pytest.approx(0.0)

    def test_partial_windows_emit_nothing(self) -> None:
        """قبل اكتمال نافذة الكفاءة (أشرطة 0-4) لا تقييم أصلًا."""
        events = _feed(_EXHAUSTION_UP_SEQ[:5], make_vol(1.0))
        assert events == []


class TestBlockingElements:
    """كل عنصر مانع مستقلًا يمنع الإعلان — «invalid case»."""

    def test_stable_efficiency_blocks(self) -> None:
        """كفاءة مستقرة (decay=1.0 > 0.6) — لا تراجع فلا إنهاك."""
        events = _feed([_HI_EFF] * 8, make_vol(1.0))
        assert events == []

    def test_no_failed_extremes_blocks(self) -> None:
        """انهيار كفاءة دون قمم فاشلة (القيم تلامس max_HIGH دون تجاوزه)."""
        seq = [
            _HI_EFF,  # 0
            _HI_EFF,  # 1
            _HI_EFF,  # 2
            _HI_EFF,  # 3
            _LO_EFF,  # 4
            _LO_EFF,  # 5
            ((75.0, 25.0), (100.0, 101.0, 99.5, 100.2)),  # 6 — لا قمة فاشلة
            ((75.0, 25.0), (100.0, 101.0, 99.5, 100.2)),  # 7
        ]
        events = _feed(seq, make_vol(1.0))
        assert events == []

    def test_high_follow_through_blocks(self) -> None:
        """متابعة مرتفعة (علامات مواصلة ≥ 4/6 > 0.3) تمنع رغم الانهيار —
        الجهد ما زال يواصل فليس منهكًا."""
        seq = [
            _HI_EFF,  # 0
            _HI_EFF,  # 1
            _HI_EFF,  # 2 — النصف الأقدم: 9.8 بلا علامة
            _HI_EFF,  # 3
            # النصف الأحدث: جهد كامل النسبة باستجابة عند العتبة — كفاءة 0.5
            # وعلامة مواصلة True
            ((100.0, 0.0), (100.0, 101.0, 99.5, 100.5)),  # 4: share=1.0 resp=0.5
            ((100.0, 0.0), (100.0, 101.0, 99.5, 100.5)),  # 5
            ((100.0, 0.0), (100.2, 103.0, 100.1, 100.7)),  # 6 — قمة فاشلة
            ((100.0, 0.0), (100.4, 104.0, 100.3, 100.9)),  # 7 — قمة فاشلة
        ]
        events = _feed(seq, make_vol(1.0))
        assert events == []

    def test_no_volatility_no_samples_no_exhaustion(self) -> None:
        """بلا تقلب لا عينات كفاءة أصلًا — النوافذ لا تمتلئ فلا إعلان."""
        events = _feed(_EXHAUSTION_UP_SEQ, None)
        assert events == []


class TestExhaustionDownMirror:
    def test_full_mirror_emits_exhaustion_down(self) -> None:
        """المرآة الهابطة: جهد بيعي منهار الكفاءة + قاعان فاشلان."""
        hi = (47.5, 52.5), (100.5, 100.9, 99.4, 100.01)  # share=−0.05، resp=0.49
        lo = (25.0, 75.0), (100.5, 100.7, 99.4, 100.3)  # share=−0.5، resp=0.2
        seq = [
            hi,  # 0
            hi,  # 1
            hi,  # 2
            hi,  # 3
            lo,  # 4
            lo,  # 5
            ((25.0, 75.0), (100.3, 100.5, 97.0, 100.1)),  # 6 — قاع فاشل 1
            ((25.0, 75.0), (100.2, 100.4, 96.5, 100.0)),  # 7 — قاع فاشل 2
        ]
        events = _feed(seq, make_vol(1.0))
        assert [i for i, _ in events] == [7]
        _, event = events[0]
        assert event.event_type is EventType.EXHAUSTION_DOWN
        p = event.payload
        assert isinstance(p, ExhaustionEventPayload)
        assert p.direction is FlowDirection.DOWN
        assert p.efficiency == pytest.approx(0.4)
        assert p.failed_extremes == 2
        assert p.follow_through == pytest.approx(0.0)


class TestDeterminismAndNoLookahead:
    def test_same_feed_same_events(self) -> None:
        """الحتمية الصرفة: نفس التدفق مرتين ⇒ نفس الأحداث بالتطابق."""
        assert _feed(_EXHAUSTION_UP_SEQ, make_vol(1.0)) == _feed(_EXHAUSTION_UP_SEQ, make_vol(1.0))

    def test_prefix_events_match_full_run(self) -> None:
        """لا-نظرة (§26.3): أحداث البادئة [0..k] نفسها في التشغيل الكامل."""
        tail = [
            ((90.0, 10.0), (100.0, 101.5, 99.5, 101.2)),
            ((10.0, 90.0), (100.0, 100.5, 98.8, 99.0)),
        ]
        full_events = _feed(_EXHAUSTION_UP_SEQ + tail, make_vol(1.0))
        prefix_events = _feed(_EXHAUSTION_UP_SEQ, make_vol(1.0))
        flags_full = [(i, e.event_type) for i, e in full_events if i <= 7]
        assert flags_full == [(i, e.event_type) for i, e in prefix_events]


class TestConfigValidation:
    def test_window_must_be_even_and_at_least_two(self) -> None:
        with pytest.raises(ValueError, match="window"):
            ExhaustionConfig(window=5)
        with pytest.raises(ValueError, match="window"):
            ExhaustionConfig(window=0)

    def test_decay_max_strictly_within_unit(self) -> None:
        with pytest.raises(ValueError, match="decay_max"):
            ExhaustionConfig(window=6, decay_max=1.0)
        with pytest.raises(ValueError, match="decay_max"):
            ExhaustionConfig(window=6, decay_max=0.0)

    def test_follow_through_max_within_unit(self) -> None:
        with pytest.raises(ValueError, match="follow_through_max"):
            ExhaustionConfig(window=6, follow_through_max=1.5)

    def test_failed_extremes_min_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="failed_extremes_min"):
            ExhaustionConfig(window=6, failed_extremes_min=0)
