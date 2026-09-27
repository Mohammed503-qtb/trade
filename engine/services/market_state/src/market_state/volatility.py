"""محرك التقلب الموضعي لكل (أداة، إطار) — §16 حرفيًا + بوابة المرحلة 2.

**جوهر بوابة خروج المرحلة 2 (§16)**: «كل عتبة سعرية تُطبَّع على الصيغة
``threshold = local_volatility × multiplier`` بدل ثابت ticks/pips واحد
عالمي». هذا الموديول هو مصدر تلك العتبات: لا يوجد فيه أي مسار ينتج عتبة
سعرية مطلقة — كل عتبة عبر :meth:`VolatilityState.threshold` هي ``atr ×
multiplier`` حصرًا (مضاعِف إعدادي معلن أو تجاوز صريح من المستدعي).

العقود الموثقة (تُختبر حرفيًا في tests/unit/test_volatility_engine.py):

- **لا نظرة مستقبلية (§26.3)**: الحالة عند الشمعة t تُحتسب من الشموع
  المغلقة [0..t] حصرًا — عبر سمة موضعية أطولها آخر شمعة؛ تعديل أي ذيل
  لا يمس حالات البادئة أبدًا (خاصية hypothesis في
  tests/property/test_features_properties.py).

- **الشمع المغلقة فقط (§27/§33.2)**: المحرك لا يقبل الشموع المتطورة —
  فصل المتطور عن المؤكد يتم في الابتلاع عبر ``is_closed``، والمحرك يفرض
  عقده على مدخلاته: ``is_closed=False`` ⇒ ValueError فوري.

- **عقد الشموع المغلقة المتكررة والمتأخرة**:
  - شمعة بـ``bar_time`` يكرر شمعة مغلقة **ما تزال محتجزة** في المخزن
    الدائري ⇒ **ValueError** (التكرار خطأ قانوني عند المغلقات — لا صمت).
    الكشف محدود بالمخزن المحتجز (طوله ``history_bars``)؛ تكرار أقدم من
    المحتجز يُعامل متأخرًا (أقدم من آخر مغلقة) ويُحصى — قيد ذاكرة موثق.
  - شمعة أقدم من آخر مغلقة مغلقةً (متأخرة) ⇒ **تُتجاهل وتُحصى** في
    ``stats.late_ignored`` — لا إسقاط صامت: الإحصاء جزء من الخرج، والحالة
    لا تتغير أبدًا بمتأخر.

- **عقد الإرجاع لـ``update``**: يعيد ``None`` حصرًا لأول شمعة تُستهلك على
  الإطلاق (لا حالة تقلب من شمعة واحدة). وما عداها: الحالة الجديدة بعد
  القبول، أو الحالة الحالية دون أي إعادة حساب عند متأخر (متطابقة مع
  ``state``).

- **الحتمية الصرفة**: نفس سلسلة الشموع المغلقة ⇒ نفس حالات بالتطابق
  التام (بما فيهما العتبات) — لا عشوائية ولا وقت ولا حالة مخفية.

- **المقايضة الموثقة — المخزن الدائري بدل التاريخ الكامل**: ATR وايلدر
  استدعاء ذاتي بذاكرة لا نهائية، وإعادة حساب التاريخ كله عند كل شمعة
  هدر. الحل الأمين: مخزن دائري بطول ``history_bars`` يكفي أدفأ أعمق
  سلسلة (بذرة ATR + نافذة المئيني)، تُعاد عليه الحزمة كاملة (المسار
  الوحيد A-02) ويؤخذ عنصره الأخير. النتيجة قيم «نافذة محدودة»: تختلف عن
  ATR التاريخ اللانهائي بفارق نسبي مضمحِل يتحلل بـ((period−1)/period)^k
  (‎≈0.06% للافتراضيات عند k≈100)، وتتطابق بتّية بين الحي والإعادة لأن
  كليهما يمر بالمخزن المنزلق نفسه — ولذا أي محرك بدأ من نقطة لاحقة
  يتطابق مع الحي بعد ``history_bars`` شمعة (ذاكرة محدودة موثقة).

- **دلالات ``data_sufficient`` والقيم None**: القيمة None تعني «لم تتوفر
  بعد» بدلالة الإتاحة (أول قيمة غير nan من مسار السمات — نوافذ المئيني
  قد تكون جزئية العضوية في حدود عقد استبعاد nan في quantmath) أو
  «انحلت» (nan/inf كناتج حراسة، كتسطّح تام ⇒ vol_of_vol = nan).
  ``data_sufficient`` = اكتمال دافئ أعمق سلسلة = ``warmup_bars_remaining
  == 0`` — وليس ضمانًا لقيم غير None على بيانات منحلة.

- **القيم غير المحدودة لا تعبر**: nan/inf في آخر عنصر (حواف quantmath)
  تُحوَّل None في الحالة — الحالة وعدُ قيم محدودة أو غياب معلن.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from types import MappingProxyType

from features import (
    FeatureSeries,
    atr_pct_series,
    atr_series,
    expected_holding_vol_series,
    gap_shock_series,
    range_expansion_series,
    realized_vol_series,
    spread_to_range_series,
    vol_of_vol_series,
)
from schemas import Candle

__all__ = [
    "DEFAULT_MULTIPLIERS",
    "ThresholdKey",
    "VolatilityConfig",
    "VolatilityEngine",
    "VolatilityEngineStats",
    "VolatilityState",
    "compute_market_volatility_summary",
]


# ═══════════════════════ العتبات التطبيعية (§16) ═══════════════════════


class ThresholdKey(StrEnum):
    """مفاتيح العتبات التطبيعية — كل عتبة ``atr × multiplier`` حصرًا.

    كل عضو موثق بمرجعه من Master Plan؛ المعاملات الافتراضية نقاط انطلاق
    إعدادية للتقييم والمعايرة (2-e وما بعدها) — **ليست توصيات تداول**.
    """

    #: هامش حول مستوى بنيوي عند التعريف والإبطال (§18.5: «below sweep low
    #: + volatility buffer» و§23.4: stop = structural invalidation + volatility buffer).
    STRUCTURAL_LEVEL_BUFFER = "STRUCTURAL_LEVEL_BUFFER"
    #: الحد الأدنى للإزاحة المُعتبَرة كسر BOS/إزاحة حقيقية (§11.2/§11.4:
    #: «configurable minimum displacement threshold»).
    DISPLACEMENT_MIN = "DISPLACEMENT_MIN"
    #: تسامح الاختراق وراء منطقة السيولة قبل عدّ الاجتياح sweep (§10.4:
    #: «excursion reaches a threshold relative to local volatility»).
    SWEEP_TOLERANCE = "SWEEP_TOLERANCE"
    #: تسامح خرق الفتيل المعزول دون إغلاق (§11.2: «not merely an isolated wick»).
    WICK_BREAK_TOLERANCE = "WICK_BREAK_TOLERANCE"
    #: مسافة الصلة: أقرب ما تظل فيه المنطقة ذات صلة بالسعر (§10.3: قوة
    #: المنطقة تعتمد «distance to current price»).
    ZONE_PROXIMITY = "ZONE_PROXIMITY"
    #: نصف عرض منطقة الدخول حول سعر التفعيل (§18.1/§24.1: entry_zone).
    ENTRY_ZONE_HALF_WIDTH = "ENTRY_ZONE_HALF_WIDTH"
    #: نصف عرض منطقة الهدف (§10.5/§24.1: الأهداف مناطق لا نقاط).
    TARGET_ZONE_HALF_WIDTH = "TARGET_ZONE_HALF_WIDTH"


#: المعاملات الافتراضية — نقطة انطلاق إعدادية معلنة، تُعايَر لاحقًا (ليست توصية).
DEFAULT_MULTIPLIERS: Mapping[ThresholdKey, float] = MappingProxyType(
    {
        ThresholdKey.STRUCTURAL_LEVEL_BUFFER: 0.5,
        ThresholdKey.DISPLACEMENT_MIN: 1.0,
        ThresholdKey.SWEEP_TOLERANCE: 0.25,
        ThresholdKey.WICK_BREAK_TOLERANCE: 0.2,
        ThresholdKey.ZONE_PROXIMITY: 2.0,
        ThresholdKey.ENTRY_ZONE_HALF_WIDTH: 0.25,
        ThresholdKey.TARGET_ZONE_HALF_WIDTH: 0.25,
    }
)


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class VolatilityConfig:
    """إعداد محرك التقلب — نوافذ السلاسل ومعاملات العتبات.

    الحقول الإضافية الموثقة عن نص المهمة: ``range_window`` (سمة توسع المدى
    تحتاج نافذتها الخاصة). ``multipliers`` تُدمج فوق
    ``DEFAULT_MULTIPLIERS`` (التجاوز يفوز) فتغطي كل مفاتيح
    :class:`ThresholdKey` دائمًا.
    """

    atr_period: int = 14
    pct_window: int = 100
    rv_window: int = 20
    vov_window: int = 50
    range_window: int = 100
    #: آفاق زمن الاحتفاظ المتوقعة (أشرطة) — 60 = ساعة على إطار الدقيقة (D-05).
    holding_horizons: tuple[int, ...] = (60,)
    #: معاملات العتبات — تُدمج فوق الافتراضات؛ كل قيمة محدودة موجبة.
    multipliers: Mapping[ThresholdKey, float] = DEFAULT_MULTIPLIERS

    def __post_init__(self) -> None:
        if self.atr_period < 1:
            raise ValueError(f"atr_period يجب أن يكون ≥ 1؛ وُجد {self.atr_period}")
        if self.pct_window < 2:
            raise ValueError(f"pct_window يجب أن يكون ≥ 2؛ وُجد {self.pct_window}")
        if self.rv_window < 2:
            raise ValueError(f"rv_window يجب أن يكون ≥ 2؛ وُجد {self.rv_window}")
        if self.vov_window < 2:
            raise ValueError(f"vov_window يجب أن يكون ≥ 2؛ وُجد {self.vov_window}")
        if self.range_window < 2:
            raise ValueError(f"range_window يجب أن يكون ≥ 2؛ وُجد {self.range_window}")
        for horizon in self.holding_horizons:
            if horizon < 1:
                raise ValueError(
                    f"كل أفق احتفاظ يجب أن يكون ≥ 1؛ وُجد {horizon} ضمن {self.holding_horizons}"
                )
        merged: dict[ThresholdKey, float] = {
            **DEFAULT_MULTIPLIERS,
            **dict(self.multipliers),
        }
        for key, value in merged.items():
            if not isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"معامل عتبة غير صالح لـ{key}: {value!r} — يجب أن يكون عددًا محدودًا موجبًا"
                )
        # تجميد نهائي: الافتراضيات معدلة بالدمج والخريطة محفوظة والآفاق صف محفوظ.
        object.__setattr__(self, "multipliers", MappingProxyType(merged))
        object.__setattr__(self, "holding_horizons", tuple(self.holding_horizons))

    @property
    def warmup_bars(self) -> int:
        """عدد الشموع اللازمة لاكتمال أعمق دافئ (دلالة الإتاحة) — صفر يقظته data_sufficient.

        الاشتقاق الموثق لكل سلسلة (فهرس أول قيمة غير nan):

        - ``atr``: ``atr_period`` شمعة.
        - ``atr_pct``: ``max(pct_window, atr_period + 1)`` — المئيني يستبعد
          دافئ ATR داخل نافذته (عقد rolling_percentile).
        - ``realized_vol`` وكل أفق ``expected_holding_vol``:
          ``max(rv_window, 3)`` — أول عائد nan يستهلك عضوًا واحدًا،
          وddof=1 يستهلك آخرًا.
        - ``range_expansion``: ``range_window``.
        - ``vol_of_vol``: ``max(vov_window, rv_start + 2)`` حيث
          ``rv_start = max(rv_window − 1, 2)`` فهرس أول قيمة تقلب محقق.
        - ``gap_shock``: ``max(atr_period, 2)``.
        - ``spread_to_range``: شمعة واحدة.
        """
        rv_start = max(self.rv_window - 1, 2)
        return max(
            self.atr_period,
            max(self.pct_window, self.atr_period + 1),
            rv_start + 1,
            self.range_window,
            max(self.vov_window, rv_start + 2),
            max(self.atr_period, 2),
        )

    @property
    def history_bars(self) -> int:
        """طول المخزن الدائري — يكفي بذرة أعمق سلسلة ونوافذها كاملة الأعضاء.

        ``max(warmup_bars, atr_period + pct_window, rv_start + vov_window + 1)``
        حيث ``rv_start = max(rv_window − 1, 2)``: البذرة الأولى تضمن أن نافذة
        مئيني ATR مكتملة الأعضاء المحدودة عند آخر عنصر، وأن نافذة vov كذلك.
        """
        rv_start = max(self.rv_window - 1, 2)
        return max(
            self.warmup_bars,
            self.atr_period + self.pct_window,
            rv_start + self.vov_window + 1,
        )


# ═════════════════════════════ الحالة ═════════════════════════════


@dataclass(frozen=True)
class VolatilityState:
    """لقطة حالة التقلب عند شمعة مغلقة — خرج المحرك (§16).

    القيم ``None`` قبل اكتمال دافئ السلسلة المعنية أو عند انحلالها (انظر
    عقود الموديول). ``atr_percentile`` ∈ [0, 1].
    """

    atr: float | None
    atr_percentile: float | None
    realized_vol: float | None
    range_expansion_percentile: float | None
    vol_of_vol: float | None
    gap_shock: float | None
    spread_to_range: float | None
    #: تقلب الاحتفاظ المتوقع عند أفق 60 شمعة (= ساعة على إطار الدقة D-05) —
    #: ``None`` إذا لم يُعد الأفق 60 ضمن ``holding_horizons`` أو قبل دافئه.
    expected_holding_vol_1h: float | None
    #: كل الآفاق المعدة: أفق → تقلب متوقع (أو None) — امتداد موثق يخدم
    #: المخاطرة (§23) والاستئصال؛ ``expected_holding_vol_1h`` هو ``get(60)``.
    expected_holding_vol: Mapping[int, float | None] = field(
        default_factory=lambda: MappingProxyType({})
    )
    data_sufficient: bool = False
    bar_time: datetime | None = None
    warmup_bars_remaining: int = 0
    #: لقطة معاملات العتبات وقت إنتاج الحالة — تجعل ``threshold`` مكتفية
    #: ذاتيًا بلا وصول للإعداد (الحالة تُنقل وتُؤرشف مستقلة).
    multipliers: Mapping[ThresholdKey, float] = DEFAULT_MULTIPLIERS

    def threshold(
        self,
        multiplier_key: ThresholdKey,
        overrides: Mapping[ThresholdKey, float] | None = None,
    ) -> float | None:
        """العتبة التطبيعية: ``atr × multiplier`` — **لا عتبة سعرية مطلقة إطلاقًا**.

        إلزام بوابة §16: كل مسافة سعرية في المحركات اللاحقة (بنية/سيولة/
        سيناريوهات/تنفيذ) تُستمد من هنا بصيغة
        ``threshold = local_volatility × multiplier`` — لا مسار آخر.

        - ``atr`` غير متوفرة (قبل الدافئ) ⇒ ``None`` — لا قيمة افتراضية مزيفة.
        - المعامل: ``overrides[key]`` إن وُجد (يفوز)، وإلا ``multipliers[key]``
          من لقطة الإعداد. القيم المجتازة يجب أن تكون محدودة موجبة وإلا
          ValueError (يُتحقق منها قبل فحص ATR — العقد صاخب دائمًا).
        - الخطية صرفة: مضاعفة ATR تضاعف العتبة بالضبط (لا حد أدنى مطلق
          ولا ثابت يضاف) — مثبتة اختباريًا بالتحجيم السعري.

        :raises ValueError: مفتاح غير معروف، أو قيمة تجاوز غير محدودة/غير موجبة.
        """
        if overrides is not None:
            for key, value in overrides.items():
                if not isfinite(value) or value <= 0.0:
                    raise ValueError(
                        f"معامل تجاوز غير صالح لـ{key}: {value!r} — يجب أن يكون عددًا محدودًا موجبًا"
                    )
        try:
            multiplier = self.multipliers[multiplier_key]
        except KeyError:
            raise ValueError(
                f"مفتاح عتبة غير معروف: {multiplier_key!r} — المفاتيح الموثقة: "
                f"{[key.value for key in ThresholdKey]}"
            ) from None
        if overrides is not None and multiplier_key in overrides:
            multiplier = overrides[multiplier_key]
        if self.atr is None:
            return None
        return self.atr * multiplier


# ═════════════════════════════ المحرك ═════════════════════════════


@dataclass(frozen=True)
class VolatilityEngineStats:
    """إحصاءات الاستهلاك — جزء من الخرج لا زينة: لا إسقاط صامت للمتأخرين."""

    bars_consumed: int = 0
    late_ignored: int = 0


def _last_or_none(values: FeatureSeries) -> float | None:
    """آخر عنصر محدود أو None — الحالة وعدُ قيم محدودة أو غياب معلن."""
    if values.shape[0] == 0:
        return None
    value = float(values[-1])
    return value if isfinite(value) else None


class VolatilityEngine:
    """محرك التقلب الموضعي لكل (instrument_id, timeframe) — شمع مغلقة فقط.

    الاستخدام: أنشئ محركًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)،
    وغذّه الشموع المغلقة بترتيب الوصول؛ كل ``update`` يعيد الحالة عند آخر
    شمعة مقبولة (انظر عقود الموديول كاملة).

    :raises ValueError: شمعة متطورة، أو خلط أداة/إطار، أو تكرار bar_time
        لشمعة محتجزة — كلها أخطاء قانونية صاخبة.
    """

    def __init__(
        self,
        config: VolatilityConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else VolatilityConfig()
        self._identity: tuple[str, str] | None = (
            (instrument_id, timeframe)
            if instrument_id is not None and timeframe is not None
            else None
        )
        self._buffer: deque[Candle] = deque(maxlen=self._config.history_bars)
        self._seen: set[datetime] = set()
        self._last_bar_time: datetime | None = None
        self._bars_consumed = 0
        self._late_ignored = 0
        self._state: VolatilityState | None = None

    # ── الخصائص ──

    @property
    def config(self) -> VolatilityConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._identity[0] if self._identity is not None else None

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._identity[1] if self._identity is not None else None

    @property
    def state(self) -> VolatilityState | None:
        """آخر حالة منتجة — None قبل ثاني شمعة مقبولة."""
        return self._state

    @property
    def stats(self) -> VolatilityEngineStats:
        """إحصاءات الاستهلاك: المقبولة والمتأخرة المتجاهَلة المحصاة."""
        return VolatilityEngineStats(
            bars_consumed=self._bars_consumed, late_ignored=self._late_ignored
        )

    # ── التغذية ──

    def update(self, candle: Candle) -> VolatilityState | None:
        """استهلاك شمعة مغلقة وإرجاع الحالة — انظر عقود الموديول حرفيًا.

        - أول شمعة على الإطلاق ⇒ ``None`` (لا حالة من شمعة واحدة).
        - متأخرة (أقدم من آخر مغلقة) ⇒ تُتجاهل وتُحصى وتُعاد الحالة الحالية
          دون أي إعادة حساب.
        - مقبولة ⇒ إعادة حساب على المخزن المنزلق وإرجاع الحالة الجديدة.
        """
        if not candle.is_closed:
            raise ValueError(
                "المحرك يستهلك الشموع المغلقة فقط (§27/§33.2) — "
                "فصل المتطور عن المؤكد مسؤولية الابتلاع عبر is_closed"
            )
        self._ensure_identity(candle)
        if self._last_bar_time is None:
            self._accept(candle)
            return None
        if candle.bar_time in self._seen:
            raise ValueError(
                f"تكرار bar_time لشمعة مغلقة سبق استهلاكها: {candle.bar_time} — "
                "التكرار خطأ قانوني عند المغلقات"
            )
        if candle.bar_time < self._last_bar_time:
            self._late_ignored += 1
            return self._state
        self._accept(candle)
        self._state = self._recompute()
        return self._state

    # ── الداخلية ──

    def _ensure_identity(self, candle: Candle) -> None:
        """فرض زوج (أداة، إطار) واحد للمحرك — الالتقاط من أول شمعة أو الرفض."""
        if self._identity is None:
            self._identity = (candle.instrument_id, candle.timeframe)
            return
        expected_instrument, expected_timeframe = self._identity
        if candle.instrument_id != expected_instrument:
            raise ValueError(
                f"خلط أدوات على محرك واحد: استُهل على {expected_instrument!r} "
                f"ووصلت شمعة {candle.instrument_id!r} — أنشئ محركًا لكل (أداة، إطار)"
            )
        if candle.timeframe != expected_timeframe:
            raise ValueError(
                f"خلط أطر على محرك واحد: استُهل على {expected_timeframe!r} "
                f"ووصلت شمعة {candle.timeframe!r} — أنشئ محركًا لكل (أداة، إطار)"
            )

    def _accept(self, candle: Candle) -> None:
        """إلحاق بالمخزن الدائري مع مزامنة طوابع الرؤية المقصوصة."""
        maxlen = self._buffer.maxlen
        if maxlen is not None and len(self._buffer) == maxlen:
            # العنصر الأيسر سيُقص عند الإلحاق — أزل طابعه من مجموعة الرؤية أولًا.
            self._seen.discard(self._buffer[0].bar_time)
        self._buffer.append(candle)
        self._seen.add(candle.bar_time)
        self._last_bar_time = candle.bar_time
        self._bars_consumed += 1

    def _recompute(self) -> VolatilityState:
        """إعادة الحزمة كاملة على المخزن المنزلق وأخذ آخر عنصر (المسار الوحيد A-02)."""
        cfg = self._config
        window = list(self._buffer)
        ehv: dict[int, float | None] = {
            horizon: _last_or_none(expected_holding_vol_series(window, horizon, cfg.rv_window))
            for horizon in cfg.holding_horizons
        }
        return VolatilityState(
            atr=_last_or_none(atr_series(window, cfg.atr_period)),
            atr_percentile=_last_or_none(atr_pct_series(window, cfg.atr_period, cfg.pct_window)),
            realized_vol=_last_or_none(realized_vol_series(window, cfg.rv_window)),
            range_expansion_percentile=_last_or_none(
                range_expansion_series(window, cfg.range_window)
            ),
            vol_of_vol=_last_or_none(vol_of_vol_series(window, cfg.rv_window, cfg.vov_window)),
            gap_shock=_last_or_none(gap_shock_series(window, cfg.atr_period)),
            spread_to_range=_last_or_none(spread_to_range_series(window)),
            expected_holding_vol_1h=ehv.get(60),
            expected_holding_vol=MappingProxyType(ehv),
            data_sufficient=self._bars_consumed >= cfg.warmup_bars,
            bar_time=self._last_bar_time,
            warmup_bars_remaining=max(0, cfg.warmup_bars - self._bars_consumed),
            multipliers=cfg.multipliers,
        )


# ═════════════════════════ لقطة §32 ═════════════════════════


def compute_market_volatility_summary(state: VolatilityState) -> dict[str, float | None]:
    """تسطيح حالة التقلب لقطة حالة السوق (§32) — الدمج مع الجلسات في 2-f.

    مفاتيح مسطحة بقيم الحالة كما هي (‎atr_percentile ∈ [0, 1] — تحويلها إلى
    نسبة مئوية للعرض مسؤولية طبقة الدمج لا المحرك).
    """
    return {
        "atr": state.atr,
        "atr_percentile": state.atr_percentile,
        "realized_vol": state.realized_vol,
        "range_expansion_percentile": state.range_expansion_percentile,
        "vol_of_vol": state.vol_of_vol,
        "gap_shock": state.gap_shock,
        "spread_to_range": state.spread_to_range,
        "expected_holding_vol_1h": state.expected_holding_vol_1h,
    }
