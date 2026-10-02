"""اختبارات نافذة القراءة المتحركة (§26.3) — المنع المعماري لبيانات المستقبل.

«The replay framework exposes only data available at each simulated
timestamp» — الشمعة لا تُرى إلا مغلقة، والحدث لا يُرى إلا بعد لحظته،
وأي طلب بفهرسة أو بعقارب غير زمنية يُرفض صريحًا.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from _backtest_fixtures import T0, candle_at
from backtest.window import ReplayWindow, timed_event


def test_closed_candles_only_after_full_bar() -> None:
    """شمعة الدقيقة n مرئية عند إغلاقها (n+1 دقيقة) لا قبل — الجارية مخفية دائمًا."""
    window = ReplayWindow(
        candles=(candle_at(0, 1.0, 1.1, 0.9, 1.0), candle_at(1, 1.0, 1.1, 0.9, 1.05)),
        timeframe_s=60.0,
    )
    # عند T0+60s: الشمعة الأولى أغلقت للتو (بدأت 0 وانتهت 60) — وحدها
    visible = window.closed_candles(T0 + timedelta(seconds=60))
    assert [c.bar_time for c in visible] == [T0]
    # عند T0+90s: الثانية ما تزال جارية — الرؤية لم تتغير
    visible = window.closed_candles(T0 + timedelta(seconds=90))
    assert [c.bar_time for c in visible] == [T0]
    # عند T0+120s: الثانية أغلقت
    visible = window.closed_candles(T0 + timedelta(seconds=120))
    assert len(visible) == 2


def test_closed_until_index_monotonic() -> None:
    """موضع القراءة رتيب غير متناقص مع تقدم عقارب المحاكاة."""
    candles = tuple(candle_at(m, 1.0, 1.1, 0.9, 1.0) for m in range(10))
    window = ReplayWindow(candles=candles, timeframe_s=60.0)
    previous = -1
    for minute in range(12):
        count = window.closed_until_index(T0 + timedelta(minutes=minute))
        assert count >= previous
        previous = count
    assert previous == 10


def test_events_until_strictly_past() -> None:
    """الأحداث تُرى عند لحظتها فصاعدًا (≤) — لا مراجعة قبل الإصدار."""
    events = (
        timed_event(event_time=T0 + timedelta(minutes=5), payload="a"),
        timed_event(event_time=T0 + timedelta(minutes=10), payload="b"),
    )
    window = ReplayWindow(candles=(), timeframe_s=60.0, events=events)
    at_5 = window.events_until(T0 + timedelta(minutes=5))
    assert [e.payload for e in at_5] == ["a"]
    at_9 = window.events_until(T0 + timedelta(minutes=9))
    assert [e.payload for e in at_9] == ["a"]
    at_10 = window.events_until(T0 + timedelta(minutes=10))
    assert [e.payload for e in at_10] == ["a", "b"]


def test_unsorted_candles_rejected() -> None:
    """سلسلة غير مرتبة رفض صريح — النافذة تُبنى فوق ترتيب زمني حصرًا."""
    with pytest.raises(ValueError, match="غير مرتبة"):
        ReplayWindow(
            candles=(candle_at(5, 1.0, 1.1, 0.9, 1.0), candle_at(3, 1.0, 1.1, 0.9, 1.0)),
            timeframe_s=60.0,
        )


def test_unsorted_events_rejected() -> None:
    """أحداث غير مرتبة رفض صريح."""
    events = (
        timed_event(event_time=T0 + timedelta(minutes=5), payload="a"),
        timed_event(event_time=T0 + timedelta(minutes=2), payload="b"),
    )
    with pytest.raises(ValueError, match="غير مرتبة"):
        ReplayWindow(candles=(), timeframe_s=60.0, events=events)


def test_non_datetime_as_of_rejected() -> None:
    """العقرب زمني حصرًا — رفض الفهرسة المقنعة برقم (§26.1 event time only)."""
    window = ReplayWindow(candles=(candle_at(0, 1.0, 1.1, 0.9, 1.0),), timeframe_s=60.0)
    with pytest.raises(ValueError, match="datetime"):
        window.closed_candles(3)  # type: ignore[arg-type]


def test_non_positive_timeframe_rejected() -> None:
    """إطار غير موجب رفض صريح."""
    with pytest.raises(ValueError, match="غير موجب"):
        ReplayWindow(candles=(), timeframe_s=0.0)


def test_audit_visible_candles_closed() -> None:
    """تدقيق §26.3-1: المستهلك القانوني يجتاز، ومتطفل المستقبل يُضبط."""
    candles = tuple(candle_at(m, 1.0, 1.1, 0.9, 1.0) for m in range(10))
    window = ReplayWindow(candles=candles, timeframe_s=60.0)
    as_of = T0 + timedelta(minutes=5, seconds=30)
    legal = window.closed_candles(as_of)  # الشموع 0..4
    assert window.audit_visible_candles_closed(as_of, legal)
    smuggled = (*legal, candles[7])  # شمعة مستقبل تهرّبت للمستهلك
    assert not window.audit_visible_candles_closed(as_of, smuggled)
