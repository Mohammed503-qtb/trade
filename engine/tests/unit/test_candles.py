"""اختبارات منشئ الشموع الحدثي (المهمة 1.4) — §8.1 و§27 و§33.1 و§38.1.

التغطية المطلوبة:
- golden مضمّن: قائمة أحداث معلومة ⇒ Candle معلوم كامل الحقول محسوب يدويًا
  (قيم وسيطة للمتطورة ثم القيم النهائية عند عبور حد الدلو).
- حدود الأطر الستة عند عبور الدلو (آخر ميكروثانية قبل الحد vs الحد نفسه).
- المتطورة لا تفوّض (§27): is_closed=False في كل إصدار وسيط، True فقط عند القفل.
- الأحداث المتأخرة بعد القفل: تُحصى، لا تمس المقفلة، ولا تنشئ شمعة فائتة.
- الحواف الموثقة: شمعة مسطحة (high==low) ⇒ body_fraction=0.0 وclv=0.5،
  وtrue_range بإغلاق سابق (تفوق قمة/قاع على المدى عبر الفجوات).
- سلّل الجودة: أسوأ مساهمة تفوز — QUARANTINED واحدة تجتاح الشمعة كلها.
- property-based (hypothesis، بذرة مثبتة): تسلسل عشوائي داخل دلو واحد
  ⇒ open=الأول، close=آخر الوصول، high=max، low=min، volume=sum — لأي إطار.
- الحتمية (نفس المدخلات ⇒ نفس المخرجات) واللا-نظرة-المستقبلية (§26.3):
  إدراج t+1 بعد بناء t لا يغيّر مخرجات t.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from ingestion.candles import (
    QUALITY_SEVERITY_LADDER,
    SUPPORTED_TIMEFRAMES,
    CandleBuilder,
    bucket_floor,
)
from schemas import Candle, DataQuality, TradeEvent

# ───────── ثوابت وأدوات ─────────

MICROSECOND = timedelta(microseconds=1)

# لحظات مرجعية — كلها UTC (عقد §7.1)
T_MIDNIGHT = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
T_02_00 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)

# عدسة تنبؤ مستقلة عن التنفيذ: طول كل إطار كما يجب أن يكون (لا تستورَد
# من الوحدة تحت الاختبار — oracle مستقل للخصائص والحدود).
TIMEFRAME_DELTAS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def _trade(
    when: datetime,
    price: float,
    quantity: float,
    *,
    venue: str = "BINANCE_USDM",
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
) -> TradeEvent:
    """حدث صفقة اصطناعي بعقد §7.1 — زمن الوصول = زمن الحدث (لا يقرأه البنّاء)."""
    return TradeEvent(
        event_time_utc=when,
        receive_time_utc=when,
        source_timeframe=timeframe,
        venue=venue,
        symbol=symbol,
        feed_id="binance.aggTrades",
        sequence_id=None,
        source_latency_ms=None,
        price=price,
        quantity=quantity,
        buyer_is_maker=None,
    )


def _dump(candle: Candle | None) -> str:
    """تمثيل حتمي قابل للمقارنة بايت-ببايت (None ⇒ علامة مميزة)."""
    return "<none>" if candle is None else candle.model_dump_json()


# ───────── golden: قائمة أحداث معلومة ⇒ شمعة معلومة كاملة الحقول ─────────


class TestGoldenCandle:
    """السيناريو الذهبي: 4 صفقات في دلو 02:00 ثم صفقة تعبر الحد إلى 02:01.

    كل القيم المتوقعة محسوبة يدويًا ( literals عشرية دقيقة) — أي انحراف في
    أي حقل من حقول §8.1 الأربعة عشر يكسر الاختبار حرفيًا.
    """

    def test_golden_full_field_candle(self) -> None:
        builder = CandleBuilder()

        # أول حدث على الإطلاق: تبدأ المتطورة ولا يُعاد شيء (لا سابقة تُقفل)
        first = builder.add_trade(_trade(T_02_00 + timedelta(seconds=10), 100.0, 2.0))
        assert first is None

        # ثاني حدث: نسخة متطورة بقيم وسيطة صحيحة — is_closed=False (لا تفوّض §27)
        evolving_2 = builder.add_trade(_trade(T_02_00 + timedelta(seconds=20), 110.0, 3.0))
        assert evolving_2 is not None and evolving_2.is_closed is False
        assert evolving_2.instrument_id == "BINANCE_USDM:BTCUSDT"
        assert evolving_2.timeframe == "1m"
        assert evolving_2.bar_time == T_02_00
        assert evolving_2.open == 100.0
        assert evolving_2.high == 110.0
        assert evolving_2.low == 100.0
        assert evolving_2.close == 110.0
        assert evolving_2.volume == 5.0
        assert evolving_2.range == 10.0
        assert evolving_2.body_size == 10.0
        assert evolving_2.upper_wick == 0.0
        assert evolving_2.lower_wick == 0.0
        assert evolving_2.body_fraction == 1.0
        assert evolving_2.close_location_value == 1.0
        assert evolving_2.true_range == 10.0  # أول شمعة في المجرى: لا إغلاق سابق
        assert evolving_2.realized_volatility == 0.09531017980432493  # |ln(110/100)|

        # ثالث حدث: هبوط تحت الافتتاح — الفتيل العلوي يتضخم والسفلي يعدم
        evolving_3 = builder.add_trade(_trade(T_02_00 + timedelta(seconds=30), 95.0, 1.5))
        assert evolving_3 is not None and evolving_3.is_closed is False
        assert evolving_3.high == 110.0
        assert evolving_3.low == 95.0
        assert evolving_3.close == 95.0
        assert evolving_3.volume == 6.5
        assert evolving_3.range == 15.0
        assert evolving_3.body_size == 5.0
        assert evolving_3.upper_wick == 10.0
        assert evolving_3.lower_wick == 0.0
        assert evolving_3.body_fraction == 0.3333333333333333  # 5/15
        assert evolving_3.close_location_value == 0.0  # الإغلاق على القاع
        assert evolving_3.true_range == 15.0
        assert evolving_3.realized_volatility == 0.05129329438755058  # |ln(95/100)|

        # رابع حدث: قيم المتطورة النهائية قبل العبور — ما زالت is_closed=False
        evolving_4 = builder.add_trade(_trade(T_02_00 + timedelta(seconds=45), 105.0, 4.0))
        assert evolving_4 is not None and evolving_4.is_closed is False
        assert evolving_4.close == 105.0
        assert evolving_4.volume == 10.5

        # العبور إلى دلو 02:01: السابقة تُقفل وتُعاد — الشمعة الذهبية الكاملة
        closed = builder.add_trade(_trade(T_02_00 + timedelta(minutes=1, seconds=5), 108.0, 2.5))
        assert closed is not None
        assert closed.is_closed is True
        assert closed.instrument_id == "BINANCE_USDM:BTCUSDT"
        assert closed.timeframe == "1m"
        assert closed.bar_time == T_02_00
        assert closed.session_id == "2026-09-27"
        assert closed.quality is DataQuality.HEALTHY
        assert closed.open == 100.0
        assert closed.high == 110.0
        assert closed.low == 95.0
        assert closed.close == 105.0
        assert closed.volume == 10.5
        # ── القيم المشتقة §8.1 — محسوبة يدويًا ──
        assert closed.range == 15.0
        assert closed.body_size == 5.0
        assert closed.upper_wick == 5.0
        assert closed.lower_wick == 5.0
        assert closed.body_fraction == 0.3333333333333333  # 5/15
        assert closed.close_location_value == 0.6666666666666666  # 10/15
        assert closed.true_range == 15.0  # أول شمعة في المجرى: high - low
        assert closed.realized_volatility == 0.04879016416943205  # |ln(105/100)|

        # الإحصاءات بعد القفل الذهبي
        assert builder.n_closed == 1
        assert builder.n_evolved_updates == 3
        assert builder.late_events == 0
        assert builder.first_bar_time == T_02_00
        assert builder.last_bar_time == T_02_00 + timedelta(minutes=1)

        # الإقفال الصريح للمتطورة 02:01 (نهاية البث): مسطحة + إغلاق سابق
        final = builder.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert final is not None
        assert final.is_closed is True
        assert final.bar_time == T_02_00 + timedelta(minutes=1)
        assert final.open == 108.0 and final.high == 108.0
        assert final.low == 108.0 and final.close == 108.0
        assert final.volume == 2.5
        assert final.range == 0.0
        assert final.body_size == 0.0
        assert final.upper_wick == 0.0
        assert final.lower_wick == 0.0
        # شمعة مسطحة (high == low): اتفاقية الحافة الموثقة
        assert final.body_fraction == 0.0
        assert final.close_location_value == 0.5
        # true_range بإغلاق سابق: |108 - 105| = 3.0 يتفوق على المدى الصفري
        assert final.true_range == 3.0
        assert final.realized_volatility == 0.0
        assert builder.n_closed == 2
        assert builder.n_evolved_updates == 3
        assert builder.late_events == 0


class TestFlatCandle:
    """الشموع المسطحة (high == low): اتفاقيات الحافة §8.1 الموثقة."""

    def test_flat_candle_with_multiple_events(self) -> None:
        builder = CandleBuilder()
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=5), 50.0, 1.0))
        flat = builder.add_trade(_trade(T_02_00 + timedelta(seconds=6), 50.0, 2.0))
        assert flat is not None and flat.is_closed is False
        assert flat.high == 50.0 and flat.low == 50.0
        assert flat.volume == 3.0
        assert flat.range == 0.0
        assert flat.body_size == 0.0
        assert flat.upper_wick == 0.0
        assert flat.lower_wick == 0.0
        assert flat.body_fraction == 0.0
        assert flat.close_location_value == 0.5
        assert flat.true_range == 0.0  # أول شمعة مسطحة بلا إغلاق سابق
        assert flat.realized_volatility == 0.0


class TestTrueRangeWithPreviousClose:
    """true_range يأخذ إغلاق الشمعة الماقفة في المجرى — الفجوات لا تُتجاوز."""

    def test_gap_up_and_down_dominated_by_previous_close(self) -> None:
        builder = CandleBuilder()
        # دلو 02:00: إغلاق 101.0 (النسخة المتطورة تؤكد الإغلاق قبل العبور)
        assert builder.add_trade(_trade(T_02_00 + timedelta(seconds=10), 99.0, 1.0)) is None
        bar1 = builder.add_trade(_trade(T_02_00 + timedelta(seconds=20), 101.0, 1.0))
        assert bar1 is not None and bar1.close == 101.0
        # عبور بفجوة صاعدة إلى دلو 02:05: يُعاد إقفال السابقة — أول شمعة بلا إغلاق سابق
        closed1 = builder.add_trade(_trade(T_02_00 + timedelta(minutes=5, seconds=1), 101.4, 1.0))
        assert closed1 is not None and closed1.is_closed is True
        assert closed1.true_range == pytest.approx(2.0)  # 101.0 - 99.0
        # الدلو الجديد 02:05: مداه نفسه أصغر من مسافة قمته عن إغلاق الأمس
        b2 = builder.add_trade(_trade(T_02_00 + timedelta(minutes=5, seconds=2), 101.2, 1.0))
        assert b2 is not None and b2.is_closed is False
        assert b2.range == pytest.approx(0.2)
        assert b2.true_range == pytest.approx(0.4)  # max(0.2, |101.4-101.0|, |101.2-101.0|)
        closed2 = builder.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert closed2 is not None and closed2.true_range == pytest.approx(0.4)
        # فجوة هابطة عن إغلاق 101.2: مسافة القاع عن الأمس تهيمن
        assert (
            builder.add_trade(_trade(T_02_00 + timedelta(minutes=10, seconds=1), 99.0, 1.0)) is None
        )  # بداية دلو جديد لا تُعاد
        b3 = builder.add_trade(_trade(T_02_00 + timedelta(minutes=10, seconds=2), 98.5, 1.0))
        assert b3 is not None
        assert b3.true_range == pytest.approx(2.7)  # max(0.5, |99-101.2|, |98.5-101.2|)


# ───────── bucket_floor: حدود الأطر والرفض والعالمية UTC ─────────


class TestBucketFloor:
    """حدود الأطر الستة: عبور الحد يفتتح دلوًا جديدًا — وكل شيء UTC.

    زوج 00:00:59.999…/00:01:00.000 الوارد في تعريف المهمة يفصل حرفيًا بين
    دلوين لإطار 1m (أصغر الأطر وأدقّها)؛ ولما كانت حدود بقية الأطر مضاعفات
    مضمنة للدقيقة، فالفصل عندها يُختبر عند حدودها الخاصة (لكل إطار حدّه) —
    هذا معنى «لكل الأطر».
    """

    @pytest.mark.parametrize("timeframe", list(TIMEFRAME_DELTAS))
    def test_boundary_crossing_starts_new_bucket(self, timeframe: str) -> None:
        delta = TIMEFRAME_DELTAS[timeframe]
        # منتصف الليل حدّ محاذى لكل الأطر الستة ⇒ الحد التالي محاذى كذلك
        boundary = T_MIDNIGHT + delta
        before = boundary - MICROSECOND  # آخر ميكروثانية قبل الحد
        assert bucket_floor(before, timeframe) == boundary - delta
        assert bucket_floor(boundary, timeframe) == boundary
        assert bucket_floor(before, timeframe) != bucket_floor(boundary, timeframe)

    def test_literal_minute_boundary_pair(self) -> None:
        before = datetime(2026, 9, 27, 0, 0, 59, 999999, tzinfo=UTC)
        after = datetime(2026, 9, 27, 0, 1, 0, 0, tzinfo=UTC)
        assert bucket_floor(before, "1m") == T_MIDNIGHT
        assert bucket_floor(after, "1m") == T_MIDNIGHT + timedelta(minutes=1)
        assert bucket_floor(before, "1m") != bucket_floor(after, "1m")

    def test_supported_timeframes_export(self) -> None:
        assert set(SUPPORTED_TIMEFRAMES) == set(TIMEFRAME_DELTAS)
        assert len(SUPPORTED_TIMEFRAMES) == 6

    def test_microsecond_floors_inside_bucket(self) -> None:
        assert bucket_floor(T_02_00 + MICROSECOND, "1m") == T_02_00

    def test_non_utc_aware_normalized_to_utc(self) -> None:
        # 05:30 بتوقيت +03:00 == 02:30 UTC
        shifted = datetime(2026, 9, 27, 5, 30, tzinfo=timezone(timedelta(hours=3)))
        assert bucket_floor(shifted, "1m") == datetime(2026, 9, 27, 2, 30, tzinfo=UTC)
        assert bucket_floor(shifted, "1h") == datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
        assert bucket_floor(shifted, "4h") == datetime(2026, 9, 27, 0, 0, tzinfo=UTC)

    def test_pre_epoch_flooring(self) -> None:
        ts = datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
        assert bucket_floor(ts, "1d") == datetime(1969, 12, 31, 0, 0, tzinfo=UTC)
        assert bucket_floor(ts, "1m") == datetime(1969, 12, 31, 23, 59, tzinfo=UTC)

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValueError, match="naive datetime"):
            bucket_floor(datetime(2026, 9, 27, 2, 0), "1m")

    @pytest.mark.parametrize(
        "bad_timeframe",
        ["2m", "1s", "1M", "1w", "60m", "tick", ""],
    )
    def test_unknown_timeframes_rejected(self, bad_timeframe: str) -> None:
        with pytest.raises(ValueError, match="unsupported timeframe"):
            bucket_floor(T_02_00, bad_timeframe)

    def test_unknown_timeframe_via_add_trade_raises_before_any_state(self) -> None:
        builder = CandleBuilder()
        with pytest.raises(ValueError, match="unsupported timeframe"):
            builder.add_trade(_trade(T_02_00, 100.0, 1.0, timeframe="3m"))
        # الرفع فوري بلا أثر جانبي: لا مجارٍ ولا إحصاءات ولا شموع
        assert builder.first_bar_time is None
        assert builder.last_bar_time is None
        assert builder.n_closed == 0
        assert builder.n_evolved_updates == 0
        assert builder.late_events == 0


# ───────── المتطورة لا تفوّض (§27) ─────────


class TestDevelopingDoesNotDelegate:
    """كل إصدار وسيط is_closed=False؛ True فقط عند القفل (بأي مسار)."""

    def test_intermediate_emissions_never_closed(self) -> None:
        builder = CandleBuilder()
        # أول حدث في المجرى: يبدأ المتطورة ولا يُعاد شيء (لا سابقة تُقفل)
        assert builder.add_trade(_trade(T_02_00 + timedelta(seconds=5), 100.0, 1.0)) is None
        # كل ما صدر داخل الدلو بعده متطور — حتى اللحظة الأخيرة قبيل العبور
        for i in range(1, 6):
            out = builder.add_trade(_trade(T_02_00 + timedelta(seconds=5 + i * 10), 100.0 + i, 1.0))
            assert out is not None
            assert out.is_closed is False
        closed = builder.add_trade(_trade(T_02_00 + timedelta(minutes=1, seconds=1), 90.0, 1.0))
        assert closed is not None and closed.is_closed is True
        explicit = builder.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert explicit is not None and explicit.is_closed is True
        # الثالثة البائتة: لا متطورة بعد الإقفال
        assert builder.close_current("BINANCE_USDM:BTCUSDT", "1m") is None


# ───────── الأحداث المتأخرة بعد القفل ─────────


class TestLateEvents:
    """المتأخر بعد تجاوز نافذته: يُحصى ولا يعود يلمس شيئًا (جمود §27)."""

    @staticmethod
    def _known_bar() -> tuple[CandleBuilder, Candle]:
        """دلو 02:00 معروف ثم عبور إلى 02:01 يقيده — يعيد البنّاء والمقفلة."""
        builder = CandleBuilder()
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=10), 100.0, 1.0))
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=20), 102.0, 2.0))
        closed = builder.add_trade(_trade(T_02_00 + timedelta(minutes=1, seconds=5), 101.0, 1.0))
        assert closed is not None and closed.is_closed is True
        return builder, closed

    def test_late_after_rollover_counted_and_ignored(self) -> None:
        builder, closed = self._known_bar()
        # حدث لدلو مقفل (02:00) يصل بعد عبور الحد إلى 02:01
        late = builder.add_trade(_trade(T_02_00 + timedelta(seconds=30), 500.0, 999.0))
        assert late is None
        assert builder.late_events == 1
        assert builder.n_closed == 1  # لم يزد القفل
        assert builder.n_evolved_updates == 1  # ولم يزد التحديث المتطور
        # المقفلة لم تتأثر: إعادة البناء بدون المتأخر ⇒ نفس الشمعة بايت-ببايت
        clean = CandleBuilder()
        clean.add_trade(_trade(T_02_00 + timedelta(seconds=10), 100.0, 1.0))
        clean.add_trade(_trade(T_02_00 + timedelta(seconds=20), 102.0, 2.0))
        clean_closed = clean.add_trade(
            _trade(T_02_00 + timedelta(minutes=1, seconds=5), 101.0, 1.0)
        )
        assert clean_closed is not None
        assert clean_closed == closed  # عزل تام للمقفلة عن المتأخر

    def test_late_gap_bucket_creates_no_retroactive_bar(self) -> None:
        builder = CandleBuilder()
        # 5m: دلو 02:00 يُقفل عند أول حدث في 02:15 (دلوا 02:05/02:10 فاضيان)
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=5), 100.0, 1.0, timeframe="5m"))
        closed = builder.add_trade(
            _trade(T_02_00 + timedelta(minutes=15, seconds=5), 103.0, 1.0, timeframe="5m")
        )
        assert closed is not None and closed.is_closed is True
        # متأخر لدلو 02:05 الفائت (لا شمعة له أصلًا ولا تُستحدث بأثر رجعي)
        late = builder.add_trade(
            _trade(T_02_00 + timedelta(minutes=7), 90.0, 500.0, timeframe="5m")
        )
        assert late is None
        assert builder.late_events == 1
        # المتطورة 02:15 لم تبتلع كمية المتأخر ⇒ لا شمعة فائتة خلف الكواليس
        evolved = builder.add_trade(
            _trade(T_02_00 + timedelta(minutes=15, seconds=6), 104.0, 2.0, timeframe="5m")
        )
        assert evolved is not None
        assert evolved.volume == 3.0  # 1.0 + 2.0 فقط — كمية المتأخر غائبة
        assert evolved.low == 103.0  # قاع 90.0 المتأخر غير موجود

    def test_event_for_explicitly_closed_bucket_is_late(self) -> None:
        builder = CandleBuilder()
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=5), 100.0, 1.0))
        closed = builder.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert closed is not None and closed.is_closed is True
        # حدث لنفس الدلو المقفل صراحةً: متأخر — لا بعث ولا شمعة مكررة
        duplicate = builder.add_trade(_trade(T_02_00 + timedelta(seconds=50), 101.0, 1.0))
        assert duplicate is None
        assert builder.late_events == 1
        # الدلو اللاحق يبدأ شمعة جديدة تعرف إغلاق المقفلة (prev_close)
        fresh = builder.add_trade(_trade(T_02_00 + timedelta(minutes=2, seconds=5), 102.0, 1.0))
        assert fresh is None  # بداية شمعة جديدة لا تُعاد (لا سابقة تُقفل)
        evolved = builder.add_trade(_trade(T_02_00 + timedelta(minutes=2, seconds=6), 102.5, 1.0))
        assert evolved is not None
        # max(0.5, |102.5-100|, |102-100|) = 2.5 ⇒ prev_close للمقفلة الصريحة
        assert evolved.true_range == 2.5
        assert builder.last_bar_time == T_02_00 + timedelta(minutes=2)


# ───────── سلّل الجودة ─────────


class TestQualityLadder:
    """سلّل الشدة: أسوأ مساهمة تفوز — وQUARANTINED واحدة تجتاح الشمعة كلها."""

    def test_ladder_is_the_documented_permutation(self) -> None:
        # الترتيب المنقول من تعريف المهمة 1.4 — قابل للمراجعة عند دمج 1-a
        assert QUALITY_SEVERITY_LADDER == (
            DataQuality.HEALTHY,
            DataQuality.DELAYED,
            DataQuality.PARTIAL,
            DataQuality.OUT_OF_ORDER,
            DataQuality.DUPLICATED,
            DataQuality.STALE,
            DataQuality.GAP_DETECTED,
            DataQuality.UNAVAILABLE,
            DataQuality.QUARANTINED,
        )
        # تباديل كامل لحالات §7.4 التسع — لا حالة ناقصة ولا مكررة
        assert len(QUALITY_SEVERITY_LADDER) == len(set(QUALITY_SEVERITY_LADDER))
        assert set(QUALITY_SEVERITY_LADDER) == set(DataQuality)
        assert len(set(DataQuality)) == 9

    def test_single_quarantined_poisons_the_whole_candle(self) -> None:
        builder = CandleBuilder()
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=1), 100.0, 1.0))
        builder.add_trade(_trade(T_02_00 + timedelta(seconds=2), 101.0, 1.0))
        poisoned = builder.add_trade(
            _trade(T_02_00 + timedelta(seconds=3), 100.5, 1.0),
            quality=DataQuality.QUARANTINED,
        )
        assert poisoned is not None
        assert poisoned.quality is DataQuality.QUARANTINED
        # أحداث أصحاء لاحقة لا تُنقذ الشمعة — التراكم لا يتراجع
        recovered = builder.add_trade(_trade(T_02_00 + timedelta(seconds=4), 100.6, 1.0))
        assert recovered is not None
        assert recovered.quality is DataQuality.QUARANTINED
        closed = builder.add_trade(_trade(T_02_00 + timedelta(minutes=1, seconds=1), 100.0, 1.0))
        assert closed is not None and closed.is_closed is True
        assert closed.quality is DataQuality.QUARANTINED

    @pytest.mark.parametrize(
        ("lesser", "worst"),
        [
            (DataQuality.HEALTHY, DataQuality.DELAYED),
            (DataQuality.DELAYED, DataQuality.PARTIAL),
            (DataQuality.PARTIAL, DataQuality.OUT_OF_ORDER),
            (DataQuality.OUT_OF_ORDER, DataQuality.DUPLICATED),
            (DataQuality.DUPLICATED, DataQuality.STALE),
            (DataQuality.STALE, DataQuality.GAP_DETECTED),
            (DataQuality.GAP_DETECTED, DataQuality.UNAVAILABLE),
            (DataQuality.UNAVAILABLE, DataQuality.QUARANTINED),
            (DataQuality.HEALTHY, DataQuality.QUARANTINED),
        ],
    )
    def test_higher_severity_wins_regardless_of_arrival_order(
        self, lesser: DataQuality, worst: DataQuality
    ) -> None:
        for first, second in ((lesser, worst), (worst, lesser)):
            builder = CandleBuilder()
            builder.add_trade(_trade(T_02_00 + timedelta(seconds=1), 100.0, 1.0), quality=first)
            evolved = builder.add_trade(
                _trade(T_02_00 + timedelta(seconds=2), 101.0, 1.0), quality=second
            )
            assert evolved is not None
            assert evolved.quality is worst


# ───────── تعدد المجاري (أداة × إطار) ─────────


class TestMultipleStreams:
    """مجراوان مستقلان يتشاركان البنّاء دون أي تسرب متبادل."""

    def test_streams_are_independent(self) -> None:
        builder = CandleBuilder()
        # BTCUSDT على 1m وETHUSDT على 5m — لحظتان متقاربتان
        assert builder.add_trade(_trade(T_02_00 + timedelta(seconds=5), 100.0, 1.0)) is None
        assert (
            builder.add_trade(
                _trade(T_02_00 + timedelta(seconds=6), 50.0, 10.0, symbol="ETHUSDT", timeframe="5m")
            )
            is None
        )
        # تحديث كل مجرى على حدة
        btc = builder.add_trade(_trade(T_02_00 + timedelta(seconds=10), 101.0, 1.0))
        eth = builder.add_trade(
            _trade(T_02_00 + timedelta(seconds=11), 51.0, 5.0, symbol="ETHUSDT", timeframe="5m")
        )
        assert btc is not None
        assert btc.instrument_id == "BINANCE_USDM:BTCUSDT"
        assert btc.timeframe == "1m"
        assert btc.volume == 2.0
        assert eth is not None
        assert eth.instrument_id == "BINANCE_USDM:ETHUSDT"
        assert eth.timeframe == "5m"
        assert eth.volume == 15.0
        # عبور حد 1m يقفل BTC فقط — متطورة ETH لم تتأثر إطلاقًا
        btc_closed = builder.add_trade(
            _trade(T_02_00 + timedelta(minutes=1, seconds=1), 100.5, 1.0)
        )
        assert btc_closed is not None and btc_closed.is_closed is True
        assert btc_closed.instrument_id == "BINANCE_USDM:BTCUSDT"
        eth_still = builder.close_current("BINANCE_USDM:ETHUSDT", "5m")
        assert eth_still is not None
        assert eth_still.is_closed is True
        assert eth_still.high == 51.0 and eth_still.low == 50.0
        assert eth_still.volume == 15.0
        assert eth_still.true_range == 1.0  # أول شمعة في مجراها: لا إغلاق سابق
        # إحصاءات البنّاء عبر المجرين معًا
        assert builder.n_closed == 2
        assert builder.n_evolved_updates == 2
        assert builder.late_events == 0
        assert builder.first_bar_time == T_02_00
        assert builder.last_bar_time == T_02_00 + timedelta(minutes=1)

    def test_close_current_unknown_or_empty_stream_returns_none(self) -> None:
        builder = CandleBuilder()
        assert builder.close_current("UNKNOWN:XYZ", "1m") is None
        builder.add_trade(_trade(T_02_00, 100.0, 1.0))
        # إطار مختلف ⇒ مجرى مختلف (لا متطورة له)
        assert builder.close_current("BINANCE_USDM:BTCUSDT", "5m") is None
        assert builder.close_current("BINANCE_USDM:BTCUSDT", "1m") is not None
        # الإقفال المزدوج: الثاني لا يجد متطورة
        assert builder.close_current("BINANCE_USDM:BTCUSDT", "1m") is None


# ───────── اللا-نظرة-المستقبلية (§26.3/§38.1) والحتمية ─────────


class TestNoLookahead:
    """إدراج t+1 بعد بناء t لا يغيّر مخرجات t — لا قيمة تُشتق من المستقبل."""

    def test_future_event_never_revises_past_outputs(self) -> None:
        prefix = [
            _trade(T_02_00 + timedelta(seconds=5), 100.0, 1.0),
            _trade(T_02_00 + timedelta(seconds=15), 103.0, 2.0),
            _trade(T_02_00 + timedelta(seconds=30), 98.0, 1.5),
        ]
        future = _trade(T_02_00 + timedelta(minutes=1, seconds=2), 250.0, 42.0)  # t+1

        # تشغيل توقف عند t (نهاية بث مفترضة ⇒ إقفال صريح)
        stopped = CandleBuilder()
        stopped_outputs = [_dump(stopped.add_trade(e)) for e in prefix]
        stopped_closed = stopped.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert stopped_closed is not None

        # نفس البادئة ثم إدراج t+1 بعدها
        continued = CandleBuilder()
        continued_outputs = [_dump(continued.add_trade(e)) for e in prefix]
        assert continued_outputs == stopped_outputs  # نفس المدخلات حتى t
        rolled = continued.add_trade(future)
        assert rolled is not None
        # الإقفال بعبور t+1 == الإقفال الصريح عند t: الحدث المستقبلي لم يساهم
        # في شمعة الدلو السابق بشيء — بايت-ببايت
        assert _dump(rolled) == _dump(stopped_closed)
        # المخرجات الملتقطة عند t لم تتغير بإدراج t+1
        assert continued_outputs == stopped_outputs
        # t+1 أسهم في شمعته هو وحدها (دلو 02:01)
        future_bar = continued.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert future_bar is not None
        assert future_bar.bar_time == T_02_00 + timedelta(minutes=1)
        assert future_bar.open == 250.0
        assert future_bar.volume == 42.0


# تسلسل مختلط مثبت حرفيًا (أقوى من بذرة عشوائية: قائمة معلومة قابلة للمراجعة
# بالعين) — وهو "البذرة المثبتة" في اختبار الحتمية أدناه: دلاء متعددة،
# اضطراب ترتيب داخل الدلو، فجوة، ومتأخران صريحان بعد القفل.
_DETERMINISM_EVENTS: list[TradeEvent] = [
    # دلو 02:00 — وصول بترتيب زمني مضطرب داخل الدلو
    _trade(T_02_00 + timedelta(seconds=20), 100.0, 1.0),
    _trade(T_02_00 + timedelta(seconds=5), 99.5, 0.5),
    _trade(T_02_00 + timedelta(seconds=40), 101.0, 2.0),
    _trade(T_02_00 + timedelta(seconds=10), 100.5, 1.5),
    # عبور الحد إلى دلو 02:01
    _trade(T_02_00 + timedelta(minutes=1, seconds=3), 102.0, 1.0),
    _trade(T_02_00 + timedelta(minutes=1, seconds=30), 101.5, 0.7),
    # قفزة إلى دلو 02:03 (دلو 02:02 فجوة فارغة)
    _trade(T_02_00 + timedelta(minutes=3, seconds=1), 98.0, 3.0),
    # متأخر صريح لدلو 02:01 المقفل
    _trade(T_02_00 + timedelta(minutes=1, seconds=45), 500.0, 9.0),
    # متأخر لدلو فائت 02:02 (لم تبدأ له شمعة أبدًا)
    _trade(T_02_00 + timedelta(minutes=2, seconds=10), 400.0, 8.0),
    # دلو 02:03 يواصل التطور
    _trade(T_02_00 + timedelta(minutes=3, seconds=20), 97.5, 1.2),
]


def _full_run(events: list[TradeEvent]) -> tuple[list[str], tuple[int, int, int]]:
    """تشغيل كامل حتى نهاية البث + لقطة إحصاءات — لمقارنة الحتمية."""
    builder = CandleBuilder()
    outputs = [_dump(builder.add_trade(e)) for e in events]
    outputs.append(_dump(builder.close_current("BINANCE_USDM:BTCUSDT", "1m")))
    stats = (builder.n_closed, builder.n_evolved_updates, builder.late_events)
    return outputs, stats


class TestDeterminism:
    """نفس المدخلات ⇒ نفس المخرجات حرفيًا — مرتين متطابقتين (بذرة مثبتة)."""

    def test_fixed_mixed_sequence_replays_identically(self) -> None:
        run_a = _full_run(_DETERMINISM_EVENTS)
        run_b = _full_run(_DETERMINISM_EVENTS)
        # مرتين متطابقتين: تدفق المخرجات كاملًا + الإحصاءات معًا
        assert run_a == run_b
        # والإحصاءات مطابقة للحساب اليدوي من بنية التسلسل أعلاه:
        # ثلاث مقفلات (02:00 و02:01 بعبور الحد، و02:03 بالإقفال الصريح)،
        # خمسة تحديثات متطورة (3+1+1)، ومتأخران
        assert run_a[1] == (3, 5, 2)


# ───────── الخصائص (hypothesis — بذرة مثبتة عبر derandomize) ─────────


class TestSingleBucketProperty:
    """تسلسل عشوائي داخل دلو واحد ⇒ التجميع الصادق — لأي إطار من الستة."""

    @given(
        timeframe=st.sampled_from(sorted(TIMEFRAME_DELTAS)),
        start_seconds=st.integers(min_value=0, max_value=200 * 86400),
        events=st.lists(
            st.tuples(
                st.floats(min_value=0.5, max_value=5000.0, allow_nan=False, allow_infinity=False),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=86_400_000_000 - 1),
            ),
            min_size=1,
            max_size=40,
        ),
    )
    @hyp_settings(max_examples=75, deadline=None, derandomize=True)
    def test_single_bucket_aggregation_any_timeframe(
        self,
        timeframe: str,
        start_seconds: int,
        events: list[tuple[float, float, int]],
    ) -> None:
        delta = TIMEFRAME_DELTAS[timeframe]
        # نقطة انطلاق عشوائية ثم محاذاة لأسفل حدّ الإطار (oracle مستقل)
        rough = datetime(2025, 6, 1, tzinfo=UTC) + timedelta(seconds=start_seconds)
        base = bucket_floor(rough, timeframe)
        span_us = int(delta.total_seconds() * 1_000_000)
        prices: list[float] = []
        quantities: list[float] = []
        evolving_seen: list[Candle] = []
        builder = CandleBuilder()
        for price, qty, offset_us in events:
            # القسمة على طول الدلو تُسقط اللحظة داخل الدلو نفسه دائمًا
            when = base + timedelta(microseconds=offset_us % span_us)
            prices.append(price)
            quantities.append(qty)
            emitted = builder.add_trade(_trade(when, price, qty, timeframe=timeframe))
            if emitted is not None:
                evolving_seen.append(emitted)
        # كل ما صدر داخل الدلو متطور لا يفوّض (§27)
        assert all(c.is_closed is False for c in evolving_seen)
        closed = builder.close_current("BINANCE_USDM:BTCUSDT", timeframe)
        # أساس التجميع: open أول حدث وصل، close آخره، high/low أقصى/أدنى،
        # volume المجموع — دائمًا مهما كان الإطار ومهما كان التسلسل
        assert closed is not None
        assert closed.is_closed is True
        assert closed.bar_time == base
        assert closed.timeframe == timeframe
        assert closed.instrument_id == "BINANCE_USDM:BTCUSDT"
        assert closed.open == prices[0]
        assert closed.close == prices[-1]
        assert closed.high == max(prices)
        assert closed.low == min(prices)
        # الخاصية الرياضية للمجموع، ثم المطابقة التامة مع التراكم الحدثي اليساري
        # بترتيب الوصول (وليس sum() المُعوّض لبايثون 3.12 — قد يخلفه بأولب واحد)
        assert closed.volume == pytest.approx(sum(quantities))
        naive_volume = 0.0
        for q in quantities:
            naive_volume += q
        assert closed.volume == naive_volume
        # المشتقات متسقة داخليًا مع عقود §8.1
        assert closed.range == closed.high - closed.low
        assert closed.body_size == abs(closed.close - closed.open)
        assert closed.upper_wick == closed.high - max(closed.open, closed.close)
        assert closed.lower_wick == min(closed.open, closed.close) - closed.low
        assert 0.0 <= closed.body_fraction <= 1.0
        assert 0.0 <= closed.close_location_value <= 1.0
        assert closed.true_range == closed.range  # أول شمعة في المجرى
        assert closed.realized_volatility == abs(math.log(closed.close / closed.open))
        assert closed.session_id == base.date().isoformat()
        # الإحصاءات
        assert builder.n_closed == 1
        assert builder.n_evolved_updates == max(0, len(events) - 1)
        assert builder.late_events == 0
        assert builder.first_bar_time == base
        assert builder.last_bar_time == base

    @given(
        prefix=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=59),
                st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
                st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
            ),
            min_size=1,
            max_size=24,
        ),
        future=st.tuples(
            st.integers(min_value=0, max_value=59),
            st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
        ),
    )
    @hyp_settings(max_examples=50, deadline=None, derandomize=True)
    def test_outputs_up_to_t_independent_of_future(
        self,
        prefix: list[tuple[int, float, float]],
        future: tuple[int, float, float],
    ) -> None:
        """خاصية §26.3: مخرجات البادئة لا تتغير بإدراج حدث t+1 بعدها."""
        prefix_events = [
            _trade(T_02_00 + timedelta(seconds=sec), price, qty) for sec, price, qty in prefix
        ]
        # t+1: أول حدث في الدلو التالي (02:01) — يضمن عبور الحد
        sec, price, qty = future
        future_event = _trade(T_02_00 + timedelta(minutes=1, seconds=sec), price, qty)

        stopped = CandleBuilder()
        stopped_outputs = [_dump(stopped.add_trade(e)) for e in prefix_events]
        stopped_closed = stopped.close_current("BINANCE_USDM:BTCUSDT", "1m")
        assert stopped_closed is not None

        continued = CandleBuilder()
        continued_outputs = [_dump(continued.add_trade(e)) for e in prefix_events]
        assert continued_outputs == stopped_outputs  # حتمية عبر النسختين
        rolled = continued.add_trade(future_event)
        assert rolled is not None
        assert _dump(rolled) == _dump(stopped_closed)
