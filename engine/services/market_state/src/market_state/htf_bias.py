"""انحياز الإطار الأعلى (§9.2) كحالة موضعية — **سياق لا مشغل**.

نص §9.2 حرفيًا: «HTF bias is contextual evidence. It does not trigger a
trade» — انحياز HTF دليل سياقي يُستهلك كخلفية للتفسير والأهلية في
المراحل اللاحقة؛ لا يفوّض أمرًا بذاته ولا يُعامل كمشغل دخول/خروج أبدًا.

**وضعا التغذية — المرحلة 3 وصلت وADR-016 أُغلق**: تغذية §9.2 الكاملة
(تتابع قمم/قيعان خارجية مؤكدة، اتجاه البنية الخارجية، نطاق المعالجة
الحالي، حالة التوسع/الانكماش، إزاحة HTF) صارت متاحة عبر الحقول البنيوية
الاختيارية في :class:`HtfBiasInputs`. **الوضع البنيوي** يُفعَّل عند كل
تحديث يتوفر فيه تتابعا المتطرفات الخارجيين وإشارة إزاحة HTF وحالة
التوسع جميعًا (الأربعة المفعِّلة — عقد التفعيل في :class:`HtfBiasInputs`)،
وينتج المرشح الخام من
:meth:`HtfBiasEngine._structural_candidate`. وعند غياب أي منها — كليًا
أو جزئيًا — يعمل المحرك بوضع الوكيل (proxy) المرحلي **نفسه حرفيًا**:
الكفاءة الاتجاهية بإشارتها وسمات التقلب وحدها تقود، بتوافق خلفي كامل
(سلوك الوكيل محفوظ بايت-بايت واختبارات 2-d باقية خضراء بلا تعديل).
المستهلك لم يتغير أبدًا: ``update`` و:class:`HtfBiasState` مستقرتان
للمستهلكين، وآلية التأكيد كاملة (الدافئ/``confirm_bars``/
``transition_flips``) تعمل فوق المرشح الخام أيًا كان مصدره — «المرحلة 3
توسع التغذية دون مساس المستهلك» (ADR-016). أما «علاقة السيولة الكبرى»
(§9.2) فتبقى مسؤولية طبقة الدمج (§19) فوق كاشف السيولة — ليست حقلًا
هنا بنطاق هذه الترقية.

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_htf_bias.py و
tests/unit/test_htf_bias_structural.py — الوكيل والبنية على التوالي):

- **الحتمية الصرفة**: نفس تسلسل المدخلات ⇒ نفس تتابع الحالات بالتطابق
  التام — لا عشوائية ولا وقت ولا حالة خفية؛ تسري على الوضعين معًا
  (الوكيل والبنية).

- **لا نظرة مستقبلية (§26.3)**: حالة الشمعة t دالة في المدخلات [0..t]
  حصرًا؛ حالات البادئة لا تتغير بإضافة ذيل أبدًا (خاصية مختبرة). في
  الوضع البنيوي العقد موروث عبر التغذية نفسها: المتطرفات الخارجية
  تُستهلك «confirmed-as-supplied» — مؤكدة أصلًا بقاعدة النظر الخلفي
  الموثقة في كائن ``schemas.Swing`` (§11.1: confirmation_time =
  bar_time + تأخير التأكيد) — فلا إعادة فحص ولا استنتاج مما بعدها؛
  عقد الترتيب الزمني والاكتمال على المستدعي (كاشف البنية).

- **بوابة التأكيد (hysteresis)**: القراءة الخام مرشح نظري — الانحياز لا
  يثبت إلا بعد ``confirm_bars`` قراءة متتالية بنفس المرشح؛ قطع السلسلة
  يعيد العد صفرًا.

- **التذبذب ⇒ TRANSITION**: انعكاسات اتجاهية متناوبة (BULLISH↔BEARISH)
  بلا تأكيد تُعدّ في ``transition_flips``؛ عند بلوغها العتبة تُفرض قراءة
  TRANSITION (بغض النظر عن القراءة الخام) — سوق يتقاذف اتجاهه بلا
  استقرار هو بحكم التعريف في انتقال بنيوي. العد يُصفَّر عند تكرار
  اتجاهي متتالٍ (خمود التذبذب) وعند أي التزام مؤكد.

- **TRANSITION يثبت هنا بخلاف النظام (§9.3)**: في §9.2 الانتقالية حالة
  HTF مشروعة تُسكن (سوق يحسم اتجاهه الأعلى لاحقًا)، بينما في مصنف
النظام تُترك مموهة عمدًا — عدم التماثل موثق ومقصود في كلا الموديولين.

- **الدافئ**: قبل ``warmup_bars`` شمعة ⇒ UNKNOWN بلا قراءات؛
  ``data_sufficient = bars_seen ≥ warmup_bars`` بنفس دلالة محرك التقلب.

- **المدخلات الناقصة**: أي حقل None ⇒ UNKNOWN لهذا التحديث حصرًا (لا
  انهيار)؛ الانحياز المؤكد داخليًا محفوظ، وتُقطع سلسلة التأكيد. في
  الوضع البنيوي يشمل ذلك التتابع غير الكافي: أقل من قمتين أو قاعين
  مؤكدتين لا يسمح بتسمية HH/HL أصلًا (تسمية الذيل تستلزم اثنين على
  الأقل من كل جانب) ⇒ UNKNOWN لهذا التحديث حصرًا كذلك.

- **العتبات نسبية لا سعرية إطلاقًا**: الكفاءات والمئينيات وشطر الموضع
  كلها نسب — لا مجال لأي ثابت ticks/pips مطلق (فحص وقائي يرفض العتبات
  السعرية)؛ وأسعار المتطرفات والنطاق والإغلاق مدخلات بيانات يُقارن
  بعضها ببعضها نسبيًا، لا عتبات.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from schemas import HTFBias

__all__ = [
    "HtfBiasConfig",
    "HtfBiasEngine",
    "HtfBiasInputs",
    "HtfBiasState",
]


def _check_unit_interval(name: str, value: float) -> None:
    """تحقق صاخب لنطاق [0, 1] لقيمة موجودة (غير None)."""
    if not isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"المدخل {name} يجب أن يكون عددًا محدودًا في [0, 1] أو None؛ وُجد {value!r}")


def _check_non_negative(name: str, value: float) -> None:
    """تحقق صاخب لقيمة محدودة غير سالبة (غير None)."""
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"المدخل {name} يجب أن يكون عددًا محدودًا غير سالب أو None؛ وُجد {value!r}")


def _check_positive_price(name: str, value: float) -> None:
    """تحقق صاخب لسعر محدود موجب — الأسعار بيانات موجبة دومًا لا عتبات."""
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"المدخل {name} يجب أن يكون سعرًا محدودًا موجبًا أو None؛ وُجد {value!r}")


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class HtfBiasConfig:
    """إعداد محرك الانحياز — عتبات نسبية قابلة للمعايرة (ليست توصية).

    الحقل الإضافي الموثق عن نص المهمة 2-d: ``transition_flips`` (عدد
    الانعكاسات الاتجاهية المتناوبة قبل فرض قراءة TRANSITION — «تذبذب
    المرشح المتكرر» في النص) — أُضيف حقلًا معلنًا بدل ثابت مخفي.
    وحقلا المهمة 3-e البنيويان — ``contraction_threshold`` و
    ``range_position_split`` (كلاهما إعدادي قابل للمعايرة، ليس توصية) —
    يعملان في الوضع البنيوي وحده ولا يمسان وضع الوكيل أبدًا.
    """

    #: كفاءة الاتجاه الصاعد المطلوبة لقراءة BULLISH.
    efficiency_bull: float = 0.45
    #: كفاءة الاتجاه الهابط المطلوبة لقراءة BEARISH.
    efficiency_bear: float = 0.45
    #: عدد قراءات التأكيد المتتالية قبل تثبيت أي انتقال (hysteresis).
    confirm_bars: int = 5
    #: أرضية دافئ إضافية للمحرك — دافئ السمات نفسه يظهر كقيم None.
    warmup_bars: int = 20
    #: انعكاسات اتجاهية متناوبة قبل فرض قراءة TRANSITION (حقل إضافي موثق).
    transition_flips: int = 2
    #: مئيني توسع المدى الذي دونه يُعدّ السوق منكمشًا (الوضع البنيوي
    #: §9.2): البنية غير الموسّعة لا تحسم اتجاهًا — القراءة الاتجاهية
    #: تُهدَّأ إلى NEUTRAL. إعدادي (ليس توصية).
    contraction_threshold: float = 0.3
    #: شطر موضع الإغلاق في نطاق المعالجة (الوضع البنيوي §9.2): الموضع
    #: دونه قاعُ النطاق يناقض بنية صاعدة، وفوق ``1 − split`` قمتُه
    #: يناقض هابطة، وبينهما دليل محايد؛ 0.5 = الشطر النصفي البسيط.
    #: إعدادي (ليس توصية).
    range_position_split: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (
            ("efficiency_bull", self.efficiency_bull),
            ("efficiency_bear", self.efficiency_bear),
        ):
            if not isfinite(value) or not 0.0 < value < 1.0:
                raise ValueError(f"عتبة {name} يجب أن تكون نسبة محدودة في (0, 1)؛ وُجدت {value!r}")
        if self.confirm_bars < 1:
            raise ValueError(f"confirm_bars يجب أن يكون ≥ 1؛ وُجد {self.confirm_bars}")
        if self.warmup_bars < 0:
            raise ValueError(f"warmup_bars يجب أن يكون ≥ 0؛ وُجد {self.warmup_bars}")
        if self.transition_flips < 1:
            raise ValueError(f"transition_flips يجب أن يكون ≥ 1؛ وُجد {self.transition_flips}")
        for name, value in (
            ("contraction_threshold", self.contraction_threshold),
            ("range_position_split", self.range_position_split),
        ):
            if not isfinite(value) or not 0.0 < value < 1.0:
                raise ValueError(f"عتبة {name} يجب أن تكون نسبة محدودة في (0, 1)؛ وُجدت {value!r}")
        if self.range_position_split > 0.5:
            raise ValueError(
                f"عتبة range_position_split يجب ألا تتجاوز النصف (0, 0.5] — فوقه تتداخل "
                f"منطقتا التناقض؛ وُجدت {self.range_position_split!r}"
            )


# ═════════════════════════════ المدخلات ═════════════════════════════


@dataclass(frozen=True)
class HtfBiasInputs:
    """تغذية المحرك عند كل شمعة مغلقة — **وضعان موثقان (ADR-016)**.

    **وضع الوكيل (سمات المرحلة 2 — محفوظ حرفيًا)**: الحقول الخمسة الأولى
    بدايات مرحلية؛ ما لم يكتمل الوضع البنيوي (عقد التفعيل أدناه) تظل
    وحدها تقود المرشح بقرار 2-d نفسه: الكفاءة وإشارتها وحدهما تقودان
    والبقية تغلق بوابة الاكتمال. المرحلة 3 توسّع التغذية عبر الحقول
    الاختيارية أدناه دون تغيير المستهلك أبدًا.

    **الوضع البنيوي (تغذية §9.2 من كواشف المرحلة 3)**: يُفعَّل عند كل
    تحديث يتوفر فيه ``external_high_sequence`` و
    ``external_low_sequence`` و``htf_displacement_direction`` و
    ``expansion_state`` **جميعًا غير None** — عندئذ يحل المرشح البنيوي
    (:meth:`HtfBiasEngine._structural_candidate`) محل مرشح الوكيل
    كليًا: حقول الوكيل تُعزل (لا تساهم ولا تعرقل حتى لو حضرت كلها).
    أي غياب **جزئي** في الأربعة ⇒ وضع الوكيل بنفس سلوكه الأول — أولوية
    موثقة: النمط الكامل أو الوكيل، لا وضع هجين. و``dealing_range`` مع
    ``close_price`` محسّنان اختياريان: لا يفعّلان الوضع وحدهما، ويطبّق
    دليل الموضع متى حضرا معًا فوق القراءة البنيوية.

    حقول وضع الوكيل:

    - ``directional_efficiency`` ∈ [0, 1] — قدرة الحركة الموجهة (ER).
    - ``efficiency_sign`` ∈ {‎+1, −1, 0‎} — إشارة ‎close_t − close_{t−window}‎
      (الER غير موقعة؛ الإشارة تحمل الاتجاه من المستدعي).
    - ``normalized_range`` = range/ATR ≥ 0 — سياق §9.2 (لا يدخل المرشح
      بعد؛ يشارك في بوابة النقص ويحفظ لاثبات التغذية).
    - ``atr_percentile`` ∈ [0, 1] — سياق نظام التقلب (المثل أعلاه).
    - ``displacement_proxy`` ∈ [0, 1] — يقرؤه المستدعي من مئيني توسع
      المدى كوكيل إزاحة HTF حتى محرك الإزاحة في المرحلة 3؛ في الوضع
      البنيوي لا دور له إطلاقًا (الإزاحة الحقيقية في الحقل البنيوي).

    حقول الوضع البنيوي (تغذية §9.2 — المستدعي يملؤها من كواشف المرحلة 3):

    - ``external_high_sequence`` — أسعار القمم الخارجية المؤكدة بترتيب
      زمني تصاعدي (الأقدم أولاً) — «تتابع القمم/القيعان المؤكدة» §9.2؛
      من كائنات ``schemas.Swing`` بنطاق EXTERNAL، مؤكدة أصلًا بقاعدة
      النظر الخلفي (§11.1) وتُستهلك كما وصلت (confirmed-as-supplied).
    - ``external_low_sequence`` — القيعان الخارجية المؤكدة كذلك.
    - ``htf_displacement_direction`` ∈ {+1, −1, 0} — إشارة آخر إزاحة HTF
      مؤكدة («إزاحة HTF» §9.2 من كاشف الإزاحة §11.4)؛ 0 = لا إزاحة
      مؤكدة بعد.
    - ``expansion_state`` ∈ [0, 1] — حالة التوسع/الانكماش: مئيني توسع
      المدى من ``VolatilityState.range_expansion_percentile``.
    - ``dealing_range`` = (low, high) — نطاق المعالجة الحالي من القمم/
      القيعان الخارجية («نطاق المعالجة الحالي» §9.2)؛ low ≤ high
      (المساواة نطاق منحل يجعل دليل الموضع غائبًا لا خطأ تحقق).
    - ``close_price`` — إغلاق الشمعة (سعر موجب) لعلاقة الموضع في النطاق.

    القرار الموثق (2-d، وضع الوكيل): الكفاءة وإشارتها وحدهما تقودان
    المرشح؛ بقية حقول الوكيل تُغلق بوابة الاكتمال (أي None ⇒ لا قراءة)
    وتُحمل لاغناء التحليل دون كسر المستهلك. nan/inf لا تعبر إطلاقًا
    (رفض صاخب) — الحالة وعدُ قيم محدودة أو غياب معلن. التتابعان
    البنيويان قد يحملان أقل من عضوين (حتى الفارغ) — ذلك بيانات غير
    كافية تُقرأ UNKNOWN لهذا التحديث حصرًا، لا خطأ تحقق.
    """

    # ── وضع الوكيل (المرحلة 2 — محفوظ حرفيًا) ──
    directional_efficiency: float | None
    efficiency_sign: int | None
    normalized_range: float | None
    atr_percentile: float | None
    displacement_proxy: float | None
    # ── الوضع البنيوي (المرحلة 3 / 3-e — اختياري كله؛ الأربعة الأولى
    # معًا تفعّل النمط، والمحسّنان الأخيران لا يفعّلانه وحدهما) ──
    external_high_sequence: tuple[float, ...] | None = None
    external_low_sequence: tuple[float, ...] | None = None
    htf_displacement_direction: int | None = None
    expansion_state: float | None = None
    dealing_range: tuple[float, float] | None = None
    close_price: float | None = None

    def __post_init__(self) -> None:
        if self.directional_efficiency is not None:
            _check_unit_interval("directional_efficiency", self.directional_efficiency)
        if self.efficiency_sign is not None and self.efficiency_sign not in (-1, 0, 1):
            raise ValueError(
                f"المدخل efficiency_sign يجب أن يكون ‎+1/-1/0‎ أو None؛ وُجد {self.efficiency_sign!r}"
            )
        if self.atr_percentile is not None:
            _check_unit_interval("atr_percentile", self.atr_percentile)
        if self.displacement_proxy is not None:
            _check_unit_interval("displacement_proxy", self.displacement_proxy)
        if self.normalized_range is not None:
            _check_non_negative("normalized_range", self.normalized_range)
        # ── الحقول البنيوية (3-e): تحقق صاخب لا يعرف الأنماط ──
        if self.htf_displacement_direction is not None and (
            self.htf_displacement_direction not in (-1, 0, 1)
        ):
            raise ValueError(
                f"المدخل htf_displacement_direction يجب أن يكون +1/-1/0 أو None؛ "
                f"وُجد {self.htf_displacement_direction!r}"
            )
        if self.expansion_state is not None:
            _check_unit_interval("expansion_state", self.expansion_state)
        if self.dealing_range is not None:
            if len(self.dealing_range) != 2:
                raise ValueError(
                    f"المدخل dealing_range يجب أن يكون زوج (low, high)؛ "
                    f"وُجد بطول {len(self.dealing_range)}"
                )
            range_low, range_high = self.dealing_range
            if not isfinite(range_low) or not isfinite(range_high) or range_low > range_high:
                raise ValueError(
                    f"المدخل dealing_range يجب أن يكون ثنائية محدودة مرتبة "
                    f"(low ≤ high)؛ وُجد {self.dealing_range!r}"
                )
        if self.close_price is not None:
            _check_positive_price("close_price", self.close_price)
        for seq_name, sequence in (
            ("external_high_sequence", self.external_high_sequence),
            ("external_low_sequence", self.external_low_sequence),
        ):
            if sequence is not None:
                for member in sequence:
                    _check_positive_price(seq_name, member)


# ═════════════════════════════ الحالة ═════════════════════════════


@dataclass(frozen=True)
class HtfBiasState:
    """لقطة انحياز HTF عند شمعة مغلقة — خرج المحرك (§9.2).

    ``pending_bias``/``pending_count``: المرشح قيد التأكيد وعدّ قراءاته
    المتتالية — إخباري للرصد (يغذي لقطة حالة السوق 2-f) لا القرار.
    """

    bias: HTFBias = HTFBias.UNKNOWN
    pending_bias: HTFBias | None = None
    pending_count: int = 0
    bars_seen: int = 0
    data_sufficient: bool = False


# ═════════════════════════════ المحرك ═════════════════════════════


class HtfBiasEngine:
    """محرك انحياز HTF الموضعي (§9.2) — سياق لا مشغل تداول.

    الاستخدام: أنشئ محركًا لكل (أداة، إطار أعلى) وغذّه :class:`HtfBiasInputs`
    عند كل شمعة مغلقة بترتيب تصاعدي — عقد الترتيب على المستدعي. ينتقي
    المحرك وضعه عند كل تحديث من اكتمال الحقول البنيوية (انظر عقد
    التفعيل في :class:`HtfBiasInputs`)، وآلية التأكيد واحدة فوق المرشح
    أيًا كان مصدره. انظر عقود الموديول كاملة (الحتمية/التذبذب/عدم
    التماثل مع مصنف النظام).
    """

    def __init__(self, config: HtfBiasConfig | None = None) -> None:
        self._config = config if config is not None else HtfBiasConfig()
        self._bias = HTFBias.UNKNOWN
        self._pending: HTFBias | None = None
        self._pending_count = 0
        self._bars_seen = 0
        self._flips = 0
        self._last_directional: HTFBias | None = None
        self._state = HtfBiasState()

    @property
    def config(self) -> HtfBiasConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def state(self) -> HtfBiasState:
        """آخر حالة منتجة — الحالة الابتدائية قبل أي تغذية."""
        return self._state

    def update(self, inputs: HtfBiasInputs) -> HtfBiasState:
        """استهلاك مدخلات شمعة مغلقة وإرجاع الانحياز — عقود الموديول حرفيًا.

        - قبل ``warmup_bars`` ⇒ UNKNOWN بلا قراءة.
        - أي حقل None ⇒ UNKNOWN لهذا التحديث حصرًا مع قطع سلسلة التأكيد؛
          الانحياز المؤكد داخليًا محفوظ (وضع البنية: حقول الوكيل لا
          تُفحص أصلًا، والتتابع غير الكافي هو مصدر UNKNOWN ذاته).
        - ما عداهما: مرشح خام — بنيوي عند اكتمال الحقول البنيوية الأربعة
          (انتقاء لكل تحديث وحقول الوكيل معزولة) وإلا وكيل 2-d حرفيًا —
          ← فرض TRANSITION عند بلوغ التذبذب ← بوابة التأكيد
          (``confirm_bars`` متتالية) — وTRANSITION يثبت هنا.
        """
        cfg = self._config
        self._bars_seen += 1
        if self._bars_seen < cfg.warmup_bars:
            self._state = HtfBiasState(bars_seen=self._bars_seen, data_sufficient=False)
            return self._state
        # انتقاء الوضع عند كل تحديث (ADR-016): اكتمال الحقول البنيوية
        # الأربعة يفعّل المرشح البنيوي ويعزل حقول الوكيل كليًا؛ أي غياب
        # فيها يعيد وضع الوكيل حرفيًا — لا وضع هجين. الآلية فوق المرشح
        # واحدة مهما كان مصدره («المرحلة 3 توسع التغذية دون مساس المستهلك»).
        if (
            inputs.external_high_sequence is not None
            and inputs.external_low_sequence is not None
            and inputs.htf_displacement_direction is not None
            and inputs.expansion_state is not None
        ):
            raw = self._structural_candidate(
                inputs.external_high_sequence,
                inputs.external_low_sequence,
                inputs.htf_displacement_direction,
                inputs.expansion_state,
                inputs.dealing_range,
                inputs.close_price,
            )
        else:
            raw = self._raw_candidate(inputs)
        if raw is HTFBias.UNKNOWN:
            # مدخلات ناقصة: لا قراءة — تُقطع السلسلة ويُخرج UNKNOWN لهذا
            # التحديث حصرًا (الانحياز الداخلي المؤكد محفوظ).
            self._pending = None
            self._pending_count = 0
            self._state = HtfBiasState(bars_seen=self._bars_seen, data_sufficient=True)
            return self._state
        # عدّ التذبذب الاتجاهي: انعكاس جديد يزيد، تكرار متتالٍ يصفّر،
        # والقراءات غير الاتجاهية (NEUTRAL/المنطقة الرمادية) محايدة.
        if raw in (HTFBias.BULLISH, HTFBias.BEARISH):
            if self._last_directional is not None:
                if raw is self._last_directional:
                    self._flips = 0
                else:
                    self._flips += 1
            self._last_directional = raw
        reading = HTFBias.TRANSITION if self._flips >= cfg.transition_flips else raw
        if reading is self._bias:
            # القراءة تطابق الانحياز المؤكد — لا تعليق ولا انتقال.
            self._pending = None
            self._pending_count = 0
        else:
            if self._pending is reading:
                self._pending_count += 1
            else:
                self._pending = reading
                self._pending_count = 1
            if self._pending_count >= cfg.confirm_bars:
                # تثبيت الانتقال: confirm_bars قراءة متتالية بنفس المرشح —
                # وTRANSITION يثبت هنا (حالة §9.2 مشروعة) ويُصفَّر التذبذب.
                self._bias = reading
                self._flips = 0
                self._pending = None
                self._pending_count = 0
        self._state = HtfBiasState(
            bias=self._bias,
            pending_bias=self._pending,
            pending_count=self._pending_count,
            bars_seen=self._bars_seen,
            data_sufficient=True,
        )
        return self._state

    def _raw_candidate(self, inputs: HtfBiasInputs) -> HTFBias:
        """المرشح الخام — الكفاءة وإشارتها وحدهما تقودان (قرار موثق)."""
        if (
            inputs.directional_efficiency is None
            or inputs.efficiency_sign is None
            or inputs.normalized_range is None
            or inputs.atr_percentile is None
            or inputs.displacement_proxy is None
        ):
            return HTFBias.UNKNOWN
        cfg = self._config
        eff = inputs.directional_efficiency
        sign = inputs.efficiency_sign
        if sign == 1 and eff >= cfg.efficiency_bull:
            return HTFBias.BULLISH
        if sign == -1 and eff >= cfg.efficiency_bear:
            return HTFBias.BEARISH
        if eff < cfg.efficiency_bull and eff < cfg.efficiency_bear:
            return HTFBias.NEUTRAL
        # المنطقة الرمادية: عَبَرَ إحدى العتبتين بإشارة لا تطابقها (أو
        # إشارة معدومة مع كفاءة عالية — قراءة متناقضة) ⇒ TRANSITION خام.
        return HTFBias.TRANSITION

    def _structural_candidate(
        self,
        highs: tuple[float, ...],
        lows: tuple[float, ...],
        displacement: int,
        expansion: float,
        dealing_range: tuple[float, float] | None,
        close_price: float | None,
    ) -> HTFBias:
        """المرشح الخام البنيوي (الوضع البنيوي §9.2) — قواعد مرتبة الأولوية.

        القيم الأربعة الأولى مضمونة الاكتمال من :meth:`update` (النمط
        مفعّل)؛ ``dealing_range`` و``close_price`` محسّنان قد يغيبان —
        ودليل الموضع يلزمهما معًا (أحدهما وحده لا يطبّق النطاق أبدًا).

        1. **تتابع غير كافٍ** (أقل من قمتين أو قاعين) ⇒ UNKNOWN لهذا
           التحديث حصرًا — تسمية الذيل تستلزم اثنين على الأقل من كل جانب.
        2. **اتجاه البنية الخارجية من ذيلي التتابعين** بتسمية صارمة:
           المساواة لا ترقّي إلى HH/HL ولا تحطّ إلى LH/LL بل تمتنع عن
           التسمية — HH+HL ⇒ +1، LH+LL ⇒ −1، والمختلط (HH+LL أو
           LH+HL) والممتنع بأي تساوٍ ⇒ 0 (بنية غير موجّهة).
        3. بنية غير موجّهة ⇒ NEUTRAL — لا اتجاه يُدَّعى فلا تعزيز ولا
           تناقض ولا تهدئة بعدها (ولا تناقض إزاحة أصلًا).
        4. **تناقض الإزاحة**: بنية موجّهة تقابلها إزاحة HTF مؤكدة
           معاكسة ⇒ TRANSITION (نظير المنطقة الرمادية في وضع الوكيل) —
           يعلو التهدئة والموضع عمدًا: تعارض مؤكد بين دعويتين بنيويتين
           أبلغ من إنكار إعدادي أو مخالفة موقع.
        5. **الانكماش** (``expansion < contraction_threshold``) ⇒ NEUTRAL
           — بنية غير موسّعة لا تحسم اتجاهًا (إعدادي). والتوسع المتطرف
           لا يضيف شيئًا أبدًا (موثق عمدًا: لا مكافأة توسع — السياق لا
           يستعجل).
        6. **موضع الإغلاق يناقض البنية** ⇒ NEUTRAL — الموقع يخفض القراءة
           الاتجاهية ولا يرقّيها أبدًا: ``position = (close − low) /
           (high − low)``؛ دونه (``< split``) قاعُ النطاق يناقض بنية
           صاعدة وفوق ``1 − split`` قمتُه يناقض هابطة، وبينهما محايد؛
           والإغلاق خارج النطاق يقع في منطقة التناقض تلقائيًا بلا قصّ؛
           والنطاق المنحل (``low == high``) بلا موضع أصلًا ⇒ دليل غائب
           يُتجاهل.
        7. الباقي ⇒ الخريطة: +1 → BULLISH و −1 → BEARISH.
        """
        # (1) التتابع غير الكافي: لا تسمية ذيل أصلًا.
        if len(highs) < 2 or len(lows) < 2:
            return HTFBias.UNKNOWN
        # (2) اتجاه البنية من الذيلين — تسمية صارمة: المساواة لا ترقّي.
        highs_up = highs[-1] > highs[-2]
        highs_down = highs[-1] < highs[-2]
        lows_up = lows[-1] > lows[-2]
        lows_down = lows[-1] < lows[-2]
        if highs_up and lows_up:
            structure = 1
        elif highs_down and lows_down:
            structure = -1
        else:
            # مختلط (HH+LL / LH+HL) أو ممتنع بتساوٍ في أي جانب.
            structure = 0
        # (3) بنية غير موجّهة: لا اتجاه يُدَّعى فلا ما بعدها يطبق.
        if structure == 0:
            return HTFBias.NEUTRAL
        # (4) تناقض الإزاحة المؤكدة مع اتجاه البنية ⇒ المنطقة الرمادية
        #     البنيوية — يعلو التهدئة والموضع (أولوية موثقة أعلاه).
        if displacement != 0 and displacement != structure:
            return HTFBias.TRANSITION
        cfg = self._config
        # (5) الانكماش: بنية غير موسّعة لا تحسم اتجاهًا (إعدادي).
        if expansion < cfg.contraction_threshold:
            return HTFBias.NEUTRAL
        # (6) موضع الإغلاق: تخفيض لا ترقية — والنطاق المنحل دليل غائب.
        if dealing_range is not None and close_price is not None:
            range_low, range_high = dealing_range
            if range_high > range_low:
                position = (close_price - range_low) / (range_high - range_low)
                if structure == 1 and position < cfg.range_position_split:
                    return HTFBias.NEUTRAL
                if structure == -1 and position > 1.0 - cfg.range_position_split:
                    return HTFBias.NEUTRAL
        # (7) الخريطة النهائية — بلا مكافأة للتوسع المتطرف (موثق عمدًا).
        return HTFBias.BULLISH if structure == 1 else HTFBias.BEARISH
