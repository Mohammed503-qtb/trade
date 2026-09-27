"""مِحور الاستئصال (§43 Research Method) — المهمة 2-e، build_plan 2.5.

جدول تشغيل ablation (base / base±feature) **مكتمل التوصيل، فارغ الوظائف**:
بنية الجدول وتنفيذه وتقاريره حتمية وحقيقية 100%، بينما دالة التقييم نفسها
``placeholder_evaluator``‏ stub موثق يعيد عدد السمات — تُستبدل في المرحلة
5a.3/9 بمقاييس الإعادة الحقيقية (تكاليف واقعية، عينات خارجية، تقسيم أنظمة،
اضطراب معاملات، ضوابط ارتباط) عبر نقطة حقن واحدة: ``MetricEvaluator``.

**القرار الموثّق لدلالة الجدول (§43 حرفيًا)**:

- ``base_features`` = مجموعة البدء (سطر الأساس في كل مقارنة).
- ``ablated`` = السمات التي تُختبر قيمتها التزايدية **بُعزلًا، واحدة-واحدة**.
- لكل سمة ``X`` في ``ablated``:

  - ``X ∉ base`` ⇒ متغير ``plus_X`` بمجموعة ``base + X`` (إضافة معلومة).
  - ``X ∈ base`` ⇒ متغير ``minus_X`` بمجموعة ``base − X`` (عزل قيمة العضو
    الحاضر). ولا يُبنى ``plus_X`` لعضو حاضر — ``base + X`` يكرر القاعدة بلا
    معلومة جديدة (رفض صريح بـValueError عربية).

- الترتيب الحتمي للجدول: سطر ``base`` وحده، ثم كتلة ``plus_*`` لكل خارج
  القاعدة بترتيب ``ablated``، ثم كتلة ``minus_*`` لكل داخل القاعدة بترتيب
  ``ablated``. أي: ``1 + N(PLUS) + N(MINUS إذا كنّ في القاعدة)`` متغيرات.

**عقد الحتمية الصارم**: نفس المدخلات ⇒ نفس التقرير بايت-بايت **ما عدا
``created_at_utc``** — وهو الاستثناء الموثق الوحيد في الوضع الإنتاجي.
معامل ``now`` القابل للحقن يجعل الحتمية كاملة: الساعة المحقونة مصدر
``created_at_utc`` **وقياس ``elapsed_ms`` معًا** (ساعة ثابتة ⇒ قياس 0.0
بالضبط)، فتتطابق بايتات ``to_json()`` بين تشغيلين.

**مصدر السمات الوحيد**: سجل السمات المركزي (:func:`features.feature_names`
و:func:`features.compute_feature`) — لا استيراد مباشر لدوال السمات هنا؛
الأسماء المجهولة تُرفض بـValueError عربية عند بناء ``FeatureSet``/``AblationSpec``.

**جسر البيانات موحد**: ``Dataset`` يحمل ``tuple[Candle]`` من schemas؛
التوصيل حقيقي فعلًا — ``run_ablation`` يحسب كل سمة في كل متغير عبر
``compute_feature`` على شموع البيانات قبل نداء المقيم (إثبات أن السمات
تعمل خلف الجدول)، ويتحقق أن طول كل سلسلة يطابق عدد الشموع (عقد السلسلة).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from features import compute_feature, feature_names
from schemas import Candle

__all__ = [
    "AblationReport",
    "AblationResult",
    "AblationSpec",
    "AblationVariant",
    "Dataset",
    "FeatureSet",
    "MetricEvaluator",
    "VariantKind",
    "placeholder_evaluator",
    "run_ablation",
]


class VariantKind(StrEnum):
    """نوع صف الجدول: الأساس، أو إضافة سمة، أو استئصال عضو حاضر."""

    BASE = "BASE"
    PLUS = "PLUS"
    MINUS = "MINUS"


@dataclass(frozen=True)
class FeatureSet:
    """مجموعة سمات مُسمّاة — أسماؤها من سجل السمات حصرًا.

    :raises ValueError: اسم غير مسجل في السجل (تُسرد الأسماء القانونية)،
        أو تكرار لاسم داخل المجموعة (لا معنى لعضو مزدوج في جدول استئصال).
    """

    name: str
    features: tuple[str, ...]

    def __post_init__(self) -> None:
        registered = set(feature_names())
        unknown = [f for f in self.features if f not in registered]
        if unknown:
            raise ValueError(
                f"سمات غير مسجلة في السجل: {tuple(unknown)} — الأسماء القانونية: {feature_names()}"
            )
        duplicates = sorted({f for f in self.features if self.features.count(f) > 1})
        if duplicates:
            raise ValueError(f"أسماء سمات مكررة في المجموعة {self.name!r}: {tuple(duplicates)}")


@dataclass(frozen=True)
class Dataset:
    """جسر البيانات الموحد — شموع مغلقة لأداة واحدة وإطار واحد.

    الشموع ``tuple`` جامدة؛ ``run_ablation`` يحوّلها لقائمة عند النداء على
    دوال السمات (عقد A-02 يقبل ``list[Candle]``).
    """

    label: str
    candles: tuple[Candle, ...]


#: نقطة الحقن الوحيدة للتقييم: (مجموعة السمات، البيانات) → مقاييس.
#: المرحلة 5a.3/9 تحقن هنا مقاييس الإعادة الحقيقية (§41/§43) دون مساس
#: ببنية الجدول أو التقارير.
type MetricEvaluator = Callable[[FeatureSet, Dataset], Mapping[str, float]]


def placeholder_evaluator(feature_set: FeatureSet, dataset: Dataset) -> Mapping[str, float]:
    """‏STUB موثق — المقيم الافتراضي حتى المرحلة 5a.3/9.

    يعيد ``{"placeholder": عدد السمات في المجموعة}`` حصرًا — **لا يختلق
    مقاييس أداء وهمية** (لا عوائد ولا نسب ربح ولا ثقل لحظي): القيمة الوحيدة
    المسموح بها في هذه المرحلة هي إثبات اكتمال التوصيل (عدد السمات التي
    حُسبت فعلًا خلف الجدول). المقاييس الحقيقية تُحقن عبر ``MetricEvaluator``.
    """
    _ = dataset  # البيانات لا تُستهلك في placeholder — المقيم الحقيقي سيستهلكها
    return {"placeholder": float(len(feature_set.features))}


@dataclass(frozen=True)
class AblationVariant:
    """صف واحد من جدول الاستئصال: تسمية + مجموعة سمات + نوع الصف."""

    label: str
    feature_set: FeatureSet
    kind: VariantKind


@dataclass(frozen=True)
class AblationSpec:
    """مواصفة تجربة الاستئصال — تبني الجدول كاملًا بمنطق §43.

    الدلالة المثبتة (انظر docstring الموديول): ``base_features`` مجموعة
    البدء؛ ``ablated`` السمات المختبرة بُعزلًا واحدة-واحدة — خارج القاعدة
    ⇒ ``plus_X``، وداخلها ⇒ ``minus_X`` (ولا ``plus`` لعضو حاضر: تكرار بلا
    معلومة). ``dataset_label`` يوثق البيانات المستهدفة بالمواصفة (إن خالفت
    ``Dataset.label`` الفعلي يُوثق ذلك كملاحظة في التقرير، لا كسر).

    :raises ValueError: أسماء غير مسجلة في أي من المجموعتين، أو تكرارات
        داخل ``base_features``/``ablated``.
    """

    base_features: tuple[str, ...]
    ablated: tuple[str, ...]
    dataset_label: str

    def __post_init__(self) -> None:
        # التحقق المبكر عبر FeatureSet (نفس مصدر الحقيقة: السجل المركزي)
        FeatureSet(name="base", features=self.base_features)
        FeatureSet(name="ablated", features=self.ablated)

    @property
    def name(self) -> str:
        """اسم المواصفة الحتمي غير الملتبس — يظهر في التقارير."""
        return f"base({'+'.join(self.base_features)});ablate({','.join(self.ablated)})"

    def base_variant(self) -> AblationVariant:
        """سطر الأساس: مجموعة البدء كما هي."""
        return AblationVariant(
            label="base",
            feature_set=FeatureSet(name="base", features=self.base_features),
            kind=VariantKind.BASE,
        )

    def plus_variant(self, x: str) -> AblationVariant:
        """متغير ``base + X`` — إضافة سمة خارج القاعدة إلى مجموعة البدء.

        :raises ValueError: السمة حاضر في القاعدة أصلًا — ``base + X`` يكرر
            القاعدة بلا معلومة (قرار موثق: لا صفوف مكررة).
        """
        if x in self.base_features:
            raise ValueError(
                f"السمة {x!r} حاضرة في القاعدة أصلًا — base+{x} يكرر القاعدة "
                "بلا معلومة جديدة؛ اختبرها بminus_variant (استئصال) بدلًا منها"
            )
        features = (*self.base_features, x)
        return AblationVariant(
            label=f"plus_{x}",
            feature_set=FeatureSet(name=f"plus_{x}", features=features),
            kind=VariantKind.PLUS,
        )

    def minus_variant(self, x: str) -> AblationVariant:
        """متغير ``base − X`` — استئصال عضو حاضر من مجموعة البدء (بترتيبها).

        :raises ValueError: السمة ليست في القاعدة — لا معنى لاستئصال غائب.
        """
        if x not in self.base_features:
            raise ValueError(
                f"لا يمكن استئصال السمة {x!r} — ليست في القاعدة الأساس "
                f"{self.base_features}؛ اختبرها بplus_variant (إضافة) بدلًا منها"
            )
        features = tuple(f for f in self.base_features if f != x)
        return AblationVariant(
            label=f"minus_{x}",
            feature_set=FeatureSet(name=f"minus_{x}", features=features),
            kind=VariantKind.MINUS,
        )

    def build_variants(self) -> tuple[AblationVariant, ...]:
        """الجدول كاملًا بترتيب حتمي: base، ثم plus_*، ثم minus_*.

        لكل ``X`` في ``ablated`` يُبنى صف واحد بالضبط: ``plus_X`` إن كانت
        خارج القاعدة، و``minus_X`` إن كانت داخلها — فلا صفوف مكررة أبدًا.
        """
        variants: list[AblationVariant] = [self.base_variant()]
        variants.extend(self.plus_variant(x) for x in self.ablated if x not in self.base_features)
        variants.extend(self.minus_variant(x) for x in self.ablated if x in self.base_features)
        return tuple(variants)


@dataclass(frozen=True)
class AblationResult:
    """نتيجة تنفيذ متغير واحد: المقاييس + الزمن + المجموعة المستخدمة.

    ``metrics`` خريطة محفوظة (قراءة فقط) طبيعية إلى float، مفاتيحها مرتبة
    عند التسوية في :func:`run_ablation` لضمان حتمية التسلسل بايت-بايت.
    """

    variant_label: str
    kind: VariantKind
    features_used: tuple[str, ...]
    metrics: Mapping[str, float]
    elapsed_ms: float


#: الملاحظات الثابتة الموثقة في كل تقرير هذه المرحلة — حتمية بايت-بايت.
_BASE_NOTES: tuple[str, ...] = (
    "منهج §43: كل سمة تُختبر قيمتها التزايدية بُعزلها — base مقابل base+X "
    "(خارج القاعدة) أو base-X (داخلها)؛ لا بقاء لسمة إلا بعد قيمة تزايدية "
    "مستقرة (تكاليف واقعية، عينات خارجية، تقسيم أنظمة، اضطراب معاملات، ضوابط ارتباط).",
    "التقييم الحالي placeholder (عدد السمات) — STUB موثق؛ المقاييس الحقيقية "
    "تُحقن عبر MetricEvaluator عند المرحلة 5a.3/9 (مِحور الإعادة §26).",
    "التوصيل حقيقي: كل سمة في كل متغير حُسبت فعلًا عبر compute_feature على "
    "شموع البيانات قبل نداء المقيم (عقود الدافئ nan من quantmath محفوظة).",
)


@dataclass(frozen=True)
class AblationReport:
    """تقرير تجربة استئصال — جاهز لبوابات الترقية §41 (code_commit،
    feature_schema، النوافذ…) عند حقن المقيم الحقيقي لاحقًا.

    ``created_at_utc`` هو **الاستثناء الوحيد** للحتمية البايتية في الوضع
    الإنتاجي؛ مع حقن ``now`` في :func:`run_ablation` تصبح الحتمية كاملة.
    """

    spec_name: str
    dataset_label: str
    created_at_utc: datetime
    variants: tuple[AblationResult, ...]
    notes: tuple[str, ...]

    def to_json(self) -> str:
        """تسلسل JSON حتمي (sort_keys، indent=2، ensure_ascii=False).

        نفس المدخلات (بساعة محقونة) ⇒ نفس البايتات بالضبط.
        """
        payload: dict[str, object] = {
            "spec_name": self.spec_name,
            "dataset_label": self.dataset_label,
            "created_at_utc": self.created_at_utc.isoformat(),
            "variants": [
                {
                    "variant_label": result.variant_label,
                    "kind": result.kind.value,
                    "features_used": list(result.features_used),
                    "metrics": dict(sorted(result.metrics.items())),
                    "elapsed_ms": result.elapsed_ms,
                }
                for result in self.variants
            ],
            "notes": list(self.notes),
        }
        return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """جدول markdown عربي للعرض: صف لكل متغير بمقاييسه وزمنه."""
        lines: list[str] = [
            f"# تقرير الاستئصال (§43) — {self.spec_name}",
            "",
            f"- البيانات: `{self.dataset_label}`",
            f"- أُنشئ (UTC): {self.created_at_utc.isoformat()}",
            f"- عدد المتغيرات: {len(self.variants)}",
            "",
            "| المتغير | النوع | عدد السمات | المقاييس | الزمن (ms) |",
            "| --- | --- | --- | --- | --- |",
        ]
        for result in self.variants:
            metrics_cell = ", ".join(
                f"{key}={value}" for key, value in sorted(result.metrics.items())
            )
            lines.append(
                f"| `{result.variant_label}` | {result.kind.value} "
                f"| {len(result.features_used)} | {metrics_cell} "
                f"| {result.elapsed_ms} |"
            )
        lines.append("")
        lines.append("## ملاحظات")
        lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines) + "\n"


def run_ablation(
    spec: AblationSpec,
    dataset: Dataset,
    evaluator: MetricEvaluator = placeholder_evaluator,
    now: Callable[[], datetime] | None = None,
) -> AblationReport:
    """تنفيذ جدول الاستئصال كاملًا على البيانات — التوصيل حقيقي، التقييم محقون.

    لكل متغير في ``spec.build_variants()``: تُحسب كل سمة في مجموعته فعليًا
    عبر :func:`features.compute_feature` على ``dataset.candles`` (إثبات أن
    السمات تعمل خلف الجدول — النوافذ الأوسع من البيانات تعيد سلاسل nan
    كاملة بحكم عقد quantmath ولا تفجر المحور)، ثم يُنداء ``evaluator``
    للمقاييس، ويُقاس الزمن بالمللي ثانية.

    ``now`` القابل للحقن (للاختبار) مصدر ``created_at_utc`` **وقياس الزمن
    معًا**: ساعة ثابتة ⇒ ``elapsed_ms = 0.0`` بالضبط وتقرير كامل الحتمية
    بايت-بايت؛ غيابه ⇒ ساعة الإنتاج (``datetime.now(UTC)`` للطابع و
    ``perf_counter`` للقياس) فيبقى ``created_at_utc`` الاستثناء الحتمي الوحيد.

    :raises ValueError: سمة أعادت سلسلة بطول يخالف عدد الشموع (كسر عقد
        التوصيل — لا صمت أمام انحراف بنية السجل).
    """
    clock: Callable[[], datetime] = now if now is not None else (lambda: datetime.now(UTC))

    def _clock_ms() -> float:
        # seam واحد: مع الساعة المحقونة يُشتق القياس منها نفسها (ساعة ثابتة
        # ⇒ 0.0)؛ وإلا فperf_counter الأحادي للقياس الجداري الحقيقي.
        if now is not None:
            return clock().timestamp() * 1000.0
        return time.perf_counter() * 1000.0

    candles = list(dataset.candles)
    results: list[AblationResult] = []
    for variant in spec.build_variants():
        start_ms = _clock_ms()
        for feature_name in variant.feature_set.features:
            series = compute_feature(feature_name, candles)
            if len(series) != len(candles):
                raise ValueError(
                    f"كسر عقد التوصيل: السمة {feature_name!r} أعادت سلسلة بطول "
                    f"{len(series)} على {len(candles)} شمعة في المتغير "
                    f"{variant.label!r} — كل سمة مسجلة يجب أن تعيد سلسلة بطول "
                    "عدد الشموع (عقد A-02)"
                )
        raw_metrics = evaluator(variant.feature_set, dataset)
        metrics: Mapping[str, float] = MappingProxyType(
            dict(sorted((key, float(value)) for key, value in raw_metrics.items()))
        )
        end_ms = _clock_ms()
        results.append(
            AblationResult(
                variant_label=variant.label,
                kind=variant.kind,
                features_used=variant.feature_set.features,
                metrics=metrics,
                elapsed_ms=max(0.0, end_ms - start_ms),
            )
        )

    notes = list(_BASE_NOTES)
    if spec.dataset_label != dataset.label:
        notes.append(
            f"تحذير مطابقة: المواصفة تعلن بيانات {spec.dataset_label!r} "
            f"وشُغّلت فعليًا على {dataset.label!r}"
        )
    return AblationReport(
        spec_name=spec.name,
        dataset_label=spec.dataset_label,
        created_at_utc=clock(),
        variants=tuple(results),
        notes=tuple(notes),
    )
