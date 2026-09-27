"""كائنات السوق القانونية — حدث خام، شمعة، فوتبرنت، لقطة حالة السوق.

المصدر: §7.1 (عقد الوقت)، §8.1 (الشمعة)، §8.2+§12 (الفوتبرنت)،
مثال §32 (لقطة حالة السوق)، §27 (فصل المتطور عن المؤكد عبر is_closed).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ._types import (
    NonNegativeFloat,
    NonNegativeInt,
    Percentile,
    Price,
    UnitInterval,
    UTCDatetime,
)
from .enums import DataQuality, HTFBias, MarketRegime


class _MarketModel(BaseModel):
    """أساس موحد لكائنات السوق: عقود مجمّدة تمنع الحقول الغريبة."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TradeEvent(_MarketModel):
    """حدث خام مطبَّع (صفقة مفردة من aggTrades أو ما يعادلها) بعقد §7.1.

    buyer_is_maker علم تصنيف العدوانية الحقيقي من Binance aggTrades (D-02):
    True ⇒ البائع هو المعتدي، False ⇒ المشتري هو المعتدي، None لمصادر بلا علم.
    """

    event_time_utc: UTCDatetime
    receive_time_utc: UTCDatetime
    source_timeframe: str
    venue: str
    symbol: str
    feed_id: str
    sequence_id: str | None = None
    source_latency_ms: NonNegativeFloat | None = None

    price: Price
    quantity: NonNegativeFloat
    buyer_is_maker: bool | None = None


class Candle(_MarketModel):
    """الشمعة القانونية (§8.1 حرفيًا) + مفاتيح جدول candles (§31.2).

    is_closed يفصل المتطور عن المؤكد (§27): الشمعة غير المغلقة قد تتغير
    ولا تفوّض قرارًا حيًا. القيم المشتقة (range/body/wicks/…) يحسبها
    منشئ الشموع ويوثقها هنا كحقول مخزنة لا تُعاد اشتقاقها عرضًا.
    """

    # مفاتيح التعريف (جدول candles §31.2)
    instrument_id: str
    timeframe: str
    bar_time: UTCDatetime
    session_id: str
    quality: DataQuality
    is_closed: bool

    # OHLCV الخام (§8.1)
    open: Price
    high: Price
    low: Price
    close: Price
    volume: NonNegativeFloat

    # القيم المشتقة (§8.1 حرفيًا)
    range: NonNegativeFloat
    body_size: NonNegativeFloat
    upper_wick: NonNegativeFloat
    lower_wick: NonNegativeFloat
    body_fraction: UnitInterval
    close_location_value: UnitInterval
    true_range: NonNegativeFloat
    realized_volatility: NonNegativeFloat


class FootprintBar(_MarketModel):
    """شريط الفوتبرنت (§8.2 حرفيًا) + وسم المصدر والمنهجية (§12.7).

    buy/sell هنا تصنيف مبني على علم buyer-is-maker لمصدر بيانات محدد —
    ليس «كل مشتريي السوق مقابل كل بائعيه»؛ لذلك source_feed وmethodology
    إلزاميان في كل سجل (§12.7).
    """

    # مفاتيح التعريف (جدول footprint_bars §31.2)
    instrument_id: str
    timeframe: str
    bar_time: UTCDatetime
    quality: DataQuality
    is_closed: bool

    # وسم المصدر والمنهجية (§12.7)
    source_feed: str
    methodology: str

    # مقاييس التدفق (§8.2 حرفيًا — راجع §12.1/§12.2/§12.5)
    buy_volume: NonNegativeFloat
    sell_volume: NonNegativeFloat
    total_volume: NonNegativeFloat
    delta: float
    buy_share: UnitInterval
    sell_share: UnitInterval
    poc: Price
    vah: Price
    val: Price
    row_count: NonNegativeInt
    buy_imbalance_count: NonNegativeInt
    sell_imbalance_count: NonNegativeInt
    max_positive_delta_row: Price | None = None
    max_negative_delta_row: Price | None = None


class MarketStateSnapshot(_MarketModel):
    """لقطة حالة السوق المبثوثة (مثال §32 حرفيًا).

    سياق للقرار لا إشارة بذاتها: النظام والانحياز والتقلب والجودة عند لحظة.
    """

    instrument: str
    timeframe: str
    event_time: UTCDatetime
    regime: MarketRegime
    htf_bias: HTFBias
    volatility_percentile: Percentile
    data_quality: DataQuality
