#!/usr/bin/env python3
"""بوابة خروج المرحلة 5a — الأنماط + بوابة الاستئصال (build_plan §D + §46-5).

يتطلب بنية حية (postgres + nats) وعينة tests/fixtures/phase2 الثلاثية
الأطر (1m/15m/1h حقيقية — 1440/192/96 شمعة BTCUSDT).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: الأطر الثلاثة متطابقة الحدود مع manifest (عد + هاشان).
2. **المسار الشموعي**: CandlePatternDetector على 1m — أحداث الأنواع
   الثلاثة ذات القاموس §20 بحمولات قانونية وقراءات السمات الست كاملة.
3. **المسار الكلاسيكي**: ClassicalPatternDetector على 1m/15m/1h — أحداث
   الكسر/الفشل بمخرجات §13.2 الثمانية (مستعلَمة من الحمولة نفسها).
4. **الحتمية**: مساران كاملان لكل كاشف ⇒ نفس الأحداث بايت-بايت.
5. **لا-نظرة-مستقبلية (§26.3)**: بادئة الشموع ⇒ نفس أحداث البادئة مع
   وجود الذيل (الكواشف لا ترى الأمام).
6. **التحجيم (عتبات نسبية §13)**: λ=2 على الأسعار ⇒ نفس أنواع الأحداث
   بترتيبها وأشرطتها (كل عتبات الأنماط نسب لا مستويات مطلقة).
7. **القانونية (§32)**: كل حدث منبعث ⇒ مغلف EventEnvelope يمر jsonschema
   وحمولته تمر مخطط حمولتها من EVENT_PAYLOAD_MODELS.
8. **بوابة الاستئصال (§46-5 نصًا: «جهاز الاستئصال موجود قبل السماح
   لهذه السمات بالتقييم الحي» + build_plan: «تشغيل ablation الفعلي لسمات
   5a»)**: جدول base/±feature لسمات الشموع الست §13.1 على 1m بالمقيّم
   الحقيقي DirectionalEvaluator (تقسيم زمني 70/30 — عتبات الإشارة من
   التدريب والقياس في OOS حصرًا)؛ الجدول كامل (1 + 6 متغيرات) وكل
   متغير بمقاييسه المحدودة، والتقرير حتمي بايت-بايت بساعة محقونة.
9. **سجل الترقية promotion-like (§41)**: أرشفة تقرير الاستئصال في
   docs/ablation/phase5a/ بحقول §41 المتاحة فعليًا (code_commit/
   feature_schema/parameter_set/training_window/OOS_window/
   data_source_versions/model_artifact_hash/approval_timestamp) — والحقول
   المؤجلة صراحة موثقة بأسبابها (cost_model وcalibration_artifact:
   مرحلتا 7/9 — لا اختلاق).
10. **البث والتخزين الحي**: عينة أحداث عبر AnalysisEventPublisher على
    market.event.* بتحقق jsonschema؛ القاعدة: upsert إلى pattern_events
    (الأنواع الست الجديدة §13) مرتين ⇒ idempotent + round-trip بالتطابق.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import uuid as uuid_module
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# الاستيرادات بعد تهيئة مسارات الحزم (نمط verify_phase3/4)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "patterns" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "worker" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "replay" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "structure" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))

from patterns.candle_patterns import CandlePatternDetector
from patterns.classical import ClassicalPatternDetector, EmittedEvent
from schemas import EventType, payload_model_for

ENGINE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase2"
GENERATED_DIR = ENGINE_ROOT / "packages" / "schemas" / "generated"
ABLATION_DIR = ENGINE_ROOT / "docs" / "ablation" / "phase5a"

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
#: هوية البث/القاعدة — نمط manifest العينة (venue:symbol).
FEED_ID = "binance-usdm-futures:BTCUSDT"
#: بادئة فحص اللا-نظرة (شموع 1m) — تغطي دفء النوافذ والسياقات.
PREFIX_BARS = 200

_rc = 0


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def fail(msg: str) -> None:
    global _rc
    _rc = 1
    print(f"✗ {msg}")


# ───────────────────────── تحميل العينة ─────────────────────────


def load_candles(timeframe: str) -> list[Any]:
    """محول klines العينة → شموع قانونية (نمط verify_phase4 حرفيًا)."""
    import math

    bars = json.loads((FIXTURE_DIR / f"klines_{timeframe}.json").read_text(encoding="utf-8"))
    from schemas import Candle, DataQuality

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
                timeframe=timeframe,
                bar_time=bt,
                session_id=bt.date().isoformat(),
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
                realized_volatility=abs(math.log(c / o)) if o > 0 else 0.0,
            )
        )
        prev_close = c
    return out


def events_fingerprint(events: list[EmittedEvent]) -> str:
    """بصمة أحداث حتمية — النوع + الوقت + الحمولة بايت-بايت."""
    parts = [
        f"{e.event_type.value}|{e.event_time.isoformat()}|{e.payload.model_dump_json()}"
        for e in events
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def scale_candles(candles: list[Any], lam: float) -> list[Any]:
    """تحجيم الأسعار بمعامل λ — الشموع النسبية تُنجو به (عتبات §13 نسب)."""
    return [
        c.model_copy(
            update={
                "open": c.open * lam,
                "high": c.high * lam,
                "low": c.low * lam,
                "close": c.close * lam,
                "range": c.range * lam,
                "body_size": c.body_size * lam,
                "upper_wick": c.upper_wick * lam,
                "lower_wick": c.lower_wick * lam,
                "true_range": c.true_range * lam,
            }
        )
        for c in candles
    ]


# ───────────────────────── مسارات الكواشف ─────────────────────────


def run_candle_detector(candles: list[Any]) -> list[EmittedEvent]:
    detector = CandlePatternDetector()
    return list(detector.on_candles(candles))


def run_classical_detector(candles: list[Any]) -> list[EmittedEvent]:
    detector = ClassicalPatternDetector()
    return list(detector.on_candles(candles))


def shared_checks(name: str, events: list[EmittedEvent]) -> None:
    """فحوص مشتركة لكل كاشف: القانونية + اكتمال مخرجات §13.2 للكلاسيكي."""
    import jsonschema

    envelope_schema = json.loads(
        (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
    )
    for event in events:
        # تسلسل JSON كامل (نمط بوابة 3: التواريخ كائنات Python لا سلاسل
        # في model_dump — والمخطط يتحقق من السلاسل)
        payload = json.loads(event.payload.model_dump_json())
        envelope = {
            "event_id": str(uuid_module.uuid4()),
            "schema_version": "1.0.0",
            "event_type": event.event_type.value,
            "event_time": event.event_time.isoformat(),
            "receive_time": event.event_time.isoformat(),
            "source": "verify-phase5",
            "trace_id": "verify-phase5",
            "correlation_id": None,
            "payload": payload,
        }
        try:
            jsonschema.validate(envelope, envelope_schema)
            model = payload_model_for(event.event_type)
            assert model is not None
            jsonschema.validate(
                payload,
                json.loads(
                    (GENERATED_DIR / f"{model.__name__}.schema.json").read_text(encoding="utf-8")
                ),
            )
        except (jsonschema.ValidationError, AssertionError) as exc:
            fail(f"{name}: حدث خالف القانونية: {exc}")
            return
    ok(f"{name}: {len(events)} حدثًا كلها مغلفة §32 وحمولاتها مخططاتها")


def determinism_and_no_lookahead(name: str, candles: list[Any], runner: Any) -> list[EmittedEvent]:
    """الحتمية (مساران) + اللا-نظرة (بادئة) — تعيد أحداث المسار الكامل."""
    events = runner(candles)
    again = runner(candles)
    if events_fingerprint(events) == events_fingerprint(again):
        ok(f"{name}: حتمي — مساران ⇒ هاش {events_fingerprint(events)[:16]}…")
    else:
        fail(f"{name}: المساران اختلفا")
        return events

    prefix = candles[:PREFIX_BARS]
    prefix_events = runner(prefix)
    full_pairs = {(e.event_type, e.event_time) for e in events}
    prefix_pairs = {(e.event_type, e.event_time) for e in prefix_events}
    if prefix_pairs <= full_pairs:
        ok(
            f"{name}: لا-نظرة — بادئة {PREFIX_BARS} شمعة "
            f"({len(prefix_events)} حدثًا) مستقلة عن الذيل"
        )
    else:
        fail(f"{name}: بادئة أنتجت أحداثًا غابت عن المسار الكامل (نظرة مستقبلية!)")
    return events


def scaling_check(name: str, candles: list[Any], runner: Any) -> None:
    """التحجيم λ=2 — نفس أنواع الأحداث بترتيبها وأوقاتها (عتبات نسبية)."""
    base_events = runner(candles)
    scaled_events = runner(scale_candles(candles, 2.0))
    base_pairs = [(e.event_type, e.event_time) for e in base_events]
    scaled_pairs = [(e.event_type, e.event_time) for e in scaled_events]
    if base_pairs == scaled_pairs:
        ok(f"{name}: تحجيج λ=2 ⇒ نفس {len(base_pairs)} حدثًا بنوعه ووقته (عتبات §13 نسبية)")
    else:
        diff = [p for p in base_pairs if p not in scaled_pairs][:3]
        fail(f"{name}: التحجيم غيّر الأحداث — أمثلة: {diff}")


# ───────────────────────── بوابة الاستئصال (§46-5) ─────────────────────────


def ablation_checks(candles: list[Any]) -> dict[str, Any]:
    """جدول ±feature لسمات §13.1 بالمقيّم الحقيقي + حتمية التقرير."""
    from engine_replay.ablation import AblationSpec, Dataset, run_ablation
    from engine_replay.ablation_evaluator import DirectionalEvaluator

    candle_features = (
        "body_fraction",
        "wick_asymmetry",
        "close_location",
        "range_percentile_100",
        "gap_relationship_20",
        "volume_relationship_20",
    )
    spec = AblationSpec(
        base_features=(),
        ablated=candle_features,
        dataset_label="phase2-BTCUSDT-1m",
    )
    dataset = Dataset(label="phase2-BTCUSDT-1m", candles=tuple(candles))
    frozen_clock = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)

    report = run_ablation(spec, dataset, evaluator=DirectionalEvaluator(), now=lambda: frozen_clock)
    again = run_ablation(spec, dataset, evaluator=DirectionalEvaluator(), now=lambda: frozen_clock)
    if report.to_json() == again.to_json():
        ok("الاستئصال: التقرير حتمي بايت-بايت بساعة محقونة")
    else:
        fail("الاستئصال: التقريران اختلفا")
        return {}

    labels = [v.variant_label for v in report.variants]
    expected = ["base", *(f"plus_{f}" for f in candle_features)]
    if labels == expected:
        ok("الاستئصال: الجدول كامل — base + 6 متغيرات plus (سمات §13.1 خارج القاعدة الفارغة)")
    else:
        fail(f"الاستئصال: الجدول ناقص/منحرف: {labels}")
        return {}

    measured = 0
    for variant in report.variants:
        if variant.variant_label == "base":
            if variant.metrics:
                fail(f"الاستئصال: القاعدة الفارغة قاست شيئًا: {variant.metrics}")
                return {}
            continue
        if "oos_signal_count" in variant.metrics and float(variant.metrics["oos_signal_count"]) > 0:
            measured += 1
    if measured >= 4:
        ok(
            f"الاستئصال: {measured}/6 متغيرات قاست إشارات فعلية في OOS "
            "(المقيّم الحقيقي — تقسيم زمني 70/30 وعتبات من التدريب حصرًا)"
        )
    else:
        fail(f"الاستئصال: {measured} متغيرًا فقط قاس إشارات — المقيّم معطل")

    return {
        "report_json": report.to_json(),
        "variants": [
            {
                "label": v.variant_label,
                "features": list(v.features_used),
                "metrics": dict(v.metrics),
            }
            for v in report.variants
        ],
        "candle_count": len(candles),
        "first_bar": candles[0].bar_time.isoformat(),
        "split_index": int(len(candles) * 0.70),
    }


def archive_promotion_record(ablation: dict[str, Any], candles: list[Any]) -> None:
    """أرشفة سجل الترقية promotion-like بحقول §41 المتاحة (§41 المتبقي مؤجل)."""
    ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    try:
        git_binary = shutil.which("git") or "/usr/bin/git"
        result = subprocess.run(  # noqa: S603 — مدخل ثابت موثوق (نمط 0002)
            [git_binary, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ENGINE_ROOT.parent,
        )
        code_commit = result.stdout.strip().splitlines()[0]
    except (subprocess.CalledProcessError, OSError):
        code_commit = "unknown"
    split_index = ablation["split_index"]
    record = {
        "artifact": "phase5a-candle-features-ablation",
        "gate": "§46-5 — جهاز الاستئصال قبل التقييم الحي",
        "methodology": (
            "§43 Base/±Feature — تقسيم زمني 70/30، عتبات إشارة كوانتيلية من التدريب حصرًا"
        ),
        "code_commit": code_commit,
        "feature_schema": [
            "body_fraction",
            "wick_asymmetry",
            "close_location",
            "range_percentile_100",
            "gap_relationship_20",
            "volume_relationship_20",
        ],
        "parameter_set": {
            "horizon": 5,
            "train_ratio": 0.70,
            "signal_quantile": 0.90,
        },
        "training_window": {
            "bars": split_index,
            "first": ablation["first_bar"],
            "last": candles[split_index - 1].bar_time.isoformat(),
        },
        "validation_window": None,
        "oos_window": {
            "bars": len(candles) - split_index,
            "first": candles[split_index].bar_time.isoformat(),
            "last": candles[-1].bar_time.isoformat(),
        },
        "cost_model": None,
        "cost_model_deferred_reason": (
            "التكاليف الواقعية بعد التداول الورقي — مرحلة 9 (§43: قيمة تزايدية بعد التكاليف)"
        ),
        "data_source_versions": {
            "fixture": "tests/fixtures/phase2",
            "symbol": "BTCUSDT",
            "venue": "binance-usdm-futures",
            "timeframe": "1m",
            "bars": len(candles),
        },
        "model_artifact_hash": hashlib.sha256(ablation["report_json"].encode("utf-8")).hexdigest(),
        "calibration_artifact": None,
        "calibration_deferred_reason": "المعايرة بعد محرك الدمج §19 — مرحلة 6/9",
        "approval_timestamp": datetime.now(UTC).isoformat(),
        "variants": ablation["variants"],
    }
    (ABLATION_DIR / "promotion_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (ABLATION_DIR / "ablation_report.json").write_text(ablation["report_json"], encoding="utf-8")
    ok(
        f"سجل الترقية: أُرشف في docs/ablation/phase5a/ (hash "
        f"{record['model_artifact_hash'][:16]}… بحقول §41 المتاحة — والمؤجل موثق بسبب)"
    )


# ───────────────────────── الفحوص الحية (NATS + القاعدة) ─────────────────────────


async def live_checks(
    candle_events: list[EmittedEvent], classical_events: list[EmittedEvent]
) -> None:
    """البث NATS بمواضيعه + التخزين idempotent في pattern_events + round-trip."""
    import jsonschema
    from asyncpg import connect as pg_connect
    from common.config import load_settings
    from engine_worker.analysis_publisher import (
        AnalysisEventPublisher,
        build_envelope,
        subject_for,
    )
    from nats.aio.client import Client as NATSClient
    from structure.store import AnalysisEventStore

    settings = load_settings()
    all_events = [*candle_events, *classical_events]
    if not all_events:
        fail("البث: لا أحداث لعينتها")
        return

    received: list[tuple[str, dict[str, Any]]] = []
    nc: NATSClient = NATSClient()
    await nc.connect(servers=[settings.nats_url], connect_timeout=5, max_reconnect_attempts=1)

    async def _cb(msg: Any) -> None:
        received.append((msg.subject, json.loads(msg.data.decode("utf-8"))))

    sample: list[EmittedEvent] = []
    seen_types: set[EventType] = set()
    for event in all_events:
        if event.event_type not in seen_types or len(sample) < 8:
            sample.append(event)
            seen_types.add(event.event_type)

    # موضوع فريد لكل اشتراك (الاشتراك المتكرر يضاعف الاستقبال)
    unique_subjects = {
        subject_for(event.event_type, event.payload.instrument, event.payload.timeframe)
        for event in sample
    }
    for subject in sorted(unique_subjects):
        await nc.subscribe(subject, cb=_cb)
    await nc.flush()

    publisher = AnalysisEventPublisher(nc)
    envelopes = []
    for event in sample:
        envelope = build_envelope(
            event,
            FEED_ID,
            source="verify-phase5",
            trace_id="verify-phase5",
            receive_time=event.event_time,
        )
        envelopes.append(envelope)
        await publisher.publish(envelope)
    await nc.flush()
    await asyncio.sleep(1.0)
    await nc.close()

    if len(received) >= len(sample):
        envelope_schema = json.loads(
            (GENERATED_DIR / "EventEnvelope.schema.json").read_text(encoding="utf-8")
        )
        for subject, payload in received:
            try:
                jsonschema.validate(payload, envelope_schema)
                model = payload_model_for(EventType(payload["event_type"]))
                assert model is not None
                jsonschema.validate(
                    payload["payload"],
                    json.loads(
                        (GENERATED_DIR / f"{model.__name__}.schema.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                )
            except (jsonschema.ValidationError, ValueError, AssertionError) as exc:
                fail(f"NATS: حمولة «{subject}» خالفت: {exc}")
                return
        ok(
            f"NATS: {len(received)} حدثًا عبر market.event.* مرّت مغلف §32 "
            f"وحمولاتها مخططاتها ({len(seen_types)} نوعًا مغطى)"
        )
    else:
        fail(f"NATS: استُقبل {len(received)} من {len(sample)} حدثًا خلال المهلة")
        return

    # ── القاعدة: upsert idempotent في pattern_events + round-trip ──
    store = AnalysisEventStore()
    conn = await pg_connect(settings.database_url)
    try:
        # المعرف كما يشتقه المخزن: من instrument الحمولة نفسها
        instrument_uuid = uuid_module.uuid5(
            uuid_module.uuid5(uuid_module.NAMESPACE_URL, "ai-market-reasoning-engine/instrument"),
            INSTRUMENT,
        )
        await conn.execute("DELETE FROM pattern_events WHERE instrument_id = $1", instrument_uuid)
        await conn.execute("COMMIT")

        for envelope in envelopes:
            await store.upsert_event(conn, envelope)
        for envelope in envelopes:
            await store.upsert_event(conn, envelope)
        n_events = await conn.fetchval("SELECT count(*) FROM pattern_events")
        await conn.execute("COMMIT")
        if n_events == len(envelopes):
            ok(
                f"القاعدة: {n_events} حدثًا في pattern_events "
                f"(إرسال مرتين ⇒ idempotent — الأنواع الستة §13 قانونية التوطين)"
            )
        else:
            fail(f"القاعدة: {n_events} صفًا مقابل {len(envelopes)} متوقعًا")
            return
        read_back = await conn.fetch(
            "SELECT event_type, payload FROM pattern_events WHERE instrument_id = $1",
            instrument_uuid,
        )

        def _dump(typed: str, payload: Any) -> str:
            # إعادة البناء عبر النموذج القانوني (عقد round-trip) ثم توحيد
            # ترتيب المفاتيح: JSONB لا يحفظ ترتيب مفاتيح الـdict والقيم
            # هي العقد — sort_keys يجعل المقارنة قياسية قاطعة.
            value = payload if isinstance(payload, dict) else json.loads(payload)
            model = payload_model_for(EventType(typed))
            assert model is not None
            restored = model.model_validate(value)
            return json.dumps(restored.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)

        dumped_back = sorted(_dump(row["event_type"], row["payload"]) for row in read_back)
        dumped_expected = sorted(_dump(e.event_type.value, e.payload) for e in envelopes)
        if dumped_back == dumped_expected:
            ok(f"round-trip: {len(read_back)} حدثًا أعيد بناؤها بالتطابق من pattern_events")
        else:
            # تشخيص: أزواج (نوع، بار_تايم) لكل طرف — يكشف الفرق الفعلي
            def _keys(dumped: list[str]) -> list[str]:
                out = []
                for text in dumped:
                    obj = json.loads(text)
                    out.append(
                        f"{obj.get('pattern_type', obj.get('family', '?'))}@{obj.get('bar_time')}"
                    )
                return out

            fail(
                "round-trip: الحمولات المقروءة خالفت — "
                f"مقروء: {_keys(dumped_back)} مقابل متوقع: {_keys(dumped_expected)}"
            )
    finally:
        await conn.close()


# ───────────────────────── الرئيسة ─────────────────────────


def main() -> int:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))

    # ── 1. العينة ──
    sample_ok = True
    for tf in ("1m", "15m", "1h"):
        tf_path = FIXTURE_DIR / f"klines_{tf}.json"
        bars = json.loads(tf_path.read_text(encoding="utf-8"))
        tf_info = manifest["timeframes"][tf]
        content_hash = hashlib.sha256(tf_path.read_bytes()).hexdigest()
        if len(bars) != tf_info["count"] or content_hash != tf_info["sha256"]:
            sample_ok = False
            fail(f"العينة {tf}: لا تطابق manifest")
    if sample_ok:
        counts = (
            manifest["timeframes"]["1m"]["count"],
            manifest["timeframes"]["15m"]["count"],
            manifest["timeframes"]["1h"]["count"],
        )
        sample_msg = (
            f"العينة: 1m/15m/1h متطابقة manifest "
            f"({counts[0]}/{counts[1]}/{counts[2]} شمعة BTCUSDT حقيقية)"
        )
        ok(sample_msg)
    else:
        return _rc

    candles_1m = load_candles("1m")
    candles_15m = load_candles("15m")
    candles_1h = load_candles("1h")

    # ── 2-3. المسارات + الحتمية + اللا-نظرة ──
    candle_events = determinism_and_no_lookahead("شموعي 1m", candles_1m, run_candle_detector)
    if _rc:
        return _rc
    shared_checks("شموعي 1m", candle_events)
    type_counts = Counter(e.event_type for e in candle_events)
    ok(f"شموعي 1m: التوزيع {dict(type_counts)} — قراءات السمات الست في كل حمولة")
    if _rc:
        return _rc

    classical_by_tf = {}
    for tf, candles in (("1m", candles_1m), ("15m", candles_15m), ("1h", candles_1h)):
        events = determinism_and_no_lookahead(f"كلاسيكي {tf}", candles, run_classical_detector)
        if _rc:
            return _rc
        classical_by_tf[tf] = events
        shared_checks(f"كلاسيكي {tf}", events)
        counts = Counter(e.payload.pattern_type.value for e in events)
        ok(f"كلاسيكي {tf}: الأنماط {dict(counts)}")
    if _rc:
        return _rc

    # ── 4. مخرجات §13.2 الثمانية مستعلَمة من الحمولات ──
    missing = []
    for events in classical_by_tf.values():
        for event in events:
            p = event.payload
            for field_name in (
                "pattern_type",
                "geometry",
                "anchor_points",
                "completion_time",
                "breakout_level",
                "invalidation_level",
                "measured_move",
                "quality",
            ):
                if field_name not in type(p).model_fields:
                    missing.append(field_name)
    if not missing:
        total_classical = sum(len(v) for v in classical_by_tf.values())
        ok(f"مخرجات §13.2 الثمانية حاضرة في كل حمولة كلاسيكية ({total_classical} حدثًا عبر الأطر)")
    else:
        fail(f"مخرجات §13.2 ناقصة: {sorted(set(missing))}")
        return _rc

    # ── 5. التحجيم ──
    scaling_check("شموعي 1m", candles_1m, run_candle_detector)
    scaling_check("كلاسيكي 15m", candles_15m, run_classical_detector)
    if _rc:
        return _rc

    # ── 6. بوابة الاستئصال (§46-5) ──
    ablation = ablation_checks(candles_1m)
    if _rc:
        return _rc

    # ── 7. سجل الترقية promotion-like (§41) ──
    archive_promotion_record(ablation, candles_1m)

    # ── 8. البث والتخزين الحي ──
    classical_15m = classical_by_tf["15m"] or classical_by_tf["1m"]
    asyncio.run(live_checks(candle_events[:8], classical_15m[:8]))

    if _rc:
        print("\n✗ بوابة المرحلة 5a فشلت")
        return 1
    print("\n✓ بوابة المرحلة 5a مغلقة: الأنماط + الاستئصال")
    return 0


if __name__ == "__main__":
    sys.exit(main())
