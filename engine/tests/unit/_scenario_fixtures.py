"""مساعدات مشتركة لاختبارات السيناريوهات (المرحلة 7) — بناة المنطقة
والشمعة وخريطة الأهداف ولقطة الحالة (نمط ``_fusion_fixtures``).

كل قيمة قابلة للحساب اليدوي وكل حقل قابل للتجاوز — فروق الاختبارات من
التغيير المقصود وحده. الهندسات مرتبطة بمنطقة بيعية مرجعية عند
[59_800, 59_900] وإطار 1m وأداة BTCUSDT الدائمة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from liquidity.targets import TargetEntry, TargetMap
from market_state.volatility import VolatilityState
from schemas import (
    Candle,
    DataQuality,
    HTFBias,
    LiquiditySide,
    LiquiditySourceType,
    LiquidityZone,
    MarketRegime,
    MarketStateSnapshot,
    SessionType,
    SweepClassification,
    ZoneState,
)
from schemas.liquidity import BreakAcceptEventPayload, SweepEventPayload

__all__ = [
    "ANCHOR_TIME",
    "ATR",
    "INSTRUMENT",
    "TIMEFRAME",
    "make_break_accept_payload",
    "make_candle",
    "make_market_state",
    "make_sweep_payload",
    "make_target_map",
    "make_volatility",
    "make_zone",
    "sell_zone",
]

#: طابع شمعة المرسِم المرجعية — بقية الأشرطة تُرقّم دقائق بعدها.
ANCHOR_TIME = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
#: ATR مرجعي موجب — مقياس كل الهندسات النسبية.
ATR = 200.0


def make_zone(
    *,
    zone_id: str = "lz-sell-001",
    side: LiquiditySide = LiquiditySide.SELL_SIDE,
    price_low: float = 59_800.0,
    price_high: float = 59_900.0,
    instrument: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    state: ZoneState = ZoneState.ACTIVE,
) -> LiquidityZone:
    """منطقة سيولة §10.2 كاملة الحقول — فاصل مرتب بقيَم محسوبة."""
    return LiquidityZone(
        zone_id=zone_id,
        side=side,
        price_low=price_low,
        price_high=price_high,
        origin_time=ANCHOR_TIME - timedelta(hours=6),
        age=120,
        source_type=LiquiditySourceType.PRIOR_SWING,
        test_count=2,
        last_test_time=ANCHOR_TIME - timedelta(hours=1),
        sweep_status=SweepClassification.UNKNOWN,
        reaction_score=0.6,
        unmitigated_score=0.7,
        importance_score=0.8,
        instrument=instrument,
        timeframe=timeframe,
        state=state,
    )


def sell_zone() -> LiquidityZone:
    """المنطقة البيعية المرجعية [59_800, 59_900] — قاع سيل دولار."""
    return make_zone()


def make_sweep_payload(
    *,
    zone_id: str = "lz-sell-001",
    zone_side: LiquiditySide = LiquiditySide.SELL_SIDE,
    excursion_atr: float = 1.0,
    reclaim_bars: int = 1,
    bar_time: datetime = ANCHOR_TIME,
) -> SweepEventPayload:
    """اجتياح مؤكد §10.4 على المنطقة المرجعية — البث نفسه التأكيد."""
    return SweepEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=bar_time,
        zone_id=zone_id,
        zone_side=zone_side,
        classification=SweepClassification.CONFIRMED_SWEEP,
        excursion_atr=excursion_atr,
        penetration_reached=True,
        reclaim_bars=reclaim_bars,
        test_count_at_event=3,
    )


def make_break_accept_payload(
    *,
    zone_id: str = "lz-sell-001",
    zone_side: LiquiditySide = LiquiditySide.SELL_SIDE,
    excursion_atr: float = 1.0,
    acceptance_ratio: float = 1.0,
    bar_time: datetime = ANCHOR_TIME,
) -> BreakAcceptEventPayload:
    """كسر بقبول §10.4 على المنطقة المرجعية."""
    return BreakAcceptEventPayload(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=bar_time,
        zone_id=zone_id,
        zone_side=zone_side,
        excursion_atr=excursion_atr,
        acceptance_ratio=acceptance_ratio,
        window_bars=3,
    )


def make_target_map(
    *,
    above: tuple[tuple[str, float, float, float, float], ...] = (
        ("lz-buy-001", 60_500.0, 60_600.0, 1.2, 0.9),
        ("lz-buy-002", 61_000.0, 61_100.0, 2.5, 0.7),
    ),
    below: tuple[tuple[str, float, float, float, float], ...] = (
        ("lz-sell-002", 59_400.0, 59_500.0, 0.8, 0.8),
        ("lz-sell-003", 59_000.0, 59_100.0, 1.9, 0.6),
    ),
) -> TargetMap:
    """خريطة أهداف §10.5 — صفوف (معرف، قاع، قمة، مسافة ATR، صلة).

    القيم الافتراضية: هدفان فوق (شرائية) وهدفان تحت (بيعية) — كل قالب
    يجد هدفه في جهته إلا عند طلب غيابه صراحة ببناء خريطة فارغة الجانب.
    """

    def _entry(row: tuple[str, float, float, float, float], side: LiquiditySide) -> TargetEntry:
        zone = make_zone(zone_id=row[0], side=side, price_low=row[1], price_high=row[2])
        return TargetEntry(
            zone=zone, zone_low=row[1], zone_high=row[2], distance_atr=row[3], relevance=row[4]
        )

    return TargetMap(
        above=tuple(_entry(row, LiquiditySide.BUY_SIDE) for row in above),
        below=tuple(_entry(row, LiquiditySide.SELL_SIDE) for row in below),
    )


def make_market_state(
    *,
    bias: HTFBias = HTFBias.BULLISH,
    data_quality: DataQuality = DataQuality.HEALTHY,
    event_time: datetime = ANCHOR_TIME,
    regime: MarketRegime = MarketRegime.TREND_PULLBACK,
) -> MarketStateSnapshot:
    """لقطة حالة §9 موثوقة الحقول عند المرسِم."""
    return MarketStateSnapshot(
        instrument=INSTRUMENT,
        timeframe=TIMEFRAME,
        event_time=event_time,
        regime=regime,
        htf_bias=bias,
        volatility_percentile=60.0,
        data_quality=data_quality,
    )


def make_volatility(atr: float = ATR, *, bar_time: datetime = ANCHOR_TIME) -> VolatilityState:
    """حالة تقلب §16 بـATR معلن — مقياس الهندسات."""
    return VolatilityState(
        atr=atr,
        atr_percentile=0.5,
        realized_vol=None,
        range_expansion_percentile=None,
        vol_of_vol=None,
        gap_shock=None,
        spread_to_range=None,
        expected_holding_vol_1h=None,
        expected_holding_vol={},
        data_sufficient=True,
        bar_time=bar_time,
        warmup_bars_remaining=0,
    )


def make_candle(
    index: int,
    *,
    open_: float = 60_000.0,
    high: float = 60_050.0,
    low: float = 59_950.0,
    close: float = 60_000.0,
    volume: float = 100.0,
) -> Candle:
    """شمعة 1m مغلقة عند الدقيقة ``index`` بعد المرسِم — قيم مشتقة صحيحة.

    القيم المشتقة تُحسب من OHLC الحقيقي لا تُخترع: المدى والجسم
    والفتيلان وموقع الإغلاق والمدى الحقيقي والتقلب المحقق.
    """
    bar_time = ANCHOR_TIME + timedelta(minutes=index)
    price_range = high - low
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    body_fraction = body / price_range if price_range > 0 else 0.0
    close_location = (close - low) / price_range if price_range > 0 else 0.5
    return Candle(
        instrument_id=INSTRUMENT,
        timeframe=TIMEFRAME,
        bar_time=bar_time,
        session_id="sess-001",
        quality=DataQuality.HEALTHY,
        is_closed=True,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        range=price_range,
        body_size=body,
        upper_wick=upper,
        lower_wick=lower,
        body_fraction=body_fraction,
        close_location_value=close_location,
        true_range=price_range,
        realized_volatility=price_range / close if close > 0 else 0.0,
    )


#: جلسة مرجعية — للاستيراد في الاختبارات التي تفحص قراءة الجلسة لاحقًا.
SESSION_TYPE = SessionType.UTC_DAY
