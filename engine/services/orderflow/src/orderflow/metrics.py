"""المقاييس المتتالية عديمة الحالة لأشرطة الفوتبرنت — §12.1 (المهمة 4-c).

المقاييس **اللحظية** للشريط الواحد (buy/sell/delta/الحصص/POC/VAH/VAL
والعدادات) ساكنة في :class:`~schemas.market.FootprintBar` نفسه (§8.2 —
يبنيها بنّاء الفوتبرنت 4-b)؛ هذه الوحدة تبني **طبقة المتتالية**: قياسات
نافذية صرفة فوق تتابع الأشرطة:

- :func:`delta_trend` — §12.1 «delta trend»: ميل انحدار الدلتا الخطي
  عبر النافذة (اتجاه تشدّد العدوانية أو تراجعها).
- :func:`volume_concentration` — §12.1 «volume concentration»: التركّز
  **الزمني** للحجم عبر أشرطة النافذة (معامل هيرفيندال المطبّع).
- :func:`volume_concentration_rows` — التركّز **السعري**: حصة حجم منطقة
  القيمة ‎[val, vah]‎ من الحجم الكلي عبر صفوف النافذة (§12.5 «auction
  concentration» — أصدق تمثيل متاح لـ«أين تركز النشاط»).

**قرار تصميمي موثق (§12.1 «volume concentration»)**: تركّز الحجم عند
السعر — مجموع حجم صف POC — **غير قابل للقياس من ``FootprintBar``
وحده**: حقوله اللحظية (§8.2) لا تحمل أحجام الصفوف، فالتعريفان
المتاحان الأمينان هما: تركّز زمني بين الأشرطة من ``FootprintBar``
وحده، وتركّز سعري من :class:`~orderflow.rows.BarRows` حيث تتوفر
الأحجام عند كل سعر (عقد الواجهة المشترك 4-a). كلا التعريفين موثق
عند دالته، ولا يُدّعى على أي منهما أنه «حجم صف POC».

العقود:

- **دوال صرفة عديمة الحالة**: لا طوابع ولا عشوائية ولا أثر جانبي —
  نفس المدخلات ⇒ نفس المخرجات حرفيًا (الحتمية الصرفة).

- **لا-نظرة-مستقبلية بالبناء (§26.3)**: كل قياس دالة في الأشرطة
  المُمرَّرة وحدها؛ المستدعي يضمن أنها ما اقفل حتى اللحظة. المقاييس
  **لا تفرض** ``is_closed`` عمدًا: قياس النافذة الجارية حالة «متطورة»
  مشروعة للعرض (§27) — أما الكواشف المؤكدة فتستهلك المغلق حصرًا
  (انظر :mod:`orderflow.imbalance`).

- **الصخب في التحقق**: القيم غير المنتهية (nan/inf) والأحجام السالبة
  ومنطقة القيمة المعكوسة تُرفض بـ``ValueError`` عند الاستدعاء — لا
  قصّ صامت للمدخلات.

- **غياب القياس معلن بـ``None``**: النافذة الأقصر من حد القياس، أو
  نافذة صفر التداول كليًا (نمط :func:`orderflow.rows.row_ratio`: صف
  بلا تداول لا مقارنة فيه) — قيمة صادقة لا استثناء.

- **الحدود الرياضية مضمونة بالقصّ الموثق**: القياسات النسبية
  (‎[0, 1]‎) تُقصّ إلى نطاقها البرهاني لتحييد خطأ الفاصلة العائمة
  وحده — الحل الرياضي داخل النطاق بالبرهان، فالقصّ لا يصحح معنى بل
  يزيح ضجيج التمثيل.

- **الأصغر الكافي**: الحصص اللحظية (``buy_share``/``sell_share``)
  متاحة في الشريط نفسه ولا تُنسخ مساعدات عليها هنا.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from schemas import FootprintBar

from orderflow.rows import BarRows

__all__ = [
    "delta_trend",
    "volume_concentration",
    "volume_concentration_rows",
]


def _checked_volume(value: float, *, field: str, bar_time: object) -> float:
    """حجم منتهٍ غير سالب أو رفض صاخب — عقود الوحدة (لا قصّ للمدخلات)."""
    if not isfinite(value) or value < 0.0:
        raise ValueError(
            f"حجم {field} غير صالح عند الشريط {bar_time}: {value!r} — المتوقع كمية منتهية غير سالبة"
        )
    return value


def delta_trend(bars: Sequence[FootprintBar]) -> float | None:
    """ميل الدلتا عبر النافذة — §12.1 «delta trend».

    انحدار خطي بسيط (المربعات الصغرى) لدلت الأشرطة ``bar.delta`` على
    مواقعها بترتيبها (x = 0..n−1). الوحدة: **وحدات حجم دلتا لكل شريط**
    — موجب = العدوانية الشرائية تشتد عبر النافذة، سالب = البيعية تشتد،
    صفر = لا ميل.

    - ``None`` لأقل من شريطين (لا ميل لنقطة واحدة).
    - عند n = 2 الميل ``delta[1] − delta[0]`` بالضبط.
    - الدلتا غير المنتهية تُرفض بـ``ValueError`` (صخب التحقق).
    """
    n = len(bars)
    if n < 2:
        return None
    deltas: list[float] = []
    for bar in bars:
        if not isfinite(bar.delta):
            raise ValueError(
                f"دلتا غير منتهية عند الشريط {bar.bar_time}: {bar.delta!r} — "
                "المقاييس تفترض قيمًا منتهية"
            )
        deltas.append(bar.delta)
    x_center = (n - 1) / 2.0
    y_mean = sum(deltas) / n
    sxx = 0.0
    sxy = 0.0
    for i, delta in enumerate(deltas):
        dx = i - x_center
        sxx += dx * dx
        sxy += dx * (delta - y_mean)
    # sxx = n(n²−1)/12 > 0 لأي n ≥ 2 — لا قسمة على صفر بالبناء.
    return sxy / sxx


def volume_concentration(bars: Sequence[FootprintBar]) -> float | None:
    """تركّز الحجم **عبر أشرطة النافذة زمنيًا** — §12.1 «volume
    concentration» (التعريف القابل للقياس من ``FootprintBar`` وحده —
    انظر قرار الوحدة).

    معامل هيرفيندال المطبّع (normalized Herfindahl–Hirschman) لحصص حجم
    الأشرطة: ``H = Σ (v_i/V)²`` ثم التطبيع
    ``(H − 1/n) / (1 − 1/n)`` إلى ‎[0, 1]‎:

    - ‏0.0 = توزيع متساوٍ تمامًا بين أشرطة النافذة (لا تركّز)؛
    - ‏1.0 = كل نشاط النافذة في شريط واحد (تركّز تام).

    - ``None`` لأقل من شريطين (التركّز النسبي بين الأشرطة قياس مقارن
      يحتاج طرفين على الأقل) أو لنافذة صفر التداول كليًا.
    - الأحجام غير المنتهية/السالبية تُرفض بـ``ValueError``.
    - القيمة مقصوصة إلى ‎[0, 1]‎ (قصّ خطأ التمثيل الموثق — الحد برهاني).
    """
    n = len(bars)
    if n < 2:
        return None
    volumes = [
        _checked_volume(bar.total_volume, field="الشريط الكلي", bar_time=bar.bar_time)
        for bar in bars
    ]
    total = sum(volumes)
    if total <= 0.0:
        return None  # نافذة بلا تداول — لا مقارنة (نمط row_ratio)
    herfindahl = sum((v / total) ** 2 for v in volumes)
    floor = 1.0 / n
    normalized = (herfindahl - floor) / (1.0 - floor)
    return max(0.0, min(1.0, normalized))


def volume_concentration_rows(bars_with_rows: Sequence[BarRows]) -> float | None:
    """تركّز الحجم **السعري** عبر النافذة — حصة منطقة القيمة من الإجمالي.

    مجموع أحجام الصفوف داخل ‎[val, vah]‎ لكل شريط ÷ الحجم الكلي لصفوف
    النافذة كلها — إجابة «أين تركز النشاط سعريًا» (§12.5: POC/VAH/VAL
    تمثل auction concentration وحدود القيمة): 1.0 = كل تداول النافذة
    داخل مناطق القيمة، 0.0 = كله خارجها.

    هذا أصدق تمثيل متاح لتركّز الحجم عند السعر: الأحجام الصفّية تتوفر
    في :class:`~orderflow.rows.BarRows` وحده (عقد الواجهة 4-a) —
    ``FootprintBar`` لحده لا يحملها (قرار الوحدة).

    - ``None`` لنافذة فارغة أو صفر التداول كليًا (كل الصفوف بلا حجم).
    - الصفوف أحادية الجانب مسموحة (نسبتها inf عند
      :func:`orderflow.rows.row_ratio` — هنا يُستهلك الحجم فقط).
    - الحجوم غير المنتهية/السالبية والأسعار غير الصالحة ومنطقة القيمة
      المعكوسة (val > vah) تُرفض بـ``ValueError``؛ المساواة
      ``val == vah`` جائزة (منطقة قيمة منحلة بمستوى معزول — نمط
      السيولة نفسه).
    - القيمة مقصوصة إلى ‎[0, 1]‎ (قصّ خطأ التمثيل الموثق — الحد برهاني).
    """
    if not bars_with_rows:
        return None
    value_area_volume = 0.0
    total = 0.0
    for bar_rows in bars_with_rows:
        bar = bar_rows.bar
        val = bar.val
        vah = bar.vah
        if not isfinite(val) or not isfinite(vah):
            raise ValueError(
                f"حدا منطقة القيمة غير منتهيين عند الشريط {bar.bar_time}: val={val!r} vah={vah!r}"
            )
        if val > vah:
            raise ValueError(
                f"منطقة قيمة معكوسة عند الشريط {bar.bar_time}: "
                f"val={val!r} > vah={vah!r} — فساد مدخل يُرفض لا يُقاس"
            )
        for row in bar_rows.rows:
            price = row.price
            if not isfinite(price) or price <= 0.0:
                raise ValueError(
                    f"سعر صف غير صالح عند الشريط {bar.bar_time}: {price!r} — "
                    "المتوقع سعر موجب منتهٍ (عقد Price)"
                )
            volume = _checked_volume(
                row.buy_volume, field="شراء الصف", bar_time=bar.bar_time
            ) + _checked_volume(row.sell_volume, field="بيع الصف", bar_time=bar.bar_time)
            total += volume
            if val <= price <= vah:
                value_area_volume += volume
    if total <= 0.0:
        return None  # كل صفوف النافذة بلا تداول — لا مقارنة
    return max(0.0, min(1.0, value_area_volume / total))
