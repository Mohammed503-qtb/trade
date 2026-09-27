#!/usr/bin/env python3
"""جلب عينة المرحلة 2 المرجعية — شموع klines لثلاثة أطر (المهمة 2-g).

الغرض: نافذة تاريخية مغلقة تُغذي بوابة verify-phase2 — مسار السياق
الكامل (جلسات ← تقلب ← نظام ← انحياز ← لقطة) يحتاج عمقًا يتجاوز عينة
المرحلة 1 القصيرة (10 دقائق):

- 1m  × 1440 (يوم UTC كامل)     — إطار التنفيذ LTF (§9.1)
- 15m × 192  (يومان UTC)        — الإطار الأوسط MTF
- 1h  × 168  (سبعة أيام UTC)    — الإطار الأعلى HTF (دافئ الانحياز)

klines المرجعية من البورصة نفسها (قانونية بموجب بوابة المرحلة 1 الذهبية:
الشموع المبنية من aggTrades تطابقها 100%، فاستخدامها مباشرة كمدخل سياق
شرعي وموفر).

الاستخدام:
    uv run --no-sync python scripts/fetch_phase2_fixture.py [--symbol BTCUSDT] [--days-ago 1]
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

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase2"

# الأطر وأعماقها (§9.1: فصل الأدوار الوظيفي — القيم إعدادية موثقة)
TIMEFRAME_DEPTHS: tuple[tuple[str, int, int], ...] = (
    # (interval, عدد الشموع, طول النافذة بالأيام)
    ("1m", 1440, 1),
    ("15m", 96 * 2, 2),
    ("1h", 24 * 7, 7),
)


def klines_to_json(bars: list[object]) -> list[dict[str, object]]:
    """ترميز الشموع الخام إلى JSON قابل للالتزام — open_time_ms هو المفتاح."""
    return [
        {
            "open_time_ms": bar.open_time_ms,  # type: ignore[attr-defined]
            "close_time_ms": bar.close_time_ms,  # type: ignore[attr-defined]
            "open": bar.open,  # type: ignore[attr-defined]
            "high": bar.high,  # type: ignore[attr-defined]
            "low": bar.low,  # type: ignore[attr-defined]
            "close": bar.close,  # type: ignore[attr-defined]
            "volume": bar.volume,  # type: ignore[attr-defined]
        }
        for bar in bars
    ]


async def fetch_all(symbol: str, days_ago: int) -> dict[str, list[dict[str, object]]]:
    """التقاط النوافذ الثلاث — كلها تنتهي عند خاتمة آخر يوم UTC مكتمل."""
    end_ms = ((int(time.time() * 1000) - days_ago * 86_400_000) // 86_400_000) * 86_400_000
    out: dict[str, list[dict[str, object]]] = {}
    async with BinanceRestClient() as client:
        for interval, expected_bars, days in TIMEFRAME_DEPTHS:
            start_ms = end_ms - days * 86_400_000
            bars = await client.fetch_klines(symbol, interval, start_ms=start_ms, end_ms=end_ms)
            # الشمعة الأخيرة إن كانت مفتوحة النطاق (نادر مع يوم مكتمل) تُقص
            if bars and getattr(bars[-1], "open_time_ms", 0) >= end_ms:
                bars = bars[:-1]
            if len(bars) != expected_bars:
                print(
                    f"تحذير: {interval} جلب {len(bars)} متوقعًا {expected_bars}",
                    file=sys.stderr,
                )
            out[interval] = klines_to_json(bars)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="جلب عينة المرحلة 2 المرجعية")
    parser.add_argument("--symbol", default="BTCUSDT", help="الرمز (افتراضي BTCUSDT)")
    parser.add_argument(
        "--days-ago", type=int, default=1, help="عمر خاتمة النافذة بأيام UTC (افتراضي 1)"
    )
    args = parser.parse_args()

    data = asyncio.run(fetch_all(args.symbol, args.days_ago))
    for interval, bars in data.items():
        if not bars:
            print(f"نافذة فارغة للإطار {interval}", file=sys.stderr)
            return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "symbol": args.symbol,
        "venue": "BINANCE_USDM",
        "source": "klines-rest",
        "timeframes": {},
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for interval, bars in data.items():
        payload = json.dumps(bars, indent=2, ensure_ascii=False) + "\n"
        path = FIXTURE_DIR / f"klines_{interval}.json"
        path.write_text(payload, encoding="utf-8")
        first, last = bars[0]["open_time_ms"], bars[-1]["close_time_ms"]  # type: ignore[index]
        manifest["timeframes"] = {  # type: ignore[assignment]
            **manifest["timeframes"],  # type: ignore[index]
            interval: {
                "count": len(bars),
                "first_open_time": first,
                "last_close_time": last,
                "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "bytes": len(payload.encode("utf-8")),
            },
        }
        print(f"✓ {interval}: {len(bars)} شمعة → klines_{interval}.json")
    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("✓ manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
