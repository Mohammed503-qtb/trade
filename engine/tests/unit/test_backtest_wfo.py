"""اختبارات التدحرج الأمامي (§39.3) — البروتوكول والحجز الزمني ورفض النقص.

بروتوكول البحث 2000/500/500 خطوة 500 يُثبت على مرشحين اصطناعيين
حتميين؛ والحجز **زمني** يُثبت بمرشحين متزاحمين (الفجوة الزمنية وحدها
تفصل الطيات لا العدد).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from backtest import DEFAULT_SAMPLE_WFO_PROTOCOL, WFOProtocolError, research_protocol, split_windows
from schemas import WFOProtocolConfig, WFORole, WFOSegment


def _times(count: int, *, spacing_s: float = 60.0, start: datetime | None = None) -> list[datetime]:
    """لحظات مرشحين متباعدة بانتظام — حتمية بالكامل."""
    base = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [base + timedelta(seconds=spacing_s * i) for i in range(count)]


def test_research_protocol_defaults() -> None:
    """بروتوكول البحث حرفي §39.3: 2000/500/500 خطوة 500."""
    protocol = research_protocol(embargo_s=14_400.0)
    assert protocol.train_candidates == 2000
    assert protocol.validation_candidates == 500
    assert protocol.oos_candidates == 500
    assert protocol.step_candidates == 500
    assert protocol.embargo_s == 14_400.0
    assert protocol.protocol_name == "RESEARCH_2000_500_500"


def test_research_protocol_splits_on_synthetic() -> None:
    """5000 مرشح متباعد دقيقة: نوافذ كاملة بطيات ثلاث وحجز زمني محقق.

    النافذة تستهلك 2000 تدريب + حجز (240 مرشحًا عند دقيقة التباعد و4
    ساعات حجز) + 500 تحقق + حجز + 500 خارج = 3480؛ بخطوة 500 تتسع
    نافذتان (0 و500) ضمن 5000.
    """
    protocol = research_protocol(embargo_s=14_400.0)
    times = _times(5000)
    report = split_windows(times, protocol)
    assert len(report.windows) == 4  # البدايات 0 و500 و1000 و1500 — 1500+3480 ≤ 5000
    first = report.windows[0]
    assert first.window_index == 0
    # الطيات الثلاث بلا تقاطع داخل النافذة
    segments = {s.role: s for s in first.segments}
    assert segments[WFORole.TRAIN].first_index == 0
    assert segments[WFORole.TRAIN].last_index == 1999
    assert segments[WFORole.VALIDATION].first_index == 2239  # بعد الحجز 14400s بالضبط
    assert segments[WFORole.OUT_OF_SAMPLE].first_index == 2978  # 2739 + الحجز نفسه
    assert segments[WFORole.OUT_OF_SAMPLE].last_index == 3477
    # النافذة التالية تتدحرج 500
    second_train = {s.role: s for s in report.windows[1].segments}[WFORole.TRAIN]
    assert second_train.first_index == 500
    # الحجز الزمني محقق عند الحدين
    assert first.embargo_boundaries_s[0] == pytest.approx(14_400.0)
    assert first.embargo_boundaries_s[1] == pytest.approx(14_400.0)
    assert report.embargoed_count == 4 * 478  # حجران (239 مرشحًا لكل حد) × 4 نوافذ


def test_embargo_is_time_based_not_count_based() -> None:
    """مرشحون متزاحمون داخل الحجز لا يدخلون الطية التالية — الزمن يفصل.

    100 مرشحًا في أول 10 دقائق (6 ثوانٍ تباعدًا) ثم بقية متباعدة:
    حجز 4 ساعات يقفز فوق المتزاحمين كلهم.
    """
    protocol = WFOProtocolConfig(
        protocol_name="TEST_DENSE",
        train_candidates=10,
        validation_candidates=5,
        oos_candidates=5,
        step_candidates=5,
        embargo_s=14_400.0,
    )
    dense = _times(30, spacing_s=6.0)  # أول 30 مرشحًا في 3 دقائق
    sparse = _times(60, spacing_s=600.0, start=dense[-1] + timedelta(hours=6))
    times = dense + sparse
    report = split_windows(times, protocol)
    window = report.windows[0]
    segments = {s.role: s for s in window.segments}
    assert segments[WFORole.TRAIN].last_index == 9
    # التحقق يبدأ بعد لحظة آخر تدريب + 4 ساعات — خارج الكتلة المتزاحمة كلها
    validation_start_time = times[segments[WFORole.VALIDATION].first_index]
    assert validation_start_time >= times[9] + timedelta(seconds=14_400.0)
    assert segments[WFORole.VALIDATION].first_index >= 30


def test_insufficient_candidates_rejected_loudly() -> None:
    """نقص المرشحين رفض صاخب يسرد المتطلبات — لا تقسيم منقوص يدّعي بحثًا."""
    protocol = research_protocol(embargo_s=14_400.0)
    with pytest.raises(WFOProtocolError, match="لا يكملون نافذة"):
        split_windows(_times(100), protocol)


def test_unsorted_times_rejected() -> None:
    """لحظات غير مرتبة رفض صريح (§39.3 زمنية-الترتيب حصرًا)."""
    protocol = WFOProtocolConfig(
        protocol_name="T",
        train_candidates=2,
        validation_candidates=1,
        oos_candidates=1,
        step_candidates=1,
        embargo_s=0.0,
    )
    times = _times(10)
    shuffled = [times[1], times[0], *times[2:]]
    with pytest.raises(WFOProtocolError, match="غير مرتبة"):
        split_windows(shuffled, protocol)


def test_sample_structure_protocol_shape() -> None:
    """بروتوكول بنية العينة المعلن — أعداده أصغر واسمه صريح لا يدّعي بحثًا."""
    protocol = WFOProtocolConfig.model_validate(DEFAULT_SAMPLE_WFO_PROTOCOL)
    assert protocol.protocol_name == "SAMPLE_STRUCTURE"
    assert protocol.step_candidates <= protocol.validation_candidates + protocol.oos_candidates
    # يتسع على مرشحين متباعدين ربع-ساعة (103 قرارات عبر 24 ساعة نمطًا)
    times = _times(103, spacing_s=840.0)
    report = split_windows(times, protocol)
    assert len(report.windows) >= 1
    for window in report.windows:
        segments = {s.role: s for s in window.segments}
        assert segments[WFORole.TRAIN].last_index >= segments[WFORole.TRAIN].first_index + 19
        assert segments[WFORole.OUT_OF_SAMPLE].last_index < 103


def test_report_schema_legality() -> None:
    """التقرير يمر عقد schemas — الطيات مرتبة والحدود داخل المرشحين."""
    protocol = WFOProtocolConfig(
        protocol_name="T",
        train_candidates=10,
        validation_candidates=5,
        oos_candidates=5,
        step_candidates=5,
        embargo_s=60.0,
    )
    report = split_windows(_times(100), protocol)
    assert report.candidates_count == 100
    for window in report.windows:
        for segment in window.segments:
            assert isinstance(segment, WFOSegment)
            assert segment.last_index < 100
