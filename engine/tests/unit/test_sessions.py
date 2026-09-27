"""اختبارات وحدة الجلسات وبنية الفتح (المهمة 2.3) — §9.4/§9.5 وقرار A-03.

التغطية المطلوبة (بوابة 2.3 — اختبارات حدود زمنية):
- انتقال منتصف الليل UTC: 23:59 ثم 00:00 ⇒ جلسة جديدة وprior_* من السابقة.
- حواف النوافذ [بداية، نهاية) حرفيًا: 00:00 داخل آسيا، 08:00 خارجها، 07:00
  داخل أوروبا وآسيا معًا (تقاطع)، مع خطر الانتقال داخل edge_minutes من الحواف.
- نوافذ عابرة لمنتصف الليل (مخصصة 22:00-02:00) واليوم الكامل والفارغة.
- DST لا وجود له: طوابع صيفية وشتوية بنفس دقائق UTC معاملة واحدة، والمناطق
  الأخرى تُطبَّن إلى UTC لا تُقرأ بقراءة الساعة المحلية.
- بنية الفتح §9.5: فجوة صعودية/هبوطية/صفرية، مدى افتتاحي يكتمل بعد N دقيقة
  ويجمد، رصيد أولي، دافعة صاعدة/هابطة/انعكاس بقيم محسوبة يدويًا، علاقة
  الإغلاق السابق، وأول شمعة بلا سياق (None).
- الترتيب: شموع متأخرة لجلسة سابقة بعد بدء الجديدة تعامل وفق العقد الموثق
  (تمتص في مجاميع جلستها، بلا إسقاط صامت، وبلا تعديل رجعي لـprior_*).
- اللا-نظرة-المستقبلية: خاصية hypothesis بأسلوب derandomize — حالة البادئة
  المقطوعة أصلًا تساوي حالة القائمة الكاملة عند الموضع نفسه.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from market_state.sessions import (
    AMERICA_WINDOW,
    ASIA_WINDOW,
    DEFAULT_SESSION_WINDOWS,
    EUROPE_WINDOW,
    OpeningDrive,
    PriorCloseRelation,
    SessionState,
    SessionTracker,
    SessionWindow,
    SessionWindowsConfig,
    is_utc_day_boundary,
    timeframe_minutes,
    utc_session_id,
)
from schemas import Candle, DataQuality

# ───────── ثوابت وأدوات ─────────

# نقطة انطلاق ثابتة (الأحد 2026-09-27 — السوق 24/7 فلا أيام عمل)
_DAY0 = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)

# نافذة صيانة اختبارية 16:00-16:05 UTC
_MAINT_WINDOW = SessionWindow("MAINTENANCE", 960, 965, "صيانة اختبارية")

# مناطق زمنية تعبيرية لإثبات التطبيع إلى UTC (لا قراءة ساعة محلية)
_UTC_PLUS_1 = timezone(timedelta(hours=1))
_UTC_PLUS_2 = timezone(timedelta(hours=2))
_UTC_PLUS_3 = timezone(timedelta(hours=3))

# حد اليوم بالدقائق (للمشيئة الدائرية في الخاصية)
_MINUTES_PER_DAY = 1440


def _at(day: int, hour: int, minute: int) -> datetime:
    """طابع UTC ثابت لدقيقة معينة من يوم الاختبار (27/28/29...)."""
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def _candle(
    bar_time: datetime,
    *,
    open_: float = 100.0,
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    volume: float = 10.0,
    timeframe: str = "1m",
    is_closed: bool = True,
) -> Candle:
    """شمعة اصطناعية بقيم مشتقة متسقة بسيطة.

    المدقق هنا هو المتتبع — لا يقرأ من الشمعة إلا bar_time/OHLCV/timeframe؛
    القيم المشتقة تُملأ متسقة (range/body/wicks/النسب) كي يبقى الكائن قانونيًا
    بلا معنى زائد. high/low اختيارية وتُطبَّع إلى مدى صالح (h ≥ max(o,c)،
    l ≤ min(o,c)).
    """
    opened = open_
    closed = close
    high_v = max(opened, closed) if high is None else max(opened, closed, high)
    low_v = min(opened, closed) if low is None else min(opened, closed, low)
    span = high_v - low_v
    body = abs(closed - opened)
    if span > 0.0:
        body_fraction = body / span
        close_location = (closed - low_v) / span
    else:
        # شمعة بلا مدى: اتفاقية منشئ الشموع الموثقة (المهمة 1.4)
        body_fraction = 0.0
        close_location = 0.5
    return Candle(
        instrument_id="BINANCE_USDM:BTCUSDT",
        timeframe=timeframe,
        bar_time=bar_time,
        session_id=utc_session_id(bar_time),
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=opened,
        high=high_v,
        low=low_v,
        close=closed,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high_v - max(opened, closed),
        lower_wick=min(opened, closed) - low_v,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=span,  # قيمة متسقة بسيطة — المتتبع لا يقرأها
        realized_volatility=abs(math.log(closed / opened)),
    )


def _c(
    day: int,
    hour: int,
    minute: int,
    open_: float,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float = 10.0,
    timeframe: str = "1m",
) -> Candle:
    """اختزال شمعة بطابع يوم/ساعة/دقيقة من أيام الاختبار."""
    return _candle(
        _at(day, hour, minute),
        open_=open_,
        close=close,
        high=high,
        low=low,
        volume=volume,
        timeframe=timeframe,
    )


def _names_at(moment: datetime) -> list[str]:
    """أسماء النوافذ الفعالة افتراضيًا عند لحظة (قراءة مستقلة عن المتتبع)."""
    return [active.window.name for active in DEFAULT_SESSION_WINDOWS.active_at(moment)]


# ───────── SessionWindow: الحواف والالتفاف والتحقق ─────────


class TestSessionWindowBasics:
    """دلالة [بداية، نهاية) حرفيًا + الالتفاف + اليوم الكامل + الفارغة."""

    def test_edge_start_inclusive_end_exclusive(self) -> None:
        """00:00 داخل آسيا؛ 07:59 داخلها؛ 08:00 خارجها (نهاية حصرية)."""
        assert ASIA_WINDOW.contains(_at(27, 0, 0)) is True
        assert ASIA_WINDOW.contains(_at(27, 7, 59)) is True
        assert ASIA_WINDOW.contains(_at(27, 8, 0)) is False
        assert ASIA_WINDOW.contains(_at(27, 23, 59)) is False

    def test_europe_and_america_edges(self) -> None:
        """أوروبا 07:00-16:00 وأمريكا 13:30-20:00 بنفس الدلالة."""
        assert EUROPE_WINDOW.contains(_at(27, 7, 0)) is True
        assert EUROPE_WINDOW.contains(_at(27, 15, 59)) is True
        assert EUROPE_WINDOW.contains(_at(27, 16, 0)) is False
        assert AMERICA_WINDOW.contains(_at(27, 13, 30)) is True
        assert AMERICA_WINDOW.contains(_at(27, 13, 29)) is False
        assert AMERICA_WINDOW.contains(_at(27, 20, 0)) is False

    def test_midnight_crossing_window(self) -> None:
        """نافذة مخصصة 22:00-02:00: الذيل والرأس داخلها والحدان خارجان."""
        late = SessionWindow("LATE", 1320, 120, "عابرة لمنتصف الليل")
        assert late.contains(_at(27, 22, 0)) is True  # البداية ضمنًا
        assert late.contains(_at(27, 23, 59)) is True
        assert late.contains(_at(28, 0, 0)) is True
        assert late.contains(_at(28, 1, 59)) is True
        assert late.contains(_at(28, 2, 0)) is False  # النهاية حصرية
        assert late.contains(_at(27, 21, 59)) is False

    def test_full_day_and_empty_windows(self) -> None:
        """(0, 1440) يوم كامل دائمًا؛ (بداية == نهاية) نافذة فارغة موثقة."""
        full = SessionWindow("FULL", 0, 1440, "يوم كامل")
        for hour in (0, 6, 12, 18, 23):
            assert full.contains(_at(27, hour, 59)) is True
        empty = SessionWindow("EMPTY", 480, 480, "فارغة")
        assert empty.contains(_at(27, 8, 0)) is False

    def test_duration_minutes(self) -> None:
        """المدة الدائرية: عادية/عابرة/كاملة/فارغة."""
        assert ASIA_WINDOW.duration_minutes == 480
        assert SessionWindow("LATE", 1320, 120, "").duration_minutes == 240
        assert SessionWindow("FULL", 0, 1440, "").duration_minutes == 1440
        assert SessionWindow("EMPTY", 480, 480, "").duration_minutes == 0

    def test_out_of_range_minutes_rejected(self) -> None:
        """حدود الدقائق خارج [0,1439]/[0,1440] مرفوضة بقيمة واضحة."""
        with pytest.raises(ValueError):
            SessionWindow("BAD", 1440, 480, "")
        with pytest.raises(ValueError):
            SessionWindow("BAD", -1, 480, "")
        with pytest.raises(ValueError):
            SessionWindow("BAD", 0, 1441, "")
        with pytest.raises(ValueError):
            SessionWindow("BAD", 0, -5, "")

    def test_naive_datetime_rejected(self) -> None:
        """الساذج مرفوض في contains (عقد الوقت §7.1)."""
        with pytest.raises(ValueError):
            ASIA_WINDOW.contains(datetime(2026, 9, 27, 3, 0))

    def test_non_utc_tz_normalized(self) -> None:
        """03:00+00:00 داخل آسيا و06:00+03:00 (== 03:00 UTC) كذلك — تطبيع
        إلى UTC لا قراءة رقمية للساعة المحلية."""
        assert ASIA_WINDOW.contains(datetime(2026, 9, 27, 3, 0, tzinfo=UTC)) is True
        assert ASIA_WINDOW.contains(datetime(2026, 9, 27, 6, 0, tzinfo=_UTC_PLUS_3)) is True
        # 02:00+03:00 == 2026-09-26 23:00 UTC — خارج آسيا رغم أن رقم الساعة
        # المحلية (2) يقع داخل نطاق آسيا رقميًا (00:00-08:00)
        assert ASIA_WINDOW.contains(datetime(2026, 9, 27, 2, 0, tzinfo=_UTC_PLUS_3)) is False


# ───────── SessionWindowsConfig: النشاط وخطر الانتقال والصيانة ─────────


class TestSessionWindowsConfig:
    """النوافذ الفعالة عند لحظة + خطر الانتقال ضمن edge_minutes من الحواف."""

    def test_documented_defaults(self) -> None:
        """الافتراضي الموثق: آسيا 00:00-08:00، أوروبا 07:00-16:00، أمريكا
        13:30-20:00، لا صيانة، حافة انتقال 5 دقائق."""
        assert DEFAULT_SESSION_WINDOWS.windows == (ASIA_WINDOW, EUROPE_WINDOW, AMERICA_WINDOW)
        assert DEFAULT_SESSION_WINDOWS.maintenance == ()
        assert DEFAULT_SESSION_WINDOWS.edge_minutes == 5

    def test_active_at_asia_only(self) -> None:
        assert _names_at(_at(27, 3, 0)) == ["ASIA"]

    def test_active_at_europe_only_midday(self) -> None:
        assert _names_at(_at(27, 12, 0)) == ["EUROPE"]

    def test_overlap_at_0700_asia_and_europe(self) -> None:
        """07:00 داخل أوروبا وآسيا معًا = تقاطع (المطلوب حرفيًا)."""
        assert _names_at(_at(27, 7, 0)) == ["ASIA", "EUROPE"]

    def test_0800_outside_asia_inside_europe(self) -> None:
        assert _names_at(_at(27, 8, 0)) == ["EUROPE"]

    def test_europe_america_overlap_at_1400(self) -> None:
        assert _names_at(_at(27, 14, 0)) == ["EUROPE", "AMERICA"]

    def test_transition_risk_near_open(self) -> None:
        """داخل edge_minutes من الافتتاح: 00:04 خطر؛ 00:05 (عند الحافة) لا."""
        at_0004 = DEFAULT_SESSION_WINDOWS.active_at(_at(27, 0, 4))
        assert [(a.window.name, a.transition_risk) for a in at_0004] == [("ASIA", True)]
        at_0005 = DEFAULT_SESSION_WINDOWS.active_at(_at(27, 0, 5))
        assert [(a.window.name, a.transition_risk) for a in at_0005] == [("ASIA", False)]

    def test_transition_risk_near_close(self) -> None:
        """قرب الإقفال: 07:56-07:59 خطر (داخل 5 من 08:00)؛ 07:55 لا."""
        at_0756 = DEFAULT_SESSION_WINDOWS.active_at(_at(27, 7, 56))
        asia_0756 = next(a for a in at_0756 if a.window.name == "ASIA")
        assert asia_0756.transition_risk is True
        at_0755 = DEFAULT_SESSION_WINDOWS.active_at(_at(27, 7, 55))
        asia_0755 = next(a for a in at_0755 if a.window.name == "ASIA")
        assert asia_0755.transition_risk is False

    def test_no_risk_mid_window(self) -> None:
        """وسط النافذة لا خطر انتقال (آسيا 03:00، أوروبا 10:00)."""
        for moment in (_at(27, 3, 0), _at(27, 10, 0)):
            assert all(not a.transition_risk for a in DEFAULT_SESSION_WINDOWS.active_at(moment))

    def test_europe_open_edge_risky_at_0700(self) -> None:
        """افتتاح أوروبا نفسه خطر انتقال (صفر دقائق من حافته) وآسيا ليست كذلك."""
        actives = DEFAULT_SESSION_WINDOWS.active_at(_at(27, 7, 0))
        flags = {a.window.name: a.transition_risk for a in actives}
        assert flags == {"ASIA": False, "EUROPE": True}

    def test_edge_minutes_zero_disables_risk(self) -> None:
        config = SessionWindowsConfig(windows=(ASIA_WINDOW,), edge_minutes=0)
        actives = config.active_at(_at(27, 0, 0))
        assert [(a.window.name, a.transition_risk) for a in actives] == [("ASIA", False)]

    def test_wrap_window_transition_risk(self) -> None:
        """خطر الانتقال للنافذة العابرة 22:00-02:00: قرب الافتتاح والإقفال
        فقط — والقياس دائري يصمد للالتفاف (لا وسط النافذة)."""
        config = SessionWindowsConfig(windows=(SessionWindow("LATE", 1320, 120, ""),))
        expected = {
            0: False,  # 00:00 — داخل النافذة لكن بعيدة عن الحافتين
            60: False,  # 01:00 — وسطها
            116: True,  # 01:56 — داخل 5 من الإقفال (02:00)
            119: True,  # 01:59
            1322: True,  # 22:02 — داخل 5 من الافتتاح (22:00)
            1350: False,  # 22:30 — وسطها
        }
        for minute, risky in expected.items():
            actives = config.active_at(_at(28, minute // 60, minute % 60))
            assert len(actives) == 1
            assert actives[0].transition_risk is risky, f"minute={minute}"

    def test_maintenance_at(self) -> None:
        config = SessionWindowsConfig(windows=(), maintenance=(_MAINT_WINDOW,))
        assert config.maintenance_at(_at(27, 16, 2)) is True
        assert config.maintenance_at(_at(27, 16, 4)) is True
        assert config.maintenance_at(_at(27, 16, 5)) is False  # النهاية حصرية
        assert config.maintenance_at(_at(27, 15, 59)) is False

    def test_empty_config_never_active(self) -> None:
        config = SessionWindowsConfig()
        assert config.windows == () and config.maintenance == ()
        assert config.active_at(_at(27, 7, 0)) == ()

    def test_negative_edge_minutes_rejected(self) -> None:
        with pytest.raises(ValueError):
            SessionWindowsConfig(edge_minutes=-1)


# ───────── الدوال المساعدة النقية ─────────


class TestUtcHelpers:
    """utc_session_id وis_utc_day_boundary وtimeframe_minutes."""

    def test_utc_session_id_iso_date(self) -> None:
        assert utc_session_id(_at(27, 23, 59)) == "2026-09-27"
        assert utc_session_id(_at(28, 0, 0)) == "2026-09-28"

    def test_utc_session_id_tz_normalized(self) -> None:
        """02:00+03:00 == 23:00 UTC بالأمس — الهوية من UTC المطبع لا المحلية."""
        assert utc_session_id(datetime(2026, 9, 28, 2, 0, tzinfo=_UTC_PLUS_3)) == "2026-09-27"

    def test_utc_session_id_consistent_with_candle_contract(self) -> None:
        """نفس قاعدة منشئ الشموع (A-03): هوية الشمعة = تاريخ bar_time بتقويم UTC."""
        candle = _candle(_at(27, 5, 30), open_=100.0, close=101.0)
        assert candle.session_id == utc_session_id(candle.bar_time) == "2026-09-27"

    def test_utc_session_id_naive_rejected(self) -> None:
        with pytest.raises(ValueError):
            utc_session_id(datetime(2026, 9, 27, 3, 0))

    def test_is_utc_day_boundary(self) -> None:
        assert is_utc_day_boundary(_at(28, 0, 0)) is True
        assert is_utc_day_boundary(_at(27, 23, 59)) is False
        assert is_utc_day_boundary(datetime(2026, 9, 28, 0, 0, 1, tzinfo=UTC)) is False
        # ميكروثانية واحدة تكفي لنفي الحدّية
        assert is_utc_day_boundary(datetime(2026, 9, 28, 0, 0, 0, 1, tzinfo=UTC)) is False

    def test_is_utc_day_boundary_tz_normalized(self) -> None:
        """02:00+02:00 هو 00:00 UTC ⇒ حد يوم؛ 00:00+02:00 ليس كذلك."""
        assert is_utc_day_boundary(datetime(2026, 9, 28, 2, 0, tzinfo=_UTC_PLUS_2)) is True
        assert is_utc_day_boundary(datetime(2026, 9, 28, 0, 0, tzinfo=_UTC_PLUS_2)) is False

    def test_is_utc_day_boundary_naive_rejected(self) -> None:
        with pytest.raises(ValueError):
            is_utc_day_boundary(datetime(2026, 9, 28, 0, 0))

    def test_timeframe_minutes(self) -> None:
        assert timeframe_minutes("1m") == 1.0
        assert timeframe_minutes("5m") == 5.0
        assert timeframe_minutes("15m") == 15.0
        assert timeframe_minutes("1h") == 60.0
        assert timeframe_minutes("4h") == 240.0
        assert timeframe_minutes("1d") == 1440.0

    def test_timeframe_minutes_unknown_returns_zero(self) -> None:
        """الأطر غير الدقائقية (1t للصفقات) = 0.0 موثقة — لا عد دقائق ولا تعطيل."""
        assert timeframe_minutes("1t") == 0.0
        assert timeframe_minutes("m") == 0.0
        assert timeframe_minutes("") == 0.0
        assert timeframe_minutes("30") == 0.0


# ───────── المتتبع: أول شمعة وانتقال منتصف الليل وprior_* ─────────


class TestTrackerMidnightTransition:
    """جوهر بوابة 2.3: 23:59 ثم 00:00 ⇒ جلسة جديدة وprior_* من السابقة."""

    def test_first_candle_returns_none(self) -> None:
        """العقد الموثق: أول شمعة على الإطلاق تعالج (لا ترمى) وتعيد None."""
        tracker = SessionTracker()
        assert tracker.update(_c(27, 23, 59, 100.0, 105.0)) is None
        assert tracker.current_state is None
        assert tracker.stats.bars_processed == 1
        # عولجت فعلًا: الشمعة الثانية بنفس الجلسة ترى bars_seen = 2
        state = tracker.update(_c(27, 23, 59, 105.0, 106.0))
        assert state is not None and state.bars_seen == 2

    def test_midnight_rollover_new_session_with_prior(self) -> None:
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 105.0, high=110.0, low=95.0, volume=2.0))
        state = tracker.update(_c(28, 0, 0, 107.0, 107.5, high=108.0, low=106.0, volume=3.0))
        assert state is not None
        assert state.session_id == "2026-09-28"
        assert state.open_time == _at(28, 0, 0)
        assert state.close_time == _at(29, 0, 0)
        assert tracker.stats.sessions_closed == 1
        # prior_* من مجاميع الجلسة السابقة النهائية لحظة الانتقال
        assert state.opening.prior_session_high == 110.0
        assert state.opening.prior_session_low == 95.0
        assert state.opening.prior_session_close == 105.0
        # الفجوة: افتتاح أول شمعة مرصودة مقابل إغلاق الأمس
        assert state.opening.gap_vs_prior_close == 2.0
        assert state.opening.gap_direction == 1
        assert state.opening.prior_close_relationship is PriorCloseRelation.ABOVE
        # المجاميع بدأت من جديد
        assert state.current_high == 108.0
        assert state.current_low == 106.0
        assert state.session_volume == 3.0
        assert state.bars_seen == 1

    def test_gap_up_down_zero_against_prior_close(self) -> None:
        """فجوة صعودية/هبوطية/صفرية بقيم يدوية (إغلاق الأمس 100)."""
        for opened, expected_gap, expected_dir in (
            (105.0, 5.0, 1),
            (95.0, 5.0, -1),
            (100.0, 0.0, 0),
        ):
            tracker = SessionTracker()
            tracker.update(_c(27, 23, 59, 100.0, 100.0))
            state = tracker.update(_c(28, 0, 0, opened, opened))
            assert state is not None
            assert state.opening.gap_vs_prior_close == expected_gap
            assert state.opening.gap_direction == expected_dir

    def test_gap_dormant_without_prior_session(self) -> None:
        """أول جلسة للمتتبع: لا فجوة ولا prior_* — غياب صادق لا قيمة مفبركة."""
        tracker = SessionTracker()
        tracker.update(_c(27, 0, 0, 100.0, 101.0))
        state = tracker.update(_c(27, 0, 1, 101.0, 102.0))
        assert state is not None
        assert state.opening.gap_vs_prior_close is None
        assert state.opening.gap_direction == 0
        assert state.opening.prior_session_high is None
        assert state.opening.prior_session_low is None
        assert state.opening.prior_session_close is None
        assert state.opening.prior_close_relationship is PriorCloseRelation.UNCHANGED

    def test_day_gap_rolls_once(self) -> None:
        """ثقب بيانات ليوم كامل: يقفل الماضية مرة ويبدأ اليوم الأحدث."""
        tracker = SessionTracker()
        tracker.update(_c(27, 12, 0, 100.0, 100.0))
        state = tracker.update(_c(29, 12, 0, 100.0, 100.0))
        assert state is not None and state.session_id == "2026-09-29"
        assert tracker.stats.sessions_closed == 1  # إقفال واحد (اليوم 28 لم يوجد أبدًا)

    def test_current_state_matches_last_update(self) -> None:
        tracker = SessionTracker()
        tracker.update(_c(27, 0, 0, 100.0, 101.0))
        state = tracker.update(_c(27, 0, 1, 101.0, 102.0))
        assert state is not None
        assert tracker.current_state == state


# ───────── المدى الافتتاحي والرصيد الأولي ─────────


class TestOpeningRangeAndBalance:
    """المدى الافتتاحي يكتمل بعد N دقيقة ويجمد؛ والرصيد الأولي بنفس العقد."""

    def test_opening_range_completes_after_n_minutes(self) -> None:
        """OR افتراضي 30 دقيقة: قيمه من داخل النافذة فقط، ويكتمل عند أول
        شمعة عند 00:30 أو بعدها — وقيم شمعة الاكتمال نفسها لا تتسرب إليه."""
        tracker = SessionTracker()
        tracker.update(_c(28, 0, 0, 100.0, 104.0, high=104.0, low=100.0))
        tracker.update(_c(28, 0, 15, 104.0, 105.0, high=106.0, low=103.0))
        forming = tracker.update(_c(28, 0, 29, 105.0, 103.0, high=107.0, low=102.0))
        assert forming is not None
        assert forming.opening.opening_range_complete is False
        assert forming.opening.opening_range_high == 107.0
        assert forming.opening.opening_range_low == 100.0
        completed = tracker.update(_c(28, 0, 30, 103.0, 104.0, high=112.0, low=102.0))
        assert completed is not None
        assert completed.opening.opening_range_complete is True
        assert completed.opening.opening_range_high == 107.0  # ذروة 00:30 خارج النافذة
        assert completed.opening.opening_range_low == 100.0
        assert completed.opening.opening_drive is OpeningDrive.PENDING  # 104 داخل الحدين

    def test_opening_range_never_completes_without_in_window_bars(self) -> None:
        """لا شموع داخل النافذة أصلًا (بيانات تبدأ 02:00) ⇒ OR يبقى None/False."""
        tracker = SessionTracker()
        tracker.update(_c(28, 2, 0, 100.0, 101.0))
        state = tracker.update(_c(28, 2, 1, 101.0, 102.0))
        assert state is not None
        assert state.opening.opening_range_high is None
        assert state.opening.opening_range_low is None
        assert state.opening.opening_range_complete is False
        assert state.opening.opening_drive is OpeningDrive.PENDING

    def test_opening_range_frozen_after_completion(self) -> None:
        """بعد الاكتمال: شمعة متأخرة داخل النافذة المجمدة لا تمس المدى — تعد
        في late_bars وتمتصها المجاميع الرسمية فقط (روح §27: المكتمل جمود)."""
        tracker = SessionTracker()
        tracker.update(_c(28, 0, 0, 100.0, 104.0, high=105.0, low=100.0))
        tracker.update(_c(28, 0, 40, 104.0, 104.0))  # تعبر الحد ⇒ اكتمال وتجميد
        state = tracker.update(_c(28, 0, 10, 100.0, 110.0, high=120.0, low=90.0, volume=5.0))
        assert state is not None
        assert state.opening.opening_range_high == 105.0  # لم يمسها المتأخر
        assert state.opening.opening_range_low == 100.0
        assert state.current_high == 120.0  # المجاميع الرسمية امتصته
        assert state.current_low == 90.0
        assert state.bars_seen == 3
        assert state.session_volume == 25.0
        assert tracker.stats.late_bars == 1
        # نافذة الرصيد الأولي ما زالت مفتوحة (لا شمعة عند 01:00 بعد) فتمتصه
        assert state.opening.initial_balance_high == 120.0

    def test_initial_balance_window(self) -> None:
        """IB افتراضي 60 دقيقة: قيمه من [00:00, 01:00) فقط — ذروة/قاع شمعة
        01:00 نفسها خارج النافذة (حد حصري)."""
        tracker = SessionTracker()
        tracker.update(_c(28, 0, 0, 100.0, 104.0, high=105.0, low=100.0))
        tracker.update(_c(28, 0, 45, 104.0, 110.0, high=115.0, low=108.0))
        before = tracker.update(_c(28, 0, 59, 110.0, 111.0))
        assert before is not None
        assert before.opening.initial_balance_high == 115.0
        assert before.opening.initial_balance_low == 100.0
        after = tracker.update(_c(28, 1, 0, 111.0, 100.0, low=90.0))
        assert after is not None
        assert after.opening.initial_balance_high == 115.0  # قاع 90 خارج النافذة
        assert after.opening.initial_balance_low == 100.0
        assert after.current_low == 90.0  # لكنه في مجاميع الجلسة

    def test_custom_opening_range_minutes(self) -> None:
        """طول النافذة إعدادي من الخارج: OR=10 دقائق يكتمل عند 00:10."""
        tracker = SessionTracker(opening_range_minutes=10)
        tracker.update(_c(28, 0, 0, 100.0, 101.0, high=103.0, low=100.0))
        tracker.update(_c(28, 0, 5, 101.0, 102.0, high=102.0, low=101.0))
        state = tracker.update(_c(28, 0, 10, 102.0, 102.0))
        assert state is not None
        assert state.opening.opening_range_complete is True
        assert state.opening.opening_range_high == 103.0
        assert state.opening.opening_range_low == 100.0


# ───────── الدافعة الافتتاحية (قيم محسوبة يدويًا) ─────────


def _with_opening_range(tracker: SessionTracker) -> SessionTracker:
    """تجهيز مشترك: OR = [100, 107] (حجم 7) خلال [00:00, 00:30) من يوم 28.

    الشموع: 00:00 (h104/l100)، 00:15 (h106/l103)، 00:29 (h107/l102) —
    العتبة الافتراضية 0.5×7 = 3.5 ⇒ حد الصعود 110.5 وحد الهبوط 96.5.
    """
    tracker.update(_c(28, 0, 0, 100.0, 104.0, high=104.0, low=100.0))
    tracker.update(_c(28, 0, 15, 104.0, 105.0, high=106.0, low=103.0))
    tracker.update(_c(28, 0, 29, 105.0, 103.0, high=107.0, low=102.0))
    return tracker


class TestOpeningDrive:
    """تصنيف الدافعة على إغلاقات ما بعد المدى الافتتاحي — يدويًا بالكامل."""

    def test_drive_up_manual(self) -> None:
        """إغلاق 112 > 110.5 (سقف المدى + 0.5×حجمه) ⇒ UP."""
        tracker = _with_opening_range(SessionTracker())
        state = tracker.update(_c(28, 0, 30, 103.0, 112.0, high=112.5, low=102.5))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.UP

    def test_drive_down_manual(self) -> None:
        """إغلاق 95 < 96.5 (قاع المدى − 0.5×حجمه) ⇒ DOWN."""
        tracker = _with_opening_range(SessionTracker())
        state = tracker.update(_c(28, 0, 30, 103.0, 95.0, high=103.5, low=94.5))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.DOWN

    def test_drive_reversal_after_up_manual(self) -> None:
        """UP عند 00:30 ثم إغلاق 94 < 96.5 عند 00:35 ⇒ REVERSAL (ترقية لازقة)."""
        tracker = _with_opening_range(SessionTracker())
        tracker.update(_c(28, 0, 30, 103.0, 112.0))
        state = tracker.update(_c(28, 0, 35, 112.0, 94.0))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.REVERSAL

    def test_drive_reversal_after_down_manual(self) -> None:
        tracker = _with_opening_range(SessionTracker())
        tracker.update(_c(28, 0, 30, 103.0, 95.0))
        state = tracker.update(_c(28, 0, 35, 95.0, 111.0))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.REVERSAL

    def test_drive_pending_until_range_completes(self) -> None:
        """أولوية موثقة: مدى مكتمل > انتظار — لا تصنيف قبل اكتمال المدى."""
        tracker = SessionTracker()
        tracker.update(_c(28, 0, 0, 100.0, 104.0, high=104.0, low=100.0))
        state = tracker.update(_c(28, 0, 29, 104.0, 103.0, high=107.0, low=102.0))
        assert state is not None
        assert state.opening.opening_range_complete is False
        assert state.opening.opening_drive is OpeningDrive.PENDING

    def test_drive_close_inside_threshold_stays_pending(self) -> None:
        """إغلاق بين الحدين (104) بعد الاكتمال ⇒ PENDING (لا تصنيف بلا عتبة)."""
        tracker = _with_opening_range(SessionTracker())
        state = tracker.update(_c(28, 0, 30, 103.0, 104.0))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.PENDING

    def test_drive_flat_range_strict_break(self) -> None:
        """مدى مسطح (حجم 0 ⇒ عتبة 0): كسر صارم فوق السقف يصنف UP والمساواة لا."""
        tracker = SessionTracker()
        tracker.update(_c(28, 0, 0, 100.0, 100.0))
        tracker.update(_c(28, 0, 29, 100.0, 100.0))
        equal = tracker.update(_c(28, 0, 30, 100.0, 100.0))
        assert equal is not None
        assert equal.opening.opening_range_high == 100.0
        assert equal.opening.opening_drive is OpeningDrive.PENDING  # المساواة ليست كسرًا
        broken = tracker.update(_c(28, 0, 31, 100.0, 100.5))
        assert broken is not None
        assert broken.opening.opening_drive is OpeningDrive.UP

    def test_drive_atr_value_mode(self) -> None:
        """وضع الأتر (قيمة لكل استدعاء): العتبة 0.5×20=10 ⇒ الحد 117 —
        إغلاق 112 لا يكفي ثم 118 يكفي (الأتر يقدم على النسبة من المدى)."""
        tracker = _with_opening_range(SessionTracker())
        first = tracker.update(_c(28, 0, 30, 103.0, 112.0), atr=20.0)
        assert first is not None
        assert first.opening.opening_drive is OpeningDrive.PENDING
        second = tracker.update(_c(28, 0, 31, 112.0, 118.0), atr=20.0)
        assert second is not None
        assert second.opening.opening_drive is OpeningDrive.UP

    def test_drive_atr_provider_used_when_no_per_call_value(self) -> None:
        """المزود يعمل حين تغيب قيمة الاستدعاء: أتر 4 ⇒ عتبة 2 ⇒ الحد 109."""
        tracker = _with_opening_range(SessionTracker(atr_provider=lambda: 4.0))
        state = tracker.update(_c(28, 0, 30, 103.0, 112.0))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.UP

    def test_per_call_atr_overrides_provider(self) -> None:
        """قيمة الاستدعاء تقدم على المزود: مزود 100 (حد 157) وقيمة 4 (حد 109)."""
        tracker = _with_opening_range(SessionTracker(atr_provider=lambda: 100.0))
        state = tracker.update(_c(28, 0, 30, 103.0, 112.0), atr=4.0)
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.UP

    def test_provider_none_falls_back_to_raw_mode(self) -> None:
        """مزود يعيد None ⇒ الوضع الخام الموثق (النسبة من المدى نفسه): حد 110.5."""
        tracker = _with_opening_range(SessionTracker(atr_provider=lambda: None))
        state = tracker.update(_c(28, 0, 30, 103.0, 112.0))
        assert state is not None
        assert state.opening.opening_drive is OpeningDrive.UP


# ───────── علاقة الإغلاق السابق ─────────


class TestPriorCloseRelationship:
    """ABOVE/BELOW/UNCHANGED عند عتبة نسبية صفرية موثقة (مساواة تامة)."""

    def test_relationship_above_below_unchanged(self) -> None:
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 100.0))
        above = tracker.update(_c(28, 0, 0, 101.0, 101.0))
        assert above is not None
        assert above.opening.prior_close_relationship is PriorCloseRelation.ABOVE
        below = tracker.update(_c(28, 0, 1, 101.0, 99.0))
        assert below is not None
        assert below.opening.prior_close_relationship is PriorCloseRelation.BELOW
        unchanged = tracker.update(_c(28, 0, 2, 99.0, 100.0))
        assert unchanged is not None
        assert unchanged.opening.prior_close_relationship is PriorCloseRelation.UNCHANGED

    def test_relationship_from_latest_observed_close(self) -> None:
        """العلاقة من آخر إغلاق مرصود لا من الشمعة الواصلة: شمعة داخل الجلسة
        (05:30) تصل بعد 06:00 فلا تغير آخر إغلاق (99) والعلاقة تظن BELOW."""
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 100.0))
        tracker.update(_c(28, 6, 0, 100.0, 99.0))  # آخر إغلاق مرصود = 99
        state = tracker.update(_c(28, 5, 30, 99.0, 101.0))  # داخل الجلسة، أبكر bar_time
        assert state is not None
        assert state.opening.prior_close_relationship is PriorCloseRelation.BELOW


# ───────── الترتيب: شموع متأخرة وجلسات سابقة ─────────


class TestArrivalOrdering:
    """عقد المتأخر الموثق: يحدّث جلسته لا الحالية — بلا إسقاط صامت ولا
    تعديل رجعي لسياق prior_* المثبت لحظة الانتقال."""

    def test_late_candle_updates_previous_session_aggregates(self) -> None:
        tracker = SessionTracker()
        tracker.update(_c(27, 0, 0, 100.0, 100.0, volume=1.0))
        tracker.update(_c(27, 23, 59, 100.0, 105.0, high=110.0, low=90.0, volume=2.0))
        current = tracker.update(_c(28, 0, 0, 105.0, 105.5, high=106.0, low=104.0, volume=3.0))
        assert current is not None and current.session_id == "2026-09-28"
        # متأخرة لجلسة 27 بعد بدء جلسة 28 — تحدّث حالة جلستها لا الحالية
        late = tracker.update(_c(27, 12, 0, 100.0, 110.0, high=120.0, low=85.0, volume=7.0))
        assert late is not None
        assert late.session_id == "2026-09-27"
        assert late.current_high == 120.0  # المجاميع امتصتها
        assert late.current_low == 85.0
        assert late.session_volume == 10.0  # 1 + 2 + 7
        assert late.bars_seen == 3
        # بنيتها المجمدة لم تُمس: المدى الافتتاحي اكتمل أثناء حياتها ([100,100] من
        # شمعة 00:00 وحدها) وقمة/قاع المتأخرة (120/85) لم يتسربا إليه
        assert late.opening.opening_range_complete is True
        assert late.opening.opening_range_high == 100.0
        assert late.opening.opening_range_low == 100.0
        assert tracker.stats.late_bars == 1
        # الحالية لم تتأثر: لقطة الجارية آخر ما أعيد لها
        assert tracker.current_state is not None
        assert tracker.current_state.session_id == "2026-09-28"
        assert tracker.current_state.current_high == 106.0

    def test_prior_context_fixed_no_retroactive_change(self) -> None:
        """سياق prior_* ثبت لحظة الانتقال: قمة 120 من المتأخرة لا تعدل
        prior_session_high لجلسة 28 (لا رسم عكسي للقطة سابقة)."""
        tracker = SessionTracker()
        tracker.update(_c(27, 0, 0, 100.0, 100.0))
        tracker.update(_c(27, 23, 59, 100.0, 105.0, high=110.0, low=90.0))
        tracker.update(_c(28, 0, 0, 105.0, 105.0))
        tracker.update(_c(27, 12, 0, 100.0, 110.0, high=120.0, low=85.0))  # متأخرة
        after = tracker.update(_c(28, 0, 1, 105.0, 105.0))
        assert after is not None
        assert after.opening.prior_session_high == 110.0  # ليس 120
        assert after.opening.prior_session_close == 105.0

    def test_older_than_retained_previous_returns_none_counted(self) -> None:
        """أقدم من السابقة المحتفظ بها: لا حالة لها — تعد مرئيًا وتعيد None."""
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 100.0))
        tracker.update(_c(28, 0, 0, 100.0, 100.0))
        tracker.update(_c(29, 0, 0, 100.0, 100.0))  # السابقة المحتفظ بها صارت 28
        late = tracker.update(_c(27, 12, 0, 100.0, 100.0))
        assert late is None
        assert tracker.stats.late_bars == 1
        # السابقة 28 ما زالت محتفظًا بها: متأخرتها تعمل وفق العقد نفسه
        retained = tracker.update(_c(28, 12, 0, 100.0, 100.0, high=130.0))
        assert retained is not None
        assert retained.session_id == "2026-09-28"
        assert retained.current_high == 130.0

    def test_intra_session_out_of_order_absorbed(self) -> None:
        """معكوس جزئي داخل الجلسة: 05:00 ثم 06:00 ثم 05:30 — المجاميع
        مستقلة عن الترتيب (high/low/volume/bars_seen) ولا نوافذ مجمّدة مسّت."""
        tracker = SessionTracker()
        tracker.update(_c(28, 5, 0, 100.0, 100.0, high=110.0, volume=1.0))
        tracker.update(_c(28, 6, 0, 100.0, 100.0, high=105.0, volume=2.0))
        state = tracker.update(_c(28, 5, 30, 100.0, 100.0, high=115.0, volume=4.0))
        assert state is not None
        assert state.current_high == 115.0
        assert state.current_low == 100.0
        assert state.session_volume == 7.0
        assert state.bars_seen == 3
        assert tracker.stats.late_bars == 0

    def test_gap_anchor_corrects_with_earlier_arrival(self) -> None:
        """مرساة الفجوة = افتتاح أقدم bar_time مرصود: وصول شمعة أبكر لاحقًا
        يصحح المرساة في اللقطات التالية (السابقة مجمدة لا تُعاد رسمها)."""
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 100.0))
        tracker.update(_c(28, 2, 0, 105.0, 105.0))  # أول مرصود: مرساة 105
        corrected = tracker.update(_c(28, 0, 10, 110.0, 110.0))  # أبكر شمعة وصلت لاحقًا
        assert corrected is not None
        assert corrected.opening.gap_vs_prior_close == 10.0  # |110 − 100|
        assert corrected.opening.gap_direction == 1


# ───────── الصيانة والإحصاءات ─────────


class TestMaintenanceAndStats:
    """علم in_maintenance وعدادات maintenance_minutes وإحصاءات المتتبع."""

    def test_in_maintenance_flag_and_counters(self) -> None:
        config = SessionWindowsConfig(windows=(), maintenance=(_MAINT_WINDOW,))
        tracker = SessionTracker(config)
        tracker.update(_c(27, 15, 59, 100.0, 100.0))
        inside = tracker.update(_c(27, 16, 2, 100.0, 100.0))
        assert inside is not None
        assert inside.in_maintenance is True
        assert [a.window.name for a in inside.active_windows] == ["MAINTENANCE"]
        assert tracker.stats.bars_in_maintenance == 1
        assert tracker.stats.maintenance_minutes == 1.0

    def test_maintenance_minutes_by_timeframe(self) -> None:
        """5m داخل الصيانة = 5 دقائق؛ وإطار غير دقائقي (1t) = 0.0 بعدّ الشمعة."""
        config = SessionWindowsConfig(windows=(), maintenance=(_MAINT_WINDOW,))
        tracker = SessionTracker(config)
        tracker.update(_c(27, 16, 3, 100.0, 100.0, timeframe="5m"))
        tracker.update(_c(27, 16, 1, 100.0, 100.0, timeframe="1t"))
        stats = tracker.stats
        assert stats.bars_in_maintenance == 2
        assert stats.maintenance_minutes == 5.0

    def test_outside_maintenance_not_counted(self) -> None:
        config = SessionWindowsConfig(windows=(), maintenance=(_MAINT_WINDOW,))
        tracker = SessionTracker(config)
        tracker.update(_c(27, 15, 0, 100.0, 100.0))  # أول شمعة: None (العقد)
        state = tracker.update(_c(27, 15, 1, 100.0, 100.0))
        assert state is not None and state.in_maintenance is False
        assert tracker.stats.bars_in_maintenance == 0

    def test_stats_hand_counted_scenario(self) -> None:
        """سيناريو يدوي كامل: 3 جلسات، 6 شموع، متأخرتان (واحدة للسابقة
        المحتفظ بها وواحدة أقدم منها)، شمعتان في صيانة بمجموع 6 دقائق."""
        config = SessionWindowsConfig(windows=(), maintenance=(_MAINT_WINDOW,))
        tracker = SessionTracker(config)
        tracker.update(_c(27, 23, 59, 100.0, 100.0))  # 1
        tracker.update(_c(28, 0, 0, 100.0, 100.0))  # 2 — انتقال 1
        tracker.update(_c(28, 16, 4, 100.0, 100.0, timeframe="5m"))  # 3 — صيانة 5m
        tracker.update(_c(29, 0, 0, 100.0, 100.0))  # 4 — انتقال 2
        tracker.update(_c(28, 16, 1, 100.0, 100.0, timeframe="1m"))  # 5 — متأخرة (وصيانة 1m)
        tracker.update(_c(27, 12, 0, 100.0, 100.0))  # 6 — أقدم من المحتفظ بها
        stats = tracker.stats
        assert stats.sessions_closed == 2
        assert stats.bars_processed == 6
        assert stats.late_bars == 2
        assert stats.bars_in_maintenance == 2
        assert stats.maintenance_minutes == 6.0

    def test_edge_minutes_inheritance_and_override(self) -> None:
        """edge_minutes=None يرث حافة الإعداد (5)؛ والقيمة الصريحة تتجاوزها."""
        config = SessionWindowsConfig(windows=(ASIA_WINDOW,), edge_minutes=5)
        inherited = SessionTracker(config)
        assert inherited.config.edge_minutes == 5
        overridden = SessionTracker(config, edge_minutes=2)
        assert overridden.config.edge_minutes == 2
        # بالحافة 2: 00:01 خطر و00:02 لا
        at_0001 = overridden.config.active_at(_at(27, 0, 1))
        at_0002 = overridden.config.active_at(_at(27, 0, 2))
        assert at_0001[0].transition_risk is True
        assert at_0002[0].transition_risk is False


# ───────── التحقق من المدخلات ─────────


class TestValidation:
    """المعاملات الإعدادية وقيم atr — رفض قبل أي أثر جانبي."""

    def test_invalid_constructor_params_rejected(self) -> None:
        for kwargs in (
            {"opening_range_minutes": 0},
            {"initial_balance_minutes": 0},
            {"drive_threshold_ratio": -0.5},
            {"drive_threshold_ratio": float("nan")},
        ):
            with pytest.raises(ValueError):
                SessionTracker(**kwargs)

    def test_invalid_atr_rejected_without_side_effects(self) -> None:
        """atr سالبة/غير منتهية ترفض قبل أي معالجة — العدادات لم تمس."""
        tracker = SessionTracker()
        candle = _c(27, 0, 0, 100.0, 101.0)
        for bad in (-1.0, float("inf"), float("nan")):
            with pytest.raises(ValueError):
                tracker.update(candle, atr=bad)
        assert tracker.stats.bars_processed == 0

    def test_invalid_atr_from_provider_rejected(self) -> None:
        tracker = SessionTracker(atr_provider=lambda: -5.0)
        with pytest.raises(ValueError):
            tracker.update(_c(27, 0, 0, 100.0, 101.0))


# ───────── DST لا وجود له ─────────


class TestDSTNonexistence:
    """كل شيء UTC صرف: الصيف والشتاء بنفس دقائق UTC معاملة واحدة،
    والمناطق الأخرى تُطبَّن ولا تُقرأ بساعة الحائط."""

    def test_summer_winter_same_utc_minutes_identical(self) -> None:
        summer = datetime(2026, 7, 15, 7, 0, tzinfo=UTC)
        winter = datetime(2026, 1, 15, 7, 0, tzinfo=UTC)
        assert DEFAULT_SESSION_WINDOWS.active_at(summer) == DEFAULT_SESSION_WINDOWS.active_at(
            winter
        )
        assert _names_at(summer) == _names_at(winter) == ["ASIA", "EUROPE"]

    def test_local_wall_clock_never_consulted(self) -> None:
        """09:00 بتوقيت +02:00 صيفًا و08:00 بتوقيت +01:00 شتاءً كلاهما 07:00
        UTC ⇒ نفس النوافذ؛ وساعة الحائط وحدها لا تعني شيئًا."""
        summer_local = datetime(2026, 7, 15, 9, 0, tzinfo=_UTC_PLUS_2)
        winter_local = datetime(2026, 1, 15, 8, 0, tzinfo=_UTC_PLUS_1)
        assert _names_at(summer_local) == ["ASIA", "EUROPE"]
        assert _names_at(winter_local) == ["ASIA", "EUROPE"]
        # 09:00 بتوقيت +01:00 شتاءً == 08:00 UTC: خارج آسيا رغم أن رقم الساعة
        # المحلية يقع ضمن نطاق آسيا رقميًا (00:00-08:00)
        late_local = datetime(2026, 1, 15, 9, 0, tzinfo=_UTC_PLUS_1)
        assert _names_at(late_local) == ["EUROPE"]

    def test_tracker_rolls_on_utc_midnight_only(self) -> None:
        """الانتقال عند منتصف الليل UTC الفعلي لا عند أي منتصف محلي."""
        tracker = SessionTracker()
        tracker.update(_c(27, 23, 59, 100.0, 100.0))
        # 01:00 بتوقيت +01:00 == 00:00 UTC ⇒ انتقال
        rollover = tracker.update(
            _candle(datetime(2026, 9, 28, 1, 0, tzinfo=_UTC_PLUS_1), open_=100.0, close=100.0)
        )
        assert rollover is not None
        assert rollover.session_id == "2026-09-28"


# ───────── الخصائص (hypothesis — بأسلوب derandomize) ─────────


def _prop_candle(spec: tuple[int, float, float, float, float, float]) -> Candle:
    """بناء شمعة من مواصفة عشوائية: (دقائق منذ البداية، open، close،
    فتيل علوي، فتيل سفلي، حجم) — المدى صالح دائمًا والأسعار موجبة."""
    minutes, opened, closed, wick_up, wick_dn, volume = spec
    return _candle(
        _DAY0 + timedelta(minutes=minutes),
        open_=opened,
        close=closed,
        high=max(opened, closed) + wick_up,
        low=min(opened, closed) - wick_dn,
        volume=volume,
    )


_SPECS = st.lists(
    st.tuples(
        # دقيقتان من اليومين (0..2879) تغطيان انتقال منتصف الليل والمتأخرات
        st.integers(min_value=0, max_value=2879),
        st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    ),
    min_size=1,
    max_size=24,
)


class TestPositionalProperties:
    """اللا-نظرة-المستقبلية والحتمية وعضوية النوافذ — خصائص مجردة."""

    @given(specs=_SPECS, data=st.data())
    @hyp_settings(max_examples=40, deadline=None, derandomize=True)
    def test_prefix_state_independent_of_future_candles(
        self,
        specs: list[tuple[int, float, float, float, float, float]],
        data: st.DataObject,
    ) -> None:
        """خاصية اللا-نظرة-المستقبلية: حالة الموضع k من قائمة مقطوعة أصلًا
        عند k تطابق حالة الموضع k نفسه من القائمة الكاملة — استنساخ المتتبع
        متعذر (حالة موضعية) فيقاس بالتشغيل على مسارين منفصلين."""
        candles = [_prop_candle(spec) for spec in specs]
        k = data.draw(st.integers(min_value=0, max_value=len(candles) - 1))

        full = SessionTracker()
        full_states: list[SessionState | None] = []
        for candle in candles:
            full_states.append(full.update(candle))

        prefix = SessionTracker()
        prefix_states: list[SessionState | None] = []
        for candle in candles[: k + 1]:
            prefix_states.append(prefix.update(candle))

        assert full_states[k] == prefix_states[k]

    @given(specs=_SPECS)
    @hyp_settings(max_examples=30, deadline=None, derandomize=True)
    def test_determinism_same_inputs_same_outputs(
        self, specs: list[tuple[int, float, float, float, float, float]]
    ) -> None:
        """الحتمية: مساران مستقلان بنفس المدخلات ⇒ نفس تتابع اللقطات كاملًا."""
        candles = [_prop_candle(spec) for spec in specs]

        first = SessionTracker()
        second = SessionTracker()
        first_states = [first.update(candle) for candle in candles]
        second_states = [second.update(candle) for candle in candles]
        assert first_states == second_states
        assert first.stats == second.stats

    @given(
        start=st.integers(min_value=0, max_value=1439),
        end=st.integers(min_value=0, max_value=1440),
        minute=st.integers(min_value=0, max_value=1439),
        day_offset=st.integers(min_value=0, max_value=365),
    )
    @hyp_settings(max_examples=60, deadline=None, derandomize=True)
    def test_contains_matches_circular_walk_oracle(
        self, start: int, end: int, minute: int, day_offset: int
    ) -> None:
        """oracle مستقل: مشية دائرية من البداية حتى النهاية تبني مجموعة
        الدقائق المغطاة — العضوية الحرفية [بداية، نهاية) مع الالتفاف."""
        window = SessionWindow("PROP", start, end, "")
        covered: set[int] = set()
        cursor = start
        while cursor != end and len(covered) < _MINUTES_PER_DAY:
            covered.add(cursor)
            cursor = (cursor + 1) % _MINUTES_PER_DAY
        moment = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day_offset, minutes=minute)
        assert window.contains(moment) is (minute in covered)
