"""اختبارات محرك انحياز HTF (§9.2) — المهمة 2-d: الوكيل المرحلي وبوابة التأكيد.

يُقفل بمسارات معروفة بقيم HtfBiasInputs مصنوعة يدويًا: الاتجاهان تحت
العتبتين وخارجهما، NEUTRAL تحت العتبة، التذبذب المتكرر ⇒ TRANSITION
(وتعافيه الاتجاهي)، الدافئ UNKNOWN، أي None ⇒ UNKNOWN لهذا التحديث مع
حفظ الانحياز الداخلي، الحتمية بايت-بايت، ولا-نظرة-مستقبلية، وتدقيق
العتبات النسبية (فحص وقائي يرفض الثوابت السعرية).
"""

from __future__ import annotations

from typing import Any

import pytest
from market_state import htf_bias as htf_module
from market_state.htf_bias import (
    HtfBiasConfig,
    HtfBiasEngine,
    HtfBiasInputs,
    HtfBiasState,
)
from schemas import HTFBias

# ── عدة الاختبار ──

_BASE: dict[str, Any] = {
    "eff": 0.6,
    "sign": 1,
    "nrange": 1.2,
    "atr_pct": 0.5,
    "displacement": 0.4,
}


def _inp(**overrides: Any) -> HtfBiasInputs:
    """بناء HtfBiasInputs بقيم نقية معلومة — تجاوز أي حقل (أو None له)."""
    v = {**_BASE, **overrides}
    return HtfBiasInputs(
        directional_efficiency=v["eff"],
        efficiency_sign=v["sign"],
        normalized_range=v["nrange"],
        atr_percentile=v["atr_pct"],
        displacement_proxy=v["displacement"],
    )


def _run(seq: list[HtfBiasInputs], config: HtfBiasConfig) -> list[HtfBiasState]:
    """تشغيل محرك نظيف على تسلسل وإرجاع تتابع الحالات كاملًا."""
    engine = HtfBiasEngine(config)
    return [engine.update(inputs) for inputs in seq]


#: إعداد مختبري: قراءات من الشمعة الأولى (confirm=5 وflips=2 كالافتراضي).
_CFG = HtfBiasConfig(warmup_bars=1)

_BEAR = {"sign": -1}  # eff=0.6 هابطًا
_NEUTRAL = {"eff": 0.2}  # تحت العتبتين صاعدًا


def _alternating(bars: int) -> list[HtfBiasInputs]:
    """تذبذب خام متناوب يبدأ صاعدًا — BULL, BEAR, BULL, ..."""
    return [_inp() if i % 2 == 0 else _inp(**_BEAR) for i in range(bars)]


def _mixed_sequence() -> list[HtfBiasInputs]:
    """تسلسل متنوع (التزامات + انعكاس + None + تذبذب + تعافٍ) للخصائص."""
    seq: list[HtfBiasInputs] = []
    seq.extend([_inp()] * 5)  # BULLISH يثبت في الخامسة
    seq.extend([_inp(**_BEAR)] * 2)  # انعكاس معلق واحد (لا تذبذب بعد)
    seq.append(_inp(eff=None))  # None — UNKNOWN لهذا التحديث
    seq.extend(_alternating(6))  # تذبذب متكرر ⇒ قراءات TRANSITION
    seq.extend([_inp()] * 7)  # تعافٍ اتجاهي ⇒ BULLISH يثبت
    seq.extend([_inp(**_NEUTRAL)] * 6)  # NEUTRAL يثبت في الخامسة
    seq.append(_inp(sign=None))  # None أخرى
    return seq


# ═══════════════════════ الإعداد: القيم والعتبات ═══════════════════════


def test_config_defaults() -> None:
    cfg = HtfBiasConfig()
    assert cfg.efficiency_bull == 0.45
    assert cfg.efficiency_bear == 0.45
    assert cfg.confirm_bars == 5
    assert cfg.warmup_bars == 20
    assert cfg.transition_flips == 2  # الحقل الإضافي الموثق


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("efficiency_bull", 0.0),
        ("efficiency_bull", 1.0),
        ("efficiency_bull", float("nan")),
        ("efficiency_bear", 0.0),
        ("efficiency_bear", 1.5),
        ("confirm_bars", 0),
        ("warmup_bars", -1),
        ("transition_flips", 0),
    ],
)
def test_config_rejects_invalid_values(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        HtfBiasConfig(**{field: value})


def test_default_thresholds_are_relative_not_price() -> None:
    """فحص وقائي موثق: الكفاءات نسب صرفة — يقبض على الثوابت السعرية الشائعة."""
    cfg = HtfBiasConfig()
    for value in (cfg.efficiency_bull, cfg.efficiency_bear):
        assert 0.0 < value < 1.0
        assert value < 10.0


# ═══════════════════════ المدخلات: العقود ═══════════════════════


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eff", 1.5),
        ("eff", -0.01),
        ("eff", float("nan")),
        ("sign", 2),
        ("sign", -2),
        ("sign", 0.5),
        ("atr_pct", 1.1),
        ("displacement", 1.2),
        ("displacement", -0.1),
        ("nrange", -1.0),
    ],
)
def test_inputs_reject_out_of_domain(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        _inp(**{field: value})


def test_inputs_accept_boundaries_and_none() -> None:
    _inp(eff=0.0, atr_pct=0.0, displacement=0.0, nrange=0.0)
    _inp(eff=1.0, atr_pct=1.0, displacement=1.0)
    _inp(sign=-1)
    _inp(sign=0)
    _inp(eff=None, sign=None, nrange=None, atr_pct=None, displacement=None)
    _inp(nrange=4.7)  # المدى قد يبلغ عدة ATR — بلا سقف موثق


# ═══════════════════════ الدافئ والحالة الابتدائية ═══════════════════════


def test_initial_state_before_any_update() -> None:
    engine = HtfBiasEngine()
    assert engine.state == HtfBiasState()
    assert engine.state.bias is HTFBias.UNKNOWN
    assert engine.state.bars_seen == 0


def test_unknown_before_warmup() -> None:
    engine = HtfBiasEngine(HtfBiasConfig(warmup_bars=5))
    for i in range(1, 5):
        state = engine.update(_inp())
        assert state.bias is HTFBias.UNKNOWN
        assert state.data_sufficient is False
        assert state.bars_seen == i
    state = engine.update(_inp())  # أول قراءة — تعليق بلا تثبيت (confirm=5)
    assert state.data_sufficient is True
    assert state.bias is HTFBias.UNKNOWN
    assert state.pending_bias is HTFBias.BULLISH
    assert state.pending_count == 1


def test_warmup_counts_none_bars() -> None:
    """أشرطة المدخلات الناقصة تُحصى في bars_seen — الدافئ أرضية إضافية فقط."""
    engine = HtfBiasEngine(HtfBiasConfig(warmup_bars=5))
    for _ in range(4):
        assert engine.update(_inp(eff=None)).data_sufficient is False
    state = engine.update(_inp())
    assert state.bars_seen == 5
    assert state.data_sufficient is True
    assert state.pending_count == 1


# ═══════════════════════ المرشح الخام: الحالات النقية ═══════════════════════


def test_bullish_confirms_after_confirm_bars() -> None:
    states = _run([_inp()] * 5, _CFG)
    assert states[3].bias is HTFBias.UNKNOWN  # الرابعة: تعليق 4 لم يثبت
    assert states[3].pending_count == 4
    assert states[4].bias is HTFBias.BULLISH  # الخامسة المتتالية تثبت
    assert states[4].pending_bias is None


def test_bearish_confirms_after_confirm_bars() -> None:
    states = _run([_inp(**_BEAR)] * 5, _CFG)
    assert states[4].bias is HTFBias.BEARISH


def test_neutral_below_thresholds() -> None:
    states = _run([_inp(**_NEUTRAL)] * 5, _CFG)
    assert states[4].bias is HTFBias.NEUTRAL
    # إشارة معدومة مع كفاءة معدومة ⇒ NEUTRAL كذلك (لا اتجاه إطلاقًا).
    states = _run([_inp(eff=0.0, sign=0)] * 5, _CFG)
    assert states[4].bias is HTFBias.NEUTRAL


def test_proxy_fields_gate_but_do_not_sway() -> None:
    """قرار موثق: الكفاءة وإشارتها وحدهما تقودان — الوكلاء يغلقون بوابة
    الاكتمال فقط ولا يميلون المرشح في هذه النسخة."""
    hot = {"eff": 0.2, "sign": 1, "nrange": 5.0, "atr_pct": 0.99, "displacement": 0.99}
    states = _run([_inp(**hot)] * 5, _CFG)
    assert states[4].bias is HTFBias.NEUTRAL


def test_dead_zone_raw_transition_commits() -> None:
    """إشارة معدومة مع كفاءة فوق العتبة — قراءة متناقضة ⇒ TRANSITION خام."""
    states = _run([_inp(eff=0.6, sign=0)] * 5, _CFG)
    assert states[0].pending_bias is HTFBias.TRANSITION
    assert states[4].bias is HTFBias.TRANSITION  # يثبت هنا بخلاف النظام §9.3


def test_asymmetric_thresholds() -> None:
    cfg = HtfBiasConfig(warmup_bars=1, efficiency_bull=0.6, efficiency_bear=0.3)
    bear = _run([_inp(eff=0.4, sign=-1)] * 5, cfg)
    assert bear[4].bias is HTFBias.BEARISH
    # عبر عتبة الهبوط دون الصعود بإشارة صاعدة ⇒ المنطقة الرمادية TRANSITION.
    grey = _run([_inp(eff=0.4, sign=1)] * 5, cfg)
    assert grey[0].pending_bias is HTFBias.TRANSITION
    assert grey[4].bias is HTFBias.TRANSITION


# ═══════════════════════ بوابة التأكيد (hysteresis) ═══════════════════════


def test_hysteresis_single_bar_does_not_flip() -> None:
    engine = HtfBiasEngine(_CFG)
    for _ in range(5):
        engine.update(_inp())
    assert engine.state.bias is HTFBias.BULLISH
    state = engine.update(_inp(**_BEAR))
    assert state.bias is HTFBias.BULLISH  # لا رفرفة
    assert state.pending_bias is HTFBias.BEARISH
    assert state.pending_count == 1


def test_hysteresis_chain_break_resets_count() -> None:
    engine = HtfBiasEngine(_CFG)
    for _ in range(5):
        engine.update(_inp())
    engine.update(_inp(**_BEAR))
    engine.update(_inp(**_BEAR))
    assert engine.state.pending_count == 2
    engine.update(_inp(**_NEUTRAL))  # قطع السلسلة
    assert engine.state.pending_bias is HTFBias.NEUTRAL
    assert engine.state.pending_count == 1
    state = engine.update(_inp(**_BEAR))  # العد من جديد — لا ذاكرة للـ2
    assert state.pending_bias is HTFBias.BEARISH
    assert state.pending_count == 1
    assert state.bias is HTFBias.BULLISH


# ═══════════════════════ التذبذب ⇒ TRANSITION ═══════════════════════


def test_oscillation_yields_transition() -> None:
    states = _run(_alternating(10), _CFG)
    # التذبذب المتكرر يفرض قراءة TRANSITION من الانعكاس الثاني ثم يثبت
    # بخمس قراءات متتالية — هنا عند الشمعة السابعة.
    assert states[2].pending_bias is HTFBias.TRANSITION
    assert states[6].bias is HTFBias.TRANSITION
    assert states[-1].bias is HTFBias.TRANSITION


def test_oscillation_recovery_to_direction() -> None:
    engine = HtfBiasEngine(_CFG)
    for inputs in _alternating(10):
        engine.update(inputs)
    assert engine.state.bias is HTFBias.TRANSITION
    # سلسلة صاعدة متصلة تطفئ التذبذب وتثبت الاتجاه (تعافٍ موثق).
    states = [engine.update(_inp()) for _ in range(7)]
    assert states[-1].bias is HTFBias.BULLISH
    assert states[-1].pending_bias is None


# ═══════════════════════ المدخلات الناقصة (None) ═══════════════════════


@pytest.mark.parametrize("field", ["eff", "sign", "nrange", "atr_pct", "displacement"])
def test_any_none_field_yields_unknown(field: str) -> None:
    engine = HtfBiasEngine(_CFG)
    for _ in range(5):
        engine.update(_inp())
    assert engine.state.bias is HTFBias.BULLISH
    state = engine.update(_inp(**{field: None}))
    assert state.bias is HTFBias.UNKNOWN  # لهذا التحديث حصرًا
    assert state.pending_bias is None  # القراءة الغائبة تقطع السلسلة
    assert state.pending_count == 0


def test_none_bar_preserves_internal_bias() -> None:
    engine = HtfBiasEngine(_CFG)
    for _ in range(5):
        engine.update(_inp())
    engine.update(_inp(eff=None))
    assert engine.state.bias is HTFBias.UNKNOWN
    state = engine.update(_inp())  # الانحياز المؤكد لم يُنسَ
    assert state.bias is HTFBias.BULLISH
    assert state.pending_bias is None


def test_none_bar_resets_pending() -> None:
    engine = HtfBiasEngine(_CFG)
    for _ in range(3):
        engine.update(_inp())
    assert engine.state.pending_count == 3
    engine.update(_inp(eff=None))
    assert engine.state.pending_count == 0
    for _ in range(4):
        engine.update(_inp())
    assert engine.state.pending_count == 4  # العد من الصفر — لا ذاكرة للقطع
    assert engine.state.bias is HTFBias.UNKNOWN
    assert engine.update(_inp()).bias is HTFBias.BULLISH


# ═══════════════════════ الخصائص: حتمية ولا-نظرة-مستقبلية ═══════════════════════


def test_determinism_identical_state_sequences() -> None:
    """نفس التسلسل مرتين ⇒ نفس تتابع الحالات بايت-بايت (قائمتان متطابقتان)."""
    seq = _mixed_sequence()
    first = _run(seq, _CFG)
    second = _run(seq, _CFG)
    assert first == second
    assert repr(first) == repr(second)
    assert len(first) == len(seq)


@pytest.mark.parametrize("k", [3, 8, 12, 17, 23, 28])
def test_no_lookahead_prefix_invariance(k: int) -> None:
    """حالات البادئة حتى k لا تتغير بإضافة ذيل — لا كاشف يشاهد مستقبلًا."""
    seq = _mixed_sequence()
    full = _run(seq, _CFG)
    prefix = _run(seq[:k], _CFG)
    assert prefix == full[:k]


# ═══════════════════════ التوصيل والتوثيق ═══════════════════════


def test_context_not_trigger_documented() -> None:
    """§9.2 نصًا: الانحياز سياق لا مشغل — موثق في رأس الموديول والوكيل."""
    doc = htf_module.__doc__ or ""
    assert "سياق لا مشغل" in doc
    assert "does not trigger" in doc
    assert "proxy" in doc  # قيد المرحلة 2 الموثق صراحة
    inputs_doc = HtfBiasInputs.__doc__ or ""
    assert "المرحلة 3" in inputs_doc


def test_package_reexports() -> None:
    import market_state

    for name in ("HtfBiasConfig", "HtfBiasEngine", "HtfBiasInputs", "HtfBiasState"):
        assert hasattr(market_state, name)
