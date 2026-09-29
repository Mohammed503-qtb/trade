"""مساعدات مشتركة لاختبارات التدفق (المهمة 4-c) — بناة أشرطة فوتبرنت
وصفوفها (نمط ``_structure_fixtures``).

الباني يشتق كل حقول ``FootprintBar`` (§8.2) من صفوف خام متسقة
(أسعار تصاعدية صارمة وأحجام منتهية غير سالبة) فلا يُبنى مدخل مرفوض
أبدًا، والقيم المختارة تجعل المقاييس قابلة للحساب اليدوي في التوقعات.

قرارات موثقة:

- **العدادات تُشتق افتراضيًا من الصفوف** بمنهجية ``rows.py`` نفسها
  (``row_imbalance_side`` عند ``IMBALANCE_RATIO``) — التجاوز الصريح
  لبناء الحالات المرضية المقصودة (مدخلات متناقضة لاختبار الاحتياطات).
- **منطقة القيمة الافتراضية = مدى صفوف الشريط كاملًا** (‎val = أدنى
  سعر، ‎vah = أعلاه) — أبسط قيمة صادحة قابلة للحساب اليدوي؛ الاختبارات
  التي تقيس حصة منطقة القيمة تمرر فاصلًا صريحًا.
- **POC = أثقل صف** (أكبر حجم كلي) وعند التعادل الأدنى سعرًا — قاعدة
  حتمية موثقة (كسر التعادل مسألة منهجية البنّاء 4-b، والاختبار يحتاج
  قيمة واحدة قابلة للتوقع).
- **الشريط صفر التداول** جائز في ``make_footprint_bar`` (حصصه 0.0
  معلنة — حالة بيانات غير كافية يسمحها المخطط) ومرفوض في
  ``make_bar_rows`` (عقد ``rows.py``: الشريط بلا صفقات لا يُبنى).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from math import isfinite

from orderflow.rows import (
    IMBALANCE_RATIO,
    METHODOLOGY_AGGTRADE_TAKER,
    BarRows,
    FootprintRow,
    row_imbalance_side,
)
from schemas import DataQuality, FootprintBar, ImbalanceSide

__all__ = [
    "BASE_TIME",
    "INSTRUMENT",
    "SOURCE_FEED",
    "TIMEFRAME",
    "make_bar_rows",
    "make_footprint_bar",
]

#: طابع الشريط الأولى — الدقائق ترقّم الأشرطة (إطار الدقيقة).
BASE_TIME = datetime(2026, 1, 5, tzinfo=UTC)
INSTRUMENT = "BINANCE_USDM:BTCUSDT"
TIMEFRAME = "1m"
#: مصدر تغذية الاختبار — وسم §12.7 إلزامي في كل سجل.
SOURCE_FEED = "binance-usdm-aggtrades-test"


def make_footprint_bar(
    index: int,
    rows_spec: tuple[tuple[float, float, float], ...],
    *,
    buy_imbalance_count: int | None = None,
    sell_imbalance_count: int | None = None,
    val: float | None = None,
    vah: float | None = None,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> FootprintBar:
    """شريط فوتبرنت كامل الحقول مشتق من صفوفه — (السعر، شراء، بيع).

    :raises ValueError: صفوف فارغة، أسعار غير تصاعدية صارمة، أحجام أو
        أسعار غير صالحة، فاصل قيمة ناقص الطرفين أو معكوس.
    """
    if not rows_spec:
        raise ValueError("الشريط يحتاج صفًا واحدًا على الأقل — rows_spec فارغة")
    rows = tuple(
        FootprintRow(price=b, buy_volume=buy, sell_volume=sell) for b, buy, sell in rows_spec
    )
    for row in rows:
        if not isfinite(row.price) or row.price <= 0.0:
            raise ValueError(f"سعر صف غير صالح: {row.price!r} — المتوقع موجب منتهٍ")
        if not isfinite(row.buy_volume) or row.buy_volume < 0.0:
            raise ValueError(f"حجم شراء سالب/فاسد: {row.buy_volume!r}")
        if not isfinite(row.sell_volume) or row.sell_volume < 0.0:
            raise ValueError(f"حجم بيع سالب/فاسد: {row.sell_volume!r}")
    for lower, upper in pairwise(rows):
        if not lower.price < upper.price:
            raise ValueError(
                f"الصفوف يجب أن تكون تصاعدية صارمة بالسعر (عقد BarRows): "
                f"{lower.price!r} ثم {upper.price!r}"
            )
    if (val is None) != (vah is None):
        raise ValueError("فاصل منطقة القيمة يمرَّر طرفيه معًا أو يترك كليًا")
    val_final = rows[0].price if val is None else val
    vah_final = rows[-1].price if vah is None else vah
    if not isfinite(val_final) or not isfinite(vah_final) or val_final <= 0.0 or vah_final <= 0.0:
        raise ValueError(f"حدا منطقة القيمة غير صالحين: val={val_final!r} vah={vah_final!r}")
    if val_final > vah_final:
        raise ValueError(f"منطقة قيمة معكوسة: val={val_final!r} > vah={vah_final!r}")
    buy_volume = sum(row.buy_volume for row in rows)
    sell_volume = sum(row.sell_volume for row in rows)
    total_volume = buy_volume + sell_volume
    if buy_imbalance_count is None or sell_imbalance_count is None:
        derived_buy = 0
        derived_sell = 0
        for row in rows:
            side = row_imbalance_side(row.buy_volume, row.sell_volume, IMBALANCE_RATIO)
            if side is ImbalanceSide.BUY:
                derived_buy += 1
            elif side is ImbalanceSide.SELL:
                derived_sell += 1
        if buy_imbalance_count is None:
            buy_imbalance_count = derived_buy
        if sell_imbalance_count is None:
            sell_imbalance_count = derived_sell
    # POC: أثقل صف؛ عند التعادل الأدنى سعرًا (قاعدة حتمية موثقة).
    poc = max(rows, key=lambda row: (row.total_volume, -row.price)).price
    deltas = [row.delta for row in rows]
    return FootprintBar(
        instrument_id=instrument_id,
        timeframe=timeframe,
        bar_time=bar_time if bar_time is not None else BASE_TIME + timedelta(minutes=index),
        quality=DataQuality.HEALTHY,
        is_closed=is_closed,
        source_feed=SOURCE_FEED,
        methodology=METHODOLOGY_AGGTRADE_TAKER,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        total_volume=total_volume,
        delta=buy_volume - sell_volume,
        buy_share=buy_volume / total_volume if total_volume > 0.0 else 0.0,
        sell_share=sell_volume / total_volume if total_volume > 0.0 else 0.0,
        poc=poc,
        vah=vah_final,
        val=val_final,
        row_count=len(rows),
        buy_imbalance_count=buy_imbalance_count,
        sell_imbalance_count=sell_imbalance_count,
        max_positive_delta_row=(
            rows[deltas.index(max(deltas))].price if max(deltas) > 0.0 else None
        ),
        max_negative_delta_row=(
            rows[deltas.index(min(deltas))].price if min(deltas) < 0.0 else None
        ),
    )


def make_bar_rows(
    index: int,
    rows_spec: tuple[tuple[float, float, float], ...],
    *,
    buy_imbalance_count: int | None = None,
    sell_imbalance_count: int | None = None,
    val: float | None = None,
    vah: float | None = None,
    instrument_id: str = INSTRUMENT,
    timeframe: str = TIMEFRAME,
    is_closed: bool = True,
    bar_time: datetime | None = None,
) -> BarRows:
    """شريط فوتبرنت مع صفوفه — مدخل الكواشف الصفّية (عقد الواجهة 4-a).

    يرفض الشريط صفر التداول (عقد ``rows.py``: الشريط بلا صفقات لا
    يُبنى)؛ لبقية العقود انظر :func:`make_footprint_bar`.
    """
    bar = make_footprint_bar(
        index,
        rows_spec,
        buy_imbalance_count=buy_imbalance_count,
        sell_imbalance_count=sell_imbalance_count,
        val=val,
        vah=vah,
        instrument_id=instrument_id,
        timeframe=timeframe,
        is_closed=is_closed,
        bar_time=bar_time,
    )
    if bar.total_volume <= 0.0:
        raise ValueError(
            f"شريط بلا صفقات لا يُبنى (عقد BarRows): {bar.bar_time} — كل الصفوف صفر التداول"
        )
    return BarRows(bar=bar, rows=tuple(FootprintRow(b, buy, sell) for b, buy, sell in rows_spec))
