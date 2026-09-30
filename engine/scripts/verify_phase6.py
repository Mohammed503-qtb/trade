#!/usr/bin/env python3
"""بوابة خروج المرحلة 6 — دمج الدليل (build_plan §D + D-03 + §46).

يتطلب بنية حية (postgres عند الرأس 0006) وعينات حقيقية: phase2 الثلاثية
الأطر (1m/15m/1h شموع BTCUSDT) وphase4 (صفقات aggTrades للفوتبرنت).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينتان**: الأطر الثلاثة وصفقات phase4 متطابقة مع manifest.
2. **الأحداث الحقيقية عبر العائلات الأربع**: بنية وسيولة (3-b/3-d)
   وتدفق (4-c/4-d) وأنماط (5-b/5-c) على البيانات الحقيقية — كلها
   أنواع §20 قانونية.
3. **بناء السجل (6.1+6.3)**: سيناريو LONG وسيناريو SHORT عند لحظة قرار
   حقيقية مع لقطة حالة موثقة (نظام/تقلب/انحياز من محركات المرحلة 2-3) —
   الاصطفاف نسبي والانحياز المؤكد دليل بنية مشتق من الحالة.
4. **c_i بمعادلة §19.2 حرفيًا**: إعادة حساب مستقلة لكل سجل تطابق
   المساهمات المخزنة.
5. **السقوف (D-03-أ)**: كل درجة مجموعة ≤ سقفها الفعلي والدرجة الخام
   داخل (-1, +1) والمجموعات بترتيب جدول §19.3.
6. **حقنة الدفعة الواحدة (6.3 حرفيًا)**: أربع حمولات حقيقية عند شمعة
   واحدة ⇒ خصم {1، γ، γ²، γ³} بالترتيب وكل مجموعة تحت سقفها —
   والدفعات الحقيقية متعددة الأحداث في العينة موضع فحص كذلك.
7. **إعادة التوزيع الحتمية (D-03-ب + A-01)**: استبعاد أدلة التدفق ⇒
   توقيع الإتاحة يعلن غياب ORDER_FLOW وحصتها 0.30 معاد توزيعها
   تناسبيًا والحصص الفعالة مجموعها 1.0.
8. **التناقض (§19.5) والـveto (D-03-د)**: المعارضة تخفض ولا تلغي (حقن
   دليل معاكس حقيقي) — وveto مُحقن يعلن بلا مساس برقم واحد.
9. **الحتمية**: مساران كاملان (بناء + حساب) ⇒ لقطتان متطابقتان بايت-بايت.
10. **لا-نظرة-مستقبلية (§26.3)**: أدلة الأحداث المبكرة لا تتغير بوجود
    الأحداث اللاحقة (بادئة ⊆ كامل عند لحظة القرار نفسها) — دفعات
    الارتباط لا تمتد عبر الشموع فالخصم مستقر.
11. **التحجيم λ=2**: مضاعفة الأسعار ⇒ نفس السجل واللقطة حرفيًا (كل
    القياسات مطبَّعة: مضاعفات ATR ونِسَب وحصص وجودة).
12. **القانونية**: كل سجل دليل يمر مخططه المصدَّر (jsonschema ضد
    EvidenceRecord.schema.json) وكل لقطة تمر FusionSnapshot.schema.json —
    والمعايرة مؤجلة موثقة (§19.6: الدرجة الخام ليست احتمالًا).
13. **التفسير (§2.8)**: كائن شرح لكل سيناريو يمر الفحص الآلي للاكتمال
    (فحصان: قبول ورفض بسبب مستند).
14. **القاعدة الحية + السلسلة باستعلام واحد (بوابة الخروج 6 نصًا)**:
    كتابة سجل السيناريو ولقطته إلى evidence_items/fusion_snapshots ثم
    قراءة السلسلة الكاملة بجولة SQL واحدة — round-trip بالتساوي عبر
    النماذج وإعادة إرسال idempotent.

لا NATS في هذه المرحلة (قرار موثق في ADR-024): الدمج مستهلك أحداث لا
منتِجها — التوصيل الحي مع مقترحات السيناريوهات (المرحلة 7).
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# الاستيرادات بعد تهيئة مسارات الحزم (نمط verify_phase3/4/5 حرفيًا:
# عبارات مستقيمة — ruff يسمح بها قبل الاستيرادات ولا يسمح بالحلقات)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "fusion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "patterns" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "orderflow" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "liquidity" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "structure" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "market_state" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "features" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "schemas" / "src"))

import jsonschema
from features import (
    directional_efficiency_series,
    normalized_range_series,
    range_expansion_series,
    volume_concentration_series,
)
from fusion.compute import FusionEngine, contribution
from fusion.explain import build_explanation
from fusion.ledger import EvidenceLedgerBuilder
from fusion.parameter_sets import FusionConfig
from liquidity import LiquidityEngine
from market_state import (
    HtfBiasEngine,
    HtfBiasInputs,
    RegimeClassifier,
    RegimeFeatures,
    SnapshotInputs,
    build_snapshot,
)
from market_state.volatility import VolatilityEngine
from orderflow.absorption import AbsorptionDetector
from orderflow.continuation import ContinuationEmitter
from orderflow.exhaustion import ExhaustionDetector
from orderflow.footprint import FootprintBuilder
from orderflow.imbalance import ImbalanceClusterDetector
from orderflow.rows import BarRows
from patterns.candle_patterns import CandlePatternDetector
from patterns.classical import ClassicalPatternDetector
from schemas import (
    Direction,
    EventType,
    EvidenceGroup,
    ExplanationObject,
    validate_explanation_completeness,
)
from schemas.export import GENERATED_DIR
from schemas.orderflow import (
    AbsorbedPressure,
    AbsorptionConditions,
    AbsorptionEventPayload,
)
from schemas.patterns import (
    CandlePatternEventPayload,
    CandlePatternFamily,
    PatternDirection,
)
from schemas.structure import (
    BreakDirection,
    DisplacementEventPayload,
    StructureBreakPayload,
    SwingScope,
)
from structure import StructureEngine

ENGINE_ROOT = Path(__file__).resolve().parents[1]
PHASE2_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase2"
PHASE4_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase4"

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAMES = ("1m", "15m", "1h")
LTF_TIMEFRAME = "1m"
HTF_TIMEFRAME = "1h"
SCENARIO_LONG = "verify-phase6:BTCUSDT:LONG"
SCENARIO_SHORT = "verify-phase6:BTCUSDT:SHORT"

_rc = 0
_checks = 0


def ok(msg: str) -> None:
    global _rc, _checks
    _checks += 1
    print(f"✓ {msg}")


def fail(msg: str) -> None:
    global _rc, _checks
    _rc = 1
    _checks += 1
    print(f"✗ {msg}")


def check(condition: bool, message_ok: str, message_fail: str) -> None:
    if condition:
        ok(message_ok)
    else:
        fail(message_fail)


# ───────────────────────── تحميل العينات ─────────────────────────


def load_phase2() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    klines_by_tf: dict[str, list[dict[str, Any]]] = {}
    manifest = json.loads((PHASE2_DIR / "manifest.json").read_text(encoding="utf-8"))
    for tf in TIMEFRAMES:
        klines_by_tf[tf] = json.loads(
            (PHASE2_DIR / f"klines_{tf}.json").read_text(encoding="utf-8")
        )
    return klines_by_tf, manifest


def load_phase4() -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    from ingestion.raw_store import read_parquet_bytes

    raw = (PHASE4_DIR / "trades.parquet").read_bytes()
    trades = read_parquet_bytes(raw)
    klines = json.loads((PHASE4_DIR / "klines.json").read_text(encoding="utf-8"))
    manifest = json.loads((PHASE4_DIR / "manifest.json").read_text(encoding="utf-8"))
    return trades, klines, manifest


def klines_to_candles(
    bars: list[dict[str, Any]], timeframe: str, instrument: str = INSTRUMENT
) -> list[Any]:
    """محول عينة → شموع قانونية (نمط verify_phase2/3/4 حرفيًا)."""
    import math

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
                instrument_id=instrument,
                timeframe=timeframe,
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


def scaled_klines(bars: list[dict[str, Any]], lam: float) -> list[dict[str, Any]]:
    """ترميز λ على الشموع المرجعية (OHLC فقط — الحجوم كما هي)."""
    return [
        {
            **bar,
            "open": float(bar["open"]) * lam,
            "high": float(bar["high"]) * lam,
            "low": float(bar["low"]) * lam,
            "close": float(bar["close"]) * lam,
        }
        for bar in bars
    ]


# ───────────────────── مسار الأحداث الكامل ─────────────────────


class FusionRun:
    """تشغيل واحد: كل كواشف المراحل 3-5a على العينات ⇒ الأحداث ولقطة
    الحالة — كل المخرجات قابلة للمقارنة بايت-بايت."""

    def __init__(
        self,
        klines_by_tf: dict[str, list[dict[str, Any]]],
        trades: list[Any],
        trades_klines: list[dict[str, Any]],
        *,
        lam: float = 1.0,
    ) -> None:
        self.lam = lam
        #: أحداث نافذة phase2 (بنية + سيولة + أنماط عبر الأطر الثلاثة)
        self.phase2_events: list[tuple[str, Any]] = []
        #: أحداث نافذة الصفقات (تدفق phase4) — نافذة زمنية لاحقة منفصلة
        self.orderflow_events: list[tuple[str, Any]] = []
        self.events: list[tuple[str, Any]] = []  # phase2 ثم التدفق (ترتيب حتمي)
        self.bias_final: Any = None
        self.regime_final: Any = None
        self.vol_final: Any = None
        #: لحظتا قرار: نهاية نافذة phase2 (A) ونهاية نافذة الصفقات (B)
        self.as_of_phase2: datetime | None = None
        self.as_of: datetime | None = None
        self._run(klines_by_tf, trades, trades_klines)

    def _run(
        self,
        klines_by_tf: dict[str, list[dict[str, Any]]],
        trades: list[Any],
        trades_klines: list[dict[str, Any]],
    ) -> None:
        # ── الشموع لكل إطار (λ على الأسعار عند الطلب) ──
        candles_by_tf = {
            tf: klines_to_candles(scaled_klines(bars, self.lam) if self.lam != 1.0 else bars, tf)
            for tf, bars in klines_by_tf.items()
        }
        self.as_of_phase2 = candles_by_tf[LTF_TIMEFRAME][-1].bar_time
        trades_feed_instrument = f"{trades[0].venue}:{trades[0].symbol}"
        trades_candles = klines_to_candles(
            scaled_klines(trades_klines, self.lam) if self.lam != 1.0 else trades_klines,
            LTF_TIMEFRAME,
            instrument=trades_feed_instrument,
        )
        self.as_of = trades_candles[-1].bar_time  # نهاية نافذة الصفقات (الأحدث)

        # ── البنية + السيولة على 1m (نمط verify_phase3: المتطرفات المؤكدة
        #    هذا الشريط تُغذى السيولة عند شمعة تأكيدها §26.3) ──
        vol_ltf = VolatilityEngine()
        structure = StructureEngine()
        liquidity = LiquidityEngine()
        known_swings: set[str] = set()
        for candle in candles_by_tf[LTF_TIMEFRAME]:
            vstate = vol_ltf.update(candle)
            for event in structure.update(candle, vstate):
                self.phase2_events.append((event.event_type.value, event))
            fresh = [
                s
                for s in structure.swings
                if s.swing_id not in known_swings and s.confirmation_time <= candle.bar_time
            ]
            known_swings.update(s.swing_id for s in fresh)
            for event in liquidity.update(candle, vstate, fresh):
                self.phase2_events.append((event.event_type.value, event))
        self.vol_final = vol_ltf.state
        self.regime_final = self._regime_final(candles_by_tf[LTF_TIMEFRAME])

        # ── التدفق من صفقات phase4 (نمط verify_phase4: الفوتبرنت بالعبور
        #    والكواشف الأربعة على الأشرطة المقفلة بالترتيب) ──
        builder = FootprintBuilder(timeframe=LTF_TIMEFRAME)
        for trade in trades:
            scaled = (
                trade
                if self.lam == 1.0
                else trade.model_copy(update={"price": trade.price * self.lam})  # type: ignore[arg-type]
            )
            builder.add_trade(scaled)
        candle_by_time = {c.bar_time: c for c in trades_candles}
        vol_by_time = self._vol_series(trades_candles)
        absorption = AbsorptionDetector()
        exhaustion = ExhaustionDetector()
        clusters = ImbalanceClusterDetector()
        continuation = ContinuationEmitter()
        for br in builder.closed_bars_with_rows():
            bar = br.bar
            candle = candle_by_time.get(bar.bar_time)
            vol = vol_by_time.get(bar.bar_time)
            if candle is None or vol is None:
                continue
            for event in continuation.update(bar, candle, vol):
                self.orderflow_events.append((event.event_type.value, event))
            for event in absorption.update(bar, candle, vol):
                self.orderflow_events.append((event.event_type.value, event))
            for event in exhaustion.update(bar, candle, vol):
                self.orderflow_events.append((event.event_type.value, event))
            for event in clusters.update(BarRows(bar=bar, rows=br.rows)):
                self.orderflow_events.append((event.event_type.value, event))

        # ── الأنماط على الأطر الثلاثة (نمط verify_phase5) ──
        for tf in TIMEFRAMES:
            candle_detector = CandlePatternDetector()
            classical = ClassicalPatternDetector()
            for candle in candles_by_tf[tf]:
                for event in candle_detector.on_candle(candle):
                    self.phase2_events.append((event.event_type.value, event))
                for event in classical.on_candle(candle):
                    self.phase2_events.append((event.event_type.value, event))

        # ── الانحياز البنيوي على 1h (نمط verify_phase3 — إغلاق ADR-016) ──
        self.bias_final = self._htf_bias(candles_by_tf.get(HTF_TIMEFRAME, []))

        # ── السلسلة الموحدة: نافذة phase2 ثم نافذة التدفق (ترتيب حتمي) ──
        self.events = self.phase2_events + self.orderflow_events

    def _vol_series(self, candles: list[Any]) -> dict[Any, Any]:
        engine = VolatilityEngine()
        series: dict[Any, Any] = {}
        for candle in candles:
            state = engine.update(candle)
            if state is not None:
                series[candle.bar_time] = state
        return series

    def _regime_final(self, candles: list[Any]) -> Any:
        """النظام النهائي على 1m بمقاييس المرحلة 2 (نمط verify_phase2)."""

        def _f(value: float | None) -> float | None:
            return None if value is None else (None if value != value else value)  # nan ⇒ None

        engine = RegimeClassifier()
        eff = directional_efficiency_series(candles, window=20)
        nrange = normalized_range_series(candles, atr_period=14)
        vconc = volume_concentration_series(candles, window=20)
        rexp = range_expansion_series(candles, window=100)
        final = None
        vol_lookup = self._vol_series(candles)
        for i, candle in enumerate(candles):
            vstate = vol_lookup.get(candle.bar_time)
            if vstate is None:
                continue
            final = engine.update(
                RegimeFeatures(
                    directional_efficiency=_f(eff[i]),
                    normalized_range=_f(nrange[i]),
                    atr_percentile=vstate.atr_percentile,
                    range_expansion_percentile=_f(rexp[i]),
                    volume_concentration=_f(vconc[i]),
                    gap_shock=vstate.gap_shock,
                )
            )
        return final

    def _htf_bias(self, htf_candles: list[Any]) -> Any:
        """الانحياز البنيوي النهائي على 1h (نمط verify_phase3 حرفيًا)."""
        if not htf_candles:
            return None
        vol_h = VolatilityEngine()
        structure_h = StructureEngine()
        bias_engine = HtfBiasEngine()
        last_displacement = 0
        final = None
        for candle in htf_candles:
            vstate = vol_h.update(candle)
            for event in structure_h.update(candle, vstate):
                if event.event_type in (EventType.DISPLACEMENT_UP, EventType.DISPLACEMENT_DOWN):
                    last_displacement = 1 if event.event_type is EventType.DISPLACEMENT_UP else -1
            all_swings = structure_h.swing_detector.swings
            ext_highs = [
                s.price
                for s in all_swings
                if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "HIGH"
            ]
            ext_lows = [
                s.price
                for s in all_swings
                if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "LOW"
            ]
            if vstate is not None and vstate.range_expansion_percentile is not None:
                dealing_range = None
                if ext_highs and ext_lows:
                    dealing_range = (min(ext_lows), max(ext_highs))
                final = bias_engine.update(
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
                        close_price=candle.close,
                    )
                )
        return final

    def market_state_phase2(self) -> Any:
        """لقطة الحالة عند لحظة A (نهاية نافذة phase2) — الحالات النهائية
        لمحركاتها الموضعية عند شموع 1m الأخيرة."""
        assert self.as_of_phase2 is not None and self.regime_final is not None
        assert self.vol_final is not None and self.bias_final is not None
        return build_snapshot(
            SnapshotInputs(
                instrument=INSTRUMENT,
                timeframe=LTF_TIMEFRAME,
                event_time=self.as_of_phase2,
                regime_state=self.regime_final,
                bias_state=self.bias_final,
                volatility_state=self.vol_final,
            )
        )


# ───────────────── حمولات الحقن (بنائون مباشرون بعقد الكواشف) ─────────────────


class _Injected:
    """حدث مُحقن بعقد الكواشف الثلاثي نفسه."""

    def __init__(self, event_type: EventType, event_time: datetime, payload: Any) -> None:
        self.event_type = event_type
        self.event_time = event_time
        self.payload = payload


def _break_payload(
    at: datetime, direction: BreakDirection, breach_atr: float
) -> StructureBreakPayload:
    return StructureBreakPayload(
        instrument=INSTRUMENT,
        timeframe=LTF_TIMEFRAME,
        bar_time=at,
        swing_id="swing-injection",
        swing_scope=SwingScope.EXTERNAL,
        break_direction=direction,
        breach_distance_atr=breach_atr,
        closing_acceptance=0.9,
        follow_through=0.6,
    )


def _displacement_payload(at: datetime, direction: BreakDirection) -> DisplacementEventPayload:
    return DisplacementEventPayload(
        instrument=INSTRUMENT,
        timeframe=LTF_TIMEFRAME,
        bar_time=at,
        direction=direction,
        range_zscore=3.0,
        body_fraction=0.85,
        close_location=0.9,
        atr_multiple=2.5,
        velocity=1.8,
        follow_through=0.7,
    )


def _absorption_payload(at: datetime, pressure: AbsorbedPressure) -> AbsorptionEventPayload:
    return AbsorptionEventPayload(
        instrument=INSTRUMENT,
        timeframe=LTF_TIMEFRAME,
        bar_time=at,
        absorbed_pressure=pressure,
        delta=-60.0,
        delta_share=-0.6,
        excursion_atr=0.2,
        conditions=AbsorptionConditions(
            elevated_delta=True, limited_extension=True, repeated_response=True
        ),
    )


def _candle_payload(at: datetime, direction: PatternDirection) -> CandlePatternEventPayload:
    return CandlePatternEventPayload(
        instrument=INSTRUMENT,
        timeframe=LTF_TIMEFRAME,
        bar_time=at,
        family=CandlePatternFamily.ENGULFING,
        direction=direction,
        feature_readings={
            "body_fraction": 0.7,
            "wick_asymmetry": -0.3,
            "close_location": 0.85,
            "range_percentile": 0.8,
            "gap_relationship": 0.5,
            "volume_relationship": 0.7,
        },
        strength=0.8,
        bars_in_pattern=2,
    )


# ───────────────────────── القسم الحي ─────────────────────────


def _live_chain_check(records: list[Any], snapshot: Any) -> tuple[bool, str]:
    """القاعدة الحية: كتابة + إعادة إرسال + قراءة السلسلة بجولة واحدة."""

    async def _run() -> tuple[bool, str]:
        import asyncpg
        from common.config import load_settings
        from fusion.store import FusionStore

        settings = load_settings()
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                "DELETE FROM evidence_items WHERE scenario_id LIKE 'verify-phase6:%'"
            )
            await conn.execute(
                "DELETE FROM fusion_snapshots WHERE scenario_id LIKE 'verify-phase6:%'"
            )
            store = FusionStore()
            await store.upsert_evidence(conn, records, scenario_id=SCENARIO_LONG)
            await store.upsert_snapshot(conn, snapshot)
            # إعادة الإرسال (at-least-once) — idempotent
            await store.upsert_evidence(conn, records, scenario_id=SCENARIO_LONG)
            await store.upsert_snapshot(conn, snapshot)
            n_rows = await conn.fetchval(
                "SELECT count(*) FROM evidence_items WHERE scenario_id = $1", SCENARIO_LONG
            )
            restored, restored_snapshot = await store.read_chain(conn, SCENARIO_LONG)
            if n_rows != len(records) or len(restored) != len(records):
                return False, f"عدد الصفوف {n_rows} ≠ السجل {len(records)}"
            if restored_snapshot is None or restored_snapshot != snapshot:
                return False, "اللقطة المستعادة لا تطابق"
            by_id = {r.evidence_id: r for r in records}
            for record in restored:
                if by_id[record.evidence_id] != record:
                    return False, f"سجل مستعاد خالف: {record.evidence_id}"
            return True, (
                f"القاعدة الحية: السلسلة باستعلام واحد — {len(restored)} سجلًا + اللقطة "
                "في جولة SQL واحدة، round-trip بالتساوي وإعادة إرسال idempotent"
            )
        finally:
            await conn.execute(
                "DELETE FROM evidence_items WHERE scenario_id LIKE 'verify-phase6:%'"
            )
            await conn.execute(
                "DELETE FROM fusion_snapshots WHERE scenario_id LIKE 'verify-phase6:%'"
            )
            await conn.close()

    return asyncio.run(_run())


# ───────────────────────── الفحوص ─────────────────────────


def main() -> int:
    print("═══ بوابة المرحلة 6: دمج الدليل (§19 + D-03) ═══")

    # ── 1) العينتان ──
    klines_by_tf, manifest2 = load_phase2()
    trades, klines4, manifest4 = load_phase4()
    check(
        all(len(klines_by_tf[tf]) == manifest2["timeframes"][tf]["count"] for tf in TIMEFRAMES),
        f"العينة الثلاثية الأطر مطابقة manifest ({'/'.join(TIMEFRAMES)})",
        "عينة phase2 لا تطابق manifest",
    )
    check(
        len(trades) == manifest4["event_count"],
        f"عينة صفقات phase4 مطابقة manifest ({len(trades)} صفقة)",
        "عينة phase4 لا تطابق manifest",
    )

    # ── 2+3) المسار الكامل ولحظتا القرار ──
    trades_klines4 = klines4
    run = FusionRun(klines_by_tf, trades, trades_klines4)
    type_counts = Counter(name for name, _ in run.events)
    legal_types = {member.value for member in EventType}
    check(
        set(type_counts) <= legal_types and len(type_counts) >= 10,
        f"الأحداث عبر العائلات الأربع: {len(run.events)} حدثًا بـ{len(type_counts)} نوعًا قانونيًا "
        f"بنافذتين منفصلتين (phase2: {len(run.phase2_events)}، تدفق: {len(run.orderflow_events)})"
        f" — أكثرها: {dict(type_counts.most_common(4))}",
        f"أنواع غير قانونية أو شحّ خانق: {set(type_counts) - legal_types} / {len(type_counts)}",
    )
    assert run.as_of is not None and run.as_of_phase2 is not None

    builder = EvidenceLedgerBuilder()
    engine = FusionEngine()

    # ── لحظة A (نهاية نافذة phase2): أحداث النافذة فقط — أحداث التدفق
    #    مستقبلية عند هذه اللحظة فلا تدخل قرارها (لا-نظرة §26.3 بالحرس الصاخب) ──
    state_a = run.market_state_phase2()
    derived_bias = state_a.htf_bias.value in ("BULLISH", "BEARISH")
    check(
        state_a.htf_bias.value in ("BULLISH", "BEARISH", "NEUTRAL", "TRANSITION", "UNKNOWN"),
        f"لقطة الحالة عند A: نظام {state_a.regime.value}، انحياز {state_a.htf_bias.value}"
        f"{' (دليل بنية مشتق)' if derived_bias else ' (لا يُختلق دليل لغير المؤكد)'}، "
        f"تقلب مئينه {state_a.volatility_percentile:.1f}",
        f"قيمة انحياز غير قانونية: {state_a.htf_bias.value}",
    )
    records_a = builder.build(
        [ev for _, ev in run.phase2_events],
        scenario_id=SCENARIO_LONG + ":A",
        direction=Direction.LONG,
        as_of=run.as_of_phase2,
        market_state=state_a,
    )
    snapshot_a = engine.compute(
        records_a,
        scenario_id=SCENARIO_LONG + ":A",
        direction=Direction.LONG,
        fusion_time=run.as_of_phase2,
    )
    n_support_a = sum(1 for r in records_a if not r.opposition)
    n_oppose_a = sum(1 for r in records_a if r.opposition)
    expected_a = len(run.phase2_events) + (1 if derived_bias else 0)
    check(
        len(records_a) == expected_a,
        f"سجل A (نافذة phase2): {len(records_a)} سجلًا"
        f"{' (منها دليل انحياز مشتق)' if derived_bias else ''} — مساندة {n_support_a} "
        f"ومعارضة {n_oppose_a}؛ ومجموعات حاضرة: "
        f"{[i.group.value for i in snapshot_a.group_scores]}",
        f"طول سجل A غير متوقع: {len(records_a)} ≠ {expected_a}",
    )

    # ── لحظة B (نهاية نافذة الصفقات): السلسلة الكاملة — أحداث phase2
    #    أقدم بيومين فطراوتها صفرية (تسجَّل ولا تؤهل) والتدفق طازج ──
    all_events = [ev for _, ev in run.events]
    records_long = builder.build(
        all_events,
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        as_of=run.as_of,
    )
    records_short = builder.build(
        all_events,
        scenario_id=SCENARIO_SHORT,
        direction=Direction.SHORT,
        as_of=run.as_of,
    )
    snapshot_long = engine.compute(
        records_long, scenario_id=SCENARIO_LONG, direction=Direction.LONG, fusion_time=run.as_of
    )
    snapshot_short = engine.compute(
        records_short, scenario_id=SCENARIO_SHORT, direction=Direction.SHORT, fusion_time=run.as_of
    )
    n_support = sum(1 for r in records_long if not r.opposition)
    n_oppose = sum(1 for r in records_long if r.opposition)
    stale = sum(1 for r in records_long if r.freshness == 0.0)
    present_b = [i.group.value for i in snapshot_long.group_scores]
    check(
        len(records_long) == len(run.events) and present_b == ["ORDER_FLOW", "PRICE_ACTION"],
        f"سجل B الكامل: {len(records_long)} سجلًا — أحداث 1m/15m الأقدم من عمرها موثقة "
        f"بطراوة صفرية ({stale}) ولا تؤهل (D-03-أ «الأعضاء المؤهلون»)، وأنماط 1h طرية "
        f"بسلّمها الزمني (عمر 60 شمعة في الإطار الساعي) والتدفق طازج ⇒ الحاضرات "
        f"{present_b} — مساندة {n_support} ومعارضة {n_oppose}؛ SHORT مرآته ({len(records_short)})",
        f"سجل B غير متوقع: {len(records_long)} سجلًا، بليغة {stale}، حاضرات {present_b}",
    )

    # ── 4) c_i بمعادلة §19.2 حرفيًا (مرجع مستقل) ──
    mismatches = [
        r.evidence_id
        for r in records_long
        if contribution(r)
        != r.prior_weight
        * r.direction_score
        * r.raw_strength
        * r.quality
        * r.freshness
        * r.independence_discount
        * r.context_modifier
    ]
    check(
        not mismatches,
        f"c_i بمعادلة §19.2 حرفيًا — إعادة حساب مستقلة لكل الـ{len(records_long)} سجلًا تطابقت",
        f"مساهمات تخالف المعادلة: {mismatches[:3]}",
    )

    # ── 5) السقوف والترتيب ──
    caps_ok = all(item.score <= item.effective_share + 1e-12 for item in snapshot_long.group_scores)
    expected_order = [
        g for g in EvidenceGroup if any(i.group is g for i in snapshot_long.group_scores)
    ]
    order_ok = [item.group for item in snapshot_long.group_scores] == expected_order
    check(
        caps_ok and order_ok and -1.0 <= snapshot_long.raw_evidence_score <= 1.0,
        f"السقوف: كل مجموعة ≤ سقفها الفعلي ودرجة LONG الخام "
        f"{snapshot_long.raw_evidence_score:+.4f} داخل (-1, +1) بترتيب §19.3 — مجموعات حاضرة: "
        f"{[i.group.value for i in snapshot_long.group_scores]}",
        "خرق سقف أو ترتيب أو نطاق",
    )

    # ── 6) حقنة الدفعة الواحدة (بوابة 6.3 حرفيًا) ──
    gamma = FusionConfig().independence_decay
    injection_time = run.as_of - timedelta(minutes=5)
    injected = [
        _Injected(
            EventType.EXTERNAL_BOS,
            injection_time,
            _break_payload(injection_time, BreakDirection.UP, 5.0),
        ),
        _Injected(
            EventType.DISPLACEMENT_UP,
            injection_time,
            _displacement_payload(injection_time, BreakDirection.UP),
        ),
        _Injected(
            EventType.ABSORPTION_BUY,
            injection_time,
            _absorption_payload(injection_time, AbsorbedPressure.SELL),
        ),
        _Injected(
            EventType.BULLISH_ENGULFING,
            injection_time,
            _candle_payload(injection_time, PatternDirection.BULLISH),
        ),
    ]
    injected_records = builder.build(
        injected, scenario_id="verify-phase6:injection", direction=Direction.LONG, as_of=run.as_of
    )
    discounts = sorted((r.independence_discount for r in injected_records), reverse=True)
    injected_snapshot = engine.compute(
        injected_records,
        scenario_id="verify-phase6:injection",
        direction=Direction.LONG,
        fusion_time=run.as_of,
    )
    batch_ok = (
        len({r.correlation_group_id for r in injected_records}) == 1
        and discounts == [1.0, gamma, gamma**2, gamma**3]
        and all(i.score <= i.effective_share for i in injected_snapshot.group_scores)
    )
    check(
        batch_ok,
        f"حقنة الدفعة الواحدة: 4 أحداث عند شمعة واحدة ⇒ خصم هندسي هابط "
        f"(1 ثم {gamma} ثم {gamma**2:.3f} ثم {gamma**3:.3f}) وكل مجموعة تحت سقفها",
        f"الحقنة خالفت العقد: خصومات {discounts}",
    )
    real_batches = Counter(r.correlation_group_id for r in records_long if r.correlation_group_id)
    multi = {k: v for k, v in real_batches.items() if v > 1}
    check(
        len(multi) >= 1,
        f"دفعات حقيقية متعددة الأحداث في العينة: {len(multi)} دفعة (أكبرها "
        f"{max(multi.values()) if multi else 0} أحداث) — كلها مخصومة بالترتيب نفسه",
        "لا دفعات متعددة الأحداث في العينة الحقيقية (غير متوقع)",
    )

    # ── 7) إعادة التوزيع الحتمية (D-03-ب + A-01) — لحظة A حالة A-01
    #    الطبيعية: لا فوتبرنت عند قرار نافذة phase2 (غياب المصدر لا خلو
    #    صامت) — واللحظة B معكوسة (الأطر الأقدم بطراوة صفرية) ──
    availability = snapshot_a.availability
    flow_share = FusionConfig().group_shares[EvidenceGroup.ORDER_FLOW]
    absent_share_a = sum(FusionConfig().group_shares[g] for g in availability.absent_groups)
    check(
        EvidenceGroup.ORDER_FLOW in availability.absent_groups
        and abs(sum(availability.effective_shares.values()) - 1.0) < 1e-9
        and abs(availability.redistributed_share - absent_share_a) < 1e-9
        and abs(
            snapshot_a.availability.effective_shares[EvidenceGroup.STRUCTURE]
            - FusionConfig().group_shares[EvidenceGroup.STRUCTURE] / (1.0 - absent_share_a)
        )
        < 1e-9,
        f"إعادة التوزيع (A): التوقيع يعلن غياب التدفق ({flow_share:.2f}) والجلسة/الكلي "
        f"({absent_share_a:.2f} معاد توزيعها تناسبيًا) والحصص الفعلية مجموعها 1.0 "
        "وبترتيب §19.3: "
        f"{[(g.value, round(s, 4)) for g, s in availability.effective_shares.items()]}",
        "إعادة التوزيع خالفت D-03-ب",
    )

    # ── 8) التناقض والـveto ──
    bearish = _Injected(
        EventType.EXTERNAL_BOS,
        injection_time,
        _break_payload(injection_time, BreakDirection.DOWN, 4.0),
    )
    with_contradiction = builder.build(
        [*all_events[-50:], bearish],
        scenario_id="verify-phase6:contradiction",
        direction=Direction.LONG,
        as_of=run.as_of,
    )
    snap_contradiction = engine.compute(
        with_contradiction,
        scenario_id="verify-phase6:contradiction",
        direction=Direction.LONG,
        fusion_time=run.as_of,
    )
    snap_clean = engine.compute(
        with_contradiction[:-1],
        scenario_id="verify-phase6:contradiction",
        direction=Direction.LONG,
        fusion_time=run.as_of,
    )
    last = with_contradiction[-1]
    check(
        last.opposition
        and last.direction_score == -1.0
        and snap_contradiction.raw_evidence_score < snap_clean.raw_evidence_score
        and snap_contradiction.raw_evidence_score > -1.0,
        f"التناقض (§19.5): دليل معاكس حقيقي يخفض الدرجة "
        f"({snap_clean.raw_evidence_score:+.4f} → {snap_contradiction.raw_evidence_score:+.4f}) "
        f"ولا يلغيها — وقائمة المعارضة الصريحة تحمله",
        "التناقض خالف «يخفض ولا يلغي»",
    )
    snap_veto = engine.compute(
        records_long,
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        fusion_time=run.as_of,
        veto_reasons=("DATA_STALE",),
    )
    check(
        snap_veto.vetoed
        and snap_veto.raw_evidence_score == snapshot_long.raw_evidence_score
        and snap_veto.group_scores == snapshot_long.group_scores,
        "veto (D-03-د): معلن بلا مساس برقم واحد (نفس الدرجة والمجموعات تمامًا)",
        "veto مسّ الحساب",
    )

    # ── 9) الحتمية ──
    rerun_records = builder.build(
        all_events,
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        as_of=run.as_of,
    )
    rerun_snapshot = engine.compute(
        rerun_records, scenario_id=SCENARIO_LONG, direction=Direction.LONG, fusion_time=run.as_of
    )
    check(
        [r.model_dump_json() for r in rerun_records] == [r.model_dump_json() for r in records_long]
        and rerun_snapshot.model_dump_json() == snapshot_long.model_dump_json(),
        "الحتمية: مساران كاملان (بناء + حساب) ⇒ السجل واللقطة متطابقان بايت-بايت",
        "انحرف المسار الثاني",
    )

    # ── 10) لا-نظرة-مستقبلية ──
    cut = run.as_of - timedelta(minutes=30)
    prefix_events = [ev for ev in all_events if ev.event_time <= cut]
    prefix_records = builder.build(
        prefix_events,
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        as_of=run.as_of,
    )
    full_by_id = {r.evidence_id: r for r in records_long}
    prefix_stable = all(
        full_by_id[r.evidence_id] == r
        for r in prefix_records
        if r.source != "market_state.htf_bias"
    )
    check(
        prefix_stable and len(prefix_records) >= 1,
        f"لا-نظرة (§26.3): أدلة بادئة أول 30 دقيقة ({len(prefix_records)} سجلًا) لم تتأثر "
        "بالأحداث اللاحقة — دفعات الارتباط لا تمتد عبر الشموع",
        "أدلة البادئة تأثرت بالذيل",
    )

    # ── 11) التحجيم λ=2 ──
    scaled_run = FusionRun(klines_by_tf, trades, trades_klines4, lam=2.0)
    scaled_records = builder.build(
        [ev for _, ev in scaled_run.events],
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        as_of=scaled_run.as_of,
    )
    scaled_snapshot = engine.compute(
        scaled_records,
        scenario_id=SCENARIO_LONG,
        direction=Direction.LONG,
        fusion_time=scaled_run.as_of,
    )
    # المقارنة الدلالية: حقول الهوية بصمات حمولات تحمل الأسعار فتختلف
    # بالضرورة تحت λ؛ والتعادل التام داخل دفعة (إمكانات متساوية بالضبط —
    # كأحداث النافذة الأقدم طراوتها صفر عند B) يجعل إسناد الخصومات بين
    # المتعادلين تبادليًا بطبيعته — فتُقارن هوية أعضاء كل دفعة وتوزيع
    # خصوماتها منفصلين (الإجمالي والدرجات محفوظان دائمًا)
    identity = {"evidence_id", "event_id", "independence_discount"}
    semantic_equal = [r.model_dump(exclude=identity) for r in scaled_records] == [
        r.model_dump(exclude=identity) for r in records_long
    ]

    def _batch_profiles(records: list[Any]) -> dict[str, tuple[list[Any], list[float]]]:
        members: dict[str, list[tuple[str, float]]] = {}
        discounts: dict[str, list[float]] = {}
        for record in records:
            if record.correlation_group_id is None:
                continue
            members.setdefault(record.correlation_group_id, []).append(
                (record.event_type.value, record.raw_strength)
            )
            discounts.setdefault(record.correlation_group_id, []).append(
                record.independence_discount
            )
        return {key: (sorted(members[key]), sorted(discounts[key])) for key in members}

    multisets_equal = _batch_profiles(scaled_records) == _batch_profiles(records_long)
    snapshot_identity = {"evidence_ids", "opposition_evidence_ids"}
    snapshot_equal = scaled_snapshot.model_dump(
        exclude=snapshot_identity
    ) == snapshot_long.model_dump(exclude=snapshot_identity)
    check(
        semantic_equal and multisets_equal and snapshot_equal,
        "التحجيم λ=2 ⇒ نفس القيم الدليلية وأعضاء الدفعات وتوزيع خصوماتها "
        "والدرجات كاملة (كل القياسات مطبَّعة؛ بصمات الهوية وحدها تتبع الأسعار)",
        "التحجيم غيّر الدمج — قياس غير مطبَّع تسرب",
    )

    # ── 12) القانونية والمعايرة ──
    evidence_schema = json.loads((GENERATED_DIR / "EvidenceRecord.schema.json").read_text("utf-8"))
    snapshot_schema = json.loads((GENERATED_DIR / "FusionSnapshot.schema.json").read_text("utf-8"))
    for record in records_long:
        jsonschema.validate(json.loads(record.model_dump_json()), evidence_schema)
    jsonschema.validate(json.loads(snapshot_long.model_dump_json()), snapshot_schema)
    ok(f"القانونية: كل سجل دليل ({len(records_long)}) واللقطة تمر مخططاتها المصدَّرة (jsonschema)")
    check(
        snapshot_long.calibration.eligible is False
        and snapshot_long.calibration.calibrated_probability is None
        and "المرحلة 9" in snapshot_long.calibration.deferral_reason,
        "المعايرة (§19.6): مؤجلة موثقة — الدرجة الخام ليست احتمالًا أبدًا",
        "المعايرة انحرفت عن التأجيل الموثق",
    )

    # ── 13) التفسير §2.8 ──
    explanation = build_explanation(snapshot_long, records_long)
    validate_explanation_completeness(explanation, rejected=False)
    rejected_explanation = build_explanation(
        snapshot_long,
        records_long,
        rejection_reason="المشغل لم يتحقق قبل انتهاء الصلاحية",
    )
    validate_explanation_completeness(rejected_explanation, rejected=True)
    check(
        isinstance(explanation, ExplanationObject)
        and len(explanation.supporting_evidence) == n_support
        and len(explanation.opposing_evidence) == n_oppose,
        f"التفسير (§2.8): كائن مكتمل يمر الفحص الآلي بوضعي القبول والرفض — "
        f"{len(explanation.supporting_evidence)} مساندة و{len(explanation.opposing_evidence)} "
        "معارضة بسطر لكل دليل بمساهمته الموقعة",
        "كائن التفسير ناقص أو مخالف للسجل",
    )

    # ── 14) القاعدة الحية + السلسلة باستعلام واحد ──
    try:
        live_ok, live_msg = _live_chain_check(records_long, snapshot_long)
    except Exception as exc:
        live_ok, live_msg = False, f"فشل القسم الحي: {exc}"
    if live_ok:
        ok(live_msg)
    else:
        fail(live_msg)

    # ── الخلاصة ──
    print("─" * 64)
    if _rc == 0:
        print(f"✓ بوابة المرحلة 6 مغلقة: الدمج — {_checks} فحصًا أخضر")
        print(
            f"  الدرجة الخام LONG: {snapshot_long.raw_evidence_score:+.4f} | "
            f"SHORT: {snapshot_short.raw_evidence_score:+.4f} (ليست احتمالًا §2.6)"
        )
    else:
        print(f"✗ فشل بوابة المرحلة 6 — راجع الفحوص أعلاه ({_checks} فحصًا)")
    return _rc


if __name__ == "__main__":
    sys.exit(main())
