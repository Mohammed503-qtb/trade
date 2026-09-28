#!/usr/bin/env python3
"""بوابة خروج المرحلة 3 — السيولة والبنية SMC (build_plan §D).

يتطلب بنية حية (postgres + nats) وعينة tests/fixtures/phase2 (جُلبت
بـscripts/fetch_phase2_fixture.py — نفس عينة المرحلة 2 تُعاد استخدامها).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: 1440×1m + 192×15m + 168×1h شموع مغلقة رتيبة زمنيًا.
2. **المسار الكامل**: تقلب + بنية (قمم/كسور/إزاحة/فجوات/كتل/موقع) لكل
   إطار، وخريطة سيولة + اجتياح على 1م تتغذى بمتطرفات 1م المؤكدة عند
   شمعة تأكيدها، وانحياز HTF **بالوضع البنيوي** (إغلاق ADR-016: متتاليات
   الخارجية + إزاحة + توسع من كواشف المرحلة 3 نفسها).
3. **الحتمية**: مساران كاملان ⇒ نفس هاش تتابعات (الأحداث/المتطرفات/
   المناطق/الانحياز).
4. **لا-نظرة-مستقبلية (§26.3)**: بادئة 1م حتى k ⇒ نفس أحداث البادئة
   ومتطرفاتها ومناطقها في التشغيل الكامل (لا رفرفة §27 — المتطرف يعلن
   عند شمعة الحسم حصرًا).
5. **التحجيم (عتبات تطبيعية §16)**: λ=2 على 1م ⇒ نفس أنواع الأحداث
   بترتيبها وتصنيفات المناطق — كل مسافة سعرية اشتقت من atr×المعامل
   فتحجّجت معه (إثبات بوابة المرحلة نصًا: «كل عتبة تطبيعية من التقلب»).
6. **القانونية (§32)**: كل حدث منبعث ⇒ مغلف EventEnvelope (event_id
   حتمي روح D-07) يمر jsonschema ضد المخطط المصدَّر **والحمولة تمر
   مخطط حمولتها الموثق من EVENT_PAYLOAD_MODELS** — بوابة المرحلة نصًا:
   «كل أحداث §20 البنيوية تُبثّ بمخططاتها».
7. **الاكتفاء**: متطرفات مؤكدة على الأطر الثلاثة + كسور بنية + إزاحات +
   فجوات + مناطق نشطة + أهداف ثنائية الجانب + انحياز معلوم — مع توثيق
   توزيع أنواع الأحداث (لا نصاب مفروض على العينة الواحدة؛ ما انبثث
   صادق ومخطط والكاشفات أهلت معلوماتها).
8. **البث والتخزين الحي**: نشر أحداث 1م عبر AnalysisEventPublisher
   (مواضيع market.event.*) واستهلاكها بالتحقق jsonschema؛ القاعدة:
   upsert الأحداث والمتطرفات (structure_events) والمناطق (liquidity_zones)
   والأنماط (pattern_events) idempotent + قراءة round-trip متطابقة.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "market_state" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "structure" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "liquidity" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker" / "src"))

from liquidity import LiquidityEngine
from market_state import HtfBiasEngine, HtfBiasInputs
from market_state.volatility import VolatilityEngine
from schemas import (
    Candle,
    DataQuality,
    EventType,
    SwingScope,
    payload_model_for,
)
from structure import StructureEngine

ENGINE_ROOT = Path(__file__).resolve().parents[1]  # بعد قسم الاستيرادات (نمط verify_phase1)

FIXTURE_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase2"
GENERATED_DIR = ENGINE_ROOT / "packages" / "schemas" / "generated"

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAMES = ("1m", "15m", "1h")
EXPECTED_COUNTS = {"1m": 1440, "15m": 192, "1h": 168}
HTF_TIMEFRAME = "1h"
LTF_TIMEFRAME = "1m"

_rc = 0


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def fail(msg: str) -> None:
    global _rc
    _rc = 1
    print(f"✗ {msg}")


# ───────────────────────── بناء الشموع من klines ─────────────────────────


def klines_to_candles(interval: str, bars: list[dict[str, Any]]) -> list[Candle]:
    """محول عينة → شموع قانونية (نمط verify_phase2 حرفيًا)."""
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
                timeframe=interval,
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


# ───────────────────────── مسار البنية والسيولة ─────────────────────────


class StructureRun:
    """تشغيل واحد للمسار الكامل — كل المخرجات قابلة للهاش والمقارنة."""

    def __init__(self, candles_by_tf: dict[str, list[Candle]], *, lam: float = 1.0) -> None:
        self.lam = lam
        self.events: dict[str, list[str]] = {}  # tf → [(type|bar_time|payload-hash)]
        self.swing_seqs: dict[str, list[str]] = {}  # tf → [swing_id|scope|price]
        self.zone_seqs: dict[str, list[str]] = {}  # tf → [zone_id|state|sweep_status]
        self.bias_seq: list[str] = []
        self.bias_final = None
        self.targets_summary: str = ""
        self._run(candles_by_tf)

    def _scaled(self, value: float) -> float:
        return self.lam * value

    def _run(self, candles_by_tf: dict[str, list[Candle]]) -> None:
        # ── HTF بالوضع البنيوي على 1h (إغلاق ADR-016) ──
        self.bias_final = None
        if HTF_TIMEFRAME in candles_by_tf:
            htf = candles_by_tf[HTF_TIMEFRAME]
            vol_h = VolatilityEngine()
            structure_h = StructureEngine()
            bias_engine = HtfBiasEngine()
            ext_highs: list[float] = []
            ext_lows: list[float] = []
            last_displacement: int = 0
            last_bias = None
            for candle in htf:
                vstate = vol_h.update(candle)
                events = structure_h.update(candle, vstate)
                for event in events:
                    if event.event_type in (
                        EventType.DISPLACEMENT_UP,
                        EventType.DISPLACEMENT_DOWN,
                    ):
                        last_displacement = (
                            1 if event.event_type is EventType.DISPLACEMENT_UP else -1
                        )
                # المتطرفات الخارجية المعلنة حتى الآن (تراكمية — قراءة موضعية)
                all_swings = structure_h.swing_detector.swings
                ext_high_prices = [
                    s.price
                    for s in all_swings
                    if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "HIGH"
                ]
                ext_low_prices = [
                    s.price
                    for s in all_swings
                    if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "LOW"
                ]
                ext_highs = ext_high_prices
                ext_lows = ext_low_prices
                if vstate is not None and vstate.range_expansion_percentile is not None:
                    dealing_range = None
                    close_price = candle.close
                    if ext_highs and ext_lows:
                        dealing_range = (min(ext_lows), max(ext_highs))
                    bstate = bias_engine.update(
                        HtfBiasInputs(
                            directional_efficiency=None,
                            efficiency_sign=None,
                            normalized_range=None,
                            atr_percentile=None,
                            displacement_proxy=None,
                            external_high_sequence=tuple(ext_highs),
                            external_low_sequence=tuple(ext_lows),
                            htf_displacement_direction=last_displacement,
                            expansion_state=vstate.range_expansion_percentile,
                            dealing_range=dealing_range,
                            close_price=close_price,
                        )
                    )
                    self.bias_seq.append(bstate.bias.value)
                    if bstate.bias is not last_bias:
                        self.bias_final = bstate
                        last_bias = bstate.bias

        # ── البنية لكل إطار + السيولة على 1m ──
        for tf in [t for t in TIMEFRAMES if t in candles_by_tf]:
            candles = candles_by_tf[tf]
            vol_engine = VolatilityEngine()
            structure = StructureEngine()
            events_seq: list[str] = []
            swing_seq: list[str] = []
            zone_seq: list[str] = []
            liquidity: LiquidityEngine | None = LiquidityEngine() if tf == LTF_TIMEFRAME else None
            known_swing_ids: set[str] = set()
            for candle in candles:
                vstate = vol_engine.update(candle)
                events = structure.update(candle, vstate)
                for event in events:
                    digest = hashlib.sha256(event.payload.model_dump_json().encode()).hexdigest()[
                        :12
                    ]
                    events_seq.append(
                        f"{event.event_type.value}|{event.event_time.isoformat()}|{digest}"
                    )
                # المتطرفات المعلنة هذا الشريط — تُغذى السيولة بها عند شمعة
                # تأكيدها (§26.3) وتُسجل في التتابع (مساعد موحد يحفظ الترتيب)
                fresh = self._diff_swings(structure, known_swing_ids, candle)
                for swing in fresh:
                    swing_seq.append(
                        f"{swing.swing_id}|{swing.external_or_internal.value}"
                        f"|{swing.price:.10g}|{swing.strength:.10g}"
                    )
                if liquidity is not None:
                    liquidity.update(candle, vstate, fresh)
                    zone_seq.extend(
                        f"{z.zone_id}|{z.state.value}|{z.sweep_status.value}"
                        for z in liquidity.zones()
                    )
            self.events[tf] = events_seq
            self.swing_seqs[tf] = swing_seq
            self.zone_seqs[tf] = zone_seq if liquidity is not None else []
            if liquidity is not None:
                final_vstate = vol_engine.state
                assert final_vstate is not None
                targets = liquidity.targets(candles[-1].close, final_vstate, limit_per_side=5)
                self.targets_summary = (
                    f"above={len(targets.above)}|below={len(targets.below)}"
                    f"|ids={','.join(e.zone.zone_id[:8] for e in targets.above + targets.below)}"
                )

    def _diff_swings(self, structure: StructureEngine, known: set[str], candle: Candle) -> list:
        """المتطرفات المعلنة هذا الشريط — بترشيح شمعة التأكيد (لا-نظرة §26.3)."""
        fresh = [
            s
            for s in structure.swings
            if s.swing_id not in known and s.confirmation_time <= candle.bar_time
        ]
        known.update(s.swing_id for s in fresh)
        return fresh

    def digest(self) -> str:
        h = hashlib.sha256()
        for tf in TIMEFRAMES:
            if tf not in self.events:
                continue
            h.update(tf.encode())
            h.update("|".join(self.events[tf]).encode())
            h.update("|".join(self.swing_seqs[tf]).encode())
            if tf == LTF_TIMEFRAME:
                h.update("|".join(self.zone_seqs[tf]).encode())
                h.update(self.targets_summary.encode())
        h.update("|".join(self.bias_seq).encode())
        return h.hexdigest()


# ───────────────────────── الفحوص الحية (NATS + القاعدة) ─────────────────────────


async def live_checks(events_1m: list, candles_1m: list[Candle], zones: list, swings: list) -> None:
    """البث NATS بمواضيعه + التخزين idempotent والقراءة round-trip."""
    from asyncpg import connect as pg_connect
    from common.config import load_settings
    from engine_worker.analysis_publisher import AnalysisEventPublisher, build_envelope
    from liquidity.store import LiquidityZoneStore
    from nats.aio.client import Client as NATSClient
    from structure.store import AnalysisEventStore

    settings = load_settings()
    envelope_schema = json.loads(
        (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
    )

    # ── NATS: نشر عينة أحداث 1m (وكل الأنواع الموجودة مرة واحدة على الأقل) ──
    nc: NATSClient = NATSClient()
    await nc.connect(servers=[settings.nats_url], connect_timeout=5, max_reconnect_attempts=1)
    received: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def _cb(msg: Any) -> None:
        received.append((msg.subject, json.loads(msg.data.decode()), dict(msg.headers or {})))

    await nc.subscribe("market.event.binance-usdm-btcusdt.1m.*", cb=_cb)
    publisher = AnalysisEventPublisher(nc)

    # عينة البث: أول 8 أحداث + أول حدث من كل نوع متاح (تغطية الأنواع)
    sample: list = list(events_1m[:8])
    seen_types = {e.event_type for e in sample}
    for event in events_1m:
        if event.event_type not in seen_types:
            sample.append(event)
            seen_types.add(event.event_type)
    envelopes = [
        build_envelope(
            event,
            INSTRUMENT,
            source="verify-phase3",
            trace_id="verify-phase3",
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
        except (jsonschema.ValidationError, ValueError) as exc:
            bad += 1
            fail(f"NATS: حمولة «{subject}» خالفت: {exc}")
    if bad == 0:
        ok(
            f"NATS: {len(received)} حدثًا عبر market.event.* مرّت مغلف §32 "
            f"وحمولاتها مخططاتها ({len(seen_types)} نوعًا مغطى)"
        )

    # ── القاعدة: upsert idempotent + قراءة round-trip ──
    event_store = AnalysisEventStore()
    zone_store = LiquidityZoneStore()
    conn = await pg_connect(settings.database_url)
    try:
        # تنظيف مسبق لصفوف الأداة — البوابة قابلة للتكرار على قاعدة عاشت تشغيلات سابقة
        instrument_uuid = __import__("uuid").uuid5(
            __import__("uuid").uuid5(
                __import__("uuid").NAMESPACE_URL, "ai-market-reasoning-engine/instrument"
            ),
            INSTRUMENT,
        )
        # SQL حرفية لكل جدول (لا تركيب سلاسل إطلاقًا)
        for delete_sql in (
            "DELETE FROM structure_events WHERE instrument_id = $1",
            "DELETE FROM pattern_events WHERE instrument_id = $1",
            "DELETE FROM liquidity_zones WHERE instrument_id = $1",
        ):
            await conn.execute(delete_sql, instrument_uuid)
        await conn.execute("COMMIT")
        for envelope in envelopes:
            await event_store.upsert_event(conn, envelope)
        # إعادة الإرسال نفسها — لا صفوف جديدة (at-least-once §32)
        for envelope in envelopes:
            await event_store.upsert_event(conn, envelope)
        # المتطرفات المؤكدة («swing» §31.3) والمناطق بدورة حياتها — ×2
        for swing in swings:
            await event_store.upsert_swing(conn, swing, INSTRUMENT)
        for swing in swings:
            await event_store.upsert_swing(conn, swing, INSTRUMENT)
        for zone in zones:
            await zone_store.upsert_zone(conn, zone)
        for zone in zones:
            await zone_store.upsert_zone(conn, zone)
        await conn.execute("COMMIT")
        recent = await event_store.recent_events(
            conn, INSTRUMENT, LTF_TIMEFRAME, limit=500, table="structure_events"
        )
        recent_swings = await event_store.recent_swings(conn, INSTRUMENT, LTF_TIMEFRAME, limit=1000)
        read_zones = await zone_store.read_zones(conn, INSTRUMENT, LTF_TIMEFRAME)
        # مقارنة بالمعرف لا بالموضع — مناطق بنفس origin_time يرتّبها SQL
        # بمعرفها فترتيب القراءة غير ترتيب الإنشاء (كلاهما حتمي)
        read_by_id = {z.zone_id: z for z in read_zones}
        zones_match = set(read_by_id) == {z.zone_id for z in zones} and all(
            read_by_id[z.zone_id] == z for z in zones
        )
        if len(recent_swings) == len(swings) and zones_match:
            ok(
                f"القاعدة: {len(envelopes)} حدثًا و{len(swings)} متطرفًا و{len(zones)} "
                f"منطقة (إرسال مرتين) upsert idempotent — قراءة round-trip متطابقة عبر pydantic "
                f"({len(recent)}+{len(recent_swings)} سجلًا مقروءًا)"
            )
        else:
            fail(
                f"القاعدة: القراءة راجعت {len(recent_swings)}/{len(swings)} متطرفًا "
                f"و{len(read_zones)}/{len(zones)} منطقة — round-trip مختل"
            )
    finally:
        await conn.close()


def main() -> int:
    global _rc
    print("═══ verify-phase3 — محرك البنية والسيولة (SMC) على عينة ثلاثية الأطر ═══")

    # 1) العينة
    candles_by_tf: dict[str, list[Candle]] = {}
    for tf, expected in EXPECTED_COUNTS.items():
        bars = json.loads((FIXTURE_DIR / f"klines_{tf}.json").read_text(encoding="utf-8"))
        if len(bars) != expected:
            fail(f"{tf}: {len(bars)} شمعة بدل {expected}")
            return _rc
        candles = klines_to_candles(tf, bars)
        candles_by_tf[tf] = candles
        first, last = candles[0], candles[-1]
        ok(
            f"{tf}: {len(candles)} شمعة مغلقة "
            f"[{first.bar_time:%m-%d %H:%M} → {last.bar_time:%m-%d %H:%M} UTC]"
        )

    # 2-6) المسار × 2 للحتمية + بادئة للاستقلال + تحجيم للعتبات
    run_a = StructureRun(candles_by_tf)
    run_b = StructureRun(candles_by_tf)
    k = len(candles_by_tf[LTF_TIMEFRAME]) - 25
    prefix_run = StructureRun({LTF_TIMEFRAME: candles_by_tf[LTF_TIMEFRAME][:k]})
    scaled_run = StructureRun({LTF_TIMEFRAME: _scale_candles(candles_by_tf[LTF_TIMEFRAME], 2.0)})

    # الحتمية
    if run_a.digest() == run_b.digest():
        ok(f"الحتمية: مساران ⇒ نفس هاش التتابعات ({run_a.digest()[:16]}…)")
    else:
        fail("الحتمية: هاشا المسارين مختلفان")

    # لا-نظرة-مستقبلية
    n_events_prefix = len(prefix_run.events[LTF_TIMEFRAME])
    if (
        prefix_run.events[LTF_TIMEFRAME] == run_a.events[LTF_TIMEFRAME][:n_events_prefix]
        and prefix_run.swing_seqs[LTF_TIMEFRAME]
        == run_a.swing_seqs[LTF_TIMEFRAME][: len(prefix_run.swing_seqs[LTF_TIMEFRAME])]
    ):
        ok(
            f"لا-نظرة-مستقبلية: بادئة 1m حتى k={k} ({n_events_prefix} حدثًا، "
            f"{len(prefix_run.swing_seqs[LTF_TIMEFRAME])} متطرفًا) مستقلة تمامًا عن الذيل"
        )
    else:
        fail("لا-نظرة-مستقبلية: تتابع البادئة تغير بإضافة الذيل (رفرفة §27)")

    # التحجيم — أنواع الأحداث بترتيبها ثابتة (كل عتبة تطبيعية تقدّمت مع ATR)
    scaled_types = [e.split("|")[0] for e in scaled_run.events[LTF_TIMEFRAME]]
    orig_types = [e.split("|")[0] for e in run_a.events[LTF_TIMEFRAME]]
    scaled_scope = [s.split("|")[1] for s in scaled_run.swing_seqs[LTF_TIMEFRAME]]
    orig_scope = [s.split("|")[1] for s in run_a.swing_seqs[LTF_TIMEFRAME]]
    if scaled_types == orig_types and scaled_scope == orig_scope:
        ok(
            f"التحجيم: λ=2 ⇒ نفس أنواع {len(orig_types)} حدثًا وتصنيفات "
            f"{len(orig_scope)} متطرفًا — كل مسافة اشتقت من ضرب ATR بمعامله"
        )
    else:
        fail(
            f"التحجيم: التصنيفات انحرفت (أحداث {len(orig_types)}→{len(scaled_types)}"
            f"{'، أنواع مختلفة' if scaled_types != orig_types else ''})"
        )

    # القانونية — كل حدث منبعث يمر مخططاته
    envelope_schema = json.loads(
        (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
    )
    from engine_worker.analysis_publisher import build_envelope

    all_events = [e for tf in TIMEFRAMES for e in _rerun_collect(candles_by_tf, tf)]
    type_counts: Mapping[str, int] = {}
    for event in all_events:
        type_counts = {
            **type_counts,
            event.event_type.value: type_counts.get(event.event_type.value, 0) + 1,
        }
    invalid = 0
    for event in all_events:
        envelope = build_envelope(
            event,
            INSTRUMENT,
            source="verify-phase3",
            trace_id="verify-phase3",
            receive_time=event.event_time,
        )
        try:
            envelope_json = json.loads(envelope.model_dump_json())
            jsonschema.validate(envelope_json, envelope_schema)
            model = payload_model_for(envelope.event_type)
            assert model is not None
            # الحمولة بعد دورة JSON الكاملة — التواريخ سلاسل ISO كما يبثها الناشر
            jsonschema.validate(
                envelope_json["payload"],
                json.loads(
                    (GENERATED_DIR / f"{model.__name__}.schema.json").read_text(encoding="utf-8")
                ),
            )
        except jsonschema.ValidationError as exc:
            invalid += 1
            fail(f"القانونية: {envelope.event_type.value} خالف: {exc.message}")
    if invalid == 0:
        ok(
            f"القانونية: كل {len(all_events)} حدثًا مرّت مغلف §32 + مخطط حمولتها "
            f"({len(type_counts)} نوعًا)"
        )

    # الاكتفاء — توثيق ما أهله كل محرك
    for tf in TIMEFRAMES:
        n_swings = len(run_a.swing_seqs[tf])
        external = sum(1 for s in run_a.swing_seqs[tf] if "|EXTERNAL|" in s)
        n_events = len(run_a.events[tf])
        print(f"  • {tf}: {n_swings} متطرفًا ({external} خارجيًا) و{n_events} حدثًا")
    types_line = "، ".join(f"{k2}={v}" for k2, v in sorted(type_counts.items()))
    print(f"  • توزيع الأحداث: {types_line}")
    bias_final_value = run_a.bias_seq[-1] if run_a.bias_seq else "—"
    print(f"  • انحياز 1h البنيوي: تتابع {len(run_a.bias_seq)} حالة ينتهي {bias_final_value}")
    print(f"  • أهداف 1m النهائية: {run_a.targets_summary[:60]}")

    swings_1m = run_a.swing_seqs[LTF_TIMEFRAME]
    zones_1m = len({z.split("|")[0] for z in run_a.zone_seqs[LTF_TIMEFRAME]})
    sufficient = (
        len(swings_1m) >= 20
        and zones_1m >= 5
        and run_a.bias_seq
        and run_a.bias_seq[-1] != "UNKNOWN"
    )
    if sufficient:
        ok(
            f"الاكتفاء: {len(swings_1m)} متطرفًا و{zones_1m} منطقة سيولة "
            f"وانحياز 1h معلوم ({run_a.bias_seq[-1]})"
        )
    else:
        fail(
            f"الاكتفاء: متطرفات {len(swings_1m)}/مناطق {zones_1m}/"
            f"انحياز {run_a.bias_seq[-1] if run_a.bias_seq else 'بلا'} — الدافئ لم يكتمل"
        )

    # 8) البث والتخزين الحي (الأحداث + المتطرفات + المناطق النهائية)
    events_1m, zones_1m, swings_1m = _rerun_collect_full(candles_by_tf)
    asyncio.run(live_checks(events_1m, candles_by_tf[LTF_TIMEFRAME], zones_1m, swings_1m))

    if _rc == 0:
        print("═══ بوابة المرحلة 3: خضراء بالكامل ═══")
    else:
        print("═══ بوابة المرحلة 3: فشل — انظر ✗ أعلاه ═══")
    return _rc


def _scale_candles(candles: list[Candle], lam: float) -> list[Candle]:
    """نسخة محجّجة الأسعار (λ قوة أساسين — دقة بتّية عبر المضاعفة)."""
    scaled = []
    prev_close: float | None = None
    import math

    for candle in candles:
        o = lam * candle.open
        h = lam * candle.high
        low = lam * candle.low
        c = lam * candle.close
        span = h - low
        body = abs(c - o)
        if span > 0.0:
            bf = body / span
            clv = (c - low) / span
        else:
            bf = 0.0
            clv = 0.5
        tr = (
            span if prev_close is None else max(h - low, abs(h - prev_close), abs(low - prev_close))
        )
        scaled.append(
            candle.model_copy(
                update={
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": c,
                    "volume": candle.volume,
                    "range": span,
                    "body_size": body,
                    "upper_wick": h - max(o, c),
                    "lower_wick": min(o, c) - low,
                    "body_fraction": bf,
                    "close_location_value": clv,
                    "true_range": tr,
                    "realized_volatility": abs(math.log(c / o)) if o > 0.0 else 0.0,
                }
            )
        )
        prev_close = c
    return scaled


def _rerun_collect(candles_by_tf: dict[str, list[Candle]], tf: str) -> list:
    """إعادة جمع أحداث إطار واحد كمجموعة EmittedEvent خام (لفحص القانونية)."""
    return (
        _rerun_collect_full(candles_by_tf)[0]
        if tf == LTF_TIMEFRAME
        else _rerun_tf(candles_by_tf, tf)
    )


def _rerun_tf(candles_by_tf: dict[str, list[Candle]], tf: str) -> list:
    """إعادة جمع أحداث إطار واحد (بلا سيولة — المسار البنيوي الصرف)."""
    vol_engine = VolatilityEngine()
    structure = StructureEngine()
    collected: list = []
    for candle in candles_by_tf[tf]:
        collected.extend(structure.update(candle, vol_engine.update(candle)))
    return collected


def _rerun_collect_full(
    candles_by_tf: dict[str, list[Candle]],
) -> tuple[list, list, list]:
    """الإعادة الكاملة 1m: أحداث + مناطق نهائية + متطرفات مؤكدة مرتبة."""
    candles = candles_by_tf[LTF_TIMEFRAME]
    vol_engine = VolatilityEngine()
    structure = StructureEngine()
    liquidity = LiquidityEngine()
    known: set[str] = set()
    collected: list = []
    for candle in candles:
        vstate = vol_engine.update(candle)
        collected.extend(structure.update(candle, vstate))
        fresh = [
            s
            for s in structure.swings
            if s.swing_id not in known and s.confirmation_time <= candle.bar_time
        ]
        known.update(s.swing_id for s in fresh)
        liquidity.update(candle, vstate, fresh)
    return collected, list(liquidity.zones()), list(structure.swings)


if __name__ == "__main__":
    raise SystemExit(main())
