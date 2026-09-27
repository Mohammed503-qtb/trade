"""مصنف جودة الشرائح (§7.4) — QualityTracker وسلّم الشدة وقواعد الانتقال.

تقسيم المسؤولية (قرار موثق): هذا الملف يحمل تصنيف الجودة وحده؛ خط التنقيح
(refine.py) يكتشف الإشارات على الأحداث ويبلّغها هنا — لا تكرارًا للاكتشاف
في الطرفين، فيبقى الملفان صغيري المسؤولية واضحي الحدود.

سلّم الشدة (SEVERITY_LADDER) مرتَّبًا من الأخف إلى الأثقل — أسوأ مساهم في
الشريحة يفوز (سيستهلكه منشئ الشموع 1.4 لوسم كل شمعة بأسوأ مساهم فيها).
الترتيب نفسه قرار موثق: HEALTHY أساس؛ DELAYED أهون التدهورات (لا يزال
مؤهلًا للقرار بموافقة صريحة §7.4)؛ ثم سلامة الترتيب (OUT_OF_ORDER)؛ ثم
سلامة العد (DUPLICATED)؛ ثم الاكتمال داخل الشريحة (PARTIAL)؛ ثم استمرارية
الزمن (GAP_DETECTED)؛ ثم طراوة الذيل (STALE)؛ ثم الثقة بالبيانات ذاتها
(QUARANTINED — بيانات مريبة/فشل تحقق)؛ وأخيرًا التوفر نفسه (UNAVAILABLE —
لا بيانات أصلًا). كل انتقال بين الجيران قرار حكمي موثق هنا.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from schemas import DataQuality, TradeEvent

# سلّم الشدة — tuple مرتب من الأخف إلى الأثقل (أسوأ مساهم يفوز في الشمعة)
SEVERITY_LADDER: tuple[DataQuality, ...] = (
    DataQuality.HEALTHY,
    DataQuality.DELAYED,
    DataQuality.OUT_OF_ORDER,
    DataQuality.DUPLICATED,
    DataQuality.PARTIAL,
    DataQuality.GAP_DETECTED,
    DataQuality.STALE,
    DataQuality.QUARANTINED,
    DataQuality.UNAVAILABLE,
)

#: رتبة كل حالة في السلّم — أداة مقارنة جاهزة للاستهلاك الخارجي (1.4)
SEVERITY_RANK: dict[DataQuality, int] = {state: rank for rank, state in enumerate(SEVERITY_LADDER)}


def worst_quality(*states: DataQuality) -> DataQuality:
    """أسوأ مساهم وفق سلّم الشدة — الوسم الذي تستحقه الشمعة/الشريحة (1.4).

    لا تقبل قائمة فارغة: «أسوأ لا شيء» غير معرَّف — خطأ برمجي يُرفع صراحة.
    """
    if not states:
        raise ValueError("worst_quality تتطلب حالة واحدة على الأقل")
    return max(states, key=SEVERITY_RANK.__getitem__)


def is_decision_eligible(state: DataQuality, allow_delayed: bool = False) -> bool:
    """§7.4 حرفيًا: فقط HEALTHY وDELAYED (بموافقة صريحة) يصلان معالجة القرار العادية.

    ``allow_delayed=True`` هي «الموافقة الصريحة» — كل حالة أخرى تحجب القرار
    أيا كانت درجتها الاتجاهية الظاهرة.
    """
    if state is DataQuality.HEALTHY:
        return True
    return allow_delayed and state is DataQuality.DELAYED


@dataclass(frozen=True, slots=True)
class QualityConfig:
    """عتبات التصنيف — افتراضيات موثقة قابلة للضبط بالحقن.

    - ``delayed_after_ms``: كمون مصدر يتجاوزه يرفع DELAYED (الافتراضي 1000ms —
      aggTrades الحية تصل عادة دون 300ms؛ تجاوز الثانية تدهور حقيقي ملموس).
    - ``stale_after_s``: صمت وصول يتجاوزه يرفع STALE (الافتراضي 10s — تدفق
      tick نشط يصمت عشر ثوانٍ كاملة يعني مشكلة تغذية لا سكونًا سوقيًا).
    - ``unavailable_after_s``: صمت يتجاوزه يرفع UNAVAILABLE (الافتراضي 60s —
      التغذية عمليًا ميتة). يجب أن يبقى أكبر من ``stale_after_s`` (مفروض أدنى).
    - ``healthy_recovery_events``: عدد الأحداث النظيفة المتتالية المطلوب
      للعودة إلى HEALTHY (الافتراضي 5 — توازن موثق بين الاستجابة ومنع الرفرفة).
    """

    delayed_after_ms: float = 1_000.0
    stale_after_s: float = 10.0
    unavailable_after_s: float = 60.0
    healthy_recovery_events: int = 5

    def __post_init__(self) -> None:
        if self.delayed_after_ms < 0.0:
            raise ValueError(f"delayed_after_ms لا يمكن أن يكون سالبًا: {self.delayed_after_ms}")
        if self.stale_after_s <= 0.0:
            raise ValueError(f"stale_after_s يجب أن يكون موجبًا: {self.stale_after_s}")
        if self.unavailable_after_s <= self.stale_after_s:
            raise ValueError(
                f"unavailable_after_s يجب أن يفوق stale_after_s (تصعيد لا تساوٍ): "
                f"{self.unavailable_after_s} ≤ {self.stale_after_s}"
            )
        if self.healthy_recovery_events < 1:
            raise ValueError(
                f"healthy_recovery_events يجب أن يكون ≥ 1: {self.healthy_recovery_events}"
            )


@dataclass
class _SymbolRecord:
    """حالة داخلية لكل رمز — لا تُصدَّر؛ الواجهة العلنية DataQuality وحدها."""

    degraded: DataQuality | None = None
    clean_streak: int = 0
    last_arrival: datetime | None = None
    last_event_time: datetime | None = None


def _worse(current: DataQuality | None, candidate: DataQuality) -> DataQuality:
    """أسوأ الحالتين وفق السلّم — None تعني «لا تدهور مسجل» (تعامل كـ HEALTHY)."""
    if current is None:
        return candidate
    return candidate if SEVERITY_RANK[candidate] > SEVERITY_RANK[current] else current


class QualityTracker:
    """يتتبع حالة الجودة لكل أداة (شريحة أداة/زمن §7.4) من إشارات خط التنقيح.

    قواعد الانتقال (موثقة، كلها أحادية الاتجاه نحو التدهور ثم تعافٍ واحد):
    - تكرار ⇒ DUPLICATED، خارج الترتيب ⇒ OUT_OF_ORDER، فجوة ⇒ GAP_DETECTED،
      فقد داخل الشريحة (قفزة تسلسل) ⇒ PARTIAL، فشل تحقق أداة/بيانات مريبة
      ⇒ QUARANTINED — كلها عبر report_* وتُمسك أسوأ تدهور غير متعافٍ بعد.
    - تأخر مصدر يتجاوز العتبة ⇒ DELAYED (داخل observe من source_latency_ms).
    - سكون وصول يتجاوز stale_after ⇒ STALE، ويتجاوز unavailable_after
      ⇒ UNAVAILABLE — تقييم كسول لحظة السؤال (state_for) عبر ساعة قابلة
      للحقن، لأن الحالات المعتمدة على الغياب لا تُطلقها الأحداث الغائبة.
    - عدم توفر بلا توفر سابق (رمز لم يُرصد له شيء إطلاقًا) ⇒ UNAVAILABLE.
    - عودة الاستقرار ⇒ HEALTHY: شرط العودة N حدثًا نظيفًا متتاليًا بلا أي
      إشارة تدهور جديدة (N = healthy_recovery_events). الحدث المتأخر المُدرج
      يبلَّغ إشارته أولًا (تصفير السلسلة) ثم يُرصد بنفسه — فيبدأ سلسلة النظافة
      ويحتاج N-1 حدثًا نظيفًا إضافيًا؛ هذا موثَّق بعمد: الحدث وإن تأخر ترتيبه
      فوروده دليل حياة للتغذية وكمونه يقاس مستقلًا.
    - STALE تراكب لا يحجب أسوأ منه (أسوأ مساهم يفوز)؛ UNAVAILABLE يفوز دائمًا.

    حدث نظيف = مقبول سليم الكمون؛ latency=None (مصدر بلا قياس) يُعامل نظيفًا —
    معلومة غائبة ليست اتهامًا.
    """

    def __init__(
        self,
        *,
        config: QualityConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """``clock`` قابل للحقن لاختبار STALE/DELAYED/UNAVAILABLE حتميًا بلا انتظار حقيقي."""
        self._config = config or QualityConfig()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, _SymbolRecord] = {}

    def observe(self, event: TradeEvent) -> DataQuality:
        """رصد حدث وصل خط التنقيح حتى مرحلة الإخراج (مقبولًا أو مُدرجًا متأخرًا).

        يحدث طراوة الوصول، ويقيس الكمون ضد عتبة DELAYED، ويقدم سلسلة النظافة
        أو يصفرها. يعيد الحالة بعد الرصد (متطابقة مع state_for التالية له).
        """
        record = self._records.setdefault(event.symbol, _SymbolRecord())
        record.last_arrival = event.receive_time_utc
        if record.last_event_time is None or event.event_time_utc > record.last_event_time:
            record.last_event_time = event.event_time_utc
        latency = event.source_latency_ms
        if latency is not None and latency > self._config.delayed_after_ms:
            record.degraded = _worse(record.degraded, DataQuality.DELAYED)
            record.clean_streak = 0
        else:
            record.clean_streak += 1
            recovery = self._config.healthy_recovery_events
            if record.degraded is not None and record.clean_streak >= recovery:
                record.degraded = None
        return self.state_for(event.symbol)

    def report_duplicate(self, event: TradeEvent) -> DataQuality:
        """إسقاط تكرار في خط التنقيح ⇒ تدهور DUPLICATED (الحدث نفسه دليل وصول)."""
        return self._degrade(event, DataQuality.DUPLICATED)

    def report_out_of_order(self, event: TradeEvent) -> DataQuality:
        """إدراج متأخر خارج الترتيب ⇒ تدهور OUT_OF_ORDER (لا حذف صامت — البيانات محفوظة)."""
        return self._degrade(event, DataQuality.OUT_OF_ORDER)

    def report_gap(self, event: TradeEvent, gap_ms: float) -> DataQuality:
        """فجوة زمنية بين حدثين متتاليين تجاوزت عتبة الخط ⇒ تدهور GAP_DETECTED."""
        return self._degrade(event, DataQuality.GAP_DETECTED)

    def report_partial(self, event: TradeEvent, missing: int) -> DataQuality:
        """أحداث مفقودة داخل الشريحة (قفزة تسلسل) ⇒ تدهور PARTIAL."""
        return self._degrade(event, DataQuality.PARTIAL)

    def report_quarantine(self, event: TradeEvent) -> DataQuality:
        """فشل تحقق أداة أو بيانات مريبة ⇒ تدهور QUARANTINED (أسوأ من كل شيء عدا الغياب)."""
        return self._degrade(event, DataQuality.QUARANTINED)

    def state_for(self, symbol: str) -> DataQuality:
        """حالة الرمز الآن — تقييم كسول للسكون فوق أسوأ تدهور غير متعافٍ."""
        record = self._records.get(symbol)
        if record is None or record.last_arrival is None:
            return DataQuality.UNAVAILABLE
        base = record.degraded if record.degraded is not None else DataQuality.HEALTHY
        silence_s = (self._clock() - record.last_arrival).total_seconds()
        if silence_s > self._config.unavailable_after_s:
            return DataQuality.UNAVAILABLE
        if silence_s > self._config.stale_after_s:
            return _worse(base, DataQuality.STALE)
        return base

    def _degrade(self, event: TradeEvent, state: DataQuality) -> DataQuality:
        """تطبيق تدهور: أسوأ مساهم يفوز، وسلسلة النظافة تبدأ من جديد."""
        record = self._records.setdefault(event.symbol, _SymbolRecord())
        record.last_arrival = event.receive_time_utc
        if record.last_event_time is None or event.event_time_utc > record.last_event_time:
            record.last_event_time = event.event_time_utc
        record.degraded = _worse(record.degraded, state)
        record.clean_streak = 0
        return self.state_for(event.symbol)
