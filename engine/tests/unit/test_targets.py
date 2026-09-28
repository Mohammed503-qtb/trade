"""اختبارات خريطة الأهداف — بوابة المهمة 3-d (§10.5 + §24.1).

يُقفل حرفيًا بعقود :mod:`liquidity.targets`: الأهداف مناطق لا نقاط (مد
بـTARGET_ZONE_HALF_WIDTH التطبيعي من كل جانب)، الجهتان معبأتان بترتيب
كلي حتمي (صلة تنازليًا ثم مسافة تصاعديًا ثم المعرف)، استبعاد كل ما ليس
ACTIVE، المسافة المعيارية من حافة الدخول (صفر داخل المنطقة)، إشباع
القرب حتى ZONE_PROXIMITY، السقف لكل جانب، والخريطة الفارغة المعلنة قبل
توفر ATR.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from _liquidity_fixtures import INSTRUMENT, TIMEFRAME, candle, swing, vol
from liquidity.targets import TargetMap, TargetMapBuilder
from schemas import (
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    SweepClassification,
    SwingDirection,
    ZoneState,
)

_ATR = 2.0
#: نصف العرض ومسافة الصلة بالافتراضيات: atr×0.25 وatr×2.0.
_HALF_WIDTH = 0.5
_PROXIMITY = 4.0
_BASE = datetime(2026, 1, 5, tzinfo=UTC)


def _vol(atr: float | None) -> object:
    return vol(atr)


def _zone(
    zone_id: str,
    side: LiquiditySide,
    price_low: float,
    price_high: float,
    *,
    importance: float = 0.5,
    state: ZoneState = ZoneState.ACTIVE,
) -> LiquidityZone:
    """لقطة منطقة مصنوعة يدويًا — الباني يقرأ الأهمية والحالة فقط."""
    return LiquidityZone(
        zone_id=zone_id,
        side=side,
        price_low=price_low,
        price_high=price_high,
        origin_time=_BASE,
        age=3,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=0,
        last_test_time=None,
        sweep_status=SweepClassification.UNKNOWN,
        reaction_score=0.0,
        unmitigated_score=1.0,
        importance_score=importance,
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        state=state,
    )


# ═══════════ §10.5: تعمير الجهتين وتعريفاتهما الحرفية ═══════════


class TestPopulation:
    """‏above مناطق BUY لم يجاوزها السعر صعودًا، وbelow بالمثل للبيعية."""

    def test_both_sides_populated_by_side(self) -> None:
        zones = [
            _zone("buy1", LiquiditySide.BUY_SIDE, 102.0, 102.4),
            _zone("sell1", LiquiditySide.SELL_SIDE, 97.0, 97.4),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        assert [e.zone.zone_id for e in target_map.above] == ["buy1"]
        assert [e.zone.zone_id for e in target_map.below] == ["sell1"]

    def test_zone_passed_above_is_not_an_upside_target(self) -> None:
        zones = [
            _zone("below-price", LiquiditySide.BUY_SIDE, 98.0, 99.0),
            _zone("just-passed", LiquiditySide.BUY_SIDE, 99.0, 100.5),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 101.0, vol(_ATR))
        # السعر 101 جااز كلي المنطقتين صعودًا (100.5 < 101) — لا هدف صاعد
        assert target_map.above == ()
        assert target_map.below == ()  # مناطق شرائية لا تظهر هبوطًا

    def test_edge_equality_included_strictly_passed_excluded(self) -> None:
        """السعر عند الحافة هدف (≤)، وما جاوزه ولو بفارق ضئيل ليس هدفًا."""
        zones = [
            _zone("at-high", LiquiditySide.BUY_SIDE, 99.0, 100.0),
            _zone("just-passed", LiquiditySide.BUY_SIDE, 99.0, 99.9999),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        # at-high: 100 ≤ 100 (مساواة الحافة) هدف؛ just-passed: 100 > 99.9999 جاوزها
        assert [e.zone.zone_id for e in target_map.above] == ["at-high"]
        sell_zones = [
            _zone("at-low", LiquiditySide.SELL_SIDE, 100.0, 101.0),
            _zone("just-passed-sell", LiquiditySide.SELL_SIDE, 100.0001, 101.0),
        ]
        target_map2 = TargetMapBuilder().build_targets(sell_zones, 100.0, vol(_ATR))
        # at-low: 100 ≥ 100 هدف؛ just-passed-sell: 100 < 100.0001 جاوزها هبوطًا
        assert [e.zone.zone_id for e in target_map2.below] == ["at-low"]

    def test_price_inside_zone_zero_distance_full_relevance(self) -> None:
        """المستوى دخله السعر ظهر عليه بمسافة صفر — الصلة كاملة."""
        zone = _zone("inside", LiquiditySide.BUY_SIDE, 99.0, 101.0, importance=0.8)
        target_map = TargetMapBuilder().build_targets([zone], 100.0, vol(_ATR))
        assert len(target_map.above) == 1
        entry = target_map.above[0]
        assert entry.distance_atr == 0.0
        assert entry.relevance == pytest.approx(0.8)  # إشباع القرب 1.0

    def test_non_active_zones_excluded(self) -> None:
        """المجتاحة والمستهلكة والباطلة ليست أهدافًا (§10.3/§31.3)."""
        zones = [
            _zone("swept", LiquiditySide.BUY_SIDE, 102.0, 102.4, state=ZoneState.SWEPT),
            _zone("consumed", LiquiditySide.BUY_SIDE, 103.0, 103.4, state=ZoneState.CONSUMED),
            _zone("invalid", LiquiditySide.BUY_SIDE, 104.0, 104.4, state=ZoneState.INVALIDATED),
            _zone("active", LiquiditySide.BUY_SIDE, 105.0, 105.4),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        assert [e.zone.zone_id for e in target_map.above] == ["active"]


# ═══════════ الهندسة: مد نصف العرض والمسافة المعيارية ═══════════


class TestGeometry:
    """فاصل الهدف = [price_low − atr×0.25, price_high + atr×0.25] حرفيًا."""

    def test_half_width_extension(self) -> None:
        zone = _zone("band", LiquiditySide.BUY_SIDE, 100.0, 100.4)
        target_map = TargetMapBuilder().build_targets([zone], 100.0, vol(_ATR))
        entry = target_map.above[0]
        assert entry.zone_low == pytest.approx(100.0 - _HALF_WIDTH)
        assert entry.zone_high == pytest.approx(100.4 + _HALF_WIDTH)
        assert entry.zone.zone_id == "band"  # اللقطة الأصلية مجمّدة داخل الهدف

    def test_distance_atr_from_entry_edge(self) -> None:
        """المسافة من الحافة القريبة مطبَّعة بالـATR — موجبة دائمًا."""
        zones = [_zone("far", LiquiditySide.BUY_SIDE, 110.0, 110.4)]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        entry = target_map.above[0]
        assert entry.distance_atr == pytest.approx(10.0 / _ATR)
        sell = [_zone("far-low", LiquiditySide.SELL_SIDE, 90.0, 90.4)]
        target_map2 = TargetMapBuilder().build_targets(sell, 100.0, vol(_ATR))
        entry2 = target_map2.below[0]
        assert entry2.distance_atr == pytest.approx(9.6 / _ATR)  # 100 − 90.4

    def test_relevance_is_importance_times_proximity_saturation(self) -> None:
        """‏relevance = importance × max(0, 1 − distance/ZONE_PROXIMITY)."""
        zone = _zone("mid", LiquiditySide.BUY_SIDE, 102.0, 102.4, importance=0.8)
        target_map = TargetMapBuilder().build_targets([zone], 100.0, vol(_ATR))
        entry = target_map.above[0]
        # مسافة سعرية 2 على مسافة صلة 4 ⇒ إشباع 0.5 ⇒ 0.8 × 0.5
        assert entry.relevance == pytest.approx(0.4)
        assert entry.distance_atr == pytest.approx(1.0)

    def test_relevance_saturates_to_zero_beyond_proximity(self) -> None:
        zones = [_zone("far", LiquiditySide.BUY_SIDE, 110.0, 110.4, importance=1.0)]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        entry = target_map.above[0]
        assert entry.relevance == 0.0  # مسافة 10 > قرب 4 — ما زال هدفًا بصلة صفرية


# ═══════════ الترتيب الكلي الحتمي ═══════════


class TestOrdering:
    """صلة تنازليًا ثم مسافة تصاعديًا ثم المعرف تصاعديًا (كسر التعادل)."""

    def test_relevance_descends_then_distance_ascends(self) -> None:
        zones = [
            _zone("near-low-rel", LiquiditySide.BUY_SIDE, 101.0, 101.2, importance=0.3),
            _zone("mid-high-rel", LiquiditySide.BUY_SIDE, 102.0, 102.2, importance=0.8),
            _zone("far-zero-rel", LiquiditySide.BUY_SIDE, 110.0, 110.2, importance=0.9),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        ids = [e.zone.zone_id for e in target_map.above]
        # mid: صلة 0.8×0.5=0.4 / near: 0.3×0.75=0.225 / far: 0 (تجاوز القرب)
        assert ids == ["mid-high-rel", "near-low-rel", "far-zero-rel"]

    def test_distance_breaks_relevance_ties(self) -> None:
        zones = [
            _zone("nearer", LiquiditySide.BUY_SIDE, 101.0, 101.2, importance=0.8),
            _zone("farther", LiquiditySide.BUY_SIDE, 102.0, 102.2, importance=0.8),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        # كلاهما صلة 0.4 — الأقرب مسافةً أولًا
        assert [e.zone.zone_id for e in target_map.above] == ["nearer", "farther"]

    def test_zone_id_breaks_full_ties_deterministically(self) -> None:
        zones = [
            _zone("bbb", LiquiditySide.BUY_SIDE, 102.0, 102.2, importance=0.8),
            _zone("aaa", LiquiditySide.BUY_SIDE, 102.0, 102.2, importance=0.8),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR))
        assert [e.zone.zone_id for e in target_map.above] == ["aaa", "bbb"]
        # والترتيب لا يعتمد على ترتيب الإدخال أبدًا
        target_map2 = TargetMapBuilder().build_targets(list(reversed(zones)), 100.0, vol(_ATR))
        assert [e.zone.zone_id for e in target_map2.above] == ["aaa", "bbb"]


# ═══════════ السقف والخريطة الفارغة ═══════════


class TestLimitsAndEmptyMap:
    """سقف لكل جانب صاخب، وخريطة فارغة معلنة قبل توفر المقياس."""

    def test_limit_per_side_keeps_top_entries(self) -> None:
        zones = [
            _zone("z1", LiquiditySide.BUY_SIDE, 101.0, 101.1, importance=0.9),
            _zone("z2", LiquiditySide.BUY_SIDE, 102.0, 102.1, importance=0.8),
            _zone("z3", LiquiditySide.BUY_SIDE, 103.0, 103.1, importance=0.7),
        ]
        target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR), limit_per_side=2)
        assert [e.zone.zone_id for e in target_map.above] == ["z1", "z2"]
        single = TargetMapBuilder().build_targets(zones, 100.0, vol(_ATR), limit_per_side=1)
        assert [e.zone.zone_id for e in single.above] == ["z1"]

    def test_limit_per_side_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="limit_per_side"):
            TargetMapBuilder().build_targets([], 100.0, vol(_ATR), limit_per_side=0)

    def test_empty_map_declared_before_atr(self) -> None:
        """بلا ATR موجب لا مسافات معيارية — صفوف فارغة لا تقريب."""
        zones = [_zone("z", LiquiditySide.BUY_SIDE, 102.0, 102.4)]
        for atr in (None, 0.0):
            target_map = TargetMapBuilder().build_targets(zones, 100.0, vol(atr))
            assert target_map == TargetMap(above=(), below=())

    def test_no_zones_yields_empty_sides(self) -> None:
        target_map = TargetMapBuilder().build_targets([], 100.0, vol(_ATR))
        assert target_map.above == () and target_map.below == ()


# ═══════════ عبر الواجهة: الأهداف بعد اجتياح فعلي ═══════════


class TestThroughFacade:
    """قراءة الأهداف من خريطة حية — المنطقة المجتاحة تختفي من الأهداف."""

    def test_swept_zone_not_a_target_anymore(self) -> None:
        from liquidity import LiquidityEngine

        engine = LiquidityEngine()
        assert engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR)) == []
        assert (
            engine.update(
                candle(1, 100.0, 100.5, 99.5, 99.8),
                vol(_ATR),
                [swing("s1", 100.0, SwingDirection.HIGH, bar_time=_BASE)],
            )
            == []
        )
        # الاجتياح التام: اقتراب ← اختراق ← استرجاع (نمط §38.1)
        for i, row in enumerate(
            (
                (99.5, 100.0, 99.0, 100.0),
                (100.0, 101.4, 99.9, 101.0),
                (100.5, 100.6, 98.8, 99.0),
            ),
            start=2,
        ):
            engine.update(candle(i, *row), vol(_ATR))
        target_map = engine.targets(99.0, vol(_ATR))
        swept_id = next(z.zone_id for z in engine.zones() if z.state is ZoneState.SWEPT)
        assert all(e.zone.zone_id != swept_id for e in target_map.above)
        assert all(e.zone.zone_id != swept_id for e in target_map.below)
        # مناطق الجلسة النشطة ما زالت أهدافًا على الجهتين
        assert {e.zone.side for e in target_map.above} == {LiquiditySide.BUY_SIDE}
        assert {e.zone.side for e in target_map.below} == {LiquiditySide.SELL_SIDE}
