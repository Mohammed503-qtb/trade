"""اختبارات تكامل الويبهوك الحي — الخطوات الثماني §36 كاملة (بوابة 10).

علامة integration: تتطلب postgres حيًا + NATS حيًا + عملية الواجهة
(FastAPI على 4001). تختبر عبر واجهة HTTP الفعلية (httpx على التطبيق
المصعود مباشرة) — نفس المسارات التي تخدمها العملية.

عقد نهائي: أي تنبيه أُنشئ أثناء الاختبار يُنظف (القاعدة تُترك نظيفة).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest
from common.config import load_settings
from engine_api.api.webhook import NATS_SUBJECT, derive_idempotency_key
from schemas import AlertDeliveryStatus, TVAlertPayload

API = "http://127.0.0.1:4001"


def _payload(event: str, bar_ms: int, price: float = 111000.5) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "source": "tradingview",
        "alert_id": f"BINANCE_USDM:BTCUSDT|1|{event}|{bar_ms}",
        "instrument": "BINANCE_USDM:BTCUSDT",
        "bar_time_ms": bar_ms,
        "timeframe": "1",
        "event": event,
        "price": price,
    }


@pytest.mark.integration
class TestWebhookEightSteps:
    """الخطوات الثماني §36 — كل واحدة بفحصها الصريح."""

    async def test_step1_missing_or_wrong_token_rejected(self) -> None:
        async with httpx.AsyncClient(base_url=API, timeout=10.0) as client:
            no_token = await client.post("/api/tv/webhook", json=_payload("CHOCH", 1))
            assert no_token.status_code == 401
            assert no_token.json()["status"] == AlertDeliveryStatus.REJECTED_AUTH.value
            bad = await client.post(
                "/api/tv/webhook", params={"token": "definitely-wrong"}, json=_payload("CHOCH", 1)
            )
            assert bad.status_code == 401

    async def test_step2_corrupt_body_rejected(self) -> None:
        settings = load_settings()
        async with httpx.AsyncClient(base_url=API, timeout=10.0) as client:
            res = await client.post(
                "/api/tv/webhook",
                params={"token": settings.tv_webhook_secret},
                json={"garbage": True},
            )
            assert res.status_code == 422
            assert res.json()["status"] == AlertDeliveryStatus.REJECTED_SCHEMA.value

    async def test_steps_3_to_5_valid_alert_acked_fast_and_persisted(self) -> None:
        settings = load_settings()
        bar_ms = 1758970000000
        body = _payload("LIQUIDITY_SWEEP_LOW", bar_ms)
        payload = TVAlertPayload.model_validate(body)
        key = derive_idempotency_key(payload)
        conn = await asyncpg.connect(load_settings().database_url)
        try:
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            async with httpx.AsyncClient(base_url=API, timeout=10.0) as client:
                t0 = datetime.now(UTC)
                res = await client.post(
                    "/api/tv/webhook", params={"token": settings.tv_webhook_secret}, json=body
                )
                elapsed = (datetime.now(UTC) - t0).total_seconds()
                # (5) الإقرار الفوري — أسرع من 3 ثوانٍ بمراحل (§6.4).
                assert res.status_code == 200
                assert elapsed < 3.0
                ack = res.json()
                assert ack["status"] == AlertDeliveryStatus.RECEIVED.value
                assert ack["alert_key"] == key  # (D-07) اشتقاق الخادم حصرًا
                # (4) الحفظ الخام — الصف موجود بالجسم الخام. الحالة قد تكون
                # تقدمت بالفعل إلى PROCESSED (المعالجة الخلفية أسرع من قراءة
                # الاختبار عندما يكون التوليف ساخنًا — سلوك صحيح لا خلل).
                row = await conn.fetchrow(
                    "SELECT raw_body, status FROM alerts WHERE idempotency_key = $1", key
                )
                assert row is not None
                assert row["status"] in (
                    AlertDeliveryStatus.RECEIVED.value,
                    AlertDeliveryStatus.PROCESSED.value,
                    AlertDeliveryStatus.REJECTED_CANONICAL.value,
                )
                assert json.loads(row["raw_body"])["event"] == "LIQUIDITY_SWEEP_LOW"
                # (3) المكرر يُقر بلا صف ثانٍ.
                dup = await client.post(
                    "/api/tv/webhook", params={"token": settings.tv_webhook_secret}, json=body
                )
                assert dup.status_code == 200
                assert dup.json()["status"] == AlertDeliveryStatus.DUPLICATE.value
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM alerts WHERE idempotency_key = $1", key
                )
                assert count == 1
        finally:
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            await conn.close()

    async def test_step6_nats_publish_and_step7_revalidation(self) -> None:
        """النشر على NATS يُسمع فعليًا ثم إعادة التحقق توثق نتيجتها."""
        settings = load_settings()
        bar_ms = 1758970100000
        body = _payload("EXTERNAL_BOS", bar_ms)
        payload = TVAlertPayload.model_validate(body)
        key = derive_idempotency_key(payload)
        conn = await asyncpg.connect(load_settings().database_url)
        received: list[bytes] = []

        import nats
        from nats.aio.msg import Msg

        nc = await nats.connect(settings.nats_url)

        async def on_msg(msg: Msg) -> None:
            received.append(msg.data)

        await nc.subscribe(NATS_SUBJECT, cb=on_msg)
        try:
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            async with httpx.AsyncClient(base_url=API, timeout=15.0) as client:
                res = await client.post(
                    "/api/tv/webhook", params={"token": settings.tv_webhook_secret}, json=body
                )
                assert res.status_code == 200
            # (6) الرسالة وصلت الناقل بمغلفها.
            for _ in range(100):
                await nc.flush()
                await asyncio.sleep(0.1)
                if received:
                    break
            assert received, "لم تصل رسالة الناقل خلال المهلة"
            envelope = json.loads(received[0])
            assert envelope["idempotency_key"] == key
            assert envelope["payload"]["event"] == "EXTERNAL_BOS"
            # (7) إعادة التحقق الخلفية توثق نتيجتها على الصف.
            status: str | None = None
            for _ in range(600):  # حتى 120 ثانية (بناء التوليف أول مرة ثقيل)
                await asyncio.sleep(0.2)
                status = await conn.fetchval(
                    "SELECT status FROM alerts WHERE idempotency_key = $1", key
                )
                if status == AlertDeliveryStatus.PROCESSED.value:
                    break
            assert status == AlertDeliveryStatus.PROCESSED.value
            result = await conn.fetchval(
                "SELECT processing_result FROM alerts WHERE idempotency_key = $1", key
            )
            assert result is not None
            revalidation = json.loads(result)
            assert revalidation["matched"] is True
        finally:
            await nc.drain()
            await nc.close()
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            await conn.close()

    async def test_unknown_event_rejected_canonically_after_persist(self) -> None:
        """حدث خارج قاموس §20: يخزن ثم يرفض قانونيًا — لا ابتلاع صامت."""
        settings = load_settings()
        bar_ms = 1758970200000
        body = _payload("NOT_A_REAL_EVENT", bar_ms)
        payload = TVAlertPayload.model_validate(body)
        key = derive_idempotency_key(payload)
        conn = await asyncpg.connect(load_settings().database_url)
        try:
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            async with httpx.AsyncClient(base_url=API, timeout=15.0) as client:
                res = await client.post(
                    "/api/tv/webhook", params={"token": settings.tv_webhook_secret}, json=body
                )
                assert res.status_code == 200  # الخام يخزن دائمًا (خطوة 4)
            status: str | None = None
            for _ in range(300):
                await asyncio.sleep(0.2)
                status = await conn.fetchval(
                    "SELECT status FROM alerts WHERE idempotency_key = $1", key
                )
                terminal = (
                    AlertDeliveryStatus.PROCESSED.value,
                    AlertDeliveryStatus.REJECTED_CANONICAL.value,
                )
                if status in terminal:
                    break
            assert status == AlertDeliveryStatus.REJECTED_CANONICAL.value
        finally:
            await conn.execute("DELETE FROM alerts WHERE idempotency_key = $1", key)
            await conn.close()
