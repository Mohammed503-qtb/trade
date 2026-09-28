"""محرك كسر البنية BOS/CHoCH — §11.2 و§11.3 حرفيًا.

نص §11.2: كسر البنية «خرق مؤكد لمتطرف سابق ذي صلة بنيوية ضمن الإطار
الاتجاهي الجاري»، بشرطه القابل للبرمجة: «إغلاق أو قبول بعد المتطرف
بعتبة إزاحة دنيا قابلة للضبط»، و«التحقق أن الكسر ليس فتيلًا معزولًا إلا
إن كانت الاستراتيجية تعتبر خرق الفتيل صريحًا صالحًا»، ثم «التصنيف داخليًا
أو خارجيًا». نص §11.3: CHoCH «انتقال بنيوي تنتهك فيه سلسلة المتطرفات
الحالية نمط الاستمرار الاتجاهي السابق لأول مرة» — وهو «أضعف من انعكاس
نظام مؤكد ولا يُعامل انعكاسًا تلقائيًا» (المحرك يبث الحدث فقط؛ التفسير
مسؤولية الطبقات الأدنى).

**آلة الحالة الاتجاهية (الإطار الخارجي)**: ``framework_direction`` هو
اتجاه آخر كسر خارجي (تأسيسًا أو استمرارًا أو انقلابًا). الكسر الخارجي
الذي يخالفه = **CHOCH** أول انتهاك (يحمل ``choch_prior_direction``)، ثم
يستقر الإطار على الاتجاه الجديد؛ الكسر الخارجي الموافق له = **EXTERNAL_BOS**
استمرار. **أول كسر خارجي على الإطلاق = EXTERNAL_BOS تأسيسًا** (لا نمط
استمرار سابق ليُنتَهك) — قرار موثق. كسور **الداخلية لا تمس الإطار** أصلًا
(INTERNAL_BOS دائمًا): البنية الداخلية حركة داخل الإطار الخارجي.

**المرجع البنيوي عند كل شمعة** (التحديد الدقيق المطلوب): الكسر صعودًا
يقيَّم ضد **أعلى قمة غير مكسورة سعرها دون الإغلاق**
(‎argmax{p ∈ القمم غير المكسورة : p < close}‎) — أقرب سقف تحت السعر؛
وبالمقابل أدنى قاع غير مكسور فوق الإغلاق للكسر هبوطًا. الحدث يقع إذا
بلغت المسافة وراء المرجع عتبة ``DISPLACEMENT_MIN``.

**استهلاك المستويات الأضعف**: عند بث كسر (جهةً ما) تُوسم مكسورةً كل
مستويات تلك القطبية الواقعة وراء امتداد الشمعة الكاسرة (قمم دون الإغلاق
صعودًا) — الكسر المُبلَّغ يبتلع ما دونه؛ المستويات التي عبرها الإغلاق دون
بلوغ العتبة (**الإخفاق القريب**) تبقى حية مسلَّحة — لا حدث ولا استهلاك
صامتًا (§27: السكوت ليس حالة).

**عتبة الفتيل (§11.2)**: افتراضيًا الكسر بإغلاق فقط — الخرق الفتيلي الذي
يرتد الإغلاق داخله ليس كسرًا («not merely an isolated wick»). مع
``wick_breaks_valid=True`` يُقبل الخرق الفتيلي إذا بلغ امتداد الفتيل وراء
المرجع عتبة ``DISPLACEMENT_MIN`` نفسها — العتبة القابلة للضبط الوحيدة
في الحكم بنص §11.2، تُطبّق على المسار الذي حقق الخرق؛ عند الكسر الفتيلي
تُقاس ``breach_distance_atr`` بامتداد الفتيل بينما ``closing_acceptance``
(بإغلاقٍ رتد داخل النطاق: 0.0 معلنة) تحمل معلومة الرفض — تفسير الرفض
العميق اجتياحًا فاشلًا/سحبًا ملف السيولة (3-c) لا هذا المحرك.

**مفتاح ``WICK_BREAK_TOLERANCE`` — قرار استخدام موثق**: متاح في حالة
التقلب (أضافه 3-a لنص §11.2) لكنه **غير مستخدم في مسار الحكم هنا**:
تصنيف «الإخفاق القريب» (عبور فتيلي/إغلاقي دون العتبة) يظهر في خرج هذا
المحرك سكوتًا محضًا — لا حدث ولا حالة — لأن §20 لا يعرف نوع حدث
للإخفاق القريب أصلًا؛ المستهلك الذي يحتاج تمييز الخرق الهامشي (امتداد
داخل التسامح) من الكسر الفتيلي الكامل (ليالي السيولة 3-c وخطط الدخول)
يقرأ العتبة من الحالة نفسها — مسار الحكم يبقى بعتبة إزاحة واحدة.

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_bos.py):

- **لا-نظرة-مستقبلية (§26.3)**: كل تقييم من الشمعة الحالية وسجل المستويات
  المتراكم حصرًا؛ ``follow_through`` عند البث 0.0 معلنة (صفر شموع منقضية
  بعد الكسر) — لا قياس من مستقبل أبدًا، والتتبع اللاحق مسؤولية المستهلك.

- **العتبات التطبيعية (§16)**: عتبة الكسر و``breach_distance_atr``
  (بسطها) كلاهما من ``vol_state.threshold``/``vol.atr`` حصرًا — لا مسافة
  سعرية مطلقة في أي مسار. ``atr`` غائب (دافئ) أو منحل (``atr ≤ 0``:
  عتبةٌ معدومة تُصدّق كل عبورٍ، والتطبيع breach/atr قسمةٌ على صفر)
  ⇒ لا تقييم إطلاقًا (العتبة أصل الحكم ولا حكم بلا أصل) — المستويات
  لا تُستهلك أثناء الدافئ وقد يُبَث كسر مستوى قديم عند أول شمعة
  تُقيَّم فعلًا (بثٌّ بعد العلم لا رفرفة).

- **حدث واحد لكل اتجاه في الشمعة** (بأولوية الإغلاق على الفتيل) وبترتيب
  حتمي (UP ثم DOWN) — قد يبثان معًا في التسلسلات المرضخة النادرة،
  حدثان مستقلان والدمج مسؤولية fusion (§19).

- **الحتمية الصرفة**: نفس الشموع والمتطرفات ⇒ نفس الأحداث بالتطابق التام.

- **الصخب في التحقق**: عقود :mod:`structure._guards` كاملة، وتغذية متطرف
  قبل أي شمعة، أو متطرف بإطار مغاير، أو مكرر المعرف، أو بعلاقة
  ``bar_time > confirmation_time`` مكسورة، أو بترتيب تأكيد متناقص — كلها
  ``ValueError`` صاخبة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import (
    BreakDirection,
    Candle,
    EventType,
    StructureBreakPayload,
    Swing,
    SwingDirection,
    SwingScope,
)

from ._guards import StreamGuards
from .events import EmittedEvent

__all__ = ["BosConfig", "StructureBreakEngine"]


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class BosConfig:
    """إعداد محرك الكسور — نقاط انطلاق إعدادية للتقييم والمعايرة
    (ليست توصيات تداول).

    العتبات السعرية نفسها ليست هنا أصلًا: ``DISPLACEMENT_MIN`` و
    ``WICK_BREAK_TOLERANCE`` تأتي من حالة التقلب (``atr × multiplier``)
    عند كل شمعة — موضعها الطبيعي ``VolatilityConfig.multipliers``.
    """

    #: اعتبار الخرق الفتيلي كسرًا صالحًا (§11.2: «unless a strategy
    #: explicitly treats wick breaks as valid») — الافتراضي الإغلاق فقط.
    wick_breaks_valid: bool = False


# ═════════════════════════════ الداخلية ═════════════════════════════


@dataclass
class _SwingLevel:
    """متطرف مسجل كسوق بنية — كائن داخلي تُوسم حالته (مكسور/حية)."""

    swing: Swing
    broken: bool = False


@dataclass
class _BreakVerdict:
    """حكم كسر جهة واحدة عند شمعة — داخلي بين مسارات التقييم."""

    level: _SwingLevel
    via_wick: bool
    breach: float  # المسافة وراء المستوى بواسطة المسار الكاسر (سعرًا)


@dataclass
class _EngineState:
    """حالة المحرك القابلة للنمو — تُبنى في البناء لا في التصريح."""

    levels: list[_SwingLevel] = field(default_factory=list)
    seen_swing_ids: set[str] = field(default_factory=set)
    last_confirmation_time: datetime | None = None
    framework: BreakDirection | None = None


# ═════════════════════════════ المحرك ═════════════════════════════


class StructureBreakEngine:
    """محرك كسر البنية الموضعي لكل (أداة، إطار) — §11.2/§11.3.

    الاستخدام (التركيب في :class:`structure.engine.StructureEngine`):
    المتطرفات المؤكدة تُغذى عبر :meth:`on_swing` قبل تقييم شمعة تأكيدها،
    ثم تقيَّم الشمعة عبر :meth:`update`. برهان استحالة كسر المتطرف عند
    شمعة تأكيده نفسها: قمم نافذة التأكيد كلها ≤ سعر القمة فإغلاق الشمعة
    المؤكِدة دون القمة حتمًا (وبالمقابل للقاع) — الترتيب آمن بالبناء.
    """

    def __init__(
        self,
        config: BosConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else BosConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        self._state = _EngineState()

    # ── الخصائص ──

    @property
    def config(self) -> BosConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.timeframe

    @property
    def framework_direction(self) -> BreakDirection | None:
        """اتجاه الإطار الخارجي الجاري (آخر كسر خارجي) — None قبل أي كسر.

        يغذي انحياز HTF (3-e) وخريطة السيولة (3-c) — القرار البنيوي
        الاتجاهي هنا، وتفسيره هناك.
        """
        return self._state.framework

    @property
    def swings(self) -> tuple[Swing, ...]:
        """كل المتطرفات المُغذاة بترتيب التغذية (مكسورها وحيها)."""
        return tuple(level.swing for level in self._state.levels)

    @property
    def unbroken_highs(self) -> tuple[Swing, ...]:
        """القمم الحية غير المكسورة بترتيب التغذية — مستويات مقاومة جارية."""
        return tuple(
            level.swing
            for level in self._state.levels
            if not level.broken and level.swing.direction is SwingDirection.HIGH
        )

    @property
    def unbroken_lows(self) -> tuple[Swing, ...]:
        """القيعان الحية غير المكسورة بترتيب التغذية — مستويات دعم جارية."""
        return tuple(
            level.swing
            for level in self._state.levels
            if not level.broken and level.swing.direction is SwingDirection.LOW
        )

    # ── تغذية المتطرفات ──

    def on_swing(self, swing: Swing) -> None:
        """تسجيل متطرف مؤكد كسوق بنية — قبل تقييم شمعة تأكيده (عقد التركيب).

        :raises ValueError: تغذية متطرف قبل أي شمعة (لا هوية بعد)، أو إطار
            مغاير لهوية المحرك، أو ``bar_time`` بعد ``confirmation_time``
            (العلاقة القانونية للمتطرف)، أو تكرار ``swing_id``، أو
            ``confirmation_time`` أقدم من آخر متطرف مُغذى.
        """
        timeframe = self._guards.timeframe
        if timeframe is None:
            raise ValueError(
                "تغذية متطرف قبل أي شمعة — المحرك يلتقط هويته من الشموع؛ "
                "أكمل تغذية شمعة التأكيد أولًا (عقد التركيب في الواجهة)"
            )
        if swing.timeframe != timeframe:
            raise ValueError(
                f"متطرف بإطار مغاير لهوية المحرك: {swing.timeframe!r} مقابل "
                f"{timeframe!r} — سجل المستويات لإطار واحد حصرًا"
            )
        if swing.bar_time > swing.confirmation_time:
            raise ValueError(
                f"علاقة قانونية مكسورة: bar_time {swing.bar_time} بعد "
                f"confirmation_time {swing.confirmation_time} — الفارق بينهما "
                "هو تأخير التأكيد ولا يكون سالبًا أبدًا (§11.1)"
            )
        if swing.swing_id in self._state.seen_swing_ids:
            raise ValueError(f"متطرف مكرر المعرف: {swing.swing_id} — التغذية لمرة واحدة")
        last_confirmation = self._state.last_confirmation_time
        if last_confirmation is not None and swing.confirmation_time < last_confirmation:
            raise ValueError(
                f"ترتيب تغذية متناقص: confirmation_time {swing.confirmation_time} "
                f"أقدم من آخر متطرف مُغذى {last_confirmation} — "
                "المتطرفات تُغذى بترتيب التأكيد"
            )
        self._state.levels.append(_SwingLevel(swing=swing))
        self._state.seen_swing_ids.add(swing.swing_id)
        self._state.last_confirmation_time = swing.confirmation_time

    # ── التقييم ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[EmittedEvent]:
        """تقييم شمعة مغلقة ضد سجل المستويات — أحداث الكسور المؤكدة عندها.

        ترجع صفر أو حدثًا واحدًا لكل اتجاه (UP ثم DOWN — ترتيب حتمي).
        ``vol`` بلا ``atr`` أو بـ``atr`` منحل (``≤ 0``) ⇒ لا تقييم (قائمة
        فارغة) — انظر عقود الموديول.
        """
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        threshold: float | None = None
        atr: float | None = None
        if vol is not None:
            atr = vol.atr
            threshold = vol.threshold(ThresholdKey.DISPLACEMENT_MIN)
        if threshold is None or atr is None or atr <= 0.0:
            # العتبة أصل الحكم ولا حكم بلا أصل — ولا استهلاك مستويات أثناء
            # الدافئ أو التقلب المنحل (atr ≤ 0: عتبة معدومة تُصدّق كل عبورٍ،
            # والتطبيع breach/atr قسمةٌ على صفر — الرفض لا القسمة).
            return []
        events: list[EmittedEvent] = []
        for direction in (BreakDirection.UP, BreakDirection.DOWN):
            verdict = self._evaluate(candle, direction, threshold, atr)
            if verdict is not None:
                events.append(self._emit(candle, direction, atr, verdict))
        return events

    # ── الداخلية ──

    def _evaluate(
        self, candle: Candle, direction: BreakDirection, threshold: float, atr: float
    ) -> _BreakVerdict | None:
        """حكم جهة واحدة: مرجع الإغلاق أولًا ثم مسار الفتيل المُفعَّل.

        مرجع الإغلاق: أقرب سقف تحت الإغلاق (أعلى قمة غير مكسورة سعرها دون
        الإغلاق) صعودًا / أقرب أرضية فوق الإغلاق هبوطًا. الإخفاق القريب
        (عبور دون عتبة) لا يُستهلك المستوى؛ عند تحقق الكسر تُبتلع كل
        مستويات القطبية الأضعف وراء امتداد الشمعة الكاسرة.
        """
        is_up = direction is BreakDirection.UP
        wanted = SwingDirection.HIGH if is_up else SwingDirection.LOW
        # ── مسار الإغلاق (الأصل §11.2) ──
        close_ref = self._nearest_level(wanted, boundary=candle.close, from_below=is_up)
        if close_ref is not None:
            breach = (
                candle.close - close_ref.swing.price
                if is_up
                else close_ref.swing.price - candle.close
            )
            if breach >= threshold:
                self._consume(wanted, beyond=candle.close)
                return _BreakVerdict(level=close_ref, via_wick=False, breach=breach)
        # ── مسار الفتيل المُفعَّل اختياريًا (§11.2 «unless a strategy…») ──
        if not self._config.wick_breaks_valid:
            return None
        wick_edge = candle.high if is_up else candle.low
        wick_ref = self._nearest_level(wanted, boundary=wick_edge, from_below=is_up)
        if wick_ref is None:
            return None
        excursion = wick_edge - wick_ref.swing.price if is_up else wick_ref.swing.price - wick_edge
        if excursion < threshold:
            return None
        self._consume(wanted, beyond=wick_edge)
        return _BreakVerdict(level=wick_ref, via_wick=True, breach=excursion)

    def _nearest_level(
        self, wanted: SwingDirection, *, boundary: float, from_below: bool
    ) -> _SwingLevel | None:
        """المرجع: أقصى قمة حية دون الحد / أدنى قاع حية فوقه.

        ``from_below=True`` يختار القمم لكسر صعودًا (أقرب سقف تحت السعر)،
        و``from_below=False`` القيعان لكسر هبوطًا (أقرب أرضية فوق السعر) —
        مساواة السعر للمستوى ليست عبورًا فلا تُختار.
        """
        best: _SwingLevel | None = None
        for level in self._state.levels:
            if level.broken or level.swing.direction is not wanted:
                continue
            price = level.swing.price
            if from_below:
                if price < boundary and (best is None or price > best.swing.price):
                    best = level
            elif price > boundary and (best is None or price < best.swing.price):
                best = level
        return best

    def _consume(self, wanted: SwingDirection, *, beyond: float) -> None:
        """استهلاك المستويات الأضعف: كل مستويات القطبية وراء امتداد الكسر."""
        for level in self._state.levels:
            if level.broken or level.swing.direction is not wanted:
                continue
            price = level.swing.price
            beyond_level = price < beyond if wanted is SwingDirection.HIGH else price > beyond
            if beyond_level:
                level.broken = True

    def _emit(
        self,
        candle: Candle,
        direction: BreakDirection,
        atr: float,
        verdict: _BreakVerdict,
    ) -> EmittedEvent:
        """بناء الحدث: تصنيف النوع بآلة الإطار ثم الحمولة الموثقة (3-a)."""
        swing = verdict.level.swing
        is_up = direction is BreakDirection.UP
        event_type: EventType
        choch_prior: BreakDirection | None = None
        if swing.external_or_internal is SwingScope.EXTERNAL:
            prior = self._state.framework
            if prior is not None and prior is not direction:
                # §11.3: أول انتهاك لنمط الاستمرار — أضعف من انعكاس نظام.
                event_type = EventType.CHOCH
                choch_prior = prior
            else:
                # استمرار الإطار، أو التأسيس الأول (لا نمط سابق ليُنتَهك).
                event_type = EventType.EXTERNAL_BOS
            self._state.framework = direction
        else:
            # البنية الداخلية حركة داخل الإطار — لا تمس آلة الإطار أصلًا.
            event_type = EventType.INTERNAL_BOS
        level_price = swing.price
        breach_atr = verdict.breach / atr
        # قبول الإغلاق (صيغة موحدة للمسارين): كم استقر الإغلاق وراء المستوى
        # نسبةً إلى امتداد الشمعة وراءه — ‎(close − L)/(high − L)‎ صعودًا
        # (وبالمقابل هبوطًا) مقصوصة إلى [0, 1]: الكسر الفتيلي الذي ارتد
        # إغلاقه داخل النطاق يقبَل 0.0 معلنًا — غياب القبول حقيقة مقيسة.
        if is_up:
            span = candle.high - level_price
            penetration = candle.close - level_price
        else:
            span = level_price - candle.low
            penetration = level_price - candle.close
        acceptance = 0.0 if span <= 0.0 else max(0.0, min(1.0, penetration / span))
        payload = StructureBreakPayload(
            instrument=self._required_instrument(),
            timeframe=self._required_timeframe(),
            bar_time=candle.bar_time,
            swing_id=swing.swing_id,
            swing_scope=swing.external_or_internal,
            break_direction=direction,
            breach_distance_atr=breach_atr,
            closing_acceptance=acceptance,
            follow_through=0.0,
            choch_prior_direction=choch_prior,
        )
        return EmittedEvent(event_type=event_type, event_time=candle.bar_time, payload=payload)

    def _required_instrument(self) -> str:
        """أداة المحرك — التقييم لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        instrument = self._guards.instrument_id
        assert instrument is not None
        return instrument

    def _required_timeframe(self) -> str:
        """إطار المحرك — التقييم لا يحدث إلا بعد أول شمعة (عقود الترتيب)."""
        timeframe = self._guards.timeframe
        assert timeframe is not None
        return timeframe
