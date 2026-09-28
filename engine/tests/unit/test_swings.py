"""اختبارات كاشف المتطرفات — بوابة المهمة 3-b الحرفية (§11.1 + §26.3).

يُقفل بمسارات معروفة محسومة يدويًا: تأخير التأكيد (المتطرف يظهر عند شمعة
الحسم بالضبط ولا يظهر قبلها أبدًا — اختبار §11.1 لا-النظرة-المستقبلية)،
إبطال المرشح داخل النافذة («لم يوجد أبدًا»)، تأسيس الإطار الخارجي
وتصنيف خارجي/داخلي، حدود القوة ورتابتها في البروز، حتمية المعرف وصيغته
الموثقة، القوة الصفرية المعلنة قبل الدافئ، وحوارس التدفق الصاخبة.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from uuid import UUID as _UUID

import pytest
from market_state.volatility import VolatilityState
from schemas import Candle, DataQuality, Swing, SwingDirection, SwingScope
from structure import SwingConfig, SwingDetector

_BASE = datetime(2026, 1, 5, tzinfo=UTC)
_INSTRUMENT = "BINANCE_USDM:BTCUSDT"
_TIMEFRAME = "1m"


def _candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    instrument_id: str = _INSTRUMENT,
    timeframe: str = _TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> Candle:
    span = high - low
    body = abs(close - open_)
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
        volume=10.0,
        range=span,
        body_size=body,
        upper_wick=high - max(open_, close),
        lower_wick=min(open_, close) - low,
        body_fraction=body / span if span > 0.0 else 0.0,
        close_location_value=(close - low) / span if span > 0.0 else 0.5,
        true_range=span,
        realized_volatility=abs(math.log(close / open_)) if open_ > 0.0 else 0.0,
    )


def _vol(atr: float | None, bar_time: datetime | None = None) -> VolatilityState:
    """حالة تقلب مصنوعة يدويًا — ما يقرؤه الكاشف منها حصرًا هو ATR."""
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=0.001,
        range_expansion_percentile=0.5,
        vol_of_vol=0.1,
        gap_shock=0.0,
        spread_to_range=0.5,
        expected_holding_vol_1h=0.001,
        bar_time=bar_time,
    )


def _feed(
    detector: SwingDetector, rows: Sequence[tuple[float, float, float, float]]
) -> list[Swing]:
    """تغذية صفوف (open, high, low, close) بإزاحات دقيقة وجمع كل المتطرفات."""
    out: list[Swing] = []
    for i, (o, h, low, c) in enumerate(rows):
        out.extend(detector.update(_candle(i, o, h, low, c), _vol(2.0)))
    return out


# ═══════════ §11.1: تأخير التأكيد — لا إعلان قبل شمعة الحسم ═══════════


class TestConfirmationDelay:
    """المتطرف يُعلن عند شمعة الحسم (i + confirm_bars) بالضبط — لا قبلها."""

    ROWS = (
        (100.0, 101.0, 99.0, 100.5),  # 0: لا سابق ⇒ لا ترشيح
        (100.5, 102.0, 100.0, 101.5),  # 1: حافة صاعدة ⇒ مرشح قمة @102
        (101.5, 101.8, 100.8, 101.2),  # 2: تأكيد 1
        (101.2, 101.6, 100.5, 101.0),  # 3: تأكيد 2
        (101.0, 101.4, 100.2, 100.8),  # 4: تأكيد 3 ⇒ مؤكد هنا (confirm_bars=3)
        (100.8, 101.0, 99.5, 99.5),  # 5 (الإغلاق داخل [low, high] — لا قاع أدنى عرضيًا)
        (99.5, 100.0, 99.0, 99.6),  # 6
    )

    def test_swing_appears_exactly_at_confirmation_bar(self) -> None:
        """الاختبار الحرفي: شموع ما قبل الحسم لا تُخرج شيئًا، والحسم يُخرج المتطرف."""
        detector = SwingDetector(SwingConfig(confirm_bars=3))
        emitted_per_bar: list[list[Swing]] = []
        for i, (o, h, low, c) in enumerate(self.ROWS):
            emitted_per_bar.append(list(detector.update(_candle(i, o, h, low, c), _vol(2.0))))
        assert emitted_per_bar[:4] == [[], [], [], []]  # الشموع 0..3: لا إعلان أبدًا
        assert len(emitted_per_bar[4]) == 1
        swing = emitted_per_bar[4][0]
        assert swing.price == 102.0
        assert swing.direction is SwingDirection.HIGH
        assert swing.bar_time == _BASE + timedelta(minutes=1)  # شمعة القمة نفسها
        assert swing.confirmation_time == _BASE + timedelta(minutes=4)  # شمعة الحسم
        assert emitted_per_bar[5:] == [[], []]  # ولا شيء بعدها

    def test_confirmation_time_is_bar_time_plus_delay(self) -> None:
        """العلاقة القانونية الموثقة في 3-a: الفارق هو تأخير التأكيد موجبًا."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(
            detector,
            [
                (100.0, 101.0, 99.0, 100.5),
                (100.5, 102.0, 100.0, 101.5),
                (101.5, 101.8, 100.8, 101.2),
                (101.2, 101.6, 100.5, 101.0),
            ],
        )
        assert len(swings) == 1
        assert swings[0].confirmation_time - swings[0].bar_time == timedelta(minutes=2)


class TestInvalidation:
    """القمة الأعلى داخل نافذة التأكيد تُسقط المرشح — «لم يوجد أبدًا»."""

    def test_higher_high_inside_window_kills_candidate(self) -> None:
        detector = SwingDetector(SwingConfig(confirm_bars=3))
        swings = _feed(
            detector,
            [
                (100.0, 101.0, 99.0, 100.5),  # 0
                (100.5, 102.0, 100.0, 101.5),  # 1: مرشح @102
                (101.5, 101.5, 100.8, 101.2),  # 2: تأكيد 1
                (101.2, 103.0, 101.0, 102.5),  # 3: قمة أعلى ⇒ إبطال؛ المرشح الجديد @103
                (102.5, 102.5, 101.5, 102.0),  # 4: تأكيد 1
                (102.0, 102.2, 101.0, 101.5),  # 5: تأكيد 2
                (101.5, 101.8, 100.5, 101.0),  # 6: تأكيد 3 ⇒ مؤكد @103
            ],
        )
        assert len(swings) == 1
        assert swings[0].price == 103.0
        assert swings[0].bar_time == _BASE + timedelta(minutes=3)
        assert swings[0].confirmation_time == _BASE + timedelta(minutes=6)
        assert all(s.price != 102.0 for s in detector.swings)  # لم يوجد أبدًا

    def test_equal_high_does_not_invalidate(self) -> None:
        """المساواة ليست «قمة أعلى» — لا إبطال، لكن البروز يسقط إلى صفر."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(
            detector,
            [
                (100.0, 101.0, 99.0, 100.5),
                (100.5, 102.0, 100.0, 101.5),  # مرشح @102
                (101.5, 102.0, 100.8, 101.2),  # قمة مساوية: تأكيد 1 ووصيف @102
                (101.2, 101.6, 100.5, 101.0),  # تأكيد 2 ⇒ مؤكد
            ],
        )
        assert len(swings) == 1
        assert swings[0].price == 102.0
        assert swings[0].strength == 0.0  # excess = 0 (تساوٍ تام مع الوصيف)


class TestSimultaneousPolarities:
    """تزامن تأكيد القطبيتين في شمعة واحدة: قائمة من عنصرين بترتيب HIGH ثم LOW."""

    def test_both_confirm_same_bar_high_first(self) -> None:
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(
            detector,
            [
                (100.0, 101.0, 99.5, 100.5),
                (100.5, 103.0, 99.0, 102.5),  # مرشح قمة @103 ومرشح قاع @99 معًا
                (101.5, 101.5, 99.5, 101.0),  # تأكيد 1 للقطبيتين (الافتتاح داخل النطاق)
                (101.0, 101.8, 99.8, 101.5),  # تأكيد 2 للقطبيتين ⇒ تزامن
            ],
        )
        assert len(swings) == 2
        assert swings[0].direction is SwingDirection.HIGH
        assert swings[1].direction is SwingDirection.LOW
        assert swings[0].confirmation_time == swings[1].confirmation_time
        assert [s.price for s in swings] == [103.0, 99.0]


# ═══════════ الإطار الخارجي: التأسيس والتصنيف (§11.2 «internal or external») ═══════════


class TestScopeClassification:
    """تسلسل مصنوع يدويًا: أول قطبية خارجية، ثم داخلية فخارجية مجددًا."""

    ROWS = (
        (100.0, 101.0, 99.0, 100.5),  # 0
        (100.5, 103.0, 100.0, 102.5),  # 1
        (102.5, 106.0, 102.0, 105.5),  # 2
        (105.5, 110.0, 105.0, 109.0),  # 3: ذروة الصعود
        (109.0, 109.5, 106.0, 107.0),  # 4
        (107.0, 108.0, 105.0, 106.0),  # 5: قمة @110 مؤكدة (خارجية أولى)
        (106.0, 107.0, 104.0, 105.0),  # 6
        (105.0, 106.0, 103.0, 104.0),  # 7
        (104.0, 105.0, 100.0, 101.0),  # 8: ذروة الهبوط
        (101.0, 102.0, 100.5, 101.5),  # 9
        (101.5, 102.5, 101.0, 102.0),  # 10: قاع @100 مؤكد (خارجي أول)
        (102.0, 103.0, 101.5, 102.5),  # 11
        (102.5, 103.5, 102.0, 103.0),  # 12
        (103.0, 104.0, 102.5, 103.5),  # 13
        (103.5, 104.5, 103.0, 104.0),  # 14: ذروة صعود أدنى
        (104.0, 104.2, 103.2, 103.6),  # 15
        (103.6, 104.0, 103.0, 103.5),  # 16: قمة @104.5 مؤكدة (داخلية: دون 110)
        (103.5, 104.0, 102.0, 102.5),  # 17
        (102.5, 103.0, 101.5, 102.0),  # 18
        (102.0, 102.5, 101.8, 102.2),  # 19
        (102.2, 102.8, 102.0, 102.5),  # 20: قاع @101.5 مؤكد (داخلي: فوق 100)
        (102.5, 105.0, 102.3, 104.5),  # 21
        (104.5, 108.0, 104.0, 107.5),  # 22
        (107.5, 112.0, 107.0, 111.0),  # 23: ذروة صاعد جديد
        (111.0, 111.5, 109.0, 110.0),  # 24
        (110.0, 111.0, 109.5, 110.5),  # 25: قمة @112 مؤكدة (خارجية: تتجاوز 110)
    )

    def test_scope_sequence_and_anchors(self) -> None:
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(detector, self.ROWS)
        expected = [
            (SwingDirection.HIGH, 110.0, SwingScope.EXTERNAL, 3, 5),
            (SwingDirection.LOW, 100.0, SwingScope.EXTERNAL, 8, 10),
            (SwingDirection.HIGH, 104.5, SwingScope.INTERNAL, 14, 16),
            (SwingDirection.LOW, 101.5, SwingScope.INTERNAL, 18, 20),
            (SwingDirection.HIGH, 112.0, SwingScope.EXTERNAL, 23, 25),
        ]
        assert len(swings) == len(expected)
        for swing, (direction, price, scope, bar_idx, confirm_idx) in zip(
            swings, expected, strict=True
        ):
            assert swing.direction is direction
            assert swing.price == price
            assert swing.external_or_internal is scope
            assert swing.bar_time == _BASE + timedelta(minutes=bar_idx)
            assert swing.confirmation_time == _BASE + timedelta(minutes=confirm_idx)
        # المرساة الخارجية تتحدث مع كل قمة خارجية فقط
        assert detector.last_external_high is not None
        assert detector.last_external_high.price == 112.0
        assert detector.last_external_low is not None
        assert detector.last_external_low.price == 100.0

    def test_equal_external_high_is_internal(self) -> None:
        """القمة المساوية للمرساة الخارجية لا توسّع الإطار — داخلية (قرار موثق)."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(
            detector,
            [
                (100.0, 101.0, 99.0, 100.5),
                (100.5, 103.0, 99.5, 102.5),
                (101.8, 101.8, 100.0, 101.2),  # تأكيد 1 (الافتتاح داخل النطاق)
                (101.2, 101.6, 100.5, 101.0),  # تأكيد 2 ⇒ قمة خارجية أولى @103
                (101.0, 101.5, 100.5, 101.2),
                (101.2, 103.0, 100.8, 102.5),  # مرشح @103 (مساوٍ للمرساة)
                (102.5, 102.5, 101.0, 102.0),  # تأكيد 1
                (102.0, 102.2, 101.2, 101.5),  # تأكيد 2 ⇒ مؤكد مساويًا
            ],
        )
        assert len(swings) == 2
        assert swings[0].external_or_internal is SwingScope.EXTERNAL
        assert swings[1].price == 103.0
        assert swings[1].external_or_internal is SwingScope.INTERNAL


# ═══════════ القوة: الحدود والرتابة والدافئ (§11.1 «strength») ═══════════


class TestStrength:
    """tanh(excess/atr) ∈ [0,1]: رتيبة في البروز، صفرية معلنة قبل الدافئ."""

    @staticmethod
    def _rows(window_highs: tuple[float, float]) -> list[tuple[float, float, float, float]]:
        """قمة @110 عند الشمعة 1 ونافذة تأكيد بقمم محددة يدويًا (confirm_bars=2).

        شموع النافذة تُبنى من القمة المحددة بتراجع متناظر (افتتاح/إغلاق داخل
        [قمة−1, قمة]) فتبقى الشموع صالحة أيا كانت عمق الوصيف — القمم وحدها
        تدخل آلة الكاشف.
        """
        h0, h1 = window_highs
        return [
            (100.0, 101.0, 99.0, 100.5),
            (100.5, 110.0, 100.0, 109.0),
            (h0 - 0.5, h0, h0 - 1.0, h0 - 0.2),
            (h1 - 0.5, h1, h1 - 0.8, h1 - 0.3),
        ]

    def test_bounds_over_full_sequence(self) -> None:
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings = _feed(detector, TestScopeClassification.ROWS)
        assert swings
        for swing in detector.swings:
            assert 0.0 <= swing.strength <= 1.0

    def test_monotone_in_excess(self) -> None:
        """وصيف أعمق ⇒ بروز أعلى ⇒ قوة أعلى (نفس ATR)."""
        shallow = SwingDetector(SwingConfig(confirm_bars=2))
        deep = SwingDetector(SwingConfig(confirm_bars=2))
        swing_shallow = _feed(shallow, self._rows((109.5, 109.0)))[0]
        swing_deep = _feed(deep, self._rows((105.0, 104.0)))[0]
        assert swing_shallow.strength == pytest.approx(math.tanh(0.5 / 2.0))
        assert swing_deep.strength == pytest.approx(math.tanh(5.0 / 2.0))
        assert swing_deep.strength > swing_shallow.strength > 0.0

    def test_warmup_atr_none_yields_declared_zero(self) -> None:
        """قبل الدافئ: قوة صفرية معلنة — لا قيمة مزيفة (عقد الحالة)."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings: list[Swing] = []
        for i, row in enumerate(self._rows((109.5, 109.0))):
            swings.extend(detector.update(_candle(i, *row), _vol(None)))
        assert len(swings) == 1
        assert swings[0].strength == 0.0

    def test_no_volatility_state_at_all_yields_declared_zero(self) -> None:
        """vol=None (أول شمعة لمستدعي محرك التقلب) ⇒ قوة صفرية معلنة كذلك."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings: list[Swing] = []
        for i, row in enumerate(self._rows((109.5, 109.0))):
            swings.extend(detector.update(_candle(i, *row), None))
        assert len(swings) == 1
        assert swings[0].strength == 0.0

    def test_flat_atr_saturation_is_full_strength(self) -> None:
        """ATR معدوم مع بروز موجب: تشبع — أقصى قوة معرَّفة (قرار موثق)."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swings: list[Swing] = []
        for i, row in enumerate(self._rows((105.0, 104.0))):
            swings.extend(detector.update(_candle(i, *row), _vol(0.0)))
        assert len(swings) == 1
        assert swings[0].strength == 1.0


# ═══════════ المعرف الحتمي (روح D-07) ═══════════


class TestSwingId:
    """uuid5 بمفتاح مركب موثق — نفس المدخل ⇒ نفس المعرف عبر المحاكاة والإعادة."""

    def test_deterministic_across_detectors(self) -> None:
        rows = TestScopeClassification.ROWS
        first = _feed(SwingDetector(SwingConfig(confirm_bars=2)), rows)
        second = _feed(SwingDetector(SwingConfig(confirm_bars=2)), rows)
        assert [s.swing_id for s in first] == [s.swing_id for s in second]

    def test_documented_key_format(self) -> None:
        """الصيغة الحرفية: uuid5(namespace, f"{instrument}|{timeframe}|{iso}|{direction}")."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        swing = _feed(
            detector,
            [
                (100.0, 101.0, 99.0, 100.5),
                (100.5, 103.0, 100.0, 102.5),
                (101.8, 101.8, 100.8, 101.2),  # تأكيد 1 (الافتتاح داخل النطاق)
                (101.2, 101.6, 100.5, 101.0),  # تأكيد 2
            ],
        )[0]
        namespace: _UUID = uuid5(NAMESPACE_URL, "ai-market-reasoning-engine/structure/swing")
        key = f"{_INSTRUMENT}|{_TIMEFRAME}|{(_BASE + timedelta(minutes=1)).isoformat()}|HIGH"
        assert swing.swing_id == str(uuid5(namespace, key))


# ═══════════ حوارس التدفق الصاخبة (عقود _guards) ═══════════


class TestStreamGuards:
    """الشمع المتطورة وخلط الهوية والتكرار والتأخر وحالة المستقبل — رفض صاخب."""

    def test_evolving_candle_rejected(self) -> None:
        detector = SwingDetector()
        with pytest.raises(ValueError, match="المغلقة فقط"):
            detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5, is_closed=False), _vol(2.0))
        assert detector.swings == ()

    def test_identity_captured_then_enforced(self) -> None:
        detector = SwingDetector()
        detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))
        assert detector.instrument_id == _INSTRUMENT
        assert detector.timeframe == _TIMEFRAME
        with pytest.raises(ValueError, match="خلط أدوات"):
            detector.update(
                _candle(1, 100.0, 101.0, 99.0, 100.5, instrument_id="BINANCE_USDM:ETHUSDT"),
                _vol(2.0),
            )
        with pytest.raises(ValueError, match="خلط أطر"):
            detector.update(_candle(1, 100.0, 101.0, 99.0, 100.5, timeframe="5m"), _vol(2.0))

    def test_explicit_identity_mismatch_rejected(self) -> None:
        detector = SwingDetector(instrument_id=_INSTRUMENT, timeframe=_TIMEFRAME)
        with pytest.raises(ValueError, match="خلط أدوات"):
            detector.update(
                _candle(0, 100.0, 101.0, 99.0, 100.5, instrument_id="OTHER:XYZ"), _vol(2.0)
            )

    def test_duplicate_bar_time_rejected(self) -> None:
        detector = SwingDetector()
        detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))
        with pytest.raises(ValueError, match="تكرار bar_time"):
            detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))

    def test_late_bar_rejected_strictly(self) -> None:
        """الكواشف البنيوية ترفض المتأخرة رفضًا صريحًا (خلافًا لمحرك التقلب)."""
        detector = SwingDetector()
        detector.update(_candle(1, 100.0, 101.0, 99.0, 100.5), _vol(2.0))
        with pytest.raises(ValueError, match="متأخرة"):
            detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))

    def test_future_volatility_state_rejected(self) -> None:
        """حارس §26.3: حالة تقلب بطابع أحدث من شمعة الحكم تسريب صاخب."""
        detector = SwingDetector()
        detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))
        future = _BASE + timedelta(minutes=3)
        with pytest.raises(ValueError, match="من المستقبل"):
            detector.update(_candle(1, 100.0, 101.0, 99.0, 100.5), _vol(2.0, bar_time=future))

    def test_stale_volatility_state_allowed(self) -> None:
        """الحالة الأقدم مسموحة — قيمها الدافئة تعلن نفسها (محاذاة المستدعي)."""
        detector = SwingDetector()
        detector.update(_candle(0, 100.0, 101.0, 99.0, 100.5), _vol(2.0))
        stale = _BASE  # طابع الشمعة الأولى لا الثانية
        detector.update(_candle(1, 100.0, 101.0, 99.0, 100.5), _vol(2.0, bar_time=stale))


# ═══════════ الإعداد والسجل ═══════════


class TestConfigAndLedger:
    """تحقق الإعداد الصاخب وسجل التراكم غير الراجع."""

    def test_confirm_bars_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="confirm_bars"):
            SwingConfig(confirm_bars=0)

    def test_confirmed_ledger_never_revises(self) -> None:
        """المتطرف المُعلن غير قابل للمراجعة: لقطة مبكرة تطابق السجل النهائي."""
        detector = SwingDetector(SwingConfig(confirm_bars=2))
        early: list[Swing] = []
        for i, row in enumerate(TestScopeClassification.ROWS[:11]):
            early.extend(detector.update(_candle(i, *row), _vol(2.0)))
        snapshot = list(early)
        for i, row in enumerate(TestScopeClassification.ROWS[11:], start=11):
            detector.update(_candle(i, *row), _vol(2.0))
        assert detector.swings[: len(snapshot)] == tuple(snapshot)
        assert len(detector.swings) > len(snapshot)  # السجل ينمو للأمام فقط
