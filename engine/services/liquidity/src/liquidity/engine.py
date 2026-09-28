"""واجهة السيولة الموحدة — خريطة + كاشف اجتياح + أهداف لكل (أداة، إطار).

المصدر: §10 (محرك خريطة السيولة كتلة واحدة)، §10.4 (ترتيب الكشف قبل
تحديث الخريطة — شرط «منطقة قائمة مسبقًا»)، §10.5 (الأهداف بعد الخريطة)،
§31.3 (لكل زوج (أداة، إطار) حالة موضعية واحدة)، §27/§33.2 (شمع مغلقة فقط)،
§26.3 (لا-نظرة-مستقبلية).

العقود الموثقة (تُختبر في اختبارات الوحدة والخصائص الثلاث للوحدة):

- **ترتيب الشمعة (جوهر الشرط 1 §10.4)**: لكل شمعة — (1) تحقق القبول
  (مغلقة + هوية + ترتيب صاعد صارم) **قبل أي طفرة**، (2) كاشف الاجتياح
  يقيّم الشمعة ضد الخريطة القائمة [0..t−1]، (3) الخريطة تُحدَّث بالشمعة
  والمتطرفات — فلا تُجتاح منطقة بشمعة تأسيسها، وكل بث بعد إقفال شمعة
  الحسم حصرًا.

- **الهوية والترتيب**: الزوج (أداة، إطار) يُثبت عند البناء أو من أول
  شمعة؛ ``bar_time`` صاعدة صراحةً حصرًا — التكرار والتأخر مرفوضان رفضًا
  صاخبًا (لا تجاهل محسوب ولا إسقاط صامت).

- **الحتمية الصرفة**: نفس التسلسل ⇒ نفس الأحداث ونفس الخريطة ونفس
  الأهداف بالتطابق التام (مختبر بخصائص hypothesis).

الإعدادات الافتراضية الكاملة (``ZoneConfig`` و``SweepConfig``) نقاط انطلاق
إعدادية للتقييم والمعايرة — **ليست توصيات تداول**؛ لا ثابت سعري مطلق في
أي منها (كل مسافة سعرية عتبة تطبيعية من حالة التقلب).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from market_state.volatility import VolatilityState
from schemas import Candle, LiquidityZone, SweepClassification, Swing

from liquidity.sweep import EmittedEvent, SweepConfig, SweepDetector
from liquidity.targets import TargetMap, TargetMapBuilder
from liquidity.zones import LiquidityMapEngine, ZoneConfig

__all__ = [
    "LiquidityConfig",
    "LiquidityEngine",
]


# ╦═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class LiquidityConfig:
    """إعداد واجهة السيولة — تجميع إعدادَي الخريطة والكاشف.

    نقاط انطلاق إعدادية للتقييم والمعايرة (دفتر التجارب/الاستئصال) — ليست
    توصيات تداول؛ كل مقبض موثق في وحدته.
    """

    #: إعداد خريطة السيولة (المصادر ودورة الحياة والدرجات — §10.1-3).
    zones: ZoneConfig = field(default_factory=ZoneConfig)
    #: إعداد كاشف الاجتياح (النافذة والقبول وحصة العرض — §10.4).
    sweep: SweepConfig = field(default_factory=SweepConfig)


# ═════════════════════════════ الواجهة ═════════════════════════════


class LiquidityEngine:
    """واجهة السيولة الموضعية لكل (أداة، إطار) — تملك الخريطة والكاشف.

    الاستخدام: أنشئ واجهة لكل زوج (أو اتركها تلتقط الهوية من أول شمعة)
    وغذّها شمعة مغلقة + حالة تقلبها + متطرفاتها المؤكدة؛ يرجع ``update``
    أحداث هذا الشريط فقط (قاموس §20)، والقراءة عبر ``zones``/``zone``/
    ``targets``/``sweep_status``.

    :raises ValueError: كل عقود القبول الصاخبة (شمعة متطورة، خلط هوية،
        ترتيب غير صاعد، متطرف من إطار آخر، سقف أهداف غير موجب).
    """

    def __init__(
        self,
        config: LiquidityConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else LiquidityConfig()
        self._map = LiquidityMapEngine(
            self._config.zones,
            instrument_id=instrument_id,
            timeframe=timeframe,
        )
        self._detector = SweepDetector(self._map, self._config.sweep)
        self._targets = TargetMapBuilder()

    # ── الخصائص ──

    @property
    def config(self) -> LiquidityConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._map.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._map.timeframe

    @property
    def bars_consumed(self) -> int:
        """عدد الشموع المقبولة — ساعة الواجهة المشتركة مع خريطتها."""
        return self._map.bars_consumed

    # ── التغذية ──

    def update(
        self,
        candle: Candle,
        vol: VolatilityState | None,
        new_swings: Sequence[Swing] = (),
    ) -> list[EmittedEvent]:
        """استهلاك شمعة مغلقة — يرجع أحداث هذا الشريط وحدها (قاموس §20).

        الترتيب الداخلي (شرط 1 §10.4): تحقق القبول ← كشف الاجتياح على
        الخريطة القائمة ← تحديث الخريطة بالشمعة والمتطرفات. ``vol = None``
        (أول شمعة عند محرك التقلب الموازي) يمر كما هو — نفس عقد حزمة
        البنية (غياب ATR: لا عتبات ولا نوافذ اجتياح).
        """
        self._map.validate_bar(candle)
        events = self._detector.update(candle, vol)
        self._map.update(candle, vol, new_swings)
        return events

    # ── القراءة ──

    def zones(self) -> list[LiquidityZone]:
        """كل لقطات الخريطة بترتيب الإنشاء — تفويض للخريطة."""
        return self._map.zones()

    def zone(self, zone_id: str) -> LiquidityZone | None:
        """لقطة منطقة بمعرفها — None إذا لم توجد."""
        return self._map.zone(zone_id)

    def sweep_status(self, zone_id: str) -> SweepClassification | None:
        """آخر تصنيف اجتياح لمنطقة — None إذا لم توجد."""
        return self._map.sweep_status(zone_id)

    def targets(
        self,
        price: float,
        vol: VolatilityState,
        limit_per_side: int = 3,
    ) -> TargetMap:
        """أهداف السيولة التالية على الجانبين عند سعر جاري (§10.5)."""
        return self._targets.build_targets(self._map.zones(), price, vol, limit_per_side)
