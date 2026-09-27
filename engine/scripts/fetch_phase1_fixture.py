#!/usr/bin/env python3
"""جلب عينة المرحلة 1 المرجعية — aggTrades خام + klines ذهبية (المهمة 1.6).

ينفذ مرة واحدة (يدوياً) لالتقاط نافذة حقيقية من Binance USDⓈ-M وتثبيتها
كنموذج اختبار قابل لإعادة الإنتاج: نفس الشموع تُبنى من نفس الخام دائماً.

المخرجات في tests/fixtures/phase1/:
- trades.parquet : الصفقات الخام بترميز Parquet نفسه الذي يستخدمه المخزن
- klines.json    : شموع 1m المرجعية من البورصة (golden)
- manifest.json  : حدود النافذة والأعداد والhash (توثيق العينة)

الاستخدام:
    uv run --no-sync python scripts/fetch_phase1_fixture.py \
        [--minutes 10] [--hours-ago 36] [--symbol BTCUSDT]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ingestion" / "src"))

from ingestion.binance import BinanceRestClient
from ingestion.raw_store import write_parquet_bytes
from schemas import TradeEvent

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase1"


async def fetch(
    minutes: int, hours_ago: int, symbol: str
) -> tuple[list[TradeEvent], list[dict[str, object]]]:
    """التقاط نافذة مغلقة [start, start+minutes) قبل hours_ago ساعات تقريباً."""
    now_ms = int(time.time() * 1000)
    # حدّ دقيقة موثق: النافذة محاذاة لحدود الدقيقة كي تتطابق دلاء الشموع
    start = ((now_ms - hours_ago * 3_600_000) // 60_000) * 60_000
    end = start + minutes * 60_000 - 1  # مغلقة الطرفين بكسر المللي الأخير
    async with BinanceRestClient() as client:
        trades = await client.fetch_aggtrades(symbol, start, end)
        klines = await client.fetch_klines(symbol, "1m", start_ms=start, end_ms=end)
    return trades, [
        {
            "open_time_ms": bar.open_time_ms,
            "close_time_ms": bar.close_time_ms,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in klines
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="جلب عينة المرحلة 1 المرجعية")
    parser.add_argument("--minutes", type=int, default=10, help="طول النافذة بالدقائق (افتراضي 10)")
    parser.add_argument(
        "--hours-ago", type=int, default=36, help="عمر النافذة بالساعات (افتراضي 36)"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="الرمز (افتراضي BTCUSDT)")
    args = parser.parse_args()

    trades, klines = asyncio.run(fetch(args.minutes, args.hours_ago, args.symbol))
    if not trades or not klines:
        print("نافذة فارغة — جرب معطيات أخرى", file=sys.stderr)
        return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    parquet_bytes = write_parquet_bytes(trades)
    (FIXTURE_DIR / "trades.parquet").write_bytes(parquet_bytes)
    (FIXTURE_DIR / "klines.json").write_text(
        json.dumps(klines, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    manifest = {
        "symbol": args.symbol,
        "venue": trades[0].venue,
        "feed_id": trades[0].feed_id,
        "minutes": args.minutes,
        "event_count": len(trades),
        "first_event_time": trades[0].event_time_utc.isoformat(),
        "last_event_time": trades[-1].event_time_utc.isoformat(),
        "kline_count": len(klines),
        "trades_parquet_sha256": hashlib.sha256(parquet_bytes).hexdigest(),
        "trades_parquet_bytes": len(parquet_bytes),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"✓ عينة {args.symbol}: {len(trades)} صفقة → trades.parquet ({len(parquet_bytes)} بايت)")
    print(f"✓ {len(klines)} شمعة مرجعية → klines.json")
    print(f"✓ manifest.json: {manifest['first_event_time']} → {manifest['last_event_time']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
