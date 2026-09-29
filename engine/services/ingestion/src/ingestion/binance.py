"""محول Binance USDⓈ-M Futures — المصدر المرجعي (D-02، §7.1، §7.3، §33.1).

هذه الوحدة أول طبقة في مسار البيانات (§33.1): تحويل رسائل البورصة الخام
إلى TradeEvent القانوني، مع عميل REST بترقيم صفحات كامل للاسترجاع التاريخي
والمقارنة المرجعية (golden) التي تستهلكها المهمتان 1.4/1.6.

قرارات موثقة:
- نقاط نهاية عامة فقط — لا مفتاح API إطلاقًا (بيانات السوق العامة بلا مصادقة).
- كل زمن حدث يُشتق من حقل T (زمن الصفقة الفعلي عند البورصة) لا من الساعة
  المحلية — §7.1 يحظر زمن الساعة الحائطية المحلية كزمن حدث سوقي.
- في رسائل WS: E لحظة إرسال البورصة للرسالة وT زمن الصفقة الفعلي — نستخدم
  T لزمن الحدث (العقد يريد «زمن الحدث الفعلي عند توفره») وE يُهمل بعد توثيقه.
- latency سالبة (ساعتنا خلف ساعة البورصة) تعني انزياح ساعة لا كمونًا مصدريًا
  — القياس غير موثوق فيُختم بـ None لا بقيمة كاذبة.
- دوال التحويل نقية بلا حالة (receive_time قابلة للحقن لحتمية الاختبارات)؛
  العميل الوحيد صاحب الحالة هو BinanceRestClient.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import httpx
from common.config import load_settings
from schemas import TradeEvent

# هوية المصدر — تُختم على كل حدث (§7.1: venue/feed_id ثابتان موثقان)
BINANCE_VENUE = "binance-usdm-futures"
AGGTRADES_FEED_ID = "binance-usdm-aggtrades"
KLINES_FEED_ID = "binance-usdm-klines"
# aggTrades مصدر tick (صفقات مجمعة) — الإطار الزمني للحدث الأصلي
TICK_TIMEFRAME = "1t"

# حد API: نافذة aggTrades الواحدة أقل من ساعة — نقسم إلى مقاطع 50 دقيقة
# بهامش أمان موثق ضد أي انزياح في تفسير الحد.
_AGGTRADES_CHUNK_MS = 50 * 60 * 1000


class BinanceParseError(ValueError):
    """رسالة Binance فاسدة أو شكل غير متوقع — تُرفض صراحة لا تُمرر صامتة."""


class BinancePaginationError(RuntimeError):
    """تجاوز سقف صفحات الترقيم أو سلوك API غير متوقع — إحباط صاخب موثق."""


def _ms_to_utc(ms: int) -> datetime:
    """ملي ثانية → datetime واعٍ UTC بحساب صحيح.

    القسمة العائمة (ms/1000) قد تُفقد دقة الميكروثانية عند التحويل؛
    الجمع الصحيح (ثوانٍ + باقي ملي ثانية) حتمي دائمًا.
    """
    return datetime.fromtimestamp(ms // 1000, tz=UTC) + timedelta(milliseconds=ms % 1000)


def _coerce_int(value: object, field: str, *, minimum: int) -> int:
    """عدد صحيح صارم — bool مرفوض (bool subclass من int في بايثون)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise BinanceParseError(f"حقل {field} يجب أن يكون عددًا صحيحًا، وصل: {value!r}")
    if value < minimum:
        raise BinanceParseError(f"حقل {field} دون الحد الأدنى {minimum}: {value!r}")
    return value


def _coerce_float(value: object, field: str, *, minimum: float, exclusive: bool) -> float:
    """عدد عشري من شكل str/int/float (البورصة ترسل الأسعار نصًا) مع فحص الحد."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise BinanceParseError(f"حقل {field} غير رقمي، وصل: {value!r}")
    try:
        number = float(value)
    except ValueError:
        raise BinanceParseError(f"حقل {field} غير قابل للتحويل إلى عدد: {value!r}") from None
    if not math.isfinite(number):
        raise BinanceParseError(f"حقل {field} غير منتهٍ: {value!r}")
    if (exclusive and number <= minimum) or (not exclusive and number < minimum):
        bound = "موجب صارم" if exclusive else "غير سالب"
        raise BinanceParseError(f"حقل {field} يجب أن يكون {bound} (>{minimum}): {value!r}")
    return number


def _positive_float(value: object, field: str) -> float:
    """سعر موجب صارم — قيد Price في schemas."""
    return _coerce_float(value, field, minimum=0.0, exclusive=True)


def _nonnegative_float(value: object, field: str) -> float:
    """كمية/حجم غير سالب — قيد NonNegativeFloat في schemas."""
    return _coerce_float(value, field, minimum=0.0, exclusive=False)


def _require_symbol(raw: dict[str, Any]) -> str:
    """استخراج الرمز من حقل s (شكل WS) — رمز غائب/فارغ خطأ صريح."""
    symbol = raw.get("s")
    if not isinstance(symbol, str) or not symbol:
        raise BinanceParseError(
            "رمز الأداة غائب: صفوف REST تتطلب symbol صريحًا ورسائل WS تحمله في s"
        )
    return symbol


def _aggtrade_core(raw: dict[str, Any], *, symbol: str, receive_time: datetime) -> TradeEvent:
    """التحويل المشترك لرسالة aggTrade (REST صفًا أو WS رسالة) إلى TradeEvent.

    الحقول المستهلكة: a (معرف aggTrade → sequence_id)، p/q (سعر/كمية)،
    T (زمن الصفقة)، m (المشتري صانع؟ → علم العدوانية). الحقول f/l (مدى
    الصفقات الخام المجمعة) خارج عقد §7.1 فتُهمل بعد التوثيق.
    """
    agg_id = _coerce_int(raw.get("a"), "a (معرف aggTrade)", minimum=1)
    price = _positive_float(raw.get("p"), "p (السعر)")
    quantity = _nonnegative_float(raw.get("q"), "q (الكمية)")
    trade_ms = _coerce_int(raw.get("T"), "T (زمن الصفقة)", minimum=0)
    buyer_is_maker = raw.get("m")
    if not isinstance(buyer_is_maker, bool):
        raise BinanceParseError(f"حقل m يجب أن يكون منطقيًا، وصل: {buyer_is_maker!r}")
    event_time = _ms_to_utc(trade_ms)
    latency_ms = (receive_time - event_time).total_seconds() * 1000.0
    return TradeEvent(
        event_time_utc=event_time,
        receive_time_utc=receive_time,
        source_timeframe=TICK_TIMEFRAME,
        venue=BINANCE_VENUE,
        symbol=symbol,
        feed_id=AGGTRADES_FEED_ID,
        sequence_id=str(agg_id),
        # قيمة سالبة = انزياح ساعة لا كمون — None (سياسة موثقة في رأس الوحدة)
        source_latency_ms=None if latency_ms < 0.0 else latency_ms,
        price=price,
        quantity=quantity,
        buyer_is_maker=buyer_is_maker,
    )


def parse_aggtrade(
    raw: dict[str, Any],
    *,
    symbol: str | None = None,
    receive_time: datetime | None = None,
) -> TradeEvent:
    """تحويل صف aggTrade من REST ‏{a,p,q,f,l,T,m} إلى TradeEvent القانوني (§7.1).

    رمز الأداة: صفوف REST لا تحمله — يمرَّر عبر ``symbol``؛ إن وصلت الرسالة
    بحقل s (شكل WS) استُخدم احتياطًا، والأولوية للمعامل الصريح (يُوثَّق أن
    التعارض بينهما يعني خلط متصل وليس خطأ بيانات). زمن الاستلام قابل للحقن
    للحتمية؛ الافتراضي الآن-UTC لحظة الاستلام الفعلي.
    """
    resolved = symbol or _require_symbol(raw)
    return _aggtrade_core(raw, symbol=resolved, receive_time=receive_time or datetime.now(UTC))


def parse_ws_aggtrade(
    raw: dict[str, Any],
    *,
    receive_time: datetime | None = None,
) -> TradeEvent:
    """تحويل رسالة aggTrade من تدفق WS ‏{e,E,a,s,p,q,f,l,T,m} — نفس عقد parse_aggtrade.

    التحقق: e يجب أن يكون "aggTrade" — هذا المحول لدفق واحد؛ رفض الأنواع
    الأخرى يمنع الخلط الصامت بين التدفقات. زمن الحدث من T لا E (موثق في
    رأس الوحدة: T زمن الصفقة الفعلي وE لحظة إرسال البورصة الرسالة).
    """
    event_type = raw.get("e")
    if event_type != "aggTrade":
        raise BinanceParseError(f"رسالة WS ليست aggTrade: e={event_type!r}")
    symbol = _require_symbol(raw)
    return _aggtrade_core(raw, symbol=symbol, receive_time=receive_time or datetime.now(UTC))


class KlineBar(NamedTuple):
    """شمعة خام من Binance klines — تمثيل أولي للمقارنة المرجعية (golden).

    تستهلكها المهمتان 1.4/1.6: مطابقة الشموع المبنية من aggTrades ضد مرجع
    البورصة نفسه. الحقول الإضافية المنبعثة upstream (quoteVolume و
    takerBuyQuoteVolume) خارج الحاجة الأولية — تُضاف عند الحاجة بتوثيق لا
    استباقًا.

    **المرحلة 4 (توسيع موثق)**: ``taker_buy_volume`` (حجم القاعدة الذي
    المشترون هم المتسببون به — البورصة تجمعه لكل شمعة) هو المرجع الذهبي
    لحجم الشراء التدفقي المبني من aggTrades عبر علم ``buyer_is_maker``
    (شراء عدواني = مشترٍ متسبب ⇒ ``m=False``): مجموع كميات الصفقات التي
    ``buyer_is_maker=False`` داخل الدلو يجب أن يطابقه. ``trade_count``
    (عدد الصفقات) مرجع ذهبي مساند لعدّ أحداث aggTrades داخل الدلو.
    """

    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float  # حجم الشراء المتسبب (index 9) — المرجع الذهبي للفوتبرنت
    trade_count: int  # عدد الصفقات في الشمعة (index 8) — مرجع مساند


def parse_kline(raw: list[Any]) -> KlineBar:
    """تحويل صف klines ‏[openTime,o,h,l,c,v,closeTime,…] إلى KlineBar.

    نقبل الأشكال ذات 12 حقلًا فأكثر (امتداد طفيف مسموح — النقص مرفوض)،
    ونتحقق اتساق OHLC (high الأقصى وlow الأدنى) وتراتب زمني الإغلاق —
    الأشكال الفاسدة تُرفض صراحة لا تُمرر مرجعًا ذهبيًا معطوبًا.
    """
    if len(raw) < 12:
        raise BinanceParseError(f"صف kline ناقص: {len(raw)} حقلًا (العقد الرسمي 12 حقلًا)")
    open_ms = _coerce_int(raw[0], "openTime", minimum=0)
    close_ms = _coerce_int(raw[6], "closeTime", minimum=0)
    if close_ms <= open_ms:
        raise BinanceParseError(f"closeTime يجب أن يكون بعد openTime: {open_ms} → {close_ms}")
    open_ = _positive_float(raw[1], "open")
    high = _positive_float(raw[2], "high")
    low = _positive_float(raw[3], "low")
    close = _positive_float(raw[4], "close")
    volume = _nonnegative_float(raw[5], "volume")
    #: المرجع الذهبي للفوتبرنت (المرحلة 4): حجم الشراء المتسبب (index 9)
    #: وعدد الصفقات (index 8) — لا يُقبل ناقصًا، والكمية الصفرية شمعة
    #: خاملة مشروعة (فراغ تداول داخل نافذة).
    taker_buy = _nonnegative_float(raw[9], "takerBuyBaseAssetVolume")
    trade_count = _coerce_int(raw[8], "tradeCount", minimum=0)
    if not (high >= open_ and high >= close and high >= low and low <= open_ and low <= close):
        raise BinanceParseError(
            f"OHLC غير متسق: high يجب أن يكون الأقصى وlow الأدنى — o={open_} h={high} "
            f"l={low} c={close}"
        )
    return KlineBar(
        open_time_ms=open_ms,
        close_time_ms=close_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        taker_buy_volume=taker_buy,
        trade_count=trade_count,
    )


def _parse_retry_after(value: str | None) -> float | None:
    """قراءة ترويسة Retry-After (ثوانٍ) — أي صيغة غريبة تعني None (تراجع أُسي احتياطيًا)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class BinanceRestClient:
    """عميل REST لبيانات Binance USDⓈ-M العامة — ترقيم صفحات + احترام حدود المعدل.

    حدود المعدل (استراتيجية موثقة): عند 429 (تجاوز وزن الطلب) أو 418 (حظر
    مؤقت) ننتظر Retry-After إن أرسلت البورصة، وإلا تراجعًا أُسيًا
    1s→2s→…→30s، حتى ``max_attempts`` محاولة إجمالية؛ بعدها يُرفع خطأ الحالة
    الأصلي (raise_for_status) — لا صمت ولا إغراق البورصة بطلبات.

    لا يحمل أي مفتاح — نقاط عامة فقط. القاعدة من common.config
    (binance_api_base) قابلة للتجاوز عبر ``base_url`` للحقن في الاختبارات.
    ``transport`` يسمح بحقن httpx.MockTransport — اختبارات الوحدة بلا شبكة.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        page_size: int = 1000,
        max_pages: int = 1000,
        max_attempts: int = 5,
        backoff_initial_s: float = 1.0,
        backoff_max_s: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if not 1 <= page_size <= 1000:
            raise ValueError(f"page_size خارج حدود API (1..1000): {page_size}")
        if max_pages < 1:
            raise ValueError(f"max_pages يجب أن يكون موجبًا: {max_pages}")
        if max_attempts < 1:
            raise ValueError(f"max_attempts يجب أن يكون موجبًا: {max_attempts}")
        self._client = httpx.AsyncClient(
            base_url=base_url or load_settings().binance_api_base,
            timeout=timeout,
            transport=transport,
        )
        self._page_size = page_size
        self._max_pages = max_pages
        self._max_attempts = max_attempts
        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep or asyncio.sleep

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 1000,
    ) -> list[KlineBar]:
        """جلب الشموع بترقيم صفحات كامل حتى استيفاء النطاق أو نهاية البيانات.

        الترقيم (موقّق): صفحات بحجم ``limit``؛ الصفحة الممتلئة قد تعني بقايا
        فيتقدم المؤشر إلى openTime آخر شمعة + 1 (لا تداخل بين الصفحات)،
        والصفحة الناقصة أو الفارغة = نهاية البيانات. ``start_ms=None`` يجعل
        الصفحة الأولى الأحدث (سلوك API بلا startTime) ثم يستمر الالتفاف قُدُمًا
        حتى النقص — تُوثَّق هذه الدلالة لا تُفترض ضمنًا. الشموع التي يتجاوز
        openTime فيها ``end_ms`` تُرشَّح خارجًا (نطاق المتصل مقيَّد بوقت الفتح).

        سقف الحماية: ``max_pages`` صفحة (افتراضي 1000 ≈ مليون شمعة) — تجاوزه
        إحباط صاخب (BinancePaginationError) لا التفاف أعمى.
        """
        if not 1 <= limit <= 1000:
            raise ValueError(f"limit خارج حدود API (1..1000): {limit}")
        if start_ms is not None and end_ms is not None and end_ms < start_ms:
            raise ValueError(f"end_ms أقدم من start_ms: {start_ms} → {end_ms}")
        bars: list[KlineBar] = []
        cursor = start_ms
        pages = 0
        while True:
            if pages >= self._max_pages:
                raise BinancePaginationError(
                    f"تجاوز سقف الصفحات ({self._max_pages}) في fetch_klines — "
                    "النطاق أوسع من المسموح"
                )
            params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
            if cursor is not None:
                params["startTime"] = cursor
            if end_ms is not None:
                params["endTime"] = end_ms
            rows = await self._get_json("/fapi/v1/klines", params)
            pages += 1
            page_bars = [parse_kline(row) for row in rows]
            kept = [bar for bar in page_bars if end_ms is None or bar.open_time_ms <= end_ms]
            bars.extend(kept)
            if len(rows) < limit or len(kept) < len(page_bars):
                break  # نهاية البيانات، أو بقية الصفحة كلها وراء end_ms
            cursor = kept[-1].open_time_ms + 1
            if end_ms is not None and cursor > end_ms:
                break
        return bars

    async def fetch_aggtrades(self, symbol: str, start_ms: int, end_ms: int) -> list[TradeEvent]:
        """جلب aggTrades في النطاق [start_ms, end_ms] مغلقًا من الطرفين.

        اختيار الترقيم (موقّق): اعتمدنا الترقيم الزمني (startTime/endTime) لا
        fromId — نقطة aggTrades في عقود USDⓈ-M توثّق الاستعلام الزمني صراحةً
        وتقيّد النافذة بساعة واحدة، بينما fromId غير مضمون التوثيق في هذه
        النقطة (النقطة المكشوفة الموثقة هي spot). التفاصيل:

        - تقسيم زمني: النطاق يُقسَّم إلى مقاطع 50 دقيقة (تحت حد الساعة بهامش).
        - داخل المقطع: المؤشر يتقدم إلى T آخر صفقة في الصفحة (لا +1) مع خصم
          المعرفات المكررة عبر مجموعة seen — يضمن عدم فقد صفقات تتشارك نفس
          المللي ثانية عند حدود الصفحات (انقسام دفعة نفس-ms بين صفحتين).
        - الصفحة الناقصة = استنفاد نافذة المقطع؛ الصفحة الممتلئة بلا معرفات
          جديدة = سلوك API غير متوقع (كتجاهل startTime) → إحباط صاخب لا حلقة.
        - نطبق افتراضًا موثقًا: الرد مرتب تصاعديًا بالزمن (سلوك API المرصود).

        ملاحظة زمن الاستلام (موثقة): هنا زمن الاستلام لحظة الجلب الأرشيفي —
        latency الناتج يشمل عمر الأرشيف ولا يُغذّى لمصنف الجودة الحي (المسار
        الحي هو WS؛ الأرشيف يُستهلك لاحقًا عبر المخزن الخام 1.5/الإعادة 9.x).
        """
        if end_ms < start_ms:
            raise ValueError(f"end_ms أقدم من start_ms: {start_ms} → {end_ms}")
        events: list[TradeEvent] = []
        seen_ids: set[int] = set()
        pages = 0
        chunk_start = start_ms
        while chunk_start <= end_ms:
            chunk_end = min(chunk_start + _AGGTRADES_CHUNK_MS - 1, end_ms)
            cursor = chunk_start
            while True:
                if pages >= self._max_pages:
                    raise BinancePaginationError(
                        f"تجاوز سقف الصفحات ({self._max_pages}) في fetch_aggtrades — "
                        "النطاق أوسع من المسموح"
                    )
                rows: list[dict[str, Any]] = await self._get_json(
                    "/fapi/v1/aggTrades",
                    {
                        "symbol": symbol,
                        "startTime": cursor,
                        "endTime": chunk_end,
                        "limit": self._page_size,
                    },
                )
                pages += 1
                if not rows:
                    break
                fresh = [row for row in rows if row["a"] not in seen_ids]
                if not fresh and len(rows) >= self._page_size:
                    raise BinancePaginationError(
                        "صفحة aggTrades ممتلئة بلا معرفات جديدة — سلوك API غير متوقع "
                        "(تجاهل startTime؟) — إحباط لا التفاف"
                    )
                for row in fresh:
                    seen_ids.add(row["a"])
                    events.append(parse_aggtrade(row, symbol=symbol))
                if len(rows) < self._page_size:
                    break  # استنفدنا نافذة المقطع
                cursor = int(rows[-1]["T"])
            chunk_start = chunk_end + 1
        return events

    async def _get_json(self, path: str, params: dict[str, Any]) -> list[Any]:
        """طلب GET واحد مع إعادة محاولة محدودة عند 429/418 (الاستراتيجية برأس الفئة)."""
        attempt = 0
        while True:
            response = await self._client.get(path, params=params)
            if response.status_code in (429, 418) and attempt < self._max_attempts - 1:
                delay = max(
                    _parse_retry_after(response.headers.get("Retry-After")) or 0.0,
                    min(self._backoff_initial_s * (2**attempt), self._backoff_max_s),
                )
                await self._sleep(delay)
                attempt += 1
                continue
            response.raise_for_status()
            payload: list[Any] = response.json()
            return payload

    async def aclose(self) -> None:
        """إغلاق العميل — يُستدعى مرة عند انتهاء الاستخدام (أو عبر async with)."""
        await self._client.aclose()

    async def __aenter__(self) -> BinanceRestClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
