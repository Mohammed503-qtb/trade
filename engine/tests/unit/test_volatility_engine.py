"""اختبارات محرك التقلب — بوابة المهمة 2.2 الحرفية (§16 + §26.3).

يُقفل بمسارات معروفة: القيم النهائية يدويًا وعبر الجسر، تقليص الدافئ،
عقد المتأخرة المحصاة والتكرار المرفوض والشمع المتطورة المرفوض،
**العتبات التطبيعية** (خطية في ATR — لا مسار ينتج عتبة مطلقة، وNone قبل
الدافئ)، والحتمية التامة بين محركين.
"""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from features import (
    atr_pct_series,
    atr_series,
    expected_holding_vol_series,
    gap_shock_series,
    range_expansion_series,
    realized_vol_series,
    spread_to_range_series,
    vol_of_vol_series,
)
from market_state.volatility import (
    DEFAULT_MULTIPLIERS,
    ThresholdKey,
    VolatilityConfig,
    VolatilityEngine,
    VolatilityState,
    compute_market_volatility_summary,
)
from schemas import Candle, DataQuality

_BASE = datetime(2026, 1, 5, tzinfo=UTC)


def _candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
    instrument_id: str = "BINANCE_USDM:BTCUSDT",
    timeframe: str = "1m",
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    span = high - low
    body = abs(close - open_)
    if span > 0.0:
        body_fraction = body / span
        close_location = (close - low) / span
    else:
        body_fraction = 0.0
        close_location = 0.5
    return Candle(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else _BASE + timedelta(minutes=index),
        session_id="2026-01-05",
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def _synth(n: int, *, scale: float = 1.0) -> list[Candle]:
    """سلسلة حتمية مضطربة — عامل scale يضرب كل الأسعار (لاختبار خطية العتبات)."""
    out: list[Candle] = []
    for i in range(n):
        open_ = (100.0 + math.sin(i / 5.0) * 5.0 + ((i % 3) - 1) * 0.25) * scale
        close = (100.0 + math.sin((i + 1) / 5.0) * 5.0) * scale
        high = (max(open_, close) / scale + abs(math.sin(i / 3.0)) * 2.0 + 0.5) * scale
        low = (min(open_, close) / scale - abs(math.cos(i / 4.0)) * 2.0 - 0.5) * scale
        out.append(
            _candle(
                i,
                open_=open_,
                high=high,
                low=low,
                close=close,
                volume=100.0 + (i * 37) % 90,
            )
        )
    return out


# الشموع اليدوية الخمس للإعداد المصغر (قيم TR = [3,3,5,3,3] باليد)
_MANUAL_OHLC: list[tuple[float, float, float, float]] = [
    (100.0, 102.0, 99.0, 101.0),
    (101.0, 103.0, 100.0, 102.0),
    (102.0, 106.0, 101.0, 105.0),
    (105.0, 107.0, 104.0, 106.0),
    (106.0, 108.0, 105.0, 107.0),
]


def _manual_candles() -> list[Candle]:
    return [
        _candle(i, open_=o, high=h, low=low, close=c)
        for i, (o, h, low, c) in enumerate(_MANUAL_OHLC)
    ]


_TINY = VolatilityConfig(
    atr_period=2,
    pct_window=3,
    rv_window=2,
    vov_window=2,
    range_window=3,
    holding_horizons=(4,),
)


# ═══════════ عقد الإرجاع والحالة الأولية ═══════════


def test_fresh_engine_initial_state() -> None:
    """محرك بكر: لا حالة، صفر استهلاك، صفر متأخرة، ولا هوية بعد."""
    engine = VolatilityEngine()
    assert engine.state is None
    assert engine.stats.bars_consumed == 0
    assert engine.stats.late_ignored == 0
    assert engine.instrument_id is None
    assert engine.timeframe is None


def test_first_candle_returns_none() -> None:
    """أول شمعة على الإطلاق ⇒ None (لا حالة تقلب من شمعة واحدة)."""
    engine = VolatilityEngine()
    candles = _manual_candles()
    assert engine.update(candles[0]) is None
    assert engine.stats.bars_consumed == 1
    assert engine.state is None


def test_second_candle_returns_state() -> None:
    """ثاني شمعة ⇒ أول حالة: bar_time للشمعة، وwarmup يقظ في العد."""
    engine = VolatilityEngine(config=_TINY)
    candles = _manual_candles()
    engine.update(candles[0])
    state = engine.update(candles[1])
    assert state is not None
    assert state.bar_time == candles[1].bar_time
    assert state.warmup_bars_remaining == _TINY.warmup_bars - 2
    assert state.data_sufficient is False
    assert state.atr == 3.0  # بذرة ATR(2) عند الشمعة الثانية: متوسط TR[0:2]
    assert state.atr_percentile is None  # المئيني(3) يحتاج فهرس 2+
    assert state.spread_to_range is not None


def test_identity_captured_from_first_candle() -> None:
    """بلا هوية صريحة تُلتقط من أول شمعة، وأي خلط لاحق يُرفض."""
    engine = VolatilityEngine()
    candles = _manual_candles()
    engine.update(candles[0])
    assert engine.instrument_id == "BINANCE_USDM:BTCUSDT"
    assert engine.timeframe == "1m"
    intruder = _candle(9, open_=100.0, high=101.0, low=99.0, close=100.0, timeframe="5m")
    with pytest.raises(ValueError, match="خلط أطر"):
        engine.update(intruder)


def test_explicit_identity_mismatch_rejected() -> None:
    """هوية صريحة في البناء ترفض أي شمعة من غيرها — أدوات وأطر معًا."""
    engine = VolatilityEngine(instrument_id="BINANCE_USDM:BTCUSDT", timeframe="1m")
    wrong_instrument = _candle(
        0, open_=100.0, high=101.0, low=99.0, close=100.0, instrument_id="BINANCE_USDM:ETHUSDT"
    )
    with pytest.raises(ValueError, match="خلط أدوات"):
        engine.update(wrong_instrument)
    wrong_timeframe = _candle(0, open_=100.0, high=101.0, low=99.0, close=100.0, timeframe="5m")
    with pytest.raises(ValueError, match="خلط أطر"):
        engine.update(wrong_timeframe)


def test_evolving_candle_rejected() -> None:
    """الشمع المتطورة مرفوضة صراحة — المحرك يستهلك المغلقات فقط (§27)."""
    engine = VolatilityEngine()
    developing = _candle(0, open_=100.0, high=101.0, low=99.0, close=100.0, is_closed=False)
    with pytest.raises(ValueError, match="المغلقة فقط"):
        engine.update(developing)
    assert engine.stats.bars_consumed == 0  # لا أثر جانبي


# ═══════════ القيم النهائية: يدويًا + جسرًا ═══════════


def test_manual_tiny_config_end_values() -> None:
    """الإعداد المصغر: قيم النهاية بالضبط — ATR=3.25 ومئيني ATR=0.0 وسبر=1/3.

    TR = [3,3,5,3,3] باليد ⇒ ATR(2) = [nan, 3.0, 4.0, 3.5, 3.25].
    المئيني(3) عند الأخيرة: النافذة [4, 3.5, 3.25] والقيمة 3.25 لا تعلو ⇒ 0.0.
    المدىات [3,3,5,3,3]: توسع المدى(3) عند الأخيرة: النافذة [5,3,3] والقيمة 3 ⇒ 0.0.
    الفجوات كلها صفرية (open = close السابق) ⇒ gap = 0.0.
    """
    engine = VolatilityEngine(config=_TINY)
    for candle in _manual_candles():
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.atr == 3.25
    assert state.atr_percentile == 0.0
    assert state.range_expansion_percentile == 0.0
    assert state.gap_shock == 0.0
    assert state.spread_to_range == 1.0 / 3.0
    assert state.data_sufficient is True
    assert state.warmup_bars_remaining == 0
    # rv وvov وehv بحساب يدوي صريح على العوائد
    closes = [c.close for c in _manual_candles()]
    r = [math.log(closes[i] / closes[i - 1]) for i in range(1, 5)]

    def _std2(a: float, b: float) -> float:
        m = (a + b) / 2.0
        return math.sqrt(((a - m) ** 2 + (b - m) ** 2) / 1.0)

    rv_last = _std2(r[2], r[3])  # آخر نافذة عوائد [ln(106/105), ln(107/106)]
    assert state.realized_vol == pytest.approx(rv_last, rel=1e-12)
    rv_prev = _std2(r[1], r[2])
    vov_expected = _std2(rv_prev, rv_last) / ((rv_prev + rv_last) / 2.0)
    assert state.vol_of_vol == pytest.approx(vov_expected, rel=1e-12)
    assert state.expected_holding_vol_1h is None  # الأفق 60 غير معد — المعد 4
    assert state.expected_holding_vol[4] == pytest.approx(rv_last * 2.0, rel=1e-12)


def test_engine_matches_features_bridge_default_config() -> None:
    """الحالة النهائية == آخر عنصر من السمات على آخر ``history_bars`` شمعة (جسر A-02)."""
    candles = _synth(150)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    window = candles[-VolatilityConfig().history_bars :]
    cfg = VolatilityConfig()
    assert state.atr == float(atr_series(window, cfg.atr_period)[-1])
    assert state.atr_percentile == float(atr_pct_series(window, cfg.atr_period, cfg.pct_window)[-1])
    assert state.realized_vol == float(realized_vol_series(window, cfg.rv_window)[-1])
    assert state.range_expansion_percentile == float(
        range_expansion_series(window, cfg.range_window)[-1]
    )
    assert state.vol_of_vol == float(vol_of_vol_series(window, cfg.rv_window, cfg.vov_window)[-1])
    assert state.gap_shock == float(gap_shock_series(window, cfg.atr_period)[-1])
    assert state.spread_to_range == float(spread_to_range_series(window)[-1])
    assert state.expected_holding_vol_1h == float(
        expected_holding_vol_series(window, 60, cfg.rv_window)[-1]
    )


def test_truncation_error_negligible_vs_full_history() -> None:
    """المقايضة الموثقة: قيم النافذة قريبة جدًا من حساب التاريخ الكامل."""
    candles = _synth(150)
    full_atr = float(atr_series(candles, 14)[-1])
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.atr is not None
    assert state.atr == pytest.approx(full_atr, rel=5e-3)


# ═══════════ الدافئ: التقليص والإتاحة ═══════════


def test_warmup_countdown_tiny_config() -> None:
    """العد يقظ حرفيًا: None أولًا ثم warmup−k حتى الصفر ثم يبقى صفريًا."""
    engine = VolatilityEngine(config=_TINY)
    candles = _manual_candles()
    assert engine.update(candles[0]) is None
    state2 = engine.update(candles[1])
    state3 = engine.update(candles[2])
    state4 = engine.update(candles[3])
    state5 = engine.update(candles[4])
    assert state2 is not None and state2.warmup_bars_remaining == 2
    assert state3 is not None and state3.warmup_bars_remaining == 1
    assert state4 is not None and state4.warmup_bars_remaining == 0
    assert state5 is not None and state5.warmup_bars_remaining == 0


def test_warmup_countdown_default_config() -> None:
    """الافتراضي: warmup_bars=100 — نقاط فحص على طول المسار."""
    candles = _synth(150)
    engine = VolatilityEngine()
    checkpoints = {2: 98, 50: 50, 99: 1, 100: 0, 150: 0}
    states: dict[int, VolatilityState] = {}
    for i, candle in enumerate(candles, start=1):
        state = engine.update(candle)
        if i in checkpoints and state is not None:
            states[i] = state
    assert VolatilityConfig().warmup_bars == 100
    for bars, remaining in checkpoints.items():
        assert states[bars].warmup_bars_remaining == remaining


def test_data_sufficient_flips_exactly_at_warmup() -> None:
    """False عند 99 شمعة، True عند 100 — بالضبط عند اكتمال أعمق سلسلة."""
    candles = _synth(101)
    engine = VolatilityEngine()
    for i, candle in enumerate(candles, start=1):
        state = engine.update(candle)
        if i in (99, 100):
            assert state is not None
            assert state.data_sufficient is (i >= 100)


def test_metric_availability_checkpoints() -> None:
    """إتاحة كل مقياس عند نقاطه الموثقة (اشتقاق warmup_bars)."""
    candles = _synth(150)
    engine = VolatilityEngine()
    observed: dict[int, VolatilityState] = {}
    for i, candle in enumerate(candles, start=1):
        state = engine.update(candle)
        if i in (2, 14, 20, 50, 100) and state is not None:
            observed[i] = state
    s2 = observed[2]
    assert s2.spread_to_range is not None
    assert s2.atr is None and s2.gap_shock is None and s2.realized_vol is None
    s14 = observed[14]
    assert s14.atr is not None and s14.gap_shock is not None
    assert s14.atr_percentile is None and s14.vol_of_vol is None
    s20 = observed[20]
    assert s20.realized_vol is not None and s20.expected_holding_vol_1h is not None
    assert s20.vol_of_vol is None and s20.atr_percentile is None
    s50 = observed[50]
    assert s50.vol_of_vol is not None
    assert s50.atr_percentile is None and s50.range_expansion_percentile is None
    s100 = observed[100]
    assert s100.atr_percentile is not None
    assert s100.range_expansion_percentile is not None


def test_data_sufficient_equals_all_metrics_available() -> None:
    """عند الاكتمال: كل المقاييس غير None معًا (بيانات سليمة)."""
    candles = _synth(120)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.data_sufficient is True
    for field in (
        "atr",
        "atr_percentile",
        "realized_vol",
        "range_expansion_percentile",
        "vol_of_vol",
        "gap_shock",
        "spread_to_range",
        "expected_holding_vol_1h",
    ):
        assert getattr(state, field) is not None, field


def test_flat_market_degenerate_values_none_but_sufficient() -> None:
    """تسطّح تام: انحلال قيم (vov/gap/atr_pct جزئيًا) لا يكذب data_sufficient."""
    candles = [_candle(i, open_=100.0, high=100.0, low=100.0, close=100.0) for i in range(120)]
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.data_sufficient is True  # الدافئ البنيوي مكتمل
    assert state.atr == 0.0
    assert state.vol_of_vol is None  # حارس |mean|<eps في quantmath ⇒ nan ⇒ None
    assert state.gap_shock is None  # 0/0 ⇒ nan ⇒ None
    assert state.spread_to_range == 0.0  # عقد المدى الصفري


# ═══════════ المتأخرة والتكرار ═══════════


def test_late_candle_ignored_counted_state_unchanged() -> None:
    """المتأخرة: تُحصى، ولا تغير الحالة، وتعيد الحالة الحالية نفسها."""
    candles = _synth(30)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    before = engine.state
    stats_before = engine.stats
    late = _candle(
        0,
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        bar_time=candles[5].bar_time - timedelta(seconds=30),  # أقدم من الأخيرة وليست تكرارًا
    )
    returned = engine.update(late)
    assert returned is before  # الكائن نفسه — لا إعادة حساب أبدًا
    assert engine.state is before
    assert engine.stats.bars_consumed == stats_before.bars_consumed
    assert engine.stats.late_ignored == 1


def test_late_candle_when_no_state_returns_none() -> None:
    """متأخرة كثاني شمعة (لا حالة بعد): None مع العد — العقد لا يخفي شيئًا."""
    first = _manual_candles()[0]
    engine = VolatilityEngine()
    engine.update(first)
    older = _candle(
        0,
        open_=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        bar_time=first.bar_time - timedelta(minutes=1),
    )
    assert engine.update(older) is None
    assert engine.stats.late_ignored == 1
    assert engine.stats.bars_consumed == 1


def test_duplicate_last_bar_raises() -> None:
    """تكرار bar_time آخر مغلقة ⇒ ValueError ولا تتغير الإحصاءات."""
    candles = _synth(20)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    stats = engine.stats
    with pytest.raises(ValueError, match="تكرار bar_time"):
        engine.update(candles[-1])
    assert engine.stats == stats


def test_duplicate_retained_older_bar_raises() -> None:
    """تكرار شمعة محتجزة أقدم من الأخيرة ⇒ ValueError أيضًا (التكرار يسبق التأخر)."""
    candles = _synth(20)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    with pytest.raises(ValueError, match="تكرار bar_time"):
        engine.update(candles[3])  # ما تزال ضمن المخزن (history_bars=114)


def test_duplicate_beyond_buffer_counted_late() -> None:
    """تكرار أقدم من المخزن المحتجز ⇒ متأخرة محصاة (قيد الذاكرة الموثق)."""
    cfg = VolatilityConfig(
        atr_period=2, pct_window=3, rv_window=2, vov_window=2, range_window=3, holding_horizons=(4,)
    )
    assert cfg.history_bars == 5
    candles = _synth(10)
    engine = VolatilityEngine(config=cfg)
    for candle in candles:
        engine.update(candle)
    evicted = candles[0]  # خارج المخزن (طوله 5)
    stats = engine.stats
    returned = engine.update(evicted)
    assert returned is engine.state  # متأخرة: تُحصى وتبقى الحالة
    assert engine.stats.late_ignored == stats.late_ignored + 1
    assert engine.stats.bars_consumed == stats.bars_consumed


# ═══════════ العتبات التطبيعية (§16 — حرج) ═══════════


def test_threshold_none_before_warmup_for_all_keys() -> None:
    """قبل اكتمال دافئ ATR ⇒ كل العتبات None — لا قيمة افتراضية مزيفة."""
    candles = _synth(3)
    engine = VolatilityEngine()
    for candle in candles:
        state = engine.update(candle)
    assert state is not None
    assert state.atr is None
    for key in ThresholdKey:
        assert state.threshold(key) is None


def test_threshold_is_exactly_atr_times_multiplier_all_keys() -> None:
    """كل مفتاح: threshold == atr × المضاعف بالضبط — لا مسار آخر."""
    candles = _synth(150)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.atr is not None
    for key in ThresholdKey:
        assert state.threshold(key) == state.atr * DEFAULT_MULTIPLIERS[key]


def test_threshold_linear_in_atr_scaling() -> None:
    """مضاعفة الأسعار تضاعف ATR والعتبات — لا حد أدنى مطلق في أي مسار (×10 كذلك)."""
    base = _synth(150)
    doubled = _synth(150, scale=2.0)
    tenfold = _synth(150, scale=10.0)

    def _final_atr(candles: list[Candle]) -> float:
        engine = VolatilityEngine()
        for candle in candles:
            engine.update(candle)
        state = engine.state
        assert state is not None and state.atr is not None
        return state.atr

    atr1, atr2, atr10 = _final_atr(base), _final_atr(doubled), _final_atr(tenfold)
    assert atr2 == pytest.approx(2.0 * atr1, rel=1e-9)
    assert atr10 == pytest.approx(10.0 * atr1, rel=1e-9)

    engine = VolatilityEngine()
    for candle in doubled:
        engine.update(candle)
    state2 = engine.state
    assert state2 is not None
    for key in ThresholdKey:
        base_threshold = atr1 * DEFAULT_MULTIPLIERS[key]
        assert state2.threshold(key) == pytest.approx(2.0 * base_threshold, rel=1e-9)


def test_threshold_overrides_win_and_validate() -> None:
    """التجاوز يفوز لكل المفتاح؛ والقيم غير المحدودة/غير الموجبة ترفض دائمًا."""
    candles = _synth(150)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.atr is not None
    key = ThresholdKey.DISPLACEMENT_MIN
    assert state.threshold(key, {key: 0.5}) == state.atr * 0.5
    # تجاوز مفتاح آخر لا يمس مفتاحنا
    other = ThresholdKey.SWEEP_TOLERANCE
    assert state.threshold(key, {other: 9.0}) == state.atr * DEFAULT_MULTIPLIERS[key]
    with pytest.raises(ValueError, match="معامل تجاوز غير صالح"):
        state.threshold(key, {key: -1.0})
    with pytest.raises(ValueError, match="معامل تجاوز غير صالح"):
        state.threshold(key, {key: 0.0})
    with pytest.raises(ValueError, match="معامل تجاوز غير صالح"):
        state.threshold(key, {key: float("nan")})


def test_threshold_unknown_key_raises() -> None:
    """مفتاح غير معروف ⇒ ValueError تسرد المفاتيح الموثقة."""
    candles = _synth(150)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    with pytest.raises(ValueError, match="مفتاح عتبة غير معروف") as exc_info:
        state.threshold("NOT_A_THRESHOLD")  # type: ignore[arg-type]
    assert "STRUCTURAL_LEVEL_BUFFER" in str(exc_info.value)


def test_threshold_override_validated_even_before_warmup() -> None:
    """العقد صاخب دائمًا: تجاوز فاسد يرفض حتى قبل اكتمال الدافئ."""
    candles = _synth(3)
    engine = VolatilityEngine()
    for candle in candles:
        state = engine.update(candle)
    assert state is not None
    with pytest.raises(ValueError, match="معامل تجاوز غير صالح"):
        state.threshold(ThresholdKey.DISPLACEMENT_MIN, {ThresholdKey.DISPLACEMENT_MIN: -3.0})


# ═══════════ الحتمية والتقارب ═══════════


def test_determinism_two_engines_identical_states() -> None:
    """نفس السلسلة مرتين ⇒ كل الحالات متطابقة تمامًا (بعتباتها)."""
    candles = _synth(150)
    runs: list[list[VolatilityState | None]] = []
    for _ in range(2):
        engine = VolatilityEngine()
        runs.append([engine.update(candle) for candle in candles])
    assert runs[0] == runs[1]
    # العتبات جزء من التطابق
    for a, b in zip(runs[0], runs[1], strict=True):
        if a is not None and b is not None:
            for key in ThresholdKey:
                assert a.threshold(key) == b.threshold(key)


def test_engine_converges_from_cold_start() -> None:
    """محرك بدأ لاحقًا يتطابق مع الحي بعد history_bars شمعة (ذاكرة محدودة موثقة)."""
    cfg = _TINY
    candles = _synth(30)
    full = VolatilityEngine(config=cfg)
    full_states = [full.update(c) for c in candles]
    late_start = VolatilityEngine(config=cfg)
    late_states = [late_start.update(c) for c in candles[cfg.history_bars :]]
    # late_states[i] يقابل الشمعة candles[history_bars + i]
    for i, late_state in enumerate(late_states):
        bar_index = cfg.history_bars + i
        if bar_index < 2 * cfg.history_bars - 1:
            continue  # قبل امتلاء مخزن المتأخر
        assert late_state == full_states[bar_index]


# ═══════════ الإعداد: التحقق والدمج ═══════════


@pytest.mark.parametrize(
    "kwargs",
    [
        {"atr_period": 0},
        {"pct_window": 1},
        {"rv_window": 1},
        {"vov_window": 1},
        {"range_window": 1},
        {"holding_horizons": (0,)},
        {"holding_horizons": (60, -3)},
        {"multipliers": {ThresholdKey.DISPLACEMENT_MIN: -1.0}},
        {"multipliers": {ThresholdKey.DISPLACEMENT_MIN: 0.0}},
        {"multipliers": {ThresholdKey.DISPLACEMENT_MIN: float("inf")}},
    ],
    ids=[
        "atr0",
        "pct1",
        "rv1",
        "vov1",
        "range1",
        "horizon0",
        "horizon-negative",
        "mult-negative",
        "mult-zero",
        "mult-inf",
    ],
)
def test_config_validation_rejects(kwargs: dict[str, object]) -> None:
    """كل قيمة إعداد فاسدة ترفض بValueError عند البناء — لا إعداد نصف شرعي."""
    with pytest.raises(ValueError):
        VolatilityConfig(**kwargs)  # type: ignore[arg-type]


def test_config_multipliers_merge_over_defaults() -> None:
    """دمج جزئي: التجاوز يفوز والبقية تبقى من الافتراضات المكتملة."""
    cfg = VolatilityConfig(multipliers={ThresholdKey.DISPLACEMENT_MIN: 2.5})
    assert cfg.multipliers[ThresholdKey.DISPLACEMENT_MIN] == 2.5
    assert (
        cfg.multipliers[ThresholdKey.SWEEP_TOLERANCE]
        == DEFAULT_MULTIPLIERS[ThresholdKey.SWEEP_TOLERANCE]
    )
    assert set(cfg.multipliers) == set(ThresholdKey)


def test_config_multipliers_snapshot_used_by_state() -> None:
    """الحالة تحمل لقطة معاملات الإعداد — العتبة مكتفية ذاتيًا بعد النشر."""
    candles = _synth(150)
    cfg = VolatilityConfig(multipliers={ThresholdKey.ZONE_PROXIMITY: 4.0})
    engine = VolatilityEngine(config=cfg)
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.threshold(ThresholdKey.ZONE_PROXIMITY) == pytest.approx(4.0 * (state.atr or 0.0))


def test_config_frozen() -> None:
    """الإعداد مجمد — الإسناد يرفض."""
    cfg = VolatilityConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.atr_period = 5  # type: ignore[misc]


def test_default_multipliers_cover_all_keys_and_immutable() -> None:
    """الافتراضيات: تغطي كل المفاتيح، موجبة محدودة، وخريطة محفوظة."""
    assert set(DEFAULT_MULTIPLIERS) == set(ThresholdKey)
    for value in DEFAULT_MULTIPLIERS.values():
        assert math.isfinite(value) and value > 0.0
    with pytest.raises(TypeError):
        DEFAULT_MULTIPLIERS[ThresholdKey.DISPLACEMENT_MIN] = 99.0  # type: ignore[index]


def test_config_warmup_history_properties_documented() -> None:
    """صيغتا warmup_bars وhistory_bars مقفلتان على الافتراضي والمصغر."""
    default_cfg = VolatilityConfig()
    assert default_cfg.warmup_bars == 100
    assert default_cfg.history_bars == 114
    assert _TINY.warmup_bars == 4
    assert _TINY.history_bars == 5


def test_state_frozen() -> None:
    """الحالة مجمدة — لا تعديل بعد الإنتاج (روح §27)."""
    candles = _synth(10)
    engine = VolatilityEngine(config=_TINY)
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    with pytest.raises(FrozenInstanceError):
        state.atr = 123.0  # type: ignore[misc]


def test_expected_holding_vol_horizons_mapping() -> None:
    """آفاق متعددة: القاموس يغطيها كلها و_1h هو أفق 60 تحديدًا."""
    cfg = VolatilityConfig(holding_horizons=(10, 60))
    candles = _synth(120)
    engine = VolatilityEngine(config=cfg)
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert set(state.expected_holding_vol) == {10, 60}
    assert state.expected_holding_vol_1h == state.expected_holding_vol[60]
    window = candles[-cfg.history_bars :]
    for horizon in (10, 60):
        expected = float(expected_holding_vol_series(window, horizon, cfg.rv_window)[-1])
        assert state.expected_holding_vol[horizon] == expected


def test_expected_holding_vol_1h_none_when_60_not_configured() -> None:
    """بلا أفق 60 في الإعداد ⇒ _1h = None حتى بعد الدافئ، والبقية تعمل."""
    candles = _synth(120)
    engine = VolatilityEngine(config=VolatilityConfig(holding_horizons=(30,)))
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    assert state.expected_holding_vol_1h is None
    assert state.expected_holding_vol[30] is not None


# ═══════════ لقطة §32 ═══════════


def test_summary_keys_and_values_match_state() -> None:
    """التسطيح: ثمانية مفاتيح مسطحة بقيم الحالة كما هي (بما فيها None)."""
    candles = _synth(150)
    engine = VolatilityEngine()
    for candle in candles:
        engine.update(candle)
    state = engine.state
    assert state is not None
    summary = compute_market_volatility_summary(state)
    assert set(summary) == {
        "atr",
        "atr_percentile",
        "realized_vol",
        "range_expansion_percentile",
        "vol_of_vol",
        "gap_shock",
        "spread_to_range",
        "expected_holding_vol_1h",
    }
    assert all(summary[key] == getattr(state, key) for key in summary)


def test_summary_before_warmup_all_none() -> None:
    """قبل الدافئ: كل قيم اللقطة None — لا اختلاق أرقام للبث."""
    candles = _synth(2)
    engine = VolatilityEngine()
    for candle in candles:
        state = engine.update(candle)
    assert state is not None
    summary = compute_market_volatility_summary(state)
    assert set(summary) >= {"atr", "atr_percentile", "vol_of_vol"}
    assert summary["atr"] is None
    assert summary["atr_percentile"] is None
    assert summary["vol_of_vol"] is None
