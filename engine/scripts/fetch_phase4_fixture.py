#!/usr/bin/env python3
"""جلب عينة المرحلة 4 المرجعية — نافذة aggTrades طويلة + klines ذهبية
بالحجم الشرائي المتسبب (المهمة 4-a).

الغرض: تمكين بوابة المرحلة 4 (الفوتبرنت والتدفق):

- الفوتبرنت يُبنى من aggTrades عبر علم ``buyer_is_maker`` — يحتاج نافذة
  أطول من عينة المرحلة 1 (10 دقائق) كي تظهر الكواشف أعلىها أحداث
  امتصاص/إنهاك/عناقيد اختلال بتنوع واقعي.
- المرجع الذهبي للمطابقة الإحصائية (بوابة 4 نصًا: «حسابات التدفق ضمن
  تسامح معلن مقابل مرجع»): ``takerBuyBaseAssetVolume`` من klines هو
  مرجع البورصة نفسه لحجم الشراء العدواني لكل شمعة 1m، و``count`` مرجع
  عدد الصفقات — كلاهما يُخزَّن في klines.json هنا.

المخرجات في tests/fixtures/phase4/:
- trades.parquet : الصفقات الخام بترميز Parquet الحتمي نفسه (raw_store)
- klines.json    : شموع 1m المرجعية OHLCV + taker_buy_volume + trade_count
- manifest.json  : حدود النافذة والأعداد والhash (توثيق العينة)

الاستخدام:
    uv run --no-sync python scripts/fetch_phase4_fixture.py \
        [--minutes 120] [--hours-ago 30] [--symbol BTCUSDT]
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

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase4"


async def fetch(
    minutes: int, hours_ago: int, symbol: str
) -> tuple[list[TradeEvent], list[dict[str, object]]]:
    """التقاط نافذة مغلقة [start, start+minutes) قبل hours_ago ساعة تقريبًا."""
    now_ms = int(time.time() * 1000)
    # محاذاة حد الدقيقة (نفس عقد المرحلة 1) كي تتطابق دلاء الشموع والفوتبرنت
    start = ((now_ms - hours_ago * 3_600_000) // 60_000) * 60_000
    end = start + minutes * 60_000 - 1
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
            # المرجع الذهبي للفوتبرنت (§12.7 + KlineBar المرحلة 4)
            "taker_buy_volume": bar.taker_buy_volume,
            "trade_count": bar.trade_count,
        }
        for bar in klines
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="جلب عينة المرحلة 4 المرجعية")
    parser.add_argument(
        "--minutes", type=int, default=120, help="طول النافذة بالدقائق (افتراضي 120)"
    )
    parser.add_argument(
        "--hours-ago", type=int, default=30, help="عمر النافذة بالساعات (افتراضي 30)"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="الرمز (افتراضي BTCUSDT)")
    args = parser.parse_args()

    trades, klines = asyncio.run(fetch(args.minutes, args.hours_ago, args.symbol))
    if not trades or not klines:
        print("نافذة فارغة — جرب معطيات أخرى", file=sys.stderr)
        return 1

    # اتساق أولي موثق: عدد الشموع = طول النافذة بالدقائق (كل دلو مكتمل)
    if len(klines) != args.minutes:
        print(
            f"تحذير: {len(klines)} شمعة لدلو {args.minutes} دقيقة — تحقق من محاذاة النافذة",
            file=sys.stderr,
        )

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
        # المراجع الذهبية: مجموع الحجم الشرائي المتسبب وعدد الصفقات عبر الدلاء
        "taker_buy_volume_sum": sum(float(k["taker_buy_volume"]) for k in klines),  # type: ignore[arg-type]
        "trade_count_sum": sum(int(k["trade_count"]) for k in klines),  # type: ignore[arg-type]
        "trades_parquet_sha256": hashlib.sha256(parquet_bytes).hexdigest(),
        "trades_parquet_bytes": len(parquet_bytes),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"✓ عينة {args.symbol}: {len(trades)} صفقة → trades.parquet ({len(parquet_bytes)} بايت)")
    print(f"✓ {len(klines)} شمعة مرجعية (بالحجم الشرائي المتسبب) → klines.json")
    print(f"✓ manifest.json: {manifest['first_event_time']} → {manifest['last_event_time']}")
    tb = manifest["taker_buy_volume_sum"]
    tc = manifest["trade_count_sum"]
    print(f"  مرجع ذهبي: taker_buy={tb:.3f} عدّاد={tc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
