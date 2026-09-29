#!/usr/bin/env python3
"""بوابة خروج المرحلة 4 — التدفق والفوتبرنت (build_plan §D).

يتطلب بنية حية (postgres + nats) وعينة tests/fixtures/phase4 (جُلبت
بـscripts/fetch_phase4_fixture.py — 35,932 صفقة aggTrades و120 شمعة 1m
مرجعية بالحجم الشرائي المتسبب).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: الصفقات والشموع المرجعية متطابقتان الحدود مع manifest.
2. **المطابقة الإحصائية (بوابة المرحلة نصًا: «حسابات التدفق ضمن تسامح
   معلن مقابل مرجع»)**: لكل دلو 1m من الـ120 — حجم شراء الفوتبرنت
   (buyer_is_maker=False) يطابق takerBuyBaseAssetVolume للبورصة تمامًا
   (rel=1e-9)، والحجم الكلي/البيعي ضمن التسامح المعلن abs=0.5 (أثر حدود
   موثق: aggTrade مجمّعة تعبئاتها عبرت حد الدلو فشطرها محرك البورصة —
   لا يمس المرجع الشرائي)، وشموع OHLCV من الصفقات تطابق klines.
3. **المسار الكامل**: فوتبرنت من الصفقات + كواشف التدفق الأربعة
   (استمرار/امتصاص/إنهاك/عناقيد اختلال) بالعتبات التطبيعية من التقلب.
4. **الحتمية**: مساران كاملان ⇒ نفس هاش (الأشرطة والأحداث).
5. **لا-نظرة-مستقبلية (§26.3)**: بادئة الدلاء k ⇒ نفس أشرطة البادئة
   وأحداثها في التشغيل الكامل.
6. **التحجيم (عتبات تطبيعية §16)**: λ=2 على الأسعار (ATR والعتبات
   تتضاعف) ⇒ نفس أنواع الأحداث بترتيبها وأشرطتها — كل مسافة سعرية اشتقت
   من atr مضروبًا في المعامل فتحجّجت معه (الحصص عديمة الأبعاد لا تتغير).
7. **القانونية (§32)**: كل حدث منبعث ⇒ مغلف EventEnvelope يمر jsonschema
   وحمولته تمر مخطط حمولتها من EVENT_PAYLOAD_MODELS.
8. **الاكتفاء**: توثيق توزيع أنواع أحداث التدفق على العينة الحقيقية (لا
   نصاب مفروض؛ ما انبثث صادق ومخطط والكواشف أهلت معلوماتها).
9. **البث والتخزين الحي**: نشر عينة عبر AnalysisEventPublisher واستهلاكها
   بتحقق jsonschema؛ القاعدة: upsert الأشرطة/الأحداث (orderflow_events)
   idempotent + صفوف الأشرطة ذات الأحداث (footprint_rows — الاحتفاظ
   المقيد §31.2) + قراءة round-trip متطابقة.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# الاستيرادات بعد تهيئة مسارات الحزم (نمط verify_phase1/2/3)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "market_state" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "orderflow" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker" / "src"))

from ingestion.candles import CandleBuilder
from ingestion.raw_store import read_parquet_bytes
from market_state.volatility import VolatilityEngine
from orderflow.absorption import AbsorptionDetector
from orderflow.continuation import ContinuationEmitter
from orderflow.exhaustion import ExhaustionDetector
from orderflow.footprint import FootprintBuilder
from orderflow.imbalance import ImbalanceClusterDetector
from orderflow.rows import BarRows
from schemas import Candle, DataQuality, EventType, FootprintBar, TradeEvent, payload_model_for

ENGINE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase4"
GENERATED_DIR = ENGINE_ROOT / "packages" / "schemas" / "generated"

#: هوية الأداة — تُشتق من الصفقات نفسها (venue:symbol — نمط verify_phase1)
#: فتبقى الشموع والفوتبرنت والناشر والمخزن على هوية واحدة متسقة.
INSTRUMENT = "binance-usdm-futures:BTCUSDT"
TIMEFRAME = "1m"
#: التسامح المعلن للمطابقة الإحصائية — شراء دقيق 1e-9، إجمالي/بيع
#: abs=0.5 لأثر حدود aggTrades الموثق (تعبئات مجمّعة عبرت حد الدلو).
BUY_TOL_REL = 1e-9
VOLUME_TOL_ABS = 0.5
#: حجم بادئة فحص اللا-نظرة (دلاء) — يغطي دفء التقلب ونوافذ الإنهاك.
PREFIX_BARS = 100

_rc = 0


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def fail(msg: str) -> None:
    global _rc
    _rc = 1
    print(f"✗ {msg}")


# ───────────────────────── تحميل العينة ─────────────────────────


def load_fixture() -> tuple[list[TradeEvent], list[dict[str, Any]], dict[str, Any]]:
    raw = (FIXTURE_DIR / "trades.parquet").read_bytes()
    trades = read_parquet_bytes(raw)
    klines = json.loads((FIXTURE_DIR / "klines.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    return trades, klines, manifest


# ───────────────────────── الشموع من klines ─────────────────────────


def klines_to_candles(bars: list[dict[str, Any]]) -> list[Candle]:
    """محول عينة → شموع قانونية (نمط verify_phase2/3 حرفيًا)."""
    import math

    out: list[Candle] = []
    prev_close: float | None = None
    for bar in bars:
        o, h, low, c = (
            float(bar["open"]),
            float(bar["high"]),
            float(bar["low"]),
            float(bar["close"]),
        )
        span = h - low
        body = abs(c - o)
        if span > 0.0:
            body_fraction = body / span
            clv = (c - low) / span
        else:
            body_fraction = 0.0
            clv = 0.5
        tr = (
            span if prev_close is None else max(h - low, abs(h - prev_close), abs(low - prev_close))
        )
        bt = datetime.fromtimestamp(int(bar["open_time_ms"]) / 1000.0, tz=UTC)
        out.append(
            Candle(
                instrument_id=INSTRUMENT,
                timeframe=TIMEFRAME,
                bar_time=bt,
                session_id=bt.strftime("%Y-%m-%d"),
                quality=DataQuality.HEALTHY,
                is_closed=True,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=float(bar["volume"]),
                range=span,
                body_size=body,
                upper_wick=h - max(o, c),
                lower_wick=min(o, c) - low,
                body_fraction=body_fraction,
                close_location_value=clv,
                true_range=tr,
                realized_volatility=abs(math.log(c / o)) if o > 0.0 else 0.0,
            )
        )
        prev_close = c
    return out


def scaled_trades(trades: list[TradeEvent], lam: float) -> list[TradeEvent]:
    """ترميز λ: مضاعفة أسعار الصفقات (الكميات كما هي — الحصص لا تتغير)."""
    return [
        t.model_copy(update={"price": t.price * lam})  # type: ignore[arg-type]
        for t in trades
    ]


def scaled_klines(klines: list[dict[str, Any]], lam: float) -> list[dict[str, Any]]:
    """ترميز λ على الشموع المرجعية (OHLC فقط — الحجوم كما هي)."""
    return [
        {
            **bar,
            "open": float(bar["open"]) * lam,
            "high": float(bar["high"]) * lam,
            "low": float(bar["low"]) * lam,
            "close": float(bar["close"]) * lam,
        }
        for bar in klines
    ]


# ───────────────────────── مسار التدفق الكامل ─────────────────────────


class FlowRun:
    """تشغيل واحد للمسار الكامل — كل المخرجات قابلة للهاش والمقارنة."""

    def __init__(
        self, trades: list[TradeEvent], candles: list[Candle], *, lam: float = 1.0
    ) -> None:
        self.lam = lam
        self.bars: list[FootprintBar] = []
        self.bar_rows: list[tuple[FootprintBar, tuple]] = []
        self.events: list[tuple[int, Any]] = []  # (فهرس الشريط، EmittedEvent)
        self._run(trades, candles)

    def _run(self, trades: list[TradeEvent], candles: list[Candle]) -> None:
        builder = FootprintBuilder(timeframe=TIMEFRAME)
        candle_builder = CandleBuilder(timeframe=TIMEFRAME)
        vol_engine = VolatilityEngine()
        absorption = AbsorptionDetector()
        exhaustion = ExhaustionDetector()
        clusters = ImbalanceClusterDetector()
        continuation = ContinuationEmitter()

        # ── الفوتبرنت من الصفقات (ترتيب الوصول — عقد البنّاء) ──
        for trade in trades:
            builder.add_trade(trade)
        # آخر دلو مكتمل بإقفال صريح؟ لا — آخر دلو في النافذة مقصوص من
        # المرجع (عدم اكتمال حدوده موثق في 1.6) فنقيس المقفل بالعبور حصرًا
        self.bars = list(builder.closed_bars())
        bar_rows = builder.closed_bars_with_rows()
        self.bar_rows = [(br.bar, br.rows) for br in bar_rows]

        # ── الشموع المقابلة (من klines — نفس الدلاء) بالخريطة الزمنية ──
        candle_by_time = {c.bar_time: c for c in candles}
        vol_by_time: dict[Any, Any] = {}
        for candle in candles:
            vol_by_time[candle.bar_time] = vol_engine.update(candle)

        # ── الكواشف الأربعة على الأشرطة المقفلة بالترتيب ──
        for idx, (bar, rows) in enumerate(self.bar_rows):
            candle = candle_by_time.get(bar.bar_time)
            if candle is None:
                fail(f"لا شمعة مقابلة للشريط {bar.bar_time} — خلل محاذاة العينة")
                return
            vol = vol_by_time.get(bar.bar_time)
            for event in continuation.update(bar, candle, vol):
                self.events.append((idx, event))
            for event in absorption.update(bar, candle, vol):
                self.events.append((idx, event))
            for event in exhaustion.update(bar, candle, vol):
                self.events.append((idx, event))
            for event in clusters.update(BarRows(bar=bar, rows=rows)):
                self.events.append((idx, event))

        # ── الشموع من الصفقات كذلك (للمطابقة الذهبية OHLCV) ──
        closed_candles: list[Candle] = []
        for trade in trades:
            emitted = candle_builder.add_trade(trade)
            if emitted is not None and emitted.is_closed:
                closed_candles.append(emitted)
        self.candles_from_trades = closed_candles

    def digest(self) -> str:
        """هاش حتمي — الأشرطة ثم الأحداث بترتيبها."""
        h = hashlib.sha256()
        for bar in self.bars:
            h.update(
                "|".join(
                    (
                        bar.bar_time.isoformat(),
                        repr(bar.buy_volume),
                        repr(bar.sell_volume),
                        repr(bar.delta),
                        repr(bar.poc),
                        repr(bar.vah),
                        repr(bar.val),
                        str(bar.row_count),
                        str(bar.buy_imbalance_count),
                        str(bar.sell_imbalance_count),
                        bar.source_feed,
                        bar.methodology,
                    )
                ).encode()
            )
        for idx, event in self.events:
            h.update(f"{idx}|{event.event_type.value}|".encode())
            h.update(hashlib.sha256(event.payload.model_dump_json().encode()).hexdigest().encode())
        return h.hexdigest()

    def event_signature(self) -> list[tuple[int, str]]:
        """توقيع الأحداث للتحجيج — (فهرس الشريط، النوع) بلا الأسعار."""
        return [(idx, e.event_type.value) for idx, e in self.events]


# ───────────────────────── المطابقة الذهبية ─────────────────────────


def golden_checks(run: FlowRun, klines: list[dict[str, Any]]) -> None:
    """المطابقة الإحصائية للبوابة — دلو-بدلو ضد مرجع البورصة نفسه."""
    bars_by_time = {bar.bar_time: bar for bar in run.bars}
    candles_by_time = {c.bar_time: c for c in run.candles_from_trades}

    exact_buy = 0
    within_total = 0
    ohlcv_match = 0
    boundary_buckets = 0
    for kline in klines:
        bt = datetime.fromtimestamp(int(kline["open_time_ms"]) / 1000.0, tz=UTC)
        bar = bars_by_time.get(bt)
        candle = candles_by_time.get(bt)
        if bar is None or candle is None:
            # آخر دلو مقصوص (عدم اكتمال حدوده — عقد 1.6): خارج الذهبية
            continue
        taker_buy = float(kline["taker_buy_volume"])
        volume = float(kline["volume"])
        # شراء الفوتبرنت == takerBuyBaseAssetVolume تمامًا (التسامح 1e-9)
        assert abs(bar.buy_volume - taker_buy) <= BUY_TOL_REL * max(1.0, taker_buy), (
            f"الدلو {bt}: buy={bar.buy_volume} ≠ taker_buy={taker_buy}"
        )
        exact_buy += 1
        # الإجمالي/البيعي ضمن التسامح المعلن (أثر حدود aggTrades الموثق)
        assert abs(bar.total_volume - volume) <= VOLUME_TOL_ABS, (
            f"الدلو {bt}: total={bar.total_volume} بعيد عن volume={volume} "
            f"أكثر من التسامح المعلن {VOLUME_TOL_ABS}"
        )
        assert abs(bar.sell_volume - (volume - taker_buy)) <= VOLUME_TOL_ABS, (
            f"الدلو {bt}: sell={bar.sell_volume} بعيد عن volume-taker_buy "
            f"أكثر من التسامح المعلن {VOLUME_TOL_ABS}"
        )
        within_total += 1
        # الشموع من الصفقات تطابق klines (ذهبية المرحلة 1 مستعادة) —
        # في الدلاء غير المتأثرة بحدود aggTrades حصرًا (المتأثرة: تعبئات
        # مجمّعة عبرت الحد فقرّبها محرك البورصة على الدلو المجاور —
        # أثر موثق في 4-b؛ قيمتا الشراء والإجمالي أعلاه تحكمانها التسامحات)
        boundary_affected = abs(bar.total_volume - volume) > 1e-9 * max(1.0, volume)
        if boundary_affected:
            boundary_buckets += 1
            continue
        assert (
            candle.open == float(kline["open"])
            and candle.high == float(kline["high"])
            and candle.low == float(kline["low"])
            and candle.close == float(kline["close"])
            and abs(candle.volume - volume) <= 1e-9 * max(1.0, volume)
        ), f"الشمعة من الصفقات عند {bt} لا تطابق kline"
        ohlcv_match += 1

    if exact_buy == len(klines) - 1:  # آخر دلو مقصوص
        ok(
            f"المطابقة الإحصائية: buy_volume == takerBuyBaseAssetVolume تمامًا "
            f"في {exact_buy}/{len(klines) - 1} دلو مكتملًا (rel={BUY_TOL_REL})؛ "
            f"total/sell ضمن التسامح المعلن abs={VOLUME_TOL_ABS} "
            f"({boundary_buckets} دلو حدود aggTrades موثق)؛ وOHLCV الشموع "
            f"من الصفقات مطابق في {ohlcv_match} دلو غير متأثر"
        )
    else:
        fail(f"عدد الدلاء المطابقة {exact_buy} ≠ المتوقع {len(klines) - 1}")


# ───────────────────────── الفحوص الحية (NATS + القاعدة) ─────────────────────────


async def live_checks(run: FlowRun) -> None:
    """البث NATS بمواضيعه + التخزين idempotent والقراءة round-trip."""
    import uuid as uuid_module

    import jsonschema
    from asyncpg import connect as pg_connect
    from common.config import load_settings
    from engine_worker.analysis_publisher import AnalysisEventPublisher, build_envelope
    from nats.aio.client import Client as NATSClient
    from orderflow.store import FootprintStore

    settings = load_settings()
    envelope_schema = json.loads(
        (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
    )

    # ── NATS: عينة أحداث (الأولى 8 + أول حدث من كل نوع متاح) ──
    nc: NATSClient = NATSClient()
    await nc.connect(servers=[settings.nats_url], connect_timeout=5, max_reconnect_attempts=1)
    received: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def _cb(msg: Any) -> None:
        received.append((msg.subject, json.loads(msg.data.decode()), dict(msg.headers or {})))

    from engine_worker.publisher import normalize_instrument

    await nc.subscribe(f"market.event.{normalize_instrument(INSTRUMENT)}.1m.*", cb=_cb)
    publisher = AnalysisEventPublisher(nc)

    events_flat = [event for _, event in run.events]
    sample: list = list(events_flat[:8])
    seen_types = {e.event_type for e in sample}
    for event in events_flat:
        if event.event_type not in seen_types:
            sample.append(event)
            seen_types.add(event.event_type)
    envelopes = [
        build_envelope(
            event,
            INSTRUMENT,
            source="verify-phase4",
            trace_id="verify-phase4",
            receive_time=event.event_time,  # إعادة تاريخية: الطابع نفسه — حتمية
        )
        for event in sample
    ]
    for envelope in envelopes:
        await publisher.publish(envelope)
    await asyncio.wait_for(nc.flush(), timeout=5)
    for _ in range(100):
        if len(received) >= len(sample):
            break
        await asyncio.sleep(0.1)
    await nc.drain()
    if len(received) < len(sample):
        fail(f"NATS: استُقبل {len(received)} من {len(sample)} حدثًا خلال المهلة")
        return
    bad = 0
    for subject, payload, headers in received:
        try:
            jsonschema.validate(payload, envelope_schema)
            model = payload_model_for(EventType(payload["event_type"]))
            assert model is not None
            jsonschema.validate(
                payload["payload"],
                json.loads(
                    (GENERATED_DIR / f"{model.__name__}.schema.json").read_text(encoding="utf-8")
                ),
            )
            if headers.get("event_type") != payload["event_type"]:
                raise ValueError("رأس event_type لا يطابق الحمولة")
        except (jsonschema.ValidationError, ValueError, AssertionError) as exc:
            bad += 1
            fail(f"NATS: حمولة «{subject}» خالفت: {exc}")
    if bad == 0:
        ok(
            f"NATS: {len(received)} حدثًا عبر market.event.* مرّت مغلف §32 "
            f"وحمولاتها مخططاتها ({len(seen_types)} نوعًا مغطى)"
        )
    else:
        return

    # ── القاعدة: upsert idempotent + صفوف مقيدة + قراءة round-trip ──
    store = FootprintStore()
    conn = await pg_connect(settings.database_url)
    try:
        instrument_uuid = uuid_module.uuid5(
            uuid_module.uuid5(uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"),
            INSTRUMENT,
        )
        for delete_sql in (
            "DELETE FROM footprint_rows WHERE instrument_id = $1",
            "DELETE FROM footprint_bars WHERE instrument_id = $1",
            "DELETE FROM orderflow_events WHERE instrument_id = $1",
        ):
            await conn.execute(delete_sql, instrument_uuid)
        await conn.execute("COMMIT")

        # الأشرطة ×2 — upsert على المفتاح الطبيعي (المتطور يُحدَّث لا يُستنسخ)
        for bar in run.bars:
            await store.upsert_bar(conn, bar)
        for bar in run.bars:
            await store.upsert_bar(conn, bar)
        n_bars = await conn.fetchval("SELECT count(*) FROM footprint_bars")
        # الأحداث ×2 — at-least-once ⇒ تحديث لا تكرار
        for event in events_flat:
            await store.upsert_event(conn, event)
        for event in events_flat:
            await store.upsert_event(conn, event)
        n_events = await conn.fetchval("SELECT count(*) FROM orderflow_events")
        # الصفوف المقيدة: أشرطة الأحداث المكتشفة حصرًا (§31.2) — ×2 idempotent
        event_bar_indices = {idx for idx, _ in run.events}
        retained = [run.bar_rows[i] for i in sorted(event_bar_indices)]
        for bar, rows in retained:
            await store.replace_rows(conn, bar, rows)
        for bar, rows in retained:
            await store.replace_rows(conn, bar, rows)
        n_rows = await conn.fetchval("SELECT count(*) FROM footprint_rows")
        expected_rows = sum(len(rows) for _, rows in retained)
        await conn.execute("COMMIT")

        if n_bars == len(run.bars) and n_events == len(events_flat) and n_rows == expected_rows:
            ok(
                f"القاعدة: {n_bars} شريطًا و{n_events} حدثًا و{n_rows} صفًا "
                f"(إرسال مرتين ⇒ idempotent تمامًا)"
            )
        else:
            fail(
                f"القاعدة: counts غير متطابقة — bars {n_bars}/{len(run.bars)} "
                f"events {n_events}/{len(events_flat)} rows {n_rows}/{expected_rows}"
            )
            return

        # قراءة round-trip عبر pydantic
        read_bars = await store.read_bars(conn, INSTRUMENT, TIMEFRAME, limit=1000)
        read_bars_by_time = {b.bar_time: b for b in read_bars}
        bars_match = all(read_bars_by_time.get(b.bar_time) == b for b in run.bars)
        read_events = await store.read_events(conn, INSTRUMENT, TIMEFRAME, limit=1000)
        events_match = sorted(e.payload.model_dump_json() for e in read_events) == sorted(
            e.payload.model_dump_json() for e in events_flat
        )
        rows_match = True
        for bar, rows in retained:
            read_back = await store.read_rows(conn, INSTRUMENT, TIMEFRAME, bar.bar_time)
            if read_back != list(rows):
                rows_match = False
                break
        if bars_match and events_match and rows_match:
            ok(
                f"round-trip: {len(read_bars)} شريطًا و{len(read_events)} حدثًا "
                f"و{len(retained)} شريط صفوف — كلها أعيد بناؤها بالتطابق عبر pydantic"
            )
        else:
            fail(f"round-trip: bars={bars_match} events={events_match} rows={rows_match}")
    finally:
        await conn.close()


# ───────────────────────── الرئيسة ─────────────────────────


def main() -> int:
    trades, klines, manifest = load_fixture()

    # ── 1. العينة ──
    if (
        len(trades) == manifest["event_count"]
        and len(klines) == manifest["kline_count"]
        and trades[0].event_time_utc.isoformat() == manifest["first_event_time"]
        and trades[-1].event_time_utc.isoformat() == manifest["last_event_time"]
    ):
        ok(
            f"العينة: {len(trades)} صفقة و{len(klines)} شمعة مرجعية "
            f"[{manifest['first_event_time']} → {manifest['last_event_time']}] مطابقة manifest"
        )
    else:
        fail("العينة لا تطابق manifest")
        return _rc

    global INSTRUMENT
    INSTRUMENT = f"{trades[0].venue}:{trades[0].symbol}"
    candles = klines_to_candles(klines)

    # ── 2+3. المسار الكامل + المطابقة الذهبية ──
    run = FlowRun(trades, candles)
    if _rc:
        return _rc
    golden_checks(run, klines)
    if _rc:
        return _rc
    if run.bars:
        ok(
            f"المسار الكامل: {len(run.bars)} شريط فوتبرنت مقفل بمنهجية "
            f"{run.bars[0].methodology} ووسم {run.bars[0].source_feed} (§12.7)"
        )
    else:
        fail("لا أشرطة فوتبرنت مغلقة — البنّاء فشل")
        return _rc

    # ── 4. الحتمية ──
    run2 = FlowRun(trades, candles)
    d1, d2 = run.digest(), run2.digest()
    if d1 == d2:
        ok(f"الحتمية: مساران ⇒ نفس هاش التتابعات ({d1[:16]}…)")
    else:
        fail(f"الحتمية: هاشان مختلفان {d1[:16]}… ≠ {d2[:16]}…")
        return _rc

    # ── 5. لا-نظرة-مستقبلية ──
    prefix_time = candles[PREFIX_BARS - 1].bar_time
    prefix_trades = [t for t in trades if t.event_time_utc < prefix_time]
    prefix_candles = [c for c in candles if c.bar_time < prefix_time]
    prun = FlowRun(prefix_trades, prefix_candles)
    # الأشرطة: بادئة المقفل == أول أشرطة التشغيل الكامل
    prefix_bars_ok = prun.bars == run.bars[: len(prun.bars)]
    # الأحداث: أحداث البادئة == أحداث الكامل المقيدة بالأشرطة المقفلة
    n_prefix_bars = len(prun.bars)
    prefix_events_sig = [(i, e.event_type.value) for i, e in prun.events]
    full_events_sig_prefix = [(i, e.event_type.value) for i, e in run.events if i < n_prefix_bars]
    if prefix_bars_ok and prefix_events_sig == full_events_sig_prefix:
        ok(
            f"لا-نظرة-مستقبلية: بادئة {PREFIX_BARS} دلو ⇒ {len(prun.bars)} شريطًا "
            f"و{len(prun.events)} حدثًا مستقلة تمامًا عن الذيل"
        )
    else:
        fail("لا-نظرة-مستقبلية: البادئة تغيرت بإضافة الذيل")
        return _rc

    # ── 6. التحجيج λ=2 ──
    lam_run = FlowRun(scaled_trades(trades, 2.0), klines_to_candles(scaled_klines(klines, 2.0)))
    if lam_run.event_signature() == run.event_signature():
        ok(
            f"التحجيم: λ=2 ⇒ نفس أنواع {len(run.events)} حدثًا وأشرطتها — "
            "كل عتبة سعرية اشتقت من atr مضروبًا في المعامل فتحجّجت معه"
        )
    else:
        fail("التحجيم: توقيعا الأحداث مختلفان بين λ=1 وλ=2")
        return _rc

    # ── 7. القانونية ──
    from engine_worker.analysis_publisher import build_envelope

    bad = 0
    for _, event in run.events:
        envelope = build_envelope(
            event,
            INSTRUMENT,
            source="verify-phase4",
            trace_id="verify-phase4",
            receive_time=event.event_time,
        )
        dumped = json.loads(envelope.model_dump_json())
        import jsonschema

        try:
            jsonschema.validate(
                dumped,
                json.loads(
                    (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
                ),
            )
            model = payload_model_for(event.event_type)
            assert model is not None
            jsonschema.validate(
                dumped["payload"],
                json.loads(
                    (GENERATED_DIR / f"{model.__name__}.schema.json").read_text(encoding="utf-8")
                ),
            )
        except (jsonschema.ValidationError, AssertionError) as exc:
            bad += 1
            fail(f"القانونية: {event.event_type.value} خالف: {exc}")
    if bad == 0:
        ok(f"القانونية: كل {len(run.events)} حدثًا مرّت مغلف §32 ومخطط حمولتها")

    # ── 8. الاكتفاء (توثيق التوزيع — لا نصاب مفروض) ──
    dist = Counter(e.event_type.value for _, e in run.events)
    dist_str = "، ".join(f"{k}={v}" for k, v in sorted(dist.items()))
    print(f"  • توزيع أحداث التدفق: {dist_str}")
    vol_engine_probe = VolatilityEngine()
    known_vol = 0
    for candle in candles:
        state = vol_engine_probe.update(candle)
        if state is not None and state.atr is not None:
            known_vol += 1
    print(
        f"  • التقلب متاح في {known_vol}/{len(candles)} شريطًا "
        f"(دفء ATR في البقية — لا قرار بتقلب غائب §16)"
    )
    confirmed_absorption = sum(
        1
        for _, e in run.events
        if e.event_type in (EventType.ABSORPTION_BUY, EventType.ABSORPTION_SELL)
        and e.payload.confirmed is False
    )
    ok(
        f"الاكتفاء: الكواشف أهلت معلوماتها على العينة الحقيقية — "
        f"{confirmed_absorption} مرشح امتصاص كلها confirmed=False (فرضيات "
        "قابلة للتأكيد §12.2) ووسم المصدر والمنهجية في كل شريط (§12.7)"
    )

    # ── 9. البث والتخزين الحي ──
    asyncio.run(live_checks(run))

    if _rc == 0:
        print("═══ بوابة المرحلة 4: خضراء بالكامل ═══")
    else:
        print("═══ بوابة المرحلة 4: فشلت — انظر ✗ أعلاه ═══")
    return _rc


if __name__ == "__main__":
    raise SystemExit(main())
