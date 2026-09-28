"""اختبارات خريطة السيولة — بوابة المهمة 3-d (§10.1-§10.3 + §31.3 + §26.3).

يُقفل حرفيًا بعقود رأس :mod:`liquidity.zones`: تأسيس مناطق PRIOR_SWING من
المتطرفات (قمة → BUY_SIDE صفرية العرض / قاع → SELL_SIDE)، دمج EQUAL_LEVEL
بالتسامح التطبيعي (حواف مغلقة وتجميع متسلسل وإحلال الأعضاء)، حدود
RANGE_BOUNDARY من المتطرفات الخارجية، تتبع SESSION_EXTREME وانقلابا
اليوم UTC والأسبوع ISO (فجوات البيانات لا تولّد مناطق)، جدول الانتقالات
الأحادي الاتجاه، تعريف الاختبار ودرجات §10.3 الثلاث (صيغها الموثقة
باليد)، الحتمية الصرفة لمعرفات uuid5، وحوارس التدفق الصاخبة.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from _liquidity_fixtures import (
    INSTRUMENT,
    TIMEFRAME,
    candle,
    minutes,
    swing,
    vol,
    zone_uuid,
)
from liquidity.zones import ImportanceWeights, LiquidityMapEngine, ZoneConfig
from schemas import (
    LiquiditySide,
    LiquiditySourceType,
    SweepClassification,
    SwingDirection,
    SwingScope,
    ZoneState,
)

_ATR = 2.0
#: تسامح المتساويات الافتراضي: atr × EQUAL_LEVEL_TOLERANCE = 2.0 × 0.25.
_TOL = 0.5


def _prior_key(swing_id: str) -> str:
    return f"{INSTRUMENT}|{TIMEFRAME}|PRIOR_SWING|{swing_id}"


def _map_with_zone(
    *,
    atr: float = _ATR,
    price: float = 100.0,
    strength: float = 0.8,
    scope: SwingScope = SwingScope.INTERNAL,
    config: ZoneConfig | None = None,
    direction: SwingDirection = SwingDirection.HIGH,
    swing_id: str = "s1",
    close: float = 100.0,
) -> tuple[LiquidityMapEngine, str]:
    """خريطة بمنطقة PRIOR_SWING واحدة مؤسسة على الشمعة الثانية (بلا كاشف).

    الشمعة الأولى واسعة المدى فتستقر مناطق الجلسة عند 105/95 بعيدًا عن
    مسار الاختبار؛ الشمعة الثانية تغلق عند ``close`` المعروفة فتُضبط بها
    قراءة القرب عند الحساب اليدوي للدرجات.
    """
    engine = LiquidityMapEngine(config)
    engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(atr))
    engine.update(
        candle(1, close - 0.2, close + 0.3, close - 0.5, close),
        vol(atr),
        [swing(swing_id, price, direction, bar_time=minutes(1), scope=scope, strength=strength)],
    )
    return engine, zone_uuid(_prior_key(swing_id))


def _quiet_bars(engine: LiquidityMapEngine, start: int, count: int, *, atr: float = _ATR) -> None:
    """شموع صامتة داخل مدى اليوم (لا قصوى جديدة ولا متطرفات) — لتقديم العمر فقط."""
    for i in range(start, start + count):
        engine.update(candle(i, 100.0, 100.3, 99.8, 100.0), vol(atr))


def _isolate(**weights: float) -> ImportanceWeights:
    """أوزان أحادية المكوّن — تُعزل درجة واحدة من مزيج §10.3 للقياس اليدوي."""
    base = {
        "structural": 0.0,
        "equal_levels": 0.0,
        "freshness": 0.0,
        "timeframe": 0.0,
        "distance": 0.0,
        "reaction": 0.0,
    }
    return ImportanceWeights(**{**base, **weights})


# ═══════════ §10.1/§10.2: مناطق PRIOR_SWING من المتطرفات ═══════════


class TestPriorSwingZones:
    """المتطرف المؤكد يصير منطقة صفرية العرض على جانبه القطبي حرفيًا."""

    def test_swing_high_founds_buy_side_zero_width(self) -> None:
        engine, zone_id = _map_with_zone(price=100.0)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.side is LiquiditySide.BUY_SIDE
        assert zone.price_low == 100.0
        assert zone.price_high == 100.0  # مستوى معزول — عرض صفري جائز (§10.2)
        assert zone.source_type is LiquiditySourceType.PRIOR_SWING
        assert zone.state is ZoneState.ACTIVE
        assert zone.origin_time == minutes(1)  # شمعة المتطرف نفسها
        assert zone.instrument == INSTRUMENT
        assert zone.timeframe == TIMEFRAME

    def test_swing_low_founds_sell_side(self) -> None:
        engine, zone_id = _map_with_zone(price=98.0, direction=SwingDirection.LOW)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.side is LiquiditySide.SELL_SIDE
        assert (zone.price_low, zone.price_high) == (98.0, 98.0)

    def test_zone_id_documented_uuid5_format(self) -> None:
        _, zone_id = _map_with_zone(swing_id="abc")
        assert zone_id == zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|PRIOR_SWING|abc")

    def test_creation_returns_dirty_snapshot_with_zero_age(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        changed = engine.update(
            candle(1, 99.8, 100.2, 99.5, 100.0),
            vol(_ATR),
            [swing("s1", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        assert [z.zone_id for z in changed] == [zone_uuid(_prior_key("s1"))]
        assert changed[0].age == 0  # عمر مشتق: شمعة التأسيس نفسها

    def test_redelivery_of_same_swing_is_idempotent(self) -> None:
        engine, zone_id = _map_with_zone()
        before = [z.zone_id for z in engine.zones()]
        again = engine.update(
            candle(2, 99.9, 100.3, 99.8, 100.0),
            vol(_ATR),
            [swing("s1", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        assert [z.zone_id for z in engine.zones()] == before  # لا ازدواج بالمفتاح الحتمي
        assert zone_id not in [z.zone_id for z in again]  # المفتاح القائم يعيد السجل كما هو

    def test_structural_is_scope_base_times_strength(self) -> None:
        """‏structural = قاعدة النطاق × قوة المتطرف — يقاس بالمزيج المعزول."""
        config = ZoneConfig(importance_weights=_isolate(structural=1.0))
        engine, internal_id = _map_with_zone(strength=0.8, scope=SwingScope.INTERNAL, config=config)
        internal = engine.zone(internal_id)
        assert internal is not None
        assert internal.importance_score == pytest.approx(0.5 * 0.8)  # القاعدة الداخلية
        engine2, external_id = _map_with_zone(
            strength=0.8, scope=SwingScope.EXTERNAL, config=config, swing_id="s2"
        )
        external = engine2.zone(external_id)
        assert external is not None
        assert external.importance_score == pytest.approx(1.0 * 0.8)  # القاعدة الخارجية


# ═══════════ §10.1: عناقيد EQUAL_LEVEL بالتسامح التطبيعي ═══════════


class TestEqualLevelClustering:
    """الانضمام: السعر ضمن التسامح من حافتي النطاق القائم — حواف مغلقة ومتسلسل."""

    @staticmethod
    def _cluster_map(
        config: ZoneConfig | None = None, *, atr: float = _ATR
    ) -> tuple[LiquidityMapEngine, str]:
        engine = LiquidityMapEngine(config)
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(atr))
        engine.update(
            candle(1, 99.8, 100.3, 99.5, 100.0),
            vol(atr),
            [swing("A", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        engine.update(
            candle(2, 99.9, 100.3, 99.6, 100.0),
            vol(atr),
            [swing("B", 100.4, SwingDirection.HIGH, bar_time=minutes(2))],
        )
        return engine, zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|A,B")

    def test_within_tolerance_merges_members(self) -> None:
        engine, cluster_id = self._cluster_map()
        cluster = engine.zone(cluster_id)
        assert cluster is not None
        assert cluster.source_type is LiquiditySourceType.EQUAL_LEVEL
        assert cluster.side is LiquiditySide.BUY_SIDE
        assert (cluster.price_low, cluster.price_high) == (100.0, 100.4)
        assert cluster.state is ZoneState.ACTIVE
        assert cluster.origin_time == minutes(1)  # أقدم عضو (A)
        # إحلال العضو المؤسس: ACTIVE → INVALIDATED (جدول الانتقالات (ب))
        prior = engine.zone(zone_uuid(_prior_key("A")))
        assert prior is not None
        assert prior.state is ZoneState.INVALIDATED

    def test_equal_count_via_isolated_blend(self) -> None:
        """‏equal_count يقاس بمزيج معزول: min(1, count/saturation)."""
        config = ZoneConfig(importance_weights=_isolate(equal_levels=1.0))
        engine, cluster_id = self._cluster_map(config)
        cluster = engine.zone(cluster_id)
        assert cluster is not None
        assert cluster.importance_score == pytest.approx(2.0 / 3.0)  # count=2 / sat=3
        saturated = ZoneConfig(
            equal_count_saturation=2, importance_weights=_isolate(equal_levels=1.0)
        )
        engine2, cluster2_id = self._cluster_map(saturated)
        cluster2 = engine2.zone(cluster2_id)
        assert cluster2 is not None
        assert cluster2.importance_score == pytest.approx(1.0)  # عنقودان يشبعان

    def test_cluster_structural_any_external_base(self) -> None:
        """أي عضو خارجي يرفع قاعدة العنقود؛ القوة متوسط أعضائه."""
        config = ZoneConfig(importance_weights=_isolate(structural=1.0))
        engine = LiquidityMapEngine(config)
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        engine.update(
            candle(1, 99.8, 100.3, 99.5, 100.0),
            vol(_ATR),
            [swing("A", 100.0, SwingDirection.HIGH, bar_time=minutes(1), strength=0.8)],
        )
        engine.update(
            candle(2, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [
                swing(
                    "B",
                    100.4,
                    SwingDirection.HIGH,
                    bar_time=minutes(2),
                    scope=SwingScope.EXTERNAL,
                    strength=0.6,
                )
            ],
        )
        cluster = engine.zone(zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|A,B"))
        assert cluster is not None
        assert cluster.importance_score == pytest.approx(1.0 * (0.8 + 0.6) / 2.0)

    def test_tolerance_edge_is_inclusive_and_chain_widens(self) -> None:
        """‏100.9 == الحافة + التسامح تنضم (حواف مغلقة) ويوسّع العنقود تسلسليًا."""
        engine, cluster_id = self._cluster_map()
        engine.update(
            candle(3, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [swing("C", 100.9, SwingDirection.HIGH, bar_time=minutes(3))],
        )
        widened = engine.zone(zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|A,B,C"))
        assert widened is not None
        assert (widened.price_low, widened.price_high) == (100.0, 100.9)
        assert widened.state is ZoneState.ACTIVE
        old = engine.zone(cluster_id)
        assert old is not None
        assert old.state is ZoneState.INVALIDATED  # العنقود الأصغر أُحيل

    def test_beyond_tolerance_stays_separate(self) -> None:
        engine, cluster_id = self._cluster_map()
        engine.update(
            candle(3, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [swing("D", 101.6, SwingDirection.HIGH, bar_time=minutes(3))],
        )
        separate = engine.zone(zone_uuid(_prior_key("D")))
        assert separate is not None  # 101.6 > 100.4 + 0.5 ⇒ PRIOR_SWING مستقلة
        assert separate.source_type is LiquiditySourceType.PRIOR_SWING
        cluster = engine.zone(cluster_id)
        assert cluster is not None
        assert cluster.state is ZoneState.ACTIVE  # العنقود لم يُمسّ

    def test_no_cross_side_merge(self) -> None:
        engine, _ = self._cluster_map()
        engine.update(
            candle(3, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [swing("L", 100.2, SwingDirection.LOW, bar_time=minutes(3))],
        )
        low_zone = engine.zone(zone_uuid(_prior_key("L")))
        assert low_zone is not None
        assert low_zone.side is LiquiditySide.SELL_SIDE  # قاع لا يندمج بعنقود قمم

    def test_no_merge_with_non_swing_sources(self) -> None:
        """منطقة الجلسة ليست مرشح دمج (المصادر المشتقة من المتطرفات فقط)."""
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))  # جلسة @105/95
        engine.update(
            candle(1, 100.0, 105.2, 99.5, 100.0),
            vol(_ATR),
            [swing("S", 105.2, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        near_session = engine.zone(zone_uuid(_prior_key("S")))
        assert near_session is not None  # ضمن التسامح من 105 لكن لا دمج
        assert near_session.source_type is LiquiditySourceType.PRIOR_SWING
        session = [
            z
            for z in engine.zones()
            if z.source_type is LiquiditySourceType.SESSION_EXTREME
            and z.side is LiquiditySide.BUY_SIDE
        ][-1]
        assert session.state is ZoneState.ACTIVE

    def test_no_merge_with_dead_swing_zone(self) -> None:
        """الدمج يقيّم ACTIVE فقط — المنطقة الميتة لا تُستدعى للتجميع."""
        engine, cluster_id = self._cluster_map()
        engine.invalidate_traversed(cluster_id)
        engine.update(
            candle(3, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [swing("C", 100.9, SwingDirection.HIGH, bar_time=minutes(3))],
        )
        # 100.9 كان سيندمج بالعنقود الحي؛ العنقود ميت ⇒ PRIOR_SWING مستقلة
        standalone = engine.zone(zone_uuid(_prior_key("C")))
        assert standalone is not None
        assert standalone.state is ZoneState.ACTIVE

    def test_member_redelivery_is_idempotent(self) -> None:
        engine, cluster_id = self._cluster_map()
        before = {z.zone_id: z.state for z in engine.zones()}
        engine.update(
            candle(3, 99.9, 100.3, 99.6, 100.0),
            vol(_ATR),
            [swing("B", 100.4, SwingDirection.HIGH, bar_time=minutes(2))],
        )
        after = {z.zone_id: z.state for z in engine.zones()}
        assert after == before  # مفتاح العنقود القائم يلتقط إعادة العضوية
        cluster = engine.zone(cluster_id)
        assert cluster is not None
        assert cluster.state is ZoneState.ACTIVE


# ═══════════ §10.1/§11.7: حدود RANGE_BOUNDARY من المتطرفات الخارجية ═══════════


class TestRangeBoundary:
    """الحد كائن حي واحد لكل جانب عند أقصى متطرف خارجي — يُحل بالإبطال (د)."""

    @staticmethod
    def _boundary_key(side: str, swing_id: str) -> str:
        return f"{INSTRUMENT}|{TIMEFRAME}|RANGE_BOUNDARY|{side}|{swing_id}"

    def test_external_swing_founds_boundary_and_duplicates_prior(self) -> None:
        """ازدواج المستوى مع PRIOR_SWING مقصود وموثق — الدلالتان مختلفتان."""
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        engine.update(
            candle(1, 99.8, 100.3, 99.5, 100.0),
            vol(_ATR),
            [
                swing(
                    "E1",
                    100.0,
                    SwingDirection.HIGH,
                    bar_time=minutes(1),
                    scope=SwingScope.EXTERNAL,
                )
            ],
        )
        boundary = engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E1")))
        assert boundary is not None
        assert boundary.source_type is LiquiditySourceType.RANGE_BOUNDARY
        assert boundary.side is LiquiditySide.BUY_SIDE
        assert (boundary.price_low, boundary.price_high) == (100.0, 100.0)
        prior = engine.zone(zone_uuid(_prior_key("E1")))
        assert prior is not None
        assert prior.state is ZoneState.ACTIVE  # الازدواج الموثق

    def test_higher_external_replaces_and_invalidates_old(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        for index, (sid, price) in enumerate((("E1", 100.0), ("E2", 102.0)), start=1):
            engine.update(
                candle(index, 99.8, 100.3, 99.5, 100.0),
                vol(_ATR),
                [
                    swing(
                        sid,
                        price,
                        SwingDirection.HIGH,
                        bar_time=minutes(index),
                        scope=SwingScope.EXTERNAL,
                    )
                ],
            )
        old = engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E1")))
        assert old is not None
        assert old.state is ZoneState.INVALIDATED  # جدول الانتقالات (د)
        new = engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E2")))
        assert new is not None
        assert new.state is ZoneState.ACTIVE
        assert new.price_high == 102.0

    def test_lower_or_equal_external_keeps_live_boundary(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        for index, (sid, price) in enumerate(
            (("E1", 102.0), ("E2", 101.0), ("E3", 102.0)), start=1
        ):
            engine.update(
                candle(index, 99.8, 100.3, 99.5, 100.0),
                vol(_ATR),
                [
                    swing(
                        sid,
                        price,
                        SwingDirection.HIGH,
                        bar_time=minutes(index),
                        scope=SwingScope.EXTERNAL,
                    )
                ],
            )
        live = engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E1")))
        assert live is not None
        assert live.state is ZoneState.ACTIVE  # الأدنى والمساوي لا يحلّان الحاكم
        assert engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E2"))) is None
        assert engine.zone(zone_uuid(self._boundary_key("BUY_SIDE", "E3"))) is None

    def test_external_low_founds_sell_boundary(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        engine.update(
            candle(1, 99.8, 100.3, 99.5, 100.0),
            vol(_ATR),
            [
                swing(
                    "L1",
                    96.0,
                    SwingDirection.LOW,
                    bar_time=minutes(1),
                    scope=SwingScope.EXTERNAL,
                )
            ],
        )
        boundary = engine.zone(zone_uuid(self._boundary_key("SELL_SIDE", "L1")))
        assert boundary is not None
        assert boundary.side is LiquiditySide.SELL_SIDE
        assert boundary.price_low == 96.0

    def test_internal_swings_never_found_boundaries(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        for index, (sid, price) in enumerate((("I1", 100.0), ("I2", 103.0)), start=1):
            engine.update(
                candle(index, 99.8, 100.3, 99.5, 100.0),
                vol(_ATR),
                [swing(sid, price, SwingDirection.HIGH, bar_time=minutes(index))],
            )
        boundaries = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.RANGE_BOUNDARY
        ]
        assert boundaries == []


# ═══════════ §9.4/قرار A-03: مناطق الجلسة الحية (يوم UTC) ═══════════


class TestSessionExtremes:
    """قمة/قاع الجلسة الجارية مستويان صفريا العرض يتحركان مع القصوى."""

    @staticmethod
    def _session_key(side: str, day: str, generation: int) -> str:
        return f"{INSTRUMENT}|{TIMEFRAME}|SESSION_EXTREME|{side}|{day}|g{generation}"

    def test_first_bar_founds_both_sides_generation_zero(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        high = engine.zone(zone_uuid(self._session_key("BUY_SIDE", "2026-01-05", 0)))
        low = engine.zone(zone_uuid(self._session_key("SELL_SIDE", "2026-01-05", 0)))
        assert high is not None and low is not None
        assert high.price_high == 101.0
        assert low.price_low == 99.0
        assert high.origin_time == minutes(0)
        assert low.origin_time == minutes(0)

    def test_extension_moves_zone_resets_origin(self) -> None:
        """الامتداد يحرك المستوى ويعيد تأسيس الأصل عند المتطرف الجاري."""
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        zone_id = zone_uuid(self._session_key("BUY_SIDE", "2026-01-05", 0))
        changed = engine.update(candle(1, 100.5, 102.0, 100.0, 101.5), vol(_ATR))
        assert zone_id in [z.zone_id for z in changed]  # متغيرة المادة
        moved = engine.zone(zone_id)
        assert moved is not None
        assert moved.price_high == 102.0
        assert moved.origin_time == minutes(1)  # عمر المنطقة يُعاد مع الامتداد

    def test_no_extension_leaves_zone_clean(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 102.0, 99.0, 100.5), vol(_ATR))
        engine.update(candle(1, 100.5, 101.5, 99.5, 101.0), vol(_ATR))  # لا قصوى جديدة
        assert engine.update(candle(2, 101.0, 101.8, 99.6, 100.8), vol(_ATR)) == []

    def test_death_refounds_new_generation(self) -> None:
        """موت منطقة الجلسة لا يُحييها — الامتداد التالي جيل جديد بهوية جديدة."""
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 100.0, 99.0, 99.5), vol(_ATR))
        g0 = zone_uuid(self._session_key("BUY_SIDE", "2026-01-05", 0))
        engine.invalidate_traversed(g0)
        engine.update(candle(1, 100.5, 101.0, 100.2, 100.8), vol(_ATR))
        g1 = engine.zone(zone_uuid(self._session_key("BUY_SIDE", "2026-01-05", 1)))
        dead = engine.zone(g0)
        assert g1 is not None and dead is not None
        assert g1.state is ZoneState.ACTIVE
        assert g1.price_high == 101.0
        assert dead.state is ZoneState.INVALIDATED  # الأجيال الميتة تُحفظ للتاريخ


# ═══════════ انقلاب اليوم UTC — مناطق PREV_DAY_EXTREME ═══════════


class TestDayRollover:
    """اكتمال يوم UTC: قصوا الأمس يصيران منطقتين وجلسته تُحال (جدول (ج))."""

    @staticmethod
    def _prev_day_key(side: str, day: str) -> str:
        return f"{INSTRUMENT}|{TIMEFRAME}|PREV_DAY_EXTREME|{side}|{day}"

    @staticmethod
    def _feed_monday_night() -> LiquidityMapEngine:
        engine = LiquidityMapEngine()
        monday = datetime(2026, 1, 5, 23, 58, tzinfo=UTC)
        engine.update(candle(0, 100.0, 101.5, 99.0, 101.0, bar_time=monday), vol(_ATR))
        engine.update(
            candle(0, 100.0, 101.0, 98.5, 99.0, bar_time=monday + timedelta(minutes=1)),
            vol(_ATR),
        )
        return engine

    def test_rollover_founds_prev_day_at_extremes(self) -> None:
        engine = self._feed_monday_night()
        tuesday = datetime(2026, 1, 6, 0, 0, tzinfo=UTC)
        engine.update(candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=tuesday), vol(_ATR))
        high = engine.zone(zone_uuid(self._prev_day_key("BUY_SIDE", "2026-01-05")))
        low = engine.zone(zone_uuid(self._prev_day_key("SELL_SIDE", "2026-01-05")))
        assert high is not None and low is not None
        assert high.price_high == 101.5  # قمة الاثنين
        assert low.price_low == 98.5  # قاع الاثنين
        assert high.origin_time == datetime(2026, 1, 5, 23, 58, tzinfo=UTC)
        assert low.origin_time == datetime(2026, 1, 5, 23, 59, tzinfo=UTC)
        assert high.state is ZoneState.ACTIVE
        # الأسبوع ISO نفسه (اثنين→ثلاثاء) ⇒ لا مناطق أسبوعية
        weekly = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.PREV_WEEK_EXTREME
        ]
        assert weekly == []

    def test_rollover_refers_yesterday_session_zones(self) -> None:
        engine = self._feed_monday_night()
        monday_high_zone = zone_uuid(
            f"{INSTRUMENT}|{TIMEFRAME}|SESSION_EXTREME|BUY_SIDE|2026-01-05|g0"
        )
        monday_low_zone = zone_uuid(
            f"{INSTRUMENT}|{TIMEFRAME}|SESSION_EXTREME|SELL_SIDE|2026-01-05|g0"
        )
        engine.update(
            candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=datetime(2026, 1, 6, tzinfo=UTC)),
            vol(_ATR),
        )
        for zone_id in (monday_high_zone, monday_low_zone):
            referred = engine.zone(zone_id)
            assert referred is not None
            assert referred.state is ZoneState.INVALIDATED  # جدول الانتقالات (ج)
        # وجلسة الثلاثاء تأسست عند قصوى شمعة الانقلاب نفسها
        tuesday_high = engine.zone(
            zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|SESSION_EXTREME|BUY_SIDE|2026-01-06|g0")
        )
        assert tuesday_high is not None
        assert tuesday_high.price_high == 100.5

    def test_same_day_bars_never_rollover(self) -> None:
        engine = LiquidityMapEngine()
        for i in range(4):
            engine.update(candle(i, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        prev_day = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.PREV_DAY_EXTREME
        ]
        assert prev_day == []

    def test_data_gap_founds_single_rollover_only(self) -> None:
        """فجوة البيانات لا تولّد مناطق لأيام فارغة — انقلاب عن آخر مرصود فقط."""
        engine = LiquidityMapEngine()
        engine.update(
            candle(0, 100.0, 103.0, 99.0, 100.5, bar_time=datetime(2026, 1, 5, 12, 0, tzinfo=UTC)),
            vol(_ATR),
        )
        engine.update(
            candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=datetime(2026, 1, 8, 12, 0, tzinfo=UTC)),
            vol(_ATR),
        )
        prev_day = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.PREV_DAY_EXTREME
        ]
        assert len(prev_day) == 2  # قمة وقاع الاثنين وحدهما — لا شيء للثلاثاء/الأربعاء
        assert {z.side for z in prev_day} == {LiquiditySide.BUY_SIDE, LiquiditySide.SELL_SIDE}


# ═══════════ انقلاب الأسبوع ISO (الاثنين→الأحد UTC) ═══════════


class TestWeekRollover:
    """اكتمال أسبوع ISO: قصواه منطقتان بعنوان ``{سنة}-W{أسبوع:02d}``."""

    @staticmethod
    def _prev_week_key(side: str, label: str) -> str:
        return f"{INSTRUMENT}|{TIMEFRAME}|PREV_WEEK_EXTREME|{side}|{label}"

    @staticmethod
    def _cross_week(sunday: datetime) -> LiquidityMapEngine:
        """شمعتا آخر أحد ثم شمعة الاثنين 00:00 — يطلق انقلابي اليوم والأسبوع."""
        engine = LiquidityMapEngine()
        engine.update(
            candle(0, 100.0, 104.0, 96.0, 103.0, bar_time=sunday - timedelta(minutes=2)), vol(_ATR)
        )
        engine.update(
            candle(0, 100.0, 104.5, 96.5, 104.0, bar_time=sunday - timedelta(minutes=1)), vol(_ATR)
        )
        engine.update(
            candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=sunday + timedelta(minutes=1)), vol(_ATR)
        )
        return engine

    def test_week_rollover_label_and_origin_bar(self) -> None:
        engine = self._cross_week(datetime(2026, 1, 4, 23, 59, tzinfo=UTC))  # أحد W01
        weekly = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.PREV_WEEK_EXTREME
        ]
        assert len(weekly) == 2
        high = engine.zone(zone_uuid(self._prev_week_key("BUY_SIDE", "2026-W01")))
        low = engine.zone(zone_uuid(self._prev_week_key("SELL_SIDE", "2026-W01")))
        assert high is not None and low is not None
        assert high.price_high == 104.5
        assert low.price_low == 96.0
        assert high.origin_time == datetime(2026, 1, 4, 23, 58, tzinfo=UTC)
        assert high.age == 0  # origin_bar = شريط الانقلاب — عقد موثق
        # انقلاب اليوم أُطلق أيضًا (أحد→اثنين) لكن بعنوان يوم الأحد المرصود
        prev_day = engine.zone(
            zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|PREV_DAY_EXTREME|BUY_SIDE|2026-01-04")
        )
        assert prev_day is not None
        assert prev_day.price_high == 104.5

    def test_iso_year_boundary_label_uses_iso_year(self) -> None:
        """أحد 2025-12-28 يكمل أسبوع 2025-W52 بعنوان سنة ISO الحاكمة."""
        engine = self._cross_week(datetime(2025, 12, 28, 23, 59, tzinfo=UTC))
        high = engine.zone(zone_uuid(self._prev_week_key("BUY_SIDE", "2025-W52")))
        assert high is not None
        assert high.price_high == 104.5
        # والأحد 2026-01-04 يكمل 2026-W01 رغم أن السنة التقويمية نفسها
        engine2 = self._cross_week(datetime(2026, 1, 4, 23, 59, tzinfo=UTC))
        high2 = engine2.zone(zone_uuid(self._prev_week_key("BUY_SIDE", "2026-W01")))
        assert high2 is not None

    def test_no_week_rollover_within_iso_week(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(
            candle(0, 100.0, 101.0, 99.0, 100.5, bar_time=datetime(2026, 1, 6, tzinfo=UTC)),
            vol(_ATR),
        )
        engine.update(
            candle(0, 100.0, 101.0, 99.0, 100.5, bar_time=datetime(2026, 1, 7, tzinfo=UTC)),
            vol(_ATR),
        )
        weekly = [
            z for z in engine.zones() if z.source_type is LiquiditySourceType.PREV_WEEK_EXTREME
        ]
        assert weekly == []  # ثلاثاء→أربعاء داخل 2026-W02


# ═══════════ §31.3: جدول الانتقالات — أحادية الاتجاه ═══════════


class TestLifecycleTransitions:
    """ACTIVE → SWEPT/CONSUMED/INVALIDATED عبر واجهة الكاشف المرتبط فقط."""

    def test_finalize_sweep_sets_swept_and_confirmed(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.finalize_sweep(zone_id)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.SWEPT
        assert zone.sweep_status is SweepClassification.CONFIRMED_SWEEP

    def test_finalize_accept_sets_consumed_and_break_accept(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.finalize_accept(zone_id)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.CONSUMED
        assert zone.sweep_status is SweepClassification.BREAK_AND_ACCEPT

    def test_invalidate_traversed_sets_invalidated(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.invalidate_traversed(zone_id)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.state is ZoneState.INVALIDATED

    def test_set_sweep_status_keeps_zone_active(self) -> None:
        engine, zone_id = _map_with_zone()
        for status in (
            SweepClassification.FAILED_SWEEP,
            SweepClassification.PARTIAL_SWEEP,
            SweepClassification.UNKNOWN,
        ):
            engine.set_sweep_status(zone_id, status)
            zone = engine.zone(zone_id)
            assert zone is not None
            assert zone.state is ZoneState.ACTIVE  # التصنيف غير الحاسم لا يُنهي
            assert zone.sweep_status is status

    def test_terminal_states_reject_further_mutations(self) -> None:
        for finalizer in ("finalize_sweep", "finalize_accept", "invalidate_traversed"):
            engine, zone_id = _map_with_zone()
            getattr(engine, finalizer)(zone_id)
            with pytest.raises(ValueError, match="حالة نهائية"):
                engine.finalize_sweep(zone_id)
            with pytest.raises(ValueError, match="حالة نهائية"):
                engine.finalize_accept(zone_id)
            with pytest.raises(ValueError, match="حالة نهائية"):
                engine.invalidate_traversed(zone_id)
            with pytest.raises(ValueError, match="حالة نهائية"):
                engine.set_sweep_status(zone_id, SweepClassification.UNKNOWN)

    def test_mutations_on_unknown_zone_raise(self) -> None:
        engine, _ = _map_with_zone()
        with pytest.raises(ValueError, match="منطقة مجهولة"):
            engine.record_test("nonexistent", minutes(2))
        with pytest.raises(ValueError, match="منطقة مجهولة"):
            engine.finalize_sweep("nonexistent")

    def test_lookups_of_unknown_zone_return_none(self) -> None:
        engine, _ = _map_with_zone()
        assert engine.zone("nonexistent") is None
        assert engine.sweep_status("nonexistent") is None


# ═══════════ §10.2 test_count: حصيلة الاختبارات ═══════════


class TestTouchCounting:
    """الاختبار حلقة تفاعل تبدؤها الخريطة بحصيلة ``record_test`` (حواف مغلقة)."""

    def test_record_test_increments_and_stamps(self) -> None:
        engine, zone_id = _map_with_zone()
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 0
        assert zone.last_test_time is None  # منطقة طازجة لم تُختبر قط
        engine.record_test(zone_id, minutes(5))
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 1
        assert zone.last_test_time == minutes(5)
        engine.record_test(zone_id, minutes(7))
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.test_count == 2
        assert zone.last_test_time == minutes(7)  # آخر اختبار يستبدل الطابع


# ═══════════ §10.3: الدرجات الثلاث — صيغ موثقة تُقاس باليد ═══════════


class TestReactionScore:
    """‏reaction_score = tanh(عمق الرفض المعياري) — بلا رفض صفر معلن."""

    def test_fresh_zone_scores_zero(self) -> None:
        _, zone_id = _map_with_zone()
        engine, _ = _map_with_zone()
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.reaction_score == 0.0

    def test_tanh_of_recorded_depth(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.record_reaction(zone_id, 0.5)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.reaction_score == pytest.approx(math.tanh(0.5))

    def test_negative_depth_is_clamped_to_zero(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.record_reaction(zone_id, -1.5)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.reaction_score == 0.0

    def test_latest_reaction_replaces_previous(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.record_reaction(zone_id, 2.0)
        engine.record_reaction(zone_id, 0.3)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.reaction_score == pytest.approx(math.tanh(0.3))

    def test_monotone_in_depth(self) -> None:
        scores = []
        for depth in (0.25, 1.0, 3.0):
            engine, zone_id = _map_with_zone()
            engine.record_reaction(zone_id, depth)
            zone = engine.zone(zone_id)
            assert zone is not None
            scores.append(zone.reaction_score)
        assert scores == sorted(scores)
        assert all(0.0 <= score < 1.0 for score in scores)  # tanh يحصر حصرًا رياضيًا


class TestUnmitigatedScore:
    """‏unmitigated = (1 − fill) / (1 + test_count) — عند الإنشاء 1.0 بالضبط."""

    def test_creation_is_exactly_one(self) -> None:
        engine, zone_id = _map_with_zone()
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.unmitigated_score == 1.0

    def test_zero_width_beyond_level_fills_completely(self) -> None:
        engine, zone_id = _map_with_zone()  # مستوى @100 صفري العرض
        engine.record_penetration(zone_id, 100.6)  # تجاوز صريح
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.unmitigated_score == 0.0

    def test_zero_width_touch_at_level_does_not_fill(self) -> None:
        """لمس المستوى لا يخففه — الفعل عند المستوى ليس وراءه."""
        engine, zone_id = _map_with_zone()
        engine.record_penetration(zone_id, 100.0)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.unmitigated_score == 1.0

    def test_wide_zone_fill_fraction(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        for index, (sid, price) in enumerate((("A", 100.0), ("B", 100.4)), start=1):
            engine.update(
                candle(index, 99.9, 100.3, 99.6, 100.0),
                vol(_ATR),
                [swing(sid, price, SwingDirection.HIGH, bar_time=minutes(index))],
            )
        cluster_id = zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|BUY_SIDE|A,B")
        engine.record_penetration(cluster_id, 100.2)  # منتصف النطاق [100, 100.4]
        zone = engine.zone(cluster_id)
        assert zone is not None
        assert zone.unmitigated_score == pytest.approx(0.5)  # fill = 0.2/0.4

    def test_sell_side_fill_from_opposite_edge(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(_ATR))
        for index, (sid, price) in enumerate((("A", 100.4), ("B", 100.0)), start=1):
            engine.update(
                candle(index, 100.0, 100.4, 99.6, 100.0),
                vol(_ATR),
                [swing(sid, price, SwingDirection.LOW, bar_time=minutes(index))],
            )
        cluster_id = zone_uuid(f"{INSTRUMENT}|{TIMEFRAME}|EQUAL_LEVEL|SELL_SIDE|A,B")
        engine.record_penetration(cluster_id, 100.2)  # كسر من الحافة العليا
        zone = engine.zone(cluster_id)
        assert zone is not None
        assert zone.unmitigated_score == pytest.approx(0.5)  # fill = (100.4-100.2)/0.4

    def test_test_count_divides(self) -> None:
        engine, zone_id = _map_with_zone()
        engine.record_test(zone_id, minutes(2))
        engine.record_test(zone_id, minutes(3))
        engine.record_test(zone_id, minutes(4))
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.unmitigated_score == pytest.approx(1.0 / 4.0)  # (1-0)/(1+3)

    def test_penetration_extreme_keeps_deepest(self) -> None:
        """التتبع يحتفظ بأقصى تغلغل (BUY: الأعلى) لا بآخره."""
        engine, zone_id = _map_with_zone()
        engine.record_penetration(zone_id, 100.6)
        engine.record_penetration(zone_id, 100.2)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.unmitigated_score == 0.0  # العمق 100.6 لا يُستبدل بالأخفض


class TestImportanceScore:
    """مزيج §10.3 — متوسط موزون بمكونات [0,1] يُطبَّع بمجموع الأوزان."""

    def test_hand_computed_default_blend(self) -> None:
        """حساب يدوي كامل بالأوزان الافتراضية عند التأسيس (عمر 0 وقرب تام)."""
        engine, zone_id = _map_with_zone(strength=0.8, close=100.0)  # structural=0.4
        zone = engine.zone(zone_id)
        assert zone is not None
        expected = (
            0.30 * 0.4  # structural (داخلي 0.5 × قوة 0.8)
            + 0.15 * (1.0 / 3.0)  # equal_count=1 / saturation=3
            + 0.20 * 1.0  # طزاجة العمر 0
            + 0.10 * 1.0  # دلالة الإطار الافتراضية
            + 0.15 * 1.0  # القرب: الإغلاق عند منتصف المستوى (فجوة 0)
            + 0.10 * 0.0  # لا رد فعل بعد
        ) / 1.0
        assert zone.importance_score == pytest.approx(expected)
        assert zone.importance_score == pytest.approx(0.62)

    def test_freshness_halving_at_documented_halflife(self) -> None:
        """مضاعفة العمر تقسم مساهمة الطزاجة إلى النصف — بالشموع لا بالسعر."""
        config = ZoneConfig(freshness_halflife=4, importance_weights=_isolate(freshness=1.0))
        engine, zone_id = _map_with_zone(config=config)
        # المنطقة تأسست بالشمعة 1 (عمرها 0) — كل شمعة لاحقة تقدم العمر واحدًا.
        expected_at_bar = {
            1: 1.0,  # عمر 0
            2: 0.5 ** (1 / 4),  # عمر 1
            3: 0.5**0.5,  # عمر 2
            5: 0.5,  # عمر 4 = نصف العمر بالضبط
            9: 0.25,  # عمر 8 = ضعف نصف العمر
        }
        for bar_index in range(2, 10):
            engine.update(candle(bar_index, 100.0, 100.3, 99.8, 100.0), vol(_ATR))
            if bar_index in expected_at_bar:
                zone = engine.zone(zone_id)
                assert zone is not None
                assert zone.importance_score == pytest.approx(expected_at_bar[bar_index])

    def test_freshness_strictly_decays_with_age(self) -> None:
        config = ZoneConfig(freshness_halflife=2, importance_weights=_isolate(freshness=1.0))
        engine, zone_id = _map_with_zone(config=config)
        previous = 1.0
        for _ in range(6):
            _quiet_bars(engine, engine.bars_consumed, 1)
            zone = engine.zone(zone_id)
            assert zone is not None
            assert zone.importance_score < previous  # اضمحلال رتيب صارم
            previous = zone.importance_score

    def test_distance_saturates_linearly_to_proximity(self) -> None:
        """إشباع خطي حتى ZONE_PROXIMITY (atr×2) ثم صفر — بالسعر الجاري."""
        config = ZoneConfig(importance_weights=_isolate(distance=1.0))
        for close, expected in ((100.8, 0.8), (103.0, 0.25), (104.0, 0.0), (105.0, 0.0)):
            engine, zone_id = _map_with_zone(config=config, close=close)
            zone = engine.zone(zone_id)
            assert zone is not None
            assert zone.importance_score == pytest.approx(expected), close

    def test_distance_defaults_to_full_before_warmup(self) -> None:
        """بلا ATR متاح: أقصى صلة لا عقاب أعمى — قرار موثق للمناطق قبل الدافئ."""
        config = ZoneConfig(importance_weights=_isolate(distance=1.0))
        engine = LiquidityMapEngine(config)
        engine.update(candle(0, 99.0, 105.0, 95.0, 100.0), vol(None))
        engine.update(
            candle(1, 103.0, 103.5, 102.5, 103.0),
            vol(None),
            [swing("s1", 100.0, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        zone = engine.zone(zone_uuid(_prior_key("s1")))
        assert zone is not None
        assert zone.importance_score == 1.0

    def test_timeframe_weight_declared_by_caller(self) -> None:
        config = ZoneConfig(timeframe_weight=0.7, importance_weights=_isolate(timeframe=1.0))
        engine, zone_id = _map_with_zone(config=config)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.importance_score == pytest.approx(0.7)

    def test_reaction_component_blended(self) -> None:
        config = ZoneConfig(importance_weights=_isolate(reaction=1.0))
        engine, zone_id = _map_with_zone(config=config)
        engine.record_reaction(zone_id, 0.9)
        zone = engine.zone(zone_id)
        assert zone is not None
        assert zone.importance_score == pytest.approx(math.tanh(0.9))

    def test_consumed_or_dead_zone_zeroes_importance(self) -> None:
        """مدخل «whether the zone has already been consumed» (§10.3) يُصفَّر كاملًا."""
        for finalizer in ("finalize_sweep", "finalize_accept", "invalidate_traversed"):
            engine, zone_id = _map_with_zone()
            engine.record_test(zone_id, minutes(2))
            engine.record_reaction(zone_id, 1.0)  # مكونات أخرى غير صفرية
            getattr(engine, finalizer)(zone_id)
            zone = engine.zone(zone_id)
            assert zone is not None
            assert zone.importance_score == 0.0, finalizer
            # التصفير للمزيج وحده: رد الفعل وعدم التخفيف يبقيان بحسابهما
            assert zone.reaction_score == pytest.approx(math.tanh(1.0))
            assert zone.unmitigated_score == pytest.approx(1.0 / 2.0)  # اختبار واحد حُسب

    def test_source_structural_defaults_table(self) -> None:
        """قيم المصادر غير المشتقة من المتطرفات — جدول الافتراضيات الموثق."""
        config = ZoneConfig(importance_weights=_isolate(structural=1.0))
        engine = LiquidityMapEngine(config)
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))  # جلسة 0.6
        engine.update(
            candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=datetime(2026, 1, 6, tzinfo=UTC)),
            vol(_ATR),
        )  # انقلاب يوم ⇒ PREV_DAY 0.8
        structurals = {
            z.source_type: z.importance_score for z in engine.zones() if z.state is ZoneState.ACTIVE
        }
        assert structurals[LiquiditySourceType.SESSION_EXTREME] == pytest.approx(0.6)
        assert structurals[LiquiditySourceType.PREV_DAY_EXTREME] == pytest.approx(0.8)

    def test_source_structural_override_merges_over_defaults(self) -> None:
        config = ZoneConfig(
            source_structural={LiquiditySourceType.PREV_DAY_EXTREME: 0.5},
            importance_weights=_isolate(structural=1.0),
        )
        engine = LiquidityMapEngine(config)
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        engine.update(
            candle(0, 100.0, 100.5, 99.5, 100.2, bar_time=datetime(2026, 1, 6, tzinfo=UTC)),
            vol(_ATR),
        )
        prev_day = next(
            z
            for z in engine.zones()
            if z.source_type is LiquiditySourceType.PREV_DAY_EXTREME and z.state is ZoneState.ACTIVE
        )
        assert prev_day.importance_score == pytest.approx(0.5)  # التجاوز يفوز

    def test_scores_within_unit_interval_over_mixed_run(self) -> None:
        engine = LiquidityMapEngine()
        rng_rows = (
            (100.0, 103.0, 97.0, 99.0),
            (99.0, 101.5, 98.0, 101.0),
            (101.0, 104.5, 100.5, 104.0),
            (104.0, 104.8, 99.5, 100.0),
            (100.0, 100.9, 96.5, 97.0),
        )
        for index, row in enumerate(rng_rows):
            swings = [
                swing(
                    f"s{index}",
                    100.0 + index * 0.3,
                    SwingDirection.HIGH,
                    bar_time=minutes(index),
                    strength=0.5 + 0.1 * index,
                )
            ]
            engine.update(candle(index, *row), vol(_ATR), swings)
            engine.record_test(next(reversed([z.zone_id for z in engine.zones()])), minutes(index))
            engine.record_penetration(
                next(reversed([z.zone_id for z in engine.zones()])), 100.0 + index * 0.3
            )
        for zone in engine.zones():
            assert 0.0 <= zone.reaction_score <= 1.0
            assert 0.0 <= zone.unmitigated_score <= 1.0
            assert 0.0 <= zone.importance_score <= 1.0


# ═══════════ روح D-07: حتمية المعرفات والخريطة ═══════════


class TestDeterministicIds:
    """نفس المدخلات ⇒ نفس الخريطة بالتطابق التام — مفاتيح uuid5 بلا أسعار."""

    @staticmethod
    def _mixed_sequence() -> list[tuple[int, tuple[float, float, float, float]]]:
        return [
            (0, (99.0, 101.5, 98.0, 100.5)),
            (1, (100.5, 102.0, 100.0, 101.5)),
            (2, (101.5, 101.8, 100.5, 101.0)),
            (3, (101.0, 101.6, 99.5, 100.0)),
        ]

    def test_two_engines_produce_identical_maps(self) -> None:
        def build() -> LiquidityMapEngine:
            engine = LiquidityMapEngine()
            for index, row in self._mixed_sequence():
                swings = [
                    swing(
                        f"sw{index}",
                        101.0 - index * 0.4,
                        SwingDirection.HIGH,
                        bar_time=minutes(index),
                    )
                ]
                engine.update(candle(index, *row), vol(_ATR), swings)
            return engine

        first, second = build(), build()
        assert [z.zone_id for z in first.zones()] == [z.zone_id for z in second.zones()]
        assert first.zones() == second.zones()  # تطابق تام بلقطات كاملة

    def test_zone_ids_carry_no_prices(self) -> None:
        """مفتاحان سعريان مختلفان لنفس المتطرف لا يغيران الهوية تحت التحجيم."""
        engine_a, _ = _map_with_zone(price=100.0, swing_id="same")
        engine_b, _ = _map_with_zone(price=3500.0, swing_id="same", close=3500.0)
        zone_a = engine_a.zone(zone_uuid(_prior_key("same")))
        zone_b = engine_b.zone(zone_uuid(_prior_key("same")))
        assert zone_a is not None and zone_b is not None
        assert zone_a.zone_id == zone_b.zone_id  # المفتاح معرف المتطرف لا سعره

    def test_zones_ordered_by_creation(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        engine.update(
            candle(1, 100.5, 100.8, 100.0, 100.2),
            vol(_ATR),
            [swing("s1", 100.8, SwingDirection.HIGH, bar_time=minutes(1))],
        )
        sources = [z.source_type for z in engine.zones()]
        assert sources == [
            LiquiditySourceType.SESSION_EXTREME,  # قمة الجلسة أولًا
            LiquiditySourceType.SESSION_EXTREME,  # ثم قاعها
            LiquiditySourceType.PRIOR_SWING,
        ]


# ═══════════ حوارس التدفق الصاخبة ═══════════


class TestStreamGuards:
    """الشمع المتطورة وخلط الهوية والترتيب غير الصاعد — رفض لا تصحيح صامت."""

    def test_evolving_candle_rejected(self) -> None:
        engine = LiquidityMapEngine()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            engine.update(candle(0, 100.0, 101.0, 99.0, 100.5, is_closed=False), vol(_ATR))
        assert engine.bars_consumed == 0  # لا طفرة قبل الرفض

    def test_identity_captured_then_enforced(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        assert engine.instrument_id == INSTRUMENT
        assert engine.timeframe == TIMEFRAME
        with pytest.raises(ValueError, match="خلط أدوات"):
            engine.update(
                candle(1, 100.0, 101.0, 99.0, 100.5, instrument_id="BINANCE_USDM:ETHUSDT"),
                vol(_ATR),
            )
        with pytest.raises(ValueError, match="خلط أطر"):
            engine.update(candle(1, 100.0, 101.0, 99.0, 100.5, timeframe="5m"), vol(_ATR))

    def test_explicit_identity_mismatch_rejected(self) -> None:
        engine = LiquidityMapEngine(instrument_id=INSTRUMENT, timeframe=TIMEFRAME)
        with pytest.raises(ValueError, match="خلط أدوات"):
            engine.update(
                candle(0, 100.0, 101.0, 99.0, 100.5, instrument_id="OTHER:XYZ"), vol(_ATR)
            )

    def test_duplicate_and_late_bar_times_rejected(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(1, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        with pytest.raises(ValueError, match="ترتيب غير صاعد"):
            engine.update(candle(1, 100.0, 101.0, 99.0, 100.5), vol(_ATR))  # تكرار
        with pytest.raises(ValueError, match="ترتيب غير صاعد"):
            engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))  # متأخرة
        assert engine.bars_consumed == 1  # الرفض لا يغير الساعة
        engine.update(candle(2, 100.0, 101.0, 99.0, 100.5), vol(_ATR))  # الأحدث يُقبل

    def test_swing_from_another_timeframe_rejected(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        with pytest.raises(ValueError, match="إطار آخر"):
            engine.update(
                candle(1, 100.0, 101.0, 99.0, 100.5),
                vol(_ATR),
                [swing("x", 101.0, SwingDirection.HIGH, bar_time=minutes(1), timeframe="5m")],
            )

    def test_validate_bar_is_read_only(self) -> None:
        engine = LiquidityMapEngine()
        engine.update(candle(0, 100.0, 101.0, 99.0, 100.5), vol(_ATR))
        before = engine.zones()
        with pytest.raises(ValueError):
            engine.validate_bar(candle(1, 100.0, 101.0, 99.0, 100.5, is_closed=False))
        engine.validate_bar(candle(1, 100.0, 101.0, 99.0, 100.5))  # مقبولة بلا أثر
        assert engine.zones() == before
        assert engine.bars_consumed == 1


# ═══════════ الإعداد الصاخب ═══════════


class TestConfigValidation:
    """مقابض ZoneConfig وImportanceWeights — تحقق صاخب لا قيم مزيفة."""

    def test_freshness_halflife_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="freshness_halflife"):
            ZoneConfig(freshness_halflife=0)

    def test_timeframe_weight_positive_unit(self) -> None:
        with pytest.raises(ValueError, match="timeframe_weight"):
            ZoneConfig(timeframe_weight=0.0)
        with pytest.raises(ValueError, match="timeframe_weight"):
            ZoneConfig(timeframe_weight=1.5)

    def test_saturation_and_structural_bases(self) -> None:
        with pytest.raises(ValueError, match="equal_count_saturation"):
            ZoneConfig(equal_count_saturation=0)
        with pytest.raises(ValueError, match="structural_external"):
            ZoneConfig(structural_external=0.0)
        with pytest.raises(ValueError, match="structural_internal"):
            ZoneConfig(structural_internal=1.5)

    def test_source_structural_values_within_unit(self) -> None:
        with pytest.raises(ValueError, match="source_structural"):
            ZoneConfig(source_structural={LiquiditySourceType.SESSION_EXTREME: 1.5})

    def test_weights_non_negative_and_positive_sum(self) -> None:
        with pytest.raises(ValueError, match="وزن"):
            ImportanceWeights(structural=-0.1)
        with pytest.raises(ValueError, match="مجموع أوزان"):
            ImportanceWeights(
                structural=0.0,
                equal_levels=0.0,
                freshness=0.0,
                timeframe=0.0,
                distance=0.0,
                reaction=0.0,
            )

    def test_source_structural_frozen_mapping(self) -> None:
        config = ZoneConfig()
        with pytest.raises(TypeError):
            config.source_structural[LiquiditySourceType.SESSION_EXTREME] = 0.1  # type: ignore[index]
