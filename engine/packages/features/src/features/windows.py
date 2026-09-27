"""استخراج مصفوفات float64 من قوائم الشموع — بوابة السمات الموحدة (A-02).

عقد هذا الموديول (قرار A-02 في plan_review + §26.3):

- **دوال صرفة بلا حالة**: ‎list[Candle] → FeatureSeries‎ — لا I/O ولا NATS ولا
  قاعدة بيانات ولا أي تبعية زمن-تشغيل سوى numpy وschemas؛ تستدعى من المحرك
  الحي (worker) ومحرك الإعادة (replay) بالتطابق البايتي.
- **المصدر الوحيد OHLCV الخام**: كل مصفوفة تُشتق من حقول open/high/low/close/
  volume حصرًا — **لا** اعتماد على أي حقل مشتق حسبه الابتلاع (range/body_size/
  true_range/realized_volatility المخزنة في الشمعة)؛ مسار الحساب واحد
  عبر quantmath مهما قالت الحقول المخزنة.
- **تحقق صارم قبل أي حساب**: الشموع لنفس (instrument_id, timeframe) وبترتيب
  bar_time تصاعدي غير متناقص (التساوي مقبول — رفض التكرار مسؤولية المحركات
  الموضعية لا طبقة الاستخراج). أي خرق ⇒ ‎ValueError‎ برسالة عربية واضحة —
  لا صمت ولا تخمين.
- **القائمة الفارغة قانونية**: تعيد كل الدوال مصفوفة فارغة (طول 0) بلا أخطاء؛
  عقود nan الدافئ في quantmath تتكفل بالباقي.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from schemas import Candle

__all__ = [
    "bodies",
    "closes",
    "highs",
    "log_returns",
    "lows",
    "opens",
    "ranges",
    "volumes",
]

#: سلسلة سمات: متجه float64 أحادي البعد بعقود nan في الدافئ (نفس عقد quantmath).
type FeatureSeries = NDArray[np.float64]


def _check_consistency(candles: list[Candle]) -> None:
    """التحقق الصارم: أداة واحدة، إطار واحد، ترتيب زمني غير متناقص.

    :raises ValueError: عند خلط الأدوات أو الأطر أو كسر الترتيب التصاعدي.
    """
    if len(candles) < 2:
        return
    first = candles[0]
    for i in range(1, len(candles)):
        candle = candles[i]
        if candle.instrument_id != first.instrument_id:
            raise ValueError(
                f"خلط أدوات في قائمة الشموع: {first.instrument_id!r} ثم "
                f"{candle.instrument_id!r} عند الموضع {i} — "
                "السمات تُحسب لأداة واحدة وإطار واحد حصرًا (عقد A-02)"
            )
        if candle.timeframe != first.timeframe:
            raise ValueError(
                f"خلط أطر زمنية في قائمة الشموع: {first.timeframe!r} ثم "
                f"{candle.timeframe!r} عند الموضع {i} — "
                "السمات تُحسب لأداة واحدة وإطار واحد حصرًا (عقد A-02)"
            )
        if candle.bar_time < candles[i - 1].bar_time:
            raise ValueError(
                f"bar_time غير تصاعدي عند الموضع {i}: "
                f"{candles[i - 1].bar_time} يليه {candle.bar_time} — "
                "رتّب الشموع تصاعديًا قبل استخراج السمات"
            )


def highs(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة القمم (من OHLCV الخام — لا من أي حقل مشتق)."""
    _check_consistency(candles)
    return np.asarray([c.high for c in candles], dtype=np.float64)


def lows(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة القيعان (من OHLCV الخام)."""
    _check_consistency(candles)
    return np.asarray([c.low for c in candles], dtype=np.float64)


def closes(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة الإغلاقات (من OHLCV الخام)."""
    _check_consistency(candles)
    return np.asarray([c.close for c in candles], dtype=np.float64)


def opens(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة الافتتاحات (من OHLCV الخام)."""
    _check_consistency(candles)
    return np.asarray([c.open for c in candles], dtype=np.float64)


def volumes(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة الأحجام (≥ 0 بحكم النموذج)."""
    _check_consistency(candles)
    return np.asarray([c.volume for c in candles], dtype=np.float64)


def ranges(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة المدى ‎high − low‎ محسوبةً من الخام — **ليست** حقل ``range`` المخزن.

    عمدًا لا نقرأ الحقل المخزن (يحسبه منشئ الشموع في ingestion): مصدر السمات
    الوحيد OHLCV الخام عبر quantmath — مسار واحد للحي والإعادة (A-02).
    """
    _check_consistency(candles)
    return np.asarray([c.high - c.low for c in candles], dtype=np.float64)


def bodies(candles: list[Candle]) -> FeatureSeries:
    """مصفوفة أجسام الشموع **موقّعة** ‎close − open‎ (سالب للهابطة).

    التوقيع مقصود: يغذي اتجاه الجسم لمن يحتاجه، والدوال التي تحتاج القيمة
    المطلقة (كـ spread_to_range في quantmath) تطبّق |·| بنفسها.
    """
    _check_consistency(candles)
    return np.asarray([c.close - c.open for c in candles], dtype=np.float64)


def log_returns(candles: list[Candle]) -> FeatureSeries:
    """العوائد اللوغاريتمية ‎ln(close_t / close_{t−1})‎ — أول عنصر nan دائمًا.

    القائمة الفردية تعيد ‎[nan]‎؛ والفارغة تعيد مصفوفة فارغة. الأسعار موجبة
    بحكم النموذج (Price) فلا حارس إشارة هنا.
    """
    _check_consistency(candles)
    n = len(candles)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return out
    with np.errstate(invalid="ignore", over="ignore"):
        prev = np.asarray([candles[i - 1].close for i in range(1, n)], dtype=np.float64)
        curr = np.asarray([c.close for c in candles[1:]], dtype=np.float64)
        out[1:] = np.log(curr / prev)
    return out
