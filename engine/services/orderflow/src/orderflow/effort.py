"""مصفوفة الجهد مقابل النتيجة (§12.2) + بدائل القياس التدفقي المشتركة.

نص §12.2: «الملاحظة المهمة ليست إشارة الدلتا وحدها؛ المحرك يقارن الدلتا
بالنتيجة السعرية» — هذه الوحدة هي هذا القانون مصنوعًا: تصنيف صرف حتمي
لكل شريط فوتبرنت على مصفوفة الحالات الأربع (+ بوابة التقلب الخامسة)،
ودالة كفاءة الدلتا التي هي القياس الأولي لـFLOW_CONTINUATION (§20:
«Delta efficiency») والأساس الكمي لعنصري الإنهاك أ/د (§12.4)، وبدائل
القياس والحماية المشتركة التي تُبنى عليها كاشفا الامتصاص والإنهاك
(ملفات موازية داخل الحزمة نفسها — لا اعتماد على بنّاء الفوتبرنت ولا
على مقاييس الشريط: المدخل القانوني هنا schemas + حالة التقلب حصرًا).

**التعريفات التشغيلية (موثقة بمرجعها)**:

- **الجهد** = ‎|delta_share|‎ لحظة الشريط — ``delta / total_volume``
  (:func:`bar_delta_share`)؛ نسبة عديمة الأبعاد لا تحتاج تطبيعًا سعريًا.
  حد «الجهد الكبير» هو :data:`EFFORT_MIN_SHARE` — ثابت إعدادي معلن
  للوحدة (نقطة انطلاق تُعايَر؛ ليس توصية تداول).
- **النتيجة** = الاستجابة السعرية باتجاه الدلتا (‎close−open‎ باتجاهها؛
  الدلتا المعدومة لا اتجاه لجهدِها فاستجابتها **صفر معلن** — لا جهد
  يُستجاب له)؛ تُقارن بالعتبة التطبيعية ``vol.threshold(FLOW_RESPONSE_MIN)``
  **سعرًا بسعر** (§16: ``threshold = atr × multiplier`` — لا ثابت مطلق
  أبدًا ولا خلط أبعاد أبدًا: درس ADR-020 في بوابة المرحلة 3).
- **الكفاءة** = :func:`efficiency` — ``response_atr / |delta_share|``:
  استجابة (بمضاعفات ATR) لكل وحدة جهد.

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_effort_result.py):

- **لا قرار بلا تقلب (§16)**: ``vol=None`` أو ATR غائب/منحل (‎≤ 0 أو غير
  محدودة) ⇒ ``INSUFFICIENT_VOLATILITY`` — لا عتبة فلا قرار، ولا قيمة
  مزيفة أبدًا.
- **الحتمية الصرفة**: دوال صرفة بلا حالة — نفس المدخلات ⇒ نفس الخرج
  بالتطابق التام.
- **لا-نظرة-مستقبلية (§26.3)**: حالة تقلب بطابع أحدث من الشمعة تُرفض
  صاخبًا (:func:`check_flow_inputs`)؛ الأقدم مسموحة (قيمها الدافئة
  ``None`` تعلن نفسها).
- **الصخب في التحقق**: الشريط غير المغلق أو الشمعة غير المغلقة (§27)،
  الثنائية غير المتطابقة (هوية/طابع)، الدلتا غير المحدودة، أو الشريط
  غير المتسق (‎|delta| > الحجم الكلي‎) — كلها ``ValueError`` لا تصحيح
  صامت.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isfinite

from market_state.volatility import ThresholdKey, VolatilityState
from schemas import Candle, FootprintBar

__all__ = [
    "EFFORT_MIN_SHARE",
    "EffortResultState",
    "FlowGuards",
    "bar_delta_share",
    "check_flow_inputs",
    "classify_effort_vs_result",
    "directional_response",
    "efficiency",
    "usable_atr",
]


#: حد «الجهد الكبير» — حصة الدلتا الدنيا لاعتبار جهد الشريط كبيرًا
#: (§12.2: «large positive delta»). نقطة انطلاق إعدادية معلنة (0.4)
#: قابلة للمعايرة؛ نسبة عديمة الأبعاد فلا تحتاج ATR — ليست توصية تداول.
EFFORT_MIN_SHARE: float = 0.4


class EffortResultState(StrEnum):
    """حالات مصفوفة الجهد/النتيجة — الأربع الحرفية §12.2 + بوابة §16.

    الأربع الأولى خلايا «جهد كبير/صغير × استجابة قوية/ضعيفة»؛ الخامسة
    ليست خلية مصفوفة بل بوابة التقلب: لا قرار بلا عتبة تطبيعية.
    """

    #: جهد كبير + استجابة قوية — «شراء عدواني مقبول» (توافق التدفق).
    AGREE_EFFORT_RESULT = "AGREE_EFFORT_RESULT"
    #: جهد كبير + استجابة ضعيفة — «امتصاص محتمل / شراء عالق»: فرضية يجب
    #: أن تؤكدها الاستجابة اللاحقة (§12.2) — مدخل كاشف الامتصاص (§12.3).
    EFFORT_NO_RESULT = "EFFORT_NO_RESULT"
    #: جهد صغير + استجابة قوية — حركة بلا عدوانية تدفعها.
    RESULT_NO_EFFORT = "RESULT_NO_EFFORT"
    #: كلاهما ضعيف — لا جهد يُذكر ولا نتيجة تُقاس.
    LOW_EFFORT_LOW_RESULT = "LOW_EFFORT_LOW_RESULT"
    #: لا تقلب قابلًا للاستخدام — لا عتبة فلا قرار (عقد §16 الصارم).
    INSUFFICIENT_VOLATILITY = "INSUFFICIENT_VOLATILITY"


# ═══════════════════════ بدائل القياس المشتركة ═══════════════════════


def usable_atr(vol: VolatilityState | None) -> float | None:
    """ATR قابل للاستخدام: محدودة موجبة — أو ``None`` عند الغياب/الانحلال.

    الانحلال (‎≤ 0 أو غير محدودة) يُعامل كغياب معلن: **الرفض لا القسمة**
    — لا عتبة من تقلب منحل (نفس قرار ``atr_zero_degenerate`` الموثق في
    كاشف الإزاحة: عند ATR معدومة تقبل المقارنات الضعيف وترفض الصحيح).
    """
    if vol is None:
        return None
    atr = vol.atr
    if atr is None or not isfinite(atr) or atr <= 0.0:
        return None
    return atr


def bar_delta_share(bar: FootprintBar) -> float:
    """حصة الدلتا ``delta / total_volume`` ∈ [-1, 1] — قياس الجهد الخام.

    الشريط بلا صفقات (``total=0`` و``delta=0``) جهدُه صفر معلن: لا عدوانية
    تُقاس. أما ``|delta| > total_volume`` فتناقض قانوني (الفرق بين الطرفين
    لا يعلو مجموعهما أبدًا) يُرفض صاخبًا — بنّاء الفوتبرنت (4-b) يضمن
    الاتساق، وهذا الحارس يمسك أي خروق. الدلتا غير المحدودة (nan/inf)
    تُرفض كذلك — قياس الجهد لا يُبنى على غير المحدود.

    :raises ValueError: دلتا غير محدودة، أو شريط غير متسق
        (|delta| أكبر من الحجم الكلي).
    """
    delta = bar.delta
    total = bar.total_volume
    if not isfinite(delta):
        raise ValueError(f"دلتا غير محدودة: {delta!r} — قياس الجهد يرفضها")
    if abs(delta) > total:
        raise ValueError(
            f"شريط فوتبرنت غير متسق: |delta|={abs(delta)!r} أكبر من الحجم "
            f"الكلي {total!r} — الفرق بين الطرفين لا يعلو مجموعهما"
        )
    if total == 0.0:
        return 0.0
    return delta / total


def directional_response(candle: Candle, direction: int) -> float:
    """الاستجابة السعرية باتجاه معلوم: ‎+1 ⇒ close−open، ‎−1 ⇒ open−close.

    قيمة سالبة تعني استجابة معاكسة للاتجاه المطلوب — صادقة بإشارتها.

    :raises ValueError: اتجاه خارج {+1, −1}.
    """
    if direction not in (1, -1):
        raise ValueError(f"اتجاه غير صالح: {direction!r} — المتوقع +1 أو -1")
    if direction > 0:
        return candle.close - candle.open
    return candle.open - candle.close


def check_flow_inputs(
    bar: FootprintBar,
    candle: Candle,
    vol: VolatilityState | None,
) -> None:
    """حارس الثلاثية الصرف: إغلاق، تطابق ثنائية، ولا حالة تقلب من المستقبل.

    - **الشريط والشمعة مغلقيْن (§27/§33.2)**: المتطور لا يُقاس — فصل
      المتطور عن المؤكد مسؤولية الابتلاع.
    - **الثنائية متطابقة**: ``bar`` و``candle`` لنفس الشريط (أداة/إطار/
      ``bar_time``) — التغذية غير المتسقة خطأ قانوني صاخب لا قياس عليها.
    - **لا-نظرة-مستقبلية (§26.3)**: حالة تقلب بطابع أحدث من الشمعة تُرفض؛
      الأقدم مسموحة (قيمها الدافئة ``None`` تعلن نفسها).

    :raises ValueError: أي خرق مما سبق.
    """
    if not bar.is_closed or not candle.is_closed:
        raise ValueError(
            "الكاشف يستهلك الأشرطة المغلقة فقط (§27/§33.2) — "
            "فصل المتطور عن المؤكد مسؤولية الابتلاع عبر is_closed"
        )
    if bar.instrument_id != candle.instrument_id or bar.timeframe != candle.timeframe:
        raise ValueError(
            f"تغذية غير متسقة: شريط فوتبرنت ({bar.instrument_id!r}, {bar.timeframe!r}) "
            f"مقابل شمعة ({candle.instrument_id!r}, {candle.timeframe!r}) — "
            "الكاشف يقيس ثنائية الشريط الواحد"
        )
    if bar.bar_time != candle.bar_time:
        raise ValueError(
            f"طابع لا يطابق: شريط فوتبرنت عند {bar.bar_time} مقابل شمعة عند "
            f"{candle.bar_time} — الثنائية يجب أن تكون لنفس الشريط"
        )
    if vol is not None and vol.bar_time is not None and vol.bar_time > candle.bar_time:
        raise ValueError(
            f"حالة تقلب من المستقبل: vol.bar_time={vol.bar_time} أحدث من شمعة "
            f"الحكم {candle.bar_time} — تسريب §26.3 يُرفض صاخبًا"
        )


# ═══════════════════════ المصفوفة §12.2 ═══════════════════════


def classify_effort_vs_result(
    bar: FootprintBar,
    candle: Candle,
    vol: VolatilityState | None,
    response_min_mult: float | None = None,
) -> EffortResultState:
    """تصنيف شريط واحد على مصفوفة §12.2 — دالة صرفة حتمية بلا حالة.

    - **الجهد**: ``|bar_delta_share(bar)| ≥ EFFORT_MIN_SHARE`` (حد مغلق).
    - **النتيجة**: استجابة السعر باتجاه الدلتا مقابل العتبة التطبيعية
      ``vol.threshold(FLOW_RESPONSE_MIN)`` **سعرًا بسعر** (حد مغلق)؛
      الدلتا المعدومة ⇒ استجابة صفر معلن (لا اتجاه جهد يُستجاب له).
    - ``response_min_mult``: تجاوز معامل العتبة (يفوز على الافتراضي
      0.5) — يجب أن يكون محدودًا موجبًا وإلا رُفض صاخبًا **حتى عند غياب
      التقلب** (المدخل الفاسد يُرفض دائمًا لا يُبتلع صمتًا).
    - بلا تقلب قابل للاستخدام (``vol`` غائب أو ATR غائب/منحل) ⇒
      ``INSUFFICIENT_VOLATILITY`` — لا قرار بلا عتبة (§16).

    خاصية بوابة المرحلة (اختبار اكتمال التغطية): كل ثلاثية صالحة تقع في
    حالة واحدة من الخمس حصرًا، والخلية مشتقة حتميًا من
    (جهد كبير؟ × استجابة قوية؟) — تقسيم حصري كامل.
    """
    if response_min_mult is not None and (
        not isfinite(response_min_mult) or response_min_mult <= 0.0
    ):
        raise ValueError(
            f"معامل تجاوز غير صالح لعتبة الاستجابة: {response_min_mult!r} — "
            "يجب أن يكون عددًا محدودًا موجبًا"
        )
    check_flow_inputs(bar, candle, vol)
    atr = usable_atr(vol)
    if vol is None or atr is None:
        return EffortResultState.INSUFFICIENT_VOLATILITY
    overrides = None
    if response_min_mult is not None:
        overrides = {ThresholdKey.FLOW_RESPONSE_MIN: response_min_mult}
    threshold = vol.threshold(ThresholdKey.FLOW_RESPONSE_MIN, overrides)
    # atr متاحة فالعتبة ليست None عقديًا؛ الفحص دفاع صريح لا يضر.
    if threshold is None:
        return EffortResultState.INSUFFICIENT_VOLATILITY
    share = bar_delta_share(bar)
    effort_large = abs(share) >= EFFORT_MIN_SHARE
    if share > 0.0:
        response = candle.close - candle.open
    elif share < 0.0:
        response = candle.open - candle.close
    else:
        response = 0.0
    response_strong = response >= threshold
    if effort_large:
        if response_strong:
            return EffortResultState.AGREE_EFFORT_RESULT
        return EffortResultState.EFFORT_NO_RESULT
    if response_strong:
        return EffortResultState.RESULT_NO_EFFORT
    return EffortResultState.LOW_EFFORT_LOW_RESULT


def efficiency(response_atr: float, delta_share_abs: float) -> float:
    """كفاءة الدلتا: ``response_atr / |delta_share|`` — استجابة لكل وحدة جهد.

    القياس الأولي لـFLOW_CONTINUATION (§20) والأساس الكمي لعنصري
    الإنهاك أ/د (§12.4). الاستجابة السالبة ⇒ كفاءة سالبة (جهد أنتج حركة
    معاكسة) — القيمة الصرفة قد تكون سالبة؛ عقود الحمولات (PositiveFloat)
    هي التي تشترط الموجبة عند البث، لا هذه الدالة.

    :raises ValueError: ``delta_share_abs`` غير محدودة أو ‏≤ 0 (لا كفاءة
        بلا جهد — القسمة على صفر تُرفض صاخبة ولا تُختلق inf)، أو
        ``response_atr`` غير محدودة.
    """
    if not isfinite(response_atr):
        raise ValueError(f"استجابة غير محدودة: {response_atr!r} — الكفاءة قياس محدود")
    if not isfinite(delta_share_abs) or delta_share_abs <= 0.0:
        raise ValueError(
            f"جهد غير صالح للكفاءة: {delta_share_abs!r} — يجب أن يكون حصة "
            "دلتا محدودة موجبة (لا كفاءة بلا جهد)"
        )
    return response_atr / delta_share_abs


# ═══════════════════════ حارس التدفق الموضعي ═══════════════════════


class FlowGuards:
    """حوارس تدفق موضعي واحد لكاشفي التدفق (الامتصاص/الإنهاك).

    عقد واحد بنمط ``structure._guards.StreamGuards`` (مكتوب محليًا لا
    مستوردًا من البنية — عقد import-linter «كاشفات مستقلة» يمنع
    الاستيراد بين الكواشف):

    - **الهوية**: كاشف واحد = زوج (أداة، إطار) واحد — يُلتقط من أول شريط
      أو يُمرر صراحة في البناء؛ أي خلط لاحق ⇒ ``ValueError`` صاخب.
    - **الترتيب التصاعدي القطعي**: ``bar_time`` الجديد يعلو آخر شريط
      قطعيًا — التساوي تكرار والانخفاض تأخر وكلاهما ``ValueError``:
      كاشفا التدفق آلات حالة متسلسلة (عداءات الفشل، الأقفال، نوافذ
      الكفاءة) يكسرها ما يكسر الترتيب — نفس القرار الموثق في البنية.
    - **الثنائية والتقلب**: عبر :func:`check_flow_inputs` عند كل شريط
      (إغلاق + تطابق + لا حالة من المستقبل).
    """

    def __init__(
        self,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._identity: tuple[str, str] | None = (
            (instrument_id, timeframe)
            if instrument_id is not None and timeframe is not None
            else None
        )
        self._last_bar_time: datetime | None = None

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شريط إن لم تُمرر في البناء."""
        return self._identity[0] if self._identity is not None else None

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شريط إن لم يُمرر في البناء."""
        return self._identity[1] if self._identity is not None else None

    def check(self, bar: FootprintBar, candle: Candle, vol: VolatilityState | None) -> None:
        """الحارس الكامل: الثنائية الصرفة ثم الهوية والترتيب التصاعدي.

        :raises ValueError: شريط/شمعة غير مغلقة أو ثنائية غير متطابقة أو
            حالة تقلب من المستقبل (عبر :func:`check_flow_inputs`)، أو خلط
            هوية، أو ``bar_time`` لا يعلو آخر شريط قطعيًا.
        """
        check_flow_inputs(bar, candle, vol)
        if self._identity is None:
            self._identity = (bar.instrument_id, bar.timeframe)
            self._last_bar_time = bar.bar_time
            return
        expected_instrument, expected_timeframe = self._identity
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
        assert last is not None  # الهوية لا تثبت إلا مع آخر طابع
        if bar.bar_time == last:
            raise ValueError(
                f"تكرار bar_time لشريط مكتمل سبق استهلاكه: {bar.bar_time} — "
                "التكرار خطأ قانوني عند المكتملات"
            )
        if bar.bar_time < last:
            raise ValueError(
                f"شريط متأخر (bar_time أقدم من آخر مكتمل): {bar.bar_time} بعد "
                f"{last} — كاشفات التدفق آلات حالة متسلسلة ترفض المتأخر رفضًا صريحًا"
            )
        self._last_bar_time = bar.bar_time
