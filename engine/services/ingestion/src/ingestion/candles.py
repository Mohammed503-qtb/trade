"""منشئ الشموع الحدثي — التجميع الصادق من أحداث وصلت فعلًا (§8.1، §27، §33.1).

الموضع في المسار (§33.1): بعد ``event published`` يأتي ``candle aggregator``
(ثم ``candle persisted``) — هذا البنّاء هو ذاك المجمّع: يستهلك أحداث صفقات
منقّحة (مسؤولية refine/quality — المهمتان 1.2/1.3) ويُنتج شموع §8.1 لكل
(instrument_id, timeframe) على حدة.

صرفية البنّاء: لا شبكة ولا قواعد بيانات ولا I/O — منطق sync خالص قابل
للاختبار الحتمي، ولا يملك أي نظرة مستقبلية (§26.3): كل قيمة تُشتق فقط من
أحداث وصلت فعلًا حتى اللحظة الجارية (نفس المدخلات حتى t ⇒ نفس المخرجات
حتى لو توفر t+1).

سياسة عدم إعادة الرسم (§27): كل إصدار يحمل ``is_closed`` — المتطورة قد
تتغير قبل الإغلاق ولا تفوّض قرارًا حيًا؛ والمقفلة جمود نهائي لا يُلمس
أبدًا (لا من أحداث متأخرة ولا من أي مسار آخر).

اتفاقيات الحواف الموثقة (تُختبر حرفيًا في tests/unit/test_candles.py):
- شمعة بلا مدى (high == low): ``body_fraction = 0.0`` و
  ``close_location_value = 0.5``.
- ``true_range`` لأول شمعة في المجرى (لا إغلاق سابق) = ``high - low``؛ وما
  بعدها ``max(high-low, |high-prev_close|, |low-prev_close|)`` بإغلاق آخر
  شمعة مقفلة في المجرى نفسه — الفجوات الزمنية لا تُتجاوز: مسافة الإغلاق
  السابق هي جوهر قياس المدى الحقيقي.
- ``realized_volatility`` قياس خام = ``|ln(close/open)|`` — التطبيع بإحصاءات
  النظام الحديث مكانه حزمة features (مرحلة 2)، لا هنا.
- ``open`` سعر أول حدث وصل إلى الدلو (بترتيب الوصول) — لا قيمة منقّحة
  عرضًا؛ و``close`` سعر آخر حدث وصل (ترتيب الوصول لا ترتيب الطوابع).
- ``session_id`` تاريخ يوم ``bar_time`` بتقويم UTC بصيغة ISO ``YYYY-MM-DD``
  (جلسة UTC اليومية — قرار A-03)؛ الجلسات الحبيبية مرحلة 2.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from schemas import Candle, DataQuality, TradeEvent

__all__ = [
    "QUALITY_SEVERITY_LADDER",
    "SUPPORTED_TIMEFRAMES",
    "CandleBuilder",
    "bucket_floor",
]

# ───────────────────────── حدود الأطر والدلاء ─────────────────────────

# الأطر المدعومة → طول الدلو. كل شيء UTC (§7.1): لا مناطق زمنية ولا توقيت
# صيفي — حدود الدلاء مطلقة على محور epoch.
_TIMEFRAME_DELTAS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

SUPPORTED_TIMEFRAMES: tuple[str, ...] = tuple(_TIMEFRAME_DELTAS)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def bucket_floor(ts: datetime, timeframe: str) -> datetime:
    """تقريب الطابع الزمني إلى أسفل حدّ الدلو (بداية شمعة الإطار) — UTC خالص.

    القسمة على طول الدلو تُطبَّق على المسافة المطلقة منذ epoch، فالحدود
    مطلقة (00:00، :05، :15…) وتصمد حتى لما قبل epoch (القسمة الأرضية نحو
    سالب ما لا نهاية).

    Args:
        ts: طابع زمني واعٍ (يُطبَّع إلى UTC — الساذج مرفوض وفق عقد §7.1).
        timeframe: أحد الأطر الستة المدعومة (انظر ``SUPPORTED_TIMEFRAMES``).

    Returns:
        بداية الدلو الذي يقع فيه ``ts`` — datetime بمنطقة UTC.

    Raises:
        ValueError: إطار غير مدعوم (بلا تخمين ولا احتساب ضمني)، أو datetime
            ساذج (عقد الوقت §7.1).
    """
    delta = _TIMEFRAME_DELTAS.get(timeframe)
    if delta is None:
        supported = ", ".join(SUPPORTED_TIMEFRAMES)
        raise ValueError(f"unsupported timeframe: {timeframe!r} (supported: {supported})")
    if ts.tzinfo is None:
        raise ValueError(
            "naive datetime rejected: bucket boundaries are UTC-only (§7.1) — "
            "pass a tz-aware datetime"
        )
    utc = ts.astimezone(UTC)
    bucket_index = (utc - _EPOCH) // delta
    return _EPOCH + bucket_index * delta


# ───────────────────────── سلّل شدة الجودة ─────────────────────────

# سلّل شدة جودة البيانات (من الأدنى إلى الأقصى) — «أسوأ مساهمة تفوز» عند
# التجميع داخل الشمعة الواحدة.
# تنبيه مهم: هذا الترتيب نسخة أولى منقولة من تعريف المهمة 1.4 وهو قابل
# للمراجعة عند دمج المهمة 1-a (مصنف شرائح الجودة §7.4)؛ يختلف عن ترتيب
# التصريح في schemas/enums.py في موضعي OUT_OF_ORDER/DUPLICATED فقط — وهذا
# مقصود وفق التعريف أعلاه.
QUALITY_SEVERITY_LADDER: tuple[DataQuality, ...] = (
    DataQuality.HEALTHY,  # 0 — أقل شدة
    DataQuality.DELAYED,  # 1
    DataQuality.PARTIAL,  # 2
    DataQuality.OUT_OF_ORDER,  # 3
    DataQuality.DUPLICATED,  # 4
    DataQuality.STALE,  # 5
    DataQuality.GAP_DETECTED,  # 6
    DataQuality.UNAVAILABLE,  # 7
    DataQuality.QUARANTINED,  # 8 — أقصى شدة
)

_SEVERITY: dict[DataQuality, int] = {q: i for i, q in enumerate(QUALITY_SEVERITY_LADDER)}


def _worse(a: DataQuality, b: DataQuality) -> DataQuality:
    """أسوأ الجودتين وفق سلّل الشدة — دمج الجودة تراكمي داخل الشمعة الواحدة."""
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


# ───────────────────────── الحالة الداخلية ─────────────────────────


@dataclass
class _EvolvingBar:
    """حالة الشمعة المتطورة الجارية (خاصة بالوحدة — لا تُصدَّر)."""

    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quality: DataQuality


@dataclass
class _StreamState:
    """حالة مجرى واحد (instrument_id, timeframe).

    ``evolving`` الشمعة الجارية؛ ``last_closed_bar_time`` تحرس حدود القفل —
    أي حدث لدلو مساوٍ أو أقدم منها متأخر لا يلمس المقفلة ولا ينشئ فائتة؛
    و``prev_close`` إغلاق آخر شمعة مقفلة في المجرى (مدخل true_range §8.1).
    """

    evolving: _EvolvingBar | None = None
    last_closed_bar_time: datetime | None = None
    prev_close: float | None = None


# ───────────────────────── البنّاء ─────────────────────────


class CandleBuilder:
    """بنّاء شموع حدثي صرف لكل (instrument_id, timeframe) على حدة.

    مفتاح المجرى مشتق من الحدث نفسه: ``instrument_id = f"{venue}:{symbol}"``
    (المفتاح الطبيعي — متسق مع فهرس ux_instruments_venue_symbol من المهمة
    0.6 وfixtures حزمة schemas مثل «BINANCE_USDM:BTCUSDT»؛ ربط UUID المفتاح
    الاصطناعي مسؤولية طبقة التخزين لاحقًا) و``timeframe = event.source_timeframe``
    (خارج الأطر المدعومة ⇒ ``ValueError`` فورية بلا أثر جانبي).

    عقد الإرجاع لـ``add_trade``:
    - ``None``: أول حدث في مجرى جديد (لا سابقة تُقفل)، أو حدث متأخر (دلو
      أقدم من المتطورة الجارية، أو مساوٍ/أقدم من آخر دلو مقفل) — المتأخر
      يُحصى في ``late_events`` ولا صمت أبدًا ولا تعديل للمقفلة ولا إنشاء
      شمعة فائتة بأثر رجعي.
    - ``Candle(is_closed=True)``: الشمعة السابقة عند أول حدث يعبر حدّ دلو
      جديد — بقيمها النهائية، جمودها نهائي (§27).
    - ``Candle(is_closed=False)``: نسخة المتطورة الحالية بعد تحديث تراكمي
      (high/low/close/volume) — المستهلك حر في تجاهلها؛ المتطورة لا تفوّض
      قرارًا حيًا (§27).

    الإحصاءات (``n_closed``/``n_evolved_updates``/``late_events``/
    ``first_bar_time``/``last_bar_time``) عبر كل مجاري البنّاء كافة. البنّاء
    غير محصّن ضد التزامن — يُستهلك من مهمة واحدة ضامنة الحتمية.
    """

    def __init__(self) -> None:
        self._streams: dict[tuple[str, str], _StreamState] = {}
        self._n_closed = 0
        self._n_evolved_updates = 0
        self._late_events = 0
        self._first_bar_time: datetime | None = None
        self._last_bar_time: datetime | None = None

    # ───────── عقد الاستهلاك ─────────

    def add_trade(
        self, event: TradeEvent, quality: DataQuality = DataQuality.HEALTHY
    ) -> Candle | None:
        """إدخال صفقة واحدة وإرجاع أثرها وفق سياسة عدم إعادة الرسم (§27).

        مرجع الدلو هو ``event_time_utc`` (زمن الحدث — لا زمن الوصول أبدًا)،
        والتحديث داخل الدلو الحالي تراكمي: high/low/close/volume وجودة
        «أسوأ مساهمة تفوز». جودة الشمعة تظل كما تراكمت — لا تراجع إذا عادت
        الأحداث اللاحقة أصحاء.

        Raises:
            ValueError: ``event.source_timeframe`` خارج الأطر المدعومة أو زمن
                الحدث ساذج — يُرفع فورًا قبل أي أثر جانبي.
        """
        timeframe = event.source_timeframe
        bar_time = bucket_floor(event.event_time_utc, timeframe)
        key = (f"{event.venue}:{event.symbol}", timeframe)
        state = self._streams.setdefault(key, _StreamState())

        evolving = state.evolving
        if evolving is None:
            # لا شمعة جارية: دلو مضى (مساوٍ أو أقدم من آخر مقفل) ⇒ متأخر؛
            # وإلا فهذه بداية أول شمعة في المجرى (لا سابقة تُقفل ⇒ None).
            if state.last_closed_bar_time is not None and bar_time <= state.last_closed_bar_time:
                self._late_events += 1
                return None
            self._start_bar(state, bar_time, event, quality)
            return None

        if bar_time == evolving.bar_time:
            # حدث داخل الدلو الحالي: تحديث تراكمي وإصدار نسخة المتطورة.
            evolving.high = max(evolving.high, event.price)
            evolving.low = min(evolving.low, event.price)
            evolving.close = event.price
            evolving.volume += event.quantity
            evolving.quality = _worse(evolving.quality, quality)
            self._n_evolved_updates += 1
            return self._build(key, state, evolving, is_closed=False)

        if bar_time > evolving.bar_time:
            # أول حدث في دلو جديد: السابقة تُقفل بقيمها النهائية وتُعاد،
            # ثم تبدأ متطورة جديدة (لا تُعاد — ستُعاد نسخها مع الحدث التالي).
            closed = self._build(key, state, evolving, is_closed=True)
            state.prev_close = evolving.close
            state.last_closed_bar_time = evolving.bar_time
            self._n_closed += 1
            self._start_bar(state, bar_time, event, quality)
            return closed

        # دلو أقدم من المتطورة الجارية ⇒ متأخر وصل بعد تجاوز نافذته:
        # يُحصى ولا يعود يلمس شيئًا (المقفلة جمود §27، والفائتة لا تُستحدث).
        self._late_events += 1
        return None

    def close_current(self, instrument_id: str, timeframe: str) -> Candle | None:
        """إقفال صريح للشمعة المتطورة الجارية في المجرى المحدد (نهاية البث).

        لا يغيّر أي قيمة — القيم نهائية منذ آخر حدث وصل؛ الإقفال قلبُ
        ``is_closed`` إلى True وتثبيت إغلاق الشمعة مرجعًا لـ``true_range``
        الشمعة التالية في المجرى. لا متطورة جارية (أو مجرى مجهول) ⇒ None.
        """
        state = self._streams.get((instrument_id, timeframe))
        if state is None or state.evolving is None:
            return None
        bar = state.evolving
        closed = self._build((instrument_id, timeframe), state, bar, is_closed=True)
        state.prev_close = bar.close
        state.last_closed_bar_time = bar.bar_time
        state.evolving = None
        self._n_closed += 1
        return closed

    # ───────── الإحصاءات القابلة للاستعلام (عبر كل المجاري) ─────────

    @property
    def n_closed(self) -> int:
        """عدد الشموع المقفلة (بعبور الحد أو الإقفال الصريح)."""
        return self._n_closed

    @property
    def n_evolved_updates(self) -> int:
        """عدد مرات إصدار نسخة المتطورة (is_closed=False) داخل دلاءها."""
        return self._n_evolved_updates

    @property
    def late_events(self) -> int:
        """عدد الأحداث المتأخرة بعد تجاوز نافذتها — لا صمت أبدًا (موثق أعلاه)."""
        return self._late_events

    @property
    def first_bar_time(self) -> datetime | None:
        """أقدم دلو بدأت منه شمعة في البنّاء (None إن لم تبدأ أي شمعة بعد)."""
        return self._first_bar_time

    @property
    def last_bar_time(self) -> datetime | None:
        """أحدث دلو بدأت منه شمعة في البنّاء (يشمل المتطورة الجارية)."""
        return self._last_bar_time

    # ───────── الداخلية ─────────

    def _start_bar(
        self,
        state: _StreamState,
        bar_time: datetime,
        event: TradeEvent,
        quality: DataQuality,
    ) -> None:
        """افتتاح شمعة متطورة من أول حدث وصل إلى الدلو (open = سعره الخام)."""
        state.evolving = _EvolvingBar(
            bar_time=bar_time,
            open=event.price,
            high=event.price,
            low=event.price,
            close=event.price,
            volume=event.quantity,
            quality=quality,
        )
        if self._first_bar_time is None or bar_time < self._first_bar_time:
            self._first_bar_time = bar_time
        if self._last_bar_time is None or bar_time > self._last_bar_time:
            self._last_bar_time = bar_time

    def _build(
        self,
        key: tuple[str, str],
        state: _StreamState,
        bar: _EvolvingBar,
        *,
        is_closed: bool,
    ) -> Candle:
        """بناء كائن الشمعة الكامل (§8.1) عند كل إصدار — حتى المتطورة.

        القيم المشتقة تُحسب هنا فقط ومن أحداث وصلت فعلًا؛ تحسب قبل تحديث
        prev_close للدلو الجديد كي تظل شمعة الدلو الجاري مرتبطة بإغلاق
        سابقتها هي، لا بنفسها.
        """
        bar_range = bar.high - bar.low
        body_size = abs(bar.close - bar.open)
        if bar_range > 0.0:
            body_fraction = body_size / bar_range
            close_location_value = (bar.close - bar.low) / bar_range
        else:
            # شمعة بلا مدى (high == low): اتفاقية الحافة الموثقة أعلاه.
            body_fraction = 0.0
            close_location_value = 0.5
        if state.prev_close is None:
            # أول شمعة في المجرى: لا إغلاق سابق ⇒ المدى وحده.
            true_range = bar_range
        else:
            prev = state.prev_close
            true_range = max(bar_range, abs(bar.high - prev), abs(bar.low - prev))
        # القيمة الخام |ln(close/open)| — التطبيع بإحصاءات النظام الحديث مكانه
        # حزمة features (مرحلة 2) لا هنا؛ وشرط open>0 حرس دفاعي موثق (Price>0
        # قانونيًا دائمًا عبر أحداث مشروعة، والقيم المتطرفة ترفضها حدود النموذج).
        realized_volatility = abs(math.log(bar.close / bar.open)) if bar.open > 0.0 else 0.0
        instrument_id, timeframe = key
        return Candle(
            instrument_id=instrument_id,
            timeframe=timeframe,
            bar_time=bar.bar_time,
            session_id=bar.bar_time.date().isoformat(),
            quality=bar.quality,
            is_closed=is_closed,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            range=bar_range,
            body_size=body_size,
            upper_wick=bar.high - max(bar.open, bar.close),
            lower_wick=min(bar.open, bar.close) - bar.low,
            body_fraction=body_fraction,
            close_location_value=close_location_value,
            true_range=true_range,
            realized_volatility=realized_volatility,
        )
