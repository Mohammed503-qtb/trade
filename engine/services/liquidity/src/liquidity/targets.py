"""خريطة الأهداف — الأهداف مناطق لا نقاط على الجانبين (§10.5).

المصدر: §10.5 («بعد إنشاء إعداد نشط يحسب المحرك أهداف السيولة ذات الصلة
التالية على الجانبين؛ توليد السيناريوهات يستخدم هذه الأهداف لتقدير المسار
المعقول ومسافة الإبطال»)، §24.1 (entry_zone/targets مناطق)، §10.3 (القرب
والأهمية — مدخلات الصلة)، §20 (لا حدث هنا — هذه قراءة خريطة لا كشف).

العقود الموثقة في هذه الوحدة (تُختبر حرفيًا في tests/unit/test_targets.py):

- **الأهداف مناطق لا نقاط**: كل هدف = فاصل المنطقة ممدودًا بنصف عرض
  ``TARGET_ZONE_HALF_WIDTH`` التطبيعي (``atr × multiplier``) من كل جانب —
  لا مستوى نقطي أبدًا (§10.5/§24.1).

- **العتبات التطبيعية (§16)**: نصف العرض ومسافة الصلة عتبتان من
  :class:`~market_state.volatility.VolatilityState` وحدها — لا ثابت سعري.

- **الحتمية الصرفة والترتيب الكلي**: الترتيب داخل كل جانب معلن حصرًا —
  ``relevance`` تنازليًا ثم ``distance_atr`` تصاعديًا ثم ``zone_id``
  تصاعديًا (كسر التعادل الحتمي) — فلا موضع في الخريطة يعتمد على ترتيب
  الإدخال أبدًا.

- **المعيار الحي عند القراءة**: ``relevance`` = ``importance_score``
  المخزونة × إشباع القرب الحي (خطي حتى مسافة ``ZONE_PROXIMITY`` ثم صفر) —
  الخريطة لقطة، والقِراءة تُقيَّم بالسعر الجاري المطلوب.

- **قبل توفر ATR موجب**: خريطة أهداف فارغة معلنة — المسافة المعيارية
  شرط وجود الهدف (لا مسافة مطلقة بديلة ولا قسمة على صفر).

التعريفات الحرفية:

- ``above``: مناطق BUY_SIDE لم يجاوز السعر قربَها صعودًا (``price ≤
  price_high``) — المستوى دخله السعر ظهر عليها بمسافة صفر؛ وما جاوزه
  السعر كليًا إلى الأعلى ليس هدفًا صاعدًا.
- ``below``: مناطق SELL_SIDE لم يجاوز السعر قربَها هبوطًا (``price ≥
  price_low``) — بالمثل.
- ``distance_atr`` = مسافة السعر من **حافة الدخول** (القريبة) مطبَّعة
  بالـATR، موجبة دائمًا (صفر داخل المنطقة) — إشارة «حافة الدخول» إلى
  أن أول لمس يقع على القرب.
- المناطق المستبعدة: كل ما ليس ACTIVE (اجتِيح أو استُهلك أو بُطل) — هدف
  المنطقة المستهلَكة ليست هي (§10.3 «whether the zone has already been
  consumed» و§31.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import LiquiditySide, LiquidityZone, ZoneState

__all__ = [
    "TargetEntry",
    "TargetMap",
    "TargetMapBuilder",
]


@dataclass(frozen=True)
class TargetEntry:
    """هدف واحد — منطقة ممدودة بمسافتها المعيارية وصلتها.

    ``zone`` لقطة المنطقة كما وصلت (مجمّدة)؛ ``zone_low``/``zone_high``
    فاصل الهدف الممدود؛ ``distance_atr`` مسافة الدخول المعيارية (≥ 0)؛
    ``relevance`` = الأهمية × إشباع القرب ∈ [0, 1] — درجة صلة خام لا
    احتمال (§10.3).
    """

    zone: LiquidityZone
    zone_low: float
    zone_high: float
    distance_atr: float
    relevance: float


@dataclass(frozen=True)
class TargetMap:
    """خريطة الأهداف الثنائية الجانب (§10.5) — صفا أهداف مرتبين حتميًا."""

    above: tuple[TargetEntry, ...]
    below: tuple[TargetEntry, ...]


def _target_order(entry: TargetEntry) -> tuple[float, float, str]:
    """مفتاح الترتيب الكلي الحتمي: صلة تنازليًا ثم مسافة تصاعديًا ثم المعرف."""
    return (-entry.relevance, entry.distance_atr, entry.zone.zone_id)


class TargetMapBuilder:
    """بناة خريطة الأهداف من لقطات الخريطة — قراءة صرفة بلا حالة.

    «قراءة» لا «كشف»: لا يبث حدثًا ولا يبدل حالة — يميز المناطق النشطة
    ويبني الأهداف على الجانبين (§10.5).
    """

    def build_targets(
        self,
        zones: Sequence[LiquidityZone],
        price: float,
        vol: VolatilityState,
        limit_per_side: int = 3,
    ) -> TargetMap:
        """بناء الأهداف على الجانبين عند سعر جاري وحالة تقلب معلنة.

        :param zones: لقطات خريطة السيولة (المرشِّح ACTIVE داخلي).
        :param price: السعر الجاري المرجعي.
        :param vol: حالة التقلب — مصدر نصف العرض ومسافة الصلة.
        :param limit_per_side: سقف الأهداف في كل جانب (يجب أن يكون ≥ 1).
        :raises ValueError: سقف غير موجب — عقد صاخب لا قص صامت.
        """
        if limit_per_side < 1:
            raise ValueError(f"limit_per_side يجب أن يكون ≥ 1؛ وُجد {limit_per_side}")
        atr = vol.atr
        if atr is None or atr <= 0.0:
            # بلا مقياس تقلب لا مسافات معيارية — خريطة فارغة معلنة (لا تقريب).
            return TargetMap(above=(), below=())
        half_width = vol.threshold(ThresholdKey.TARGET_ZONE_HALF_WIDTH)
        proximity = vol.threshold(ThresholdKey.ZONE_PROXIMITY)
        assert half_width is not None and proximity is not None  # atr موجب
        above: list[TargetEntry] = []
        below: list[TargetEntry] = []
        for zone in zones:
            if zone.state is not ZoneState.ACTIVE:
                continue  # المستهلَكة/الباطلة ليست أهدافًا (§10.3/§31.3)
            if zone.side is LiquiditySide.BUY_SIDE:
                if price > zone.price_high:
                    continue  # جاازها السعر صعودًا — ليست هدفًا صاعدًا
                distance_price = max(0.0, zone.price_low - price)
                entries = above
            else:
                if price < zone.price_low:
                    continue  # جاوزها السعر هبوطًا — ليست هدفًا هابطًا
                distance_price = max(0.0, price - zone.price_high)
                entries = below
            proximity_saturation = max(0.0, 1.0 - distance_price / proximity)
            entries.append(
                TargetEntry(
                    zone=zone,
                    zone_low=zone.price_low - half_width,
                    zone_high=zone.price_high + half_width,
                    distance_atr=distance_price / atr,
                    relevance=zone.importance_score * proximity_saturation,
                )
            )
        return TargetMap(
            above=tuple(sorted(above, key=_target_order)[:limit_per_side]),
            below=tuple(sorted(below, key=_target_order)[:limit_per_side]),
        )
