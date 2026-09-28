"""اختبار integration حي مقابل fapi.binance.com (علامة integration).

قد تكون الشبكة محجوبة في بيئة التنفيذ — فشل الاتصال (TransportError/OSError)
أو الحجب الجغرافي (403/451) يُحوَّل إلى pytest.skip نظيف لا فشلًا؛ أي خطأ
API آخر فشل حقيقي يُرفع.
"""

from __future__ import annotations

import asyncio
import itertools

import httpx
import pytest
from ingestion.binance import BINANCE_VENUE, BinanceRestClient, KlineBar
from schemas import TradeEvent

pytestmark = pytest.mark.integration


def _skip_on_network_failure(exc: BaseException) -> None:
    """سياسة التخطي النظيف: انقطاع/حجب الشبكة ليس فشل كود.

    تشمل ``TimeoutError`` (المهلة الصلبة للأداة أدناه): حل DNS المعلق في
    بيئة محجوبة قد لا تُلغيه مهلة httpx (خيط getaddrinfo لا يُقاطع) فالسقف
    الصلب حول الاستدعاء هو الحاسم — انتهاؤه تخطٍ لا فشل.
    """
    if isinstance(exc, (httpx.TransportError, OSError, TimeoutError)):
        pytest.skip(f"الشبكة محجوبة في هذه البيئة: {exc}")
    # 403/451 حجب جغرافي صريح؛ 418 «إبريق الشاي» هو رمز حظر/حجب Binance
    # الموثق (بعد استنفاد العميل محاولاته الشرعية) — كلاهما بيئة لا فشل كود
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (403, 451, 418):
        pytest.skip(f"البوابة محجوبة جغرافيًا: {exc.response.status_code}")
    raise exc


async def test_live_klines_fetch_and_convert() -> None:
    """10 شموع حية 1m من البورصة المرجعية — التحويل والعقد سليمان.

    عميل سريع الفشل (محاولتان بتراجع لطيف): البيئة المحجوبة جغرافيًا
    تستنفد محاولاتها في أجزاء الثانية فتتخطى نظيفًا بدل انتظار التراجع
    الكامل (1+2+4+8 ثوانٍ لكل طلب) — استراتيجية العميل الكاملة تختبرها
    وحدات المحاكاة بلا شبكة.
    """
    async with BinanceRestClient(max_attempts=1) as client:
        try:
            bars = await asyncio.wait_for(
                client.fetch_klines("BTCUSDT", "1m", limit=10), timeout=30
            )
        except (httpx.TransportError, OSError, httpx.HTTPStatusError, TimeoutError) as exc:
            _skip_on_network_failure(exc)
            raise AssertionError("غير قابل للوصول") from exc
    # الحد أقصى لا ضمان عددي — البيانات الحية قد تعيد أقل عند حدود الدقيقة
    assert 1 <= len(bars) <= 10, f"عدد غير معقول من الشموع الحية: {len(bars)}"
    for previous, current in itertools.pairwise(bars):
        assert current.open_time_ms > previous.open_time_ms  # تراتب زمني
    for bar in bars:
        assert bar.high >= max(bar.open, bar.close, bar.low)
        assert bar.low <= min(bar.open, bar.close, bar.high)
        assert bar.close_time_ms > bar.open_time_ms


async def test_live_aggtrades_match_closed_kline_extremes() -> None:
    """مجموع تحقق متقاطع: قمة/قاع الشمعة المكتملة يحتضنان صفقات نافذتها.

    خذ آخر شمعة مكتملة (الأخيرة متشكلة بعد)، اجلب aggTrades نافذتها الزمنية
    بالضبط، وتحقق: high ≥ أقصى سعر صفقة، low ≤ أدنى سعر، ومجموع الكميات
    يقارب حجم الشمعة (تسامح 1% لحدود المللي ثانية).
    """

    async def _fetch_pair() -> tuple[KlineBar, list[TradeEvent]]:
        # العميل كله داخل السقف الصلب (إلغاء aclose المنتظر خيط DNS معلقًا)
        async with BinanceRestClient(max_attempts=1) as client:
            bars = await client.fetch_klines("BTCUSDT", "1m", limit=10)
            closed = bars[-2]
            events = await client.fetch_aggtrades(
                "BTCUSDT", closed.open_time_ms, closed.close_time_ms
            )
            return closed, events

    try:
        closed, events = await asyncio.wait_for(_fetch_pair(), timeout=45)
    except (httpx.TransportError, OSError, httpx.HTTPStatusError, TimeoutError) as exc:
        _skip_on_network_failure(exc)
        raise AssertionError("غير قابل للوصول") from exc
    assert isinstance(closed, KlineBar)
    assert events, "دقيقة مكتملة لـBTCUSDT يجب أن تحمل صفقات"
    prices = [event.price for event in events]
    times = [event.event_time_utc for event in events]
    assert all(event.venue == BINANCE_VENUE for event in events)
    assert all(event.symbol == "BTCUSDT" for event in events)
    assert all(event.sequence_id is not None for event in events)
    assert times == sorted(times), "الرد مرتب تصاعديًا (افتراض موثق في العميل)"
    assert closed.high >= max(prices), "قمة الشمعة يجب أن تحتضن أقصى سعر صفقة نافذتها"
    assert closed.low <= min(prices), "قاع الشمعة يجب أن يحتضن أدنى سعر صفقة نافذتها"
    total_quantity = sum(event.quantity for event in events)
    assert abs(total_quantity - closed.volume) <= max(0.01 * closed.volume, 1e-9)
