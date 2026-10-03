"""مُصدّر JSON Schema — واجهة CLI: ``python -m schemas.export write|check``.

حرس «لا رسالة بلا مخطط مُصدَّر» (build_plan §A.5 و§32): كل نموذج جذري
يُصدَّر حتميًا 100% إلى ``generated/``، وأي انحراف بايت-بايت بين النماذج
وما على القرص يُفشل البوابة (exit code 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from . import SCHEMA_VERSION
from .backtest import (
    BacktestIdentity,
    BacktestMetrics,
    BacktestReport,
    EntrySpec,
    RDistribution,
    RealizedCosts,
    RegimeMetrics,
    SimulatedFill,
    SimulatedTrade,
    WFOProtocolConfig,
    WFOReport,
    WFOSegment,
    WFOWindow,
)
from .dashboard import (
    DashboardCounts,
    DashboardOverview,
    ExecutionView,
    PanelField,
    ReasoningTraceView,
    RejectionView,
    ScenarioView,
    WebhookEventView,
)
from .envelope import EventEnvelope
from .evidence import (
    AvailabilitySignature,
    CalibrationReport,
    EvidenceRecord,
    ExplanationObject,
    FusionSnapshot,
    GroupScore,
)
from .execution import LatencyRecord, OrderIntent, SlippageRecord
from .learning import ExperienceRecord
from .liquidity import BreakAcceptEventPayload, LiquidityZone, SweepEventPayload
from .market import Candle, FootprintBar, MarketStateSnapshot, TradeEvent
from .orderflow import (
    AbsorptionConditions,
    AbsorptionEventPayload,
    ExhaustionEventPayload,
    FlowContinuationEventPayload,
    ImbalanceClusterEventPayload,
)
from .patterns import (
    AnchorPoint,
    CandlePatternEventPayload,
    ClassicalPatternEventPayload,
)
from .risk import (
    CostBreakdown,
    EvaluationContext,
    MacroEventWindow,
    NoTradeExplanation,
    RewardRiskEstimate,
    RiskDecision,
    SizingModifier,
    SizingResult,
    StructuralStop,
)
from .scenario import (
    InvalidationRule,
    PriceZone,
    Scenario,
    ScenarioTransition,
    TargetZone,
    TriggerDefinition,
)
from .structure import (
    DisplacementEventPayload,
    FvgEventPayload,
    OrderBlockEventPayload,
    PremiumDiscountEventPayload,
    StructureBreakPayload,
    Swing,
)
from .tv import (
    AlertRevalidation,
    TVAlertEnvelope,
    TVAlertPayload,
    WebhookAck,
)

# كل النماذج الجذرية — مرتبة بالطبقة (مغلف ← سوق ← سيولة ← بنية ← دليل ←
# سيناريو ← تنفيذ ← تعلم).
ALL_MODELS: dict[str, type[BaseModel]] = {
    # مغلف الرسائل (§32)
    "EventEnvelope": EventEnvelope,
    # كائنات السوق (§7.1/§8.1/§8.2/§32)
    "TradeEvent": TradeEvent,
    "Candle": Candle,
    "FootprintBar": FootprintBar,
    "MarketStateSnapshot": MarketStateSnapshot,
    # كائنات السيولة (§10) وحمولاتها (§20)
    "LiquidityZone": LiquidityZone,
    "SweepEventPayload": SweepEventPayload,
    "BreakAcceptEventPayload": BreakAcceptEventPayload,
    # كائنات البنية (§11) وحمولاتها (§20)
    "Swing": Swing,
    "StructureBreakPayload": StructureBreakPayload,
    "DisplacementEventPayload": DisplacementEventPayload,
    "FvgEventPayload": FvgEventPayload,
    "OrderBlockEventPayload": OrderBlockEventPayload,
    "PremiumDiscountEventPayload": PremiumDiscountEventPayload,
    # حمولات التدفق (§12 + §20)
    "AbsorptionConditions": AbsorptionConditions,
    "AbsorptionEventPayload": AbsorptionEventPayload,
    "FlowContinuationEventPayload": FlowContinuationEventPayload,
    "ExhaustionEventPayload": ExhaustionEventPayload,
    "ImbalanceClusterEventPayload": ImbalanceClusterEventPayload,
    # الأنماط: كائن الإرساء وحمولتا الأحداث (§13 + §20)
    "AnchorPoint": AnchorPoint,
    "CandlePatternEventPayload": CandlePatternEventPayload,
    "ClassicalPatternEventPayload": ClassicalPatternEventPayload,
    # الدليل (§19.1) ومخرجات دمجه (§19.2-6 + D-03) والتفسير (§2.8)
    "EvidenceRecord": EvidenceRecord,
    "AvailabilitySignature": AvailabilitySignature,
    "GroupScore": GroupScore,
    "CalibrationReport": CalibrationReport,
    "FusionSnapshot": FusionSnapshot,
    "ExplanationObject": ExplanationObject,
    # السيناريو ومكوناته (§18/§10.5)
    "PriceZone": PriceZone,
    "TriggerDefinition": TriggerDefinition,
    "InvalidationRule": InvalidationRule,
    "TargetZone": TargetZone,
    "Scenario": Scenario,
    "ScenarioTransition": ScenarioTransition,
    # التنفيذ (§24)
    "OrderIntent": OrderIntent,
    "SlippageRecord": SlippageRecord,
    "LatencyRecord": LatencyRecord,
    # الإعادة والتنفيذ المحاكى والوسم والمقاييس (§26 + §30 + §29.2 + §39.3)
    "SimulatedFill": SimulatedFill,
    "RealizedCosts": RealizedCosts,
    "SimulatedTrade": SimulatedTrade,
    "EntrySpec": EntrySpec,
    "RDistribution": RDistribution,
    "RegimeMetrics": RegimeMetrics,
    "BacktestMetrics": BacktestMetrics,
    "BacktestIdentity": BacktestIdentity,
    "WFOSegment": WFOSegment,
    "WFOWindow": WFOWindow,
    "WFOProtocolConfig": WFOProtocolConfig,
    "WFOReport": WFOReport,
    "BacktestReport": BacktestReport,
    # المخاطرة (§22/§23/§25.2 + §17.3 + §31.3)
    "MacroEventWindow": MacroEventWindow,
    "EvaluationContext": EvaluationContext,
    "NoTradeExplanation": NoTradeExplanation,
    "StructuralStop": StructuralStop,
    "SizingModifier": SizingModifier,
    "SizingResult": SizingResult,
    "CostBreakdown": CostBreakdown,
    "RewardRiskEstimate": RewardRiskEstimate,
    "RiskDecision": RiskDecision,
    # التعلم (§29.1)
    "ExperienceRecord": ExperienceRecord,
    # جسر TradingView (§36 + D-07 + §31.6)
    "TVAlertPayload": TVAlertPayload,
    "TVAlertEnvelope": TVAlertEnvelope,
    "AlertRevalidation": AlertRevalidation,
    "WebhookAck": WebhookAck,
    # اللوحة الدنيا (§35.2 + §35.3)
    "PanelField": PanelField,
    "ReasoningTraceView": ReasoningTraceView,
    "ScenarioView": ScenarioView,
    "RejectionView": RejectionView,
    "ExecutionView": ExecutionView,
    "WebhookEventView": WebhookEventView,
    "DashboardCounts": DashboardCounts,
    "DashboardOverview": DashboardOverview,
}

# مرجع فقرة الخطة لكل نموذج — يظهر في جدول التوثيق المولّد.
MODEL_PLAN_REFS: dict[str, str] = {
    "EventEnvelope": "§32",
    "TradeEvent": "§7.1",
    "Candle": "§8.1",
    "FootprintBar": "§8.2 + §12.7",
    "MarketStateSnapshot": "§32 (المثال)",
    "LiquidityZone": "§10.2",
    "SweepEventPayload": "§10.4 + §20",
    "BreakAcceptEventPayload": "§10.4 + §20",
    "Swing": "§11.1",
    "StructureBreakPayload": "§11.2-3 + §20",
    "DisplacementEventPayload": "§11.4 + §20",
    "FvgEventPayload": "§11.5 + §20",
    "OrderBlockEventPayload": "§11.6 + §20",
    "PremiumDiscountEventPayload": "§11.7 + §20",
    "AbsorptionConditions": "§12.3",
    "AbsorptionEventPayload": "§12.3 + §20",
    "FlowContinuationEventPayload": "§12.2 + §20",
    "ExhaustionEventPayload": "§12.4 + §20",
    "ImbalanceClusterEventPayload": "§12.6 + §20",
    "AnchorPoint": "§13.2 (anchor_points)",
    "CandlePatternEventPayload": "§13.1 + §20",
    "ClassicalPatternEventPayload": "§13.2 + §20",
    "EvidenceRecord": "§19.1",
    "AvailabilitySignature": "D-03-ب + A-01",
    "GroupScore": "§19.3 + D-03-أ",
    "CalibrationReport": "§19.6",
    "FusionSnapshot": "§19.2-5 + D-03",
    "ExplanationObject": "§2.8",
    "PriceZone": "§18.1 (entry_zone)",
    "TriggerDefinition": "§18.1 + §18.4",
    "InvalidationRule": "§18.5 + §23.4",
    "TargetZone": "§10.5",
    "Scenario": "§18.1",
    "ScenarioTransition": "§18.2 + §31.3",
    "OrderIntent": "§24.1",
    "SlippageRecord": "§24.4",
    "LatencyRecord": "§24.5",
    "MacroEventWindow": "§17.3 + §22.1-10",
    "EvaluationContext": "§22.1 + §22.2",
    "NoTradeExplanation": "§22.3",
    "StructuralStop": "§23.4",
    "SizingModifier": "§23.2",
    "SizingResult": "§23.2",
    "CostBreakdown": "§25.2",
    "RewardRiskEstimate": "§23.5",
    "RiskDecision": "§31.3 (decisions)",
    "ExperienceRecord": "§29.1",
    "TVAlertPayload": "§36 + D-07",
    "TVAlertEnvelope": "§32 (الروح) + §36",
    "AlertRevalidation": "§36 (خطوة 7) + §31.6",
    "WebhookAck": "§6.4 + §36",
    "PanelField": "§35.2",
    "ReasoningTraceView": "§35.3",
    "ScenarioView": "§35.1 (طبقتا 4-5) + §18",
    "RejectionView": "§22 + §31.3",
    "ExecutionView": "§28 + §51",
    "WebhookEventView": "§31.6",
    "DashboardCounts": "بوابة 10 (مطابقة الأرقام)",
    "DashboardOverview": "§35.2 + §35.3",
    "SimulatedFill": "§26.1",
    "RealizedCosts": "§25.2 (المحقق)",
    "SimulatedTrade": "§26.1 + §30",
    "EntrySpec": "§24.1 + §26.3",
    "RDistribution": "§29.2",
    "RegimeMetrics": "§29.2 + §43",
    "BacktestMetrics": "§29.2 + §39.2",
    "BacktestIdentity": "§26.2",
    "WFOSegment": "§39.3",
    "WFOWindow": "§39.3",
    "WFOProtocolConfig": "§39.3",
    "WFOReport": "§39.3",
    "BacktestReport": "§26.2 + بوابة 9",
}

# مجلد التصدير: packages/schemas/generated — مشتق من موقع هذه الوحدة لا من cwd.
GENERATED_DIR = Path(__file__).resolve().parents[2] / "generated"


def _file_name(model_name: str) -> str:
    return f"{model_name}.schema.json"


def _schema_text(model: type[BaseModel]) -> str:
    """نص مخطط واحد — حتمي: indent=2 + sort_keys + سطر نهائي."""
    schema = model.model_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _index_text() -> str:
    """فهرس generated/index.json — {model: file, schema_version} حرفيًا."""
    index = {
        name: {"file": _file_name(name), "schema_version": SCHEMA_VERSION} for name in ALL_MODELS
    }
    return json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _readme_text() -> str:
    """جدول توثيق عربي مولّد آليًا لكل النماذج المُصدَّرة."""
    lines = [
        "# المخططات المُصدَّرة — حزمة schemas",
        "",
        "> هذا الملف مولّد آليًا بواسطة `python -m schemas.export write` — **لا تحرّره يدويًا أبدًا**.",
        "> حرس الجودة: `python -m schemas.export check` يجب أن يبقى أخضر في كل بوابة"
        " (لا رسالة بلا مخطط مُصدَّر).",
        "",
        f"- إصدار المخططات: `{SCHEMA_VERSION}`",
        f"- عدد النماذج الجذرية: {len(ALL_MODELS)}",
        "",
        "| النموذج | الملف | الوحدة | فقرة الخطة |",
        "|---|---|---|---|",
    ]
    for name, model in ALL_MODELS.items():
        lines.append(
            f"| `{name}` | `{_file_name(name)}` | `{model.__module__}` | {MODEL_PLAN_REFS[name]} |"
        )
    lines.append("")
    return "\n".join(lines)


def _expected_contents(base: Path) -> dict[Path, str]:
    """كل الملفات المتوقعة بمحتواها الحتمي — تُبنى في الذاكرة للمقارنة."""
    contents: dict[Path, str] = {
        base / _file_name(name): _schema_text(model) for name, model in ALL_MODELS.items()
    }
    contents[base / "index.json"] = _index_text()
    contents[base / "README.md"] = _readme_text()
    return contents


def write(target_dir: Path | None = None) -> int:
    """توليد كل ملفات generated/ — عملية حتمية قابلة للتكرار."""
    base = GENERATED_DIR if target_dir is None else target_dir
    base.mkdir(parents=True, exist_ok=True)
    for path, text in _expected_contents(base).items():
        path.write_text(text, encoding="utf-8")
    print(f"schemas: كُتبت {len(ALL_MODELS)} مخططًا + index.json + README.md في {base}")
    return 0


def check(target_dir: Path | None = None) -> int:
    """إعادة التوليد في الذاكرة والمقارنة بايت-بايت بما على القرص.

    أي فرق (ملف مفقود/منحرف/زائد) أو مجلد فارغ = رسالة واضحة + exit code 1.
    """
    base = GENERATED_DIR if target_dir is None else target_dir
    if not base.is_dir() or not any(base.iterdir()):
        print(
            f"FAIL [{base}]: مجلد generated مفقود أو فارغ — "
            "شغّل `python -m schemas.export write` أولًا",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    expected = _expected_contents(base)
    for path in sorted(expected):
        if not path.is_file():
            problems.append(f"ملف مفقود: {path.name}")
            continue
        if path.read_bytes() != expected[path].encode("utf-8"):
            problems.append(f"ملف منحرف: {path.name} يختلف بايت-بايت عن المولّد")
    expected_names = {path.name for path in expected}
    for path in sorted(base.glob("*.schema.json")):
        if path.name not in expected_names:
            problems.append(f"ملف زائد على القرص: {path.name} لا يقابله أي نموذج")

    if problems:
        for problem in problems:
            print(f"FAIL [{base}]: {problem}", file=sys.stderr)
        print(
            "فشل التحقق: المخططات المُصدَّرة ليست متطابقة مع النماذج — "
            "شغّل `python -m schemas.export write` ثم راجع الفرق",
            file=sys.stderr,
        )
        return 1
    print(f"schemas: check OK — {len(ALL_MODELS)} مخططًا متطابقة بايت-بايت في {base}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m schemas.export",
        description="تصدير JSON Schema من نماذج Pydantic والتحقق من انضباطها (§32)",
    )
    parser.add_argument(
        "command",
        choices=("write", "check"),
        help="write: توليد الملفات الحتمية | check: تحقق بايت-بايت (exit 1 عند أي فرق)",
    )
    args = parser.parse_args(argv)
    command: str = args.command
    if command == "write":
        return write()
    return check()


if __name__ == "__main__":
    sys.exit(main())
