"""تجميع تقرير الإعادة (§26.2 + بوابة 9) — «إعادة كاملة آلية موثقة».

التقرير يحمل هوية الاستنساخ التساعية ومخرجات المحاكي كاملة ومقاييسها
وإعداده المختوم — ويتسلسل بايت-بايت حتمًا ما عدا ``created_at_utc``
(الاستثناء الموثق الوحيد — نمط AblationReport)؛ مع الساعة المحقونة
تكتمل الحتمية فيصبح التقريران المتطابقان الهوية متطابقين بايت-بايت.

«The exact result must be reproducible from those identifiers» — البنّاء
يختم ``backtest_id`` من المعرّفات ذاتها (uuid5 في :mod:`backtest.identity`)
فلا انفصام بين الهوية والمضمون.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from schemas import BacktestIdentity, BacktestReport, CostMode, IntrabarPolicy, SimulatedTrade

from .identity import backtest_id_for
from .metrics import compute_metrics
from .parameter_sets import BacktestConfig

__all__ = ["BASE_NOTES", "build_report"]

#: الملاحظات الثابتة في كل تقرير — حتمية بايت-بايت.
BASE_NOTES: tuple[str, ...] = (
    "الترتيب داخل الشمعة متحفظ (§30): الوقف قبل الهدف عند لمسهما معًا، "
    "والدخول ثم الوقف عند اقترانهما — لا مخرج محابٍ أبدًا.",
    "التعبئة عند الحافة المعاكسة للمنطقة (أسوأ تعبئة قانونية) بنسبة "
    "إعدادية لكل شمعة لمس — تعبئة جزئية §26.1.",
    "التكاليف تحلل محقق واحد §25.2 (لا انزلاق مضاعف داخل أسعار التعبئة) "
    "وREALISTIC نمط القبول حصرًا (§25.1).",
    "الباقيات مفتوحات حتى نهاية البيانات لا وسم لهن (§30: الوسم بعد "
    "انقضاء الأفق) — يُحصين في المقاييس عدًّا لا يُختلق لهن حكم.",
)


def build_report(
    *,
    identity: BacktestIdentity,
    trades: Sequence[SimulatedTrade],
    config: BacktestConfig,
    now: Callable[[], datetime] | None = None,
    extra_notes: Sequence[str] = (),
) -> BacktestReport:
    """تجميع التقرير — يختم الهوية ويحسب المقاييس ويثبت الملاحظات.

    :param identity: المعرّفات التسع دون ``backtest_id`` — يُختم هنا
        من المعرّفات ذاتها (أي قيمة عابرة تُستبدل).
    :param trades: صفقات المحاكي بترتيب حتمي (مسؤولية المستدعي:
        زمن القرار ثم معرف السيناريو).
    """
    sealed = identity.model_copy(update={"backtest_id": backtest_id_for(identity)})
    clock: Callable[[], datetime] = now if now is not None else (lambda: datetime.now(UTC))
    metrics = compute_metrics(trades)

    notes = list(BASE_NOTES)
    if metrics.open_at_data_end:
        notes.append(
            f"{metrics.open_at_data_end} نية بقيت مفتوحة/غير محسومة حتى نهاية "
            "البيانات — خارج الوسم والمقاييس (§30)."
        )
    if metrics.not_executable:
        notes.append(
            f"{metrics.not_executable} نية لم تعبأ أصلًا (NOT_EXECUTABLE) — عدّ "
            "مستقل لا يدخل إحصاءات R."
        )
    notes.extend(extra_notes)

    return BacktestReport(
        identity=sealed,
        cost_mode=CostMode.REALISTIC,
        intrabar_policy=IntrabarPolicy.CONSERVATIVE,
        config_fingerprint=config.fingerprint(),
        trades=tuple(trades),
        metrics=metrics,
        notes=tuple(notes),
        created_at_utc=clock(),
    )
