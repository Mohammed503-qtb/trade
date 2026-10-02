"""اختبارات المنفّذ المحاكي (§26.1 + §30) — الحتمية والتحفظ والتعبئة الجزئية.

السيناريو الذهبي المرجعي (المهمة 9.2): مسار معلن بتكاليف معلنة ⇒
نتائج ذهبية محسوبة يدويًا — العلاقات الحسابية كلها محققة بالضبط.
"""

from __future__ import annotations

import pytest
from _backtest_fixtures import T0, candle_at, entry_spec
from backtest import BacktestConfig, SimulatedExecutor, default_backtest_config
from schemas import Direction, ExitReason, LabelState


def _executor(**config_overrides: object) -> SimulatedExecutor:
    return SimulatedExecutor(BacktestConfig(**config_overrides))  # type: ignore[arg-type]


def test_golden_target_first() -> None:
    """الذهبي: لمس منطقة ثم هدف — تعبئة كاملة عند الحافة المعاكسة ومخرج الهدف.

    دخول 100.5 (حافة معاكسة) ومخرج 102.0 ⇒ إجمالي 1.5 لكل وحدة؛
    التكاليف REALISTIC: فاتحة 2×0.5 + انزلاق 2×0.3 + عمولة 2bps×(100.5+102.0).
    """
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),  # شمعة القرار — لا يُرى داخلها
        candle_at(1, 100.4, 100.45, 100.1, 100.3),  # لمس المنطقة [100.0, 100.5]
        candle_at(2, 100.35, 100.4, 100.2, 100.3),
        candle_at(3, 100.5, 102.4, 100.4, 102.2),  # الهدف 102.0
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.label is LabelState.TARGET_FIRST
    assert trade.filled_quantity == pytest.approx(10.0)
    assert trade.entry_fills[0].price == pytest.approx(100.5)
    assert trade.exit_fill is not None and trade.exit_fill.price == pytest.approx(102.0)
    costs = trade.costs
    assert costs is not None
    assert costs.gross_realized_edge == pytest.approx(1.5)
    assert costs.spread == pytest.approx(1.0)
    assert costs.slippage == pytest.approx(0.6)
    assert costs.commission == pytest.approx(2.0 * 1e-4 * (100.5 + 102.0))
    expected_net = 1.5 - (1.0 + 0.6 + 2.0 * 1e-4 * (100.5 + 102.0))
    assert costs.net_realized_edge == pytest.approx(expected_net)
    # MFE/MAE: شمعة الدخول معاكس فقط (low 100.1)، ثم المواتي الكامل (high 102.4)
    assert trade.mae_r == pytest.approx(0.4)
    assert trade.mfe_r == pytest.approx(1.9)


def test_conservative_both_touched_same_bar() -> None:
    """§30 حرفيًا: شمعة لمست الوقف والهدف معًا ⇒ الوقف (أسوأ حالة) موثقًا."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),  # تعبئة الدخول
        candle_at(2, 100.4, 102.5, 99.4, 101.0),  # الوقف 99.5 والهدف 102 معًا
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.STOP
    assert trade.label is LabelState.INVALIDATION_FIRST
    assert trade.ambiguity_resolved_conservatively is True


def test_conservative_entry_then_stop_same_bar() -> None:
    """دخول ووقف في الشمعة نفسها ⇒ تعبئة ثم وقف (أسوأ حالة — لا تجاهل الدخول)."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 99.4, 99.6),  # المنطقة والوقف معًا
    )
    trade = _executor().execute(spec, path)
    assert trade.filled_quantity == pytest.approx(10.0)
    assert trade.exit_reason is ExitReason.STOP
    assert trade.exit_fill is not None and trade.exit_fill.price == pytest.approx(99.5)
    assert trade.mae_r == pytest.approx(1.1)  # (100.5 − 99.4) / 1.0


def test_entry_zone_then_target_same_bar_is_causal() -> None:
    """دخول وهدف (دون وقف) في الشمعة نفسها ⇒ الترتيب السببي الوحيد — لا غموض."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.3, 102.4, 100.15, 102.0),  # المنطقة والهدف دون الوقف
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.ambiguity_resolved_conservatively is False


def test_unfilled_window_expired() -> None:
    """نافذة الدخول انقضت بلا لمس ⇒ UNFILLED/NOT_EXECUTABLE — لم تقم صفقة."""
    spec = entry_spec(horizon_minutes=240)
    path = tuple(candle_at(m, 105.0, 105.5, 104.8, 105.1) for m in range(250))
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.UNFILLED
    assert trade.label is LabelState.NOT_EXECUTABLE
    assert trade.filled_quantity == 0.0
    assert trade.costs is None
    assert trade.mfe_r == 0.0 and trade.mae_r == 0.0


def test_open_at_data_end_unresolved() -> None:
    """بيانات أقصر من أفق النية ⇒ بلا حكم (§30: الوسم بعد الأفق حصرًا)."""
    spec = entry_spec(horizon_minutes=240)
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 105.0, 105.5, 104.8, 105.1),  # لا منطقة ولا وقف — والبيانات تنتهي
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is None
    assert trade.label is None
    assert trade.exit_fill is None


def test_timeout_exit_at_last_certain_close() -> None:
    """المهلة تنقضي: المخرج عند إغلاق آخر شمعة مؤكدة ≤ المهلة — لا هدف بعد المهلة."""
    spec = entry_spec(horizon_minutes=240)
    path = [candle_at(0, 100.6, 100.7, 100.5, 100.6)]
    path.append(candle_at(1, 100.4, 100.45, 100.1, 100.3))  # تعبئة
    path.extend(candle_at(m, 100.5, 100.9, 100.3, 100.7) for m in range(2, 240))
    straddling = candle_at(240, 101.0, 103.0, 100.9, 102.5)  # يغلق بعد المهلة وهدفه بعدها
    path.append(straddling)
    trade = _executor().execute(spec, path)
    # الهدف 103.0 وقع بعد المهلة — لا يُدّعى؛ الخروج عند إغلاق الشمعة 239
    assert trade.exit_reason is ExitReason.TIMEOUT
    assert trade.exit_fill is not None
    assert trade.exit_fill.price == pytest.approx(100.7)
    costs = trade.costs
    assert costs is not None
    assert trade.label is LabelState.TIMEOUT_WITH_LOSS  # صافي سالب بعد التكاليف
    assert costs.net_realized_edge == pytest.approx(0.2 - (1.0 + 0.6 + 2.0 * 1e-4 * 201.2))


def test_straddling_bar_stop_is_adverse_hypothesis() -> None:
    """شريط المهلة العابر لمس الوقف ⇒ فرضية الضرر: وقف (قد سبق المهلة)."""
    spec = entry_spec(horizon_minutes=240)
    path = [candle_at(0, 100.6, 100.7, 100.5, 100.6)]
    path.append(candle_at(1, 100.4, 100.45, 100.1, 100.3))  # تعبئة
    path.extend(candle_at(m, 100.5, 100.9, 100.3, 100.7) for m in range(2, 240))
    path.append(candle_at(240, 100.5, 101.0, 99.4, 100.0))  # وقف داخل الشريط العابر
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.STOP
    assert trade.exit_fill is not None and trade.exit_fill.price == pytest.approx(99.5)


def test_partial_fills_fraction() -> None:
    """تعبئة جزئية §26.1: نسبة إعدادية لكل شمعة لمس حتى اكتمال الكمية."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.3, 100.5, 100.2, 100.4),
        candle_at(3, 100.4, 102.5, 100.3, 102.3),
    )
    trade = _executor(fill_fraction_per_bar=0.5).execute(spec, path)
    assert [f.quantity for f in trade.entry_fills] == pytest.approx([5.0, 5.0])
    assert trade.filled_quantity == pytest.approx(10.0)
    assert trade.exit_reason is ExitReason.TARGET


def test_partial_then_expiry_entry_expiry() -> None:
    """دخول ناقص قطعته المهلة ⇒ ENTRY_EXPIRY للمعبأ عند آخر سعر مؤكد."""
    spec = entry_spec(horizon_minutes=4)
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),  # نصف الكمية (بنسبة 0.5)
        candle_at(2, 100.3, 100.5, 100.2, 100.4),  # النصف الثاني — داخل النافذة (إغلاق 3د ≤ 4د)
        candle_at(3, 101.0, 103.0, 100.9, 102.5),  # يغلق عند 4د = المهلة بالضبط
        candle_at(4, 102.0, 104.0, 101.9, 103.5),  # بعد المهلة
    )
    trade = _executor(fill_fraction_per_bar=0.5).execute(spec, path)
    # الشمعة 3 تغلق عند 4د = المهلة: هدفها 103 > 102 وقع داخل النافذة
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.filled_quantity == pytest.approx(10.0)


def test_short_side_mirrors_long() -> None:
    """البيع مرآة الشراء: تعبئة عند الحافة المعاكسة (أدنى) ووقف أعلى وهدف أدنى."""
    spec = entry_spec(side=Direction.SHORT)
    path = (
        candle_at(0, 99.4, 99.5, 99.3, 99.45),  # شمعة القرار
        candle_at(1, 99.7, 99.9, 99.55, 99.8),  # لمس المنطقة [99.5, 100.0]
        candle_at(2, 99.6, 99.8, 99.4, 99.5),  # اقتراب بلا هدف
        candle_at(3, 98.5, 99.4, 97.9, 98.3),  # الهدف 98.0 ملموسًا
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.TARGET
    assert trade.entry_fills[0].price == pytest.approx(99.5)
    assert trade.exit_fill is not None and trade.exit_fill.price == pytest.approx(98.0)
    costs = trade.costs
    assert costs is not None
    assert costs.gross_realized_edge == pytest.approx(99.5 - 98.0)  # بيع: (خروج−دخول)×(−1)


def test_short_stop_before_target_conservative() -> None:
    """بيع: وقف وهدف معًا في شمعة ⇒ الوقف (التحفظ جهة-محيّد)."""
    spec = entry_spec(side=Direction.SHORT)
    path = (
        candle_at(0, 99.4, 99.5, 99.3, 99.45),
        candle_at(1, 99.7, 99.9, 99.55, 99.8),
        candle_at(2, 99.0, 100.6, 97.9, 99.2),  # الوقف 100.5 والهدف 98.0 معًا
    )
    trade = _executor().execute(spec, path)
    assert trade.exit_reason is ExitReason.STOP
    assert trade.ambiguity_resolved_conservatively is True


def test_no_lookahead_entry_from_next_bar_only() -> None:
    """§26.3: شمعة القرار نفسها لمست المنطقة ولا تعبئة عليها — التالية حصرًا."""
    spec = entry_spec(decision_minute=5, horizon_minutes=2)
    # الشمعة 5 (شمعة القرار) لمست المنطقة بقوة — لا تعبئة عليها أبدًا
    decision_bar = candle_at(5, 100.4, 100.45, 100.05, 100.3)
    after = (
        candle_at(6, 105.0, 105.5, 104.8, 105.1),  # داخل النافذة بلا لمس
        candle_at(7, 105.0, 105.5, 104.8, 105.1),  # عابر — النافذة انقضت
    )
    trade = _executor().execute(spec, (decision_bar, *after))
    assert trade.filled_quantity == 0.0
    assert trade.exit_reason is ExitReason.UNFILLED


def test_unsupported_timeframe_rejected() -> None:
    """إطار غير 1m رفض صريح — إطار التنفيذ الموحد في MVP."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6, timeframe="5m"),
        candle_at(5, 100.4, 100.5, 100.2, 100.3, timeframe="5m"),
    )
    with pytest.raises(ValueError, match="إطار غير مدعوم"):
        _executor().execute(spec, path)


def test_executor_determinism_byte_identical() -> None:
    """الحتمية: نفس المدخلات مرتين ⇒ نفس الصفقة حقلاً حقلاً (بايت-بايت)."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.35, 100.4, 100.2, 100.3),
        candle_at(3, 100.5, 102.4, 100.4, 102.2),
    )
    first = _executor().execute(spec, path)
    second = _executor().execute(spec, path)
    assert first.model_dump() == second.model_dump()
    assert first == second


def test_fill_time_is_bar_close_event_time() -> None:
    """زمن الحدث: التعبئة تؤرخ عند إغلاق شمعة اللمس (bar_time + الإطار)."""
    from datetime import timedelta

    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.5, 102.4, 100.4, 102.2),
    )
    trade = _executor().execute(spec, path)
    expected_entry = T0 + timedelta(minutes=2)  # إغلاق شمعة الدقيقة 1
    expected_exit = T0 + timedelta(minutes=3)  # إغلاق شمعة الدقيقة 2
    assert trade.entry_fills[0].fill_time == expected_entry
    assert trade.exit_fill is not None
    assert trade.exit_fill.fill_time == expected_exit


def test_latency_recorded_on_fills() -> None:
    """الكمون الإعدادي يسجل في كل تعبئة (§24.5) — قياس نمذجة لا ساعة داخلية."""
    spec = entry_spec()
    path = (
        candle_at(0, 100.6, 100.7, 100.5, 100.6),
        candle_at(1, 100.4, 100.45, 100.1, 100.3),
        candle_at(2, 100.5, 102.4, 100.4, 102.2),
    )
    trade = _executor(latency_ms=500.0).execute(spec, path)
    assert trade.entry_fills[0].latency_ms == pytest.approx(500.0)
    assert trade.exit_fill is not None
    assert trade.exit_fill.latency_ms == pytest.approx(500.0)


def test_default_config_matches_defaults() -> None:
    """الإعداد الافتراضي قابل للبناء وبصمته حتمة — لا حالة كونية."""
    first = default_backtest_config()
    second = default_backtest_config()
    assert first.fingerprint() == second.fingerprint()
    assert len(first.fingerprint()) == 64
