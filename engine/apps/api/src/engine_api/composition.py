"""تركيب اللوحة — الحالة القانونية الحتمية التي تعرضها واجهة §35.

القرار المعماري (ADR-028): اللوحة تعرض **كائنات البوابات نفسها** لا
نسخة ثانية — ``ScenarioRun`` و``RiskPipeline`` يُستوردان حرفيًا من
سلسلة سكربتات البوابات (verify_phase7/8) فوق العينة المرجعية الثلاثية
الأطر نفسها، فيحمل أي رقم في اللوحة نفس قيمة البوابة الموثقة
(103 قرارات/58 ترخيصًا/45 رفضًا) — والفحص الآلي في بوابة 10 يثبت
المطابقة بندًا بندًا.

المصادر:
- السلسلة الحية: ScenarioRun (المرحلة 7) + RiskPipeline (المرحلة 8).
- الحصيلة الموثقة: تقرير الإعادة (المرحلة 9، §26.2) — مقاييس التنفيذ.
- لوحة §35.2 الثلاثة عشر حقلاً من آخر لقطة سياق + الخريطة الحية.
- أثر الاستدلال §35.3 من أطروحة كل سيناريو وأدلته المؤيدة والمعارضة.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from schemas import (
    DashboardCounts,
    DashboardOverview,
    ExecutionView,
    PanelField,
    ReasoningTraceView,
    RejectionView,
    ScenarioView,
    WebhookEventView,
)

_ENGINE_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _ENGINE_ROOT / "scripts"

#: حقن مسار سكربتات البوابات — نفس نمط استيراد verify_phase8/9 حرفيًا
#: (الوثيقة في ADR-028: كائن واحد لا نسختان).
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

#: تقرير الإعادة الموثق (بوابة 9) — مصدر مقاييس التنفيذ حصرًا.
_BACKTEST_REPORT = _ENGINE_ROOT / "docs" / "backtest" / "phase9" / "backtest_report.json"

_CACHE: dict[str, Any] = {}


def _ensure_built() -> dict[str, Any]:
    """بناء السلسلة مرة واحدة لكل عملية — حتمية كاملة (لا ساعة جدرية)."""
    cached: dict[str, Any] | None = _CACHE.get("chain")
    if cached is not None:
        return cached

    # الاستيراد بعد حقن المسار (نمط verify_phase9 الحرفي) — سكربتات
    # البوابات ليست حزمًا مثبتة (مستوردة بمسار مطلق موثق في ADR-028).
    from verify_phase7 import (  # type: ignore[import-not-found]
        LTF_TIMEFRAME,
        ScenarioRun,
        load_phase2,
    )
    from verify_phase8 import RiskPipeline  # type: ignore[import-not-found]

    klines_by_tf, manifest = load_phase2()
    run = ScenarioRun(klines_by_tf)
    risk = RiskPipeline(run)

    # خريطة السيولة الحية لحظة آخر شريط (للوحة §35.2) — إعادة تشغيل
    # الواجهة نفسها فوق العينة (ترتيب §10.4 الموثق: كشف ثم تحديث).
    from liquidity import LiquidityEngine
    from market_state.volatility import VolatilityEngine
    from structure import StructureEngine

    vol = VolatilityEngine()
    structure = StructureEngine()
    liquidity = LiquidityEngine()
    known_swings: set[str] = set()
    candles = [ctx[0] for ctx in run.bar_contexts]
    for candle in candles:
        vstate = vol.update(candle)
        structure.update(candle, vstate)
        fresh = [
            s
            for s in structure.swings
            if s.swing_id not in known_swings and s.confirmation_time <= candle.bar_time
        ]
        known_swings.update(s.swing_id for s in fresh)
        liquidity.update(candle, vstate, fresh)
    zones = [
        {"price_low": float(z.price_low), "price_high": float(z.price_high)}
        for z in liquidity.zones()
        if z.state.value == "ACTIVE"
    ]

    chain: dict[str, Any] = {
        "run": run,
        "risk": risk,
        "manifest": manifest,
        "timeframe": LTF_TIMEFRAME,
        "liquidity_zones": zones,
    }
    # فهرس بالسيناريو — القرارات تُخزن بمعرف القرار في البوابة (ADR-026).
    chain["decisions_by_scenario"] = {d.scenario_id: d for d in risk.decisions.values()}
    _CACHE["chain"] = chain
    return chain


def _panel_fields(chain: dict[str, Any]) -> tuple[PanelField, ...]:
    """لوحة المعلومات الدنيا — §35.2 حرفيًا (ثلاثة عشر حقلاً بترتيب النص)."""
    run: Any = chain["run"]
    risk: Any = chain["risk"]
    last_candle, last_atr, last_state = run.bar_contexts[-1]

    # الخريطة الحية: إعادة تشغيل السيولة فوق العينة نفسها (خريطة لحظة
    # آخر شريط) — مصدر «السيولة فوق/تحت» لقطة اللوحة.
    zones = chain["liquidity_zones"]
    price = float(last_candle.close)
    above = [z for z in zones if z["price_low"] > price]
    below = [z for z in zones if z["price_high"] < price]
    nearest_above = min(above, key=lambda z: z["price_low"]) if above else None
    nearest_below = max(below, key=lambda z: z["price_high"]) if below else None

    # آخر قرار مخاطرة وحالة السيناريوهات النشطة
    decisions = list(risk.decisions.values())
    last_decision = max(decisions, key=lambda d: d.decided_at) if decisions else None
    active = [
        s for s in run.scenarios if s.state.value not in ("EXPIRED", "INVALIDATED", "COMPLETED")
    ]

    fields = [
        PanelField(key="market_regime", value=str(last_state.regime.value)),
        PanelField(key="htf_bias", value=str(last_state.htf_bias.value)),
        PanelField(
            key="mtf_setup_state",
            value=f"{len(active)} نشط" if active else "لا مقترحات قائمة",
            detail="محرك السيناريوهات §18 — لا مقترح بلا مشغل مؤكد (بوابة 7)",
        ),
        PanelField(
            key="liquidity_above_below",
            value=(
                f"{nearest_above['price_low']:.1f} / {nearest_below['price_high']:.1f}"
                if nearest_above and nearest_below
                else "—"
            ),
            detail="أقرب سيولة فوق/تحت السعر (خريطة §10.1 عند آخر شريط)",
        ),
        PanelField(
            key="flow_state",
            value="عينة البنية (§12 خارج عينة اللوحة)",
            detail="التدفق يُستكمل مع الابتلاع الحي — الفرق الموثق لا يخفى",
        ),
        PanelField(
            key="delta",
            value="غير متاح على هذه العينة",
            detail="دلتا الفوتبرنت (§8.2) خارج العينة المرجعية الثلاثية",
        ),
        PanelField(
            key="volatility_state",
            value=f"مئين {last_state.volatility_percentile:.0f}",
            detail=f"ATR لحظة آخر شريط ≈ {last_atr:.2f} (§16)",
        ),
        PanelField(
            key="session",
            value=last_candle.session_id,
            detail="معرف الجلسة (يوم UTC — §9)",
        ),
        PanelField(
            key="macro_risk",
            value="لا نوافذ كلية قادمة",
            detail="عينة اللوحة بلا أحداث كلية (§17.3) — الحجب الكلي معطل لغيابها",
        ),
        PanelField(
            key="active_scenario",
            value=active[0].scenario_id[:13] + "…" if active else "—",
            detail=f"{len(active)} سيناريو غير منتهٍ من {len(run.scenarios)} إجمالًا",
        ),
        PanelField(
            key="trigger_status",
            value=("مشتعل — قُيّم بالمخاطرة" if last_decision is not None else "لا اشتعال بعد"),
            detail=(
                f"آخر قرار: {'ترخيص' if last_decision.approved else 'رفض'}"
                if last_decision is not None
                else "محرك §18.4"
            ),
        ),
        PanelField(
            key="risk_status",
            value=(
                (
                    "مرخّص"
                    if last_decision.approved
                    else f"مرفوض: {last_decision.rejection_basis.value}"
                )
                if last_decision is not None
                else "—"
            ),
            detail="بوابة لا-تداول §22 + وحدة R §23",
        ),
        PanelField(
            key="execution_status",
            value="SIMULATION_ONLY",
            detail="القبول القانوني في محرك الإعادة §28 — التنفيذ الحي مؤجل للمرحلة 11",
        ),
    ]
    return tuple(fields)


def _scenario_views(chain: dict[str, Any], limit: int = 25) -> tuple[ScenarioView, ...]:
    """عرض السيناريوهات الأحدث أولاً (الطبقتان 4-5 من §35.1)."""
    run: Any = chain["run"]
    out: list[ScenarioView] = []
    for scenario in sorted(
        run.scenarios, key=lambda s: s.context_snapshot.event_time, reverse=True
    )[:limit]:
        entry = scenario.entry_zone
        target = scenario.primary_targets[0] if scenario.primary_targets else None
        invalidation = scenario.invalidation
        out.append(
            ScenarioView(
                scenario_id=scenario.scenario_id,
                template=str(scenario.template.value),
                direction=str(scenario.direction.value),
                state=str(scenario.state.value),
                created_time=scenario.context_snapshot.event_time,
                trigger_status=str(scenario.state.value),
                entry_price_low=float(entry.price_low),
                entry_price_high=float(entry.price_high),
                stop=float(invalidation.structural_level),
                target_price=float(target.price_level) if target else 0.0,
                evidence_count=len(scenario.supporting_evidence),
                score=float(scenario.scenario_score),
            )
        )
    return tuple(out)


def _trace_views(chain: dict[str, Any], limit: int = 12) -> tuple[ReasoningTraceView, ...]:
    """أثر الاستدلال القابل للطي (§35.3) — أثمن من ملصق نسبة شرائية.

    الأولوية للسيناريوهات ذات القرار: تفسير §2.8 المرافق (نص إنساني
    كامل: السياق والسيولة والبنية والأدلة) هو مصدر «لماذا نشط؟» و«ماذا
    ضده؟» — لا معرفات أحداث خام.
    """
    run: Any = chain["run"]
    decisions_by_scenario: dict[str, Any] = chain["decisions_by_scenario"]
    ordered = sorted(run.scenarios, key=lambda s: s.context_snapshot.event_time, reverse=True)
    with_decision = [s for s in ordered if s.scenario_id in decisions_by_scenario]
    rest = [s for s in ordered if s.scenario_id not in decisions_by_scenario]
    out: list[ReasoningTraceView] = []
    for scenario in (with_decision + rest)[:limit]:
        decision = decisions_by_scenario.get(scenario.scenario_id)
        why_wait: list[str] = []
        if decision is None:
            why_wait.append("المشغل (§18.4) لم يشتعل بعد — لا قرار مخاطرة بلا اشتعال")
        elif not decision.approved:
            why_wait.append(f"مرفوض بالمخاطرة: {decision.rejection_basis.value}")
        else:
            why_wait.append("مرخّص — نُفذ في العالم المحاكى (بوابة 9)")
        if decision is not None:
            explanation = decision.explanation
            why_active = [
                explanation.liquidity_map,
                explanation.structural_state,
                *explanation.supporting_evidence[:3],
            ]
            what_against = list(explanation.opposing_evidence[:3])
            if explanation.rejection_reason:
                what_against.append(explanation.rejection_reason)
            why_active.append(explanation.market_context)
        else:
            why_active = [scenario.thesis]
            what_against = (
                [f"{len(scenario.opposing_evidence)} دليل معارض مرصود"]
                if scenario.opposing_evidence
                else ["لا أدلة معارضة مرصودة في اللقطة"]
            )
        out.append(
            ReasoningTraceView(
                scenario_id=scenario.scenario_id,
                template=str(scenario.template.value),
                direction=str(scenario.direction.value),
                why_active=tuple(why_active[:6]),
                what_against=tuple(what_against[:6]),
                why_wait=tuple(why_wait),
            )
        )
    return tuple(out)


def _rejection_views(chain: dict[str, Any], limit: int = 50) -> tuple[RejectionView, ...]:
    """سجل الرفض — لا-تداول §22 والكتم الموزون بأساس كل رفض."""
    risk: Any = chain["risk"]
    out: list[RejectionView] = []
    for decision in risk.decisions.values():
        if decision.approved:
            continue
        basis = decision.rejection_basis.value if decision.rejection_basis else "UNKNOWN"
        detail = (
            f"حاجب صلب: {decision.hard_blocks[0].no_trade_code.value}"
            if decision.hard_blocks
            else f"كتم موزون ({decision.soft_total:.2f})"
        )
        out.append(
            RejectionView(
                decision_id=decision.decision_id,
                scenario_id=decision.scenario_id,
                reason_code=str(basis),
                explanation=(f"{detail} — {decision.explanation.structural_state}"),
                as_of=decision.decided_at,
            )
        )
    out.sort(key=lambda r: r.as_of, reverse=True)
    return tuple(out[:limit])


def _execution_view() -> ExecutionView:
    """حالة التنفيذ من حصيلة بوابة 9 الموثقة (§26.2 — إعادة قابلة للاستنساخ)."""
    report = json.loads(_BACKTEST_REPORT.read_text(encoding="utf-8"))
    metrics = report["metrics"]
    identity = report["identity"]
    return ExecutionView(
        mode="SIMULATION_ONLY",
        trades_count=int(metrics.get("labeled_trades", 0)),
        net_expectancy_r=float(metrics.get("net_expectancy_r", 0.0)),
        profit_factor=metrics.get("profit_factor"),
        win_rate=float(metrics.get("win_rate", 0.0)),
        report_ref=(
            "docs/backtest/phase9/backtest_report.json — "
            f"backtest_id {str(identity.get('backtest_id', '?'))[:13]}…"
        ),
    )


def _alert_views(alerts: list[dict[str, Any]] | None = None) -> tuple[WebhookEventView, ...]:
    """تنبيهات الويبهوك الحديثة (سجل التسليم §31.6) — من قاعدة البيانات."""
    if not alerts:
        return ()
    out = [
        WebhookEventView(
            alert_key=str(a["idempotency_key"])[:16] + "…",
            instrument=str(a["instrument"]),
            event=str(a["event"]),
            status=str(a["status"]),
            received_at=a["received_at"],
        )
        for a in alerts
    ]
    return tuple(out)


def _counts(chain: dict[str, Any]) -> DashboardCounts:
    run: Any = chain["run"]
    risk: Any = chain["risk"]
    report = json.loads(_BACKTEST_REPORT.read_text(encoding="utf-8"))
    return DashboardCounts(
        risk_decisions=len(risk.decisions),
        authorized=len(risk.authorized),
        rejected=sum(1 for d in risk.decisions.values() if not d.approved),
        simulated_trades=int(report["metrics"].get("labeled_trades", 0)),
        active_scenarios=sum(
            1 for s in run.scenarios if s.state.value not in ("EXPIRED", "INVALIDATED", "COMPLETED")
        ),
    )


def build_overview(alerts: list[dict[str, Any]] | None = None) -> DashboardOverview:
    """اللقطة الكاملة — حتمية بايت-بايت عدا التنبيهات (سجل حي)."""
    chain = _ensure_built()
    return DashboardOverview(
        panel=_panel_fields(chain),
        traces=_trace_views(chain),
        scenarios=_scenario_views(chain),
        rejections=_rejection_views(chain),
        execution=_execution_view(),
        alerts=_alert_views(alerts),
        counts=_counts(chain),
        composition_ref=(
            f"ScenarioRun+RiskPipeline فوق عينة phase2 ({chain['manifest'].get('symbol', '?')} "
            f"1m/15m/1h) — كائنات بوابتي 7 و8 حرفيًا"
        ),
    )
