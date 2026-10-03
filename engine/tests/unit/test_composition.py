"""اختبارات وحدة تركيب اللوحة — الحتمية ومطابقة أرقام البوابات (بوابة 10).

العقد الجوهري (ADR-028): اللوحة تعرض كائنات البوابات نفسها — فكل رقم
فيها يساوي رقم البوابة الموثق حرفيًا (103/58/45/58 من إغلاق 8 و9).
"""

from __future__ import annotations

import pytest
from engine_api.composition import build_overview
from schemas import DashboardOverview


@pytest.fixture(scope="module")
def overview() -> object:
    """بناء واحد للوحدة — الحتمية تجعل التكرار بلا معنى."""
    return build_overview()


class TestCompositionMatchesGateNumbers:
    """أرقام البوابات الموثقة — إغلاق المرحلتين 8 و9 حرفيًا."""

    def test_risk_counts_match_phase8_gate(self, overview: DashboardOverview) -> None:
        assert overview.counts.risk_decisions == 103
        assert overview.counts.authorized == 58
        assert overview.counts.rejected == 45

    def test_simulated_trades_match_phase9_gate(self, overview: DashboardOverview) -> None:
        assert overview.counts.simulated_trades == 58

    def test_execution_metrics_match_phase9_report(self, overview: DashboardOverview) -> None:
        assert overview.execution.mode == "SIMULATION_ONLY"
        assert overview.execution.net_expectancy_r == pytest.approx(-0.967, abs=0.001)
        assert overview.execution.win_rate == pytest.approx(0.22, abs=0.005)

    def test_rejections_log_complete(self, overview: DashboardOverview) -> None:
        assert len(overview.rejections) == 45
        assert all(r.reason_code for r in overview.rejections)


class TestPanelContract:
    """لوحة §35.2 — ثلاثة عشر حقلًا حرفيًا بمعرفات ثابتة."""

    EXPECTED_KEYS: tuple[str, ...] = (
        "market_regime",
        "htf_bias",
        "mtf_setup_state",
        "liquidity_above_below",
        "flow_state",
        "delta",
        "volatility_state",
        "session",
        "macro_risk",
        "active_scenario",
        "trigger_status",
        "risk_status",
        "execution_status",
    )

    def test_panel_has_exactly_thirteen_fields_in_order(self, overview: DashboardOverview) -> None:
        assert [f.key for f in overview.panel] == list(self.EXPECTED_KEYS)

    def test_every_field_has_nonempty_value(self, overview: DashboardOverview) -> None:
        assert all(f.value for f in overview.panel)


class TestReasoningTraces:
    """أثر §35.3 — ثلاث قوائم صريحة لا ملصق نسبة."""

    def test_traces_have_three_sections(self, overview: DashboardOverview) -> None:
        assert len(overview.traces) > 0
        first = overview.traces[0]
        assert hasattr(first, "why_active")
        assert hasattr(first, "what_against")
        assert hasattr(first, "why_wait")
        assert first.why_wait  # سبب انتظار معلن دائمًا

    def test_decision_traces_carry_human_explanation(self, overview: DashboardOverview) -> None:
        with_text = [t for t in overview.traces if len(t.why_active) >= 2]
        assert with_text, "تفسير §2.8 النصي يجب أن يظهر في الأثر"


class TestDeterminism:
    def test_two_builds_identical_byte_for_byte(self) -> None:
        first = build_overview()
        second = build_overview()
        assert first.model_dump(mode="json") == second.model_dump(mode="json")

    def test_legality_against_exported_schema(self, overview: DashboardOverview) -> None:
        import json

        import jsonschema
        from schemas.export import GENERATED_DIR

        schema = json.loads(
            (GENERATED_DIR / "DashboardOverview.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(overview.model_dump(mode="json"), schema)
