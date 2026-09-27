#!/usr/bin/env python3
"""run-ablation — تشغيل تجريبي لمِحور الاستئصال (§43) — المهمة 2-e، build_plan 2.5.

يبني ``Dataset`` قانونيًا من عينة المرحلة 1 (نفس نمط ``scripts/verify_phase1.py``
حرفيًا: قراءة trades.parquet عبر ingestion → خط التنقيح §33.1 → جودة الحدث →
شموع 1m مغلقة)، ثم يشغّل جدول الاستئصال على سمات المرحلة 2 بتقييم
placeholder موثق (يُستبدل بمقاييس الإعادة الحقيقية في 5a.3/9)، يطبع جدول
markdown للمتغيرات في stdout ويكتب التقرير JSON+MD في مجلد الخرج.

الاستخدام:
    uv run --no-sync python scripts/run_ablation.py --dataset phase1 \
        [--out data/research/ablation] [--base a,b,…] [--ablate a,b,…]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ingestion" / "src"))

from engine_replay import AblationSpec, Dataset, run_ablation
from features import FeatureCategory, list_features
from ingestion.candles import CandleBuilder
from ingestion.market_store import event_quality
from ingestion.raw_store import read_parquet_bytes
from ingestion.refine import RefinementPipeline
from schemas import Candle

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase1"
OUTPUT_TIMEFRAME = "1m"

#: القاعدة الافتراضية الموثقة: كل السمات المسجلة خارج فئة VOLATILITY —
#: فتختبر --ablate الافتراضية (فئة VOLATILITY كاملة) القيمة التزايدية
#: لسمات التقلب فوق قاعدة بلا تقلب (وبلا تداخل: لا plus لعضو حاضر).
DEFAULT_BASE: tuple[str, ...] = (
    "range_expansion_100",
    "spread_to_range",
    "normalized_range_14",
    "directional_efficiency_20",
    "volume_concentration_20",
)


def default_ablated() -> tuple[str, ...]:
    """السمات المستأصلة الافتراضية: كل سمات فئة VOLATILITY (بترتيب السجل)."""
    return tuple(
        spec.name for spec in list_features() if spec.category is FeatureCategory.VOLATILITY
    )


def build_phase1_dataset() -> Dataset:
    """بناء Dataset من عينة المرحلة 1 — النمط القانوني نفسه كverify_phase1.

    قراءة trades.parquet عبر ingestion (read_parquet_bytes) ثم خط التنقيح
    وجودة الحدث وبناء شموع 1m عبر CandleBuilder — بلا بنية حية (مسار صرف).
    """
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    events = read_parquet_bytes((FIXTURE_DIR / "trades.parquet").read_bytes())
    if len(events) != manifest["event_count"]:
        raise SystemExit(
            f"✗ عينة المرحلة 1 فسدت: {len(events)} صفقة مقابل {manifest['event_count']} بالبيان"
        )
    pipeline = RefinementPipeline(allowed_symbols={manifest["symbol"]})
    builder = CandleBuilder(timeframe=OUTPUT_TIMEFRAME)
    closed: list[Candle] = []
    for event in events:
        result = pipeline.process(event)
        if result.event is None:
            continue  # مكرر/مرفوض — خارج البناء (يحصيها verify_phase1 لا نحن)
        quality = event_quality(result.signals)
        emitted = builder.add_trade(event, quality=quality)
        if emitted is not None and emitted.is_closed:
            closed.append(emitted)
    instrument = f"{events[0].venue}:{events[0].symbol}"
    final = builder.close_current(instrument, OUTPUT_TIMEFRAME)
    if final is not None:
        closed.append(final)
    return Dataset(label="phase1", candles=tuple(closed))


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_ablation",
        description="تشغيل تجريبي لمِحور الاستئصال (§43) — تقرير placeholder موثق",
    )
    parser.add_argument(
        "--dataset",
        choices=["phase1"],
        default="phase1",
        help="البيانات: phase1 فقط المتاح الآن (عينة fixtures/phase1)",
    )
    parser.add_argument(
        "--out",
        default="data/research/ablation",
        help="مجلد الخرج (افتراضي: data/research/ablation)",
    )
    parser.add_argument(
        "--base",
        type=_split_csv,
        default=DEFAULT_BASE,
        help="أسماء سمات القاعدة مفصولة بفواصل",
    )
    parser.add_argument(
        "--ablate",
        type=_split_csv,
        default=default_ablated(),
        help="أسماء السمات المستأصلة مفصولة بفواصل (افتراضي: فئة VOLATILITY كاملة)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = build_phase1_dataset()
    print(
        f"═══ ablation — بيانات {args.dataset}: {len(dataset.candles)} شمعة "
        f"{OUTPUT_TIMEFRAME} مغلقة ═══"
    )
    print(f"القاعدة ({len(args.base)}): {', '.join(args.base)}")
    print(f"المستأصلة ({len(args.ablate)}): {', '.join(args.ablate)}")
    print()

    spec = AblationSpec(
        base_features=tuple(args.base),
        ablated=tuple(args.ablate),
        dataset_label=args.dataset,
    )
    report = run_ablation(spec, dataset)
    markdown = report.to_markdown()
    print(markdown)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"{stamp}-{args.dataset}.json"
    md_path = out_dir / f"{stamp}-{args.dataset}.md"
    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    print(f"✓ التقرير: {json_path} + {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
