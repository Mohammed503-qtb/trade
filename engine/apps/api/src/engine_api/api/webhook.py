"""مسار الويبهوك — الخطوات الثماني §36 حرفيًا (D-09 + D-07).

الحافة العامة مسار Next ‎/api/tv/webhook‎ يمرر إلى هنا عبر نمط المنصة
(‎?XTransformPort=4001‎) — التوكن في معامل الاستعلام حصرًا (TV لا يضبط
ترويسات مخصصة) ولا أسرار في الجسم أبدًا (§6.4/§37.1).

الخطوات الثماني (كل واحدة موثقة عند موقعها):
1. المصادقة — مقارنة زمنية ثابتة على التوكن.
2. تحقق المخطط — TVAlertPayload (حقول §36 الثمانية).
3. فحص التكرار — قيد فريد على مفتاح D-07 المشتق خادميًا.
4. حفظ الخام — جدول alerts (§31.6) بايت-بايت.
5. الإقرار الفوري — أسرع من 3 ثوانٍ بمراحل (§6.4).
6. النشر على NATS — tv.alert.received بمغلف TVAlertEnvelope.
7. إعادة التحقق القانوني — خلفية مقابل التوليف القانوني.
8. المخاطرة حينها فقط — توثق ولا أمر حي في MVP (المرحلة 11 مؤجلة).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import nats
import structlog
from asyncpg import Pool
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from schemas import (
    AlertDeliveryStatus,
    AlertRevalidation,
    TVAlertPayload,
    WebhookAck,
)

from ..composition import build_overview
from ..settings_bridge import get_pool, get_settings

log = structlog.get_logger(__name__)

router = APIRouter()

#: موضوع الناقل لاستقبال التنبيهات (المستهلك: إعادة التحقق ثم المخاطرة).
NATS_SUBJECT = "tv.alert.received"


def derive_idempotency_key(payload: TVAlertPayload) -> str:
    """مفتاح D-07 — يشتقه الخادم حصرًا فوق الحقول الخمسة الخام.

    ``sha256(schema_version|source|alert_id|instrument|bar_time|event)``
    حيث ``bar_time`` هو ``bar_time_ms`` — حتمي قابل لإعادة الإنتاج ولا
    ثقة بمفتاح وافد إطلاقًا.
    """
    material = "|".join(
        (
            payload.schema_version,
            payload.source,
            payload.alert_id,
            payload.instrument,
            str(payload.bar_time_ms),
            payload.event,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _auth_ok(provided: str | None, expected: str) -> bool:
    """مقارنة زمنية ثابتة — لا تسريب توقيت (§37.1)."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


@router.post("/api/tv/webhook")
async def tv_webhook(request: Request) -> JSONResponse:
    """استقبال تنبيه Pine — الخطوات الثماني §36."""
    settings = get_settings()
    pool: Pool = get_pool()

    # (1) المصادقة — التوكن في معامل الاستعلام حصرًا.
    token = request.query_params.get("token")
    if not _auth_ok(token, settings.tv_webhook_secret):
        log.warning("webhook_auth_rejected")
        return JSONResponse({"status": AlertDeliveryStatus.REJECTED_AUTH.value}, status_code=401)

    # (2) تحقق المخطط — الجسم الخام الثمانية حقول.
    try:
        body = await request.json()
        payload = TVAlertPayload.model_validate(body)
    except Exception:
        log.warning("webhook_schema_rejected")
        return JSONResponse({"status": AlertDeliveryStatus.REJECTED_SCHEMA.value}, status_code=422)

    # (3) مفتاح D-07 المشتق خادميًا + فحص التكرار (4) الحفظ الخام.
    key = derive_idempotency_key(payload)
    alert_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"alert|{key}"))
    received_at = datetime.now(UTC)
    bar_time = datetime.fromtimestamp(payload.bar_time_ms / 1000.0, tz=UTC)
    raw_body = json.dumps(body, sort_keys=True, ensure_ascii=False)

    async with pool.acquire() as conn:
        inserted = await conn.fetchval(
            """
            INSERT INTO alerts (
                alert_id, idempotency_key, schema_version, source,
                source_alert_id, instrument, bar_time, timeframe, event,
                price, raw_body, status, received_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING alert_id
            """,
            alert_uuid,
            key,
            payload.schema_version,
            payload.source,
            payload.alert_id,
            payload.instrument,
            bar_time,
            payload.timeframe,
            payload.event,
            payload.price,
            raw_body,
            AlertDeliveryStatus.RECEIVED.value,
            received_at,
        )
    if inserted is None:
        # مكرر — إقرار بلا معالجة ثانية (§36 خطوة 3: idempotent).
        log.info("webhook_duplicate", alert_key=key[:12])
        ack = WebhookAck(
            status=AlertDeliveryStatus.DUPLICATE,
            alert_key=key,
            received_at=datetime.now(UTC),
        )
        return JSONResponse(ack.model_dump(mode="json"), status_code=200)

    # (5) الإقرار الفوري — العمل الثقيل خلفي (§6.4: أسرع من 3 ثوانٍ).
    # (6) النشر على NATS + (7/8) إعادة التحقق القانوني خلفية.
    task = asyncio.create_task(_process_async(payload, key, alert_uuid))
    task.add_done_callback(_log_task_failure)

    ack = WebhookAck(status=AlertDeliveryStatus.RECEIVED, alert_key=key, received_at=received_at)
    return JSONResponse(ack.model_dump(mode="json"), status_code=200)


def _log_task_failure(task: asyncio.Future[None]) -> None:
    """لا ابتلاع صامت لفشل المعالجة الخلفية — يوثق ويستمر الخدمة."""
    if not task.cancelled() and task.exception() is not None:
        log.error("webhook_background_failed", error=repr(task.exception()))


async def _process_async(payload: TVAlertPayload, key: str, alert_uuid: str) -> None:
    """المعالجة الخلفية: النشر على NATS ثم إعادة التحقق القانوني (7-8)."""
    settings = get_settings()
    pool: Pool = get_pool()
    # (6) النشر على NATS بمغلف العقود المُصدَّرة.
    try:
        envelope = {
            "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"envelope|{key}")),
            "schema_version": payload.schema_version,
            "idempotency_key": key,
            "source": payload.source,
            "event_time": datetime.fromtimestamp(payload.bar_time_ms / 1000.0, tz=UTC).isoformat(),
            "receive_time": datetime.now(UTC).isoformat(),
            "payload": payload.model_dump(mode="json"),
        }
        nc = await nats.connect(settings.nats_url)
        await nc.publish(NATS_SUBJECT, json.dumps(envelope).encode("utf-8"))
        await nc.drain()
    except Exception:
        # فشل النشر لا يفقد التنبيه (الخام مخزون) — يوثق ويمضي.
        log.error("webhook_nats_publish_failed", alert_key=key[:12])

    # (7) إعادة التحقق القانوني: الحدث المعلن يطابق الحالة القانونية؟
    revalidation = await _revalidate_canonical(payload)
    status = (
        AlertDeliveryStatus.PROCESSED
        if revalidation.matched
        else AlertDeliveryStatus.REJECTED_CANONICAL
    )
    # (8) المخاطرة حينها فقط — موثقة داخل نتيجة إعادة التحقق؛ لا أمر
    # حي في MVP (التنفيذ مؤجل للمرحلة 11 معلنًا).
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE alerts
            SET status = $1, processing_result = $2, processed_at = $3
            WHERE alert_id = $4
            """,
            status.value,
            json.dumps(revalidation.model_dump(mode="json"), ensure_ascii=False),
            datetime.now(UTC),
            alert_uuid,
        )
    log.info("webhook_processed", alert_key=key[:12], status=status.value)


#: مجموعة الأحداث القابلة للتنبيه من المؤشر (pine/alerts/README.md) —
#: عائلات البنية والسيولة التي تبثها كواشف المحرك نفسها.
PINE_ALERTABLE = frozenset(
    {
        "LIQUIDITY_SWEEP_HIGH",
        "LIQUIDITY_SWEEP_LOW",
        "BREAK_AND_ACCEPT_HIGH",
        "BREAK_AND_ACCEPT_LOW",
        "EXTERNAL_BOS",
        "INTERNAL_BOS",
        "CHOCH",
    }
)


async def _revalidate_canonical(payload: TVAlertPayload) -> AlertRevalidation:
    """إعادة التحقق القانوني (§36 خطوة 7) ضد التوليف الحتمي.

    التنبيه إشارة مرشحة فقط (§36) — المحرك القانوني يعيد قراءة الحالة
    قبل أي تخويل: (أ) الحدث ضمن قاموس §20؟ (ب) من عائلة يبثها كواشف
    المحرك (مجموعة المؤشر القابلة للتنبيه)؟ (ج) الأداة تطابق أدوات
    التوليف القانوني الحي؟ (د) الاستدلال الحتمي يعمل (أثر قائم)؟
    المطابقة الزمنية العميقة للحظة-بلحظة مرحلة الابتلاع الحي (11) —
    الحد المعلن موثق في ADR-028.
    """
    from schemas import EventType

    try:
        EventType(payload.event)
    except ValueError:
        return AlertRevalidation(
            matched=False,
            detail=f"حدث خارج قاموس §20: {payload.event}",
        )
    try:
        overview = await asyncio.to_thread(build_overview)
    except Exception as exc:  # pragma: no cover — تحوط تشغيلي موثق
        return AlertRevalidation(
            matched=False,
            detail=f"فشل بناء الحالة القانونية: {type(exc).__name__}",
        )

    def _symbol_of(instrument: str) -> str:
        return instrument.rsplit(":", 1)[-1].rsplit("|", 1)[-1]

    # فحص الرمز (لا بادئة المقر): تسمية TV قد تختلف عن تسمية المحرك
    # (BINANCE:BTCUSDT مقابل BINANCE_USDM:BTCUSDT) — الرمز هو المشترك.
    family_ok = payload.event in PINE_ALERTABLE
    instrument_ok = _symbol_of(payload.instrument) == "BTCUSDT"
    reasoning_alive = len(overview.traces) > 0
    matched = family_ok and instrument_ok and reasoning_alive
    risk_outcome = (
        f"مرخّص {overview.counts.authorized} من {overview.counts.risk_decisions} قرارًا"
        if overview.counts.risk_decisions > 0
        else None
    )
    reasons = []
    if not family_ok:
        reasons.append("الحدث من عائلة لا يبثها المؤشر")
    if not instrument_ok:
        reasons.append("الأداة خارج توليف الحالة القانونية")
    if not reasoning_alive:
        reasons.append("لا أثر استدلال قائمًا")
    return AlertRevalidation(
        matched=matched,
        scenario_id=overview.traces[0].scenario_id if matched and overview.traces else None,
        risk_outcome=risk_outcome if matched else None,
        detail=(
            "الحدث ضمن قاموس §20 وعائلة المؤشر والأداة والتوليف الحتمي حي"
            if matched
            else "؛ ".join(reasons)
        ),
    )
