"""كاشف عناقيد الاختلال الصفّي المتكررة — §12.6 + §20
BUY/SELL_IMBALANCE_CLUSTER (المهمة 4-c).

نص §12.6: «An isolated imbalance has low directional weight. Repeated
imbalances aligned with displacement and structure carry more evidence.»
— هذا الكاشف الترجمة التشغيلية للشطر الأول: يرصد **العناقيد** لا
الاختلالات المعزولة، ويخزّن الخام (عدادات الشريط) والأهمية السياقية
معًا (حمولة 4-a).

**تصنيف الشريط (من عداداته اللحظية §8.2)**: الشريط «اختلالي بجهة»
إذا بلغ عدّاد جهته ``min_imbalance_count`` **وكان الغالب من
العدّادين** (``buy_imbalance_count > sell_imbalance_count`` أو
العكس) — تعادل العدّادين عند الحدّ فأعلى لا جهة حاسمة فيه فيعدّ
محايدًا (يكسر أي سلسلة). العدادات يحسبها بنّاء الفوتبرنت (4-b)
بمنهجية المقارنة الصفّية المباشرة عند ``IMBALANCE_RATIO``
(:mod:`orderflow.rows`) — الكاشف يستهلكها كما هي ولا يعيد اشتقاقها.

**آلة السلسلة (متتالية بجهة واحدة)**:

- الشريط المحايد (لا اختلال أو تعادل) يغلق السلسلة الجارية بلا بث إن
  لم تبلغ ``min_cluster_bars`` ويصفّر العدّ (سلسلة جديدة تبدأ من
  الصفر عند أول شريط اختلالي لاحق).
- الشريط المختل بالجهة المعاكسة يكسر السلسلة السابقة ويبدأ سلسلة
  معاكسة هو أول أشرطتها.
- **البث عند اكتمال الشرط حصرًا (§26.3)**: عند اللحظة التي يبلغ فيها
  طول السلسلة ``min_cluster_bars`` يبث حدث واحد للعنقيد عند
  ``bar_time`` **آخر شريط فيه** — لا نظرة مستقبلية: الإعلان لا ينتظر
  انكسار السلسلة.
- **النمو المتواصل (§27 لا رفرفة)**: العنقيد المبث ينتهي عند إعلانه
  حصرًا — الأشرطة اللاحقة بالجهة نفسها سلسلة **جديدة** تُعدّ من
  الصفر وقد تكمل عنقيدًا آخر مستقلًا؛ لا إعادة بث لنفس الأشرطة أبدًا
  ولا تمديد لأثر رجعي.

**``max_row_ratio`` (أمانة القياس الصفّي)** — أقصى
:func:`orderflow.rows.row_ratio` عبر صفوف أشرطة العنقيد، على ثلاث
درجات موثقة:

1. الأقصى بين الصفوف المصنّفة **بجهة العنقيد** عند ``ratio_min``
   (:func:`orderflow.rows.row_imbalance_side`) — القياس الأول؛
2. احتياطًا إن لم يُصنَّف أي صف بالجهة عند الحد (تباعد حد الكاشف عن
   منهجية بناء العدادات): الأقصى بين الصفوف **المهيمنة** بالجهة بأي
   نسبة (شراء > بيع لشرائي — قياس خام غير مصفّى)؛
3. وإن لم يوجد صف مهيمن بالجهة أصلًا (مدخل متناقض): القيمة الحيادية
   ``1.0`` — غياب هيمنة معلن لا قيمة مختلقة.

**تشبّع الصف الأحادي**: ``row_ratio`` تعيد ``inf`` للصف الذي طبعت فيه
جهة واحدة فقط (صف أحادي الجانب — واقعي تمامًا في aggTrades)؛ حمولة
``max_row_ratio`` منتهية بالعقد (``PositiveFloat`` في 4-a) فتُشبَّع
النسبة غير المنتهية إلى :data:`SATURATED_ROW_RATIO` — تمثيل «هيمنة
غير محدودة» بأقصى نسبة منتهية قابلة للتمثيل، معلنًا لا صامتًا.

**حقن توائم الإزاحة (§12.6 «aligned with displacement»)**:
``displacement_aligner`` معامل اختياري — نداء يقرر هل تتوائم أشرطة
العنقيد مع إزاحة/بنية مؤكدة. **لا يستورد الكاشف حزمة structure
أبدًا** (عقد استقلال الكواشف في import-linter: الدمج مسؤولية الطبقة
الأعلى وحدها) — المحقِن (طبقة التجميع لاحقًا) يقرر التوائم؛
``None`` (الافتراضي) ⇒ ``aligned_with_displacement=False`` دائمًا —
قيمة صادقة غير مدركة، لا تخمين.

**الحوارس (نمط كواشف المرحلة 3)**: أشرطة مغلقة فقط (§27 فصل المتطور
عن المؤكد)، هوية واحدة (أداة/إطار تُلتقط من أول شريط)، وترتيب
``bar_time`` تصاعدي قطعي (التكرار والتأخر يكسران آلة الحالة
التتابعية فيُرفضان رفضًا صاخبًا). الحارس محلي خاص بالحزمة — عمدًا لا
يُستورد من ``structure._guards`` (عقد الاستقلال يمنع؛ التكرار الموثق
أهون من كسر الطبقة).

**الحتمية الصرفة**: آلة حالة تتابعية بلا طوابع استقبال ولا عشوائية
ولا معرفات تُولَّد — نفس الأشرطة بالترتيب ⇒ نفس الأحداث بالترتيب
(المعرّف يخلقه الناشر لاحقًا بعقد §32). المحقِن (``aligner``)
مسؤولية حتميته على المستدعي.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from sys import float_info

from schemas import EventType, FootprintBar, ImbalanceClusterEventPayload, ImbalanceSide

from orderflow.events import EmittedEvent
from orderflow.rows import IMBALANCE_RATIO, BarRows, row_imbalance_side, row_ratio

__all__ = [
    "SATURATED_ROW_RATIO",
    "ImbalanceClusterConfig",
    "ImbalanceClusterDetector",
]

#: قيمة تشبّع النسبة الصفّية غير المنتهية — الصف الأحادي الجانب (جهة
#: واحدة فقط مطبوعة عند سعر) نسبته ``inf`` عند ``row_ratio``، وحمولة
#: ``max_row_ratio`` منتهية بالعقد (4-a: ``PositiveFloat``)، فتمثَّل
#: الهيمنة غير المحدودة بهذه القيمة المعلنة. أي نسبة منتهية محسوبة
#: أصغر منها أو تساويها بالتمثيل — لا تعارض.
SATURATED_ROW_RATIO: float = float_info.max


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class ImbalanceClusterConfig:
    """إعداد كاشف عناقيد الاختلال — نقاط انطلاق إعدادية للتقييم
    والمعايرة (ليست توصيات تداول).

    - ``min_imbalance_count``: حد العدّاد في الشريط كي يُعد «شريطًا
      اختلاليًا» بجهته الغالبة (§12.6 «repeated»).
    - ``min_cluster_bars``: أقل أشرطة متتالية بجهة واحدة يكتمل بها
      العنقيد (كثافة الاختلال — القياس الأول للحدث في §20).
    - ``ratio_min``: حد نسبة الاختلال الصفّي للعمل الصفّي
      (``max_row_ratio``) — يُمرَّر إلى ``row_imbalance_side``؛ ينبغي
      مواءمته مع منهجية بناء العدادات (``IMBALANCE_RATIO`` افتراضيًا).
    """

    min_imbalance_count: int = 2
    min_cluster_bars: int = 3
    ratio_min: float = IMBALANCE_RATIO

    def __post_init__(self) -> None:
        if self.min_imbalance_count < 1:
            raise ValueError(
                f"min_imbalance_count يجب أن يكون ≥ 1 (شريط اختلالي يحتاج اختلالًا "
                f"واحدًا على الأقل)؛ وُجد {self.min_imbalance_count}"
            )
        if self.min_cluster_bars < 1:
            raise ValueError(
                f"min_cluster_bars يجب أن يكون ≥ 1 (حمولة العنقيد bar_count ≥ 1)؛ "
                f"وُجد {self.min_cluster_bars}"
            )
        if not isfinite(self.ratio_min) or not self.ratio_min > 1.0:
            raise ValueError(f"ratio_min يجب أن تكون نسبة محدودة > 1.0؛ وُجد {self.ratio_min!r}")


# ═════════════════════════════ الكاشف ═════════════════════════════


class ImbalanceClusterDetector:
    """كاشف عناقيد الاختلال الموضعي لكل (أداة، إطار) — أشرطة مغلقة فقط.

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اتركه يلتقط الهوية من أول شريط)
    وغذّه كل ``BarRows`` مقفلًا بترتيبه الزمني؛ عند كل شريط يعيد قائمة
    فارغة أو حدثًا واحدًا حصرًا (اكتمال عنقيد عند هذا الشريط بالضبط).
    انظر عقود الموديول كاملة (آلة السلسلة ودرجات ``max_row_ratio``
    والتشبّع وحقن التوائم والحوارس).
    """

    def __init__(
        self,
        config: ImbalanceClusterConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        displacement_aligner: Callable[[Sequence[FootprintBar]], bool] | None = None,
    ) -> None:
        if (instrument_id is None) != (timeframe is None):
            raise ValueError(
                "الهوية تُمرَّر كاملة (أداة وإطار معًا) أو تُترك لتُلتقط من أول "
                "شريط — تمرير أحدهما وحده لبسٌ صامت لا يُقبل"
            )
        self._config = config if config is not None else ImbalanceClusterConfig()
        self._instrument_id = instrument_id
        self._timeframe = timeframe
        self._last_bar_time: datetime | None = None
        self._aligner = displacement_aligner
        self._chain: list[BarRows] = []
        self._chain_side: ImbalanceSide | None = None

    # ── الخصائص ──

    @property
    def config(self) -> ImbalanceClusterConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شريط إن لم تُمرر في البناء."""
        return self._instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شريط إن لم يمرر في البناء."""
        return self._timeframe

    # ── التغذية ──

    def update(self, bar_rows: BarRows) -> list[EmittedEvent]:
        """استهلاك شريط مقفل — قائمة فارغة أو حدث اكتمال عنقيد واحد حصرًا.

        الترتيب الداخلي (حتمي موثق): الحوارس ← تصنيف جهة الشريط من
        عداداته ← تحديث السلسلة (امتداد/كسر/تصفير) ← البث عند اكتمال
        ``min_cluster_bars`` حصرًا (ثم تُقفل السلسلة — لا نمو لأثر رجعي).
        """
        bar = bar_rows.bar
        self._guard_bar(bar)
        side = self._bar_side(bar)
        if side is None:
            # محايد: يغلق السلسلة بلا بث إن لم تكتمل (اكتملتها بثت قبلًا).
            self._chain = []
            self._chain_side = None
            return []
        if self._chain_side is side:
            self._chain.append(bar_rows)
        else:
            # بداية سلسلة (لا سلسلة جارية) أو كسر بجهة معاكسة — العدّ من الصفر.
            self._chain = [bar_rows]
            self._chain_side = side
        if len(self._chain) >= self._config.min_cluster_bars:
            return [self._emit_cluster()]
        return []

    # ── الداخلية ──

    def _bar_side(self, bar: FootprintBar) -> ImbalanceSide | None:
        """جهة اختلال الشريط — الغالبة من العدّادين عند بلوغ الحد.

        ``None`` إذا لم يبلغ أي عدّاد الحد، أو تعادل العدّادان (لا جهة
        حاسمة — الشريط محايد يكسر السلسلة).
        """
        buy = bar.buy_imbalance_count
        sell = bar.sell_imbalance_count
        if buy > sell and buy >= self._config.min_imbalance_count:
            return ImbalanceSide.BUY
        if sell > buy and sell >= self._config.min_imbalance_count:
            return ImbalanceSide.SELL
        return None

    def _emit_cluster(self) -> EmittedEvent:
        """بناء حدث العنقيد الجاري عند إعلانه وإقفال سلسلته (§27).

        ``bar_time`` آخر شريط في العنقيد (الشريط الذي أكمل الشرط —
        لا-نظرة-مستقبلية §26.3)، و``total_imbalances`` مجموع عدادات جهة
        العنقيد عبر أشرطته (الخام §12.6)، و``max_row_ratio`` بدرجاته
        الثلاث الموثقة في وثائق الموديول.
        """
        side = self._chain_side
        assert side is not None, "البث لا يُستدعى إلا بسلسلة حاملة جهة"
        bars = [bar_rows.bar for bar_rows in self._chain]
        total_imbalances = sum(
            bar.buy_imbalance_count if side is ImbalanceSide.BUY else bar.sell_imbalance_count
            for bar in bars
        )
        aligned = self._aligner(tuple(bars)) if self._aligner is not None else False
        last = bars[-1]
        payload = ImbalanceClusterEventPayload(
            instrument=last.instrument_id,
            timeframe=last.timeframe,
            bar_time=last.bar_time,
            side=side,
            bar_count=len(bars),
            total_imbalances=total_imbalances,
            max_row_ratio=self._max_row_ratio(self._chain, side),
            aligned_with_displacement=bool(aligned),
        )
        event_type = (
            EventType.BUY_IMBALANCE_CLUSTER
            if side is ImbalanceSide.BUY
            else EventType.SELL_IMBALANCE_CLUSTER
        )
        # العنقيد المبث ينتهي عند إعلانه — سلسلة جديدة تبدأ (§27).
        self._chain = []
        self._chain_side = None
        return EmittedEvent(event_type=event_type, event_time=last.bar_time, payload=payload)

    def _max_row_ratio(self, chain: Sequence[BarRows], side: ImbalanceSide) -> float:
        """أقصى نسبة صفّية بجهة العنقيد — الدرجات الثلاث الموثقة.

        ``row_ratio`` يرفض الأحجام السالبة صاخبًا (عقد rows) ويعيد
        ``None`` للصف بلا تداول (يُتجاوز) و``inf`` للأحادي الجانب
        (يُشبَّع إلى :data:`SATURATED_ROW_RATIO`).
        """
        best_classified: float | None = None
        best_dominant: float | None = None
        for bar_rows in chain:
            for row in bar_rows.rows:
                ratio = row_ratio(row.buy_volume, row.sell_volume)
                if ratio is None:
                    continue  # صف بلا تداول — لا مقارنة (عقد rows)
                if row_imbalance_side(
                    row.buy_volume, row.sell_volume, self._config.ratio_min
                ) is side and (best_classified is None or ratio > best_classified):
                    best_classified = ratio
                dominant = (
                    row.buy_volume > row.sell_volume
                    if side is ImbalanceSide.BUY
                    else row.sell_volume > row.buy_volume
                )
                if dominant and (best_dominant is None or ratio > best_dominant):
                    best_dominant = ratio
        if best_classified is not None:
            return min(best_classified, SATURATED_ROW_RATIO)
        if best_dominant is not None:
            # احتياط الدرجة الثانية — مدخلات متناقضة مع الحد: قياس خام غير مصفّى.
            return min(best_dominant, SATURATED_ROW_RATIO)
        return 1.0  # الدرجة الثالثة: لا صف مهيمن بالجهة أصلًا — حيادي معلن

    def _guard_bar(self, bar: FootprintBar) -> None:
        """حارس التدفق المحلي — إقفال وهووية وترتيب (عقود الموديول).

        لا حارس حالة تقلب هنا: الكاشف لا يستهلك عتبات سعرية أصلًا
        (نِسَب صرفة — §16 لا ينطبق).
        """
        if not bar.is_closed:
            raise ValueError(
                "الكاشف يستهلك الأشرطة المغلقة فقط (§27 فصل المتطور عن المؤكد) — "
                "الشريط المتطور لا يدخل آلة سلاسل العناقيد"
            )
        if self._instrument_id is None:
            self._instrument_id = bar.instrument_id
            self._timeframe = bar.timeframe
        else:
            expected_instrument = self._instrument_id
            expected_timeframe = self._timeframe
            assert expected_timeframe is not None  # الهوية تثبت معًا أو تغيب معًا
            if bar.instrument_id != expected_instrument:
                raise ValueError(
                    f"خلط أدوات على كاشف واحد: استُهل على {expected_instrument!r} "
                    f"ووصل شريط {bar.instrument_id!r} — أنشئ كاشفًا لكل (أداة، إطار)"
                )
            if bar.timeframe != expected_timeframe:
                raise ValueError(
                    f"خلط أطر زمنية على كاشف واحد: استُهل على {expected_timeframe!r} "
                    f"ووصل شريط {bar.timeframe!r} — أنشئ كاشفًا لكل (أداة، إطار)"
                )
        last = self._last_bar_time
        if last is not None:
            if bar.bar_time == last:
                raise ValueError(
                    f"تكرار bar_time لشريط مقفل سبق استهلاكه: {bar.bar_time} — "
                    "التكرار خطأ قانوني عند المغلقات"
                )
            if bar.bar_time < last:
                raise ValueError(
                    f"شريط متأخر (bar_time أقدم من آخر مقفل): {bar.bar_time} بعد "
                    f"{last} — آلة السلاسل التتابعية ترفض المتأخر رفضًا صريحًا"
                )
        self._last_bar_time = bar.bar_time
