"""كاشف المتطرفات (القمم/القيعان) بتأكيد متأخر — §11.1 حرفيًا.

نص §11.1: «A swing is confirmed only after a defined structural
lookback/confirmation rule is satisfied. The rule must not rely on future bars
in live mode beyond the required confirmation delay» — هذا الموديول هو
الترجمة التشغيلية لتلك الجملة: كل متطرف يُعلن **بعد** تأخير التأكيد المعلن
حصرًا، وكل مرشح يُبطَل قبل اكتمال التأخير **لم يوجد أبدًا** (لا رفرفة §27:
المتطرف المؤكد عند اللحظة t غير قابل للتعديل أو السحب).

**قاعدة الاكتشاف الفراكتلية (شرط الدخول)**: شمعة i مرشح قمة إذا
``high[i] > high[i-1]`` (حافة صاعدة؛ وبالمقابل ``low[i] < low[i-1]``
للقاع) — شرط خلفي من شمعتين حصرًا لا يرى المستقبل أصلًا. الشمعة الأولى
من السلسلة لا مرشح لها (لا سابق لها).

**قاعدة التأكيد المتأخر (شرط الخروج)**: المرشح (بسعر p عند الشمعة i)
يؤكَّد عند الشمعة ``t = i + confirm_bars`` إذا كانت قمم شموع النافذة
‎(i, t]‎ كلها ``≤ p`` — والمؤكِّدة هي الشمعة t نفسها فيحمل المتطرف
``confirmation_time = bar_time(t)`` و``bar_time = bar_time(i)`` (العلاقة
القانونية الموثقة في 3-a: الفارق بينهما هو تأخير التأكيد نفسه، موجب
دائمًا).

**قاعدة الإبطال**: أي شمعة j داخل نافذة التأكيد بقمة ``> p`` تُسقط المرشح
— لم يوجد أبدًا — وتصبح الشمعة j نفسها المرشح الجديد فورًا (مبرهَن:
قمة كل شمعة بين i وj ≤ p < قمة j فحافة الدخول متحققة فيها دائمًا).

العقود الموثقة (تُقفل حرفيًا في tests/unit/test_swings.py):

- **لا-نظرة-مستقبلية (§26.3)**: خرج ``update`` عند الشمعة t هو المتطرفات
  التي **تأكدت عند t حصرًا** — قرار الكاشف دالة في الشموع [0..t] فقط
  (خاصية البادئة في tests/property/test_structure_properties.py: حالات
  البادئة لا تتغير بتمديد الذيل أبدًا).

- **مرشح واحد معلق لكل قطبية**: بين ولادة المرشح وحسمه (تأكيدًا أو
  إبطالًا) تُهمل حواف الدخول الأخرى — لا نوافذ تأكيد متراكبة ولا
  متطرفان بنفس القطبية من نفس النافذة. شمعة الحسم نفسها قد تبدأ ترشيحًا
  جديدًا (قرارها من [n-1, n] حصرًا) — استمرارية السلسلة بلا فجوة.

- **قمة/قاع بشمعة واحدة كحد أقصى لكل تحديث، واثنان عند تزامن القطبيتين**:
  القائمة المرجعة تضم المتطرف المؤكد إن وجد، بترتيب حتمي موثق
  (HIGH ثم LOW) عند تزامن تأكيديهما في الشمعة نفسها.

- **الحتمية الصرفة**: نفس سلسلة الشموع والحالات ⇒ نفس المتطرفات
  بالتطابق التام (بما فيها ``swing_id``).

- **العتبات التطبيعية (§16)**: القوة تطبيع بـATR وحده (أسفل) — لا ثابت
  سعري مطلق في أي مسار.

- **الصخب في التحقق**: شمعة متطورة، خلط أداة/إطار، تكرار أو تأخر
  ``bar_time``، وحالة تقلب من المستقبل — كلها ``ValueError`` صاخب
  (عقود :mod:`structure._guards`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from uuid import UUID as _UUID

from market_state.volatility import VolatilityState
from schemas import Candle, Swing, SwingDirection, SwingScope

from ._guards import StreamGuards

__all__ = ["SwingConfig", "SwingDetector"]


#: مساحة اسم معرف المتطرف — نمط ترميز ingestion/market_store نفسه
#: (uuid5 فوق NAMESPACE_URL بمفتاح نطاق معلن): تحديد لا عشوائية — نفس
#: المفتاح ⇒ نفس المعرف دائمًا عبر الجلسات والإعادات (روح D-07).
_SWING_NAMESPACE: _UUID = uuid5(NAMESPACE_URL, "ai-market-reasoning-engine/structure/swing")


# ═════════════════════════════ الإعداد ═════════════════════════════


@dataclass(frozen=True)
class SwingConfig:
    """إعداد كاشف المتطرفات — نقاط انطلاق إعدادية للتقييم والمعايرة
    (ليست توصيات تداول).

    ``confirm_bars`` هو «defined structural lookback/confirmation rule»
    (§11.1): عدد الشموع اللاحقة الخالية من قمة أعلى (أو قاع أدنى) قبل
    إعلان المتطرف.
    """

    #: عدد شموع التأكيد بعد شمعة المتطرف قبل الإعلان (تأخير التأكيد).
    confirm_bars: int = 3

    def __post_init__(self) -> None:
        if self.confirm_bars < 1:
            raise ValueError(f"confirm_bars يجب أن يكون ≥ 1؛ وُجد {self.confirm_bars}")


# ═════════════════════════════ الداخلية ═════════════════════════════


@dataclass
class _Candidate:
    """مرشح متطرف معلق — كائن داخلي يجري (عدّاد التأكيد و«الوصيف» يتحدثان).

    ``runner_up``: أقصى قمة (أو أدنى قاع) شوهدت داخل نافذة التأكيد المنقضية
    — «الوصيف» الذي تقاس عليه بروز المتطرف عند التأكيد.
    """

    bar_time: datetime
    price: float
    runner_up: float
    confirm_count: int = 0


# ═════════════════════════════ الكاشف ═════════════════════════════


class SwingDetector:
    """كاشف المتطرفات الموضعي لكل (أداة، إطار) — شمع مغلقة فقط (§11.1).

    الاستخدام: أنشئ كاشفًا لكل زوج (أو اتركه يلتقط الهوية من أول شمعة)
    وغذّه كل شمعة مغلقة مع حالة التقلب عند الشمعة نفسها (المستدعي يشغّل
    ``VolatilityEngine`` بالتوازي — نمط verify_phase2). ``vol = None`` يعني
    «لا حالة تقلب بعد» (أول شمعة) فتخرج القوة 0.0 المعلنة لا قيمة مزيفة.
    انظر عقود الموديول كاملة.
    """

    def __init__(
        self,
        config: SwingConfig | None = None,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> None:
        self._config = config if config is not None else SwingConfig()
        self._guards = StreamGuards(instrument_id=instrument_id, timeframe=timeframe)
        self._pending_high: _Candidate | None = None
        self._pending_low: _Candidate | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._swings: list[Swing] = []
        self._external_high_price: float | None = None
        self._external_low_price: float | None = None
        self._external_high_swing: Swing | None = None
        self._external_low_swing: Swing | None = None

    # ── الخصائص ──

    @property
    def config(self) -> SwingConfig:
        """الإعداد (مجمد) — للقراءة والتوثيق."""
        return self._config

    @property
    def instrument_id(self) -> str | None:
        """هوية الأداة — تُلتقط من أول شمعة إن لم تُمرر في البناء."""
        return self._guards.instrument_id

    @property
    def timeframe(self) -> str | None:
        """الإطار الزمني — يُلتقط من أول شمعة إن لم يُمرر في البناء."""
        return self._guards.timeframe

    @property
    def swings(self) -> tuple[Swing, ...]:
        """المتطرفات المؤكدة بترتيب التأكيد — سجل تراكمي غير قابل للرجوع."""
        return tuple(self._swings)

    @property
    def last_external_high(self) -> Swing | None:
        """آخر متطرف قمة خارجي — سقف الإطار الخارجي الجاري (لتغذية 3-c/3-e)."""
        return self._external_high_swing

    @property
    def last_external_low(self) -> Swing | None:
        """آخر متطرف قاع خارجي — أرضية الإطار الخارجي الجاري (لتغذية 3-c/3-e)."""
        return self._external_low_swing

    # ── التغذية ──

    def update(self, candle: Candle, vol: VolatilityState | None) -> list[Swing]:
        """استهلاك شمعة مغلقة — يعيد المتطرفات **المؤكدة عند هذه الشمعة**.

        - القائمة فارغة غالبًا؛ عنصر واحد عند تأكيد قطبية؛ وعنصران (HIGH ثم
          LOW — ترتيب حتمي) عند تزامن تأكيدي القطبيتين في الشمعة نفسها.
        - المتطرف المُبطَل داخل نافذة التأكيد لا يظهر هنا أبدًا («لم يوجد»).
        - ``vol`` يُقرأ لأجل ATR لحظة التأكيد حصرًا (حساب القوة)؛ ``None``
          أو ``atr=None`` (دافئ) ⇒ قوة 0.0 معلنة لا مزيفة.
        """
        self._guards.check_candle(candle)
        self._guards.check_vol(candle, vol)
        confirmed_high = self._process_polarity(candle, vol, SwingDirection.HIGH)
        confirmed_low = self._process_polarity(candle, vol, SwingDirection.LOW)
        return [swing for swing in (confirmed_high, confirmed_low) if swing is not None]

    # ── الداخلية ──

    def _process_polarity(
        self, candle: Candle, vol: VolatilityState | None, direction: SwingDirection
    ) -> Swing | None:
        """آلة حالة قطبية واحدة: ترشيح ← تأكيد/إبطال ← ترشيح جديد.

        القرارات عند الشمعة n من [n-1, n] حصرًا (لا-نظرة-مستقبلية بالبناء).
        """
        is_high = direction is SwingDirection.HIGH
        extreme = candle.high if is_high else candle.low
        prev_extreme = self._prev_high if is_high else self._prev_low
        pending = self._pending_high if is_high else self._pending_low

        confirmed: Swing | None = None
        if pending is None:
            if prev_extreme is not None and self._is_entry_edge(is_high, extreme, prev_extreme):
                # شرط الدخول الفراكتلي: حافة صاعدة (أو هابطة) مقابل الشمعة السابقة.
                candidate = _Candidate(
                    bar_time=candle.bar_time, price=extreme, runner_up=self._seed_runner_up(is_high)
                )
                self._set_pending(is_high, candidate)
        elif self._violates(is_high, extreme, pending.price):
            # إبطال: المرشح «لم يوجد أبدًا»؛ والمُبطِل مرشح جديد فورًا
            # (حافة دخوله متحققة بالبرهان الموثق في ترويسة الموديول).
            self._set_pending(
                is_high,
                _Candidate(
                    bar_time=candle.bar_time, price=extreme, runner_up=self._seed_runner_up(is_high)
                ),
            )
        else:
            pending.confirm_count += 1
            pending.runner_up = self._worse_runner_up(is_high, pending.runner_up, extreme)
            if pending.confirm_count >= self._config.confirm_bars:
                # تأكيد عند هذه الشمعة: البث بعد إقفالها حصرًا (§26.3/§27).
                confirmed = self._confirm(candle, vol, direction, pending)
                self._set_pending(is_high, None)
                # شمعة الحسم قد تبدأ ترشيحًا جديدًا في الخطوة نفسها —
                # القرار من [n-1, n] حصرًا (استمرارية بلا فجوة ولا نظرة خلف).
                if prev_extreme is not None and self._is_entry_edge(is_high, extreme, prev_extreme):
                    self._set_pending(
                        is_high,
                        _Candidate(
                            bar_time=candle.bar_time,
                            price=extreme,
                            runner_up=self._seed_runner_up(is_high),
                        ),
                    )
        if is_high:
            self._prev_high = extreme
        else:
            self._prev_low = extreme
        return confirmed

    def _confirm(
        self,
        candle: Candle,
        vol: VolatilityState | None,
        direction: SwingDirection,
        pending: _Candidate,
    ) -> Swing:
        """بناء المتطرف المؤكد: التصنيف الخارجي/الداخلي ثم القوة ثم المعرف."""
        is_high = direction is SwingDirection.HIGH
        # ── الإطار الخارجي الجاري (§11.2 «classify as internal or external»):
        # القمة تُوسِّع الإطار إذا تجاوزت قطعيًا آخر قمة خارجية (المساواة
        # لا توسّع — قمة مساوية بنية داخلية)؛ أول متطرف قطبية يؤسس الإطار.
        anchor = self._external_high_price if is_high else self._external_low_price
        if anchor is None or (pending.price > anchor if is_high else pending.price < anchor):
            scope = SwingScope.EXTERNAL
        else:
            scope = SwingScope.INTERNAL
        swing = Swing(
            swing_id=self._swing_id(direction, pending),
            price=pending.price,
            timeframe=self._required_timeframe(),
            direction=direction,
            strength=self._strength(vol, is_high, pending),
            confirmation_time=candle.bar_time,
            external_or_internal=scope,
            bar_time=pending.bar_time,
        )
        if scope is SwingScope.EXTERNAL:
            if is_high:
                self._external_high_price = pending.price
                self._external_high_swing = swing
            else:
                self._external_low_price = pending.price
                self._external_low_swing = swing
        self._swings.append(swing)
        return swing

    def _strength(self, vol: VolatilityState | None, is_high: bool, pending: _Candidate) -> float:
        """قوة البروز مطبَّعة بـATR ∈ [0, 1] — ``tanh(excess / atr)``.

        ``excess`` = بُعد المتطرف عن «الوصيف»: أقصى قمة (أدنى قاع) داخل
        نافذة التأكيد المنقضية ‎(i, t]‎ — المتطرف الذي لا يعلو وصيفه قط
        (تساوٍ تام) قوته صفر.

        - ``atr`` غائب (``vol=None`` أو دافئ) ⇒ **0.0 معلنة** — قبل الدافئ
          قوة صفرية صريحة لا قيمة مزيفة (عقد الحالة في market_state).
        - ``atr ≤ 0`` مع بروز موجب ⇒ **1.0** (تشبّع: المتطرف يعلو خلفية
          مسطحة تمامًا — أقصى بروز معرَّف).
        - غير ذلك: ``tanh(excess / atr)`` — رتيبة تصاعديًا في البروز وسالبة
          الأسّ في ATR (خيار tanh الأملس بدل عتبة is_saturated المنطقية).
        """
        excess = pending.price - pending.runner_up if is_high else pending.runner_up - pending.price
        atr = vol.atr if vol is not None else None
        if atr is None or excess <= 0.0:
            return 0.0
        if atr <= 0.0:
            return 1.0
        return math.tanh(excess / atr)

    def _swing_id(self, direction: SwingDirection, pending: _Candidate) -> str:
        """معرف حتمي قابل للإعادة — ``uuid5`` بمفتاح مركب موثق الصيغة.

        الصيغة الحرفية للمفتاح:
        ``f"{instrument_id}|{timeframe}|{bar_time.isoformat()}|{direction.value}"``
        حيث ``bar_time`` طابع **شمعة القمة/القاع نفسها** — هوية الكاشف
        تضمن تفرد المفتاح (مرشح معلق واحد لكل قطبية وشمع فريدة الطابع).
        """
        identity = self._guards.instrument_id, self._guards.timeframe
        key = f"{identity[0]}|{identity[1]}|{pending.bar_time.isoformat()}|{direction.value}"
        return str(uuid5(_SWING_NAMESPACE, key))

    def _required_timeframe(self) -> str:
        """إطار الكاشف عند البناء — التأكيد لا يحدث إلا بعد أول شمعة."""
        timeframe = self._guards.timeframe
        assert timeframe is not None  # لا تأكيد بلا شموع أصلًا (عقود الترتيب)
        return timeframe

    @staticmethod
    def _is_entry_edge(is_high: bool, extreme: float, prev_extreme: float) -> bool:
        """شرط الدخول الفراكتلي: قمة أعلى من سابقتها / قاع أدنى من سابقه."""
        return extreme > prev_extreme if is_high else extreme < prev_extreme

    @staticmethod
    def _violates(is_high: bool, extreme: float, candidate_price: float) -> bool:
        """شرط الإبطال: قمة **أعلى قطعيًا** (المساواة لا تُبطل — ليست «قمة أعلى»)."""
        return extreme > candidate_price if is_high else extreme < candidate_price

    @staticmethod
    def _seed_runner_up(is_high: bool) -> float:
        """بذرة الوصيف: سالب ما لا نهاية للقمة / موجب ما لا نهاية للقاع."""
        return math.inf if not is_high else -math.inf

    @staticmethod
    def _worse_runner_up(is_high: bool, current: float, extreme: float) -> float:
        """تحديث الوصيف: الأقصى للقمة / الأدنى للقاع داخل نافذة التأكيد."""
        return max(current, extreme) if is_high else min(current, extreme)

    def _set_pending(self, is_high: bool, candidate: _Candidate | None) -> None:
        """كتابة المرشح المعلق للقطبية المعنية (مسار وحيد للحالة)."""
        if is_high:
            self._pending_high = candidate
        else:
            self._pending_low = candidate
