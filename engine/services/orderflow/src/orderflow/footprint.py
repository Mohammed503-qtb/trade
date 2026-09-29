"""بنّاء الفوتبرنت الحدثي من aggTrades — التجميع الصفّي بمنهجية الطرف
المتسبب (§8.2 + §12 + §27 + §26.3 — المهمة 4-b من خطة البناء).

الموضع في المسار: يستهلك صفقات منقّحة (``schemas.TradeEvent`` من aggTrades
أو ما يعادلها) وينتج أشرطة ``schemas.FootprintBar`` لكل (instrument_id,
timeframe) على حدة — نظير «candle aggregator» في §33.1 لكن للتدفق الصفّي.

صرفية البنّاء: لا شبكة ولا قواعد بيانات ولا I/O — منطق sync خالص قابل
للاختبار الحتمي، بلا أي نظرة مستقبلية (§26.3): كل قيمة تُشتق فقط من
أحداث وصلت فعلًا حتى اللحظة الجارية (نفس المدخلات حتى t ⇒ نفس المخرجات
حتى لو توفر t+1).

منهجية التصنيف (§12.7 + عقد ``rows.py``):
- **الشراء العدواني** = صفقة ``buyer_is_maker=False`` (المشتري متسبب)
  و**البيع العدواني** = ``buyer_is_maker=True`` (البائع متسبب) — كل صفقة
  تتراكم في صف سعرها ``FootprintRow(price, buy_volume, sell_volume)``.
- ``methodology = METHODOLOGY_AGGTRADE_TAKER`` في كل شريط — الشطر مؤسسي
  موسوم بالمصدر، ولا يُفترض أبدًا أنه «كل مشتريي السوق مقابل كل بائعيه».
- حدث ``buyer_is_maker=None`` (مصدر بلا علم) **يُرفض صراحة** بـValueError
  قبل أي أثر جانبي: منهجية aggtrades-taker-side تتطلب العلم، ومصدر خارج
  المنهجية لا يُجمَّع بصمت (الصخب في التحقق) — والرفض يسبق التصنيف
  الزمني (يُرفض حتى لو كان حدثًا متأخرًا فلا يُحصى في ``late_events``).

دلالات المتطور/المقفل (§27 — نفس عقد ``CandleBuilder`` حرفيًا):
- كل إصدار داخل الدلو الجاري ``is_closed=False`` (نسخة متطورة كاملة
  المقاييس قد تتغير — لا تفوّض قرارًا حيًا)، والإقفال وحده
  ``is_closed=True`` بقيم نهائية جمودها أبدي.
- المقفل لا يُعدّل أبدًا: الأحداث المتأخرة بعد تجاوز نافذتها تُحصى في
  ``late_events`` ولا تمس المقفلة ولا تنشئ شريطًا فائتًا بأثر رجعي.

الإطار الصريح (قرار 1.6 نفسه): ``FootprintBuilder(timeframe="1m")`` يبني
الفوتبرنت بإطاره هو من أحداث tick — الدلو يُحسب بزمن الحدث على إطار
البادئ لا على ``event.source_timeframe`` (يبقى محفوظًا في الحدث ذاته)،
ومفتاح المجرى ``instrument_id = f"{venue}:{symbol}"`` (نفس اصطلاح
candles.py) — الإطار ثابت للبنّاء كله فمفتاح المجرى هو الأداة وحدها.

الخوارزميات الحتمية الموثقة (تُختبر حرفيًا في tests/unit/test_footprint.py):

- **POC (§12.5)**: سعر الصف ذي الحجم الكلي الأقصى. عند تعادل عدة صفوف:
  الأقرب إلى المتوسط المرجح بالحجم (VWAP = Σ(سعر×حجم الصف)/Σالحجم)؛
  وعند تساوي البعد (أو تعذّر VWAP في شريط متحنة الأحجام — أدناه):
  الأدنى سعرًا — سلسلة حتمية واحدة لا تتفرع.

- **منطقة القيمة 70% (§12.5)** — التوسّع بثنائيات الصفوف:
  1. التغطية تبدأ من صف POC وحده والحجم المغطى حجمه الكلي.
  2. ما دام الحجم المغطى < ``VALUE_AREA_FRACTION`` من الحجم الكلي
     وتوجد صفوف غير مغطاة: تُقارن **الثنائية العليا** (أقرب صفين غير
     مغطيين فوق VAH الجاري — أو صف واحد إن لم يبق عند الحافة إلا هو)
     مع **الثنائية الدنيا** (بالمراسلة تحت VAL الجاري) بحجمهما الكلي.
  3. تُضمّ الثنائية ذات الحجم الأكبر (صفّاها معًا) إلى التغطية.
  4. عند التساوي: تُفضَّل الجهة المضادة لميل POC داخل النطاق المغطى —
     POC أعلى من منتصف النطاق المغطى ⇒ الثنائية الدنيا، وأدنى منه ⇒
     العليا، وتساوٍ تام مع المنتصف ⇒ العليا (ثابت حتمي موثق) — توسيع
     أوسع نحو الجهة الأخف توازنًا.
  5. عند استنفاد جهة (لا صفوف فوق/تحت): الجهة الأخرى تتوسع وحدها؛
     والتوقف عند بلوغ الحصة (التجاوز بثنائية كاملة جائز).
  6. ``vah`` أعلى سعر مغطى و``val`` أدناه عند التوقف.

- **max_positive_delta_row / max_negative_delta_row**: سعر الصف ذي أقصى
  دلتا موجبة (buy−sell) / أدنى دلتا سالبة؛ ``None`` إن لا دلتا من
  جنسه في الشريط؛ عند تعادل القيمة القصوى: الأدنى سعرًا (الأول بالترتيب
  التصاعدي).

- **عدادات الاختلال (§12.6)**: تطبيق مباشر لعقد ``rows.py`` —
  ``row_imbalance_side(buy, sell)`` بنسبة البنّاء الإعدادية
  (``imbalance_ratio``، افتراضها ``IMBALANCE_RATIO`` = 3:1 الكلاسيكي).
  المقارنة الصفّية المباشرة عند السعر ذاته (لا القطرية) — عقد مستقر
  موثق في رأس ``rows.py``.

اتفاقيات الحواف الموثقة (تُختبر حرفيًا):
- **الدلو الفارغ لا يُبنى أصلًا** (لا شريط بلا صفقات — كما في الشموع؛
  الفجوات الزمنية تتخطى ولا تُسدّ)؛ وكل سعر صفقة له صف في الشريط ولو
  كانت كميته صفرًا (``row_count`` يعدّه) — ``row_ratio`` تعامله بلا
  مقارنة (عقد rows.py).
- **شريط متحنة الأحجام** (كميات كل أحداثه صفر — قانونية بحدود النموذج):
  ``buy_share = sell_share = 0.0`` اتفاقية موثقة (0/0 غير معرفة)،
  والدلتا 0، وVWAP يتعذر فPOC = أدنى سعر، ومنطقة القيمة تنحل في POC
  وحده (هدف 70% من صفر يُبلغ فورًا) فـ``vah = val = poc``.
- **الجودة**: «أسوأ جودة الأحداث داخل الدلو» وفق ``QUALITY_SEVERITY_LADDER``
  المستورد من ``ingestion.candles`` (نفس عقد الشموع 1.4 — تعريف واحد
  للشدة عبر الشموع والفوتبرنت) — التراكم لا يتراجع.
- **source_feed**: ``feed_id`` آخر حدث غذّى الدلو («الأخير يفوز» — الشريط
  يوثق آخر مصدر غذاه)؛ أي تعارض داخل الدلو يُعدّ في ``feed_id_conflicts``
  الكلي عبر البنّاء (لا حقل قانونيًا له في ``FootprintBar`` §8.2 المغلق).

الصفوف المقفلة تُحفظ كلها عبر :meth:`closed_bars_with_rows` — مدخل
الكواشف الصفّية (4-c) بعقد ``BarRows``؛ النمو مستمر مع الأشرطة المقفلة،
وحد الاحتفاظ سياسة مستوى العامل/التخزين لاحقًا (§8.2: لا تخزين صفوف غير
محدود «لأجل التصور» — هنا الحفظ لأجل الكواشف لا التصور، والتقادم مسؤولية
الطبقة الأعلى).
"""

from __future__ import annotations

from bisect import bisect_left, insort
from dataclasses import dataclass, field
from datetime import datetime

from ingestion.candles import (
    QUALITY_SEVERITY_LADDER,
    SUPPORTED_TIMEFRAMES,
    bucket_floor,
)
from schemas import DataQuality, FootprintBar, ImbalanceSide, TradeEvent

from orderflow.rows import (
    IMBALANCE_RATIO,
    METHODOLOGY_AGGTRADE_TAKER,
    BarRows,
    FootprintRow,
    row_imbalance_side,
)

__all__ = [
    "VALUE_AREA_FRACTION",
    "FootprintBuilder",
]

#: حصة منطقة القيمة من الحجم الكلي (§12.5) — «70%» المنهجية الموثقة.
#: ثابت منهجي لا معامل إعدادي: كل شريط مشتق من نفس التعريف فتظل
#: القيم قابلة للمقارنة بين الأشرطة والأدوات والأزمنة.
VALUE_AREA_FRACTION: float = 0.70

# سلّل شدة الجودة — عقد المهمة 1.4 نفسه (مستورد من بنّاء الشموع).
_SEVERITY: dict[DataQuality, int] = {q: i for i, q in enumerate(QUALITY_SEVERITY_LADDER)}


def _worse(a: DataQuality, b: DataQuality) -> DataQuality:
    """أسوأ الجودتين وفق سلّل الشدة — دمج تراكمي داخل الدلو لا يتراجع."""
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


# ───────────────────────── الحالة الداخلية ─────────────────────────


@dataclass(frozen=True)
class _Metrics:
    """مقاييس §8.2 الكاملة لشريط واحد — مشتقة صرفة من الصفوف عند كل إصدار."""

    buy_volume: float
    sell_volume: float
    total_volume: float
    delta: float
    buy_share: float
    sell_share: float
    poc: float
    vah: float
    val: float
    row_count: int
    buy_imbalance_count: int
    sell_imbalance_count: int
    max_positive_delta_row: float | None
    max_negative_delta_row: float | None


@dataclass
class _EvolvingBar:
    """حالة الشريط المتطور الجارية (خاصة بالوحدة — لا تُصدَّر).

    ``prices`` قائمة الأسعار مرتبة تصاعديًا حصرًا (تُدرج بـ``insort`` عند
    أول صفقة عند سعر جديد — عقد ``rows.py``)؛ و``volumes`` خريطة السعر →
    ``[buy, sell]`` التراكميَّين بعدوانية الطرف المتسبب.
    """

    bar_time: datetime
    prices: list[float] = field(default_factory=list)
    volumes: dict[float, list[float]] = field(default_factory=dict)
    quality: DataQuality = DataQuality.HEALTHY
    source_feed: str = ""


@dataclass
class _StreamState:
    """حالة مجرى أداة واحدة (الإطار ثابت للبنّاء كله فالمفتاح الأداة).

    ``last_closed_bar_time`` تحرس حدود القفل: أي حدث لدلو مساوٍ أو أقدم
    منها متأخر لا يلمس المقفلة ولا ينشئ فائتة؛ و``closed`` الأشرطة
    المقفلة بصفوفها (``closed_bars_with_rows``) بترتيب الإقفال.
    """

    evolving: _EvolvingBar | None = None
    last_closed_bar_time: datetime | None = None
    closed: list[BarRows] = field(default_factory=list)


# ───────────────────────── اشتقاق المقاييس ─────────────────────────


def _pair_volume(
    prices: list[float],
    volumes: dict[float, list[float]],
    start: int,
    stop: int,
) -> float:
    """الحجم الكلي لشريحة الصفوف ``prices[start:stop]`` (ثنائية التوسّع)."""
    total = 0.0
    for price in prices[start:stop]:
        cell = volumes[price]
        total += cell[0] + cell[1]
    return total


def _value_area_bounds(
    prices: list[float],
    volumes: dict[float, list[float]],
    poc: float,
    poc_total: float,
    total_volume: float,
) -> tuple[float, float]:
    """حدّا منطقة القيمة ``(vah, val)`` — خوارزمية الثنائيات الموثقة.

    التوسّع من POC بثنائيات الصفوف (زوج أعلى مقابل زوج أدنى) مختارًا
    الأكبر حجمًا حتى بلوغ حصة ``VALUE_AREA_FRACTION`` من الحجم الكلي؛
    قاعدة التعادل والجهة المنفدة والحتمية كلها في رأس الوحدة.
    """
    n = len(prices)
    lo = hi = bisect_left(prices, poc)
    covered = poc_total
    target = VALUE_AREA_FRACTION * total_volume
    while covered < target and (lo > 0 or hi < n - 1):
        up_to = min(hi + 3, n)
        dn_from = max(lo - 2, 0)
        # −1.0 حارس جهة منفدة (الأحجام غير سالبة أصلًا بحدود النموذج)
        up_vol = _pair_volume(prices, volumes, hi + 1, up_to) if hi < n - 1 else -1.0
        dn_vol = _pair_volume(prices, volumes, dn_from, lo) if lo > 0 else -1.0
        if dn_vol < 0.0:
            take_up = True  # الدنيا منفدة ⇒ العليا وحدها
        elif up_vol < 0.0:
            take_up = False
        elif up_vol > dn_vol:
            take_up = True
        elif dn_vol > up_vol:
            take_up = False
        else:
            # تعادل الثنائيتين: الجهة المضادة لميل POC داخل النطاق المغطى
            midpoint = (prices[lo] + prices[hi]) / 2.0
            take_up = poc <= midpoint
        if take_up:
            covered += up_vol
            hi = up_to - 1
        else:
            covered += dn_vol
            lo = dn_from
    return prices[hi], prices[lo]


def _compute_metrics(bar: _EvolvingBar, *, imbalance_ratio: float) -> _Metrics:
    """اشتقاق مقاييس §8.2 كاملة من صفوف الشريط — دالة صرفة حتمية.

    تمريرة واحدة على الصفوف بالترتيب التصاعدي ثم توسّع منطقة القيمة؛
    كل القواعد الحتمية (POC/VA/الاختلال/الدلتا القصوى) موثقة في رأس
    الوحدة. الشريط له صف واحد على الأقل دائمًا (لا شريط بلا صفقات).
    """
    prices = bar.prices
    volumes = bar.volumes
    buy_volume = 0.0
    sell_volume = 0.0
    vwap_num = 0.0
    max_total = -1.0
    poc_candidates: list[float] = []
    buy_imbalance_count = 0
    sell_imbalance_count = 0
    max_pos_delta = 0.0
    max_pos_price: float | None = None
    max_neg_delta = 0.0
    max_neg_price: float | None = None
    for price in prices:
        cell = volumes[price]
        buy, sell = cell[0], cell[1]
        buy_volume += buy
        sell_volume += sell
        row_total = buy + sell
        vwap_num += price * row_total
        if row_total > max_total:
            max_total = row_total
            poc_candidates = [price]
        elif row_total == max_total:
            poc_candidates.append(price)
        side = row_imbalance_side(buy, sell, imbalance_ratio)
        if side is ImbalanceSide.BUY:
            buy_imbalance_count += 1
        elif side is ImbalanceSide.SELL:
            sell_imbalance_count += 1
        row_delta = buy - sell
        # التعادل في القيمة القصوى ⇒ الأدنى سعرًا (الأول تصاعديًا) يفوز
        if row_delta > 0.0 and row_delta > max_pos_delta:
            max_pos_delta = row_delta
            max_pos_price = price
        elif row_delta < 0.0 and row_delta < max_neg_delta:
            max_neg_delta = row_delta
            max_neg_price = price
    total_volume = buy_volume + sell_volume
    if total_volume > 0.0:
        vwap = vwap_num / total_volume
        poc = min(poc_candidates, key=lambda p: (abs(p - vwap), p))
        buy_share = buy_volume / total_volume
        sell_share = sell_volume / total_volume
    else:
        # شريط متحنة الأحجام: اتفاقيات موثقة في رأس الوحدة
        poc = min(poc_candidates)
        buy_share = 0.0
        sell_share = 0.0
    vah, val = _value_area_bounds(prices, volumes, poc, max_total, total_volume)
    return _Metrics(
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        total_volume=total_volume,
        delta=buy_volume - sell_volume,
        buy_share=buy_share,
        sell_share=sell_share,
        poc=poc,
        vah=vah,
        val=val,
        row_count=len(prices),
        buy_imbalance_count=buy_imbalance_count,
        sell_imbalance_count=sell_imbalance_count,
        max_positive_delta_row=max_pos_price,
        max_negative_delta_row=max_neg_price,
    )


# ───────────────────────── البنّاء ─────────────────────────


class FootprintBuilder:
    """بنّاء أشرطة فوتبرنت حدثي صرف لكل (instrument_id, timeframe).

    الإطار الزمني **إلزامي صريح** من البادئ (قرار 1.6: الإطار من البادئة
    لا من الحدث — أحداث aggTrades مصدرها "1t" tick فلا يُشتق منها إطار
    زمني أصلًا)؛ و``imbalance_ratio`` معامل إعدادي معلن (ليس توصية) على
    عقد ``rows.py``.

    عقد الإرجاع لـ``add_trade`` (نفس دلالات ``CandleBuilder`` §27):
    - ``None``: أول حدث في مجرى جديد (لا سابقة تُقفل)، أو حدث متأخر
      (دلو أقدم من المتطورة الجارية أو مساوٍ/أقدم من آخر دلو مقفل) —
      المتأخر يُحصى في ``late_events`` ولا صمت أبدًا ولا تعديل للمقفلة
      ولا إنشاء شريط فائت بأثر رجعي.
    - ``FootprintBar(is_closed=True)``: الشريط السابق عند أول حدث يعبر
      حدّ دلو جديد — بقيمه النهائية، جموده نهائي.
    - ``FootprintBar(is_closed=False)``: نسخة المتطورة الحالية بعد تراكم
      الحدث (كاملة مقاييس §8.2) — المستهلك حر في تجاهلها؛ المتطورة لا
      تفوّض قرارًا حيًا.

    ``close_current`` إقفال صريح للمتطورة الجارية (نهاية البث) — لا يغيّر
    قيمة (نهائية منذ آخر حدث) بل يقلب ``is_closed`` ويثبّت حدود القفل.
    ``evolving`` قراءة حية للمتطورة (لا تعدّ في ``n_evolved_updates``).
    ``closed_bars`` كل الأشرطة المقفلة وحدها، و``closed_bars_with_rows``
    كل المقفل مع صفوفه — كلاهما بترتيب حتمي ``(bar_time, instrument_id)``
    (مدخل الكواشف 4-c هو الثاني: الصفوف لا تُستعار من مقاييس الشريط).

    الإحصاءات (``n_closed``/``n_evolved_updates``/``late_events``/
    ``first_bar_time``/``last_bar_time``/``feed_id_conflicts``) عبر كل
    مجاري البنّاء كافة. البنّاء غير محصّن ضد التزامن — يُستهلك من مهمة
    واحدة ضامنة الحتمية.
    """

    def __init__(self, *, timeframe: str, imbalance_ratio: float = IMBALANCE_RATIO) -> None:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"إطار الإخراج الصريح غير مدعوم: {timeframe!r} — "
                f"المدعوم: {sorted(SUPPORTED_TIMEFRAMES)}"
            )
        if not (imbalance_ratio > 1.0 and imbalance_ratio < float("inf")):
            raise ValueError(f"حد نسبة الاختلال الصفّي غير صالح: {imbalance_ratio} (المتوقع > 1.0)")
        self._timeframe = timeframe
        self._imbalance_ratio = imbalance_ratio
        self._streams: dict[str, _StreamState] = {}
        self._n_closed = 0
        self._n_evolved_updates = 0
        self._late_events = 0
        self._feed_id_conflicts = 0
        self._first_bar_time: datetime | None = None
        self._last_bar_time: datetime | None = None

    # ───────── عقد الاستهلاك ─────────

    def add_trade(
        self, event: TradeEvent, quality: DataQuality = DataQuality.HEALTHY
    ) -> FootprintBar | None:
        """إدخال صفقة واحدة وإرجاع أثرها وفق سياسة عدم إعادة الرسم (§27).

        مرجع الدلو ``event.event_time_utc`` على إطار البنّاء الصريح (لا زمن
        الوصول أبدًا)؛ والتراكم داخل الدلو الحالي صفّي: كمية الصفقة تضاف
        إلى صف سعرها بمنهجية الطرف المتسبب، والجودة «أسوأ مساهمة تفوز»،
        و``source_feed`` آخر مغذٍ يفوز مع عدّ التعارض.

        Raises:
            ValueError: ``buyer_is_maker=None`` (مصدر بلا علم — خارج منهجية
                §12.7)، أو إطار غير مدعوم/زمن ساذج من ``bucket_floor`` —
                الرفع فوري قبل أي أثر جانبي.
        """
        if event.buyer_is_maker is None:
            raise ValueError(
                "buyer_is_maker=None مرفوض: منهجية aggtrade-taker-side (§12.7) "
                "تتطلب علم الطرف المتسبب — مصدر بلا علم خارج المنهجية"
            )
        bar_time = bucket_floor(event.event_time_utc, self._timeframe)
        instrument_id = f"{event.venue}:{event.symbol}"
        state = self._streams.setdefault(instrument_id, _StreamState())

        evolving = state.evolving
        if evolving is None:
            # لا شريط جارٍ: دلو مضى (مساوٍ أو أقدم من آخر مقفل) ⇒ متأخر؛
            # وإلا فهذه بداية أول شريط في المجرى (لا سابقة تُقفل ⇒ None).
            if state.last_closed_bar_time is not None and bar_time <= state.last_closed_bar_time:
                self._late_events += 1
                return None
            self._start_bar(state, bar_time, event, quality)
            return None

        if bar_time == evolving.bar_time:
            # حدث داخل الدلو الحالي: تراكم صفّي وإصدار نسخة متطورة كاملة.
            self._accumulate(evolving, event)
            evolving.quality = _worse(evolving.quality, quality)
            if event.feed_id != evolving.source_feed:
                evolving.source_feed = event.feed_id
                self._feed_id_conflicts += 1
            self._n_evolved_updates += 1
            return self._assemble(instrument_id, evolving, is_closed=False)

        if bar_time > evolving.bar_time:
            # أول حدث في دلو جديد: السابق يُقفل بقيمه النهائية ويُعاد،
            # ثم تبدأ متطورة جديدة (لا تُعاد — تُعاد نسختها بالحدث التالي).
            closed = self._close(instrument_id, state, evolving)
            self._start_bar(state, bar_time, event, quality)
            return closed

        # دلو أقدم من المتطور الجاري ⇒ متأخر بعد تجاوز نافذته: يُحصى ولا
        # يعود يلمس شيئًا (المقفلة جمود §27، والفائتة لا تُستحدث).
        self._late_events += 1
        return None

    def close_current(self, instrument_id: str) -> FootprintBar | None:
        """إقفال صريح للمتطورة الجارية لدى الأداة (نهاية البث).

        لا يغيّر أي قيمة — القيم نهائية منذ آخر حدث وصل؛ الإقفال قلبُ
        ``is_closed`` إلى True وتثبيت حدود القفل (أي حدث تالٍ لدلو أقدم
        متأخر). لا متطورة جارية (أو أداة مجهولة) ⇒ ``None``.
        """
        state = self._streams.get(instrument_id)
        if state is None or state.evolving is None:
            return None
        return self._close(instrument_id, state, state.evolving)

    def evolving(self, instrument_id: str) -> FootprintBar | None:
        """نسخة حية من المتطورة الجارية لدى الأداة (``is_closed=False``).

        قراءة بلا أثر: لا تعدّ في ``n_evolved_updates`` ولا تمس أي حالة؛
        ``None`` إن لا متطورة جارية (أو أداة مجهولة).
        """
        state = self._streams.get(instrument_id)
        if state is None or state.evolving is None:
            return None
        return self._assemble(instrument_id, state.evolving, is_closed=False)

    def closed_bars(self) -> tuple[FootprintBar, ...]:
        """كل الأشرطة المقفلة وحدها — بنفس الترتيب الحتمي للحفظ الداخلي.

        قراءة صرفة فوق ``closed_bars_with_rows`` (``(bar_time,
        instrument_id)`` عبر كل مجاري البنّاء): من يحتاج الصفوف السعرية
        (الكواشف 4-c) يستهلك التخزين الأغنى مباشرة؛ وهذه الواجهة الأبسط
        لمن يريد مقاييس §8.2 فحسب.
        """
        return tuple(br.bar for br in self.closed_bars_with_rows())

    def closed_bars_with_rows(self) -> tuple[BarRows, ...]:
        """كل الأشرطة المقفلة مع صفوفها — مدخل الكواشف الصفّية (4-c).

        ``rows`` داخل كل :class:`BarRows` مرتبة تصاعديًا بالسعر حصرًا
        (عقد ``rows.py``)؛ والمخرج كله مرتبًا حتميًا بـ``(bar_time,
        instrument_id)`` عبر كل مجاري البنّاء.
        """
        all_closed = [br for state in self._streams.values() for br in state.closed]
        all_closed.sort(key=lambda br: (br.bar.bar_time, br.bar.instrument_id))
        return tuple(all_closed)

    # ───────── الإحصاءات القابلة للاستعلام (عبر كل المجاري) ─────────

    @property
    def n_closed(self) -> int:
        """عدد الأشرطة المقفلة (بعبور الحد أو الإقفال الصريح)."""
        return self._n_closed

    @property
    def n_evolved_updates(self) -> int:
        """عدد مرات إصدار نسخة المتطورة (``is_closed=False``) داخل دلاءها."""
        return self._n_evolved_updates

    @property
    def late_events(self) -> int:
        """عدد الأحداث المتأخرة بعد تجاوز نافذتها — لا صمت أبدًا (موثق أعلاه)."""
        return self._late_events

    @property
    def first_bar_time(self) -> datetime | None:
        """أقدم دلو بدأ منه شريط في البنّاء (None إن لم يبدأ أي شريط بعد)."""
        return self._first_bar_time

    @property
    def last_bar_time(self) -> datetime | None:
        """أحدث دلو بدأ منه شريط في البنّاء (يشمل المتطورة الجارية)."""
        return self._last_bar_time

    @property
    def feed_id_conflicts(self) -> int:
        """عدد تعارضات ``feed_id`` داخل الدلاء — كل تعارض يعدّ مرة (§12.7)."""
        return self._feed_id_conflicts

    # ───────── الداخلية ─────────

    def _accumulate(self, evolving: _EvolvingBar, event: TradeEvent) -> None:
        """تراكم صفقة في صف سعرها بمنهجية الطرف المتسبب (§12.7).

        ``buyer_is_maker=False`` ⇒ المشتري متسبب (شراء عدواني)؛ ``True``
        ⇒ البائع متسبب (بيع عدواني). سعر جديد يُدرج في ``prices``
        (``insort`` يحفظ الترتيب التصاعدي — عقد ``rows.py``).
        """
        cell = evolving.volumes.get(event.price)
        if cell is None:
            cell = [0.0, 0.0]
            evolving.volumes[event.price] = cell
            insort(evolving.prices, event.price)
        if event.buyer_is_maker is False:
            cell[0] += event.quantity
        else:
            cell[1] += event.quantity

    def _start_bar(
        self,
        state: _StreamState,
        bar_time: datetime,
        event: TradeEvent,
        quality: DataQuality,
    ) -> None:
        """افتتاح شريط متطور من أول حدث وصل إلى الدلو (feed المصدر له)."""
        evolving = _EvolvingBar(bar_time=bar_time, quality=quality, source_feed=event.feed_id)
        self._accumulate(evolving, event)
        state.evolving = evolving
        if self._first_bar_time is None or bar_time < self._first_bar_time:
            self._first_bar_time = bar_time
        if self._last_bar_time is None or bar_time > self._last_bar_time:
            self._last_bar_time = bar_time

    def _close(
        self,
        instrument_id: str,
        state: _StreamState,
        evolving: _EvolvingBar,
    ) -> FootprintBar:
        """إقفال المتطورة: إصدار نهائي + حفظ صفوفها + تثبيت حدود القفل."""
        bar = self._assemble(instrument_id, evolving, is_closed=True)
        rows = tuple(
            FootprintRow(
                price=price,
                buy_volume=evolving.volumes[price][0],
                sell_volume=evolving.volumes[price][1],
            )
            for price in evolving.prices
        )
        state.closed.append(BarRows(bar=bar, rows=rows))
        state.last_closed_bar_time = evolving.bar_time
        state.evolving = None
        self._n_closed += 1
        return bar

    def _assemble(
        self,
        instrument_id: str,
        evolving: _EvolvingBar,
        *,
        is_closed: bool,
    ) -> FootprintBar:
        """بناء كائن الشريط الكامل (§8.2) عند كل إصدار — حتى المتطورة.

        القيم المشتقة تُحسب هنا فقط ومن أحداث وصلت فعلًا (لا-نظرة-
        مستقبلية §26.3)؛ والمنهجية ثابتة القانون ``METHODOLOGY_AGGTRADE_TAKER``
        (§12.7 — لا نص حر في أي مسار).
        """
        m = _compute_metrics(evolving, imbalance_ratio=self._imbalance_ratio)
        return FootprintBar(
            instrument_id=instrument_id,
            timeframe=self._timeframe,
            bar_time=evolving.bar_time,
            quality=evolving.quality,
            is_closed=is_closed,
            source_feed=evolving.source_feed,
            methodology=METHODOLOGY_AGGTRADE_TAKER,
            buy_volume=m.buy_volume,
            sell_volume=m.sell_volume,
            total_volume=m.total_volume,
            delta=m.delta,
            buy_share=m.buy_share,
            sell_share=m.sell_share,
            poc=m.poc,
            vah=m.vah,
            val=m.val,
            row_count=m.row_count,
            buy_imbalance_count=m.buy_imbalance_count,
            sell_imbalance_count=m.sell_imbalance_count,
            max_positive_delta_row=m.max_positive_delta_row,
            max_negative_delta_row=m.max_negative_delta_row,
        )
