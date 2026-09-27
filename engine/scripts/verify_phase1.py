#!/usr/bin/env python3
"""verify-phase1 — البوابة الشاملة للمرحلة 1 (المهمة 1.6، build_plan §D).

يثبت الأبواب الثلاثة للمرحلة دفعة واحدة على عينة مرجعية حقيقية مثبتة
(tests/fixtures/phase1 — نافذة BTCUSDT مغلقة أُلقطت من Binance):

1. **الحتمية:** المسار الأرشيفي (خام → مخزن) ثم الإعادة (قراءة الخام من
   المخزن → إعادة المعالجة) تنتجان سلسلة شموع متطابقة hash-for-hash.
2. **الذهبية:** شموع 1m المبنية من aggTrades تطابق OHLCV شموع البورصة
   نفسها (klines) 100% على الدلاء المكتملة التغطية.
3. **الخلود والاستعلام:** الخام خالد في الكائني (round-trip عبر RawStore)،
   والقاعدة تعرف الأحداث المنقّاة والشموع (كتابة idempotent + قراءة موثوقة).

الاستخدام (يتطلب البنية الحية — supervisor يعمل):
    uv run --no-sync python scripts/verify_phase1.py
خروج 0 = البوابة خضراء؛ أي فشل يطبع تشخيصاً ويخرج 1.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ingestion" / "src"))

from ingestion.candles import CandleBuilder
from ingestion.market_store import MarketStore, event_quality
from ingestion.raw_store import RawStore, read_parquet_bytes
from ingestion.refine import RefinementAction, RefinementPipeline
from schemas import Candle, DataQuality, TradeEvent

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase1"
OUTPUT_TIMEFRAME = "1m"


@dataclass(frozen=True, slots=True)
class PipelineOutput:
    """مخرجات مسار واحد كامل — أساس المقارنة الحتمية.

    refined يحمل الأحداث المنقّاة (مقبولة + متأخرة الإدراج) مع جودة كل
    حدث — المكرر والمرفوض خارج الأرشفة (قرار موثق: market_events للمنقّى
    لا للضجيج المكرر؛ المكرر نفسه محجوم أصلاً بـON CONFLICT على مفتاحه).
    """

    closed_candles: list[Candle]
    refined: list[tuple[TradeEvent, DataQuality]]
    accepted: int
    late: int
    duplicates: int
    rejected: int


def run_pipeline(events: list[TradeEvent]) -> PipelineOutput:
    """المراحل §33.1: تنقيح → جودة الحدث → شموع 1m — دالة نقية حتمية."""
    pipeline = RefinementPipeline(allowed_symbols={events[0].symbol})
    builder = CandleBuilder(timeframe=OUTPUT_TIMEFRAME)
    closed: list[Candle] = []
    refined: list[tuple[TradeEvent, DataQuality]] = []
    accepted = late = duplicates = rejected = 0
    for event in events:
        result = pipeline.process(event)
        if result.event is None:
            if result.action is RefinementAction.DUPLICATE_DROPPED:
                duplicates += 1
            else:
                rejected += 1
            continue
        if result.action is RefinementAction.LATE_INSERTED:
            late += 1
        else:
            accepted += 1
        # جودة الحدث من إشاراته الحدثية البحتة — قرار موثق في market_store
        quality = event_quality(result.signals)
        refined.append((event, quality))
        emitted = builder.add_trade(event, quality=quality)
        if emitted is not None and emitted.is_closed:
            closed.append(emitted)
    instrument = f"{events[0].venue}:{events[0].symbol}"
    final = builder.close_current(instrument, OUTPUT_TIMEFRAME)
    if final is not None:
        closed.append(final)
    return PipelineOutput(
        closed_candles=closed,
        refined=refined,
        accepted=accepted,
        late=late,
        duplicates=duplicates,
        rejected=rejected,
    )


def candles_hash(candles: list[Candle]) -> str:
    """hash حتمي لسلسلة شموع — تمثيل قانوني مرتب ثابت البنية."""
    canonical = json.dumps(
        [c.model_dump(mode="json") for c in candles],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compare_golden(
    candles: list[Candle], klines: list[dict[str, object]], last_event_ms: int
) -> tuple[int, list[str]]:
    """مطابقة OHLCV مع شموع البورصة — فقط الدلاء المكتملة التغطية.

    الدلو مكتمل التغطية إذا أغلقت البورصة نافذته قبل آخر صفقة في عينتنا
    (close_time_ms < آخر حدث) — الدلو الأخير المقصوص حكمه مؤجل لا فاشل.
    """
    errors: list[str] = []
    covered = 0
    for kline in klines:
        if int(kline["close_time_ms"]) >= last_event_ms:  # type: ignore[arg-type]
            continue  # دلو مقصوص — خارج حكم المطابقة
        covered += 1
        bar_time = datetime.fromtimestamp(int(kline["open_time_ms"]) / 1000.0, tz=UTC)  # type: ignore[arg-type]
        match = next((c for c in candles if c.bar_time == bar_time), None)
        if match is None:
            errors.append(f"شمعة {bar_time.isoformat()} غائبة عن المخرجات")
            continue
        for field, expected in (
            ("open", kline["open"]),
            ("high", kline["high"]),
            ("low", kline["low"]),
            ("close", kline["close"]),
            ("volume", kline["volume"]),
        ):
            actual = getattr(match, field)
            if abs(float(actual) - float(expected)) > 1e-9:  # type: ignore[arg-type]
                errors.append(
                    f"شمعة {bar_time.isoformat()} حقل {field}: بنينا {actual} والمرجع {expected}"
                )
    return covered, errors


async def main() -> int:
    trades_path = FIXTURE_DIR / "trades.parquet"
    klines = json.loads((FIXTURE_DIR / "klines.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    symbol = manifest["symbol"]

    print(f"═══ verify-phase1 — عينة {symbol} ({manifest['event_count']} صفقة) ═══")
    events = read_parquet_bytes(trades_path.read_bytes())
    if len(events) != manifest["event_count"]:
        print(f"✗ العينة فسدت: {len(events)} صفقة مقابل {manifest['event_count']} بالبيان")
        return 1

    # ── (1) الخام خالد: كتابة → قراءة من الكائني (round-trip) ──
    async with RawStore() as raw:
        await raw.ensure_bucket()
        batch = await raw.write_batch(events)
        print(
            f"✓ الخام خالد: {batch.event_count} صفقة → {batch.s3_key} ({batch.parquet_bytes} بايت)"
        )
        replayed = await raw.read_batch(batch.batch_id)
        if len(replayed) != len(events):
            print(f"✗ الإعادة فقدت صفقات: {len(replayed)} مقابل {len(events)}")
            return 1

    # ── (2) الحتمية: المسار الأرشيفي مقابل الإعادة من المخزن ──
    run_a = run_pipeline(events)
    run_b = run_pipeline(replayed)
    hash_a = candles_hash(run_a.closed_candles)
    hash_b = candles_hash(run_b.closed_candles)
    print(
        f"✓ المسار الأرشيفي: {run_a.accepted} مقبول، {run_a.late} متأخر، "
        f"{run_a.duplicates} مكرر، {run_a.rejected} مرفوض"
    )
    if hash_a != hash_b:
        print("✗ الحتمية انكسرت: hash أ ≠ hash ب")
        print(f"    أ: {hash_a}")
        print(f"    ب: {hash_b}")
        return 1
    print(f"✓ الحتمية: نفس الهاش عبر المسارين ({hash_a[:16]}…)")

    # ── (3) الذهبية: مطابقة OHLCV مع شموع البورصة نفسها ──
    last_event_ms = int(events[-1].event_time_utc.timestamp() * 1000)
    covered, errors = compare_golden(run_a.closed_candles, klines, last_event_ms)
    if errors:
        print(f"✗ المطابقة الذهبية: {len(errors)} خللاً من {covered} دلو مكتمل")
        for error in errors[:10]:
            print(f"    - {error}")
        return 1
    print(f"✓ الذهبية: {covered}/{covered} دلو مكتمل التغطية مطابق لـOHLCV البورصة 100%")

    # ── (4) القاعدة: أحداث منقّاة + شموع idempotent وقراءة مطابقة ──
    async with MarketStore() as market:
        inserted = await market.write_events(
            [e for e, _ in run_a.refined], [q for _, q in run_a.refined]
        )
        inserted_again = await market.write_events(
            [e for e, _ in run_a.refined], [q for _, q in run_a.refined]
        )
        total = await market.count_events(symbol)
        if inserted_again != 0:
            print(f"✗ idempotency الأحداث انكسرت: الكتابة الثانية أدخلت {inserted_again}")
            return 1
        print(f"✓ الأحداث في القاعدة: {total} صف (أول كتابة {inserted} ثم 0 عند الإعادة)")

        await market.upsert_candles(run_a.closed_candles)
        await market.upsert_candles(run_b.closed_candles)  # idempotent
        from_db = await market.read_candles(
            f"{events[0].venue}:{symbol}", OUTPUT_TIMEFRAME, closed_only=False
        )
        db_hash = candles_hash(from_db)
        if db_hash != hash_a:
            print("✗ الشموع في القاعدة انحرفت عن سلسلة المسار")
            print(f"    القاعدة: {db_hash}")
            print(f"    المسار:  {hash_a}")
            return 1
        print(f"✓ الشموع في القاعدة: {len(from_db)} صف مطابق للسلسلة (hash موحد)")

    print("═══ بوابة المرحلة 1: خضراء بالكامل ═══")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
