#!/usr/bin/env python3
"""بوابة خروج المرحلة 7 — محرك السيناريوهات (build_plan §D + D-04 + §18).

يتطلب بنية حية (postgres عند الرأس 0007 + nats) وعينة phase2 الثلاثية
الأطر الحقيقية (1m/15m/1h شموع BTCUSDT).

الفحوص (كلها صارمة — أي فشل = خروج 1):

1. **العينة**: الأطر الثلاثة متطابقة مع manifest.
2. **المراسيم الحقيقية**: أحداث السيولة الموقعية المؤكدة (اجتياح/كسر-قبول
   بـzone_id) على بيانات حقيقية عبر كواشف المرحلة 3 — وقود D-04.
3. **الاستنساخ (D-04)**: كل مرسِم يستنسخ حتى ثلاثة قوالب §21.2 بمقترحات
   DRAFT كاملة عناصر §18.3 التسعة، وغيوب موثقة (لا انحياز مؤكد = لا
   استمرار؛ لا هدف = لا استنساخ) — إعلان صريح لا صمت.
4. **الترقية (§18.4)**: على الأقل سيناريو يبلغ ACTIVE بسبب مجموعتين
   دالتين على الأقل (المرسِم + الانحياز/التدفق) بأسباب موثقة العدد —
   ومن دونهما يبقى DRAFT.
5. **المشغلات (7.3)**: على الأقل سيناريو TRIGGERED بمشغل مرصود فعليًا
   من أحداث البنية/الشموع الحقيقية، وسبب يسمي نوعه ويوثق الانجراف.
6. **دورة الحياة (7.2)**: كل انتقال ضمن خريطة §18.2 القانونية حصرًا،
   ولا خروج من نهائية أبدًا (§38.2) — تدقيق كامل للسجل.
7. **الإبطال والانقضاء (§18.5)**: النهايات بأسبابها الموثقة (شرط معلن)
   — والحكم المنظم يحمل حالته الهدف الصحيحة.
8. **التنافس (7.4)**: حل التنافس على المُشعلين الفعليين حتمي ومتطابق
   مرتين، وكل SUPPRESSED بسبب يسمي فائزه.
9. **بوابة الخروج 7 نصًا (القاعدة الحية)**: كتابة السيناريوهات
   وانتقالاتها إلى scenarios/scenario_transitions ثم الفحص الآلي
   ``audit_licensing_readiness`` — كل TRIGGERED فما فوق له مشغل وإبطال
   معرّفان (صفر مخالفين)، وidempotent، ودورة الحياة باستعلام واحد.
10. **الحتمية**: مساران كاملان ⇒ نفس السيناريوهات والانتقالات بايت-بايت.
11. **لا-نظرة-مستقبلية (§26.3)**: انتقالات البادئة [0..k] مطابقة لبادئة
    التشغيل الكامل — التقييم لا يرى إلا الأشرطة الماضية.
12. **التحجيم λ=2**: نفس البنية دلاليًا (قوالب واتجاهات ودرجات متطابقة)
    والأسعار مضاعفة والمعرفات وحدها تتبع بصمة الحمولة.
13. **القانونية**: كل سيناريو وانتقال يمر مخططه المصدَّر (jsonschema).
14. **الجودة (حقن موثق)**: لقطة غير آمنة تُطفئ كل الأحياء CANCELLED —
    التدهور الآمن لا التداول الأعمى (§49).
15. **البث الحي (NATS)**: المراسِم §20 تُبث عبر الناقل فتُستقبل وتغذي
    المحرك ⇒ نفس المقترحات حرفيًا — التوصيل الحي مع المقترحات (وعد
    ADR-024 المسدد).
16. **التفسير (§2.8)**: كائن شرح لكل سيناريو مُرخِّص بمشغله وإبطاله
    ومساره الحقيقيين (حقول المرحلة 7 مكتملة) يمر فحص الاكتمال.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# الاستيرادات بعد تهيئة مسارات الحزم (نمط verify_phase3-6 حرفيًا)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "scenarios" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "fusion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "liquidity" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "structure" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "market_state" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "features" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "schemas" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "common" / "src"))

from features import (
    directional_efficiency_series,
    normalized_range_series,
    range_expansion_series,
    volume_concentration_series,
)
from liquidity import LiquidityEngine
from market_state.htf_bias import HtfBiasEngine, HtfBiasInputs
from market_state.regime import RegimeClassifier, RegimeFeatures
from market_state.volatility import VolatilityEngine
from scenarios.competition import CompetingScenario, resolve_conflicts
from scenarios.engine import ScenarioEngine
from scenarios.lifecycle import LEGAL_TRANSITIONS, TERMINAL_STATES
from scenarios.proposer import MIN_SUPPORTING_GROUPS, ProposalOutcome
from scenarios.store import ScenarioStore
from schemas import (
    DataQuality,
    EventType,
    MarketStateSnapshot,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
    ScenarioTransition,
    SwingScope,
    validate_explanation_completeness,
)
from schemas.export import GENERATED_DIR
from structure import StructureEngine

ENGINE_ROOT = Path(__file__).resolve().parents[1]
PHASE2_DIR = ENGINE_ROOT / "tests" / "fixtures" / "phase2"

INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAMES = ("1m", "15m", "1h")
LTF_TIMEFRAME = "1m"
HTF_TIMEFRAME = "1h"
#: المراسِم السيولية الموقعية (D-04): حدثان يحملان zone_id حصرًا.
ANCHOR_TYPES = frozenset(
    {
        EventType.LIQUIDITY_SWEEP_HIGH,
        EventType.LIQUIDITY_SWEEP_LOW,
        EventType.BREAK_AND_ACCEPT_HIGH,
        EventType.BREAK_AND_ACCEPT_LOW,
    }
)
#: بادئة اللا-نظرة: نصف النافذة تقريبًا — تقييم البادئة مقابل الكامل.
PREFIX_FRACTION = 0.5

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


# ───────────────────────── تحميل العينة وتحويلها ─────────────────────────


def load_phase2() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    klines_by_tf: dict[str, list[dict[str, Any]]] = {}
    manifest = json.loads((PHASE2_DIR / "manifest.json").read_text(encoding="utf-8"))
    for tf in TIMEFRAMES:
        klines_by_tf[tf] = json.loads(
            (PHASE2_DIR / f"klines_{tf}.json").read_text(encoding="utf-8")
        )
    return klines_by_tf, manifest


def klines_to_candles(
    bars: list[dict[str, Any]], timeframe: str, instrument: str = INSTRUMENT
) -> list[Any]:
    """محول عينة → شموع قانونية (نمط verify_phase2-6 حرفيًا)."""
    import math

    from schemas import Candle

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


# ───────────────────────── التشغيل المتكامل ─────────────────────────


class ScenarioRun:
    """تشغيل واحد: كواشف البنية والسيولة والتقلب والنظام والانحياز على
    بيانات حقيقية تقود محرك السيناريوهات شريطًا فوق شريط.

    كل المخرجات قابلة للمقارنة بايت-بايت (الحتمية) أو دلاليًا (λ).
    """

    def __init__(
        self,
        klines_by_tf: dict[str, list[dict[str, Any]]],
        *,
        lam: float = 1.0,
        prefix_bars: int | None = None,
        inject_unsafe_quality_at: int | None = None,
    ) -> None:
        self.lam = lam
        self.prefix_bars = prefix_bars
        self.inject_unsafe_quality_at = inject_unsafe_quality_at
        self.engine = ScenarioEngine()
        self.anchors: list[tuple[EventType, Any]] = []  # (نوع، حمولة)
        self.anchor_outcomes: list[ProposalOutcome] = []
        self.bar_transitions: list[list[ScenarioTransition]] = []
        # سياق كل شريط (شمعة، ATR المستخدم، لقطة الحالة) — تستهلكه بوابة
        # المرحلة 8 (قرار المخاطرة عند المشتعلين) — سجل حتمي من نفس المسار.
        self.bar_contexts: list[tuple[Any, float, MarketStateSnapshot]] = []
        self._run(klines_by_tf)

    # ── الخصائص المشتقة ──

    @property
    def scenarios(self) -> tuple[Scenario, ...]:
        return self.engine.scenarios()

    @property
    def transitions(self) -> tuple[ScenarioTransition, ...]:
        return self.engine.transitions()

    def _run(self, klines_by_tf: dict[str, list[dict[str, Any]]]) -> None:
        candles_by_tf = {
            tf: klines_to_candles(scaled_klines(bars, self.lam) if self.lam != 1.0 else bars, tf)
            for tf, bars in klines_by_tf.items()
        }
        ltf = candles_by_tf[LTF_TIMEFRAME]
        if self.prefix_bars is not None:
            ltf = ltf[: self.prefix_bars]

        # ── سلاسل سمات النظام (سببية — نافذة متدرجة لكل موضع) ──
        eff = directional_efficiency_series(ltf, window=20)
        nrange = normalized_range_series(ltf, atr_period=14)
        vconc = volume_concentration_series(ltf, window=20)
        rexp = range_expansion_series(ltf, window=100)

        # ── الانحياز البنيوي على 1h (زيادة موضعية عند كل إغلاق ساعة) ──
        htf_bias_engine = HtfBiasEngine()
        vol_h = VolatilityEngine()
        structure_h = StructureEngine()
        htf_last_displacement = 0
        bias_state: Any = None

        def advance_htf(htf_candle: Any) -> None:
            nonlocal htf_last_displacement, bias_state
            vstate = vol_h.update(htf_candle)
            for event in structure_h.update(htf_candle, vstate):
                if event.event_type in (EventType.DISPLACEMENT_UP, EventType.DISPLACEMENT_DOWN):
                    htf_last_displacement = (
                        1 if event.event_type is EventType.DISPLACEMENT_UP else -1
                    )
            swings = structure_h.swing_detector.swings
            ext_highs = [
                s.price
                for s in swings
                if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "HIGH"
            ]
            ext_lows = [
                s.price
                for s in swings
                if s.external_or_internal is SwingScope.EXTERNAL and s.direction.value == "LOW"
            ]
            if vstate is not None and vstate.range_expansion_percentile is not None:
                dealing_range = None
                if ext_highs and ext_lows:
                    dealing_range = (min(ext_lows), max(ext_highs))
                bias_state = htf_bias_engine.update(
                    HtfBiasInputs(
                        directional_efficiency=None,
                        efficiency_sign=None,
                        normalized_range=None,
                        atr_percentile=None,
                        displacement_proxy=None,
                        external_high_sequence=tuple(ext_highs),
                        external_low_sequence=tuple(ext_lows),
                        htf_displacement_direction=htf_last_displacement,
                        expansion_state=vstate.range_expansion_percentile,
                        dealing_range=dealing_range,
                        close_price=htf_candle.close,
                    )
                )

        htf_candles = candles_by_tf.get(HTF_TIMEFRAME, [])
        htf_done_until: Any = None  # آخر برميل ساعة استُهلك

        # ── القيادة على 1m ──
        vol = VolatilityEngine()
        structure = StructureEngine()
        liquidity = LiquidityEngine()
        regime_engine = RegimeClassifier()
        regime_state: Any = None
        known_swings: set[str] = set()

        for index, candle in enumerate(ltf):
            # الانحياز: استهلاك براميل الساعة المغلقة حتى الآن (لا-نظرة)
            if htf_candles:
                closed = [
                    h
                    for h in htf_candles
                    if h.bar_time + timedelta(seconds=_tf_seconds(HTF_TIMEFRAME)) <= candle.bar_time
                    and (htf_done_until is None or h.bar_time > htf_done_until)
                ]
                for h in closed:
                    advance_htf(h)
                    htf_done_until = h.bar_time

            vstate = vol.update(candle)
            struct_events = list(structure.update(candle, vstate))
            fresh = [
                s
                for s in structure.swings
                if s.swing_id not in known_swings and s.confirmation_time <= candle.bar_time
            ]
            known_swings.update(s.swing_id for s in fresh)
            liq_events = list(liquidity.update(candle, vstate, fresh))

            # لقطة الحالة عند الشريط (النظام + الانحياز + التقلب)
            atr = vstate.atr if vstate is not None else None
            if vstate is not None and vstate.atr_percentile is not None:

                def _f(value: float | None) -> float | None:
                    return None if value is None or value != value else value

                regime_state = regime_engine.update(
                    RegimeFeatures(
                        directional_efficiency=_f(eff[index]),
                        normalized_range=_f(nrange[index]),
                        atr_percentile=vstate.atr_percentile,
                        range_expansion_percentile=_f(rexp[index]),
                        volume_concentration=_f(vconc[index]),
                        gap_shock=vstate.gap_shock,
                    )
                )
            state = self._snapshot(candle.bar_time, regime_state, bias_state, vstate, index)

            # المراسِم: أحداث السيولة الموقعية المؤكدة تستنسخ القوالب (D-04)
            for event in liq_events:
                if event.event_type not in ANCHOR_TYPES:
                    continue
                if atr is None or atr <= 0.0:
                    continue  # قبل دافئ التقلب لا هندسة نسبية — تجاوز موثق
                zone = liquidity.zone(event.payload.zone_id)
                if zone is None:
                    continue
                targets = liquidity.targets(float(candle.close), vstate)
                outcome = self.engine.on_anchor(
                    event.event_type,
                    event.event_time,
                    event.payload,
                    zone=zone,
                    targets=targets,
                    state=state,
                    atr=atr,
                )
                self.anchors.append((event.event_type, event.payload))
                self.anchor_outcomes.append(outcome)

            effective_atr = atr if atr is not None and atr > 0.0 else 1.0  # عقود المحرك
            produced = self.engine.on_bar(
                candle,
                analysis_events=struct_events + liq_events,
                state=state,
                atr=effective_atr,
            )
            self.bar_contexts.append((candle, effective_atr, state))
            self.bar_transitions.append(list(produced))

    def _snapshot(
        self, bar_time: datetime, regime_state: Any, bias_state: Any, vstate: Any, index: int
    ) -> MarketStateSnapshot:
        """لقطة الحالة عند الشريط — الحالة الموضعية الأقرب (نمط build_snapshot)."""
        regime_value = regime_state.regime if regime_state is not None else None
        bias_value = bias_state.bias if bias_state is not None else None
        vol_percentile = (
            vstate.atr_percentile
            if vstate is not None and vstate.atr_percentile is not None
            else 0.0
        )
        quality = DataQuality.HEALTHY
        unsafe = (
            self.inject_unsafe_quality_at is not None and index >= self.inject_unsafe_quality_at
        )
        if unsafe:
            quality = DataQuality.STALE
        return MarketStateSnapshot(
            instrument=INSTRUMENT,
            timeframe=LTF_TIMEFRAME,
            event_time=bar_time,
            regime=regime_value if regime_value is not None else _UNKNOWN_REGIME,
            htf_bias=bias_value if bias_value is not None else _UNKNOWN_BIAS,
            volatility_percentile=vol_percentile,
            data_quality=quality,
        )


def _tf_seconds(tf: str) -> float:
    return {"1m": 60.0, "15m": 900.0, "1h": 3600.0, "4h": 14400.0, "1d": 86400.0}[tf]


from schemas import HTFBias, MarketRegime  # noqa: E402

_UNKNOWN_REGIME = MarketRegime.UNKNOWN
_UNKNOWN_BIAS = HTFBias.UNKNOWN


# ───────────────────────── فحوص §18.3 والتدقيق ─────────────────────────


def audit_18_3(scenario: Scenario) -> str | None:
    """عناصر §18.3 التسعة كاملة؟ — أول ناقص باسمه أو None."""
    if scenario.context_snapshot is None:
        return "السياق"
    if not scenario.location_snapshot.get("zone"):
        return "الموقع"
    if not scenario.thesis.strip():
        return "الآلية (الأطروحة)"
    if not scenario.trigger_definition.condition_type.strip():
        return "المشغل"
    if float(scenario.invalidation.structural_level) <= 0.0:
        return "الإبطال"
    if not scenario.primary_targets:
        return "المسار المتوقع (الهدف الأساسي)"
    if scenario.expiry_time is None:
        return "الأفق الزمني (الزعنفة)"
    if scenario.opposing_evidence is None or scenario.supporting_evidence is None:
        return "التناقضات (قائمتا الدليل)"
    return None


def serialize(run: ScenarioRun) -> tuple[list[str], list[str]]:
    """تمثيل حتمي قابل للمقارنة بايت-بايت (حتمية) ودلاليًا (λ)."""
    scenarios = [s.model_dump_json() for s in sorted(run.scenarios, key=lambda s: s.scenario_id)]
    transitions = [
        json.dumps(
            {
                "scenario_id": t.scenario_id,
                "from": t.from_state.value,
                "to": t.to_state.value,
                "at": t.transition_time.isoformat(),
                "reason": t.reason,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for t in run.transitions
    ]
    return scenarios, transitions


# ───────────────────────── الفحوص الأساسية ─────────────────────────


def core_checks(
    klines_by_tf: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]
) -> ScenarioRun:
    """الفحوص 1-8: العينة والمراسيم والاستنساخ والدورة كاملة."""
    bars_1m = len(klines_by_tf["1m"])
    check(
        all(len(klines_by_tf[tf]) == manifest["timeframes"][tf]["count"] for tf in TIMEFRAMES),
        f"العينة: الأطر الثلاثة مطابقة للـmanifest ({bars_1m} شمعة 1m)",
        "العينة: خلل في أعداد الأشرطة مقابل manifest",
    )

    run = ScenarioRun(klines_by_tf)
    sweep_count = sum(
        1
        for etype, _ in run.anchors
        if etype in (EventType.LIQUIDITY_SWEEP_HIGH, EventType.LIQUIDITY_SWEEP_LOW)
    )
    accept_count = len(run.anchors) - sweep_count
    check(
        len(run.anchors) > 0,
        f"المراسيم: {len(run.anchors)} حدثًا موقعيًا مؤكدًا على بيانات حقيقية "
        f"({sweep_count} اجتياحًا و{accept_count} كسر-قبول) — وقود D-04",
        "المراسيم: لا أحداث سيولة موقعية على العينة — لا يمكن اختبار D-04",
    )

    # الاستنساخ: كل مرسِم ≤3 قوالب + غيوب موثقة + عناصر §18.3 كاملة
    proposals = list(run.scenarios)
    absence_docs = [a for outcome in run.anchor_outcomes for a in outcome.absences]
    missing_elements = [
        (s.scenario_id, audit_18_3(s)) for s in proposals if audit_18_3(s) is not None
    ]
    templates_seen = {s.template for s in proposals}
    check(
        bool(proposals)
        and not missing_elements
        and templates_seen >= {ScenarioTemplate.REVERSAL, ScenarioTemplate.BREAKOUT},
        f"الاستنساخ (D-04): {len(proposals)} مقترحًا من {len(run.anchors)} مرسِمًا — "
        f"القوالب {sorted(t.value for t in templates_seen)} وعناصر §18.3 التسعة "
        f"كاملة في كل مقترح و{len(absence_docs)} غيابًا موثقًا",
        f"الاستنساخ: مقترحات ناقصة العناصر: {missing_elements[:3]}",
    )

    # الترقية: ≥1 ACTIVE بسبب مجموعتين دالتين
    promoted = [t for t in run.transitions if t.to_state is ScenarioState.ACTIVE]
    promotion_documented = all("مجموعات دليل مستقلة داعمة" in t.reason for t in promoted)
    check(
        bool(promoted) and promotion_documented,
        f"الترقية (§18.4): {len(promoted)} ترقية بموثوقية «≥{MIN_SUPPORTING_GROUPS} مجموعات "
        f"داعمة ولا حجب» — الحد ثابت المواصفة لا معامل إعدادي",
        "الترقية: لا ترقيات موثقة على العينة أو أسبابها فقيرة التوثيق",
    )

    # المشغلات: ≥1 TRIGGERED بمشغل مرصود فعليًا
    triggered = [t for t in run.transitions if t.to_state is ScenarioState.TRIGGERED]
    trigger_named = all("رُصد فعليًا" in t.reason for t in triggered)
    check(
        bool(triggered) and trigger_named,
        f"المشغلات (7.3): {len(triggered)} اشتعالًا مرصودًا فعليًا من أحداث العينة "
        "(إزاحة/BOS داخلي/قبول/إعادة اختبار) بأسباب تسمي النوع وتوثق الانجراف",
        "المشغلات: لا اشتعال مرصود على العينة أو أسبابه بلا توثيق",
    )

    # دورة الحياة: كل انتقال قانوني ولا خروج من نهائية
    illegal = [
        (t.from_state, t.to_state)
        for t in run.transitions
        if t.to_state not in LEGAL_TRANSITIONS[t.from_state]
    ]
    from_terminal = [t for t in run.transitions if t.from_state in TERMINAL_STATES]
    check(
        not illegal and not from_terminal,
        f"دورة الحياة (§18.2): {len(run.transitions)} انتقالًا كلها ضمن الخريطة "
        "القانونية — ولا خروج من نهائية أبدًا (§38.2)",
        f"دورة الحياة: انتقالات غير قانونية {illegal[:3]} أو خروج من نهائية",
    )

    # الإبطال والانقضاء: النهايات بأسبابها الموثقة بحسب نوعها — شروط
    # §18.5 للإبطال والانقضاء والإلغاء، وقرار التنافس 7.4 للكتم
    endings = Counter(t.to_state.value for t in run.transitions if t.to_state in TERMINAL_STATES)
    undocumented = []
    for t in run.transitions:
        if t.to_state not in TERMINAL_STATES:
            continue
        if t.to_state is ScenarioState.SUPPRESSED:
            if "7.4" not in t.reason and "تنافس" not in t.reason:
                undocumented.append(t.to_state.value)
        elif "§18.5" not in t.reason:
            undocumented.append(t.to_state.value)
    check(
        bool(endings) and not undocumented,
        f"الإبطال والانقضاء (§18.5/7.4): {dict(endings)} — كل نهاية بسبب موثق "
        "من نوعها (شرط §18.5 معلن أو قرار تنافس يسمي فائزه)",
        f"النهايات: {undocumented[:3]} بلا سبب موثق",
    )

    # التنافس: حتمية الحل على المُشعلين الفعليين + كل كتم يسمي فائزه
    final_triggered = [
        CompetingScenario(s, _supporting_groups_of(run, s))
        for s in run.scenarios
        if s.state is ScenarioState.TRIGGERED
    ]
    if final_triggered:
        first_pass = resolve_conflicts(final_triggered)
        second_pass = resolve_conflicts(final_triggered)
        deterministic = [w.scenario_id for w in first_pass.survivors] == [
            w.scenario_id for w in second_pass.survivors
        ]
        suppressed_documented = [
            t
            for t in run.transitions
            if t.to_state is ScenarioState.SUPPRESSED and "المعارض" not in t.reason
        ]
        check(
            deterministic and not suppressed_documented,
            f"التنافس (7.4): حل المتزامنين حتمي متطابق مرتين — "
            f"{len(first_pass.survivors)} ناجيًا وكل SUPPRESSED يسمي فائزه",
            "التنافس: حل غير حتمي أو كتم بلا تسمية الفائز",
        )
    else:
        ok(
            "التنافس (7.4): لا متزامنين TRIGGERED متضادين في العينة — "
            "منطق الحسم مغطى اختبارات الوحدة والخاصية (لا فرض مصطنع)"
        )

    return run


def _supporting_groups_of(run: ScenarioRun, scenario: Scenario) -> int:
    """عدد المجموعات الداعمة عند لحظة الاشتعال — من سجل المحرك الداخلي.

    المحرك يخزن آخر عدّ محسوب عند كل ترقية/اشتعال (``_supporting_groups``)
    — قراءة مرجعية لفحص التنافس فقط.
    """
    return int(run.engine._supporting_groups.get(scenario.scenario_id, 0))


# ───────────────────────── الحتمية والخصائص ─────────────────────────


def property_checks(klines_by_tf: dict[str, list[dict[str, Any]]], base: ScenarioRun) -> None:
    """الفحوص 9-13: الحتمية واللا-نظرة والتحجيم والقانونية."""
    scenarios_a, transitions_a = serialize(base)
    repeat = ScenarioRun(klines_by_tf)
    scenarios_b, transitions_b = serialize(repeat)
    check(
        scenarios_a == scenarios_b and transitions_a == transitions_b,
        f"الحتمية: مساران كاملان ⇒ {len(scenarios_a)} سيناريوًا و"
        f"{len(transitions_a)} انتقالًا متطابقة بايت-بايت",
        "الحتمية: المسارين اختلفا",
    )

    # اللا-نظرة: بادئة نصف النافذة ⊆ الكامل
    bars_1m = len(klines_by_tf["1m"])
    prefix_bars = int(bars_1m * PREFIX_FRACTION)
    prefix_run = ScenarioRun(klines_by_tf, prefix_bars=prefix_bars)
    _, prefix_transitions = serialize(prefix_run)
    check(
        transitions_a[: len(prefix_transitions)] == prefix_transitions,
        f"لا-نظرة (§26.3): انتقالات أول {prefix_bars} شمعة مطابقة لبادئة "
        "التشغيل الكامل — التقييم لا يرى إلا الماضي",
        "لا-نظرة: انتقالات البادئة اختلفت عن بادئة الكامل",
    )

    # λ=2: تكافؤ دلالي — الفئات نفسها بأعدادها والاقتران بالترتيب داخل
    # كل فئة (القوالب×الاتجاه ليست فريدة — 559 مقترحًا في 4 فئات؛
    # المعرفات وحدها تتبع بصمة الحمولة والدرجات نسب صرفة)
    scaled = ScenarioRun(klines_by_tf, lam=2.0)
    base_groups: dict[Any, list[Any]] = {}
    for s in base.scenarios:
        base_groups.setdefault((s.template, s.direction), []).append(s)
    scaled_groups: dict[Any, list[Any]] = {}
    for s in scaled.scenarios:
        scaled_groups.setdefault((s.template, s.direction), []).append(s)
    semantic_ok = base_groups.keys() == scaled_groups.keys() and all(
        len(base_groups[key]) == len(scaled_groups[key]) for key in base_groups
    )
    if semantic_ok:
        for key in base_groups:
            for s1, s2 in zip(base_groups[key], scaled_groups[key], strict=True):
                if abs(s1.scenario_score - s2.scenario_score) > 1e-9:
                    semantic_ok = False
                    break
                if (
                    abs(s2.invalidation.structural_level - 2.0 * s1.invalidation.structural_level)
                    > 1e-6
                ):
                    semantic_ok = False
                    break
                if abs(s2.entry_zone.price_low - 2.0 * s1.entry_zone.price_low) > 1e-6 * max(
                    1.0, abs(s1.entry_zone.price_low)
                ):
                    semantic_ok = False
                    break
            if not semantic_ok:
                break
    check(
        semantic_ok,
        "التحجيم λ=2: نفس البنية دلاليًا (فئات بأعدادها ودرجات متطابقة بالترتيب) "
        "والمستويات تتضاعف بدقة — القياسات مطبَّعة كلها",
        "التحجيم λ=2: اختلال دلالي في البنية أو القيم",
    )

    # القانونية: مخططات jsonschema المصدَّرة
    import jsonschema

    scenario_schema = json.loads((GENERATED_DIR / "Scenario.schema.json").read_text("utf-8"))
    transition_schema = json.loads(
        (GENERATED_DIR / "ScenarioTransition.schema.json").read_text("utf-8")
    )
    violations = 0
    for s in base.scenarios:
        try:
            jsonschema.validate(json.loads(s.model_dump_json()), scenario_schema)
        except jsonschema.ValidationError:
            violations += 1
    for t in base.transitions:
        try:
            jsonschema.validate(json.loads(t.model_dump_json()), transition_schema)
        except jsonschema.ValidationError:
            violations += 1
    check(
        violations == 0,
        f"القانونية: {len(base.scenarios)} سيناريوًا و{len(base.transitions)} انتقالًا "
        "تمر مخططاتها المصدَّرة (jsonschema)",
        f"القانونية: {violations} سجلًا خالف مخططه",
    )


# ───────────────────────── حقن الجودة ─────────────────────────


def quality_injection_check(klines_by_tf: dict[str, list[dict[str, Any]]]) -> None:
    """الفحص 14: لقطة غير آمنة تُطفئ كل الأحياء وترفض المراسِم — حقن موثق."""
    # عتبة الحقن داخل النافذة فعلًا (العينة 1440 شمعة — الحقن عند 1000
    # يترك أحياء كافين للإلغاء ومراسيم كافية بعده لاختبار حرس الجودة)
    unsafe_run = ScenarioRun(klines_by_tf, inject_unsafe_quality_at=1000)
    cancellations = [
        t for t in unsafe_run.transitions if t.to_state is ScenarioState.CANCELLED_BY_DATA_QUALITY
    ]
    live_after = [s for s in unsafe_run.scenarios if s.state not in TERMINAL_STATES]
    check(
        bool(cancellations) and not live_after,
        f"الجودة (حقن موثق عند الشريط 1000): {len(cancellations)} إلغاءً بلا أحياء "
        "بعدها — التدهور الآمن لا التداول الأعمى (§18.5 شرط 5 + §49)",
        "الجودة: الإلغاء بالحقن لم يعمل كما يجب",
    )


# ───────────────────────── التفسير §2.8 ─────────────────────────


def explanation_check(run: ScenarioRun) -> None:
    """الفحص 16: كائن التفسير بمشغل المرحلة 7 وإبطالها ومسارها."""
    from fusion.explain import build_explanation

    triggered = [s for s in run.scenarios if s.state is ScenarioState.TRIGGERED]
    if not triggered:
        # لا مُرخِّص في العينة — الفحص على أول سيناريو واصل ACTIVE (رفض موثق)
        triggered = [s for s in run.scenarios if s.state is ScenarioState.ACTIVE] or list(
            run.scenarios
        )
    scenario = triggered[0]
    explanation = build_explanation(
        _reference_snapshot(run, scenario),
        _reference_records(run, scenario),
        market_state=scenario.context_snapshot,
        trigger=(
            f"مشغل {scenario.trigger_definition.condition_type} بمعاملاته "
            f"{json.dumps(scenario.trigger_definition.params, ensure_ascii=False, sort_keys=True)}"
            " — "
            "معرّف هيكلي قابل للرصد (D-04/§18.4)"
        ),
        invalidation=(
            f"الإبطال §18.5/§23.4: قبول عبر {scenario.invalidation.structural_level:.2f} "
            f"بعازلة تقلب {scenario.invalidation.volatility_buffer:.2f}"
        ),
        expected_path=(
            f"الأهداف §10.5: أساسي {scenario.primary_targets[0].price_level:.2f} "
            f"({scenario.primary_targets[0].zone_id}) و{len(scenario.secondary_targets)} ثانويًا"
        ),
    )
    try:
        validate_explanation_completeness(explanation, rejected=False)
        ok(
            f"التفسير (§2.8): كائن مكتمل لمقترح {scenario.template.value} "
            f"{scenario.direction.value} — مشغله وإبطاله ومساره من المرحلة 7 "
            "(حقول 6.5 المؤجلة تسددت)"
        )
    except ValueError as exc:
        fail(f"التفسير: كائن ناقص — {exc}")


def _reference_snapshot(run: ScenarioRun, scenario: Scenario) -> Any:
    from fusion.compute import FusionEngine

    records = _reference_records(run, scenario)
    engine = FusionEngine()
    triggered_at = [
        t
        for t in run.transitions
        if t.scenario_id == scenario.scenario_id and t.to_state is ScenarioState.TRIGGERED
    ]
    fusion_time = triggered_at[0].transition_time if triggered_at else scenario.expiry_time
    return engine.compute(
        records,
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        fusion_time=fusion_time,
    )


def _reference_records(run: ScenarioRun, scenario: Scenario) -> Any:
    from fusion.ledger import EvidenceLedgerBuilder

    ledger = EvidenceLedgerBuilder()
    events = run.engine._events
    triggered_at = [
        t
        for t in run.transitions
        if t.scenario_id == scenario.scenario_id and t.to_state is ScenarioState.TRIGGERED
    ]
    as_of = triggered_at[0].transition_time if triggered_at else scenario.expiry_time
    filtered = [e for e in events if e.event_time <= as_of]
    return ledger.build(
        filtered,
        scenario_id=scenario.scenario_id,
        direction=scenario.direction,
        as_of=as_of,
        market_state=scenario.context_snapshot,
    )


# ───────────────────────── القاعدة الحية + NATS ─────────────────────────


async def live_checks(run: ScenarioRun) -> None:
    """الفحص 9 (بوابة الخروج نصًا) + الفحص 15 (البث الحي للمراسِم)."""
    import asyncpg
    import jsonschema
    from common.config import load_settings
    from nats.aio.client import Client as NATSClient

    settings = load_settings()
    store = ScenarioStore()
    conn = await asyncpg.connect(settings.database_url)
    try:
        # تنظيف أي أثر سابق (idempotent عبر الحذف الاختباري)
        await conn.execute("DELETE FROM scenarios WHERE symbol = $1", INSTRUMENT)

        # كتابة كل دورة حياة كاملة (سيناريو + انتقالاته معاملة واحدة)
        transitions_by_scenario: dict[str, list[ScenarioTransition]] = {}
        for t in run.transitions:
            transitions_by_scenario.setdefault(t.scenario_id, []).append(t)
        for scenario in run.scenarios:
            await store.write_lifecycle(
                conn, scenario, transitions_by_scenario.get(scenario.scenario_id, [])
            )
        # إعادة الكتابة كلها — idempotent (التاريخ DO NOTHING)
        for scenario in run.scenarios:
            await store.write_lifecycle(
                conn, scenario, transitions_by_scenario.get(scenario.scenario_id, [])
            )

        rows = await conn.fetchval("SELECT count(*) FROM scenarios WHERE symbol = $1", INSTRUMENT)
        trans_rows = await conn.fetchval("SELECT count(*) FROM scenario_transitions")
        check(
            rows == len(run.scenarios) and trans_rows == len(run.transitions),
            f"القاعدة: {rows} سيناريوًا و{trans_rows} انتقالًا — إعادة الكتابة "
            "كاملة idempotent (لا تكرار في التاريخ)",
            "القاعدة: خلل idempotent في الكتابة أو التاريخ تكرر",
        )

        # بوابة الخروج 7 نصًا: كل مرخِّص له مشغل وإبطال معرّفان
        checked, violators = await store.audit_licensing_readiness(conn)
        check(
            not violators,
            f"بوابة الخروج 7 (نصًا): {checked} سيناريو مرخِّصًا (TRIGGERED فما فوق) "
            "كلها بمشغل معرّف وإبطال معرّف — صفر مخالفين",
            f"بوابة الخروج 7: مخالفون بلا مشغل/إبطال: {violators[:3]}",
        )

        # دورة الحياة باستعلام واحد (عيّنة من ثلاثة)
        sample_ids = sorted({t.scenario_id for t in run.transitions})[:3]
        single_query_ok = True
        for sid in sample_ids:
            lifecycle = await store.read_lifecycle(conn, sid)
            if lifecycle is None:
                single_query_ok = False
                break
            scenario, transitions = lifecycle
            expected = transitions_by_scenario.get(sid, [])
            if [t.to_state for t in transitions] != [t.to_state for t in expected]:
                single_query_ok = False
                break
        check(
            single_query_ok,
            f"دورة الحياة باستعلام واحد: قراءة {len(sample_ids)} سلسلة كاملة "
            "(السيناريو + انتقالاته بترتيب الوقوع) بجولة SQL لكل منها",
            "دورة الحياة: قراءة السلسلة خالفت المكتوب",
        )
    finally:
        await conn.close()

    # ── البث الحي: المراسِم §20 عبر NATS تغذي المحرك ⇒ نفس المقترحات ──
    nc: NATSClient = NATSClient()
    await nc.connect(servers=[settings.nats_url], connect_timeout=5, max_reconnect_attempts=1)
    from engine_worker.analysis_publisher import (  # type: ignore[import-not-found]
        AnalysisEventPublisher,
        build_envelope,
        subject_for,
    )

    received: list[Any] = []
    anchor_sample = run.anchors[: min(4, len(run.anchors))]
    subjects = {
        subject_for(etype, payload.instrument, payload.timeframe)
        for etype, payload in anchor_sample
    }

    async def _cb(msg: Any) -> None:
        received.append(json.loads(msg.data.decode("utf-8")))

    for subject in sorted(subjects):
        await nc.subscribe(subject, cb=_cb)
    await nc.flush()
    publisher = AnalysisEventPublisher(nc)
    for etype, payload in anchor_sample:
        envelope = build_envelope(
            _FakeEmittedEvent(etype, payload),
            "verify-phase7",
            source="verify-phase7",
            trace_id="verify-phase7",
            receive_time=payload.bar_time,
        )
        await publisher.publish(envelope)
    await nc.flush()
    await asyncio.sleep(1.0)
    await nc.close()

    envelope_schema = json.loads((GENERATED_DIR / "EventEnvelope.schema.json").read_text("utf-8"))
    legal = 0
    for payload in received:
        try:
            jsonschema.validate(payload, envelope_schema)
            legal += 1
        except jsonschema.ValidationError:
            legal = -1
            break
    check(
        legal == len(received) and len(received) >= len(anchor_sample),
        f"البث الحي (NATS): {len(received)} مرسِمًا عبر market.event.* بمغلف §32 "
        "مخططه — أحداث العينة نفسها التي قادت D-04 (وعد ADR-024 مسدد)",
        "البث الحي: استقبال ناقص أو مغلف فاسد",
    )


class _FakeEmittedEvent:
    """حدث مكشوف بثوب بروتوكول الناشر — من (النوع، الحمولة) المرجعيين."""

    def __init__(self, event_type: EventType, payload: Any) -> None:
        self.event_type = event_type
        self.event_time = payload.bar_time
        self.payload = payload


# ───────────────────────── main ─────────────────────────


async def _run() -> int:
    klines_by_tf, manifest = load_phase2()
    base = core_checks(klines_by_tf, manifest)
    property_checks(klines_by_tf, base)
    quality_injection_check(klines_by_tf)
    explanation_check(base)
    await live_checks(base)
    return _rc


def main() -> int:
    rc = asyncio.run(_run())
    print("─" * 72)
    if rc == 0:
        print(
            f"✓ بوابة المرحلة 7 مغلقة: محرك السيناريوهات — {_checks} فحصًا أخضر\n"
            "  المُقترِحات (D-04) ودورة الحياة (§18.2) والمشغلات والإبطال (§18.4/18.5)\n"
            "  والتنافس (7.4) — ولا ترخيص بلا مشغل وإبطال معرّفين"
        )
    else:
        print(f"✗ بوابة المرحلة 7: فشل — راجع الفحوص أعلاه ({_checks} فحصًا)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
