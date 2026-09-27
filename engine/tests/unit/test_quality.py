"""اختبارات مصنف الجودة (§7.4) — الحالات التسع بحقن حتمي + سلّم الشدة + الأهلية.

الساعة قابلة للحقن (FakeClock) فتختبر STALE/DELAYED/UNAVAILABLE حتميًا بلا
انتظار حقيقي ولا نوم في الاختبارات.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from ingestion.quality import (
    SEVERITY_LADDER,
    SEVERITY_RANK,
    QualityConfig,
    QualityTracker,
    is_decision_eligible,
    worst_quality,
)
from schemas import DataQuality, TradeEvent

NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@dataclass
class FakeClock:
    """ساعة قابلة للحقن — تتقدم يدويًا في الاختبارات (حتمية كاملة)."""

    current: datetime = field(default_factory=lambda: NOW)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def _qevent(
    *,
    symbol: str = "BTCUSDT",
    t_ms: int = 0,
    latency_ms: float = 5.0,
) -> TradeEvent:
    """حدث مرصود — الزمنان مشتقان من NOW بإزاحات صريحة (متسقة مع الساعة المزيفة)."""
    event_time = NOW + timedelta(milliseconds=t_ms)
    return TradeEvent(
        event_time_utc=event_time,
        receive_time_utc=event_time + timedelta(milliseconds=latency_ms),
        source_timeframe="1t",
        venue="binance-usdm-futures",
        symbol=symbol,
        feed_id="binance-usdm-aggtrades",
        sequence_id=None,
        source_latency_ms=latency_ms,
        price=100.0,
        quantity=1.0,
        buyer_is_maker=False,
    )


# ═════════════════════ سلّم الشدة والأسوأ مساهم ═════════════════════


class TestSeverityLadder:
    """السلّم المرتب — أي تعديل فيه يجب أن يكون قرارًا واعيًا (اختبار قفل)."""

    def test_ladder_is_the_documented_order(self) -> None:
        assert SEVERITY_LADDER == (
            DataQuality.HEALTHY,
            DataQuality.DELAYED,
            DataQuality.OUT_OF_ORDER,
            DataQuality.DUPLICATED,
            DataQuality.PARTIAL,
            DataQuality.GAP_DETECTED,
            DataQuality.STALE,
            DataQuality.QUARANTINED,
            DataQuality.UNAVAILABLE,
        )

    def test_rank_covers_all_nine_exactly_once(self) -> None:
        assert len(SEVERITY_RANK) == 9
        assert sorted(SEVERITY_RANK.values()) == list(range(9))

    def test_worst_examples(self) -> None:
        gap, dup = DataQuality.GAP_DETECTED, DataQuality.DUPLICATED
        assert worst_quality(gap, dup) is DataQuality.GAP_DETECTED
        assert worst_quality(DataQuality.HEALTHY, DataQuality.DELAYED) is DataQuality.DELAYED
        assert worst_quality(*SEVERITY_LADDER) is DataQuality.UNAVAILABLE

    def test_worst_requires_input(self) -> None:
        with pytest.raises(ValueError, match="حالة واحدة على الأقل"):
            worst_quality()

    @given(
        states=st.lists(st.sampled_from(SEVERITY_LADDER), min_size=1, max_size=12),
    )
    @hyp_settings(max_examples=50)
    def test_worst_is_max_rank_and_healthy_identity(self, states: list[DataQuality]) -> None:
        """أسوأ مساهم = الأعلى رتبة دائمًا؛ HEALTHY عنصر محايد."""
        expected = max(states, key=SEVERITY_RANK.__getitem__)
        assert worst_quality(*states) is expected
        assert worst_quality(states[0], DataQuality.HEALTHY) is states[0]
        assert worst_quality(*reversed(states)) is expected  # تبديلي


# ═════════════════════ أهلية القرار (§7.4) ═════════════════════


class TestDecisionEligibility:
    """«فقط HEALTHY وDELAYED (بموافقة صريحة) يصلان معالجة القرار العادية»."""

    @pytest.mark.parametrize("state", list(DataQuality))
    def test_only_healthy_by_default(self, state: DataQuality) -> None:
        expected = state is DataQuality.HEALTHY
        assert is_decision_eligible(state) is expected

    @pytest.mark.parametrize("state", list(DataQuality))
    def test_delayed_with_explicit_approval(self, state: DataQuality) -> None:
        expected = state in (DataQuality.HEALTHY, DataQuality.DELAYED)
        assert is_decision_eligible(state, allow_delayed=True) is expected


# ═════════════════════ الحالات التسع بحقن حتمي ═════════════════════


class TestNineStatesInjections:
    """لكل حالة من التسع حقنة تنتجها حتميًا — قواعد الانتقال موثقة في الفئة."""

    def test_healthy_on_clean_observation(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.observe(_qevent()) is DataQuality.HEALTHY
        assert tracker.state_for("BTCUSDT") is DataQuality.HEALTHY

    def test_duplicated_on_report(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        event = _qevent()
        assert tracker.report_duplicate(event) is DataQuality.DUPLICATED
        assert tracker.state_for("BTCUSDT") is DataQuality.DUPLICATED

    def test_out_of_order_on_report(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.report_out_of_order(_qevent()) is DataQuality.OUT_OF_ORDER

    def test_gap_on_report(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.report_gap(_qevent(), 15_000.0) is DataQuality.GAP_DETECTED

    def test_partial_on_report(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.report_partial(_qevent(), 3) is DataQuality.PARTIAL

    def test_quarantined_on_report(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.report_quarantine(_qevent()) is DataQuality.QUARANTINED

    def test_delayed_on_latency_beyond_threshold(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        slow = _qevent(latency_ms=1_500.0)  # العتبة الافتراضية 1000ms
        assert tracker.observe(slow) is DataQuality.DELAYED

    def test_delayed_threshold_is_strict(self) -> None:
        """المساواة بالعتبة ليست تجاوزًا — الحد صارم."""
        tracker = QualityTracker(clock=lambda: NOW)
        boundary = _qevent(latency_ms=1_000.0)
        assert tracker.observe(boundary) is DataQuality.HEALTHY

    def test_none_latency_is_clean(self) -> None:
        """مصدر بلا قياس كمون: معلومة غائبة ليست اتهامًا (موثق)."""
        tracker = QualityTracker(clock=lambda: NOW)
        event = _qevent().model_copy(update={"source_latency_ms": None})
        assert tracker.observe(event) is DataQuality.HEALTHY

    def test_stale_on_silence_beyond_threshold(self) -> None:
        clock = FakeClock()
        tracker = QualityTracker(clock=clock)
        tracker.observe(_qevent())
        clock.advance(10.5)  # stale_after الافتراضي 10s
        assert tracker.state_for("BTCUSDT") is DataQuality.STALE

    def test_unavailable_on_longer_silence(self) -> None:
        """«عدم توفر بعد توفر سابق»: صمت يتجاوز unavailable_after يصعّد إلى UNAVAILABLE."""
        clock = FakeClock()
        tracker = QualityTracker(clock=clock)
        tracker.observe(_qevent())
        clock.advance(60.5)  # unavailable_after الافتراضي 60s
        assert tracker.state_for("BTCUSDT") is DataQuality.UNAVAILABLE

    def test_unavailable_for_never_seen_symbol(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        assert tracker.state_for("NEVERSEEN") is DataQuality.UNAVAILABLE

    def test_stale_cleared_by_fresh_arrival(self) -> None:
        """السكون تقييم كسول — وصول جديد يطرّي الحالة فورًا."""
        clock = FakeClock()
        tracker = QualityTracker(clock=clock)
        tracker.observe(_qevent(t_ms=0))
        clock.advance(15.0)
        assert tracker.state_for("BTCUSDT") is DataQuality.STALE
        fresh = _qevent(t_ms=15_000, latency_ms=5.0)  # استلامه «الآن» بعد التقدم
        assert tracker.observe(fresh) is DataQuality.HEALTHY

    def test_stale_overlay_does_not_mask_worse_base(self) -> None:
        """التراكب يأخذ أسوأ مساهم — QUARANTINED لا يختفي خلف STALE."""
        clock = FakeClock()
        tracker = QualityTracker(clock=clock)
        tracker.observe(_qevent())
        tracker.report_quarantine(_qevent(t_ms=10))
        clock.advance(11.0)  # سكون فوق العتبلة لكن دون التصعيد
        assert tracker.state_for("BTCUSDT") is DataQuality.QUARANTINED

    def test_unavailable_wins_over_everything(self) -> None:
        clock = FakeClock()
        tracker = QualityTracker(clock=clock)
        tracker.observe(_qevent())
        tracker.report_quarantine(_qevent(t_ms=10))
        clock.advance(120.0)  # صمت يتجاوز التصعيد — UNAVAILABLE يفوز دائمًا
        assert tracker.state_for("BTCUSDT") is DataQuality.UNAVAILABLE


# ═════════════════════ التعافي وحدود التهيئة ═════════════════════


class TestRecoveryAndConfig:
    """شرط عودة HEALTHY (N نظيف متتالٍ) وحدود QualityConfig."""

    def test_recovery_after_clean_streak(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        tracker.report_duplicate(_qevent())
        for i in range(4):  # N-1 نظيف — لا يزال متدهورًا
            state = tracker.observe(_qevent(t_ms=(i + 1) * 100))
        assert state is DataQuality.DUPLICATED
        state = tracker.observe(_qevent(t_ms=500))  # الخامس يكمل السلسلة
        assert state is DataQuality.HEALTHY

    def test_delayed_recovers_by_same_mechanism(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        tracker.observe(_qevent(latency_ms=5_000.0))
        assert tracker.state_for("BTCUSDT") is DataQuality.DELAYED
        for i in range(5):
            tracker.observe(_qevent(t_ms=(i + 1) * 100))
        assert tracker.state_for("BTCUSDT") is DataQuality.HEALTHY

    def test_new_degradation_resets_streak(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        tracker.report_duplicate(_qevent())
        for i in range(3):
            tracker.observe(_qevent(t_ms=(i + 1) * 100))
        # تدهور جديد (أشد — أسوأ مساهم يفوز) يصفّر السلسلة من جديد
        tracker.report_gap(_qevent(t_ms=400), 20_000.0)
        assert tracker.state_for("BTCUSDT") is DataQuality.GAP_DETECTED
        for i in range(3):
            state = tracker.observe(_qevent(t_ms=500 + i * 100))
        assert state is DataQuality.GAP_DETECTED  # أربعة لم تكمل السلسلة بعد

    def test_symbols_are_independent(self) -> None:
        tracker = QualityTracker(clock=lambda: NOW)
        tracker.report_duplicate(_qevent(symbol="BTCUSDT"))
        assert tracker.state_for("BTCUSDT") is DataQuality.DUPLICATED
        assert tracker.observe(_qevent(symbol="ETHUSDT")) is DataQuality.HEALTHY

    def test_worst_degradation_wins_within_window(self) -> None:
        """إشارتان متتاليتان — الأسوأ مساهمًا يبقى حتى التعافي الموحد."""
        tracker = QualityTracker(clock=lambda: NOW)
        tracker.report_duplicate(_qevent())
        tracker.report_gap(_qevent(t_ms=100), 20_000.0)
        assert tracker.state_for("BTCUSDT") is DataQuality.GAP_DETECTED

    def test_config_validations(self) -> None:
        with pytest.raises(ValueError, match="unavailable_after_s"):
            QualityConfig(stale_after_s=10.0, unavailable_after_s=10.0)
        with pytest.raises(ValueError, match="healthy_recovery_events"):
            QualityConfig(healthy_recovery_events=0)
        with pytest.raises(ValueError, match="delayed_after_ms"):
            QualityConfig(delayed_after_ms=-1.0)
