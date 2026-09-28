"""اختبارات الوضع البنيوي لمحرك انحياز HTF (§9.2) — المهمة 3-e (إغلاق ADR-016).

يقفل عقود التغذية البنيوية الاختيارية: انتقاء الوضع عند كل تحديث (الأربعة
المفعِّلة كاملة ⇒ بنيوي؛ جزئية/غائبة ⇒ وكيل 2-d حرفيًا)، المرشح البنيوي
بقواعده المرتبة (HH+HL/LH+LL/المختلط/الممتنع بالمساواة/غير الكافي/تناقض
الإزاحة/انكماش التهدئة/موضع النطاق)، سريان آلية التأكيد كاملة فوق المرشح
البنيوي (الدافئ/confirm_bars/التذبذب)، الحتمية ولا-النظرة-المستقبلية،
والتحقق الصاخب للحقول والإعدادات الجديدة — ووضع الوكيل محفوظ بايت-بايت.
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

#: قيم وضع الوكيل النقية — مرآة مساعد test_htf_bias.py (لا استيراد بين
#: ملفات الاختبار: المساران مستقلان عمدًا كي يثبت كلٌّ ملفَه).
_PROXY: dict[str, Any] = {
    "eff": 0.6,
    "sign": 1,
    "nrange": 1.2,
    "atr_pct": 0.5,
    "displacement": 0.4,
}

#: بنية صاعدة نقية: HH (105>100) وHL (95>90) بإزاحة صاعدة وتوسع معتدل.
_UP: dict[str, Any] = {
    "highs": (100.0, 105.0),
    "lows": (90.0, 95.0),
    "displacement_dir": 1,
    "expansion": 0.5,
}
#: بنية هابطة نقية: LH (100<105) وLL (90<95) بإزاحة هابطة.
_DOWN: dict[str, Any] = {
    "highs": (105.0, 100.0),
    "lows": (95.0, 90.0),
    "displacement_dir": -1,
    "expansion": 0.5,
}


def _proxy(**overrides: Any) -> HtfBiasInputs:
    """تغذية وكيل خالصة — الحقول البنيوية غائبة (الافتراضية None)."""
    v = {**_PROXY, **overrides}
    return HtfBiasInputs(
        directional_efficiency=v["eff"],
        efficiency_sign=v["sign"],
        normalized_range=v["nrange"],
        atr_percentile=v["atr_pct"],
        displacement_proxy=v["displacement"],
    )


def _struct_fields(base: dict[str, Any]) -> dict[str, Any]:
    """خريطة مفاتيح البناء البسيطة إلى حقول HtfBiasInputs البنيوية."""
    return {
        "external_high_sequence": base["highs"],
        "external_low_sequence": base["lows"],
        "htf_displacement_direction": base["displacement_dir"],
        "expansion_state": base["expansion"],
        "dealing_range": base.get("range"),
        "close_price": base.get("close"),
    }


def _struct(**overrides: Any) -> HtfBiasInputs:
    """تغذية بنيوية كاملة (النمط مفعّل) — تجاوز أي حقل بقيمة أو None."""
    v = {**_UP, **overrides}
    return HtfBiasInputs(
        directional_efficiency=None,
        efficiency_sign=None,
        normalized_range=None,
        atr_percentile=None,
        displacement_proxy=None,
        **_struct_fields(v),
    )


def _merged(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """دمج قاعدة بنيوية مع تجاوزات (يفادي ازدواج مفاتيح ** المتكررة)."""
    return {**base, **overrides}


def _run(seq: list[HtfBiasInputs], config: HtfBiasConfig) -> list[HtfBiasState]:
    """تشغيل محرك نظيف على تسلسل وإرجاع تتابع الحالات كاملًا."""
    engine = HtfBiasEngine(config)
    return [engine.update(inputs) for inputs in seq]


#: إعداد مختبري: قراءة فورية من الشمعة الأولى (التأكيد = 1).
_FAST = HtfBiasConfig(warmup_bars=1, confirm_bars=1)


def _bias(inputs: HtfBiasInputs, config: HtfBiasConfig = _FAST) -> HTFBias:
    """انحياز محرك نظيف من شمعة واحدة (confirm=1: الخام يثبت فورًا)."""
    return HtfBiasEngine(config).update(inputs).bias


# ═══════════════════════ انتقاء الوضع (ADR-016) ═══════════════════════


def test_structural_fields_default_none() -> None:
    """التوافق الخلفي البنيوي: الباني بحقول الوكيل الخمسة وحدها يبقى
    قانونيًا وكل الحقول البنيوية None (النمط وكيلًا)."""
    inputs = HtfBiasInputs(
        directional_efficiency=0.6,
        efficiency_sign=1,
        normalized_range=1.2,
        atr_percentile=0.5,
        displacement_proxy=0.4,
    )
    assert inputs.external_high_sequence is None
    assert inputs.external_low_sequence is None
    assert inputs.htf_displacement_direction is None
    assert inputs.expansion_state is None
    assert inputs.dealing_range is None
    assert inputs.close_price is None


def test_proxy_mode_known_outcomes_unchanged() -> None:
    """توافق خلفي مقفول: مدخلات الوكيل وحدها تنتج تتابع 2-d نفسه حرفيًا
    (BULLISH يثبت في الخامسة بـconfirm=5 الافتراضي — مرآة اختبار 2-d)."""
    states = _run([_proxy()] * 5, HtfBiasConfig(warmup_bars=1))
    assert states[3].bias is HTFBias.UNKNOWN
    assert states[3].pending_count == 4
    assert states[4].bias is HTFBias.BULLISH


@pytest.mark.parametrize(
    "drop_field",
    [
        "external_high_sequence",
        "external_low_sequence",
        "htf_displacement_direction",
        "expansion_state",
    ],
)
def test_partial_structural_fields_stay_proxy_mode(drop_field: str) -> None:
    """أولوية موثقة: النمط الكامل أو الوكيل — لا وضع هجين. غياب أي من
    الأربعة المفعِّلة يُبقي وضع الوكيل: قراءة الوكيل تنتصر حتى لو مالت
    البقايا البنيوية عكسها، والبقايا الصاعدة لا ترفع وكيلًا محايدًا."""
    down_fields = _struct_fields(_DOWN)
    down_fields[drop_field] = None
    bull_proxy = HtfBiasInputs(
        directional_efficiency=0.6,
        efficiency_sign=1,
        normalized_range=1.2,
        atr_percentile=0.5,
        displacement_proxy=0.4,
        **down_fields,
    )
    assert _bias(bull_proxy) is HTFBias.BULLISH
    up_fields = _struct_fields(_UP)
    up_fields[drop_field] = None
    neutral_proxy = HtfBiasInputs(
        directional_efficiency=0.2,
        efficiency_sign=1,
        normalized_range=1.2,
        atr_percentile=0.5,
        displacement_proxy=0.4,
        **up_fields,
    )
    assert _bias(neutral_proxy) is HTFBias.NEUTRAL


def test_full_structural_set_activates_structural_mode() -> None:
    """اكتمال الأربعة ⇒ بنيوي: قراءة البنية تنتصر على قراءة الوكيل
    المخالفة، وتستقل عن حقول الوكيل كليًا (حتى لو كانت كلها None)."""
    bear_proxy_up_structure = HtfBiasInputs(
        directional_efficiency=0.6,
        efficiency_sign=-1,
        normalized_range=1.2,
        atr_percentile=0.5,
        displacement_proxy=0.4,
        **_struct_fields(_UP),
    )
    assert _bias(bear_proxy_up_structure) is HTFBias.BULLISH
    assert _bias(_struct()) is HTFBias.BULLISH  # حقول الوكيل كلها None


def test_mode_selection_per_update_switching() -> None:
    """الانتقاء لكل تحديث لا للمحرك: بنيوي ← وكيل ← بنيوي — القراءة تتبع
    مصدرها عند كل شمعة (confirm=1 يجعل التبديل فوريًا في الاتجاهين)."""
    engine = HtfBiasEngine(_FAST)
    assert engine.update(_struct()).bias is HTFBias.BULLISH  # بنيوي صاعد
    assert engine.update(_proxy(sign=-1)).bias is HTFBias.BEARISH  # وكيل هابط
    assert engine.update(_struct()).bias is HTFBias.BULLISH  # بنيوي من جديد


def test_zero_valued_structural_fields_are_present() -> None:
    """الصفر قيمة حاضرة لا غياب: الانتقاء بـ«is not None» لا بالصدق —
    إزاحة معدومة حاضرة لا تناقض، وتوسع أرضي حاضر هو انكماش تام يهدّئ."""
    assert _bias(_struct(displacement_dir=0)) is HTFBias.BULLISH  # لا إزاحة بعد
    assert _bias(_struct(expansion=0.0)) is HTFBias.NEUTRAL  # انكماش تام


# ═══════════════════════ المرشح البنيوي: الحالات النقية ═══════════════════════


def test_hh_hl_yields_bullish() -> None:
    """بنية خارجية صاعدة (HH+HL) بإزاحة موافقة وتوسع معتدل ⇒ BULLISH خام."""
    assert _bias(_struct()) is HTFBias.BULLISH


def test_lh_ll_yields_bearish() -> None:
    """بنية خارجية هابطة (LH+LL) بإزاحة موافقة وتوسع معتدل ⇒ BEARISH خام."""
    assert _bias(_struct(**_DOWN)) is HTFBias.BEARISH


@pytest.mark.parametrize(
    ("highs", "lows"),
    [
        ((100.0, 105.0), (95.0, 90.0)),  # HH + LL
        ((105.0, 100.0), (90.0, 95.0)),  # LH + HL
    ],
)
def test_mixed_structure_yields_neutral(
    highs: tuple[float, ...],
    lows: tuple[float, ...],
) -> None:
    """تسمية متعاكسة (HH+LL أو LH+HL) ⇒ بنية غير موجّهة ⇒ NEUTRAL خام."""
    state = HtfBiasEngine(_FAST).update(_struct(highs=highs, lows=lows, displacement_dir=0))
    assert state.bias is HTFBias.NEUTRAL


@pytest.mark.parametrize(
    ("highs", "lows"),
    [
        ((100.0, 100.0), (90.0, 95.0)),  # قمة متساوية مع HL
        ((100.0, 105.0), (90.0, 90.0)),  # قاع متساوٍ مع HH
        ((100.0, 100.0), (90.0, 90.0)),  # تساوٍ مزدوج
        ((105.0, 105.0), (95.0, 90.0)),  # قمة متساوية مع LL — لا ترقّي ولا تحطيط
    ],
)
def test_equal_values_withhold_label(
    highs: tuple[float, ...],
    lows: tuple[float, ...],
) -> None:
    """تسمية صارمة بالمساواة لا ترقّي: التساوي يمتنع عن التسمية (لا HH/HL
    ولا LH/LL) فأي جانب متساوٍ يجعل البنية غير موجّهة ⇒ NEUTRAL — حتى مع
    LL في الجانب الآخر (لا تنقلب هبوطًا بتساوٍ)."""
    state = HtfBiasEngine(_FAST).update(_struct(highs=highs, lows=lows, displacement_dir=0))
    assert state.bias is HTFBias.NEUTRAL


@pytest.mark.parametrize(
    ("highs", "lows"),
    [
        ((), (90.0, 95.0)),  # لا قمم إطلاقًا
        ((100.0,), (90.0, 95.0)),  # قمة واحدة
        ((100.0, 105.0), ()),  # لا قيعان
        ((100.0, 105.0), (90.0,)),  # قاع واحد
    ],
)
def test_insufficient_sequences_yield_unknown_this_update(
    highs: tuple[float, ...],
    lows: tuple[float, ...],
) -> None:
    """أقل من اثنين من أي جانب ⇒ UNKNOWN لهذا التحديث حصرًا مع حفظ
    الانحياز المؤكد داخليًا وقطع سلسلة التأكيد (عقد النقص نفسه)."""
    engine = HtfBiasEngine(_FAST)
    assert engine.update(_struct()).bias is HTFBias.BULLISH  # تأسيس
    state = engine.update(_struct(highs=highs, lows=lows))
    assert state.bias is HTFBias.UNKNOWN
    assert state.pending_bias is None
    assert state.pending_count == 0
    # الانحياز الداخلي محفوظ — القراءة الكاملة التالية تعيده فورًا (confirm=1).
    assert engine.update(_struct()).bias is HTFBias.BULLISH


# ═══════════════════════ الانكماش (expansion_state) ═══════════════════════


def test_contraction_dampens_to_neutral() -> None:
    """expansion تحت العتبة (0.2 < 0.3) مع HH+HL ⇒ بنية غير موسّعة لا
    تحسم اتجاهًا ⇒ NEUTRAL خام (إعدادي موثق)."""
    assert _bias(_struct(expansion=0.2)) is HTFBias.NEUTRAL


def test_contraction_threshold_is_strict() -> None:
    """العتبة حصرية الدنيا: المساواة بها (0.3) ليست انكماشًا — القراءة
    الاتجاهية تبقى في الاتجاهين."""
    assert _bias(_struct(expansion=0.3)) is HTFBias.BULLISH
    assert _bias(_struct(**_merged(_DOWN, expansion=0.3))) is HTFBias.BEARISH


def test_contraction_threshold_calibratable() -> None:
    """الإعداد إعدادي قابل للمعايرة: رفع العتبة إلى 0.6 يوسّع منطقة
    التهدئة فتبلغ توسعًا معتدلًا (0.5)."""
    cfg = HtfBiasConfig(warmup_bars=1, confirm_bars=1, contraction_threshold=0.6)
    assert _bias(_struct(expansion=0.5), cfg) is HTFBias.NEUTRAL


def test_extreme_expansion_adds_nothing() -> None:
    """التوسع المتطرف (فوق 0.9) لا يضيف شيئًا عمدًا — يبقي القراءة كما
    هي (لا مكافأة توسع: انحياز HTF سياق لا يستعجل)."""
    assert _bias(_struct(expansion=0.95)) is HTFBias.BULLISH
    assert _bias(_struct(**_merged(_DOWN, expansion=1.0))) is HTFBias.BEARISH


# ═══════════════════════ تناقض الإزاحة (htf_displacement_direction) ═══════════════════════


def test_displacement_contradiction_yields_transition() -> None:
    """بنية موجّهة تقابلها إزاحة HTF مؤكدة معاكسة ⇒ TRANSITION خام (نظير
    المنطقة الرمادية في وضع الوكيل) — وبالمرآة للاتجاهين."""
    assert _bias(_struct(displacement_dir=-1)) is HTFBias.TRANSITION
    assert _bias(_struct(**_merged(_DOWN, displacement_dir=1))) is HTFBias.TRANSITION


def test_displacement_same_or_absent_keeps_reading() -> None:
    """الإزاحة الموافقة أو الغياب المعلن (0) لا يغيران شيئًا — القراءة
    البنيوية تبقى كما هي."""
    assert _bias(_struct(displacement_dir=1)) is HTFBias.BULLISH
    assert _bias(_struct(displacement_dir=0)) is HTFBias.BULLISH
    assert _bias(_struct(**_DOWN)) is HTFBias.BEARISH


def test_contradiction_outranks_dampening_and_location() -> None:
    """أولوية موثقة: التناقض المؤكد (TRANSITION) يعلو التهدئة الانكماشية
    ومخالفة الموضع (كلتاهما NEUTRAL) — تعارض ملموس بين دعويتين بنيويتين
    أبلغ من إنكار إعدادي أو مخالفة موقع."""
    state = HtfBiasEngine(_FAST).update(
        _struct(displacement_dir=-1, expansion=0.2, range=(100.0, 200.0), close=120.0)
    )
    assert state.bias is HTFBias.TRANSITION


def test_neutral_structure_ignores_displacement() -> None:
    """البنية غير الموجّهة لا تدّعي اتجاهًا فلا تناقِض الإزاحة أصلًا —
    حتى لو كانت الإزاحة حادة الاتجاه."""
    state = HtfBiasEngine(_FAST).update(
        _struct(highs=(100.0, 105.0), lows=(95.0, 90.0), displacement_dir=-1)
    )
    assert state.bias is HTFBias.NEUTRAL


# ═══════════════════════ موضع النطاق (dealing_range + close_price) ═══════════════════════


def test_range_position_downgrades_not_upgrades() -> None:
    """الموقع يخفّض القراءة الاتجاهية ولا يرقّيها أبدًا: بنية صاعدة
    والإغلاق في قاع النطاق ⇒ NEUTRAL (الموقع يناقض)، وفي قمته ⇒ تبقى
    BULLISH — وبالمرآة للهبوط."""
    assert _bias(_struct(range=(100.0, 200.0), close=120.0)) is HTFBias.NEUTRAL
    assert _bias(_struct(range=(100.0, 200.0), close=180.0)) is HTFBias.BULLISH
    down_bottom = _struct(**_merged(_DOWN, range=(100.0, 200.0), close=120.0))
    assert _bias(down_bottom) is HTFBias.BEARISH
    down_top = _struct(**_merged(_DOWN, range=(100.0, 200.0), close=180.0))
    assert _bias(down_top) is HTFBias.NEUTRAL


def test_range_midpoint_never_contradicts() -> None:
    """منتصف النطاق (position = 0.5) دليل محايد بحكم التعريف — لا يناقض
    بنية صاعدة ولا هابطة (المقارنات حصرية الدنيا والعليا)."""
    assert _bias(_struct(range=(100.0, 200.0), close=150.0)) is HTFBias.BULLISH
    mid_down = _struct(**_merged(_DOWN, range=(100.0, 200.0), close=150.0))
    assert _bias(mid_down) is HTFBias.BEARISH


def test_close_outside_range_lands_in_contradiction_zone() -> None:
    """الإغلاق خارج النطاق يقع في منطقة التناقض تلقائيًا بلا قصّ: فوق
    القمة يؤكد صعودًا ويناقض هبوطًا، وتحت القاع بالعكس."""
    assert _bias(_struct(range=(100.0, 200.0), close=250.0)) is HTFBias.BULLISH
    above_down = _struct(**_merged(_DOWN, range=(100.0, 200.0), close=250.0))
    assert _bias(above_down) is HTFBias.NEUTRAL
    assert _bias(_struct(range=(100.0, 200.0), close=50.0)) is HTFBias.NEUTRAL
    below_down = _struct(**_merged(_DOWN, range=(100.0, 200.0), close=50.0))
    assert _bias(below_down) is HTFBias.BEARISH


def test_degenerate_range_voids_location_evidence() -> None:
    """النطاق المنحل (low == high) جائز في التحقق (low ≤ high) لكنه بلا
    موضع أصلًا — دليل الموضع غائب يُتجاهل والقراءة البنيوية تبقى."""
    assert _bias(_struct(range=(150.0, 150.0), close=150.0)) is HTFBias.BULLISH
    assert _bias(_struct(range=(150.0, 150.0), close=99999.0)) is HTFBias.BULLISH
    degenerate_down = _struct(**_merged(_DOWN, range=(150.0, 150.0), close=150.0))
    assert _bias(degenerate_down) is HTFBias.BEARISH


def test_location_needs_both_range_and_close() -> None:
    """دليل الموضع يلزمه النطاق والإغلاق معًا — أحدهما وحده يُتجاهل
    كليًا (لا يطبّق النطاق بنصف أدواته)."""
    assert _bias(_struct(range=(100.0, 200.0))) is HTFBias.BULLISH  # بلا إغلاق
    assert _bias(_struct(close=120.0)) is HTFBias.BULLISH  # بلا نطاق


def test_range_position_split_calibratable() -> None:
    """الشطر إعدادي قابل للمعايرة: تقليصه إلى 0.25 يجعل [0.25, 0.75]
    نطاقًا محايدًا لا يناقض شيئًا — الموضع 0.3 كان يناقض بالنصف ولم يعد."""
    cfg = HtfBiasConfig(warmup_bars=1, confirm_bars=1, range_position_split=0.25)
    assert _bias(_struct(range=(100.0, 200.0), close=120.0), cfg) is HTFBias.NEUTRAL
    assert _bias(_struct(range=(100.0, 200.0), close=130.0), cfg) is HTFBias.BULLISH


# ═══════════════════════ آلية التأكيد فوق المرشح البنيوي ═══════════════════════


def test_hysteresis_confirm_bars_in_structural_mode() -> None:
    """بوابة التأكيد تعمل فوق المرشح البنيوي كما هي: confirm=3 تحتاج
    ثلاث قراءات متتالية بنفس المرشح قبل التثبيت — ولا رفرفة قبلها."""
    cfg = HtfBiasConfig(warmup_bars=1, confirm_bars=3)
    states = _run([_struct()] * 3, cfg)
    assert states[0].bias is HTFBias.UNKNOWN
    assert states[0].pending_bias is HTFBias.BULLISH
    assert states[1].bias is HTFBias.UNKNOWN
    assert states[1].pending_count == 2
    assert states[2].bias is HTFBias.BULLISH  # الثالثة المتتالية تثبت
    assert states[2].pending_bias is None


def test_hysteresis_chain_break_in_structural_mode() -> None:
    """قطع السلسلة بمرشح مختلف يعيد العد صفرًا — لا ذاكرة للقراءات
    المقطوعة (NEUTRAL البنيوي يقصّ بلا مساس عدّاد التذبذب الاتجاهي)."""
    cfg = HtfBiasConfig(warmup_bars=1, confirm_bars=3)
    engine = HtfBiasEngine(cfg)
    for _ in range(3):
        engine.update(_struct())
    assert engine.state.bias is HTFBias.BULLISH
    engine.update(_struct(highs=(100.0, 105.0), lows=(95.0, 90.0), displacement_dir=0))
    assert engine.state.pending_bias is HTFBias.NEUTRAL  # المختلط يقصّ
    assert engine.state.pending_count == 1
    states = [engine.update(_struct(**_DOWN)) for _ in range(3)]
    assert states[0].pending_count == 1  # العد من جديد — لا ذاكرة
    assert states[1].pending_count == 2
    assert states[2].bias is HTFBias.BEARISH


def test_structural_oscillation_yields_transition() -> None:
    """التذبذب البنيوي (تناوب خام BULLISH/BEARISH بلا تأكيد) يفرض TRANSITION
    من الانعكاس الثاني ثم يثبت بخمس متتاليات — مرآة اختبار التذبذب في وضع
    الوكيل حرفيًا (confirm=5 كي يتراكم التذبذب قبل أي التزام — التزام
    الانتقال يصفّر العد بآلية 2-d نفسها)."""
    cfg = HtfBiasConfig(warmup_bars=1)  # confirm=5 وflips=2 كالافتراضي
    seq = [_struct() if i % 2 == 0 else _struct(**_DOWN) for i in range(10)]
    states = _run(seq, cfg)
    assert states[2].pending_bias is HTFBias.TRANSITION
    assert states[6].bias is HTFBias.TRANSITION
    assert states[-1].bias is HTFBias.TRANSITION


def test_warmup_applies_in_structural_mode() -> None:
    """الدافئ أرضية المحرك لا السمات: قبل warmup_bars ⇒ UNKNOWN بلا
    قراءات حتى مع تغذية بنيوية كاملة — ثم يقرأ من اكتماله."""
    cfg = HtfBiasConfig(warmup_bars=3, confirm_bars=1)
    engine = HtfBiasEngine(cfg)
    for i in range(1, 3):
        state = engine.update(_struct())
        assert state.bias is HTFBias.UNKNOWN
        assert state.data_sufficient is False
        assert state.bars_seen == i
    state = engine.update(_struct())
    assert state.data_sufficient is True
    assert state.bias is HTFBias.BULLISH


def test_insufficient_bar_cuts_pending_chain() -> None:
    """UNKNOWN البنيوي (تتابع غير كافٍ) يقطع سلسلة التأكيد ويعيد العد
    صفرًا — كأي مدخل ناقص في وضع الوكيل (عقد مشترك موثق)."""
    cfg = HtfBiasConfig(warmup_bars=1, confirm_bars=3)
    engine = HtfBiasEngine(cfg)
    engine.update(_struct())
    engine.update(_struct())
    assert engine.state.pending_count == 2
    engine.update(_struct(highs=(100.0,)))  # غير كافٍ
    assert engine.state.pending_count == 0
    assert engine.state.pending_bias is None
    engine.update(_struct())
    assert engine.state.pending_count == 1  # لا ذاكرة للقطع


# ═══════════════════════ الخصائص: حتمية ولا-نظرة-مستقبلية ═══════════════════════


def _mixed_structural_sequence() -> list[HtfBiasInputs]:
    """تسلسل بنيوي متنوع (اتجاه/انعكاس/مختلط/غير كافٍ/انكماش/تناقض/
    مواضع نطاق) للخصائص."""
    return [
        _struct(),  # BULLISH خام
        _struct(),  # تعميق
        _struct(**_DOWN),  # انعكاس
        _struct(highs=(100.0, 105.0), lows=(95.0, 90.0), displacement_dir=0),  # مختلط
        _struct(highs=(100.0,)),  # غير كافٍ ⇒ UNKNOWN
        _struct(expansion=0.1),  # انكماش ⇒ NEUTRAL
        _struct(displacement_dir=-1),  # تناقض إزاحة ⇒ TRANSITION
        _struct(range=(100.0, 200.0), close=120.0),  # موضع يناقض ⇒ NEUTRAL
        _struct(range=(100.0, 200.0), close=180.0),  # موضع يوافق ⇒ BULLISH
        _struct(**_DOWN),  # انعكاس
        _struct(),  # تعافٍ
        _struct(),  # تعميق
    ]


def test_determinism_identical_structural_sequences() -> None:
    """نفس التسلسل البنيوي مرتين ⇒ نفس تتابع الحالات بالتطابق التام
    (بايت-بايت عبر repr) — لا عشوائية ولا حالة خفية."""
    seq = _mixed_structural_sequence()
    cfg = HtfBiasConfig(warmup_bars=1)
    first = _run(seq, cfg)
    second = _run(seq, cfg)
    assert first == second
    assert repr(first) == repr(second)
    assert len(first) == len(seq)


@pytest.mark.parametrize("k", [3, 5, 8, 11])
def test_no_lookahead_prefix_invariance_structural(k: int) -> None:
    """حالات البادئة حتى k لا تتغير بإضافة ذيل — عقد §26.3 موروث في
    الوضع البنيوي (التغذية confirmed-as-supplied من المستدعي)."""
    seq = _mixed_structural_sequence()
    cfg = HtfBiasConfig(warmup_bars=1)
    full = _run(seq, cfg)
    prefix = _run(seq[:k], cfg)
    assert prefix == full[:k]


# ═══════════════════════ التحقق الصاخب للحقول البنيوية ═══════════════════════


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("displacement_dir", 5),
        ("displacement_dir", -2),
        ("displacement_dir", 0.5),
        ("expansion", 1.5),
        ("expansion", -0.1),
        ("expansion", float("nan")),
        ("range", (200.0, 100.0)),  # معكوس
        ("range", (float("nan"), 100.0)),
        ("range", (100.0, float("inf"))),
        ("range", (100.0, 200.0, 300.0)),  # ليس زوجًا
        ("close", -5.0),
        ("close", 0.0),
        ("close", float("nan")),
        ("highs", (-1.0, 105.0)),
        ("highs", (100.0, float("nan"))),
        ("lows", (0.0, 95.0)),
        ("lows", (90.0, float("inf"))),
    ],
)
def test_structural_inputs_reject_out_of_domain(field: str, value: Any) -> None:
    """تحقق صاخب: إزاحة خارج {+1, 0, -1} وتوسع خارج [0, 1] ونطاق معكوس
    أو غير زوج وإغلاق غير موجب وأسعار متتابع غير موجبة — كلها ValueError
    ولا تُصحَّح صمتًا أبدًا."""
    with pytest.raises(ValueError):
        _struct(**{field: value})


def test_structural_inputs_accept_boundaries() -> None:
    """الحدود الجائزة: الإزاحة 0 والتوسع 0.0/1.0 والنطاق المنحل بالمساواة
    والتتابع الفارغ (بيانات غير كافية تُقرأ لا تُرفض) وإغلاق موجب."""
    _struct(displacement_dir=0, expansion=0.0)
    _struct(expansion=1.0)
    _struct(range=(150.0, 150.0))
    _struct(highs=(), lows=())
    _struct(close=123.45)


def test_partial_structural_fields_still_validated() -> None:
    """التحقق الصاخب لا يعرف الأنماط: قيمة فاسدة تُرفض حتى لو غابت بقية
    التغذية البنيوية (كون النمط وكيلًا لا يليّن التحقق أبدًا)."""
    with pytest.raises(ValueError):
        HtfBiasInputs(
            directional_efficiency=0.6,
            efficiency_sign=1,
            normalized_range=1.2,
            atr_percentile=0.5,
            displacement_proxy=0.4,
            htf_displacement_direction=5,
        )
    with pytest.raises(ValueError):
        HtfBiasInputs(
            directional_efficiency=None,
            efficiency_sign=None,
            normalized_range=None,
            atr_percentile=None,
            displacement_proxy=None,
            external_high_sequence=(100.0, -1.0),
        )


# ═══════════════════════ الإعداد: الحقولان الجديدان ═══════════════════════


def test_config_structural_defaults() -> None:
    """الافتراضيات الإعدادية الموثقة: عتبة الانكماش 0.3 وشطر الموضع 0.5
    (الشطر النصفي البسيط)."""
    cfg = HtfBiasConfig()
    assert cfg.contraction_threshold == 0.3
    assert cfg.range_position_split == 0.5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contraction_threshold", 0.0),
        ("contraction_threshold", 1.0),
        ("contraction_threshold", float("nan")),
        ("range_position_split", 0.0),
        ("range_position_split", 0.6),
        ("range_position_split", 1.0),
    ],
)
def test_config_rejects_invalid_structural_values(field: str, value: Any) -> None:
    """عتبتا الوضع البنيوي نسبتان محدودتان: (0, 1) للانكماش و(0, 0.5]
    للشطر — فوق النصف تتداخل منطقتا التناقض فيُرفض."""
    with pytest.raises(ValueError):
        HtfBiasConfig(**{field: value})


def test_config_accepts_split_upper_bound() -> None:
    """الشطر يقبل النصف حصرًا كحد أعلى (تتلاصق منطقتا التناقض عنده)."""
    HtfBiasConfig(range_position_split=0.5)
    HtfBiasConfig(range_position_split=0.25)


# ═══════════════════════ التوصيل والتوثيق ═══════════════════════


def test_structural_mode_contract_documented() -> None:
    """ADR-016 موثق مغلقًا في رأس الموديول: الوضعان، الحفظ الحرفي
    للوكيل (كلمة proxy باقية — يطلبها اختبار 2-d)، والعقد الموروث
    (confirmed-as-supplied §11.1)، وعقد التفعيل في وثائق المدخلات."""
    doc = htf_module.__doc__ or ""
    assert "ADR-016" in doc
    assert "الوضع البنيوي" in doc
    assert "وضع الوكيل" in doc
    assert "proxy" in doc
    assert "confirmed-as-supplied" in doc
    inputs_doc = HtfBiasInputs.__doc__ or ""
    assert "المرحلة 3" in inputs_doc  # يطلبها اختبار 2-d أيضًا
    # عقد التفعيل: الأربعة معًا، والمحسّنان اختياريان.
    assert "جميعًا غير None" in inputs_doc
    assert "محسّنان اختياريان" in inputs_doc
