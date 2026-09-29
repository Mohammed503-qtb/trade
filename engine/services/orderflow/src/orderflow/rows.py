"""بدائيات صفوف الفوتبرنت المشتركة — عقد الواجهة بين بنّاء الفوتبرنت
(4-b) وكواشف التدفق الصفّية (4-c) (§8.2 + §12.6 + §12.7).

هذه الوحدة **عقد استقرار مبكر** كتبها المنسق (4-a): البنّاء والكواشف
المتوازية تبرمجان ضد هذه الواجهة الثابتة — لا واحدة منهما تعرّفها ولا
تعدّلها؛ أي تغيير لاحق يمر عبر المنسق بتوثيق.

العقود الموثقة:

- **الصف سجل خام مجمد**: سعر + حجم شراء عدواني + حجم بيع عدواني عند ذلك
  السعر داخل دلو الشريط (فوتبرنت aggTrades). لا أعلام ولا مشتقات —
  القياسات المشتقة (الدلتا/النسبة) دوال صرفة هنا، لا حالات مخزنة.

- **قاعدة الاختلال الصفّي (§12.6 «the feed's row-level buy/sell
  comparison rule»)**: منهجيتنا المؤسسة على aggTrades هي **المقارنة
  الصفّية المباشرة** — حجم الشراء العدواني عند السعر p مقابل حجم البيع
  العدواني عند السعر p نفسه (لا القطرية ثنائية الصفوف: تلك اصطلاح
  منصات فوتبرنت ذات سلم سعر/طلب مختلف؛ مصدرنا تصنيف تسبب مباشر بلا
  كتاب أوامر، فالمقارنة عند السعر ذاته هي الأمينة للمنهجية). الاختلال
  عند نسبة ``IMBALANCE_RATIO`` فأعلى (اصطلاح 3:1 الكلاسيكي — معامل
  إعدادي معلن لا توصية).

- **وسم المنهجية (§12.7)**: ``METHODOLOGY_AGGTRADE_TAKER`` هو المعرف
  القانوني لمنهجية «تصنيف الطرف المتسبب من aggTrades عبر علم
  buyer_is_maker» — يُكتب في ``methodology`` كل ``FootprintBar`` ولا
  يُخترع نص حر في أي مسار.

- **الحتمية**: ``rows`` في :class:`BarRows` مرتبة تصاعديًا بالسعر حصرًا
  (مسؤولية البنّاء — العقد موثق هنا) فأي تكرار إخراج للصفوف حتمي.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas import FootprintBar, ImbalanceSide

__all__ = [
    "IMBALANCE_RATIO",
    "METHODOLOGY_AGGTRADE_TAKER",
    "BarRows",
    "FootprintRow",
    "row_imbalance_side",
    "row_ratio",
]

#: معرف المنهجية القانوني (§12.7) — تصنيف الطرف المتسبب من aggTrades.
METHODOLOGY_AGGTRADE_TAKER = "aggtrade-taker-side-v1"

#: الحد الأدنى لنسبة الاختلال الصفّي (§12.6) — اصطلاح 3:1 الكلاسيكي؛
#: معامل إعدادي معلن قابل للمعايرة (ليس توصية تداول).
IMBALANCE_RATIO: float = 3.0


@dataclass(frozen=True)
class FootprintRow:
    """صف سعر واحد داخل شريط فوتبرنت — سجل خام مجمد بلا مشتقات مخزنة."""

    price: float
    buy_volume: float
    sell_volume: float

    @property
    def total_volume(self) -> float:
        """حجم الصف الكلي (شراء + بيع عدوانيَّي التسبب)."""
        return self.buy_volume + self.sell_volume

    @property
    def delta(self) -> float:
        """دلتا الصف (شراء − بيع) — مشتق صرف لا حالة."""
        return self.buy_volume - self.sell_volume


@dataclass(frozen=True)
class BarRows:
    """شريط فوتبرنت مكتمل مع صفوفه السعرية — مدخل الكواشف الصفّية.

    ``rows`` مرتبة تصاعديًا بالسعر حصرًا (عقد البنّاء) وغير فارغة (شريط
    بلا صفقات لا يُبنى أصلًا — الدلو الفارغ خارج نطاق الفوتبرنت).
    """

    bar: FootprintBar
    rows: tuple[FootprintRow, ...]


def row_ratio(buy: float, sell: float) -> float | None:
    """نسبة هيمنة الصف — ``max(buy/sell, sell/buy)``.

    ``None`` إذا كان الحجمان كلاهما صفرًا (صف بلا تداول: لا مقارنة)؛
    القيم السالبة تُرفض بValueError (حجم صفّي لا يكون سالبًا — الصخب
    في التحقق لا التصحيح الصامت).
    """
    if buy < 0.0 or sell < 0.0:
        raise ValueError(f"أحجام صفّية سالبة: buy={buy} sell={sell}")
    if buy == 0.0 and sell == 0.0:
        return None
    if sell == 0.0:
        return float("inf")
    if buy == 0.0:
        return float("inf")
    return buy / sell if buy >= sell else sell / buy


def row_imbalance_side(
    buy: float,
    sell: float,
    ratio_min: float = IMBALANCE_RATIO,
) -> ImbalanceSide | None:
    """جهة الاختلال الصفّي عند ``ratio_min`` — أو ``None`` إن لا اختلال.

    قاعدة المقارنة الصفّية المباشرة (انظر وثائق الوحدة): هيمنة أحد
    الجانبين على الآخر عند السعر نفسه بنسبة الحد فأعلى. ``ratio_min``
    يجب أن تكون محدودة موجبة (وإلا ValueError صاخب).
    """
    if not (ratio_min > 1.0 and ratio_min < float("inf")):
        raise ValueError(f"حد نسبة اختلال غير صالح: {ratio_min} (المتوقع > 1.0)")
    ratio = row_ratio(buy, sell)
    if ratio is None or ratio < ratio_min:
        return None
    return ImbalanceSide.BUY if buy > sell else ImbalanceSide.SELL
