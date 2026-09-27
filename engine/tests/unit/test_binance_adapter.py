"""اختبارات وحدة محول Binance — بلا شبكة إطلاقًا (httpx.MockTransport).

الأشكال منسوخة من التوثيق الرسمي للحمولات: صف aggTrade من REST
{a,p,q,f,l,T,m} ورسالة aggTrade من WS {e,E,a,s,p,q,f,l,T,m} وصف klines
[openTime,o,h,l,c,v,closeTime,quoteVolume,trades,takerBuyBase,takerBuyQuote,ignore].
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from ingestion.binance import (
    AGGTRADES_FEED_ID,
    BINANCE_VENUE,
    TICK_TIMEFRAME,
    BinancePaginationError,
    BinanceParseError,
    BinanceRestClient,
    parse_aggtrade,
    parse_kline,
    parse_ws_aggtrade,
)

BASE = "https://unit.test"
# 1704067200000ms = 2024-01-01T00:00:00Z — لحظة مرجعية حتمية
T0_MS = 1_704_067_200_000
EVENT_T0 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
RECEIVE = datetime(2024, 1, 1, 0, 0, 0, 500_000, tzinfo=UTC)  # +500ms كمون مرجعي


def _rest_aggtrade(**overrides: Any) -> dict[str, Any]:
    """صف aggTrade بشكل REST الرسمي — الحقول f/l حاضرة في الحمولة رغم إهمالها."""
    row: dict[str, Any] = {
        "a": 26129,
        "p": "0.0163",
        "q": "10",
        "f": 27781,
        "l": 27781,
        "T": T0_MS,
        "m": False,
    }
    row.update(overrides)
    return row


def _ws_aggtrade(**overrides: Any) -> dict[str, Any]:
    """رسالة aggTrade بشكل WS الرسمي — E زمن إرسال البورصة (لاحق لـT عمدًا)."""
    message: dict[str, Any] = {
        "e": "aggTrade",
        "E": T0_MS + 400,
        "a": 424951,
        "s": "BTCUSDT",
        "p": "9643.5",
        "q": "0.043",
        "f": 609110,
        "l": 609110,
        "T": T0_MS + 200,
        "m": True,
    }
    message.update(overrides)
    return message


# ═════════════════════ التحويل: aggTrade ‏REST/WS ═════════════════════


class TestParseAggtrade:
    """عقد §7.1 كاملًا على تحويل aggTrade."""

    def test_rest_row_full_contract(self) -> None:
        event = parse_aggtrade(_rest_aggtrade(), symbol="BTCUSDT", receive_time=RECEIVE)
        assert event.event_time_utc == EVENT_T0
        assert event.receive_time_utc == RECEIVE
        assert event.source_latency_ms == 500.0
        assert event.venue == BINANCE_VENUE
        assert event.feed_id == AGGTRADES_FEED_ID
        assert event.source_timeframe == TICK_TIMEFRAME
        assert event.symbol == "BTCUSDT"
        assert event.sequence_id == "26129"
        assert event.buyer_is_maker is False
        assert event.price == pytest.approx(0.0163)
        assert event.quantity == pytest.approx(10.0)

    def test_rest_row_symbol_from_ws_field_fallback(self) -> None:
        """الرسالة الشكل-WS تحمل s — يُستخدم احتياطًا عند غياب المعامل الصريح."""
        event = parse_aggtrade(_ws_aggtrade())
        assert event.symbol == "BTCUSDT"

    def test_explicit_symbol_overrides_message(self) -> None:
        """الأولوية للمعامل الصريح — توثيق خلط المتصل لا خطأ بيانات."""
        event = parse_aggtrade(_ws_aggtrade(), symbol="ETHUSDT")
        assert event.symbol == "ETHUSDT"

    def test_rest_row_without_symbol_rejected(self) -> None:
        with pytest.raises(BinanceParseError, match="رمز الأداة غائب"):
            parse_aggtrade(_rest_aggtrade())

    def test_negative_latency_is_none_not_a_lie(self) -> None:
        """ساعتنا خلف ساعة البورصة ⇒ انزياح ساعة لا كمون ⇒ None (سياسة موثقة)."""
        event = parse_aggtrade(
            _rest_aggtrade(),
            symbol="BTCUSDT",
            receive_time=EVENT_T0 - timedelta(seconds=1),
        )
        assert event.source_latency_ms is None

    def test_latency_computed_from_injected_receive(self) -> None:
        receive = datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC)
        event = parse_aggtrade(_rest_aggtrade(), symbol="BTCUSDT", receive_time=receive)
        assert event.source_latency_ms == 2000.0

    @pytest.mark.parametrize(
        "overrides",
        [
            {"a": None},  # معرف غائب
            {"a": 0},  # معرف غير موجب
            {"a": "26129"},  # معرف نصي (العقد: عدد صحيح)
            {"a": True},  # bool يتسلل كـint
            {"T": None},  # زمن غائب
            {"T": "1704067200000"},  # زمن نصي
            {"p": "abc"},  # سعر غير رقمي
            {"p": "0"},  # سعر غير موجب
            {"p": "-1.5"},  # سعر سالب
            {"q": "-1"},  # كمية سالبة
            {"q": None},  # كمية غائبة
            {"m": "no"},  # علم غير منطقي
            {"m": 1},  # عدد مكان العلم
        ],
    )
    def test_malformed_rows_rejected(self, overrides: dict[str, Any]) -> None:
        with pytest.raises(BinanceParseError):
            parse_aggtrade(_rest_aggtrade(**overrides), symbol="BTCUSDT")


class TestParseWsAggtrade:
    """رسائل WS: التحقق من النوع وزمن الحدث من T لا E."""

    def test_event_time_from_T_not_E(self) -> None:
        event = parse_ws_aggtrade(_ws_aggtrade(), receive_time=RECEIVE)
        assert event.event_time_utc == datetime(2024, 1, 1, 0, 0, 0, 200_000, tzinfo=UTC)
        assert event.sequence_id == "424951"
        assert event.buyer_is_maker is True
        assert event.price == pytest.approx(9643.5)
        assert event.quantity == pytest.approx(0.043)

    @pytest.mark.parametrize(
        "raw",
        [
            {"e": "kline"},  # نوع رسالة آخر
            {"e": "aggTrade", "T": T0_MS, "a": 1, "p": "1", "q": "1", "m": False},  # بلا s
        ],
    )
    def test_rejects_foreign_shapes(self, raw: dict[str, Any]) -> None:
        with pytest.raises(BinanceParseError):
            parse_ws_aggtrade(raw)


# ═════════════════════ التحويل: klines ═════════════════════


def _kline_row(open_ms: int, o: str, h: str, low: str, c: str, v: str) -> list[Any]:
    """صف klines كامل الأشكال الرسمية (12 حقلًا)."""
    return [open_ms, o, h, low, c, v, open_ms + 59_999, "123.45", 57, "12.5", "61.7", "0"]


class TestParseKline:
    """تحويل صف klines إلى KlineBar مع رفض الأشكال الفاسدة."""

    def test_full_row(self) -> None:
        bar = parse_kline(_kline_row(T0_MS, "100.5", "110.0", "99.0", "105.0", "42.5"))
        assert bar.open_time_ms == T0_MS
        assert bar.close_time_ms == T0_MS + 59_999
        assert bar.open == pytest.approx(100.5)
        assert bar.high == pytest.approx(110.0)
        assert bar.low == pytest.approx(99.0)
        assert bar.close == pytest.approx(105.0)
        assert bar.volume == pytest.approx(42.5)

    def test_zero_volume_allowed(self) -> None:
        """شمعة بلا صفقات شرعية — الكمية غير سالبة لا موجبة."""
        bar = parse_kline(_kline_row(T0_MS, "1", "1", "1", "1", "0"))
        assert bar.volume == 0.0

    @pytest.mark.parametrize(
        "row",
        [
            _kline_row(T0_MS, "1", "1", "1", "1", "1")[:11],  # صف ناقص
            ["x", "1", "1", "1", "1", "1", 1, "0", 0, "0", "0", "0"],  # openTime غير رقمي
            _kline_row(T0_MS, "100", "99", "90", "95", "1"),  # high دون open — OHLC غير متسق
            _kline_row(T0_MS, "100", "110", "101", "105", "1"),  # low فوق open
            _kline_row(T0_MS, "100", "110", "90", "-5", "1"),  # close سالب
            _kline_row(T0_MS, "100", "110", "90", "105", "-1"),  # حجم سالب
            # closeTime يساوي openTime — تراتب زمني مكسور
            [T0_MS, "100", "110", "90", "105", "1", T0_MS, "0", 0, "0", "0", "0"],
        ],
    )
    def test_malformed_rows_rejected(self, row: list[Any]) -> None:
        with pytest.raises(BinanceParseError):
            parse_kline(row)


# ═════════════════════ العميل: ترقيم وحدود المعدل ═════════════════════


class _SleepRecorder:
    """حقن النوم بدل asyncio.sleep — يوثق التأخيرات بلا انتظار حقيقي."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _client(handler: Any, **kwargs: Any) -> BinanceRestClient:
    return BinanceRestClient(base_url=BASE, transport=httpx.MockTransport(handler), **kwargs)


def _agg_row(agg_id: int, t_ms: int) -> dict[str, Any]:
    return {"a": agg_id, "p": "100.0", "q": "1.0", "f": 1, "l": 1, "T": t_ms, "m": False}


def _aggtrades_api(rows: list[dict[str, Any]], calls: list[dict[str, str]]) -> Any:
    """محاكاة دقيقة لدلالات aggTrades: حدّان زمنيان مغلقان + حد صفحة."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        start = int(params["startTime"])
        end = int(params["endTime"])
        limit = int(params["limit"])
        page = [row for row in rows if start <= row["T"] <= end][:limit]
        return httpx.Response(200, json=page)

    return handler


class TestFetchKlines:
    """ترقيم صفحات klines: التقدم بالمؤشر والسقف والحد الأعلى."""

    async def test_single_page_no_pagination(self) -> None:
        calls: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            return httpx.Response(
                200,
                json=[_kline_row(T0_MS, "1", "2", "0.5", "1.5", "10")],
            )

        async with _client(handler) as client:
            bars = await client.fetch_klines("BTCUSDT", "1m", start_ms=T0_MS, limit=5)
        assert len(bars) == 1
        assert len(calls) == 1
        assert calls[0]["symbol"] == "BTCUSDT"
        assert calls[0]["interval"] == "1m"
        assert calls[0]["limit"] == "5"
        assert calls[0]["startTime"] == str(T0_MS)

    async def test_pagination_until_short_page(self) -> None:
        calls: list[dict[str, str]] = []
        rows = [_kline_row(T0_MS + i * 60_000, "1", "2", "0.5", "1.5", "10") for i in range(5)]

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            calls.append(params)
            start = int(params["startTime"])
            limit = int(params["limit"])
            page = [row for row in rows if row[0] >= start][:limit]
            return httpx.Response(200, json=page)

        async with _client(handler) as client:
            bars = await client.fetch_klines("BTCUSDT", "1m", start_ms=T0_MS, limit=3)
        assert len(bars) == 5
        assert len(calls) == 2  # صفحة ممتلئة (3) ثم ناقصة (2) فتوقف
        # المؤشر تقدم إلى openTime آخر شمعة في الصفحة الأولى + 1
        assert calls[1]["startTime"] == str(T0_MS + 2 * 60_000 + 1)

    async def test_end_ms_filters_beyond(self) -> None:
        rows = [_kline_row(T0_MS + i * 60_000, "1", "2", "0.5", "1.5", "10") for i in range(4)]

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            end = int(params["endTime"])
            return httpx.Response(200, json=[row for row in rows if row[0] <= end])

        end_ms = T0_MS + 2 * 60_000
        async with _client(handler) as client:
            bars = await client.fetch_klines(
                "BTCUSDT", "1m", start_ms=T0_MS, end_ms=end_ms, limit=10
            )
        assert [b.open_time_ms for b in bars] == [T0_MS + i * 60_000 for i in range(3)]

    async def test_max_pages_guard_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.params.get("startTime", "0"))
            return httpx.Response(
                200,
                json=[
                    _kline_row(start + i * 60_000, "1", "2", "0.5", "1.5", "10") for i in range(2)
                ],
            )

        async with _client(handler, max_pages=3) as client:
            with pytest.raises(BinancePaginationError, match="سقف الصفحات"):
                await client.fetch_klines("BTCUSDT", "1m", start_ms=T0_MS, limit=2)

    @pytest.mark.parametrize("limit", [0, 1001, -5])
    async def test_limit_bounds_rejected(self, limit: int) -> None:
        async with _client(lambda request: httpx.Response(200, json=[])) as client:
            with pytest.raises(ValueError, match="limit"):
                await client.fetch_klines("BTCUSDT", "1m", limit=limit)

    async def test_inverted_range_rejected(self) -> None:
        async with _client(lambda request: httpx.Response(200, json=[])) as client:
            with pytest.raises(ValueError, match="end_ms أقدم"):
                await client.fetch_klines("BTCUSDT", "1m", start_ms=100, end_ms=50)


class TestFetchAggtrades:
    """ترقيم aggTrades الزمني: مقاطع دون ساعة + خصم المكرر عند نفس-ms."""

    async def test_pagination_same_ms_boundary_dedup(self) -> None:
        """7 صفقات بصفحات من 3 — إعادة جلب نفس المللي ثانية مع خصم المعرف."""
        rows = [
            _agg_row(1, 0),
            _agg_row(2, 1),
            _agg_row(3, 2),
            _agg_row(4, 3),
            _agg_row(5, 4),
            _agg_row(6, 5),
            _agg_row(7, 60_000),
        ]
        calls: list[dict[str, str]] = []
        async with _client(_aggtrades_api(rows, calls), page_size=3) as client:
            events = await client.fetch_aggtrades("BTCUSDT", 0, 120_000)
        assert [e.sequence_id for e in events] == [str(i) for i in range(1, 8)]
        assert all(e.venue == BINANCE_VENUE for e in events)
        # المؤشر يعود إلى T آخر صفقة في الصفحة (لا +1) فتعاد نفس-ms وتُخصم بالمعرف:
        # صفحة [5,6,7] ممتلئة → المؤشر T(7)=60000 → الطلب الأخير يعيد 7 وحده
        # (أقل من الحد) فيُخصم ويُختم المقطع — لا حدث يُفد ولا يُكرر نهائياً.
        assert calls[1]["startTime"] == "2"
        assert calls[2]["startTime"] == "4"
        assert calls[3]["startTime"] == "60000"
        assert calls[3]["limit"] == "3"

    async def test_window_chunks_under_one_hour(self) -> None:
        """نطاق 61 دقيقة — كل طلب أقل من ساعة (حد API) والمقاطع تغطي الكل."""
        rows = [_agg_row(1, 0), _agg_row(2, 61 * 60_000)]
        calls: list[dict[str, str]] = []
        async with _client(_aggtrades_api(rows, calls)) as client:
            events = await client.fetch_aggtrades("BTCUSDT", 0, 61 * 60_000)
        assert [int(e.sequence_id) for e in events if e.sequence_id is not None] == [1, 2]
        for params in calls:
            assert int(params["endTime"]) - int(params["startTime"]) < 3_600_000
        # مقطعان على الأقل: التقسيم الزمني فعلي لا اسمي
        assert len({params["endTime"] for params in calls}) >= 2

    async def test_empty_window_returns_no_events(self) -> None:
        calls: list[dict[str, str]] = []
        async with _client(_aggtrades_api([], calls)) as client:
            events = await client.fetch_aggtrades("BTCUSDT", 0, 1_000)
        assert events == []
        assert len(calls) == 1

    async def test_inverted_range_rejected(self) -> None:
        async with _client(lambda request: httpx.Response(200, json=[])) as client:
            with pytest.raises(ValueError, match="end_ms أقدم"):
                await client.fetch_aggtrades("BTCUSDT", 200, 100)


class TestRateLimits:
    """الاستراتيجية: Retry-Atter أولاً وإلا تراجع أُسي — ثم إحباط صاخب."""

    async def test_429_honors_retry_after_header(self) -> None:
        calls: list[dict[str, str]] = []
        sleep = _SleepRecorder()

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "2"})
            return httpx.Response(200, json=[])

        async with _client(handler, sleep=sleep) as client:
            bars = await client.fetch_klines("BTCUSDT", "1m", limit=5)
        assert bars == []
        assert len(calls) == 2
        assert sleep.calls == [2.0]  # ترويسة البورصة تتفوق على التراجع الأُسي

    async def test_418_exponential_backoff_without_header(self) -> None:
        calls: list[dict[str, str]] = []
        sleep = _SleepRecorder()

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            if len(calls) <= 2:
                return httpx.Response(418)
            return httpx.Response(200, json=[])

        async with _client(handler, sleep=sleep) as client:
            await client.fetch_klines("BTCUSDT", "1m", limit=5)
        assert sleep.calls == [1.0, 2.0]  # تراجع أُسي 1s→2s

    async def test_exhaustion_raises_original_status(self) -> None:
        sleep = _SleepRecorder()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        async with _client(handler, sleep=sleep, max_attempts=2) as client:
            with pytest.raises(httpx.HTTPStatusError) as excinfo:
                await client.fetch_klines("BTCUSDT", "1m", limit=5)
        assert excinfo.value.response.status_code == 429
        assert len(sleep.calls) == 1  # محاولتان إجمالًا = نوم واحد بينهما

    async def test_client_error_not_retried(self) -> None:
        calls: list[dict[str, str]] = []
        sleep = _SleepRecorder()

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

        async with _client(handler, sleep=sleep) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.fetch_klines("NOSUCH", "1m", limit=5)
        assert len(calls) == 1
        assert sleep.calls == []  # خطأ العميل لا يُعاد — ليس حد معدل


class TestClientConstruction:
    """حدود البناء: page_size وmax_attempts وسياق الإغلاق."""

    def test_page_size_bounds(self) -> None:
        with pytest.raises(ValueError, match="page_size"):
            BinanceRestClient(base_url=BASE, page_size=0)
        with pytest.raises(ValueError, match="page_size"):
            BinanceRestClient(base_url=BASE, page_size=1001)

    def test_max_attempts_positive(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):
            BinanceRestClient(base_url=BASE, max_attempts=0)

    async def test_context_manager_closes(self) -> None:
        async with _client(lambda request: httpx.Response(200, json=[])) as client:
            pass
        assert client._client.is_closed
