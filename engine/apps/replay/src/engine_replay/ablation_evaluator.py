"""مقيّم الاستئصال الحقيقي — الطاقة التنبؤية بتقسيم زمني (المهمة 5a.3).

الوعد المؤجل في :mod:`engine_replay.ablation` (2-e): ``placeholder_evaluator``
‏STUB موثق يعيد عدد السمات «حتى المرحلة 5a.3» — هذا الموديول يفي به:
مقيّم قابل للحقن في ``MetricEvaluator`` يقيس من البيانات فعلًا لا يختلق
مقاييس أداء وهمية، ويحترم عقد §43 المتاح في هذه المرحلة:

- **عينات خارجية (OOS)**: تقسيم زمني صارم — أول ``train_ratio`` من
  السلسلة تدريب (اختيار عتبات الإشارة) وآخرها تقييم حصرًا؛ العتبات من
  التدريب فقط فلا تسرب معلومي إلى التقييم (لا-نظرة داخل التجربة نفسها).
- **اضطراب معاملات** و**تقسيم أنظمة** و**تكاليف واقعية**: مؤجلة صراحة
  إلى مرحلتي 7/9 (محرك السيناريوهات والإعادة) — موثقة في سجل الترقية
  promotion-like الذي تولده بوابة المرحلة، لا مختلقة هنا.

**مقاييس المقيّم** (لكل مجموعة سمات، على شموع OOS):

- ``oos_signal_count``: عدد إشارات السمات مجتمعة (شمعة تجاوزت سمة فيها
  إحدى عتبتي كوانتيل التدريب) — الإشارة النادرة تحكم القياس كله.
- ``oos_absolute_response_median``: وسيط الاستجابة المطلقة عند الإشارات
  ‎(|close[t+h]−close[t]|/close[t]|) — «هل تسبق السمة حركة قادمة؟»
  بصياغة محايدة اتجاهيًا تصلح لكل السمات (قوة الشمعة ومداها وحجمها
  واختلالها وإغلاقها — سمات غير موجهة أصلًا).
- ``oos_directional_hit_rate_median``: وسيط دقة الاتجاه للسمات **الموجهة**
  حصرًا (خريطة :data:`FEATURE_POLARITY`): إشارة علوية ⇒ close[t+h] أعلى،
  وسفلية ⇒ أدنى؛ يُحذف المفتاح إن خلت المجموعة من سمات موجهة (غياب
  معلن لا قيمة مختلقة).

**القطبية المعلنة** (:data:`FEATURE_POLARITY`) — السمات الست §13.1:

====================  ==========================
السمة                القطبية (علوية ⇒ اتجاه)
====================  ==========================
close_location       موجبة (إغلاق جهوي صاعد)
wick_asymmetry       معكوسة (سالب = ذيل سفلي = صاعد)
gap_relationship     موجبة (فجوة صاعدة)
body_fraction        غير موجهة (قوة جسم بلا جهة)
range_percentile     غير موجهة (توسع مدى)
volume_relationship  غير موجهة (توسع حجم)
====================  ==========================

**عقد الحتمية**: كل الحسابات حتمية (كوانتيلات numpy بالاستيفاء الخطي
الافتراضي، وسائط، تجميع بترتيب المجموعة) — نفس المدخلات ⇒ نفس المقاييس
بايت-بايت؛ ``run_ablation`` بساعة محقونة يجعل التقرير كله حتميًا.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from .ablation import Dataset, FeatureSet

__all__ = [
    "FEATURE_POLARITY",
    "AblationEvaluatorConfig",
    "DirectionalEvaluator",
    "evaluate_directional",
]


#: قطبية السمات الموجهة: موجبة (إشارة علوية ⇒ اتجاه صاعد) أو معكوسة
#: (السفلية ⇒ صاعد). السمات غير الموجودة هنا غير موجهة — يقاس لها
#: الاستجابة المطلقة حصرًا.
FEATURE_POLARITY: dict[str, float] = {
    "close_location": 1.0,
    "gap_relationship": 1.0,
    "wick_asymmetry": -1.0,  # سالب = ذيل سفلي مهيمن = رفض هابط ⇒ صاعد
}


@dataclass(frozen=True)
class AblationEvaluatorConfig:
    """إعداد المقيّم — كل القيم موثقة الأثر (لا سحر أرقام)."""

    #: أفق الاتجاه المستقبلي المقيس (شموع أمامية).
    horizon: int = 5
    #: نصيب التدريب من السلسلة (التقسيم الزمني §43) — الباقي OOS.
    train_ratio: float = 0.70
    #: كوانتيل عتبة الإشارة العلوية من التدريب (السفلية مرآته 1−q).
    signal_quantile: float = 0.90

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizon ≥ 1 حصرًا؛ وُجد {self.horizon}")
        if not 0.1 <= self.train_ratio <= 0.9:
            raise ValueError(f"train_ratio من [0.1, 0.9]؛ وُجد {self.train_ratio}")
        if not 0.5 < self.signal_quantile < 1.0:
            raise ValueError(f"signal_quantile من (0.5, 1.0)؛ وُجد {self.signal_quantile}")


def _forward_response(closes: np.ndarray, horizon: int) -> np.ndarray:
    """المردود الموقعي الأمامي عند كل موضع: (close[t+h]−close[t])/close[t].

    المواضع الأخيرة h بلا أفق كامل ⇒ nan (لا تقييم بناقص المعلومة).
    """
    n = closes.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n <= horizon:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        out[: n - horizon] = (closes[horizon:] - closes[: n - horizon]) / closes[: n - horizon]
    return out


def evaluate_directional(
    feature_sets: Mapping[str, np.ndarray],
    closes: np.ndarray,
    config: AblationEvaluatorConfig,
) -> dict[str, float]:
    """القياس الصرف لسماتٍ مسماة — قلب المقيّم (حتمي بنيويًا).

    :param feature_sets: اسم السمة → سلسلة قيمها (بأي ترتيب عرض؛
        التكرارات تُقاس كلها — متغير الجدول قد يضم السمة مرة واحدة).
    :param closes: سلسلة الإغلاقات (المصفوف المرجعي للأفق والقسمة).
    :return: مقاييس المجموعة الموثقة في رأس الموديول.
    """
    n = closes.shape[0]
    split = int(n * config.train_ratio)
    # نافذة التقييم: التدريب ينتهي عند split، والإشارات تقيَّم من split
    # فصاعدًا مع أفق كامل (آخر horizon مواضع لا أفق لها ⇒ nan يُستبعد).
    response = _forward_response(closes, config.horizon)
    eval_slice = slice(split, n)
    responses_eval = response[eval_slice]

    signal_counts: list[int] = []
    absolute_responses: list[float] = []
    hit_rates: list[float] = []

    for name, series in sorted(feature_sets.items()):
        if series.shape[0] != n:
            raise ValueError(
                f"كسر عقد التوصيل: السمة {name!r} بطول {series.shape[0]} "
                f"لا يطابق {n} إغلاقًا — المقيّم يقيس سمات بنفس طول السلسلة"
            )
        train = series[:split]
        finite_train = train[np.isfinite(train)]
        if finite_train.shape[0] < 10:
            continue  # دفء أطول من التدريب — لا قياس لهذه السمة (معلن بالغياب)
        hi = float(np.quantile(finite_train, config.signal_quantile))
        lo = float(np.quantile(finite_train, 1.0 - config.signal_quantile))
        if hi <= lo:
            continue  # سلسلة شبه ثابتة — لا عتبتين مميزتين
        values_eval = series[eval_slice]
        mask_hi = np.isfinite(values_eval) & (values_eval >= hi)
        mask_lo = np.isfinite(values_eval) & (values_eval <= lo)
        count = int(np.count_nonzero(mask_hi) + np.count_nonzero(mask_lo))
        signal_counts.append(count)
        valid_hi = mask_hi & np.isfinite(responses_eval)
        valid_lo = mask_lo & np.isfinite(responses_eval)
        # الاستجابة المطلقة عند كل الإشارات الصالحة
        abs_at = np.concatenate(
            [
                np.abs(responses_eval[valid_hi]),
                np.abs(responses_eval[valid_lo]),
            ]
        )
        if abs_at.shape[0] > 0:
            absolute_responses.append(float(np.median(abs_at)))
        # دقة الاتجاه للسمات الموجهة حصرًا (خريطة القطبية)
        polarity = FEATURE_POLARITY.get(name)
        if polarity is not None:
            correct = 0
            total = 0
            if np.any(valid_hi):
                expected = np.sign(polarity)
                correct += int(np.count_nonzero(np.sign(responses_eval[valid_hi]) == expected))
                total += int(np.count_nonzero(valid_hi))
            if np.any(valid_lo):
                expected = np.sign(-polarity)
                correct += int(np.count_nonzero(np.sign(responses_eval[valid_lo]) == expected))
                total += int(np.count_nonzero(valid_lo))
            if total > 0:
                hit_rates.append(correct / total)

    metrics: dict[str, float] = {}
    if not signal_counts:
        # لا سمات قِيست أصلًا (مجموعة فارغة أو دفء أطول من التدريب كله)
        # — خريطة مقاييس فارغة، لا مفاتيح صفرية توحي بقياس تمّ.
        return metrics
    metrics["oos_signal_count"] = float(sum(signal_counts))
    if absolute_responses:
        metrics["oos_absolute_response_median"] = float(np.median(absolute_responses))
    if hit_rates:
        metrics["oos_directional_hit_rate_median"] = float(np.median(hit_rates))
    return metrics


class DirectionalEvaluator:
    """مقيّم ``MetricEvaluator`` قابل للحقن في :func:`run_ablation`.

    يحسب كل سمة في المجموعة عبر :func:`features.compute_feature` (المسار
    الوحيد — مثل المحور نفسه؛ حساب مزدوج داخل المقيّم انتهاك لـA-02)
    ثم يقيسها بـ:func:`evaluate_directional`. الإنشاء بلا حالة متراكمة —
    الاستدعاءات المتتالية مستقلة (الحتمية).
    """

    def __init__(self, config: AblationEvaluatorConfig | None = None) -> None:
        self._config = config if config is not None else AblationEvaluatorConfig()

    def __call__(self, feature_set: FeatureSet, dataset: Dataset) -> dict[str, float]:
        from features import compute_feature

        candles = list(dataset.candles)
        closes = np.asarray([c.close for c in candles], dtype=np.float64)
        feature_arrays = {name: compute_feature(name, candles) for name in feature_set.features}
        return evaluate_directional(feature_arrays, closes, self._config)
