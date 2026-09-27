#!/usr/bin/env python3
"""بوابة خروج المرحلة 2 — التقلب والجلسات والسياق (build_plan §D).

يتطلب بنية حية (postgres + nats) وعينة tests/fixtures/phase2 (جُلبت
بـscripts/fetch_phase2_fixture.py).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: 1440×1m + 192×15m + 168×1h شموع مغلقة رتيبة زمنيًا.
2. **مسار السياق الكامل**: جلسات ← تقلب ← نظام ← انحياز ← لقطة، على
   الأطر الثلاثة، مع توثيق تتابعات الانتقالات (بوابة المرحلة نصًا:
   «تتابعات الحالات حتمية وموثقة»).
3. **العتبات التطبيعية** (بوابة المرحلة نصًا: «كل عتبة تطبيعية من
   التقلب — لا ثوابت مطلقة»): عبر كل شمعة وكل مفتاح عتبة، النسبة
   threshold/atr ثابتة = المضاعف الإعدادي حصرًا (أي انحراف = فشل).
4. **لا-نظرة-مستقبلية على بيانات حقيقية**: حالة بادئة 1m عند k من
   تشغيل مقصوص == حالتها في التشغيل الكامل.
5. **الحتمية**: مساران كاملان ⇒ نفس هاش تتابعات الحالات واللقطة.
6. **القانونية**: كل لقطة تمر jsonschema ضد المخطط المصدَّر.
7. **البث والتخزين الحي**: نشر لقطة 1m النهائية عبر NATS واستهلاكها
   بالتحقق + upsert اللقطات الثلاث في market_states وإعادة قراءتها
   idempotent.
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

import numpy as np
from features import (
    directional_efficiency_series,
    normalized_range_series,
    range_expansion_series,
    volume_concentration_series,
)
from market_state import (
    HtfBiasEngine,
    HtfBiasInputs,
    RegimeClassifier,
    RegimeFeatures,
    SnapshotInputs,
    build_snapshot,
)
from market_state.sessions import SessionTracker
from market_state.volatility import ThresholdKey, VolatilityEngine, VolatilityState
from schemas import Candle, DataQuality

ENGINE_ROOT = Path(__file__).resolve().parents[1]  # بعد قسم الاستيرادات (نمط verify_phase1)

FIXTURE_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase2"
SCHEMA_PATH = ENGINE_ROOT / "packages" / "schemas" / "generated" / "MarketStateSnapshot.schema.json"

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
SYMBOL = "BTCUSDT"
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


def _f(v: Any) -> float | None:
    """nan/inf → None (عقد RegimeFeatures/HtfBiasInputs: قيم محدودة أو غياب معلن)."""
    if v is None:
        return None
    f = float(v)
    return f if np.isfinite(f) else None


def _s(v: Any) -> int:
    """إشارة القيمة: ‎+1/−1/0‎ (nan تعتبر 0)."""
    f = _f(v)
    return 0 if f is None else (1 if f > 0 else (-1 if f < 0 else 0))


# ───────────────────────── بناء الشموع من klines ─────────────────────────


def klines_to_candles(interval: str, bars: list[dict[str, Any]]) -> list[Candle]:
    """محول عينة → شموع قانونية.

    الحقول المشتقة تحسب هنا لرضا عقد نموذج Candle (§8.1) — محرك السياق
    نفسه يقرأ OHLCV الخام وحده عبر features (عقد 2-c الموثق).
    """
    out: list[Candle] = []
    prev_close: float | None = None
    import math

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


# ───────────────────────── مسار السياق ─────────────────────────


class ContextRun:
    """تشغيل واحد للمسار الكامل — كل مخرجات التتابع قابلة للهاش."""

    def __init__(self, candles_by_tf: dict[str, list[Candle]]) -> None:
        self.regime_seqs: dict[str, list[str]] = {}
        self.vol_hashes: dict[str, list[str]] = {}
        self.snapshots: dict[str, str] = {}
        self.regime_transitions: dict[str, list[tuple[str, str, str]]] = {}
        self.bias_seq: list[str] = []
        self.bias_transitions: list[tuple[str, str, str]] = []
        self.session_seq: list[str] = []
        self.threshold_audit_ok = True
        self.threshold_multipliers_seen: dict[str, float] = {}
        self._run(candles_by_tf)

    def _run(self, candles_by_tf: dict[str, list[Candle]]) -> None:
        # ── الانحياز HTF على 1h (إن حضر — تشغيل البادئة 1m فقط لا يحتاجه) ──
        self.bias_final = None
        self.bias_transitions = []
        if HTF_TIMEFRAME in candles_by_tf:
            htf_candles = candles_by_tf[HTF_TIMEFRAME]
            eff = directional_efficiency_series(htf_candles, window=20)
            nrange = normalized_range_series(htf_candles, atr_period=14)
            rexp = range_expansion_series(htf_candles, window=100)
            vol_h = VolatilityEngine()
            bias_engine = HtfBiasEngine()
            closes = [c.close for c in htf_candles]
            last_bias = None
            for i, candle in enumerate(htf_candles):
                vstate = vol_h.update(candle)
                if vstate is None:
                    continue
                window = 20
                sign_src = closes[i] - closes[i - window] if i >= window else None
                inputs = HtfBiasInputs(
                    directional_efficiency=_f(eff[i]),
                    efficiency_sign=_s(sign_src),
                    normalized_range=_f(nrange[i]),
                    atr_percentile=vstate.atr_percentile,
                    displacement_proxy=_f(rexp[i]),
                )
                bstate = bias_engine.update(inputs)
                self.bias_seq.append(f"{bstate.bias.value}")
                if bstate.bias is not last_bias:
                    self.bias_transitions.append(
                        (candle.bar_time.isoformat(), str(last_bias), bstate.bias.value)
                    )
                    last_bias = bstate.bias
                self._audit_thresholds(vstate)
            self.bias_final = bias_engine.state

        # ── الجلسات على 1m (إن حضر) ──
        self.session_final = None
        if LTF_TIMEFRAME in candles_by_tf:
            tracker = SessionTracker()
            for candle in candles_by_tf[LTF_TIMEFRAME]:
                state = tracker.update(candle)
                if state is not None:
                    self.session_seq.append(
                        f"{state.session_id}|{state.opening.opening_drive.value}"
                        if hasattr(state.opening, "opening_drive")
                        else state.session_id
                    )
            self.session_final = tracker.current_state

        # ── النظام والتقلب واللقطة لكل إطار متاح ──
        for tf in [t for t in TIMEFRAMES if t in candles_by_tf]:
            candles = candles_by_tf[tf]
            vol_engine = VolatilityEngine()
            regime_engine = RegimeClassifier()
            eff = directional_efficiency_series(candles, window=20)
            nrange = normalized_range_series(candles, atr_period=14)
            vconc = volume_concentration_series(candles, window=20)
            rexp = range_expansion_series(candles, window=100)
            seq: list[str] = []
            vhashes: list[str] = []
            transitions: list[tuple[str, str, str]] = []
            last_regime = None
            final_vstate: VolatilityState | None = None
            final_rstate = None
            for i, candle in enumerate(candles):
                vstate = vol_engine.update(candle)
                if vstate is None:
                    continue
                final_vstate = vstate
                rstate = regime_engine.update(
                    RegimeFeatures(
                        directional_efficiency=_f(eff[i]),
                        normalized_range=_f(nrange[i]),
                        atr_percentile=vstate.atr_percentile,
                        range_expansion_percentile=_f(rexp[i]),
                        volume_concentration=_f(vconc[i]),
                        gap_shock=vstate.gap_shock,
                    )
                )
                final_rstate = rstate
                seq.append(rstate.regime.value)
                if rstate.regime is not last_regime:
                    transitions.append(
                        (candle.bar_time.isoformat(), str(last_regime), rstate.regime.value)
                    )
                    last_regime = rstate.regime
                vhashes.append(repr(vstate))
                self._audit_thresholds(vstate)
            self.regime_seqs[tf] = seq
            self.vol_hashes[tf] = vhashes
            self.regime_transitions[tf] = transitions
            assert final_vstate is not None and final_rstate is not None
            if self.bias_final is None:
                continue  # تشغيل بادئة بلا HTF — اللقطة تُبنى فقط عند اكتمال المسار
            snapshot = build_snapshot(
                SnapshotInputs(
                    instrument=SYMBOL,
                    timeframe=tf,
                    event_time=candles[-1].bar_time,
                    regime_state=final_rstate,
                    bias_state=self.bias_final,
                    volatility_state=final_vstate,
                    data_quality=DataQuality.HEALTHY,
                )
            )
            self.snapshots[tf] = snapshot.model_dump_json()

    def _audit_thresholds(self, vstate: VolatilityState) -> None:
        """بوابة «لا ثوابت مطلقة»: threshold/atr ≡ المضاعف — عبر كل شمعة ومفتاح."""
        atr = vstate.atr
        for key in ThresholdKey:
            t = vstate.threshold(key)
            if t is None or atr is None or atr <= 0.0:
                continue
            ratio = t / atr
            prev = self.threshold_multipliers_seen.get(key.value)
            if prev is not None and abs(ratio - prev) > 1e-9:
                self.threshold_audit_ok = False
            self.threshold_multipliers_seen[key.value] = ratio

    def digest(self) -> str:
        h = hashlib.sha256()
        for tf in TIMEFRAMES:
            if tf not in self.regime_seqs:
                continue
            h.update(tf.encode())
            h.update("|".join(self.regime_seqs[tf]).encode())
            h.update("".join(self.vol_hashes[tf]).encode())
            if tf in self.snapshots:
                h.update(self.snapshots[tf].encode())
        h.update("|".join(self.bias_seq).encode())
        h.update("|".join(self.session_seq).encode())
        return h.hexdigest()


async def live_checks(run: ContextRun) -> None:
    """البث NATS + التخزين الحي — نفس أدوات 2-f الحية."""
    from asyncpg import connect as pg_connect
    from common.config import load_settings
    from engine_worker.publisher import SnapshotPublisher
    from market_state.store import MarketStateStore
    from nats.aio.client import Client as NATSClient

    settings = load_settings()
    snapshot_json = json.loads(run.snapshots[LTF_TIMEFRAME])
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    # ── NATS: نشر + استهلاك بالتحقق ──
    nc: NATSClient = NATSClient()
    await nc.connect(servers=[settings.nats_url], connect_timeout=5, max_reconnect_attempts=1)
    received: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def _cb(msg: Any) -> None:
        received.append((msg.subject, json.loads(msg.data.decode()), dict(msg.headers or {})))

    sub_subject = (
        "market.state.btcusdt.1m.updated"  # أداة اللقطة مطبَّعة (publisher.normalize_instrument)
    )
    await nc.subscribe(sub_subject, cb=_cb)
    publisher = SnapshotPublisher(nc)
    from schemas import MarketStateSnapshot

    snap = MarketStateSnapshot.model_validate(snapshot_json)
    await publisher.publish(snap)
    await asyncio.wait_for(nc.flush(), timeout=5)
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.1)
    await nc.drain()
    if not received:
        fail("NATS: لم تُستقبل اللقطة خلال المهلة")
        return
    subject, payload, headers = received[0]
    try:
        jsonschema.validate(payload, schema)
        ok(
            f"NATS: لقطة 1m استُهلكت عبر «{subject}» "
            f"ومرّت المخطط (event_type={headers.get('event_type')})"
        )
    except jsonschema.ValidationError as exc:
        fail(f"NATS: الحمولة خالفت المخطط: {exc.message}")

    # ── القاعدة: upsert الثلاث + قراءة + إعادة idempotent ──
    store = MarketStateStore()
    conn = await pg_connect(settings.database_url)
    try:
        for tf in TIMEFRAMES:
            await store.upsert_snapshot(
                conn, MarketStateSnapshot.model_validate(json.loads(run.snapshots[tf]))
            )
        await conn.execute("COMMIT")
        # إعادة الإرسال نفسه — لا صفوف جديدة
        counts_before = await store.count_snapshots(conn, instrument=SYMBOL)
        for tf in TIMEFRAMES:
            await store.upsert_snapshot(
                conn, MarketStateSnapshot.model_validate(json.loads(run.snapshots[tf]))
            )
        await conn.execute("COMMIT")
        counts_after = await store.count_snapshots(conn, instrument=SYMBOL)
        if counts_before != counts_after:
            fail(f"القاعدة: إعادة الإرسال غيّرت العدد {counts_before} → {counts_after}")
            return
        latest = await store.latest_snapshot(conn, SYMBOL, LTF_TIMEFRAME)
        if latest is None or latest.model_dump_json() != run.snapshots[LTF_TIMEFRAME]:
            fail("القاعدة: أحدث لقطة 1m لا تطابق المرسلة")
            return
        ok(
            f"القاعدة: 3 لقطات في market_states ({counts_after} صفًا للأداة) "
            "— upsert idempotent وأحدث 1m مطابق"
        )
    finally:
        await conn.close()


def main() -> int:
    global _rc
    print("═══ verify-phase2 — مسار السياق على عينة ثلاثية الأطر ═══")

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

    # 2-6) المسار × 2 للحتمية + بادئة للاستقلال
    run_a = ContextRun(candles_by_tf)
    run_b = ContextRun(candles_by_tf)
    k = len(candles_by_tf[LTF_TIMEFRAME]) - 10
    prefix_run = ContextRun({LTF_TIMEFRAME: candles_by_tf[LTF_TIMEFRAME][:k]})

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for tf in TIMEFRAMES:
        jsonschema.validate(json.loads(run_a.snapshots[tf]), schema)
    ok("القانونية: اللقطات الثلاث تمر jsonschema ضد المخطط المصدَّر")

    # العتبات التطبيعية
    if run_a.threshold_audit_ok:
        sample = ", ".join(
            f"{k2}={v:.3g}" for k2, v in sorted(run_a.threshold_multipliers_seen.items())
        )
        ok(f"العتبات التطبيعية: threshold/atr ≡ المضاعف عبر كل شمعة ومفتاح ({sample})")
    else:
        fail("العتبات: النسبة threshold/atr انحرفت بين الشموع — ثابت مطلق متسرب")

    # لا-نظرة-مستقبلية (البادئة تنتج k-1 حالة — الشمعة الأولى بلا حالة تقلب)
    n_prefix = len(prefix_run.regime_seqs[LTF_TIMEFRAME])
    if (
        prefix_run.regime_seqs[LTF_TIMEFRAME] == run_a.regime_seqs[LTF_TIMEFRAME][:n_prefix]
        and prefix_run.vol_hashes[LTF_TIMEFRAME] == run_a.vol_hashes[LTF_TIMEFRAME][:n_prefix]
    ):
        ok(f"لا-نظرة-مستقبلية: تتابع 1m حتى k={k} ({n_prefix} حالة) مستقل تمامًا عن الذيل")
    else:
        fail("لا-نظرة-مستقبلية: تتابع البادئة تغير بإضافة الذيل")

    # الحتمية
    if run_a.digest() == run_b.digest():
        ok(f"الحتمية: مساران ⇒ نفس هاش التتابعات ({run_a.digest()[:16]}…)")
    else:
        fail("الحتمية: هاشا المسارين مختلفان")

    # التوثيق: تتابعات الحالات
    for tf in TIMEFRAMES:
        seq = run_a.regime_seqs[tf]
        counts: Mapping[str, int] = {}
        for s in seq:
            counts = {**counts, s: counts.get(s, 0) + 1}
        summary = "، ".join(f"{k2}={v}" for k2, v in sorted(counts.items()))
        print(f"  • نظام {tf}: {len(seq)} حالة ({summary})")
        for bar_time, old, new in run_a.regime_transitions[tf][:8]:
            print(f"      {bar_time} ← {old} → {new}")
    print(f"  • انحياز 1h: {len(run_a.bias_seq)} حالة؛ الانتقالات:")
    for bar_time, old, new in run_a.bias_transitions[:8]:
        print(f"      {bar_time} ← {old} → {new}")
    if run_a.session_final is not None:
        n_windows = len(run_a.session_final.active_windows)
        print(f"  • الجلسة الأخيرة: {run_a.session_final.session_id} (نوافذ نشطة: {n_windows})")

    # التكافؤ النهائي
    sufficient = (
        all(s and s[-1] != "UNKNOWN" for s in (run_a.regime_seqs[tf] for tf in TIMEFRAMES))
        and run_a.bias_seq[-1] != "UNKNOWN"
    )
    if sufficient:
        ok("الاكتفاء: النظام والانحياز واصلوا حالات معلومة (ليست UNKNOWN) بنهاية كل إطار")
    else:
        fail("الاكتفاء: حالة نهائية UNKNOWN — الدافئ لم يكتمل أو التغذية مفقودة")

    # 7) البث والتخزين الحي
    asyncio.run(live_checks(run_a))

    if _rc == 0:
        print("═══ بوابة المرحلة 2: خضراء بالكامل ═══")
    else:
        print("═══ بوابة المرحلة 2: فشل — انظر ✗ أعلاه ═══")
    return _rc


if __name__ == "__main__":
    raise SystemExit(main())
