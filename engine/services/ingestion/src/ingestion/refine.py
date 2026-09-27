"""خط التنقيح (§33.1) — من الحدث الخام إلى حدث منقًّى + إشارات جودة.

الترتيب حرفي كـ§33.1 لكل حدث:
timestamp normalization → duplicate check → sequence/order check →
instrument validation → event output.

تقسيم المسؤولية (قرار موثق): هذا الملف يحمل خط التنقيح وحده؛ التصنيف
والعتبات وسلّم الشدة في quality.py — الخط يكتشف ويبلّغ، المصنف يصنف.

قرار خارج-الترتيب (موقّق): الحدث القديم الواصل متأخرًا يُدرج موسومًا
(LATE_INSERTED) لا يُرفض ولا يُحذف — الحذف الصامت محظور؛ الصفقة وقعت
فعلًا وإسقاطها يفقد حجمًا حقيقيًا، والإدراج المتأخر مع إشارة OUT_OF_ORDER
يحفظ البيانات ويسمح لمنشئ الشموع (1.4) بوسم الشمعة المتأثرة بأسوأ مساهم.

حدود الخصم المضاعف (موثقة): نافذة LRU محدودة الحجم تعني أن إعادة توصيل
أقدم من النافذة تظهر «إدراجًا متأخرًا» لا «تكرارًا» — لا تمييز ممكنًا بلا
مخزن دائم (يسدده المخزن الخام 1.5 لاحقًا). التسلسل الرقمي (حيث يتوفر) هو
الحَكَم؛ وبدله يُقارن زمن الحدث.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from statistics import median

from schemas import DataQuality, TradeEvent

from .quality import QualityTracker


class RefinementAction(StrEnum):
    """مصير الحدث داخل الخط — لكل حدث وارد فعلًا مصير واحد بالضبط (لا صمت)."""

    ACCEPTED = "ACCEPTED"  # مقبول في الترتيب
    LATE_INSERTED = "LATE_INSERTED"  # مُدرج متأخرًا موسومًا (قرار خارج-الترتيب)
    DUPLICATE_DROPPED = "DUPLICATE_DROPPED"  # مكرر أُسقط وأُحصي
    REJECTED_INSTRUMENT = "REJECTED_INSTRUMENT"  # أداة غير مسموحة
    QUARANTINED_TIMESTAMP = "QUARANTINED_TIMESTAMP"  # فشل تحقق الطابع الزمني


@dataclass(frozen=True, slots=True)
class RefinementResult:
    """نتيجة معالجة حدث واحد — الحدث المنقّى (إن بقي) + إشارات الجودة التي أطلقها."""

    event: TradeEvent | None
    action: RefinementAction
    signals: tuple[DataQuality, ...] = ()
    missing_sequence_count: int = 0
    gap_ms: float | None = None


@dataclass(frozen=True, slots=True)
class PipelineStats:
    """إحصاءات داخلية قابلة للاستعلام — كل قرار محسوب، لا قرار صامت.

    الثابت الحسابي: received = مجموع مصائر الـactions السبعة الباقية.
    """

    received: int
    accepted: int
    late_inserted: int
    duplicates_dropped: int
    rejected_instrument: int
    quarantined: int
    sequence_jumps: int
    gaps_detected: int


@dataclass(frozen=True, slots=True)
class RefinementConfig:
    """عتبات الخط — افتراضيات موثقة قابلة للضبط بالحقن.

    - ``duplicate_window``: حجم نافذة LRU لمفاتيح (symbol, sequence_id)
      (الافتراضي 4096 — يغطي إعادات التوصيل والوصول المتأخر الشائع بذاكرة
      محدودة؛ معرفات aggTrade رتيبة فالنافذة الأحدث تكفي التشغيل الحي).
    - ``gap_floor_ms``: أرضية مطلقة لعتبة الفجوة (الافتراضي 10000ms — صمت
      عشر ثوانٍ في تدفق aggTrades مرجعي عمليًا مشكلة تغذية لا سكون سوق).
    - ``gap_multiplier``: مضاعف وسيط الفواصل المتدحرجة (3× كما تنص الخطة).
    - ``gap_median_window``: حجم نافذة الوسيط المتدحرج (128 عينة).
    - ``gap_warmup``: حد أدنى من العينات قبل اعتماد الوسيط التكيفي — بدونه
      تُستخدم الأرضية المطلقة (وسيط بلا عينات ضجيج).
    """

    duplicate_window: int = 4096
    gap_floor_ms: float = 10_000.0
    gap_multiplier: float = 3.0
    gap_median_window: int = 128
    gap_warmup: int = 8

    def __post_init__(self) -> None:
        if self.duplicate_window < 1:
            raise ValueError(f"duplicate_window يجب أن يكون ≥ 1: {self.duplicate_window}")
        if self.gap_floor_ms < 0.0:
            raise ValueError(f"gap_floor_ms لا يمكن أن يكون سالبًا: {self.gap_floor_ms}")
        if self.gap_multiplier < 1.0:
            raise ValueError(f"gap_multiplier يجب أن يكون ≥ 1: {self.gap_multiplier}")
        if self.gap_median_window < 1:
            raise ValueError(f"gap_median_window يجب أن يكون ≥ 1: {self.gap_median_window}")
        if self.gap_warmup < 1:
            raise ValueError(f"gap_warmup يجب أن يكون ≥ 1: {self.gap_warmup}")


@dataclass
class _SymbolState:
    """حالة الخط لكل رمز — علامة تسلسل مائية + آخر زمن + نافذة الفواصل."""

    last_seq: int | None = None
    last_event_time: datetime | None = None
    gap_window: deque[float] = field(default_factory=deque)


def _try_int(value: str | None) -> int | None:
    """محاولة قراءة معرف تسلسل رقمي — غير الرقمي يعني مصدرًا بلا تسلسل (None)."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class RefinementPipeline:
    """يستهلك TradeEvent خامًا وينتج أحداثًا منقّاة + إشارات جودة (§33.1).

    ``tracker`` اختياري: إن حُقن فالخط يبلّغه كل إشارة ويرصده كل حدث يصل
    مرحلة الإخراج — التوصيل بين الاكتشاف والتصنيف ملموس لا ضمني.

    القرار التوثيقي الوحيد الدقيق: انظر رأس الوحدة (سياسة خارج-الترتيب
    وحدود نافذة الخصم). الأحداث المرفوضة (أداة غير مسموحة / حجر طابع) لا
    تترك أثرًا في حالة الخصم أو الترتيب — الفصل النظيف يمنع تسرب رموز
    غريبة إلى حالة الأدوات المتعقبة.
    """

    def __init__(
        self,
        *,
        allowed_symbols: frozenset[str] | set[str] | None = None,
        tracker: QualityTracker | None = None,
        config: RefinementConfig | None = None,
    ) -> None:
        self._allowed: frozenset[str] | None = (
            frozenset(allowed_symbols) if allowed_symbols is not None else None
        )
        self._tracker = tracker
        self._config = config or RefinementConfig()
        self._dup_window: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._symbols: dict[str, _SymbolState] = {}
        self._received = 0
        self._accepted = 0
        self._late_inserted = 0
        self._duplicates_dropped = 0
        self._rejected_instrument = 0
        self._quarantined = 0
        self._sequence_jumps = 0
        self._gaps_detected = 0

    def process(self, raw: TradeEvent) -> RefinementResult:
        """معالجة حدث واحد عبر مراحل §33.1 بالترتيب الحرفي."""
        self._received += 1

        # (1) تطبيع/تحقق الطابع الزمني — دفاع عمق: schemas ترفض الساذج أصلًا،
        # لكن model_construct يتجاوز التحقق؛ المقارنات الوعية صحيحة مطلقًا
        # أياً كانت منطقتها، فالخلل الحقيقي الوحيد هو الساذج.
        if raw.event_time_utc.tzinfo is None or raw.receive_time_utc.tzinfo is None:
            self._quarantined += 1
            self._notify_quarantine(raw)
            return RefinementResult(
                event=None,
                action=RefinementAction.QUARANTINED_TIMESTAMP,
                signals=(DataQuality.QUARANTINED,),
            )

        # (2) فحص التكرار — مفتاح (symbol, sequence_id) في نافذة LRU.
        # الأحداث بلا sequence_id لا تدخل الفحص (لا مفتاح لها — موثق).
        if raw.sequence_id is not None:
            key = (raw.symbol, raw.sequence_id)
            if key in self._dup_window:
                self._duplicates_dropped += 1
                self._notify_duplicate(raw)
                return RefinementResult(
                    event=None,
                    action=RefinementAction.DUPLICATE_DROPPED,
                    signals=(DataQuality.DUPLICATED,),
                )

        # (3) فحص التسلسل/الترتيب — التسلسل الرقمي هو الحكم؛ وبدله زمن الحدث.
        state = self._symbols.get(raw.symbol)
        if state is None:
            state = _SymbolState(gap_window=deque(maxlen=self._config.gap_median_window))
            self._symbols[raw.symbol] = state
        late = False
        missing = 0
        seq_num = _try_int(raw.sequence_id)
        if seq_num is not None and state.last_seq is not None:
            if seq_num == state.last_seq:
                # مضاعفة التقطها المرحلة الثالثة لا الثانية: المفتاح خرج من
                # نافذة LRU لكنه يطابق العلامة المائية — الإسقاط نفسه، لا صمت.
                self._duplicates_dropped += 1
                self._notify_duplicate(raw)
                return RefinementResult(
                    event=None,
                    action=RefinementAction.DUPLICATE_DROPPED,
                    signals=(DataQuality.DUPLICATED,),
                )
            late = seq_num < state.last_seq
            if seq_num > state.last_seq + 1:
                missing = seq_num - state.last_seq - 1
        elif seq_num is None and state.last_event_time is not None:
            # مصدر بلا تسلسل رقمي: مقارنة زمنية فقط (لا كشف فقد ممكن — موثق)
            late = raw.event_time_utc < state.last_event_time

        # (4) تحقق الأداة — الرمز يجب أن يكون ضمن القائمة المسموحة (None = الكل).
        if self._allowed is not None and raw.symbol not in self._allowed:
            self._rejected_instrument += 1
            self._notify_quarantine(raw)
            return RefinementResult(
                event=None,
                action=RefinementAction.REJECTED_INSTRUMENT,
                signals=(DataQuality.QUARANTINED,),
            )

        # (5) الإخراج — فحص الفجوة، تحديث الحالة، تذكر المفتاح، رصد المصنف.
        gap_ms = self._gap_check(state, raw.event_time_utc)
        signals: list[DataQuality] = []
        if gap_ms is not None:
            self._gaps_detected += 1
            signals.append(DataQuality.GAP_DETECTED)
            if self._tracker is not None:
                self._tracker.report_gap(raw, gap_ms)
        if missing > 0:
            self._sequence_jumps += 1
            signals.append(DataQuality.PARTIAL)
            if self._tracker is not None:
                self._tracker.report_partial(raw, missing)
        if late:
            signals.append(DataQuality.OUT_OF_ORDER)
            if self._tracker is not None:
                self._tracker.report_out_of_order(raw)
        if seq_num is not None and (state.last_seq is None or seq_num > state.last_seq):
            state.last_seq = seq_num
        if raw.sequence_id is not None:
            key = (raw.symbol, raw.sequence_id)
            self._dup_window[key] = None
            self._dup_window.move_to_end(key)
            while len(self._dup_window) > self._config.duplicate_window:
                self._dup_window.popitem(last=False)
        if late:
            self._late_inserted += 1
            action = RefinementAction.LATE_INSERTED
        else:
            self._accepted += 1
            action = RefinementAction.ACCEPTED
        if self._tracker is not None:
            self._tracker.observe(raw)
        return RefinementResult(
            event=raw,
            action=action,
            signals=tuple(signals),
            missing_sequence_count=missing,
            gap_ms=gap_ms,
        )

    def stats(self) -> PipelineStats:
        """لقطة الإحصاءات — كل قرار قابل للاستعلام (لا قرار صامت)."""
        return PipelineStats(
            received=self._received,
            accepted=self._accepted,
            late_inserted=self._late_inserted,
            duplicates_dropped=self._duplicates_dropped,
            rejected_instrument=self._rejected_instrument,
            quarantined=self._quarantined,
            sequence_jumps=self._sequence_jumps,
            gaps_detected=self._gaps_detected,
        )

    def _gap_check(self, state: _SymbolState, event_time: datetime) -> float | None:
        """فجوة زمنية بين حدثين متتاليين تجاوزت العتبة ⇒ GAP (قيمة الفجوة ms).

        العتبة = max(الأرضية المطلقة، مضاعف × وسيط الفواصل المتدحرجة). الفواصل
        موجبة تدخل النافذة كلها (الفجوات الكبيرة أيضًا — الوسيط المتدحرج يعدّل
        نفسه بعد الانقطاعات ثم يتحلل بالانزلاق؛ قرار موثق: بديل «استبعاد
        الشواذ» كان سيجمّد العتبة على ما قبل الانقطاع فيعلن فجوات كاذبة
        للأبد بعد كل هدوء سوقي حقيقي). الأحداث المتأخرة (فاصل سالب) لا تدخل.
        """
        previous = state.last_event_time
        if previous is None:
            state.last_event_time = event_time
            return None
        delta_ms = (event_time - previous).total_seconds() * 1000.0
        if delta_ms <= 0.0:
            return None
        window = state.gap_window
        threshold = self._config.gap_floor_ms
        if len(window) >= self._config.gap_warmup:
            adaptive = self._config.gap_multiplier * float(median(window))
            threshold = max(threshold, adaptive)
        window.append(delta_ms)
        # الفاصل الموجب يثبت أن الحدث أحدث من المحفوظ — تحديث العلامة الزمنية
        state.last_event_time = event_time
        return delta_ms if delta_ms > threshold else None

    def _notify_duplicate(self, raw: TradeEvent) -> None:
        if self._tracker is not None:
            self._tracker.report_duplicate(raw)

    def _notify_quarantine(self, raw: TradeEvent) -> None:
        if self._tracker is not None:
            self._tracker.report_quarantine(raw)
