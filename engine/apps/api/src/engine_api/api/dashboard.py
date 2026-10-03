"""مسارات اللوحة — قراءة الحالة القانونية للواجهة (§35.2 + §35.3).

مساران فقط (لا شيء آخر يكشف):
- ‎GET /api/dashboard/overview‎: اللقطة الكاملة (لوحة + سيناريوهات +
  أثر استدلال + سجل رفض + تنفيذ + تنبيهات حديثة + خلاصة المطابقة).
- ‎GET /api/dashboard/alerts‎: سجل تسليم تنبيهات الويبهوك (§31.6).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from ..composition import build_overview
from ..settings_bridge import get_pool

router = APIRouter()


@router.get("/api/dashboard/overview")
async def dashboard_overview() -> ORJSONResponse:
    """اللقطة الكاملة للوحة الدنيا — بيانات فعلية من التوليف القانوني."""
    pool = get_pool()
    alerts: list[dict[str, object]] = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT idempotency_key, instrument, event, status, received_at "
            "FROM alerts ORDER BY received_at DESC LIMIT 10"
        )
        alerts = [dict(r) for r in rows]
    import asyncio

    # to_thread: بناء التوليف عمل حسابي ثقيل أول مرة — لا يسدّ الحلقة.
    overview = await asyncio.to_thread(build_overview, alerts)
    return ORJSONResponse(overview.model_dump(mode="json"))


@router.get("/api/dashboard/alerts")
async def dashboard_alerts(limit: int = 50) -> ORJSONResponse:
    """سجل تسليم التنبيهات — الأحدث أولاً (§31.6)."""
    pool = get_pool()
    bounded = max(1, min(limit, 200))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT alert_id, idempotency_key, instrument, event, timeframe, "
            "price, status, received_at, processed_at, processing_result "
            "FROM alerts ORDER BY received_at DESC LIMIT $1",
            bounded,
        )
    return ORJSONResponse(
        {
            "alerts": [
                {
                    "alert_key": r["idempotency_key"],
                    "instrument": r["instrument"],
                    "event": r["event"],
                    "timeframe": r["timeframe"],
                    "price": r["price"],
                    "status": r["status"],
                    "received_at": r["received_at"].isoformat(),
                    "processed_at": r["processed_at"].isoformat() if r["processed_at"] else None,
                    "processing_result": r["processing_result"],
                }
                for r in rows
            ]
        }
    )
