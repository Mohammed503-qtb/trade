"""اختبارات هوية الاستنساخ وتقرير الإعادة (§26.2) — الختم والحتمية البايتية.

«The exact result must be reproducible from those identifiers» — نفس
المعرفات التسع ⇒ نفس backtest_id؛ ونفس الهوية والمدخلات ⇒ نفس بايتات
التقرير كلها ما خلا created_at_utc (الاستثناء الموثق الوحيد).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from _backtest_fixtures import T0, candle_at, entry_spec
from backtest import SimulatedExecutor, backtest_id_for, build_report, default_backtest_config
from schemas import (
    BacktestIdentity,
    BacktestReport,
    CostMode,
    EntrySpec,
    ExitReason,
    IntrabarPolicy,
    LabelState,
    SimulatedTrade,
)


def _identity(**overrides: object) -> BacktestIdentity:
    base: dict[str, object] = {
        "backtest_id": "placeholder",  # يختمه البنّاء من المعرّفات ذاتها
        "data_snapshot_id": "phase2-v1",
        "code_version": "0.9.0",
        "model_version": "none-mvp",
        "parameter_set_version": "risk-v1",
        "cost_model_version": "realistic-v1",
        "random_seed": 0,
        "start_time": T0,
        "end_time": datetime(2026, 1, 2, tzinfo=UTC),
        "instrument_set": ("BTCUSDT",),
    }
    base.update(overrides)
    return BacktestIdentity(**base)  # type: ignore[arg-type]


def _trades() -> list[SimulatedTrade]:
    executor = SimulatedExecutor(default_backtest_config())
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.5, 102.4, 100.4, 102.2),
    )
    return [executor.execute(spec, path)]


_FIXED_CLOCK = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_identity_seal_deterministic() -> None:
    """نفس المعرّفات ⇒ نفس الختم؛ وأي معرّف مختلف ⇒ ختم مختلف."""
    first = backtest_id_for(_identity())
    second = backtest_id_for(_identity())
    assert first == second
    assert first != backtest_id_for(_identity(code_version="0.9.1"))
    assert first != backtest_id_for(_identity(random_seed=7))
    assert first != backtest_id_for(_identity(instrument_set=("BTCUSDT", "ETHUSDT")))


def test_identity_contract_sanity() -> None:
    """أدوات فارغة أو نافذة معكوسة رفض صريح من العقد."""
    with pytest.raises(ValueError, match="مجموعة الأدوات فارغة"):
        _identity(instrument_set=())
    with pytest.raises(ValueError, match="معكوسة"):
        _identity(end_time=T0.replace(year=2025))


def test_report_byte_determinism_with_injected_clock() -> None:
    """ساعة محقونة ⇒ تقريران متطابقان بايت-بايت (الحتمية الكاملة)."""
    trades = _trades()
    config = default_backtest_config()
    first = build_report(
        identity=_identity(),
        trades=trades,
        config=config,
        now=lambda: _FIXED_CLOCK,
    )
    second = build_report(
        identity=_identity(),
        trades=trades,
        config=config,
        now=lambda: _FIXED_CLOCK,
    )
    assert first.model_dump_json() == second.model_dump_json()


def test_report_created_at_sole_exception() -> None:
    """بدون ساعة محقونة يظل created_at_utc الاستثناء الحتمي الوحيد."""
    trades = _trades()
    config = default_backtest_config()
    first = build_report(identity=_identity(), trades=trades, config=config)
    second = build_report(identity=_identity(), trades=trades, config=config)
    assert first.created_at_utc != second.created_at_utc
    first_payload = first.model_dump(exclude={"created_at_utc"})
    second_payload = second.model_dump(exclude={"created_at_utc"})
    assert first_payload == second_payload


def test_report_seals_identity_from_fields() -> None:
    """البنّاء يختم backtest_id من المعرّفات — القيمة العابرة تُستبدل."""
    report = build_report(
        identity=_identity(backtest_id="whatever"),
        trades=_trades(),
        config=default_backtest_config(),
        now=lambda: _FIXED_CLOCK,
    )
    assert report.identity.backtest_id == backtest_id_for(_identity())
    assert report.identity.backtest_id != "whatever"


def test_report_acceptance_mode_realistic_only() -> None:
    """العقد يرفض تقرير قبول بغير REALISTIC أو غير CONSERVATIVE (§25.1/§30)."""
    base = build_report(
        identity=_identity(),
        trades=_trades(),
        config=default_backtest_config(),
        now=lambda: _FIXED_CLOCK,
    )
    payload = base.model_dump()
    optimistic = dict(payload)
    optimistic["cost_mode"] = CostMode.OPTIMISTIC.value
    with pytest.raises(ValueError, match="نمط القبول"):
        BacktestReport.model_validate(optimistic)
    stress = dict(payload)
    stress["intrabar_policy"] = IntrabarPolicy.HIGHER_RESOLUTION.value
    with pytest.raises(ValueError, match="غير متاحة في MVP"):
        BacktestReport.model_validate(stress)


def test_report_notes_document_discipline() -> None:
    """الملاحظات تثبت قواعد التحفظ والتكلفة — بلا-صمت في التقرير الموثق."""
    report = build_report(
        identity=_identity(),
        trades=_trades(),
        config=default_backtest_config(),
        now=lambda: _FIXED_CLOCK,
    )
    assert any("متحفظ" in note for note in report.notes)
    assert any("REALISTIC" in note for note in report.notes)


def test_report_counts_open_and_unfilled() -> None:
    """المفتوحة عند نهاية البيانات وغير المنفذة تُحصى عدًّا موثقًا."""
    executor = SimulatedExecutor(default_backtest_config())
    # غير منفذة
    unfilled = executor.execute(
        entry_spec(
            horizon_minutes=10,
            trade_intent_id="ti-u",
            scenario_id="sc-u",
            decision_id="dc-u",
        ),
        tuple(candle_at(m, 105.0, 105.5, 104.8, 105.1) for m in range(15)),
    )
    # مفتوحة عند نهاية البيانات
    open_trade = executor.execute(
        entry_spec(trade_intent_id="ti-o", scenario_id="sc-o", decision_id="dc-o"),
        (
            candle_at(0, 100.6, 100.7, 100.5, 100.6),
            candle_at(1, 100.4, 100.45, 100.1, 100.3),
            candle_at(2, 100.4, 100.5, 100.3, 100.45),
        ),
    )
    report = build_report(
        identity=_identity(),
        trades=[*_trades(), unfilled, open_trade],
        config=default_backtest_config(),
        now=lambda: _FIXED_CLOCK,
    )
    assert unfilled.exit_reason is ExitReason.UNFILLED
    assert unfilled.label is LabelState.NOT_EXECUTABLE
    assert open_trade.exit_reason is None
    assert report.metrics.not_executable == 1
    assert report.metrics.open_at_data_end == 1
    assert any("مفتوحة" in note for note in report.notes)
    assert any("NOT_EXECUTABLE" in note for note in report.notes)


def test_report_schema_legality_roundtrip() -> None:
    """التقرير يمر عقد schemas ذهابًا وإيابًا — عقود العبور محفوظة."""
    report = build_report(
        identity=_identity(),
        trades=_trades(),
        config=default_backtest_config(),
        now=lambda: _FIXED_CLOCK,
    )
    assert isinstance(report.identity.instrument_set, tuple)
    validated = BacktestReport.model_validate_json(report.model_dump_json())
    assert validated == report


def test_entry_spec_contract_guards() -> None:
    """مواصفة الدخول ترفض الهندسة المعكوسة والنية المنقضية قبل قرارها."""
    broken = entry_spec().model_dump() | {"stop_price": 101.0}  # وقف فوق دخول شراء
    with pytest.raises(ValueError, match="هندسة معكوسة"):
        EntrySpec.model_validate(broken)
    with pytest.raises(ValueError, match="لا يتقدم"):
        entry_spec(horizon_minutes=-5)
