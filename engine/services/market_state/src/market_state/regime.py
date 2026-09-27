"""مصنف نظام السوق (§9.3) — حالة موضعية حتمية ببوابة تأكيد (hysteresis).

**جوهر التصميم — فصل مسؤولية صارم**: المصنف لا يحسب سماته بنفسه إطلاقًا؛
المستدعي يملأ :class:`RegimeFeatures` من طبقة السمات
(:mod:`features.vol_features` عبر السجل المركزي) ومن لقطة
:class:`~market_state.volatility.VolatilityState` — فيبقى المصنف نقاءً
حتميًا قابلًا للإعادة المعزولة والاختبار بقيم مصنوعة يدويًا بمسارات
معروفة (لا شموع ولا نوافذ داخله). عقد الترتيب والشموع المغلقة على عاتق
المستدعي (انظر عقود :mod:`market_state.volatility`).

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_regime.py):

- **الحتمية الصرفة**: نفس تسلسل المدخلات ⇒ نفس تتابع الحالات بالتطابق
  التام — لا عشوائية ولا وقت ولا حالة خفية خارج الحالة المعلنة.

- **لا نظرة مستقبلية (§26.3)**: حالة الشمعة t دالة في المدخلات [0..t]
  حصرًا؛ حالات البادئة لا تتغير بإضافة ذيل أبدًا (خاصية مختبرة).

- **بوابة التأكيد (hysteresis)**: القراءة الخام مرشح نظري فقط — الانتقال
  لا يثبت إلا بعد ``confirm_bars`` قراءة متتالية بنفس المرشح؛ التذبذب
  يبقي الحالة القديمة (لا رفرفة)، وقطع السلسلة بمرشح مختلف يعيد العد
  صفرًا. الانتقالات المؤكدة تُحصى في ``RegimeState.transitions`` (يشمل
  التأسيس الأول من UNKNOWN — تغيّر الحالة المعلنة).

- **TRANSITION مموه عمدًا ولا يثبت أبدًا**: قاعدة 7 مصممة كمصيد الغموض —
  كفاءة وسطى بلا توسع ليست نظامًا قابلاً للسكنى؛ يظل المرشح معلقًا
  (``pending_count`` يتراكم إخباريًا بلا سقف) ولا يلتزم أبدًا، فتبقى
  الحالة المؤكدة الأخيرة هي المعتمدة حتى يظهر مرشح ملموس يثبت. السبب
  الموثق: أنظمة §9.3 سلوكيات سوقية ملموسة، والغموض المستمر ليس نظامًا
  جديدًا — إسكانه كان سيولّد رفرفة كاذبة حول منطقة رمادية.

- **الدافئ**: قبل ``warmup_bars`` شمعة ⇒ UNKNOWN بلا قراءات إطلاقًا؛
  ``data_sufficient = bars_seen ≥ warmup_bars`` بنفس دلالة محرك التقلب
  (اكتمال عند العدد نفسه). دافئ السمات نفسه يظهر للمصنف كقيم None
  (مسؤولية المستدعي في الملء) — الدافئ هنا أرضية إضافية موثقة.

- **السمات الناقصة**: أي حقل None ⇒ UNKNOWN لهذا التحديث حصرًا (لا
  انهيار)؛ النظام المؤكد داخليًا محفوظ ولا يُنسى بعد الفجوة (لا يعاد
  تأسيسه من الصفر)، وتُقطع سلسلة التأكيد — القراءة الغائبة لا تمدد شيئًا.

- **العتبات نسبية لا سعرية إطلاقًا** (بوابة خروج المرحلة 2): مئينيات
  وكفاءات ∈ (0, 1)؛ ``volume_concentration_high`` نسبة حجم إلى متوسط
  نافذته (بلا وحدة)؛ ``gap_shock_atr`` نسبة فجوة إلى ATR — لا مجال لأي
  ثابت ticks/pips مطلق في هذا الإعداد (فحص وقائي يرفض العتبات السعرية).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from schemas import MarketRegime

__all__ = [
    "REGIME_RULES_DOC",
    "RegimeClassifier",
    "RegimeConfig",
    "RegimeFeatures",
    "RegimeState",
]


#: جدول قرار المرشح الخام الموثق — بوابة «تتابعات الحالات موثقة» للمرحلة 2.
#: القيم الرقمية في ذيله أمثلة على افتراضات ``RegimeConfig`` الافتراضية
#: (تُعاير من دفتر التجارب/الاستئصال 2-e)؛ الصياغة الرمزية بالعتبات هي
#: المرجع الدائم في :meth:`RegimeClassifier._raw_candidate`.
REGIME_RULES_DOC = """\
جدول قرار المرشح الخام (§9.3) — أول قاعدة تطابق تفوز (أولوية صارمة):

 1. VOLATILITY_SHOCK   atr_percentile >= atr_pct_shock
                       أو gap_shock >= gap_shock_atr (نسبة ATR)
                       — أولوية قصوى حتى مع كفاءة اتجاهية 1.0.
 2. TREND_EXPANSION    directional_efficiency >= efficiency_trend
                       و( atr_percentile >= atr_pct_mid
                          أو range_expansion >= range_expansion_high
                          أو volume_concentration >= volume_concentration_high )
 3. TREND_PULLBACK     directional_efficiency >= efficiency_trend
                       بعد استنفاد مؤكدات قاعدة 2 — حركة موجّهة داخل
                       نظام هادئ نسبيًا (شرط atr < high الحرفي يبتلع
                       في البقية: من بلغ high كان atr >= mid سلفًا).
 4. COMPRESSION        directional_efficiency <= efficiency_range
                       و atr_percentile <= atr_pct_low
 5. RANGE_BALANCE      directional_efficiency <= efficiency_range
 6. RANGE_EXPANSION    range_expansion >= range_expansion_high
                       دون كفاءة اتجاهية (فعلية في منطقة الكفاءة الوسطى)
 7. TRANSITION         الباقي — غموض مموه عمدًا (لا يثبت أبدًا)

 UNKNOWN               قبل اكتمال warmup_bars أو عند أي سمة ناقصة
                       (None) — لهذا التحديث حصرًا؛ النظام المؤكد
                       داخليًا محفوظ ولا يُنسى بعد الفجوة.

قرارات موثقة:
- atr_pct_mid = (atr_pct_low + atr_pct_high) / 2 — اشتقاق لا مقبض إضافي
  («mid-ish» في نص المهمة)؛ يضمن mid < high دائمًا ما دام low < high.
- volume_concentration يدخل قاعدة 2 كمؤكد توسع ثالث: تركيز الحجم يسبق
  عادة لحاق مئيني ATR — قرار موضع الاستخدام (النص يعدّه سمة بلا موضع).
- normalized_range يُحمل في الواجهة لاكتمال قائمة سمات §9.3 ويشارك في
  بوابة النقص، ولا يدخل الجدول — لا عتبة معلنة له في الإعداد.
- بالأولوية الصارمة، المنطقة الفعلية لكل قاعدة (بالافتراضيات):
  2: eff>=0.55 مع (atr>=0.50 أو re>=0.75 أو volc>=2.0)
  3: eff>=0.55 بلا أي مؤكد من قاعدة 2
  4: eff<=0.30 و atr<=0.20
  5: eff<=0.30 و atr>0.20
  6: 0.30<eff<0.55 و re>=0.75
  7: 0.30<eff<0.55 و re<0.75
- البوابة: أي انتقال يحتاج confirm_bars قراءة متتالية بنفس المرشح؛
  TRANSITION يظل معلقًا للأبد؛ أي None يقطع السلسلة ويعيد العد صفرًا.
"""


# ═════════════════════════════ الإعداد ═════════════════════════════


def _check_unit_interval(name: str, value: float) -> None:
    """تحقق صاخب لنطاق [0, 1] لقيمة موجودة (غير None)."""
    if not isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"السمة {name} يجب أن تكون عددًا محدودًا في [0, 1] أو None؛ وُجدت {value!r}")


def _check_non_negative(name: str, value: float) -> None:
    """تحقق صاخب لقيمة محدودة غير سالبة (غير None)."""
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"السمة {name} يجب أن تكون عددًا محدودًا غير سالب أو None؛ وُجدت {value!r}")


@dataclass(frozen=True)
class RegimeConfig:
    """عتبات المصنف — **نسبية لا سعرية إطلاقًا** (بوابة خروج المرحلة 2).

    كل القيم افتراضات إعدادية معلنة قابلة للمعايرة (دفتر التجارب ومِحور
    الاستئصال 2-e) — **ليست توصيات تداول**. المئينيات والكفاءات ∈ (0, 1)؛
    ``volume_concentration_high`` نسبة حجم إلى متوسط نافذته (1.0 = عادي)؛
    ``gap_shock_atr`` نسبة فجوة إلى ATR — كلاهما بلا وحدة سعرية.

    الحقل الإضافي الموثق عن نص المهمة: ``gap_shock_atr`` (عتبة صدمة الفجوة
    كنسبة ATR — النص يوثق 3.0) — أُضيف حقلًا ليظل قابلاً للمعايرة بلا
    ثابت مخفي في الشيفرة.
    """

    #: كفاءة كوفمان التي تُعدّ حركة موجّهة (عتبة الاتجاه).
    efficiency_trend: float = 0.55
    #: الكفاءة التي تحتها يُعدّ السوق بلا اتجاه (عتبة النطاق).
    efficiency_range: float = 0.30
    #: مئيني ATR الذي يُعدّ تقلبًا مرتفعًا.
    atr_pct_high: float = 0.80
    #: مئيني ATR الذي تحته يُعدّ التقلب أرضيًا.
    atr_pct_low: float = 0.20
    #: مئيني ATR لحد الصدمة (فوق العالي حصرًا).
    atr_pct_shock: float = 0.97
    #: مئيني توسع المدى الذي يُعدّ توسعًا مرتفعًا.
    range_expansion_high: float = 0.75
    #: تركيز الحجم (حجم الشمعة ÷ متوسط نافذتها) الذي يُعدّ مؤكد توسع.
    volume_concentration_high: float = 2.0
    #: صدمة الفجوة كنسبة ATR (حقل إضافي موثق — النص يوثق 3.0).
    gap_shock_atr: float = 3.0
    #: عدد قراءات التأكيد المتتالية قبل تثبيت أي انتقال (hysteresis).
    confirm_bars: int = 3
    #: أرضية دافئ إضافية للمصنف — دافئ السمات نفسه يظهر كقيم None.
    warmup_bars: int = 30

    def __post_init__(self) -> None:
        for name, value in (
            ("efficiency_trend", self.efficiency_trend),
            ("efficiency_range", self.efficiency_range),
            ("atr_pct_high", self.atr_pct_high),
            ("atr_pct_low", self.atr_pct_low),
            ("range_expansion_high", self.range_expansion_high),
        ):
            if not isfinite(value) or not 0.0 < value < 1.0:
                raise ValueError(f"عتبة {name} يجب أن تكون نسبة محدودة في (0, 1)؛ وُجدت {value!r}")
        if not isfinite(self.atr_pct_shock) or not 0.0 < self.atr_pct_shock <= 1.0:
            raise ValueError(
                f"عتبة atr_pct_shock يجب أن تكون نسبة محدودة في (0, 1]؛ وُجدت {self.atr_pct_shock!r}"
            )
        for name, value in (
            ("volume_concentration_high", self.volume_concentration_high),
            ("gap_shock_atr", self.gap_shock_atr),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"عتبة {name} يجب أن تكون نسبة محدودة موجبة؛ وُجدت {value!r}")
        if self.efficiency_trend <= self.efficiency_range:
            raise ValueError(
                f"عتبة الاتجاه يجب أن تعلو عتبة النطاق؛ وُجد trend={self.efficiency_trend} "
                f"و range={self.efficiency_range}"
            )
        if self.atr_pct_high <= self.atr_pct_low:
            raise ValueError(
                f"atr_pct_high يجب أن تعلو atr_pct_low؛ وُجد high={self.atr_pct_high} "
                f"و low={self.atr_pct_low}"
            )
        if self.atr_pct_shock <= self.atr_pct_high:
            raise ValueError(
                f"atr_pct_shock يجب أن تعلو atr_pct_high؛ وُجد shock={self.atr_pct_shock} "
                f"و high={self.atr_pct_high}"
            )
        if self.confirm_bars < 1:
            raise ValueError(f"confirm_bars يجب أن يكون ≥ 1؛ وُجد {self.confirm_bars}")
        if self.warmup_bars < 0:
            raise ValueError(f"warmup_bars يجب أن يكون ≥ 0؛ وُجد {self.warmup_bars}")

    @property
    def atr_pct_mid(self) -> float:
        """منتصف نطاق التقلب المستقر: ‎(atr_pct_low + atr_pct_high) / 2‎.

        قرار موثق: النص يقول «mid-ish» — الاشتقاق من العتبتين المعلنتين
        بدل حقل إضافي يقلل المقابض ويضمن ‎mid < high‎ دائمًا.
        """
        return (self.atr_pct_low + self.atr_pct_high) / 2.0


# ═════════════════════════════ المدخلات ═════════════════════════════


@dataclass(frozen=True)
class RegimeFeatures:
    """مدخلات المصنف عند كل شمعة مغلقة — يملؤها المستدعي (فصل مسؤولية).

    القيم ``None`` تعني «لم تتوفر بعد» (دافئ سلسلة السمة) أو «انحلت»
    (حواف quantmath حُوّلت None في :class:`~market_state.volatility.VolatilityState`)
    — nan/inf لا تعبر إلى هنا إطلاقًا: أي قيمة غير محدودة تُرفض رفضًا
    صاخبًا (الحالة وعدُ قيم محدودة أو غياب معلن).

    النطاقات الموثقة:
    - ``directional_efficiency`` ∈ [0, 1] — كفاءة كوفمان ER.
    - ``normalized_range`` = range/ATR ≥ 0 — بلا سقف (المدى قد يبلغ عدة ATR).
    - ``atr_percentile`` و``range_expansion_percentile`` ∈ [0, 1].
    - ``volume_concentration`` ≥ 0 — 1.0 حجم عادي نسبيًا.
    - ``gap_shock`` ≥ 0 — فجوة معيارية بالـATR (نسبة لا سعر).
    """

    directional_efficiency: float | None
    normalized_range: float | None
    atr_percentile: float | None
    range_expansion_percentile: float | None
    volume_concentration: float | None
    gap_shock: float | None

    def __post_init__(self) -> None:
        if self.directional_efficiency is not None:
            _check_unit_interval("directional_efficiency", self.directional_efficiency)
        if self.atr_percentile is not None:
            _check_unit_interval("atr_percentile", self.atr_percentile)
        if self.range_expansion_percentile is not None:
            _check_unit_interval("range_expansion_percentile", self.range_expansion_percentile)
        if self.normalized_range is not None:
            _check_non_negative("normalized_range", self.normalized_range)
        if self.volume_concentration is not None:
            _check_non_negative("volume_concentration", self.volume_concentration)
        if self.gap_shock is not None:
            _check_non_negative("gap_shock", self.gap_shock)


# ═════════════════════════════ الحالة ═════════════════════════════


@dataclass(frozen=True)
class RegimeState:
    """لقطة حالة النظام عند شمعة مغلقة — خرج المصنف (§9.3).

    ``pending_regime``/``pending_count``: المرشح قيد التأكيد وعدّ قراءاته
    المتتالية — إخباري للرصد والتشخيص (يغذي لقطة حالة السوق 2-f) لا
    القرار. ``transitions``: عدد الانتقالات المؤكدة (يشمل التأسيس الأول
    من UNKNOWN — كل تغيّر للحالة المعلنة انتقال مؤكد).
    """

    regime: MarketRegime = MarketRegime.UNKNOWN
    pending_regime: MarketRegime | None = None
    pending_count: int = 0
    bars_seen: int = 0
    data_sufficient: bool = False
    transitions: int = 0


# ═════════════════════════════ المصنف ═════════════════════════════


class RegimeClassifier:
    """مصنف نظام السوق الموضعي (§9.3) — سمات شمعة ⇒ حالة بلا رفرفة.

    الاستخدام: أنشئ مصنفًا لكل (أداة، إطار) وغذّه :class:`RegimeFeatures`
    عند كل شمعة مغلقة بترتيب زمني تصاعدي — عقود الترتيب على المستدعي.
    انظر عقود الموديول كاملة (الحتمية/لا-نظرة-مستقبلية/hysteresis/None).
    """

    def __init__(self, config: RegimeConfig | None = None) -> None:
        self._config = config if config is not None else RegimeConfig()
        self._regime = MarketRegime.UNKNOWN
        self._pending: MarketRegime | None = None
        self._pending_count = 0
        self._bars_seen = 0
        self._transitions = 0
        self._state = RegimeState()

    @property
    def config(self) -> RegimeConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def state(self) -> RegimeState:
        """آخر حالة منتجة — الحالة الابتدائية قبل أي تغذية."""
        return self._state

    def update(self, features: RegimeFeatures) -> RegimeState:
        """استهلاك سمات شمعة مغلقة وإرجاع حالة النظام — عقود الموديول حرفيًا.

        - قبل ``warmup_bars`` ⇒ UNKNOWN بلا قراءة (شريط الدافئ لا يراكم
          تعليقًا — التعليق يبدأ مع أول قراءة).
        - أي حقل None ⇒ UNKNOWN لهذا التحديث حصرًا مع قطع سلسلة التأكيد؛
          النظام المؤكد داخليًا محفوظ.
        - ما عداهما: مرشح خام وفق :data:`REGIME_RULES_DOC` ثم بوابة
          التأكيد (``confirm_bars`` متتالية) — والانتقال المؤكد يُحصى.
        """
        cfg = self._config
        self._bars_seen += 1
        if self._bars_seen < cfg.warmup_bars:
            self._state = RegimeState(
                regime=MarketRegime.UNKNOWN,
                bars_seen=self._bars_seen,
                data_sufficient=False,
                transitions=self._transitions,
            )
            return self._state
        candidate = self._raw_candidate(features)
        if candidate is MarketRegime.UNKNOWN:
            # سمات ناقصة: لا قراءة لهذه الشمعة — تُقطع سلسلة التأكيد
            # ويُخرج UNKNOWN لهذا التحديث حصرًا (النظام الداخلي محفوظ).
            self._pending = None
            self._pending_count = 0
            self._state = RegimeState(
                regime=MarketRegime.UNKNOWN,
                bars_seen=self._bars_seen,
                data_sufficient=True,
                transitions=self._transitions,
            )
            return self._state
        if candidate is self._regime:
            # المرشح يطابق النظام المؤكد — لا تعليق ولا انتقال.
            self._pending = None
            self._pending_count = 0
        else:
            if self._pending is candidate:
                self._pending_count += 1
            else:
                self._pending = candidate
                self._pending_count = 1
            if candidate is not MarketRegime.TRANSITION and self._pending_count >= cfg.confirm_bars:
                # تثبيت الانتقال: confirm_bars قراءة متتالية بنفس المرشح.
                self._regime = candidate
                self._transitions += 1
                self._pending = None
                self._pending_count = 0
        self._state = RegimeState(
            regime=self._regime,
            pending_regime=self._pending,
            pending_count=self._pending_count,
            bars_seen=self._bars_seen,
            data_sufficient=True,
            transitions=self._transitions,
        )
        return self._state

    def _raw_candidate(self, features: RegimeFeatures) -> MarketRegime:
        """قراءة السمات اللحظية → مرشح نظري وفق :data:`REGIME_RULES_DOC`."""
        if (
            features.directional_efficiency is None
            or features.normalized_range is None
            or features.atr_percentile is None
            or features.range_expansion_percentile is None
            or features.volume_concentration is None
            or features.gap_shock is None
        ):
            return MarketRegime.UNKNOWN
        cfg = self._config
        eff = features.directional_efficiency
        atr_pct = features.atr_percentile
        re_pct = features.range_expansion_percentile
        # 1) الصدمة أولوية قصوى — حتى فوق كفاءة اتجاهية 1.0.
        if atr_pct >= cfg.atr_pct_shock or features.gap_shock >= cfg.gap_shock_atr:
            return MarketRegime.VOLATILITY_SHOCK
        # 2) اتجاه مؤكد بمؤكد توسعي واحد على الأقل (تقلب مرتفع نسبيًا أو
        #    توسع مدى أو تركيز حجم — الحجم يسبق عادة لحاق مئيني ATR).
        if eff >= cfg.efficiency_trend and (
            atr_pct >= cfg.atr_pct_mid
            or re_pct >= cfg.range_expansion_high
            or features.volume_concentration >= cfg.volume_concentration_high
        ):
            return MarketRegime.TREND_EXPANSION
        # 3) اتجاه بلا أي مؤكد توسعي — ساق اتجاهي داخل نظام هادئ نسبيًا
        #    (شاهد ترند عادي/ارتدادي داخل نطاق، لا اندفاع توسعي).
        if eff >= cfg.efficiency_trend:
            return MarketRegime.TREND_PULLBACK
        # 4) لا كفاءة مع تقلب أرضي → انضغاط (مزاد ضيق يتراكم).
        if eff <= cfg.efficiency_range and atr_pct <= cfg.atr_pct_low:
            return MarketRegime.COMPRESSION
        # 5) لا كفاءة → توازن نطاقي (ذهاب وإياب).
        if eff <= cfg.efficiency_range:
            return MarketRegime.RANGE_BALANCE
        # 6) توسع مدى بلا كفاءة اتجاهية — فعلية في المنطقة الوسطى
        #    (قواعد 4/5 استهلكت الكفاءة المنخفضة قبلها بالأولوية الصارمة).
        if re_pct >= cfg.range_expansion_high:
            return MarketRegime.RANGE_EXPANSION
        # 7) المنطقة الرمادية: كفاءة وسطى بلا توسع — مموهة عمدًا ولا تثبت.
        return MarketRegime.TRANSITION
