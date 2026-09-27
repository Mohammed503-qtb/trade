"""اختبارات وحدة خط التنقيح (§33.1) — fixtures مكرر/معكوس/فجوة/أداة غير مسموحة.

كل قرار (إسقاط/رفض/إدراج متأخر) له فعل محسوب في stats — لا قرار صامت،
وخاصية hypothesis تثبت حفاظ المحصلة: المدخل = المخرجات + المكرر + المرفوض.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from ingestion.quality import QualityTracker
from ingestion.refine import RefinementAction, RefinementConfig, RefinementPipeline
from pydantic import ValidationError
from schemas import DataQuality, TradeEvent

BASE_TIME = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def _event(
    *,
    seq: str | None = "1",
    symbol: str = "BTCUSDT",
    t_ms: int = 0,
    latency_ms: float = 5.0,
    price: float = 100.0,
) -> TradeEvent:
    """حدث قانوني قابل للتوليف — الزمن مشتق من إزاحة ملي ثانية عن BASE_TIME."""
    event_time = BASE_TIME + timedelta(milliseconds=t_ms)
    receive_time = event_time + timedelta(milliseconds=latency_ms)
    return TradeEvent(
        event_time_utc=event_time,
        receive_time_utc=receive_time,
        source_timeframe="1t",
        venue="binance-usdm-futures",
        symbol=symbol,
        feed_id="binance-usdm-aggtrades",
        sequence_id=seq,
        source_latency_ms=latency_ms,
        price=price,
        quantity=1.0,
        buyer_is_maker=False,
    )


class TestLiteralPipelineStages:
    """المراحل الحرفية لـ§33.1 على fixtures اليدوية."""

    def test_first_event_accepted(self) -> None:
        pipeline = RefinementPipeline(allowed_symbols={"BTCUSDT"})
        result = pipeline.process(_event(seq="1"))
        assert result.action is RefinementAction.ACCEPTED
        assert result.event is not None
        assert result.event.sequence_id == "1"
        assert result.signals == ()
        stats = pipeline.stats()
        assert stats.received == 1
        assert stats.accepted == 1

    def test_duplicate_dropped_and_counted(self) -> None:
        """مكرر: يُسقط، يُحصى، ويوسم DUPLICATED — لا صمت."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        pipeline = RefinementPipeline(tracker=tracker)
        first = pipeline.process(_event(seq="10"))
        assert first.action is RefinementAction.ACCEPTED
        second = pipeline.process(_event(seq="10", t_ms=1))
        assert second.action is RefinementAction.DUPLICATE_DROPPED
        assert second.event is None
        assert DataQuality.DUPLICATED in second.signals
        stats = pipeline.stats()
        assert stats.duplicates_dropped == 1
        assert stats.accepted == 1
        assert tracker.state_for("BTCUSDT") is DataQuality.DUPLICATED

    def test_out_of_order_inserted_late_not_dropped(self) -> None:
        """معكوس: يُدرج متأخرًا موسومًا — الحذف الصامت محظور (قرار موثق)."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        pipeline = RefinementPipeline(tracker=tracker)
        pipeline.process(_event(seq="5", t_ms=500))
        late = pipeline.process(_event(seq="3", t_ms=300))
        assert late.action is RefinementAction.LATE_INSERTED
        assert late.event is not None, "الحدث القديم الواصل متأخرًا يُدرج لا يُحذف"
        assert DataQuality.OUT_OF_ORDER in late.signals
        assert pipeline.stats().late_inserted == 1
        assert tracker.state_for("BTCUSDT") is DataQuality.OUT_OF_ORDER

    def test_sequence_jump_signals_partial(self) -> None:
        """فقد داخل الشريحة: قفزة معرفات ⇒ PARTIAL مع عدّ المفقود."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        pipeline = RefinementPipeline(tracker=tracker)
        pipeline.process(_event(seq="1", t_ms=0))
        result = pipeline.process(_event(seq="5", t_ms=100))
        assert result.action is RefinementAction.ACCEPTED
        assert result.missing_sequence_count == 3
        assert DataQuality.PARTIAL in result.signals
        assert pipeline.stats().sequence_jumps == 1
        assert tracker.state_for("BTCUSDT") is DataQuality.PARTIAL

    def test_disallowed_symbol_rejected(self) -> None:
        """أداة غير مسموحة: تُرفض بوسم QUARANTINED وتحصى."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        pipeline = RefinementPipeline(allowed_symbols={"BTCUSDT"}, tracker=tracker)
        result = pipeline.process(_event(symbol="ETHUSDT", seq="1"))
        assert result.action is RefinementAction.REJECTED_INSTRUMENT
        assert result.event is None
        assert DataQuality.QUARANTINED in result.signals
        assert pipeline.stats().rejected_instrument == 1
        assert tracker.state_for("ETHUSDT") is DataQuality.QUARANTINED

    def test_allowed_none_means_all(self) -> None:
        pipeline = RefinementPipeline()
        result = pipeline.process(_event(symbol="ETHUSDT", seq="1"))
        assert result.action is RefinementAction.ACCEPTED

    def test_naive_timestamp_quarantined(self) -> None:
        """دفاع عمق: model_construct يتجاوز تحقق pydantic — الخط يمسك الساذج."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        pipeline = RefinementPipeline(tracker=tracker)
        raw = TradeEvent.model_construct(
            event_time_utc=datetime(2024, 1, 1),  # ساذج — لا يمر عبر schemas أبدًا
            receive_time_utc=BASE_TIME,
            source_timeframe="1t",
            venue="binance-usdm-futures",
            symbol="BTCUSDT",
            feed_id="binance-usdm-aggtrades",
            sequence_id="1",
            source_latency_ms=5.0,
            price=100.0,
            quantity=1.0,
            buyer_is_maker=False,
        )
        result = pipeline.process(raw)
        assert result.action is RefinementAction.QUARANTINED_TIMESTAMP
        assert result.event is None
        assert pipeline.stats().quarantined == 1
        assert tracker.state_for("BTCUSDT") is DataQuality.QUARANTINED

    def test_events_without_sequence_fall_back_to_time(self) -> None:
        """مصدر بلا تسلسل: مقارنة زمنية فقط، والخصم مستحيل بلا مفتاح (موثق)."""
        pipeline = RefinementPipeline()
        first = pipeline.process(_event(seq=None, t_ms=1000))
        assert first.action is RefinementAction.ACCEPTED
        # إعادة توصيل نفس الحدث بلا مفتاح خصم — تُقبل (لا تمييز ممكن بلا مفتاح)
        again = pipeline.process(_event(seq=None, t_ms=1000))
        assert again.action is RefinementAction.ACCEPTED
        # ثم حدث أقدم زمنًا ⇒ إدراج متأخر عبر المقارنة الزمنية
        late = pipeline.process(_event(seq=None, t_ms=500))
        assert late.action is RefinementAction.LATE_INSERTED
        assert DataQuality.OUT_OF_ORDER in late.signals

    def test_schemas_reject_broken_event_first(self) -> None:
        """schemas نفسها ترفض الحدث الفاسد قبل الخط — طبقة الدفاع الأولى."""
        with pytest.raises(ValidationError):
            _event(price=-1.0)


class TestDuplicateWindow:
    """نافذة LRU: حجمها الموثق وحدودها المعلنة (إعادة توصيل أقدم من النافذة)."""

    def test_eviction_older_redelivery_becomes_late_insert(self) -> None:
        """توثيق تنفيذي للحد: إعادة توصيل خرجت من النافذة تظهر إدراجًا متأخرًا
        لا تكرارًا — التمييز يحتاج مخزنًا دائمًا (يسدده 1.5)، ولا حذف صامت أبدًا."""
        pipeline = RefinementPipeline(config=RefinementConfig(duplicate_window=4))
        for seq in range(1, 7):  # المفاتيح 1،2 تُطرد من نافذة حجمها 4
            pipeline.process(_event(seq=str(seq), t_ms=seq * 100))
        redelivered = pipeline.process(_event(seq="1", t_ms=100))
        assert redelivered.action is RefinementAction.LATE_INSERTED
        assert redelivered.event is not None, "لا حذف صامت حتى خارج نافذة الخصم"
        assert DataQuality.OUT_OF_ORDER in redelivered.signals

    def test_watermark_duplicate_beyond_lru_still_dropped(self) -> None:
        """مضاعفة تطابق العلامة المائية بعد خروجها من النافذة — إسقاط محسوب."""
        pipeline = RefinementPipeline(config=RefinementConfig(duplicate_window=2))
        for seq in (1, 2, 3, 4):
            pipeline.process(_event(seq=str(seq), t_ms=seq * 100))
        pipeline.process(_event(seq="2", t_ms=200))  # إدراج متأخر — يدخل النافذة
        pipeline.process(_event(seq="3", t_ms=300))  # إدراج متأخر — يطرد 4
        # الآن 4 خارج النافذة لكنه العلامة المائية — إعادة توصيله إسقاط تكرار
        result = pipeline.process(_event(seq="4", t_ms=400))
        assert result.action is RefinementAction.DUPLICATE_DROPPED
        assert DataQuality.DUPLICATED in result.signals


class TestGapDetection:
    """فجوة: عتبة تكيفية 3× وسيط الفواصل المتدحرجة فوق أرضية مطلقة."""

    def test_no_gap_within_threshold(self) -> None:
        config = RefinementConfig(gap_floor_ms=100.0, gap_multiplier=3.0)
        pipeline = RefinementPipeline(config=config)
        for i in range(12):
            result = pipeline.process(_event(seq=str(i + 1), t_ms=i * 100))
            assert result.gap_ms is None
        assert pipeline.stats().gaps_detected == 0

    def test_gap_raised_beyond_adaptive_threshold(self) -> None:
        """فواصل 100ms متتالية ترفع الوسيط — فاصل 500ms يتجاوز 3× الوسيط (300ms)."""
        tracker = QualityTracker(clock=lambda: BASE_TIME)
        config = RefinementConfig(gap_floor_ms=100.0, gap_multiplier=3.0)
        pipeline = RefinementPipeline(tracker=tracker, config=config)
        for i in range(10):
            pipeline.process(_event(seq=str(i + 1), t_ms=i * 100))
        result = pipeline.process(_event(seq="11", t_ms=9 * 100 + 500))
        assert result.gap_ms == pytest.approx(500.0)
        assert DataQuality.GAP_DETECTED in result.signals
        assert pipeline.stats().gaps_detected == 1
        assert tracker.state_for("BTCUSDT") is DataQuality.GAP_DETECTED

    def test_gap_floor_dominates_during_warmup(self) -> None:
        """قبل اكتمال عينات الإحماء العتبة أرضية مطلقة — لا وسيط بلا عينات."""
        pipeline = RefinementPipeline(
            config=RefinementConfig(gap_floor_ms=10_000.0, gap_warmup=8),
        )
        pipeline.process(_event(seq="1", t_ms=0))
        # فاصل 500ms تحت الأرضية 10s خلال الإحماء ⇒ لا فجوة
        result = pipeline.process(_event(seq="2", t_ms=500))
        assert result.gap_ms is None

    def test_late_events_do_not_pollute_gap_window(self) -> None:
        """الفواصل السالبة (متأخرات) لا تدخل نافذة الوسيط (موثق).

        السيناريو الواقعي: 1، 2 تصل، ثم 4 (قفزة — 3 مفقود)، ثم 3 يصل متأخراً
        بمعرف غير مرئي تحت العلامة المائية — إدراج متأخر لا مكرر (المكرر
        معرف مستهلك أصلًا)، وفاصله الزمني سالب فلا يدخل النافذة.
        """
        config = RefinementConfig(gap_floor_ms=100.0, gap_multiplier=3.0)
        pipeline = RefinementPipeline(config=config)
        pipeline.process(_event(seq="1", t_ms=0))
        pipeline.process(_event(seq="2", t_ms=100))
        pipeline.process(_event(seq="4", t_ms=200))  # قفزة فوق 3
        late = pipeline.process(_event(seq="3", t_ms=150))  # متأخر بمعرف جديد
        assert late.action is RefinementAction.LATE_INSERTED
        assert late.gap_ms is None
        # النافذة لم تتلوث بفاصل سالب: آخر فاصل موجب مسجل 100ms لا -50ms
        # (تحقق سلوكي: حدث لاحق بفاصل 50ms تحت الأرضية 100ms لا يُعلن فجوة)
        after = pipeline.process(_event(seq="5", t_ms=250))
        assert after.action is RefinementAction.ACCEPTED
        assert after.gap_ms is None


class TestStatsAccounting:
    """الثابت الحسابي: كل وارد له فعل واحد بالضبط والمحصلة محفوظة."""

    def test_stats_actions_partition(self) -> None:
        pipeline = RefinementPipeline(allowed_symbols={"BTCUSDT"})
        pipeline.process(_event(seq="1"))
        pipeline.process(_event(seq="1", t_ms=1))  # مكرر
        pipeline.process(_event(seq="9", t_ms=200))  # قفزة
        pipeline.process(_event(symbol="ETHUSDT", seq="1"))  # مرفوض
        pipeline.process(_event(seq="5", t_ms=150))  # متأخر
        stats = pipeline.stats()
        assert stats.received == 5
        assert stats.accepted == 2  # 1 و9
        assert stats.late_inserted == 1
        assert stats.duplicates_dropped == 1
        assert stats.rejected_instrument == 1
        assert (
            stats.received
            == stats.accepted
            + stats.late_inserted
            + stats.duplicates_dropped
            + stats.rejected_instrument
            + stats.quarantined
        )

    def test_no_tracker_is_fine(self) -> None:
        """الخط يعمل بلا مصنف — الإشارات في النتيجة والحصيلة في stats."""
        pipeline = RefinementPipeline()
        result = pipeline.process(_event(seq="1"))
        assert result.action is RefinementAction.ACCEPTED


# ═════════════════════ خاصية الحفاظ (hypothesis) ═════════════════════

_ALLOWED = "BTCUSDT"
_FOREIGN = "ETHUSDT"


@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    length=st.integers(min_value=0, max_value=120),
)
@hyp_settings(max_examples=40, deadline=None)
def test_property_no_clean_event_lost_silently(seed: int, length: int) -> None:
    """تسلسل عشوائي مُبذَّر: لا حدث سليم يُفقد صمتًا.

    المحصلة = المدخل - المكرر - المرفوض: كل حدث إما يخرج (مقبولًا أو
    مُدرجًا متأخرًا) أو يُسقط/يُرفض بفعل محسوب. التصنيف المتوقع يُشتق
    بنموذج مرجعي مستقل (LRU + علامة مائية) ويطابق فعل الخط حدثًا حدثًا.
    """
    # بذور الاختبار ليست تشفيرًا — S311 غير منطبق (توليد fixtures حتمي)
    rng = random.Random(seed)  # noqa: S311
    config = RefinementConfig(
        duplicate_window=8,
        gap_floor_ms=10**9,  # الفجوات معطلة هنا — ليست محل هذه الخاصية
    )
    pipeline = RefinementPipeline(allowed_symbols={_ALLOWED}, config=config)

    next_seq = {_ALLOWED: 1, _FOREIGN: 1}
    high_water = {_ALLOWED: 0, _FOREIGN: 0}
    emitted: dict[str, list[int]] = {_ALLOWED: [], _FOREIGN: []}
    emitted_any = {_ALLOWED: False, _FOREIGN: False}  # هل وصل أي حدث للمرحلة 5؟
    lru: OrderedDict[tuple[str, int], None] = OrderedDict()  # نموذج النافذة
    expected_outputs = 0

    for _ in range(length):
        symbol = _ALLOWED if rng.random() < 0.7 else _FOREIGN
        kind = rng.choice(["fresh", "fresh", "dup", "jump"])
        seq: int
        if kind == "dup" and emitted[symbol]:
            seq = rng.choice(emitted[symbol])  # إعادة توصيل لمعرف سابق
        elif kind == "jump":
            seq = next_seq[symbol] + rng.randint(1, 3)
            next_seq[symbol] = seq + 1
        else:
            seq = next_seq[symbol]
            next_seq[symbol] += 1
        event = _event(symbol=symbol, seq=str(seq), t_ms=seq * 100)

        watermark_before = high_water[symbol]
        key = (symbol, seq)
        # النموذج المرجعي المستقل — يطابق ترتيب مراحل §33.1
        if symbol != _ALLOWED:
            expected = RefinementAction.REJECTED_INSTRUMENT
        elif key in lru or seq == watermark_before:
            expected = RefinementAction.DUPLICATE_DROPPED
        elif seq < watermark_before:
            expected = RefinementAction.LATE_INSERTED
        else:
            expected = RefinementAction.ACCEPTED

        result = pipeline.process(event)
        assert result.action is expected, (
            f"seed={seed} seq={seq} symbol={symbol} kind={kind}: "
            f"توقع {expected} ووصل {result.action}"
        )
        if expected in (RefinementAction.ACCEPTED, RefinementAction.LATE_INSERTED):
            assert result.event is event, "الحدث السليم يعاد كما هو — لا نسخ ولا فقد"
            expected_outputs += 1
            lru[key] = None
            lru.move_to_end(key)
            while len(lru) > 8:
                lru.popitem(last=False)
            if seq > high_water[symbol]:
                high_water[symbol] = seq
            # عدّ المفقود يُطلب فقط بوجود سابقة فعلية (علامة مائية محققة):
            # أول حدث في المجرى لا سابقة له فالخط يحتسب 0 بحق — لا نعرف إن
            # كان ما قبله مفقوداً أو المجرى بدأ للتو (قرار موثق في refine.py).
            if (
                expected is RefinementAction.ACCEPTED
                and emitted_any[symbol]
                and (seq > watermark_before + 1)
            ):
                assert result.missing_sequence_count == seq - watermark_before - 1
            emitted_any[symbol] = True
        if seq not in emitted[symbol]:
            emitted[symbol].append(seq)

    stats = pipeline.stats()
    assert stats.received == length
    assert stats.accepted + stats.late_inserted == expected_outputs
    assert (
        stats.received
        == stats.accepted
        + stats.late_inserted
        + stats.duplicates_dropped
        + stats.rejected_instrument
        + stats.quarantined
    ), "المحصلة = المدخل - المكرر - المرفوض — لا حدث يختفي بلا فعل"
