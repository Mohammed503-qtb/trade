"""بنّاء لقطة حالة السوق (مثال §32) — دمج الحالات الموضعية في رسالة واحدة.

هذه هي «طبقة الدمج» التي يوثّق لها ``compute_market_volatility_summary``
في market_state.volatility: المحركات الموضعية (نظام §9.3 / انحياز HTF §9.2 /
تقلب §16) تُخرج حالاتها النقية، وهنا فقط تُدمج في
``schemas.MarketStateSnapshot`` — النموذج القانوني للمخطط المصدَّر
``MarketStateSnapshot.schema.json``.

العقود الموثقة (تُختبر حرفيًا في tests/unit/test_snapshot.py):

- **الحتمية الصرفة**: نفس المدخلات ⇒ نفس اللقطة بايت-بايت — النموذج مجمّد
  وحقوله السبعة كلها دوالّ نقية للمدخلات (لا ساعة ولا عشوائية ولا حالة).

- **الصمت عن الجودة الكسولة**: عدم كفاية بيانات التقلب **لا يسقط اللقطة** —
  ``volatility_percentile = 0.0`` (سياسة مرحلية موثقة: لقطة ما قبل الدافئ
  قانونية لأن regime/bias بقيمة UNKNOWN قبل الدافئ قيمتا تعداد مقررتان
  أصلًا، والقيمة 0.0 قابلة للتمييز في المراقبة عبر عمود data_quality
  والمحقّق لاحقًا عبر حالة المحرك). جودة البيانات تمر كما أوصلها
  المستدعي دون أي إعادة كتابة هنا.

- **تحويل المقياس** [0,1] ← [0,100]: ``VolatilityState.atr_percentile`` كسرة
  مغلقة [0, 1] (عقد المحرك)، وحقل المخطط ``Percentile`` نسبة مئوية مغلقة
  [0, 100] (مثال §32: ``"volatility_percentile": 62.4``). الضرب في 100
  مسؤولية هذه الطبقة حرفيًا: «تحويلها إلى نسبة مئوية للعرض مسؤولية طبقة
  الدمج لا المحرك» (توثيق compute_market_volatility_summary).

- **عقد الجلسة**: ``session_id`` لا يدخل حقول النموذج — المخطط المصدَّر
  يحصر الحقول السبعة بـ``additionalProperties: false``. دوره عقدي صرف:
  يوثّق سياق الجلسة عند المستدعي (من SessionTracker) ويُتحقق من صيغته هنا
  فورًا (يوم ISO ‏≤ 20 حرفًا — عمود القاعدة VARCHAR(20))؛ والقيمة المخزنة
  في الجدول تُشتق حتميًا من ``event_time`` عند التخزين (متسقة مع
  ``Candle.session_id`` = تاريخ الشمعة UTC بصيغة ISO).

- **عقد الوقت**: ``event_time`` واعٍ إلزاميًا (عقد §7.1 عبر ``UTCDatetime``
  في النموذج) — الساذج يُرفض ويطبع الواعي إلى UTC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from schemas import DataQuality, MarketStateSnapshot

from market_state.htf_bias import HtfBiasState
from market_state.regime import RegimeState
from market_state.volatility import VolatilityState

__all__ = [
    "SnapshotInputs",
    "build_snapshot",
    "snapshot_session_id",
]

#: صيغة يوم ISO الصالحة لمعرف الجلسة — ``YYYY-MM-DD`` حصرًا (10 حروف ≤ 20 عمود القاعدة)
_SESSION_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class SnapshotInputs:
    """مدخلات بناء اللقطة — الحالات الموضعية الثلاث عند شمعة مغلقة واحدة.

    كل حقل يأتي من محركه الموضعي (لا حساب سمات هنا إطلاقًا — فصل المسؤولية
    نفسه الذي تتبعه مصنفات §9): ``regime_state`` من RegimeClassifier و
    ``bias_state`` من HtfBiasEngine و``volatility_state`` من VolatilityEngine
    عند نفس الشمعة، و``data_quality`` من مقيّم جودة الابتلاع.
    """

    instrument: str
    timeframe: str
    event_time: datetime
    regime_state: RegimeState
    bias_state: HtfBiasState
    volatility_state: VolatilityState
    data_quality: DataQuality = DataQuality.HEALTHY
    #: سياق الجلسة عند المستدعي — لا يدخل النموذج (انظر عقد الجلسة أعلاه)
    session_id: str | None = None


def snapshot_session_id(event_time: datetime, explicit: str | None = None) -> str:
    """معرف جلسة اللقطة — يوم UTC بصيغة ISO، صريح أو مشتق حتميًا.

    - ``explicit`` موجود ⇒ يمر كما هو بعد تحقق الصيغة (``YYYY-MM-DD`` حصرًا،
      ضمن حد عمود القاعدة 20 حرفًا) — القيمة القبيحة تُرفض عند المصدر لا
      عند الكتابة.
    - ``explicit`` غائب ⇒ يوم ``event_time`` بتوقيت UTC — نفس دلالة
      ``Candle.session_id`` (تاريخ الشمعة) فلا انحراف بين مساري الشمعة
      واللقطة.

    :raises ValueError: معرف جلسة صريح لا يطابق صيغة يوم ISO.
    """
    if explicit is not None:
        if len(explicit) > 20 or _SESSION_ID_PATTERN.match(explicit) is None:
            raise ValueError(
                f"معرف جلسة غير صالح (يوم ISO متوقع): {explicit!r} — المشتق من event_time هو البديل"
            )
        return explicit
    return event_time.astimezone(UTC).date().isoformat()


def build_snapshot(inputs: SnapshotInputs) -> MarketStateSnapshot:
    """دمج الحالات الموضعية في لقطة §32 القانونية — نقي وحتمي صرف.

    - الجودة الكسولة تُترك كسولة: بيانات تقلب غير كافية ⇒
      ``volatility_percentile = 0.0`` بلا إسقاط للقطة وبلا مساس بجودة
      المستدعي (انظر عقود الموديول).
    - كسرة المئيني [0,1] من المحرك تُضرب في 100 لمقياس المخطط [0,100].
    - ``session_id`` يُتحقق من صيغته هنا فورًا (فشل مبكر عند المصدر) لكنه
      لا يدخل حقول النموذج — المخطط المصدَّر يحصرها.
    """
    # تحقق صيغة الجلسة عند المصدر — القيمة نفسها لا تدخل النموذج (عقد الجلسة)
    snapshot_session_id(inputs.event_time, inputs.session_id)

    volatility = inputs.volatility_state
    if not volatility.data_sufficient or volatility.atr_percentile is None:
        percentile = 0.0
    else:
        percentile = volatility.atr_percentile * 100.0

    return MarketStateSnapshot(
        instrument=inputs.instrument,
        timeframe=inputs.timeframe,
        event_time=inputs.event_time,
        regime=inputs.regime_state.regime,
        htf_bias=inputs.bias_state.bias,
        volatility_percentile=percentile,
        data_quality=inputs.data_quality,
    )
