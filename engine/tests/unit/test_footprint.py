"""اختبارات بنّاء الفوتبرنت الحدثي (المهمة 4-b) — §8.2 + §12 + §27 + §26.3.

التغطية المطلوبة:
- golden يدوي هندسي: شريطان بقيم صغيرة قابلة للحساب الذهني — كل حقول §8.2
  بما فيها POC/VAH/VAL بتوسّع ثنائي غير متناظر وقاعدة تعادل الثنائيتين،
  ونسخة متطورة وسيطة بقيم محسوبة يدويًا، وشريط أحادي الصف بالإقفال الصريح.
- golden الحقيقي (بوابة المرحلة): عينة phase4 (35,932 صفقة BTCUSDT /
  120 دقيقة) — مطابقة الدلو-بالدلو ضد klines المرجعية: buy_volume ==
  taker_buy_volume وtotal/sell == volume (مع دلتا حدود موثقة لدلاء
  aggTrades عابرة للحد) — parametrize على كل الشموع الـ120.
- الحتمية: نفس القائمة مرتين ⇒ نفس هاش sha256 للترميز JSON الكامل
  للأشرطة المقفلة وصفوفها.
- اللا-نظرة-المستقبلية (§26.3): إقفال الدلو بالعبور == إقفاله الصريح
  قبل تغذية أي حدث لاحق (بايت-ببايت)، وخاصية hypothesis: مخرجات البادئة
  لا تتغير بإضافة ذيل.
- المتأخرون (§27): يُحصون ولا يمسّون المقفلة ولا ينشئون فائتة.
- الجودة: أسوأ مساهمة تفوز — QUARANTINED واحدة تجتاح الشريط.
- الاختلال الصفّي (§12.6): 10/2 ⇒ BUY و1/9 ⇒ SELL و4/4 ⇒ لا شيء،
  والعدادات صحيحة، والنسبة معامل بادئ فعال.
- رفض None (§12.7): مصدر بلا علم يُرفض قبل أي أثر جانبي.
- خصائص hypothesis (derandomize): حصص تسجم 1 و|delta| ≤ total وصفوف
  مرتبة تصاعديًا وPOC ∈ [VAL, VAH] وVAH ≥ VAL واتساق الصفوف مع الشريط.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from ingestion.raw_store import read_parquet_bytes
from orderflow.footprint import VALUE_AREA_FRACTION, FootprintBuilder
from orderflow.rows import (
    IMBALANCE_RATIO,
    METHODOLOGY_AGGTRADE_TAKER,
    BarRows,
    row_imbalance_side,
)
from schemas import DataQuality, FootprintBar, ImbalanceSide, TradeEvent

# ───────── ثوابت وأدوات ─────────

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
SOURCE_FEED = "binance.aggTrades"

T0 = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)  # لحظة مرجعية — UTC (عقد §7.1)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "phase4"


def _trade(
    when: datetime,
    price: float,
    quantity: float,
    buyer_is_maker: bool,
    *,
    venue: str = "BINANCE_USDM",
    symbol: str = "BTCUSDT",
    timeframe: str = "1t",
    feed_id: str = SOURCE_FEED,
) -> TradeEvent:
    """حدث صفقة اصطناعي بعقد §7.1 — مصدره tick "1t" (الإطار من البادئ).

    ``buyer_is_maker`` إلزامي موضعيًا: الفوتبرنت لا يُبنى بلا علم الطرف
    المتسبب (§12.7) فكل موقع استدعاء يعلن جهته صراحة.
    """
    return TradeEvent(
        event_time_utc=when,
        receive_time_utc=when,
        source_timeframe=timeframe,
        venue=venue,
        symbol=symbol,
        feed_id=feed_id,
        sequence_id=None,
        source_latency_ms=None,
        price=price,
        quantity=quantity,
        buyer_is_maker=buyer_is_maker,
    )


def _dump(bar: FootprintBar | None) -> str:
    """تمثيل حتمي قابل للمقارنة بايت-ببايت (None ⇒ علامة مميزة)."""
    return "<none>" if bar is None else bar.model_dump_json()


def _builder_digest(builder: FootprintBuilder) -> str:
    """بصمة sha256 للترميز JSON الكامل للأشرطة المقفلة وصفوفها معًا."""
    parts: list[str] = []
    for br in builder.closed_bars_with_rows():
        parts.append(br.bar.model_dump_json())
        parts.append(json.dumps([[r.price, r.buy_volume, r.sell_volume] for r in br.rows]))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# ───────── golden يدوي: صفوف قابلة للحساب الذهني ─────────
#
# الشريط 1 (دلو 02:00) — الصفوف المستهدفة (سعر: شراء/بيع):
#   100: 0.5/0.5 → 1    101: 1/3 → 4 (اختلال بيعي 3:1 بالضبط)
#   102: 2/8 → 10 (بيعي 4:1)    103: 5/5 → 10
#   104: 20/4 → 24 (POC؛ شرائي 5:1)    105: 6/0 → 6 (شرائي ∞)
#   106: 2/2 → 4    107: 0.5/0.5 → 1
#   ⇒ buy=37 sell=23 total=60 delta=+14، VWAP=6211/60≈103.5167، POC=104
#   منطقة القيمة: من 104 (مغطى 24 < 42): ثنائية عليا [105,106]=10 ضد
#   دنيا [102,103]=20 ⇒ الدنيا ⇒ مغطى 44 ≥ 42 ⇒ val=102, vah=104
#   (توسّع غير متناظر: صفان مغطيان تحت POC وثلاثة فوقه خارجه).
#   عدادات: شرائي 2 (104 و105) وبيعي 2 (101 و102)؛ أقصى موجبة 104
#   (+16) وأقصى سالبة 102 (−6).
_BAR1_TRADES: list[tuple[timedelta, float, float, bool]] = [
    (timedelta(seconds=1), 104.0, 20.0, False),
    (timedelta(seconds=2), 102.0, 8.0, True),
    (timedelta(seconds=3), 101.0, 3.0, True),
    (timedelta(seconds=4), 105.0, 6.0, False),
    (timedelta(seconds=5), 100.0, 0.5, False),
    (timedelta(seconds=6), 103.0, 5.0, False),
    (timedelta(seconds=7), 106.0, 2.0, True),
    (timedelta(seconds=8), 102.0, 2.0, False),
    (timedelta(seconds=9), 107.0, 0.5, True),
    (timedelta(seconds=10), 104.0, 4.0, True),
    (timedelta(seconds=11), 101.0, 1.0, False),
    (timedelta(seconds=12), 103.0, 5.0, True),
    (timedelta(seconds=13), 100.0, 0.5, True),
    (timedelta(seconds=14), 106.0, 2.0, False),
    (timedelta(seconds=15), 107.0, 0.5, False),
]
# الشريط 2 (دلو 02:01) — الصفوف المستهدفة:
#   199: 2/2 → 4    200: 1/3 → 4 (بيعي)    201: 3/3 → 6    202: 2/2 → 4
#   203: 6/6 → 12 (POC)    204: 3/3 → 6    205: 1.5/0.5 → 2 (شرائي 3:1)
#   206: 1/1 → 2    207: 0.5/0.5 → 1
#   ⇒ buy=20 sell=21 total=41 delta=−1، POC=203، VWAP=8299/41≈202.415
#   منطقة القيمة: مغطى 12 < 28.7: عليا [204,205]=8 ضد دنيا [201,202]=10
#   ⇒ الدنيا (مغطى 22، النطاق [201..203])؛ ثم عليا [204,205]=8 ضد دنيا
#   [199,200]=8 ⇒ **تعادل** — منتصف النطاق المغطى 202 وPOC=203 أعلى منه
#   ⇒ الجهة المضادة للميل = الدنيا ⇒ مغطى 30 ≥ 28.7 ⇒ val=199, vah=203.
#   (اختيار العليا عند التعادل كان سيعطي val=201/vah=205 — القاعدة
#   الحتمية الموثقة تفصل حرفيًا بين النتيجتين.)
#   عدادات: شرائي 1 (205) وبيعي 1 (200)؛ أقصى موجبة 205 (+1) وسالبة 200 (−2).
_BAR2_TRADES: list[tuple[timedelta, float, float, bool]] = [
    (timedelta(minutes=1, seconds=1), 203.0, 6.0, False),
    (timedelta(minutes=1, seconds=2), 199.0, 2.0, True),
    (timedelta(minutes=1, seconds=3), 205.0, 1.5, False),
    (timedelta(minutes=1, seconds=4), 201.0, 3.0, True),
    (timedelta(minutes=1, seconds=5), 206.0, 1.0, True),
    (timedelta(minutes=1, seconds=6), 200.0, 3.0, True),
    (timedelta(minutes=1, seconds=7), 204.0, 3.0, True),
    (timedelta(minutes=1, seconds=8), 202.0, 2.0, False),
    (timedelta(minutes=1, seconds=9), 207.0, 0.5, True),
    (timedelta(minutes=1, seconds=10), 199.0, 2.0, False),
    (timedelta(minutes=1, seconds=11), 201.0, 3.0, False),
    (timedelta(minutes=1, seconds=12), 205.0, 0.5, True),
    (timedelta(minutes=1, seconds=13), 206.0, 1.0, False),
    (timedelta(minutes=1, seconds=14), 204.0, 3.0, False),
    (timedelta(minutes=1, seconds=15), 202.0, 2.0, True),
    (timedelta(minutes=1, seconds=16), 200.0, 1.0, False),
    (timedelta(minutes=1, seconds=17), 207.0, 0.5, False),
    (timedelta(minutes=1, seconds=18), 203.0, 6.0, True),
]


def _feed(builder: FootprintBuilder, trades: list[tuple[timedelta, float, float, bool]]) -> None:
    """تغذية قائمة (إزاحة، سعر، كمية، جهة) على البنّاء (تجاهل المخرجات)."""
    for offset, price, quantity, buyer_is_maker in trades:
        builder.add_trade(_trade(T0 + offset, price, quantity, buyer_is_maker))


class TestGoldenManual:
    """الذهبي اليدوي: كل حقول §8.2 محسوبة يدويًا — أي انحراف يكسر الاختبار."""

    def test_golden_full_field_bars(self) -> None:
        builder = FootprintBuilder(timeframe="1m")

        # أول حدث على الإطلاق: تبدأ المتطورة ولا يُعاد شيء (لا سابقة تُقفل)
        first = builder.add_trade(_trade(*_to_args(_BAR1_TRADES[0])))
        assert first is None
        # بقية أحداث الدلو: نسخ متطورة لا تفوّض (§27)
        for offset, price, quantity, buyer_is_maker in _BAR1_TRADES[1:]:
            evolved = builder.add_trade(_trade(T0 + offset, price, quantity, buyer_is_maker))
            assert evolved is not None and evolved.is_closed is False

        # عبور الحد إلى 02:01 بأول صفقة للشريط 2: السابق يُقفل ويُعاد
        closed1 = builder.add_trade(_trade(*_to_args(_BAR2_TRADES[0])))
        assert closed1 is not None
        assert closed1.is_closed is True
        assert closed1.instrument_id == INSTRUMENT
        assert closed1.timeframe == "1m"  # إطار البادئ لا إطار المصدر "1t"
        assert closed1.bar_time == T0
        assert closed1.quality is DataQuality.HEALTHY
        assert closed1.source_feed == SOURCE_FEED
        assert closed1.methodology == METHODOLOGY_AGGTRADE_TAKER
        # ── مجاميع §8.2 — محسوبة يدويًا ──
        assert closed1.buy_volume == 37.0
        assert closed1.sell_volume == 23.0
        assert closed1.total_volume == 60.0
        assert closed1.delta == 14.0
        assert closed1.buy_share == pytest.approx(37.0 / 60.0)
        assert closed1.sell_share == pytest.approx(23.0 / 60.0)
        assert closed1.buy_share + closed1.sell_share == pytest.approx(1.0)
        # ── POC ومنطقة القيمة — التوسّع الثنائي غير المتناظر ──
        assert closed1.poc == 104.0  # الحجم الأقصى 24 فريد
        assert closed1.val == 102.0  # الثنائية الدنيا [102,103]=20 فازت بالعليا
        assert closed1.vah == 104.0  # POC أعلى سعر مغطى
        assert closed1.row_count == 8
        assert closed1.buy_imbalance_count == 2  # 104 (5:1) و105 (∞)
        assert closed1.sell_imbalance_count == 2  # 101 (1:3 بالضبط) و102 (1:4)
        assert closed1.max_positive_delta_row == 104.0  # +16
        assert closed1.max_negative_delta_row == 102.0  # −6

        # بقية أحداث الشريط 2 داخل دلو 02:01
        for trade in _BAR2_TRADES[1:]:
            evolved = builder.add_trade(_trade(*_to_args(trade)))
            assert evolved is not None and evolved.is_closed is False

        # عبور إلى 02:02: الشريط 2 يُقفل — التعادل حُسم بالجهة المضادة للميل
        closed2 = builder.add_trade(_trade(T0 + timedelta(minutes=2, seconds=1), 300.0, 3.0, False))
        assert closed2 is not None and closed2.is_closed is True
        assert closed2.bar_time == T0 + timedelta(minutes=1)
        assert closed2.buy_volume == 20.0
        assert closed2.sell_volume == 21.0
        assert closed2.total_volume == 41.0
        assert closed2.delta == -1.0
        assert closed2.buy_share == pytest.approx(20.0 / 41.0)
        assert closed2.sell_share == pytest.approx(21.0 / 41.0)
        assert closed2.poc == 203.0  # 12 فريد
        assert closed2.val == 199.0  # التعادل ⇒ الجهة المضادة لميل POC
        assert closed2.vah == 203.0
        assert closed2.row_count == 9
        assert closed2.buy_imbalance_count == 1  # 205 (3:1)
        assert closed2.sell_imbalance_count == 1  # 200 (1:3)
        assert closed2.max_positive_delta_row == 205.0  # +1
        assert closed2.max_negative_delta_row == 200.0  # −2

        # الشريط 3 (02:02): صف وحيد ثم إقفال صريح — أصغر شريط قانوني
        evolved3 = builder.add_trade(_trade(T0 + timedelta(minutes=2, seconds=2), 300.0, 1.0, True))
        assert evolved3 is not None and evolved3.is_closed is False
        closed3 = builder.close_current(INSTRUMENT)
        assert closed3 is not None and closed3.is_closed is True
        assert closed3.bar_time == T0 + timedelta(minutes=2)
        assert closed3.buy_volume == 3.0
        assert closed3.sell_volume == 1.0
        assert closed3.total_volume == 4.0
        assert closed3.delta == 2.0
        assert closed3.buy_share == 0.75
        assert closed3.sell_share == 0.25
        assert closed3.poc == 300.0  # الصف الوحيد: هدف 70% يُبلغ فورًا
        assert closed3.vah == 300.0
        assert closed3.val == 300.0
        assert closed3.row_count == 1
        assert closed3.buy_imbalance_count == 1  # 3:1 بالضبط
        assert closed3.sell_imbalance_count == 0
        assert closed3.max_positive_delta_row == 300.0
        assert closed3.max_negative_delta_row is None  # لا دلتا سالبة أصلًا

        # الإحصاءات بعد الذهبي كله: 3 مقفلات (2 عبور + 1 صريح)، تحديثات
        # متطورة (15−1)+(18−1)+(2−1)=32، لا متأخرين ولا تعارضات تغذية
        assert builder.n_closed == 3
        assert builder.n_evolved_updates == 32
        assert builder.late_events == 0
        assert builder.feed_id_conflicts == 0
        assert builder.first_bar_time == T0
        assert builder.last_bar_time == T0 + timedelta(minutes=2)

        # الصفوف المقفلة: مرتبة تصاعديًا بالسعر وبحجمات الشريط الذهبي
        bars_rows = builder.closed_bars_with_rows()
        assert len(bars_rows) == 3
        rows1 = bars_rows[0].rows
        expected_prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
        assert [r.price for r in rows1] == expected_prices
        assert [(r.buy_volume, r.sell_volume) for r in rows1] == [
            (0.5, 0.5),
            (1.0, 3.0),
            (2.0, 8.0),
            (5.0, 5.0),
            (20.0, 4.0),
            (6.0, 0.0),
            (2.0, 2.0),
            (0.5, 0.5),
        ]
        assert bars_rows[0].bar == closed1  # نفس الشريط المقفل حرفيًا
        assert [r.price for r in bars_rows[2].rows] == [300.0]  # الشريط الأحادي
        # closed_bars: المقفل وحده بنفس الترتيب الحتمي (تسلسل الإقفال هنا
        # ومتسقًا مع (bar_time, instrument_id) — مجرى واحد بثلاثة دلاء)
        assert builder.closed_bars() == (closed1, closed2, closed3)
        assert builder.closed_bars() == tuple(br.bar for br in bars_rows)

    def test_golden_evolving_snapshot_mid_bar(self) -> None:
        """نسخة متطورة وسيطة (بعد 4 صفقات) بقيم محسوبة يدويًا.

        الصفوف: 101:(0,3) و102:(0,8) و104:(20,0) و105:(6,0) — صفوف
        أحادية الجانب بالكامل (اختلالات ∞) وقبول الشريط لها.
        """
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=1), 104.0, 20.0, False)) is None
        assert builder.add_trade(_trade(T0 + timedelta(seconds=2), 102.0, 8.0, True)) is not None
        assert builder.add_trade(_trade(T0 + timedelta(seconds=3), 101.0, 3.0, True)) is not None
        snapshot = builder.add_trade(_trade(T0 + timedelta(seconds=4), 105.0, 6.0, False))
        assert snapshot is not None and snapshot.is_closed is False
        assert snapshot.bar_time == T0
        assert snapshot.buy_volume == 26.0
        assert snapshot.sell_volume == 11.0
        assert snapshot.total_volume == 37.0
        assert snapshot.delta == 15.0
        assert snapshot.buy_share == pytest.approx(26.0 / 37.0)
        assert snapshot.poc == 104.0  # 20 فريدًا
        # منطقة القيمة: مغطى 20 < 25.9: العليا [105]=6 (صف وحيد عند الحافة)
        # ضد الدنيا [101,102]=11 ⇒ الدنيا ⇒ مغطى 31 ⇒ val=101, vah=104
        assert snapshot.val == 101.0
        assert snapshot.vah == 104.0
        assert snapshot.row_count == 4
        assert snapshot.buy_imbalance_count == 2  # 104 و105 (∞ شرائي)
        assert snapshot.sell_imbalance_count == 2  # 101 و102 (∞ بيعي)
        assert snapshot.max_positive_delta_row == 104.0
        assert snapshot.max_negative_delta_row == 102.0
        # evolving() القراءة الحية == آخر إصدار حرفيًا
        assert builder.evolving(INSTRUMENT) == snapshot


def _to_args(trade: tuple[timedelta, float, float, bool]) -> tuple[datetime, float, float, bool]:
    """تحويل (إزاحة، سعر، كمية، جهة) إلى وسيطات ``_trade``."""
    offset, price, quantity, buyer_is_maker = trade
    return T0 + offset, price, quantity, buyer_is_maker


# ───────── قواعد POC الحتمية ─────────


class TestPocTieBreak:
    """تعادل الحجم الأقصى: الأقرب إلى VWAP؛ وتعادل البعد: الأدنى سعرًا."""

    def test_tie_resolved_by_vwap_proximity(self) -> None:
        # صفوف: 100:(5,5)=10 و110:(5,5)=10 متعادلان و104:(0,2)=2
        # ⇒ VWAP = (1000+208+1100)/22 = 104.909 ⇒ 100 أقرب (4.909 < 5.091)
        builder = FootprintBuilder(timeframe="1m")
        for offset, price, quantity, buyer_is_maker in [
            (1, 100.0, 5.0, False),
            (2, 100.0, 5.0, True),
            (3, 110.0, 5.0, False),
            (4, 110.0, 5.0, True),
            (5, 104.0, 2.0, True),
        ]:
            when = T0 + timedelta(seconds=offset)
            builder.add_trade(_trade(when, price, quantity, buyer_is_maker))
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.poc == 100.0

    def test_equidistant_tie_resolved_by_lower_price(self) -> None:
        # صفّا 100 و110 متعادلان وحدهما ⇒ VWAP=105 ⇒ متساويان بعدًا ⇒ الأدنى
        builder = FootprintBuilder(timeframe="1m")
        for offset, price, quantity, buyer_is_maker in [
            (1, 110.0, 5.0, False),
            (2, 110.0, 5.0, True),
            (3, 100.0, 5.0, False),
            (4, 100.0, 5.0, True),
        ]:
            when = T0 + timedelta(seconds=offset)
            builder.add_trade(_trade(when, price, quantity, buyer_is_maker))
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.poc == 100.0
        # منطقة القيمة انحلّت بالتوسّع نحو الجهة الوحيدة المتاحة
        assert closed.val == 100.0
        assert closed.vah == 110.0


# ───────── الاختلال الصفّي (§12.6) ─────────


class TestRowImbalance:
    """10/2 ⇒ BUY و1/9 ⇒ SELL و4/4 ⇒ لا شيء — والنسبة معامل بادئ فعال."""

    def test_row_level_sides_and_bar_counts(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        _feed(
            builder,
            [
                (timedelta(seconds=1), 100.0, 10.0, False),
                (timedelta(seconds=2), 100.0, 2.0, True),  # 10/2 ⇒ BUY
                (timedelta(seconds=3), 101.0, 1.0, False),
                (timedelta(seconds=4), 101.0, 9.0, True),  # 1/9 ⇒ SELL
                (timedelta(seconds=5), 102.0, 4.0, False),
                (timedelta(seconds=6), 102.0, 4.0, True),  # 4/4 ⇒ لا شيء
            ],
        )
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.buy_imbalance_count == 1
        assert closed.sell_imbalance_count == 1
        assert closed.row_count == 3

    def test_imbalance_ratio_is_a_builder_knob(self) -> None:
        # 6/3 = 2.0 بالضبط: اختلال عند نسبة 2.0 وليس عند الافتراضية 3.0
        trades: list[tuple[timedelta, float, float, bool]] = [
            (timedelta(seconds=1), 100.0, 6.0, False),
            (timedelta(seconds=2), 100.0, 3.0, True),
        ]
        loose = FootprintBuilder(timeframe="1m", imbalance_ratio=2.0)
        _feed(loose, trades)
        closed_loose = loose.close_current(INSTRUMENT)
        assert closed_loose is not None
        assert closed_loose.buy_imbalance_count == 1

        default = FootprintBuilder(timeframe="1m", imbalance_ratio=IMBALANCE_RATIO)
        _feed(default, trades)
        closed_default = default.close_current(INSTRUMENT)
        assert closed_default is not None
        assert closed_default.buy_imbalance_count == 0

    @pytest.mark.parametrize("bad_ratio", [1.0, 0.5, 0.0, -3.0, float("inf")])
    def test_invalid_ratio_rejected(self, bad_ratio: float) -> None:
        with pytest.raises(ValueError, match="نسبة الاختلال"):
            FootprintBuilder(timeframe="1m", imbalance_ratio=bad_ratio)


# ───────── رفض مصدر بلا علم (§12.7) ─────────


class TestNoneRejected:
    """buyer_is_maker=None يُرفض صراحة قبل أي أثر جانبي — وبلا صمت أبدًا."""

    def test_none_rejected_without_side_effects(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=1), 100.0, 2.0, False)) is None
        with pytest.raises(ValueError, match="buyer_is_maker"):
            builder.add_trade(_trade(T0 + timedelta(seconds=2), 101.0, 5.0, None))  # type: ignore[arg-type]
        # الرفع فوري بلا أثر جانبي: الإحصاءات والمتطورة كما كانت
        assert builder.n_closed == 0
        assert builder.n_evolved_updates == 0
        assert builder.late_events == 0
        # الحالة سليمة: حدث سليم لاحق يستأنف التراكم على الشريط نفسه
        resumed = builder.add_trade(_trade(T0 + timedelta(seconds=3), 102.0, 3.0, True))
        assert resumed is not None
        assert resumed.total_volume == 5.0  # 2 + 3 فقط

    def test_none_rejected_even_in_late_position(self) -> None:
        # الرفض يسبق التصنيف الزمني: متأخر بلا علم يُرفض ولا يُحصى متأخرًا
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=1), 100.0, 1.0, False)) is None
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        with pytest.raises(ValueError, match="buyer_is_maker"):
            builder.add_trade(
                _trade(T0 + timedelta(seconds=30), 100.0, 1.0, None)  # type: ignore[arg-type]
            )
        assert builder.late_events == 0


# ───────── بادئ البنّاء ─────────


class TestConstructor:
    """الإطار إلزامي صريح ومعتمَد من الأطر الستة المدعومة (قرار 1.6)."""

    @pytest.mark.parametrize("timeframe", ["1m", "5m", "15m", "1h", "4h", "1d"])
    def test_all_supported_timeframes_accepted(self, timeframe: str) -> None:
        builder = FootprintBuilder(timeframe=timeframe)
        closed = _single_trade_bar(builder)
        assert closed is not None and closed.timeframe == timeframe

    @pytest.mark.parametrize("bad_timeframe", ["1t", "2m", "1s", "tick", ""])
    def test_invalid_timeframe_rejected(self, bad_timeframe: str) -> None:
        with pytest.raises(ValueError, match="غير مدعوم"):
            FootprintBuilder(timeframe=bad_timeframe)

    def test_tick_events_bucketed_by_explicit_frame(self) -> None:
        """أحداث "1t" عبر دقيقتين ⇒ شريطا 1m: العبور يقفل والأخير صريح."""
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0, 100.0, 1.0, False)) is None
        mid = builder.add_trade(_trade(T0 + timedelta(seconds=30), 101.0, 2.0, True))
        assert mid is not None and mid.timeframe == "1m" and not mid.is_closed
        rolled = builder.add_trade(_trade(T0 + timedelta(minutes=1), 102.0, 3.0, False))
        assert rolled is not None and rolled.is_closed and rolled.bar_time == T0
        assert rolled.total_volume == 3.0
        final = builder.close_current(INSTRUMENT)
        assert final is not None and final.is_closed
        assert final.bar_time == T0 + timedelta(minutes=1)
        assert final.total_volume == 3.0


def _single_trade_bar(builder: FootprintBuilder) -> FootprintBar | None:
    """شريط أصغر (صفقة واحدة) عبر الإقفال الصريح — مفتاح بناء سريع."""
    builder.add_trade(_trade(T0, 100.0, 1.0, False))
    return builder.close_current(INSTRUMENT)


# ───────── سلّل الجودة (عقد 1.4 نفسه) ─────────


class TestQualityLadder:
    """أسوأ مساهمة تفوز — QUARANTINED واحدة تجتاح الشريط كله."""

    def test_single_quarantined_poisons_the_whole_bar(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        builder.add_trade(_trade(T0 + timedelta(seconds=1), 100.0, 1.0, False))
        poisoned = builder.add_trade(
            _trade(T0 + timedelta(seconds=2), 101.0, 1.0, True),
            quality=DataQuality.QUARANTINED,
        )
        assert poisoned is not None
        assert poisoned.quality is DataQuality.QUARANTINED
        # أحداث أصحاء لاحقة لا تُنقذ الشريط — التراكم لا يتراجع
        recovered = builder.add_trade(_trade(T0 + timedelta(seconds=3), 100.5, 1.0, False))
        assert recovered is not None
        assert recovered.quality is DataQuality.QUARANTINED
        closed = builder.add_trade(_trade(T0 + timedelta(minutes=1, seconds=1), 100.0, 1.0, False))
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
            builder = FootprintBuilder(timeframe="1m")
            builder.add_trade(_trade(T0 + timedelta(seconds=1), 100.0, 1.0, False), quality=first)
            evolved = builder.add_trade(
                _trade(T0 + timedelta(seconds=2), 101.0, 1.0, True), quality=second
            )
            assert evolved is not None
            assert evolved.quality is worst


# ───────── الأحداث المتأخرة بعد القفل (§27) ─────────


class TestLateEvents:
    """المتأخر بعد تجاوز نافذته: يُحصى ولا يعود يلمس شيئًا (جمود §27)."""

    @staticmethod
    def _known_bar() -> tuple[FootprintBuilder, FootprintBar]:
        """دلو 02:00 معروف ثم عبور إلى 02:01 يقيده — يعيد البنّاء والمقفل."""
        builder = FootprintBuilder(timeframe="1m")
        builder.add_trade(_trade(T0 + timedelta(seconds=10), 100.0, 1.0, False))
        builder.add_trade(_trade(T0 + timedelta(seconds=20), 102.0, 2.0, True))
        closed = builder.add_trade(_trade(T0 + timedelta(minutes=1, seconds=5), 101.0, 1.0, False))
        assert closed is not None and closed.is_closed is True
        return builder, closed

    def test_late_after_rollover_counted_and_ignored(self) -> None:
        builder, closed = self._known_bar()
        late = builder.add_trade(_trade(T0 + timedelta(seconds=30), 500.0, 999.0, True))
        assert late is None
        assert builder.late_events == 1
        assert builder.n_closed == 1  # لم يزد القفل
        assert builder.n_evolved_updates == 1  # ولم يزد التحديث المتطور
        # المقفلة لم تتأثر: إعادة البناء بدون المتأخر ⇒ نفس الشريط بايت-ببايت
        clean = FootprintBuilder(timeframe="1m")
        clean.add_trade(_trade(T0 + timedelta(seconds=10), 100.0, 1.0, False))
        clean.add_trade(_trade(T0 + timedelta(seconds=20), 102.0, 2.0, True))
        clean_closed = clean.add_trade(
            _trade(T0 + timedelta(minutes=1, seconds=5), 101.0, 1.0, False)
        )
        assert clean_closed is not None
        assert clean_closed == closed  # عزل تام للمقفلة عن المتأخر

    def test_late_gap_bucket_creates_no_retroactive_bar(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        builder.add_trade(_trade(T0 + timedelta(seconds=5), 100.0, 1.0, False))
        closed = builder.add_trade(_trade(T0 + timedelta(minutes=3, seconds=5), 103.0, 1.0, False))
        assert closed is not None and closed.is_closed is True
        assert closed.bar_time == T0  # دلوا 02:01/02:02 فاضيان فلا شريط لهما
        # متأخر لدلو 02:01 الفائت (لا شريط له أصلًا ولا يُستحدث بأثر رجعي)
        late = builder.add_trade(_trade(T0 + timedelta(minutes=1, seconds=30), 90.0, 500.0, True))
        assert late is None
        assert builder.late_events == 1
        # المتطورة 02:03 لم تبتلع كمية المتأخر ولا سعره
        evolved = builder.add_trade(_trade(T0 + timedelta(minutes=3, seconds=6), 104.0, 2.0, False))
        assert evolved is not None
        assert evolved.total_volume == 3.0  # 1.0 + 2.0 فقط
        assert evolved.row_count == 2  # صفّا 103 و104 — صف 90.0 المتأخر غائب

    def test_event_for_explicitly_closed_bucket_is_late(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        builder.add_trade(_trade(T0 + timedelta(seconds=5), 100.0, 1.0, False))
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None and closed.is_closed is True
        # حدث لنفس الدلو المقفل صراحةً: متأخر — لا بعث ولا شريط مكرر
        duplicate = builder.add_trade(_trade(T0 + timedelta(seconds=50), 101.0, 1.0, True))
        assert duplicate is None
        assert builder.late_events == 1
        # الدلو اللاحق يبدأ شريطًا جديدًا نظيفًا
        fresh = builder.add_trade(_trade(T0 + timedelta(minutes=2, seconds=5), 102.0, 1.0, False))
        assert fresh is None  # بداية شريط جديد لا تُعاد (لا سابقة مفتوحة)
        assert builder.n_closed == 1  # لم يُقفل شيء جديد بعد
        evolved = builder.add_trade(_trade(T0 + timedelta(minutes=2, seconds=6), 102.5, 1.0, True))
        assert evolved is not None and evolved.total_volume == 2.0
        assert builder.last_bar_time == T0 + timedelta(minutes=2)


# ───────── المتطورة لا تفوّض (§27) ─────────


class TestDevelopingDoesNotDelegate:
    """كل إصدار وسيط is_closed=False؛ True فقط عند القفل (بأي مسار)."""

    def test_intermediate_emissions_never_closed(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=5), 100.0, 1.0, False)) is None
        for i in range(1, 6):
            out = builder.add_trade(
                _trade(T0 + timedelta(seconds=5 + i * 10), 100.0 + i, 1.0, True)
            )
            assert out is not None
            assert out.is_closed is False
        closed = builder.add_trade(_trade(T0 + timedelta(minutes=1, seconds=1), 90.0, 1.0, False))
        assert closed is not None and closed.is_closed is True
        explicit = builder.close_current(INSTRUMENT)
        assert explicit is not None and explicit.is_closed is True
        # الإقفال المزدوج: الثاني لا يجد متطورة
        assert builder.close_current(INSTRUMENT) is None
        assert builder.evolving(INSTRUMENT) is None


# ───────── تعدد المجاري (أداة × بنّاء) ─────────


class TestMultipleStreams:
    """مجراوان مستقلان يتشاركان البنّاء دون أي تسرب متبادل."""

    def test_streams_are_independent(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=5), 100.0, 1.0, False)) is None
        assert (
            builder.add_trade(
                _trade(
                    T0 + timedelta(seconds=6),
                    50.0,
                    10.0,
                    True,
                    symbol="ETHUSDT",
                )
            )
            is None
        )
        btc = builder.add_trade(_trade(T0 + timedelta(seconds=10), 101.0, 1.0, True))
        eth = builder.add_trade(
            _trade(T0 + timedelta(seconds=11), 51.0, 5.0, False, symbol="ETHUSDT")
        )
        assert btc is not None
        assert btc.instrument_id == INSTRUMENT
        assert btc.total_volume == 2.0
        assert eth is not None
        assert eth.instrument_id == "BINANCE_USDM:ETHUSDT"
        assert eth.total_volume == 15.0
        # عبور حد 1m يقفل BTC فقط — متطورة ETH لم تتأثر إطلاقًا
        btc_closed = builder.add_trade(
            _trade(T0 + timedelta(minutes=1, seconds=1), 100.5, 1.0, False)
        )
        assert btc_closed is not None and btc_closed.is_closed is True
        assert btc_closed.instrument_id == INSTRUMENT
        eth_still = builder.evolving("BINANCE_USDM:ETHUSDT")
        assert eth_still is not None and eth_still.total_volume == 15.0
        eth_closed = builder.close_current("BINANCE_USDM:ETHUSDT")
        assert eth_closed is not None and eth_closed.is_closed is True
        assert eth_closed.total_volume == 15.0
        # closed_bars_with_rows: الترتيب الحتمي (bar_time, instrument_id)
        bars_rows = builder.closed_bars_with_rows()
        assert [br.bar.instrument_id for br in bars_rows] == [
            INSTRUMENT,
            "BINANCE_USDM:ETHUSDT",
        ]
        assert [br.bar.bar_time for br in bars_rows] == [T0, T0]
        # إحصاءات البنّاء عبر المجرين معًا
        assert builder.n_closed == 2
        assert builder.n_evolved_updates == 2
        assert builder.late_events == 0

    def test_close_and_evolving_unknown_stream_return_none(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.close_current("UNKNOWN:XYZ") is None
        assert builder.evolving("UNKNOWN:XYZ") is None
        assert builder.closed_bars_with_rows() == ()
        builder.add_trade(_trade(T0, 100.0, 1.0, False))
        assert builder.close_current(INSTRUMENT) is not None
        # بعد الإقفال: لا متطورة للمقرأ ولا للإقفال الثاني
        assert builder.evolving(INSTRUMENT) is None
        assert builder.close_current(INSTRUMENT) is None


# ───────── تعارض التغذية (§12.7) ─────────


class TestFeedConflict:
    """source_feed آخر مغذٍ يفوز وكل تعارض يُعدّ — لا صمت أبدًا."""

    def test_last_feed_wins_and_conflicts_counted(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=1), 100.0, 1.0, False)) is None
        second = builder.add_trade(
            _trade(T0 + timedelta(seconds=2), 101.0, 1.0, True, feed_id="other.feed")
        )
        assert second is not None
        assert second.source_feed == "other.feed"
        assert builder.feed_id_conflicts == 1
        third = builder.add_trade(_trade(T0 + timedelta(seconds=3), 102.0, 1.0, False))
        assert third is not None
        assert third.source_feed == SOURCE_FEED  # الأخير فائز دومًا
        assert builder.feed_id_conflicts == 2
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.source_feed == SOURCE_FEED
        assert closed.methodology == METHODOLOGY_AGGTRADE_TAKER
        assert builder.feed_id_conflicts == 2  # الإقفال لا يضيف تعارضًا


# ───────── شريط متحنة الأحجام (اتفاقية موثقة) ─────────


class TestDegenerateZeroQuantity:
    """كميات صفرية قانونية: صفوف بلا حجم وحصص 0.0 ومنطقة قيمة منحلة."""

    def test_all_zero_quantities_bar(self) -> None:
        builder = FootprintBuilder(timeframe="1m")
        assert builder.add_trade(_trade(T0 + timedelta(seconds=1), 200.0, 0.0, False)) is None
        snapshot = builder.add_trade(_trade(T0 + timedelta(seconds=2), 100.0, 0.0, True))
        assert snapshot is not None and snapshot.is_closed is False
        assert snapshot.buy_volume == 0.0
        assert snapshot.sell_volume == 0.0
        assert snapshot.total_volume == 0.0
        assert snapshot.delta == 0.0
        assert snapshot.buy_share == 0.0  # اتفاقية 0/0 الموثقة
        assert snapshot.sell_share == 0.0
        assert snapshot.poc == 100.0  # تعذّر VWAP ⇒ الأدنى سعرًا
        assert snapshot.vah == 100.0  # هدف 70% من صفر يُبلغ فورًا
        assert snapshot.val == 100.0
        assert snapshot.row_count == 2  # كل سعر صفقة له صف ولو صفر الحجم
        assert snapshot.buy_imbalance_count == 0  # row_ratio: بلا مقارنة
        assert snapshot.sell_imbalance_count == 0
        assert snapshot.max_positive_delta_row is None
        assert snapshot.max_negative_delta_row is None
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.total_volume == 0.0
        assert [r.price for r in builder.closed_bars_with_rows()[0].rows] == [100.0, 200.0]


# ───────── الذهبي الحقيقي: عينة phase4 ضد klines المرجعية ─────────

REAL_INSTRUMENT = "binance-usdm-futures:BTCUSDT"  # venue:symbol من manifest

#: أثر حدود aggTrades الموثق: الصفقة المجمّعة عند 20:28:59.994 (كمية 2.734
#: بيعية عند 84591.6) امتدت تعبئاتها الفردية عبر حد 20:29:00.000 — محرك
#: klines لدى البورصة قاس 0.150 من كميتها في شمعة 20:29 بينما aggTrades
#: يحمل التجميعة كلها بطابع 20:28:59.994. التجميعة الواحدة غير قابلة
#: للشطر من مصدرنا (حد مصدر معلوم §6.2) — فمرجع taker_buy (الشراء
#: المتسبب) مطابق حرفيًا في الدلوين معًا، وحمل الأثر البيعي وحده.
#: الدلتان ثابتتان في العينة المقيدة بالهاش في manifest.json.
_BOUNDARY_TOTAL_DELTA: dict[int, float] = {
    1790540880000: 0.15,  # دلو 20:28 — كيّنا أكثر من الشمعة بمقدار الأثر
    1790540940000: -0.15,  # دلو 20:29 — والشمعة أكثر منّا بنفس المقدار
}


@lru_cache(maxsize=1)
def _real_sample() -> tuple[list[TradeEvent], tuple[dict[str, Any], ...], dict[str, Any]]:
    """تحميل عينة phase4 مرة واحدة: الصفقات + الشموع المرجعية + البيان."""
    events = read_parquet_bytes((FIXTURE_DIR / "trades.parquet").read_bytes())
    klines = json.loads((FIXTURE_DIR / "klines.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    return events, tuple(klines), manifest


def _build_real() -> FootprintBuilder:
    """بناء كامل للعينة على إطار 1m: العبور يقفل والدلو الأخير إقفالًا صريحًا."""
    events, _, _ = _real_sample()
    builder = FootprintBuilder(timeframe="1m")
    for event in events:
        builder.add_trade(event)
    # آخر دلو في العينة بلا خَلَف يعبُر الحد — الإقفال الصريح وحده يكمله
    builder.close_current(REAL_INSTRUMENT)
    return builder


@lru_cache(maxsize=1)
def _real_builder() -> FootprintBuilder:
    """الباني المبني مرة واحدة (كاش مستوى الوحدة) للمقارنات المتكررة."""
    return _build_real()


@lru_cache(maxsize=1)
def _real_closed_by_time() -> dict[datetime, BarRows]:
    """الأشرطة المقفلة مفهرسة بطابع دلوها — مدخل البارامترات الـ120."""
    return {br.bar.bar_time: br for br in _real_builder().closed_bars_with_rows()}


class TestGoldenReal:
    """المطابقة الإحصائية الدلو-بالدلو ضد مرجع البورصة (بوابة المرحلة 4)."""

    def test_real_sample_builder_sanity(self) -> None:
        """صحة العينة والبناء الكامل قبل المقارنات المفصلة."""
        events, klines, manifest = _real_sample()
        builder = _real_builder()
        assert len(events) == manifest["event_count"] == 35_932
        assert len(klines) == manifest["kline_count"] == 120
        assert f"{manifest['venue']}:{manifest['symbol']}" == REAL_INSTRUMENT
        # كل دلو مكتمل غير فارغ: 120 شريطًا (119 بعبور الحد + الأخير صريح)
        assert builder.n_closed == 120
        assert builder.late_events == 0  # العينة مرتبة زمنيًا (عقد raw_store)
        assert builder.n_evolved_updates == len(events) - 120
        assert builder.feed_id_conflicts == 0  # مصدر واحد للعينة كلها
        # حدود النافذة على حدود الدلاء المحاذية
        first_ms = klines[0]["open_time_ms"]
        last_ms = klines[-1]["open_time_ms"]
        assert builder.first_bar_time == datetime.fromtimestamp(first_ms / 1000, tz=UTC)
        assert builder.last_bar_time == datetime.fromtimestamp(last_ms / 1000, tz=UTC)
        # إثبات 4-a نفسه على مستوى النافذة: مجموع الشراء المتسبب == المرجع
        total_buy = sum(br.bar.buy_volume for br in builder.closed_bars_with_rows())
        assert total_buy == pytest.approx(manifest["taker_buy_volume_sum"], abs=1e-6)

    @pytest.mark.parametrize(
        "kline",
        _real_sample()[1],
        ids=lambda k: str(k["open_time_ms"]),
    )
    def test_bucket_matches_kline_reference(self, kline: dict[str, Any]) -> None:
        """دلو مكتمل ⇒ buy == taker_buy وtotal/sell == volume (± دلتا الحدود)."""
        bar_time = datetime.fromtimestamp(kline["open_time_ms"] / 1000, tz=UTC)
        br = _real_closed_by_time()[bar_time]
        bar = br.bar
        taker_buy = float(kline["taker_buy_volume"])
        volume = float(kline["volume"])
        boundary = _BOUNDARY_TOTAL_DELTA.get(int(kline["open_time_ms"]), 0.0)
        # المرجع الذهبي للشراء العدواني (§12.7): مطابقة تامة في كل دلو —
        # حتى دلوا الأثر الحدودي (أثره بيعي فحسب)
        assert bar.buy_volume == pytest.approx(taker_buy, rel=1e-9, abs=1e-9)
        assert bar.total_volume == pytest.approx(volume + boundary, rel=1e-9, abs=1e-9)
        assert bar.sell_volume == pytest.approx(volume + boundary - taker_buy, rel=1e-9, abs=1e-9)
        # الوسم القانوني للشريط (§12.7)
        assert bar.is_closed is True
        assert bar.instrument_id == REAL_INSTRUMENT
        assert bar.timeframe == "1m"
        assert bar.methodology == METHODOLOGY_AGGTRADE_TAKER
        assert bar.source_feed == _real_sample()[2]["feed_id"]
        # اتساق داخلي: الشريط == صفوفه (مجاميع وحصص وترتيب وعدادات)
        rows = br.rows
        assert bar.row_count == len(rows)
        assert [r.price for r in rows] == sorted(r.price for r in rows)
        assert sum(r.buy_volume for r in rows) == pytest.approx(bar.buy_volume, abs=1e-9)
        assert sum(r.sell_volume for r in rows) == pytest.approx(bar.sell_volume, abs=1e-9)
        assert sum(r.total_volume for r in rows) == pytest.approx(bar.total_volume, abs=1e-9)
        assert bar.delta == pytest.approx(bar.buy_volume - bar.sell_volume, abs=1e-9)
        assert bar.buy_share + bar.sell_share == pytest.approx(1.0, abs=1e-9)
        assert bar.val <= bar.poc <= bar.vah
        # العدادات = إعادة اشتقاق مباشرة بعقد rows.py
        assert bar.buy_imbalance_count == sum(
            1 for r in rows if row_imbalance_side(r.buy_volume, r.sell_volume) is ImbalanceSide.BUY
        )
        assert bar.sell_imbalance_count == sum(
            1 for r in rows if row_imbalance_side(r.buy_volume, r.sell_volume) is ImbalanceSide.SELL
        )

    def test_boundary_artifact_is_confined_to_documented_buckets(self) -> None:
        """أثر الحدود محصور بالدلوين الموثقين — 118 دلوًا مطابقًا تمامًا."""
        _, klines, _ = _real_sample()
        assert len(_BOUNDARY_TOTAL_DELTA) == 2
        non_boundary = [k for k in klines if int(k["open_time_ms"]) not in _BOUNDARY_TOTAL_DELTA]
        assert len(non_boundary) == 118
        by_time = _real_closed_by_time()
        for kline in non_boundary:
            bar_time = datetime.fromtimestamp(kline["open_time_ms"] / 1000, tz=UTC)
            bar = by_time[bar_time].bar
            assert bar.total_volume == pytest.approx(float(kline["volume"]), rel=1e-9, abs=1e-9)


# ───────── الحتمية ─────────


class TestDeterminism:
    """نفس القائمة مرتين ⇒ نفس هاش sha256 للترميز JSON الكامل للمقفل."""

    def test_real_sample_replays_identically(self) -> None:
        builder_a = _real_builder()
        builder_b = _build_real()
        assert _builder_digest(builder_a) == _builder_digest(builder_b)
        # والإحصاءات كذلك: لا حالة خفية تفرق التشغيلين
        assert (builder_a.n_closed, builder_a.n_evolved_updates, builder_a.late_events) == (
            builder_b.n_closed,
            builder_b.n_evolved_updates,
            builder_b.late_events,
        )
        assert builder_a.feed_id_conflicts == builder_b.feed_id_conflicts


# ───────── اللا-نظرة-المستقبلية (§26.3) ─────────


class TestNoLookahead:
    """إقفال الدلو k بالعبور == إقفاله الصريح قبل أي حدث لاحق — بايت-ببايت."""

    def test_rollover_close_equals_explicit_close_bytes(self) -> None:
        prefix = [_trade(*_to_args(t)) for t in _BAR1_TRADES]
        future = _trade(*_to_args(_BAR2_TRADES[0]))  # أول حدث الدلو التالي

        # مسار 1: توقف عند نهاية الدلو (نهاية بث مفترضة ⇒ إقفال صريح)
        stopped = FootprintBuilder(timeframe="1m")
        stopped_outputs = [_dump(stopped.add_trade(e)) for e in prefix]
        stopped_closed = stopped.close_current(INSTRUMENT)
        assert stopped_closed is not None

        # مسار 2: نفس البادئة ثم أول حدث الدلو التالي (يعبر الحد)
        continued = FootprintBuilder(timeframe="1m")
        continued_outputs = [_dump(continued.add_trade(e)) for e in prefix]
        assert continued_outputs == stopped_outputs  # نفس المدخلات حتى t
        rolled = continued.add_trade(future)
        assert rolled is not None
        # الإقفال بعبور t+1 == الإقفال الصريح عند t: الحدث المستقبلي لم
        # يساهم في شريط الدلو السابق بشيء — بايت-ببايت
        assert _dump(rolled) == _dump(stopped_closed)
        # والصفوف كذلك: جمود المقفل بكل تفاصيله
        assert stopped.closed_bars_with_rows() == continued.closed_bars_with_rows()
        # t+1 أسهم في شريطه هو وحده (دلو 02:01)
        future_bar = continued.close_current(INSTRUMENT)
        assert future_bar is not None
        assert future_bar.bar_time == T0 + timedelta(minutes=1)
        assert future_bar.total_volume == 6.0  # صفقة الترجيح وحدها

    @given(
        prefix=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=59),
                st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
                st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
                st.booleans(),
            ),
            min_size=1,
            max_size=24,
        ),
        future=st.tuples(
            st.integers(min_value=0, max_value=59),
            st.floats(min_value=90.0, max_value=110.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            st.booleans(),
        ),
    )
    @hyp_settings(max_examples=50, deadline=None, derandomize=True)
    def test_outputs_up_to_t_independent_of_future(
        self,
        prefix: list[tuple[int, float, float, bool]],
        future: tuple[int, float, float, bool],
    ) -> None:
        """خاصية §26.3: مخرجات البادئة لا تتغير بإدراج حدث t+1 بعدها."""
        prefix_events = [
            _trade(T0 + timedelta(seconds=sec), price, qty, bim) for sec, price, qty, bim in prefix
        ]
        sec, price, qty, bim = future
        future_event = _trade(T0 + timedelta(minutes=1, seconds=sec), price, qty, bim)

        stopped = FootprintBuilder(timeframe="1m")
        stopped_outputs = [_dump(stopped.add_trade(e)) for e in prefix_events]
        stopped_closed = stopped.close_current(INSTRUMENT)
        assert stopped_closed is not None

        continued = FootprintBuilder(timeframe="1m")
        continued_outputs = [_dump(continued.add_trade(e)) for e in prefix_events]
        assert continued_outputs == stopped_outputs  # حتمية عبر النسختين
        rolled = continued.add_trade(future_event)
        assert rolled is not None
        assert _dump(rolled) == _dump(stopped_closed)


# ───────── الخصائص (hypothesis — derandomize) ─────────


class TestSingleBucketProperties:
    """تسلسل عشوائي داخل دلو واحد ⇒ كل عقود §8.2 الداخلية متسقة."""

    @given(
        start_seconds=st.integers(min_value=0, max_value=200 * 86400),
        trades=st.lists(
            st.tuples(
                st.floats(min_value=0.5, max_value=5000.0, allow_nan=False, allow_infinity=False),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=59_999_999),
                st.booleans(),
            ),
            min_size=1,
            max_size=40,
        ),
    )
    @hyp_settings(max_examples=75, deadline=None, derandomize=True)
    def test_single_bucket_invariants(
        self,
        start_seconds: int,
        trades: list[tuple[float, float, int, bool]],
    ) -> None:
        # نقطة انطلاق عشوائية محاذة لحد الدقيقة (عدسة مستقلة عن bucket_floor)
        rough = datetime(2025, 6, 1, tzinfo=UTC) + timedelta(seconds=start_seconds)
        base = rough.replace(second=0, microsecond=0)
        builder = FootprintBuilder(timeframe="1m")
        evolving_seen: list[FootprintBar] = []
        for price, qty, offset_us, bim in trades:
            when = base + timedelta(microseconds=offset_us % 60_000_000)
            emitted = builder.add_trade(_trade(when, price, qty, bim))
            if emitted is not None:
                evolving_seen.append(emitted)
        # كل ما صدر داخل الدلو متطور لا يفوّض (§27)
        assert all(b.is_closed is False for b in evolving_seen)
        closed = builder.close_current(INSTRUMENT)
        assert closed is not None
        assert closed.is_closed is True
        assert closed.bar_time == base
        assert closed.instrument_id == INSTRUMENT
        assert closed.timeframe == "1m"
        assert closed.methodology == METHODOLOGY_AGGTRADE_TAKER
        rows = builder.closed_bars_with_rows()[0].rows

        # الشريط == صفوفه: مجاميع وعدادات (النموذج يضمن عدم السالبية)
        total = closed.total_volume
        assert closed.row_count == len(rows)
        assert closed.buy_volume == pytest.approx(sum(r.buy_volume for r in rows), abs=1e-9)
        assert closed.sell_volume == pytest.approx(sum(r.sell_volume for r in rows), abs=1e-9)
        assert closed.total_volume == pytest.approx(sum(r.total_volume for r in rows), abs=1e-9)
        # الحصص تسجم 1 داخل الفاصل [0,1] (والمتحنة 0.0 اتفاقية)
        assert 0.0 <= closed.buy_share <= 1.0
        assert 0.0 <= closed.sell_share <= 1.0
        if total > 0.0:
            assert closed.buy_share + closed.sell_share == pytest.approx(1.0, abs=1e-12)
            assert abs(closed.delta) <= total + 1e-9
        else:
            assert closed.buy_share == 0.0
            assert closed.sell_share == 0.0
        # الصفوف مرتبة تصاعديًا حصرًا (عقد rows.py)
        assert [r.price for r in rows] == sorted(r.price for r in rows)
        # منطقة القيمة وPOC: حدود مرتبة وPOC داخلها وصفه ذو الحجم الأقصى
        assert closed.vah >= closed.val
        assert closed.val <= closed.poc <= closed.vah
        max_row_total = max(r.total_volume for r in rows)
        poc_row = next(r for r in rows if r.price == closed.poc)
        assert poc_row.total_volume == max_row_total
        # العدادات = إعادة اشتقاق مباشرة بعقد rows.py (النسبة الافتراضية)
        assert closed.buy_imbalance_count == sum(
            1 for r in rows if row_imbalance_side(r.buy_volume, r.sell_volume) is ImbalanceSide.BUY
        )
        assert closed.sell_imbalance_count == sum(
            1 for r in rows if row_imbalance_side(r.buy_volume, r.sell_volume) is ImbalanceSide.SELL
        )
        # دلتا الصف القصوى: السعر الموثق هو ذو القيمة القصوى فعلًا (أو None)
        pos_deltas = [r.delta for r in rows if r.delta > 0.0]
        if pos_deltas:
            assert closed.max_positive_delta_row is not None
            chosen = next(r for r in rows if r.price == closed.max_positive_delta_row)
            assert chosen.delta == max(pos_deltas)
        else:
            assert closed.max_positive_delta_row is None
        neg_deltas = [r.delta for r in rows if r.delta < 0.0]
        if neg_deltas:
            assert closed.max_negative_delta_row is not None
            chosen = next(r for r in rows if r.price == closed.max_negative_delta_row)
            assert chosen.delta == min(neg_deltas)
        else:
            assert closed.max_negative_delta_row is None
        # الإحصاءات
        assert builder.n_closed == 1
        assert builder.n_evolved_updates == len(trades) - 1
        assert builder.late_events == 0
        assert builder.first_bar_time == base
        assert builder.last_bar_time == base


# ───────── ثابت المنهجية الموثق ─────────


def test_value_area_fraction_is_the_documented_70_percent() -> None:
    """VALUE_AREA_FRACTION = 0.70 (§12.5) — ثابت المنهجية الموثق."""
    assert VALUE_AREA_FRACTION == 0.70
