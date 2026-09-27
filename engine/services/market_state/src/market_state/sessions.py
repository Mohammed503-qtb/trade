"""وحدة الجلسات وبنية الفتح (§9.4/§9.5 + قرار A-03) — حالة موضعية صرفة بلا نظرة مستقبلية.

الذهنية الحاكمة (قرار A-03 في plan_review): السوق يعمل 24/7 (Binance USDⓈ-M —
قرار D-02)، فالجلسة ليست ساعات بورصة تفتح وتغلق؛ هي **حدود يوم UTC** (00:00→24:00)
كهوية أولية، والنوافذ السلوكية (آسيا/أوروبا/أمريكا) كائنات إعدادية اختيارية
بطوابع UTC صرفة، إضافة إلى نوافذ صيانة المنصة. «الجلسة بيانات سياقية لا إشارة
اتجاه بذاتها» (§9.4) — لا خرج اتجاهيًا من هذه الوحدة إطلاقًا: تصنيفاتها بنية
وشروط تنفيذ، والقرار الاتجاهي مكان آخر (fusion/scenarios).

العقود الموثقة لهذه الوحدة (تُختبر حرفيًا في tests/unit/test_sessions.py):

- **حالة موضعية بلا نظرة مستقبلية** (نمط §26.3): المتتبع يستهلك الشموع بترتيب
  وصولها، وحالة الشمعة t لا تعتمد إلا على شموع وصلت قبلها — نفس المدخلات حتى
  t تعني نفس المخرجات حتى لو توفرت t+1 (خاصية hypothesis مختبرة).

- **UTC صرف — التوقيت الصيفي لا وجود له**: كل حدود الجلسات والنوافذ على محور
  UTC المطلق؛ الطابع الواعي بمنطقة أخرى يُطبَّع إلى UTC قبل أي حساب، ولا تُستشار
  ساعة محلية ولا جداول DST أبدًا. طابعان صيفي وشتوي بنفس دقائق UTC يعاملان
  معاملة واحدة.

- **لا ثابت سعري مطلق واحد** (بوابة المرحلة 2): كل عتبة إما نسبة إعدادية من
  كيان مقاس ذاتي المرجع (``drive_threshold_ratio`` من المدى الافتتاحي — الافتراضي
  الموثق)، أو قيمة يمررها المستدعي من خارج (ATR لكل استدعاء أو عبر
  ``atr_provider`` — وعندها تُطبَّق النسبة نفسها على الأتر). إن غاب الأتر تمامًا
  عملت الوحدة بوضع خام: قيم مقاسة ذاتية المرجع بتصنيف معلَّق على كيان داخلي،
  موثق في عقود الدوال.

- **دلالة الحواف [بداية، نهاية) حرفيًا**: دقيقة البداية داخل النافذة ودقيقة
  النهاية خارجها (00:00 داخل آسيا؛ 08:00 خارجها؛ 07:00 داخل أوروبا وآسيا معًا
  = تقاطع). النوافذ العابرة لمنتصف الليل مدعومة (بداية > نهاية = التفاف).

- **عقد الإرجاع لـ``update``**: None فقط (1) لأول شمعة يستهلكها المتتبع على
  الإطلاق، أو (2) لشمعة أقدم من الجلسة السابقة المحتفَظ بها (تُحصى في late_bars
  — بلا إسقاط صامت). وما عدا ذلك: حالة الجلسة التي تنتمي إليها الشمعة بعد
  تطبيقها (الجارية عادةً؛ وللمتأخرة بعد إقفال جلستها: حالة جلستها المقفلة
  نفسها بعد امتصاصها في مجاميعها). انتقال اليوم = إقفال الجلسة السابقة وتثبيت
  prior_* منها لحظة الانتقال — لا تعديل بأثر رجعي أبدًا.

- **البنية المكتملة مجمّدة** (روح §27): المدى الافتتاحي والرصيد الأولي
  والدافعة، متى اكتملت، لا تُلمس من وصول لاحق متأخر؛ الشموع المتأخرة إلى نافذة
  مجمّدة تُحصى في late_bars وتمتصها المجاميع الرسمية للجلسة فقط.

- **كل كائن Candle رصد مستقل**: المتتبع لا يفكّك «متطورة ثم مقفلة» لنفس الدلو —
  إن غُذِّيت النسختان فستُحتسب مرتين؛ سياسة اختيار النسخ المسماة مسؤولية
  المستدعي (موثق، لا مفاعلة ضمنية).

- **الاحتفاظ المحدود**: الجارية + الجلسة السابقة المقفلة وحدهما في الذاكرة
  (الأخيرة هي مصدر سياق prior_* ولا هدف بعده)؛ جلسات أقدم لا حالة لها.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isfinite

from schemas import Candle

__all__ = [
    "AMERICA_WINDOW",
    "ASIA_WINDOW",
    "DEFAULT_SESSION_WINDOWS",
    "EUROPE_WINDOW",
    "ActiveWindow",
    "OpeningDrive",
    "OpeningStructure",
    "PriorCloseRelation",
    "SessionState",
    "SessionTracker",
    "SessionTrackerStats",
    "SessionWindow",
    "SessionWindowsConfig",
    "is_utc_day_boundary",
    "timeframe_minutes",
    "utc_session_id",
]

# دقائق اليوم UTC — ثابت زمني (لا علاقة له بالأسعار إطلاقًا).
_MINUTES_PER_DAY = 1440
_ONE_DAY = timedelta(days=1)
_TIMEFRAME_RE = re.compile(r"^(\d+)([mhd])$")


# ───────────────────────── دوال مساعدة نقية ─────────────────────────


def _minute_of_day(dt: datetime) -> int:
    """دقيقة اليوم UTC لطابع واعٍ (طباعة إلى UTC) — الساذج مرفوض (عقد §7.1)."""
    if dt.tzinfo is None:
        raise ValueError(
            "naive datetime rejected: session windows are UTC-only (§7.1) — pass tz-aware"
        )
    utc = dt.astimezone(UTC)
    return utc.hour * 60 + utc.minute


def _sign(value: float) -> int:
    """إشارة قيمة: ‎+1/‎−1/0 بمساواة تامة موثقة (عقد gap_direction)."""
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def utc_session_id(dt: datetime) -> str:
    """هوية الجلسة = تاريخ يوم UTC بصيغة ISO ``YYYY-MM-DD``.

    متسقة مع ``Candle.session_id`` (نفس قاعدة منشئ الشموع — A-03): هوية الشمعة
    تُشتق من ``bar_time`` وحده (مصدر الحقيقة الموضعي الواحد) فتتفقان بالبناء
    لأي شمعة سليمة.

    Raises:
        ValueError: طابع ساذج (عقد الوقت §7.1).
    """
    if dt.tzinfo is None:
        raise ValueError(
            "naive datetime rejected: session identity is UTC-only (§7.1) — pass tz-aware"
        )
    return dt.astimezone(UTC).date().isoformat()


def is_utc_day_boundary(dt: datetime) -> bool:
    """هل اللحظة حدّ يوم UTC بالضبط (00:00:00.000000 UTC)؟

    الطوابع بمناطق أخرى تُطبَّن أولًا: 02:00+02:00 حد يوم (00:00 UTC)؛ وحدّ
    الساعة المحلية ليس حدّ يوم UTC إلا إذا طابق منتصف الليل الفعلي.
    """
    if dt.tzinfo is None:
        raise ValueError(
            "naive datetime rejected: day boundaries are UTC-only (§7.1) — pass tz-aware"
        )
    utc = dt.astimezone(UTC)
    return utc.hour == 0 and utc.minute == 0 and utc.second == 0 and utc.microsecond == 0


def timeframe_minutes(timeframe: str) -> float:
    """طول الإطار بالدقائق من صيغة ``<n><m|h|d>`` (مثل ``1m``/``4h``/``1d``).

    الصيغ خارج النمط (مثل ``1t`` للصفقات المفردة) تعيد 0.0 — سياسة موثقة لا
    استثناء: العدادات الدقائقية (maintenance_minutes) لا تعطلها أطر غير
    دقائقية، وعداد العدّ bars_in_maintenance يظل يحصيها.
    """
    match = _TIMEFRAME_RE.match(timeframe)
    if match is None:
        return 0.0
    count = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return float(count)
    if unit == "h":
        return float(count * 60)
    return float(count * _MINUTES_PER_DAY)


# ───────────────────────── نوافذ الجلسات السلوكية ─────────────────────────


@dataclass(frozen=True)
class SessionWindow:
    """نافذة سلوكية بتوقيت UTC — كائن إعدادي اختياري لا توصية تداول (A-03).

    الحدود بدقائق اليوم UTC: ``start_minute_utc`` ضمن ‎[0, 1439]‎ و
    ``end_minute_utc`` ضمن ‎[0, 1440]‎ حيث 1440 تعني 24:00. العضوية بدلالة
    [بداية، نهاية): دقيقة البداية داخل والدقيقة التي بعدها خارجة. النافذة
    العابرة لمنتصف الليل (بداية > نهاية) تغطي ذيل اليوم ثم رأسه؛ والمتساوية
    (بداية == نهاية) نافذة فارغة موثقة. الدقة دقيقة واحدة — مكونات الثواني
    دون أثر لأن حواف النوافذ دائمًا على حدود دقائق كاملة.
    """

    name: str
    start_minute_utc: int
    end_minute_utc: int
    description: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.start_minute_utc <= 1439:
            raise ValueError(f"start_minute_utc خارج النطاق [0, 1439]: {self.start_minute_utc}")
        if not 0 <= self.end_minute_utc <= 1440:
            raise ValueError(f"end_minute_utc خارج النطاق [0, 1440]: {self.end_minute_utc}")

    def _contains_minute(self, minute: int) -> bool:
        """عضوية بدقائق اليوم UTC — بداية ضمنًا ونهاية خارجًا، مع دعم الالتفاف."""
        if self.start_minute_utc < self.end_minute_utc:
            return self.start_minute_utc <= minute < self.end_minute_utc
        if self.start_minute_utc > self.end_minute_utc:
            return minute >= self.start_minute_utc or minute < self.end_minute_utc
        return False  # بداية == نهاية: نافذة فارغة (موثق أعلاه)

    def contains(self, dt: datetime) -> bool:
        """هل اللحظة داخل النافذة؟ بدلالة [بداية، نهاية) بدقائق اليوم UTC.

        Raises:
            ValueError: طابع ساذج (عقد §7.1).
        """
        return self._contains_minute(_minute_of_day(dt))

    def _transition_risk(self, minute: int, edge_minutes: int) -> bool:
        """خطر انتقال (§9.4): اللحظة داخل النافذة وضمن edge_minutes من إحدى
        حافتيها (قرب الافتتاح أو قرب الإقفال) — قياس دائري يصمد للنوافذ
        العابرة لمنتصف الليل. edge_minutes = 0 يعطّل الخطر كليًا.
        """
        if edge_minutes <= 0 or not self._contains_minute(minute):
            return False
        near_open = (minute - self.start_minute_utc) % _MINUTES_PER_DAY < edge_minutes
        near_close = (self.end_minute_utc - minute) % _MINUTES_PER_DAY < edge_minutes
        return near_open or near_close

    @property
    def duration_minutes(self) -> int:
        """مدة النافذة بالدقائق (بصيغتها الدائرية): (نهاية−بداية) mod 1440 —
        مع تمييز اليوم الكامل (1440) من النافذة الفارغة (0)."""
        if self.start_minute_utc == self.end_minute_utc:
            return 0  # نافذة فارغة (موثق أعلاه)
        duration = (self.end_minute_utc - self.start_minute_utc) % _MINUTES_PER_DAY
        return _MINUTES_PER_DAY if duration == 0 else duration


@dataclass(frozen=True)
class ActiveWindow:
    """نافذة نشطة لحظة معينة + علم خطر الانتقال (§9.4)."""

    window: SessionWindow
    transition_risk: bool


@dataclass(frozen=True)
class SessionWindowsConfig:
    """إعداد النوافذ السلوكية — قيم إعدادية لا توصية تداول (A-03).

    الافتراضي الموثق: آسيا 00:00-08:00، أوروبا 07:00-16:00، أمريكا 13:30-20:00
    (طوابع UTC صرفة لا تتأثر بالتوقيت الصيفي أبدًا)، بلا نوافذ صيانة، وحافة
    خطر الانتقال 5 دقائق. الترتيب في المخرجات حتمي: النوافذ السلوكية بترتيب
    تصريحها ثم نوافذ الصيانة بترتيبها.
    """

    windows: tuple[SessionWindow, ...] = ()
    maintenance: tuple[SessionWindow, ...] = ()
    edge_minutes: int = 5

    def __post_init__(self) -> None:
        if self.edge_minutes < 0:
            raise ValueError(f"edge_minutes سالب: {self.edge_minutes}")

    def active_at(self, dt: datetime) -> tuple[ActiveWindow, ...]:
        """النوافذ النشطة عند لحظة ما (سلوكية + صيانة) بعلم خطر الانتقال.

        Raises:
            ValueError: طابع ساذج (عقد §7.1).
        """
        minute = _minute_of_day(dt)
        return tuple(
            ActiveWindow(
                window=window,
                transition_risk=window._transition_risk(minute, self.edge_minutes),
            )
            for window in (*self.windows, *self.maintenance)
            if window._contains_minute(minute)
        )

    def maintenance_at(self, dt: datetime) -> bool:
        """هل اللحظة داخل نافذة صيانة؟ (تُستخدم لعلم in_maintenance والإحصاءات).

        Raises:
            ValueError: طابع ساذج (عقد §7.1).
        """
        minute = _minute_of_day(dt)
        return any(window._contains_minute(minute) for window in self.maintenance)


# الافتراضيات الموثقة (قيم إعدادية سلوكية — A-03): أسماؤها تطابق قيم
# SessionType في schemas (ASIA/EUROPE/AMERICA/MAINTENANCE) والنوافذ المخصصة
# حرة التسمية.
ASIA_WINDOW = SessionWindow(
    name="ASIA",
    start_minute_utc=0,
    end_minute_utc=480,
    description="نافذة سلوكية إعدادية 00:00-08:00 UTC — ليست توصية تداول",
)
EUROPE_WINDOW = SessionWindow(
    name="EUROPE",
    start_minute_utc=420,
    end_minute_utc=960,
    description="نافذة سلوكية إعدادية 07:00-16:00 UTC — ليست توصية تداول",
)
AMERICA_WINDOW = SessionWindow(
    name="AMERICA",
    start_minute_utc=810,
    end_minute_utc=1200,
    description="نافذة سلوكية إعدادية 13:30-20:00 UTC — ليست توصية تداول",
)

DEFAULT_SESSION_WINDOWS = SessionWindowsConfig(
    windows=(ASIA_WINDOW, EUROPE_WINDOW, AMERICA_WINDOW),
    maintenance=(),
    edge_minutes=5,
)


# ───────────────────────── بنية الفتح (§9.5) ─────────────────────────


class OpeningDrive(StrEnum):
    """تصنيف الدافعة الافتتاحية (§9.5) — بنية سياقية لا إشارة اتجاه بذاتها.

    لا افتراض أن الدافعة تستمر (§9.5 حرفيًا): التصنيف وصفٌ لما وقع فحسب.
    """

    PENDING = "PENDING"  # بانتظار اكتمال المدى الافتتاحي (أولوية: الاكتمال ثم التصنيف)
    UP = "UP"  # إغلاق فوق سقف المدى الافتتاحي بعتبة التصنيف
    DOWN = "DOWN"  # إغلاق تحت قاع المدى الافتتاحي بعتبة التصنيف
    REVERSAL = "REVERSAL"  # بعد دافعة مثبتة: إغلاق عبر الحد المقابل بعتبة التصنيف


class PriorCloseRelation(StrEnum):
    """علاقة السعر الراهن بإغلاق الجلسة السابقة عند عتبة نسبية صفرية موثقة."""

    ABOVE = "ABOVE"
    BELOW = "BELOW"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class OpeningStructure:
    """مخرجات §9.5 عند كل تحديث — كلها مقاييس خام بلا مرجع تقلب خارجي.

    العقود:
    - ``gap_vs_prior_close`` فرق مطلق بنقاط خام (مرساة الفجوة = افتتاح أقدم
      شمعة bar_time شوهِدت في الجلسة؛ غياب إغلاق سابق ⇒ None). التطبيع بـATR
      مسؤولية المتصل/محرك التقلب (§16) — هذه الوحدة لا تعرف الأتر إلا ما
      يمرَّر إليها صراحة لتصنيف الدافعة فقط. ``gap_direction`` إشارته ‎−1/0/‎+1
      بمساواة تامة موثقة.
    - المدى الافتتاحي: نافذة ‎[00:00, opening_range_minutes) بدلالة bar_time
      (عضوية الدلو ببدايته). يكتمل عند أول شمعة لاحقة للجلسة عند الحد أو
      بعده، وبشرط رصد شمعة واحدة على الأقل داخل النافذة — لا شموع داخلها
      أصلًا ⇒ يبقى None/False بصدق (الافتتاح لم يُرصد). متى اكتمل تجمّد (روح
      §27).
    - الرصيد الأولي بنفس العقد ونافذة ‎[00:00, initial_balance_minutes).
    - ``opening_drive``: التصنيف على إغلاقات الشموع بعد اكتمال المدى الافتتاحي
      فقط (أولوية موثقة: مدى مكتمل > انتظار)، بعتبة نقاط =
      ``drive_threshold_ratio`` × المدى الافتتاحي (الافتراضي الموثق — وضع خام
      ذاتي المرجع)، أو × ATR إن مرره المستدعي (لكل استدعاء أو عبر المزود —
      يقدَّم متى وُجد). أول إغلاق مؤهل بحسب الوصول يثبت الدافعة (لازقة)، وما
      بعده لا يرفعها إلا ترقية UP/DOWN → REVERSAL. عتبة 0 (مدى مسطح أو أتر
      معدوم) تجعل التصنيف كسرًا صارمًا لحد المدى.
    - ``prior_close_relationship``: مقارنة آخر إغلاق مرصود بإغلاق الجلسة
      السابقة عند عتبة نسبية صفرية موثقة (المساواة التامة = UNCHANGED)؛ غياب
      الإغلاق السابق ⇒ UNCHANGED بوصفه غياب سياق لا ادعاء مساواة (موثق).
    - **لا افتراض أن الفجوة تُسد أو أن الدافعة تستمر** (§9.5 حرفيًا): هذه
      مقاييس وصفية فحسب، وأي فرضية عن السد أو الاستمرار مكانها سيناريوهات
      المرحلة اللاحقة لا هنا.

    مؤجل صراحة (لا تُخترع حقوله هنا): تشكل السيولة المبكرة (early liquidity
    formation — المرحلة 3 مع محرك السيولة)، واختلال الافتتاح (opening
    imbalance — المرحلة 4 مع الفوتبرنت §12).
    """

    gap_vs_prior_close: float | None
    gap_direction: int
    opening_range_high: float | None
    opening_range_low: float | None
    opening_range_complete: bool
    initial_balance_high: float | None
    initial_balance_low: float | None
    opening_drive: OpeningDrive
    prior_session_high: float | None
    prior_session_low: float | None
    prior_session_close: float | None
    prior_close_relationship: PriorCloseRelation


# ───────────────────────── حالة الجلسة والإحصاءات ─────────────────────────


@dataclass(frozen=True)
class SessionState:
    """لقطة حالة الجلسة عند شمعة معينة — بيانات سياقية لا إشارة اتجاه (§9.4).

    ``session_id`` تاريخ يوم UTC بصيغة ISO (متسق مع Candle.session_id)؛
    ``open_time``/``close_time`` بداية/نهاية يوم UTC ‎[00:00, 24:00)؛
    ``active_windows`` تُحسب عند bar_time الشمعة (أول لحظة يثبتها الدلو)؛
    ``overlap_flags`` أسماء النوافذ السلوكية النشطة عند وجود اثنتين فأكثر
    متقاطعتين لحظيًا (وإلا فارغة) — الصيانة خارجها وعلمها in_maintenance؛
    ``current_high/low`` أقصى/أدنى من بداية الجلسة؛ و``bars_seen`` عدد
    الشموع الممتصة في مجاميعها.
    """

    session_id: str
    open_time: datetime
    close_time: datetime
    active_windows: tuple[ActiveWindow, ...]
    overlap_flags: tuple[str, ...]
    in_maintenance: bool
    opening: OpeningStructure
    current_high: float | None
    current_low: float | None
    session_volume: float
    bars_seen: int


@dataclass(frozen=True)
class SessionTrackerStats:
    """عدادات المتتبع — قراءة فقط، لا حالات ولا اتجاهات."""

    sessions_closed: (
        int  # أحداث إقفال جلسة (عبور يوم UTC جديد — الثقب في البيانات يقفل الماضية مرة)
    )
    bars_processed: int  # كل الشموع المستهلكة عبر update
    late_bars: int  # شموع وصلت بعد تجاوز بنيتها: لجلسة سابقة/أقدم، أو داخل نافذة مجمّدة
    bars_in_maintenance: int  # شموع bar_time داخل نافذة صيانة
    maintenance_minutes: float  # مجموع دقائق أطرها (الأطر غير الدقائقية تعد 0.0 — موثق)


# ───────────────────────── الحالة الداخلية (خاصة بالوحدة) ─────────────────────────


@dataclass(frozen=True)
class _PriorContext:
    """سياق الجلسة السابقة — يثبت لحظة انتقال اليوم ولا يعدل بعدها أبدًا."""

    high: float | None
    low: float | None
    close: float | None


@dataclass
class _SessionAccumulator:
    """مجمّع جلسة واحد (قابل للتغيير — خاص بالوحدة، مخرجاته لقطات مجمدة).

    or_end/ib_end نهايتا نافذتي المدى الافتتاحي والرصيد الأولي (تُحسبان مرة
    عند الإنشاء لأن open_time ثابتة للجلسة). المجمّع المقفل (السابق) يمتص
    المتأخرات في مجاميعه الرسمية فقط — بناه المجمدة لا تُلمس.
    """

    session_id: str
    open_time: datetime
    close_time: datetime
    prior: _PriorContext | None
    or_end: datetime
    ib_end: datetime
    anchor_bar_time: datetime | None = None
    anchor_open: float | None = None
    last_bar_time: datetime | None = None
    last_close: float | None = None
    current_high: float | None = None
    current_low: float | None = None
    session_volume: float = 0.0
    bars_seen: int = 0
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    opening_range_complete: bool = False
    initial_balance_high: float | None = None
    initial_balance_low: float | None = None
    initial_balance_complete: bool = False
    drive: OpeningDrive = OpeningDrive.PENDING


# ───────────────────────── المتتبع ─────────────────────────


class SessionTracker:
    """متتبع الجلسات وبنية الفتح — حالة موضعية صرفة لكل مجرى شموع.

    الاستهلاك: ``update(candle)`` بترتيب الوصول (مغلقة كانت الشمعة أو متطورة —
    كل كائن رصد مستقل، موثق في رأس الوحدة). النوافذ ونشاط الصيانة يُقيَّمان عند
    ``bar_time`` الشمعة. غير محصّن ضد التزامن — يُستهلك من مهمة واحدة ضامنة
    الحتمية (نمط CandleBuilder).

    عتبات البوابة (لا ثوابت سعرية مطلقة): ``opening_range_minutes`` و
    ``initial_balance_minutes`` أطوال نوافذ بالدقائق؛ ``drive_threshold_ratio``
    نسبة تصنيف الدافعة (من المدى الافتتاحي افتراضيًا — الوضع الخام؛ أو من ATR
    إن مُرر عبر ``atr``/``atr_provider`` فيقدَّم مرجعًا)؛ ``edge_minutes`` يرث
    حافة خطر الانتقال من الإعداد (أو يتجاوزها صراحة).

    Raises:
        ValueError: معاملات إعدادية غير صالحة، أو قيمة atr سالبة/غير منتهية —
            قبل أي أثر جانبي.
    """

    def __init__(
        self,
        config: SessionWindowsConfig = DEFAULT_SESSION_WINDOWS,
        *,
        opening_range_minutes: int = 30,
        initial_balance_minutes: int = 60,
        drive_threshold_ratio: float = 0.5,
        edge_minutes: int | None = None,
        atr_provider: Callable[[], float | None] | None = None,
    ) -> None:
        if opening_range_minutes < 1:
            raise ValueError(f"opening_range_minutes < 1: {opening_range_minutes}")
        if initial_balance_minutes < 1:
            raise ValueError(f"initial_balance_minutes < 1: {initial_balance_minutes}")
        if not isfinite(drive_threshold_ratio) or drive_threshold_ratio < 0.0:
            raise ValueError(f"drive_threshold_ratio خارج النطاق [0, ∞): {drive_threshold_ratio}")
        self._config = (
            config if edge_minutes is None else replace(config, edge_minutes=edge_minutes)
        )
        self._opening_range_minutes = opening_range_minutes
        self._initial_balance_minutes = initial_balance_minutes
        self._drive_threshold_ratio = drive_threshold_ratio
        self._atr_provider = atr_provider
        self._current: _SessionAccumulator | None = None
        self._previous: _SessionAccumulator | None = None
        self._current_snapshot: SessionState | None = None
        self._sessions_closed = 0
        self._bars_processed = 0
        self._late_bars = 0
        self._bars_in_maintenance = 0
        self._maintenance_minutes = 0.0

    # ───────── خصائص قراءة ─────────

    @property
    def config(self) -> SessionWindowsConfig:
        """الإعداد الفعلي المستخدم (بعد توريث/تجاوز حافة خطر الانتقال)."""
        return self._config

    @property
    def current_state(self) -> SessionState | None:
        """آخر لقطة للجلسة الجارية (None قبل أول شمعة تنتج لقطة)."""
        return self._current_snapshot

    @property
    def stats(self) -> SessionTrackerStats:
        """عدادات المتتبع — انظر SessionTrackerStats لعقود كل عداد."""
        return SessionTrackerStats(
            sessions_closed=self._sessions_closed,
            bars_processed=self._bars_processed,
            late_bars=self._late_bars,
            bars_in_maintenance=self._bars_in_maintenance,
            maintenance_minutes=self._maintenance_minutes,
        )

    # ───────── عقد الاستهلاك ─────────

    def update(self, candle: Candle, *, atr: float | None = None) -> SessionState | None:
        """إدخال شمعة واحدة وإرجاع أثرها الموضعي.

        عقد الإرجاع (موثق صراحة):
        - ``None`` في حالتين فقط: (1) أول شمعة يستهلكها المتتبع على الإطلاق —
          تُنشأ الجلسة وتُمتص الشمعة لكن لا سياق بعدُ يُعاد؛ (2) شمعة لجلسة أقدم
          من الجلسة السابقة المقفلة المحتفظ بها — حالتها لم تعد موجودة، تُحصى
          في ``late_bars`` (بلا إسقاط صامت) ولا تعاد.
        - ``SessionState`` فيما عدا ذلك: حالة الجلسة التي تنتمي إليها الشمعة بعد
          تطبيقها — الجلسة الجارية عادة؛ وللشمعة المتأخرة لجلسة سابقة: حالة تلك
          الجلسة المقفلة نفسها بعد امتصاص الشمعة في مجاميعها (بنيتها المجمدة
          لا تُلمس — عقد المتأخر أدناه).

        عقد الشمعة المتأخرة (ترتيب وصول معكوس جزئيًا): شمعة لجلسة سابقة تحدّث
        حالة جلستها لا الحالية — لا إسقاط صامت: مجاميعها الرسمية
        (current_high/low وsession_volume وbars_seen) تمتصها، وبنيتها المجمدة
        (المدى الافتتاحي والرصيد الأولي والدافعة ومرساة الفجوة وآخر إغلاق) لا
        تُلمس، وسياق ``prior_*`` للجلسة اللاحقة ثبت لحظة الانتقال فلا يتعدل
        بأثر رجعي أبدًا (اللقطات المعادة سابقًا كائنات مجمدة لا تُرسم من جديد).

        عقد انتقال اليوم: أول شمعة ليوم UTC جديد تقفل الجلسة السابقة
        (``sessions_closed`` يزداد) وتثبت ``prior_*`` من مجاميعها النهائية لحظة
        الانتقال، ثم تبدأ جلسة اليوم الجديد وتعاد حالتها بعد امتصاص الشمعة.

        ATR (اختياري): قيمة لكل استدعاء تُقدَّم على المزود، والمزود على الوضع
        الخام؛ تُستخدم لعتبة تصنيف الدافعة وحدها (عقد OpeningStructure). القيمة
        السالبة/غير المنتهية تُرفض بـValueError قبل أي أثر جانبي.

        Raises:
            ValueError: atr سالبة أو غير منتهية (قبل أي أثر جانبي).
        """
        atr_value = self._resolve_atr(atr)
        self._bars_processed += 1
        if self._config.maintenance_at(candle.bar_time):
            self._bars_in_maintenance += 1
            self._maintenance_minutes += timeframe_minutes(candle.timeframe)

        session_id = utc_session_id(candle.bar_time)
        current = self._current
        if current is None:
            # أول شمعة على الإطلاق: تُبنى الجلسة وتُمتص الشمعة ولا يعاد شيء.
            self._current = self._new_accumulator(session_id, candle.bar_time, prior=None)
            self._apply(self._current, candle, atr_value, frozen=False)
            return None
        if session_id == current.session_id:
            self._apply(current, candle, atr_value, frozen=False)
            return self._publish(current, candle.bar_time)
        if session_id > current.session_id:
            # انتقال يوم UTC جديد: إقفال الجارية وتثبيت سياقها ثم بدء اللاحقة.
            prior = _PriorContext(
                high=current.current_high,
                low=current.current_low,
                close=current.last_close,
            )
            self._sessions_closed += 1
            self._previous = current
            self._current = self._new_accumulator(session_id, candle.bar_time, prior=prior)
            self._apply(self._current, candle, atr_value, frozen=False)
            return self._publish(self._current, candle.bar_time)
        # جلسة سابقة بترتيب الوصول — العقد الموثق أعلاه: تحدّث جلستها لا الحالية.
        self._late_bars += 1
        previous = self._previous
        if previous is not None and session_id == previous.session_id:
            self._apply(previous, candle, atr_value, frozen=True)
            return self._snapshot(previous, at=candle.bar_time)
        # أقدم من السابقة المحتفظ بها: لا حالة لها — عدّ مرئي بلا إسقاط صامت.
        return None

    # ───────── الداخلية ─────────

    def _resolve_atr(self, atr: float | None) -> float | None:
        """حل قيمة الأتر: قيمة الاستدعاء تقدم على المزود، والمزود على الوضع
        الخام — والقيمة غير الصالحة ترفض قبل أي أثر جانبي."""
        value: float | None
        if atr is not None:
            value = atr
        else:
            value = self._atr_provider() if self._atr_provider is not None else None
        if value is None:
            return None
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"atr خارج العقد (غير سالبة ومنتهية): {value}")
        return value

    def _new_accumulator(
        self,
        session_id: str,
        bar_time: datetime,
        *,
        prior: _PriorContext | None,
    ) -> _SessionAccumulator:
        """إنشاء مجمّع جلسة يوم UTC: open_time منتصف الليل وحدود النوافذ منه."""
        midnight = bar_time.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return _SessionAccumulator(
            session_id=session_id,
            open_time=midnight,
            close_time=midnight + _ONE_DAY,
            prior=prior,
            or_end=midnight + timedelta(minutes=self._opening_range_minutes),
            ib_end=midnight + timedelta(minutes=self._initial_balance_minutes),
        )

    def _apply(
        self,
        acc: _SessionAccumulator,
        candle: Candle,
        atr_value: float | None,
        *,
        frozen: bool,
    ) -> None:
        """امتصاص شمعة في مجمّع جلسة.

        المجمّع المقفل (frozen=True — الجلسة السابقة بعد انتقال اليوم): تمتص
        المجاميع الرسمية فقط وبناه المجمدة لا تُلمس (عقد المتأخر في update).
        """
        t = candle.bar_time
        if not frozen:
            if acc.anchor_bar_time is None or t < acc.anchor_bar_time:
                # مرساة الفجوة = افتتاح أقدم bar_time شوهد — تصحح نفسها إن وصل
                # أقدم لاحقًا (اللقطات المعادة سابقًا مجمدة لا تُرسم من جديد).
                acc.anchor_bar_time = t
                acc.anchor_open = candle.open
            if acc.last_bar_time is None or t >= acc.last_bar_time:
                acc.last_bar_time = t
                acc.last_close = candle.close
            self._apply_opening_windows(acc, candle)
            self._evaluate_drive(acc, candle, atr_value)
        acc.current_high = (
            candle.high if acc.current_high is None else max(acc.current_high, candle.high)
        )
        acc.current_low = (
            candle.low if acc.current_low is None else min(acc.current_low, candle.low)
        )
        acc.session_volume += candle.volume
        acc.bars_seen += 1

    def _apply_opening_windows(self, acc: _SessionAccumulator, candle: Candle) -> None:
        """نوافذا المدى الافتتاحي والرصيد الأولي: امتصاص ما دامتا مفتوحتين،
        واكتمال عند أول شمعة عند الحد أو بعده (بشرط رصد شمعة داخل النافذة)،
        وتجميد تام بعده — المتأخر إلى نافذة مجمّدة يُعدّ مرة واحدة."""
        t = candle.bar_time
        missed_frozen_window = False
        if t < acc.or_end:
            if acc.opening_range_complete:
                missed_frozen_window = True
            else:
                acc.opening_range_high = (
                    candle.high
                    if acc.opening_range_high is None
                    else max(acc.opening_range_high, candle.high)
                )
                acc.opening_range_low = (
                    candle.low
                    if acc.opening_range_low is None
                    else min(acc.opening_range_low, candle.low)
                )
        elif not acc.opening_range_complete and acc.opening_range_high is not None:
            acc.opening_range_complete = True
        if t < acc.ib_end:
            if acc.initial_balance_complete:
                missed_frozen_window = True
            else:
                acc.initial_balance_high = (
                    candle.high
                    if acc.initial_balance_high is None
                    else max(acc.initial_balance_high, candle.high)
                )
                acc.initial_balance_low = (
                    candle.low
                    if acc.initial_balance_low is None
                    else min(acc.initial_balance_low, candle.low)
                )
        elif not acc.initial_balance_complete and acc.initial_balance_high is not None:
            acc.initial_balance_complete = True
        if missed_frozen_window:
            self._late_bars += 1

    def _evaluate_drive(
        self,
        acc: _SessionAccumulator,
        candle: Candle,
        atr_value: float | None,
    ) -> None:
        """تصنيف الدافعة على إغلاقات ما بعد نافذة المدى الافتتاحي — أولوية
        موثقة: مدى مكتمل > انتظار؛ أول مؤهل بحسب الوصول يثبت، والترقية إلى
        REVERSAL فقط (لا فك تصنيف ولا تذبذب)."""
        if candle.bar_time < acc.or_end:
            return  # شمعة داخل النافذة لا تصنف دافعة (عقد OpeningStructure)
        if acc.drive is OpeningDrive.REVERSAL or not acc.opening_range_complete:
            return
        if acc.opening_range_high is None or acc.opening_range_low is None:
            return
        # العتبة: نسبة × ATR إن وُجد (يقدم)، وإلا نسبة × المدى الافتتاحي (الافتراضي
        # الموثق — وضع خام ذاتي المرجع). عتبة 0 = كسر صارم لحد المدى.
        threshold = self._drive_threshold_ratio * (
            atr_value if atr_value is not None else (acc.opening_range_high - acc.opening_range_low)
        )
        up_level = acc.opening_range_high + threshold
        down_level = acc.opening_range_low - threshold
        close = candle.close
        if acc.drive is OpeningDrive.PENDING:
            if close > up_level:
                acc.drive = OpeningDrive.UP
            elif close < down_level:
                acc.drive = OpeningDrive.DOWN
        elif acc.drive is OpeningDrive.UP:
            if close < down_level:
                acc.drive = OpeningDrive.REVERSAL
        else:  # DOWN — الترقية المقابلة
            if close > up_level:
                acc.drive = OpeningDrive.REVERSAL

    def _publish(self, acc: _SessionAccumulator, at: datetime) -> SessionState:
        """بناء لقطة الجارية وتثبيتها حاليةً (current_state) ثم إعادتها."""
        snapshot = self._snapshot(acc, at=at)
        self._current_snapshot = snapshot
        return snapshot

    def _snapshot(self, acc: _SessionAccumulator, *, at: datetime) -> SessionState:
        """لقطة مجمّدة لحالة الجلسة عند لحظة الشمعة — دالة صرفة بلا أثر جانبي."""
        active = self._config.active_at(at)
        minute = _minute_of_day(at)
        behavioral = [w for w in self._config.windows if w._contains_minute(minute)]
        overlap = tuple(w.name for w in behavioral) if len(behavioral) >= 2 else ()
        in_maintenance = any(w._contains_minute(minute) for w in self._config.maintenance)

        prior = acc.prior
        prior_close = prior.close if prior is not None else None
        anchor_open = acc.anchor_open
        if prior_close is not None and anchor_open is not None:
            diff = anchor_open - prior_close
            gap: float | None = abs(diff)
            gap_direction = _sign(diff)
        else:
            gap = None
            gap_direction = 0
        if prior_close is not None and acc.last_close is not None:
            if acc.last_close > prior_close:
                relationship = PriorCloseRelation.ABOVE
            elif acc.last_close < prior_close:
                relationship = PriorCloseRelation.BELOW
            else:
                relationship = PriorCloseRelation.UNCHANGED
        else:
            relationship = PriorCloseRelation.UNCHANGED  # غياب سياق موثق لا ادعاء مساواة

        opening = OpeningStructure(
            gap_vs_prior_close=gap,
            gap_direction=gap_direction,
            opening_range_high=acc.opening_range_high,
            opening_range_low=acc.opening_range_low,
            opening_range_complete=acc.opening_range_complete,
            initial_balance_high=acc.initial_balance_high,
            initial_balance_low=acc.initial_balance_low,
            opening_drive=acc.drive,
            prior_session_high=prior.high if prior is not None else None,
            prior_session_low=prior.low if prior is not None else None,
            prior_session_close=prior.close if prior is not None else None,
            prior_close_relationship=relationship,
        )
        return SessionState(
            session_id=acc.session_id,
            open_time=acc.open_time,
            close_time=acc.close_time,
            active_windows=active,
            overlap_flags=overlap,
            in_maintenance=in_maintenance,
            opening=opening,
            current_high=acc.current_high,
            current_low=acc.current_low,
            session_volume=acc.session_volume,
            bars_seen=acc.bars_seen,
        )
