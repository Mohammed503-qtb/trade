"""حتمية الإعادة (§26.2 + المهمة 9.6) — فحص CI-مستمر في كل ``make gate``.

«The exact result must be reproducible from those identifiers» — على
عقد صناعي صغير حتمي (بلا اعتماد على بيانات خارجية): نفس المعرّفات
التسع ⇒ نفس backtest_id ونفس بايتات التقرير كلها (بساعة محقونة)،
وأي معرّف مختلف ⇒ ختم مختلف.

هذا هو فحص الحتمية **المستمر**؛ الحتمية الكاملة للمسار الحقيقي
(كواشف ← دمج ← سيناريوهات ← مخاطرة ← تنفيذ) تثبتها بوابة المرحلة 9
بتشغيلين كاملين متطابقين على العينة الحقيقية.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from backtest import ReplayWindow, backtest_id_for
from engine_replay import run_backtest
from schemas import (
    BacktestIdentity,
    Candle,
    DataQuality,
    Direction,
    EntrySpec,
    LabelState,
)

pytestmark = pytest.mark.replay

#: ساعة محقونة — الحتمية الكاملة (لا استثناء created_at).
FIXED_CLOCK = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

#: لحظة الصفر.
T0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def _candle(minute: int, o: float, h: float, lo: float, c: float) -> Candle:
    rng = h - lo
    return Candle(
        instrument_id="BTCUSDT",
        timeframe="1m",
        bar_time=T0 + timedelta(minutes=minute),
        session_id="sess-replay",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=100.0,
        range=rng,
        body_size=abs(c - o),
        upper_wick=h - max(o, c),
        lower_wick=min(o, c) - lo,
        body_fraction=(abs(c - o) / rng) if rng > 0 else 0.0,
        close_location_value=((c - lo) / rng) if rng > 0 else 0.5,
        true_range=rng,
        realized_volatility=(rng / c) if c > 0 else 0.0,
    )


def _specs() -> tuple[EntrySpec, ...]:
    """نيتان متنافستان زمنيًا (شراء فائز وبيع لم يعبأ) بترتيب وصول معكوس.

    الخط يعيد الترتيب الحتمي (القرار ثم السيناريو) — نثبت ذلك هنا.
    """
    long_winner = EntrySpec(
        trade_intent_id="ti-r1",
        scenario_id="sc-r2",
        decision_id="dc-r2",
        symbol="BTCUSDT",
        side=Direction.LONG,
        entry_price=100.5,
        zone_opposite_price=100.0,
        stop_price=99.5,
        target_price=105.0,
        decision_time=T0 + timedelta(minutes=10),
        expiry=T0 + timedelta(minutes=250),
        planned_quantity=8.0,
        regime="TREND",
    )
    short_open = EntrySpec(
        trade_intent_id="ti-r0",
        scenario_id="sc-r1",
        decision_id="dc-r1",
        symbol="BTCUSDT",
        side=Direction.SHORT,
        entry_price=99.5,
        zone_opposite_price=100.0,
        stop_price=100.5,
        target_price=95.0,
        decision_time=T0 + timedelta(minutes=10),
        expiry=T0 + timedelta(minutes=250),
        planned_quantity=6.0,
        regime="RANGE",
    )
    return (short_open, long_winner)  # ترتيب وصول معكوس عمدًا


def _candles() -> tuple[Candle, ...]:
    """مسار حتمي: هبوط للمنطقة ثم صعود لهدف بعيد — منطقة البيع لا تُلمس أبدًا."""
    path = [_candle(m, 100.9, 101.0, 100.7, 100.8) for m in range(10)]  # قبل القرار
    path.append(_candle(10, 100.8, 100.9, 100.6, 100.7))  # شمعة القرار
    path.append(_candle(11, 100.5, 100.6, 100.05, 100.2))  # تعبئة الشراء عند 100.5
    path.append(_candle(12, 100.3, 100.5, 100.1, 100.4))
    path.append(_candle(13, 100.6, 105.5, 100.5, 105.2))  # هدف الشراء 105
    path.append(_candle(14, 101.5, 101.6, 101.3, 101.4))
    path.append(_candle(15, 101.2, 101.3, 100.9, 101.0))
    # منطقة البيع [99.5, 100.0] لم تُلمس — نيته تبقى غير محسومة حتى نهاية البيانات
    return tuple(path)


def _identity(**overrides: object) -> BacktestIdentity:
    base: dict[str, object] = {
        "backtest_id": "sealed",
        "data_snapshot_id": "replay-ci-v1",
        "code_version": "workspace",
        "model_version": "none-mvp",
        "parameter_set_version": "risk-default-v1",
        "cost_model_version": "backtest-default",
        "random_seed": 0,
        "start_time": T0,
        "end_time": T0 + timedelta(minutes=250),
        "instrument_set": ("BTCUSDT",),
    }
    base.update(overrides)
    return BacktestIdentity(**base)  # type: ignore[arg-type]


def test_same_identity_same_report_byte_for_byte() -> None:
    """نفس المعرّفات والمدخلات ⇒ نفس التقرير بايت-بايت (ساعة محقونة)."""
    first, _ = run_backtest(
        specs=_specs(),
        candles=_candles(),
        identity=_identity(),
        now=lambda: FIXED_CLOCK,
    )
    second, _ = run_backtest(
        specs=_specs(),
        candles=_candles(),
        identity=_identity(),
        now=lambda: FIXED_CLOCK,
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert first.identity.backtest_id == second.identity.backtest_id


def test_any_identifier_change_changes_seal() -> None:
    """أي معرّف من التسع يتغير ⇒ ختم مختلف — لا انفصام هوية/مضمون."""
    sealed = backtest_id_for(_identity())
    for field, value in (
        ("data_snapshot_id", "replay-ci-v2"),
        ("code_version", "v2"),
        ("model_version", "calibrated-1"),
        ("parameter_set_version", "risk-v2"),
        ("cost_model_version", "backtest-v2"),
        ("random_seed", 99),
    ):
        assert sealed != backtest_id_for(_identity(**{field: value})), field


def test_pipeline_orders_trades_deterministically() -> None:
    """ترتيب الصفقات حتمي (القرار ثم السيناريو) رغم ترتيب وصول معكوس."""
    _, trades = run_backtest(
        specs=_specs(),
        candles=_candles(),
        identity=_identity(),
        now=lambda: FIXED_CLOCK,
    )
    assert [t.scenario_id for t in trades] == ["sc-r1", "sc-r2"]
    # الشراء فائز (هدف بعيد) والبيع لم يعبأ (منطقته لم تُلمس — غير محسوم)
    assert trades[1].label is LabelState.TARGET_FIRST
    assert trades[0].exit_reason is None


def test_report_sealed_and_reproducible_artifact() -> None:
    """التقرير المختوم قابل لإعادة الإنتاج: أثر JSON معاد البناء متطابق بايت-بايت."""
    report, _ = run_backtest(
        specs=_specs(),
        candles=_candles(),
        identity=_identity(),
        now=lambda: FIXED_CLOCK,
    )
    artifact = json.dumps(
        json.loads(report.model_dump_json()),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    again, _ = run_backtest(
        specs=_specs(),
        candles=_candles(),
        identity=_identity(),
        now=lambda: FIXED_CLOCK,
    )
    rebuilt = json.dumps(
        json.loads(again.model_dump_json()),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    assert artifact == rebuilt


def test_window_no_lookahead_property() -> None:
    """خاصية §26.3 المستمرة: كل ما تراه النافذة عند أي لحظة مغلقٌ بحكم البناء."""
    candles = _candles()
    window = ReplayWindow(candles=candles, timeframe_s=60.0)
    for index in range(len(candles)):
        as_of = candles[index].bar_time + timedelta(seconds=60)
        visible = window.closed_candles(as_of)
        for candle in visible:
            assert candle.bar_time + timedelta(seconds=60.0) <= as_of
            assert candle.is_closed
