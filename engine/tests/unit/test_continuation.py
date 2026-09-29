"""اختبارات باعث توافق التدفق — §12.2 (إكمال المنسق للمسار الحدثي للاستمرار).

- خلية التوافق (جهد كبير + استجابة قوية) ⇒ ‏FLOW_CONTINUATION بالجهة
  الصحيحة وحمولة كاملة القياسات (المشتقات تُحسب من الشريط والشمعة والتقلب).
- خلايا المصفوفة الأخرى لا تصدر شيئًا (جهد بلا نتيجة/نتيجة بلا جهد/
  ضعيفان/بلا تقلب) — ميادين كواشف أخرى أو لا شيء.
- الحتمية: نفس الثلاثية مرتين ⇒ نفس الحدث.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from market_state.volatility import VolatilityState
from orderflow.continuation import ContinuationEmitter
from orderflow.effort import EffortResultState, classify_effort_vs_result
from orderflow.rows import METHODOLOGY_AGGTRADE_TAKER
from schemas import (
    Candle,
    DataQuality,
    EventType,
    FlowContinuationEventPayload,
    FlowDirection,
    FootprintBar,
)

BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"


def make_candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
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


class TestContinuationEmitter:
    def test_agree_up_emits_flow_continuation_up(self) -> None:
        """جهد شرائي كبير (share=0.6) + صعود قوي (0.8×ATR) ⇒ توافق صاعد."""
        bar = make_fp_bar(0, 80.0, 20.0)
        candle = make_candle(0, 100.0, 101.0, 99.9, 100.8)
        vol = make_vol(1.0)
        assert classify_effort_vs_result(bar, candle, vol) is EffortResultState.AGREE_EFFORT_RESULT

        events = ContinuationEmitter().update(bar, candle, vol)
        assert len(events) == 1
        event = events[0]
        assert event.event_type is EventType.FLOW_CONTINUATION_UP
        assert event.event_time == bar.bar_time
        p = event.payload
        assert isinstance(p, FlowContinuationEventPayload)
        assert p.direction is FlowDirection.UP
        assert p.delta == pytest.approx(60.0)
        assert p.delta_share == pytest.approx(0.6)
        assert p.response_atr == pytest.approx(0.8)
        assert p.efficiency == pytest.approx(0.8 / 0.6)

    def test_agree_down_emits_flow_continuation_down(self) -> None:
        """المرآة: جهد بيعي كبير + هبوط قوي ⇒ توافق هابط."""
        bar = make_fp_bar(0, 20.0, 80.0)
        candle = make_candle(0, 100.0, 100.1, 99.0, 99.2)
        events = ContinuationEmitter().update(bar, candle, make_vol(1.0))
        assert len(events) == 1
        assert events[0].event_type is EventType.FLOW_CONTINUATION_DOWN
        p = events[0].payload
        assert isinstance(p, FlowContinuationEventPayload)
        assert p.direction is FlowDirection.DOWN

    def test_other_matrix_cells_emit_nothing(self) -> None:
        """بقية الخلايا لا باعث لها هنا — الامتصاص/الإنهاك ميادين أخرى."""
        emitter = ContinuationEmitter()
        # جهد كبير بردّ ضعيف (EFFORT_NO_RESULT)
        weak = make_fp_bar(0, 80.0, 20.0), make_candle(0, 100.0, 100.9, 99.9, 100.1)
        assert emitter.update(weak[0], weak[1], make_vol(1.0)) == []
        # جهد صغير (LOW_EFFORT أو RESULT_NO_EFFORT)
        small = make_fp_bar(1, 55.0, 45.0), make_candle(1, 100.0, 100.9, 99.9, 100.8)
        assert emitter.update(small[0], small[1], make_vol(1.0)) == []
        # بلا تقلب (INSUFFICIENT_VOLATILITY) — طابع جديد يصعد
        no_vol = make_fp_bar(2, 80.0, 20.0), make_candle(2, 100.0, 100.9, 99.9, 100.1)
        assert emitter.update(no_vol[0], no_vol[1], None) == []

    def test_determinism_same_inputs_same_event(self) -> None:
        """الحتمية الصرفة — الباعث عديم الحالة."""
        bar = make_fp_bar(0, 80.0, 20.0)
        candle = make_candle(0, 100.0, 101.0, 99.9, 100.8)
        vol = make_vol(1.0)
        first = ContinuationEmitter().update(bar, candle, vol)
        second = ContinuationEmitter().update(bar, candle, vol)
        assert first == second

    def test_ascending_order_enforced(self) -> None:
        """الحارس: طابع مكرر/سابق يُرفض — الباعث متسلسل عبر حارس التدفق."""
        emitter = ContinuationEmitter()
        bar = make_fp_bar(0, 80.0, 20.0)
        candle = make_candle(0, 100.0, 101.0, 99.9, 100.8)
        emitter.update(bar, candle, make_vol(1.0))
        with pytest.raises(ValueError, match="تكرار bar_time"):
            emitter.update(bar, candle, make_vol(1.0))
