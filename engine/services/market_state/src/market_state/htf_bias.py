"""انحياز الإطار الأعلى (§9.2) كحالة موضعية — **سياق لا مشغل**.

نص §9.2 حرفيًا: «HTF bias is contextual evidence. It does not trigger a
trade» — انحياز HTF دليل سياقي يُستهلك كخلفية للتفسير والأهلية في
المراحل اللاحقة؛ لا يفوّض أمرًا بذاته ولا يُعامل كمشغل دخول/خروج أبدًا.

**قيود المرحلة 2 الموثقة صراحة**: مدخلات §9.2 الكاملة (تتابع قمم/قيعان
مؤكدة، اتجاه البنية الخارجية، نطاق المعالجة الحالي، علاقة السيولة
الكبرى، حالة التوسع/الانكماش، إزاحة HTF) تأتي من محرك البنية في
المرحلة 3. هذه النسخة **وكيل مرحلي (proxy)** لا يستعمل إلا ما توفره
المرحلة 2: كفاءة اتجاهية بإشارتها + سمات التقلب. عقد الواجهة مصمم
ليُستبدل التغذية دون تغيير المستهلك: :class:`HtfBiasInputs` وحدها تحمل
التغذية (تتسع/تُستبدل في المرحلة 3)، بينما ``update`` و:class:`HtfBiasState`
مستقرتان للمستهلكين.

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_htf_bias.py):

- **الحتمية الصرفة**: نفس تسلسل المدخلات ⇒ نفس تتابع الحالات بالتطابق
  التام — لا عشوائية ولا وقت ولا حالة خفية.

- **لا نظرة مستقبلية (§26.3)**: حالة الشمعة t دالة في المدخلات [0..t]
  حصرًا؛ حالات البادئة لا تتغير بإضافة ذيل أبدًا (خاصية مختبرة).

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
  انهيار)؛ الانحياز المؤكد داخليًا محفوظ، وتُقطع سلسلة التأكيد.

- **العتبات نسبية لا سعرية إطلاقًا**: الكفاءات ∈ (0, 1) — لا مجال لأي
  ثابت ticks/pips مطلق (فحص وقائي يرفض العتبات السعرية).
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


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class HtfBiasConfig:
    """إعداد محرك الانحياز — عتبات نسبية قابلة للمعايرة (ليست توصية).

    الحقل الإضافي الموثق عن نص المهمة: ``transition_flips`` (عدد
    الانعكاسات الاتجاهية المتناوبة قبل فرض قراءة TRANSITION — «تذبذب
    المرشح المتكرر» في النص) — أُضيف حقلًا معلنًا بدل ثابت مخفي.
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


# ═════════════════════════════ المدخلات ═════════════════════════════


@dataclass(frozen=True)
class HtfBiasInputs:
    """تغذية المحرك عند كل شمعة مغلقة — **بدايات مرحلية (proxies)**.

    هذه بدايات مرحلية من سمات المرحلة 2 حصرًا؛ المرحلة 3 ستغذي التتابع
    البنيوي (قمم/قيعان مؤكدة، بنية خارجية، نطاق معالجة، علاقة سيولة)
    عبر توسيع/استبدال هذه الحزمة وحدها — المستهلك
    (:meth:`HtfBiasEngine.update` و:class:`HtfBiasState`) لا يتغير.

    - ``directional_efficiency`` ∈ [0, 1] — قدرة الحركة الموجهة (ER).
    - ``efficiency_sign`` ∈ {‎+1, −1, 0‎} — إشارة ‎close_t − close_{t−window}‎
      (الER غير موقعة؛ الإشارة تحمل الاتجاه من المستدعي).
    - ``normalized_range`` = range/ATR ≥ 0 — سياق §9.2 (لا يدخل المرشح
      بعد؛ يشارك في بوابة النقص ويحفظ لاثبات التغذية).
    - ``atr_percentile`` ∈ [0, 1] — سياق نظام التقلب (المثل أعلاه).
    - ``displacement_proxy`` ∈ [0, 1] — يقرؤه المستدعي من مئيني توسع
      المدى كوكيل إزاحة HTF حتى محرك الإزاحة في المرحلة 3.

    القرار الموثق: الكفاءة وإشارتها وحدهما تقودان المرشح في هذه النسخة
    (النص يوجّه كذلك)؛ بقية الحقول تُغلق بوابة الاكتمال (أي None ⇒ لا
    قراءة) وتُحمل لاغناء المرحلة 3 دون كسر المستهلك. nan/inf لا تعبر
    إطلاقًا (رفض صاخب) — الحالة وعدُ قيم محدودة أو غياب معلن.
    """

    directional_efficiency: float | None
    efficiency_sign: int | None
    normalized_range: float | None
    atr_percentile: float | None
    displacement_proxy: float | None

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
    عند كل شمعة مغلقة بترتيب تصاعدي — عقد الترتيب على المستدعي. انظر
    عقود الموديول كاملة (الحتمية/التذبذب/عدم التماثل مع مصنف النظام).
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
          الانحياز المؤكد داخليًا محفوظ.
        - ما عداهما: مرشح خام ← فرض TRANSITION عند بلوغ التذبذب ← بوابة
          التأكيد (``confirm_bars`` متتالية) — وTRANSITION يثبت هنا.
        """
        cfg = self._config
        self._bars_seen += 1
        if self._bars_seen < cfg.warmup_bars:
            self._state = HtfBiasState(bars_seen=self._bars_seen, data_sufficient=False)
            return self._state
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
