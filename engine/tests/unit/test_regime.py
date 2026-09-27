"""اختبارات مصنف نظام السوق (§9.3) — المهمة 2-d: الحتمية وhysteresis والبوابة.

يُقفل بمسارات معروفة بقيم RegimeFeatures مصنوعة يدويًا: كل قاعدة من جدول
القرار بحالة نقية، أولوية الصدمة القصوى، بوابة التأكيد (confirm_bars
متتالية؛ قطع السلسلة يعيد العد صفرًا)، TRANSITION المموه لا يثبت أبدًا،
UNKNOWN عند أي None وعند الدافئ، الحتمية بايت-بايت بين مصنفين،
لا-نظرة-مستقبلية (بادئة مستقلة عن الذيل)، وتدقيق العتبات النسبية
(فحص وقائي يرفض الثوابت السعرية الشائعة).
"""

from __future__ import annotations

from typing import Any

import pytest
from market_state.regime import (
    REGIME_RULES_DOC,
    RegimeClassifier,
    RegimeConfig,
    RegimeFeatures,
    RegimeState,
)
from schemas import MarketRegime

# ── عدة الاختبار ──

_BASE: dict[str, Any] = {
    "eff": 0.5,
    "nrange": 1.0,
    "atr_pct": 0.5,
    "re_pct": 0.5,
    "volc": 1.0,
    "gap": 0.5,
}


def _feat(**overrides: Any) -> RegimeFeatures:
    """بناء RegimeFeatures بقيم نقية معلومة — تجاوز أي حقل (أو None له)."""
    v = {**_BASE, **overrides}
    return RegimeFeatures(
        directional_efficiency=v["eff"],
        normalized_range=v["nrange"],
        atr_percentile=v["atr_pct"],
        range_expansion_percentile=v["re_pct"],
        volume_concentration=v["volc"],
        gap_shock=v["gap"],
    )


def _run(seq: list[RegimeFeatures], config: RegimeConfig) -> list[RegimeState]:
    """تشغيل مصنف نظيف على تسلسل وإرجاع تتابع الحالات كاملًا."""
    clf = RegimeClassifier(config)
    return [clf.update(features) for features in seq]


#: إعداد مختبري: قراءات من الشمعة الأولى (دافئ محرك التقلب يظهر كNone).
_CFG = RegimeConfig(warmup_bars=1)

# قراءات نقية معلومة لكل قاعدة من جدول القرار (بالافتراضيات الافتراضية).
_EXPANSION = {"eff": 0.7, "atr_pct": 0.6}  # قاعدة 2 عبر atr ≥ mid
_PULLBACK = {"eff": 0.7, "atr_pct": 0.4}  # قاعدة 3 (بلا أي مؤكد توسعي)
_COMPRESSION = {"eff": 0.2, "atr_pct": 0.1}  # قاعدة 4
_BALANCE = {"eff": 0.2, "atr_pct": 0.5}  # قاعدة 5
_RANGE_EXPANSION = {"eff": 0.4, "re_pct": 0.8}  # قاعدة 6 (كفاءة وسطى)
_TRANSITION = {"eff": 0.4, "re_pct": 0.5}  # قاعدة 7 (المنطقة الرمادية)
_SHOCK_ATR = {"eff": 0.5, "atr_pct": 0.98}  # قاعدة 1 عبر مئيني ATR
_SHOCK_GAP = {"eff": 0.5, "atr_pct": 0.5, "gap": 3.5}  # قاعدة 1 عبر الفجوة


def _mixed_sequence() -> list[RegimeFeatures]:
    """تسلسل متنوع (انتقالات مؤكدة + قطع + None + صدمة) للخصائص."""
    seq: list[RegimeFeatures] = []
    seq.extend([_feat(**_EXPANSION)] * 5)
    seq.extend([_feat(**_BALANCE)] * 2)
    seq.append(_feat(**_EXPANSION))
    seq.append(_feat(**_TRANSITION))
    seq.append(_feat(eff=None))
    seq.extend([_feat(**_RANGE_EXPANSION)] * 4)
    seq.extend([_feat(eff=0.9, atr_pct=0.99)] * 3)
    return seq


# ═══════════════════════ الإعداد: القيم والعتبات ═══════════════════════


def test_config_defaults() -> None:
    cfg = RegimeConfig()
    assert cfg.efficiency_trend == 0.55
    assert cfg.efficiency_range == 0.30
    assert cfg.atr_pct_high == 0.80
    assert cfg.atr_pct_low == 0.20
    assert cfg.atr_pct_shock == 0.97
    assert cfg.range_expansion_high == 0.75
    assert cfg.volume_concentration_high == 2.0
    assert cfg.gap_shock_atr == 3.0
    assert cfg.confirm_bars == 3
    assert cfg.warmup_bars == 30


def test_config_atr_pct_mid_derived() -> None:
    assert RegimeConfig().atr_pct_mid == pytest.approx(0.50)
    cfg = RegimeConfig(atr_pct_low=0.1, atr_pct_high=0.6)
    assert cfg.atr_pct_mid == pytest.approx(0.35)
    assert cfg.atr_pct_mid < cfg.atr_pct_high


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("efficiency_trend", 0.0),
        ("efficiency_trend", 1.0),
        ("efficiency_trend", float("nan")),
        ("efficiency_range", -0.1),
        ("atr_pct_high", 1.0),
        ("atr_pct_low", 0.0),
        ("atr_pct_shock", 0.0),
        ("atr_pct_shock", float("inf")),
        ("range_expansion_high", 1.0),
        ("volume_concentration_high", 0.0),
        ("volume_concentration_high", -1.0),
        ("gap_shock_atr", 0.0),
        ("confirm_bars", 0),
        ("warmup_bars", -1),
    ],
)
def test_config_rejects_invalid_values(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        RegimeConfig(**{field: value})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"efficiency_trend": 0.30, "efficiency_range": 0.30},
        {"efficiency_trend": 0.20, "efficiency_range": 0.30},
        {"atr_pct_high": 0.20, "atr_pct_low": 0.20},
        {"atr_pct_shock": 0.80, "atr_pct_high": 0.80},
    ],
)
def test_config_rejects_inconsistent_ordering(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        RegimeConfig(**kwargs)


def test_default_thresholds_are_relative_not_price() -> None:
    """فحص وقائي موثق: كل العتبات نسبية — يقبض على الثوابت السعرية الشائعة."""
    cfg = RegimeConfig()
    ratios = {
        "efficiency_trend": cfg.efficiency_trend,
        "efficiency_range": cfg.efficiency_range,
        "atr_pct_high": cfg.atr_pct_high,
        "atr_pct_low": cfg.atr_pct_low,
        "atr_pct_shock": cfg.atr_pct_shock,
        "range_expansion_high": cfg.range_expansion_high,
        "volume_concentration_high": cfg.volume_concentration_high,
        "gap_shock_atr": cfg.gap_shock_atr,
    }
    for name, value in ratios.items():
        assert 0.0 < value < 10.0, f"العتبة {name} تبدو سعرية: {value}"
    for name in (
        "efficiency_trend",
        "efficiency_range",
        "atr_pct_high",
        "atr_pct_low",
        "atr_pct_shock",
        "range_expansion_high",
    ):
        assert 0.0 < ratios[name] < 1.0


@pytest.mark.parametrize("price_like", [550.0, 25.0, 10.0, -3.0, float("nan")])
def test_config_rejects_price_like_thresholds(price_like: float) -> None:
    """قيمة على مقاس ثابت سعري (ticks/pips) تُرفض — لا عتبات مطلقة إطلاقًا."""
    with pytest.raises(ValueError):
        RegimeConfig(efficiency_trend=price_like)
    with pytest.raises(ValueError):
        RegimeConfig(atr_pct_high=price_like)


# ═══════════════════════ مدخلات السمات: العقود ═══════════════════════


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eff", 1.5),
        ("eff", -0.01),
        ("eff", float("nan")),
        ("atr_pct", 1.2),
        ("atr_pct", -0.1),
        ("re_pct", 1.1),
        ("re_pct", float("inf")),
        ("volc", -0.5),
        ("gap", -1.0),
        ("nrange", -0.5),
        ("nrange", float("nan")),
    ],
)
def test_features_reject_out_of_domain(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        _feat(**{field: value})


def test_features_accept_boundaries_and_none() -> None:
    _feat(eff=0.0, nrange=0.0, atr_pct=0.0, re_pct=0.0, volc=0.0, gap=0.0)
    _feat(eff=1.0, atr_pct=1.0, re_pct=1.0)
    _feat(eff=None, nrange=None, atr_pct=None, re_pct=None, volc=None, gap=None)
    _feat(nrange=4.7)  # المدى قد يبلغ عدة ATR — بلا سقف موثق


# ═══════════════════════ الدافئ والحالة الابتدائية ═══════════════════════


def test_initial_state_before_any_update() -> None:
    clf = RegimeClassifier()
    assert clf.state == RegimeState()
    assert clf.state.regime is MarketRegime.UNKNOWN
    assert clf.state.bars_seen == 0


def test_unknown_before_warmup() -> None:
    clf = RegimeClassifier(RegimeConfig(warmup_bars=5))
    for i in range(1, 5):
        state = clf.update(_feat(**_EXPANSION))
        assert state.regime is MarketRegime.UNKNOWN
        assert state.data_sufficient is False
        assert state.bars_seen == i
        assert state.pending_regime is None
    # الشمعة الخامسة: أول قراءة — تعليق بلا تثبيت (confirm_bars=3).
    state = clf.update(_feat(**_EXPANSION))
    assert state.data_sufficient is True
    assert state.regime is MarketRegime.UNKNOWN
    assert state.pending_regime is MarketRegime.TREND_EXPANSION
    assert state.pending_count == 1


def test_warmup_counts_missing_feature_bars() -> None:
    """أشرطة السمات الناقصة تُحصى في bars_seen — الدافئ أرضية إضافية فقط."""
    clf = RegimeClassifier(RegimeConfig(warmup_bars=5))
    for _ in range(4):
        state = clf.update(_feat(eff=None))
        assert state.data_sufficient is False
    state = clf.update(_feat(**_EXPANSION))
    assert state.bars_seen == 5
    assert state.data_sufficient is True
    assert state.pending_count == 1


# ═══════════════════════ جدول القرار: حالات نقية ═══════════════════════


def _committed_regime(overrides: dict[str, Any], bars: int = 3) -> MarketRegime:
    states = _run([_feat(**overrides)] * bars, _CFG)
    return states[-1].regime


def test_rule_shock_via_atr_percentile() -> None:
    assert _committed_regime(_SHOCK_ATR) is MarketRegime.VOLATILITY_SHOCK


def test_rule_shock_via_gap() -> None:
    assert _committed_regime(_SHOCK_GAP) is MarketRegime.VOLATILITY_SHOCK


def test_shock_has_top_priority_over_high_efficiency() -> None:
    hot = {"eff": 0.95, "nrange": 2.0, "atr_pct": 0.98, "re_pct": 0.9, "volc": 3.0, "gap": 0.2}
    assert _committed_regime(hot) is MarketRegime.VOLATILITY_SHOCK


def test_rule_trend_expansion_via_atr_mid() -> None:
    assert _committed_regime(_EXPANSION) is MarketRegime.TREND_EXPANSION


def test_rule_trend_expansion_via_range_expansion() -> None:
    assert _committed_regime({"eff": 0.7, "atr_pct": 0.4, "re_pct": 0.8}) is (
        MarketRegime.TREND_EXPANSION
    )


def test_rule_trend_expansion_via_volume_concentration() -> None:
    assert _committed_regime({"eff": 0.7, "atr_pct": 0.4, "re_pct": 0.5, "volc": 2.5}) is (
        MarketRegime.TREND_EXPANSION
    )


def test_trend_expansion_eats_high_atr_pullback_zone() -> None:
    """شرط قاعدة 3 الحرفي (atr < high) يبتلع في البقية: [mid, high) لقاعدة 2."""
    assert _committed_regime({"eff": 0.7, "atr_pct": 0.72}) is MarketRegime.TREND_EXPANSION


def test_rule_trend_pullback() -> None:
    assert _committed_regime(_PULLBACK) is MarketRegime.TREND_PULLBACK


def test_rule_compression() -> None:
    assert _committed_regime(_COMPRESSION) is MarketRegime.COMPRESSION


def test_rule_range_balance() -> None:
    assert _committed_regime(_BALANCE) is MarketRegime.RANGE_BALANCE


def test_rule_range_expansion() -> None:
    assert _committed_regime(_RANGE_EXPANSION) is MarketRegime.RANGE_EXPANSION


def test_rule_transition_zone_candidate() -> None:
    states = _run([_feat(**_TRANSITION)] * 3, _CFG)
    assert all(state.regime is MarketRegime.UNKNOWN for state in states)
    assert states[-1].pending_regime is MarketRegime.TRANSITION


def test_priority_compression_over_range_expansion() -> None:
    """كفاءة منخفضة + تقلب أرضي + توسع مدى ⇒ COMPRESSION (قاعدة 4 قبل 6)."""
    assert _committed_regime({"eff": 0.2, "atr_pct": 0.1, "re_pct": 0.95}) is (
        MarketRegime.COMPRESSION
    )


def test_priority_range_balance_over_range_expansion() -> None:
    assert _committed_regime({"eff": 0.2, "atr_pct": 0.5, "re_pct": 0.95}) is (
        MarketRegime.RANGE_BALANCE
    )


# ═══════════════════════ بوابة التأكيد (hysteresis) ═══════════════════════


def test_single_new_candidate_does_not_flip() -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    assert clf.state.regime is MarketRegime.TREND_EXPANSION
    state = clf.update(_feat(**_COMPRESSION))
    assert state.regime is MarketRegime.TREND_EXPANSION  # لا رفرفة
    assert state.pending_regime is MarketRegime.COMPRESSION
    assert state.pending_count == 1


def test_confirm_bars_consecutive_commits() -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    for expected in (1, 2):
        state = clf.update(_feat(**_COMPRESSION))
        assert state.regime is MarketRegime.TREND_EXPANSION
        assert state.pending_count == expected
    state = clf.update(_feat(**_COMPRESSION))  # الثالثة المتتالية تثبت
    assert state.regime is MarketRegime.COMPRESSION
    assert state.pending_regime is None
    assert state.transitions == 2  # التأسيس + الانتقال


def test_chain_break_resets_count() -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    clf.update(_feat(**_COMPRESSION))
    clf.update(_feat(**_COMPRESSION))
    assert clf.state.pending_count == 2
    clf.update(_feat(**_BALANCE))  # قطع السلسلة
    assert clf.state.pending_regime is MarketRegime.RANGE_BALANCE
    assert clf.state.pending_count == 1
    state = clf.update(_feat(**_COMPRESSION))  # العد بدأ من جديد — لا ذاكرة للـ2
    assert state.pending_regime is MarketRegime.COMPRESSION
    assert state.pending_count == 1
    assert state.regime is MarketRegime.TREND_EXPANSION


def test_transitions_includes_initial_establishment() -> None:
    clf = RegimeClassifier(_CFG)
    assert clf.update(_feat(**_BALANCE)).transitions == 0
    assert clf.update(_feat(**_BALANCE)).transitions == 0
    assert clf.update(_feat(**_BALANCE)).transitions == 1  # UNKNOWN → RANGE_BALANCE
    assert clf.update(_feat(**_BALANCE)).transitions == 1


# ═══════════════════════ السمات الناقصة (None) ═══════════════════════


@pytest.mark.parametrize("field", ["eff", "nrange", "atr_pct", "re_pct", "volc", "gap"])
def test_any_none_field_yields_unknown(field: str) -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    assert clf.state.regime is MarketRegime.TREND_EXPANSION
    state = clf.update(_feat(**{**_EXPANSION, field: None}))
    assert state.regime is MarketRegime.UNKNOWN  # لهذا التحديث حصرًا
    assert state.pending_regime is None  # القراءة الغائبة تقطع السلسلة
    assert state.pending_count == 0


def test_none_bar_preserves_internal_regime() -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    clf.update(_feat(eff=None))
    assert clf.state.regime is MarketRegime.UNKNOWN
    state = clf.update(_feat(**_EXPANSION))  # النظام المؤكد لم يُنسَ
    assert state.regime is MarketRegime.TREND_EXPANSION
    assert state.pending_regime is None


def test_none_bar_resets_pending() -> None:
    clf = RegimeClassifier(_CFG)
    clf.update(_feat(**_EXPANSION))
    clf.update(_feat(**_EXPANSION))
    assert clf.state.pending_count == 2
    clf.update(_feat(eff=None))
    assert clf.state.pending_count == 0
    clf.update(_feat(**_EXPANSION))
    clf.update(_feat(**_EXPANSION))
    assert clf.state.pending_count == 2  # العد من الصفر — لا ذاكرة للقطع
    assert clf.state.regime is MarketRegime.UNKNOWN
    assert clf.update(_feat(**_EXPANSION)).regime is MarketRegime.TREND_EXPANSION


# ═══════════════════════ TRANSITION المموه ═══════════════════════


def test_transition_never_commits_from_unknown() -> None:
    states = _run([_feat(**_TRANSITION)] * 10, _CFG)
    assert all(state.regime is MarketRegime.UNKNOWN for state in states)
    assert all(state.transitions == 0 for state in states)
    # العد يتراكم إخباريًا بلا سقف — والبوابة تتجاوزه عمدًا.
    assert states[-1].pending_regime is MarketRegime.TRANSITION
    assert states[-1].pending_count == 10


def test_transition_never_commits_after_established() -> None:
    clf = RegimeClassifier(_CFG)
    for _ in range(3):
        clf.update(_feat(**_EXPANSION))
    for _ in range(10):
        state = clf.update(_feat(**_TRANSITION))
        assert state.regime is MarketRegime.TREND_EXPANSION
        assert state.transitions == 1
    assert state is not None
    assert state.pending_count == 10


# ═══════════════════════ الخصائص: حتمية ولا-نظرة-مستقبلية ═══════════════════════


def test_determinism_identical_state_sequences() -> None:
    """نفس التسلسل مرتين ⇒ نفس تتابع الحالات بايت-بايت (قائمتا متطابقتان)."""
    seq = _mixed_sequence()
    first = _run(seq, _CFG)
    second = _run(seq, _CFG)
    assert first == second
    assert repr(first) == repr(second)
    assert len(first) == len(seq)


@pytest.mark.parametrize("k", [2, 4, 8, 11, 13, 16])
def test_no_lookahead_prefix_invariance(k: int) -> None:
    """حالات البادئة حتى k لا تتغير بإضافة ذيل — لا كاشف يشاهد مستقبلًا."""
    seq = _mixed_sequence()
    full = _run(seq, _CFG)
    prefix = _run(seq[:k], _CFG)
    assert prefix == full[:k]


# ═══════════════════════ التوصيل والتوثيق ═══════════════════════


def test_regime_rules_doc_documents_all_states() -> None:
    for regime in MarketRegime:
        assert regime.value in REGIME_RULES_DOC
    assert "confirm_bars" in REGIME_RULES_DOC
    assert "hysteresis" in REGIME_RULES_DOC.lower() or "confirm_bars" in REGIME_RULES_DOC


def test_package_reexports() -> None:
    import market_state

    for name in (
        "RegimeClassifier",
        "RegimeConfig",
        "RegimeFeatures",
        "RegimeState",
        "REGIME_RULES_DOC",
    ):
        assert hasattr(market_state, name)
