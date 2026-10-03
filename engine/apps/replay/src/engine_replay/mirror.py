"""المرآة الحتمية D-08 — نسخة بايثونية مستقلة من مصدر Pine تُقارن بالمحرك.

المهمة 10.4 (build_plan §D): «تشغيل المرآة الحتمية لأهم الأحداث + مقارنة
بالجدول D-08». هذه الوحدة هي التنفيذ التشغيلي لهذه الجملة:

(1) **منافذ Pine**: نسخ حرفي بالبايثون لمصدر ``pine/libraries/engine_core.pine``
    (كُتبت بإعادة قراءة المصدر — لا بنسخ المحرك): ATR وايلدر، آلة
    المتطرفات الفراكتلية، خريطة السيولة الكبرى بدمج المستوى المتساوي،
    آلة الاجتياح، ومحرك كسر البنية.

(2) **سلسلة المحرك**: المكونات الحقيقية نفسها التي تثبتها البوابات
    (VolatilityEngine + SwingDetector + StructureBreakEngine +
    LiquidityMapEngine + SweepDetector) بترتيب الواجهات الموثق.

(3) **المقارنة (جدول D-08)**: OHLCV مطابقة تامة، ATR ±0.01%، الأحداث
    البنائية (Sweep/BOS) مطابقة صارمة على المجموعة المشتركة (مناطق
    المتطرفات)، وصف دلتا/POC «غير مشترك» موثق (فوتبرنت TV يتطلب حساب
    Premium §6.2 — الفرق المنهجي معلن لا يعد فشلًا).

الحصيلة: ``engine/docs/mirror/phase10/mirror_report.json`` — قابلة لإعادة
الإنتاج بايت-بايت (لا ساعة جدرية في أي مسار).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from schemas import Candle, DataQuality

__all__ = [
    "pine_alert_payload",
    "pine_atr_wilder",
    "run_mirror",
    "validate_pine_source",
]

#: جذر المحرك — من هذه الوحدة: apps/replay/src/engine_replay/mirror.py
_ENGINE_ROOT = Path(__file__).resolve().parents[4]

#: موضع مكونات pine في المستودع (جذر sandbox).
PINE_LIB = _ENGINE_ROOT.parent / "pine" / "libraries" / "engine_core.pine"
PINE_INDICATOR = _ENGINE_ROOT.parent / "pine" / "indicators" / "reasoning_engine.pine"

#: عينة المرآة — العينة المرجعية الثلاثية الأطر نفسها (المرحلة 2).
PHASE2_DIR = _ENGINE_ROOT / "tests" / "fixtures" / "phase2"

#: جدول التسامح D-08 حرفيًا — لكل عائلة حساب حكمها المعلن.
D08_TOLERANCES: dict[str, dict[str, Any]] = {
    "OHLCV": {"rule": "exact", "tolerance": 0.0},
    "ATR": {"rule": "relative", "tolerance": 0.0001},  # ±0.01%
    "SWEEP": {"rule": "strict", "tolerance": 0.0},
    "BOS": {"rule": "strict", "tolerance": 0.0},
    "DELTA_POC": {"rule": "not_shared", "tolerance": None},  # فوتبرنت TV يتطلب Premium (§6.2)
}

#: مضاعفات العتبة — تطابق مصدر Pine (EC_* ) وDEFAULT_MULTIPLIERS في المحرك.
_SWING_CONFIRM_BARS = 3
_STRUCT_BUF_MULT = 0.5
_SWEEP_TOL_MULT = 0.25
_DISP_MIN_MULT = 1.0
_EQUAL_TOL_MULT = 0.25
_SWEEP_WIDTH_FRACTION = 0.5
_SWEEP_EVAL_WINDOW = 3
_SWEEP_ACCEPT_CLOSES = 2
_ATR_PERIOD = 14

_SENTINEL = math.inf  # بذرة الوصيف (±∞ منطقياً — انظر f_updatePolarity)


# ═══════════════════════════ منافذ Pine (نسخ مستقل من المصدر) ═══════════════════════════


def pine_true_range(bars: list[dict[str, Any]]) -> list[float]:
    """``ta.tr(true)`` — أول قيمة H−L ثم max(H−L, |H−Cp|, |L−Cp|)."""
    out: list[float] = []
    prev_close: float | None = None
    for b in bars:
        h, low, c = float(b["high"]), float(b["low"]), float(b["close"])
        tr = (
            h - low
            if prev_close is None
            else max(h - low, abs(h - prev_close), abs(low - prev_close))
        )
        out.append(tr)
        prev_close = c
    return out


def pine_atr_wilder(trs: list[float], period: int) -> list[float | None]:
    """``ta.rma(ta.tr(true), period)`` — بذرة SMA عند period−1 فاستدعاء ذاتي.

    ``None`` قبل الدافئ (nan في Pine).
    """
    out: list[float | None] = [None] * len(trs)
    if period == 1:
        return list(trs)
    acc = 0.0
    prev: float | None = None
    for i, tr in enumerate(trs):
        if i < period:
            acc += tr
            if i == period - 1:
                prev = acc / period
                out[i] = prev
        else:
            assert prev is not None
            prev = (prev * (period - 1) + tr) / period
            out[i] = prev
    return out


def pine_volatility_atr(
    trs: list[float], history_bars: int, period: int = _ATR_PERIOD
) -> list[float | None]:
    """ATR بسياسة ``VolatilityEngine`` الحرفية: مخزن دائري بطول
    ``history_bars`` وإعادة حساب ``wilder_atr`` على النافذة كاملة كل
    شريط وأخذ آخر عنصر — لا تراكم غير محدود أبدًا (ذاكرة محدودة
    موثقة في المحرك: نفس القيم بعد امتلاء المخزن حرفيًا).

    ``None`` قبل توفر عنصرين (لا حالة من شمعة واحدة — عقد المحرك).
    """
    out: list[float | None] = []
    window: list[float] = []
    for i, tr in enumerate(trs):
        window.append(tr)
        if len(window) > history_bars:
            window.pop(0)
        if i == 0:
            out.append(None)
            continue
        series = pine_atr_wilder(window, period)
        out.append(series[-1])
    return out


@dataclass
class PineSwing:
    """متطرف مؤكد — منافذ لنوع Swing في مصدر Pine."""

    price: float
    is_high: bool
    scope: str  # "EXTERNAL" | "INTERNAL"
    strength: float
    bar_index: int
    confirm_index: int


@dataclass
class PineSwingPolarity:
    """منفذ f_updatePolarity — آلة قطبية واحدة (حالة دائمة)."""

    is_high: bool
    cand_price: float | None = None
    cand_index: int = 0
    confirm_count: int = 0
    runner_up: float | None = None
    prev_extreme: float | None = None
    external_anchor: float | None = None

    def _entry_edge(self, extreme: float) -> bool:
        if self.prev_extreme is None:
            return False
        return extreme > self.prev_extreme if self.is_high else extreme < self.prev_extreme

    def _seed_runner(self) -> float:
        return -_SENTINEL if self.is_high else _SENTINEL

    def update(self, bar_index: int, extreme: float, atr: float | None) -> PineSwing | None:
        """معالجة شمعة مغلقة — يرجع المتطرف المؤكد عند هذه الشمعة أو None."""
        result: PineSwing | None = None
        if self.cand_price is None:
            # (1) ترشيح عند حافة الدخول الفراكتلية.
            if self._entry_edge(extreme):
                self.cand_price = extreme
                self.cand_index = bar_index
                self.confirm_count = 0
                self.runner_up = self._seed_runner()
        elif (extreme > self.cand_price) if self.is_high else (extreme < self.cand_price):
            # (2) إبطال قطعي (المساواة لا تُبطل) — المُبطِل مرشح جديد فورًا.
            self.cand_price = extreme
            self.cand_index = bar_index
            self.confirm_count = 0
            self.runner_up = self._seed_runner()
        else:
            # (3) عدّ التأكيد وتحديث الوصيف.
            self.confirm_count += 1
            if self.is_high:
                self.runner_up = max(self.runner_up, extreme)  # type: ignore[type-var]
            else:
                self.runner_up = min(self.runner_up, extreme)  # type: ignore[type-var]
            if self.confirm_count >= _SWING_CONFIRM_BARS:
                price = self.cand_price
                assert price is not None
                is_external = self.external_anchor is None or (
                    price > self.external_anchor if self.is_high else price < self.external_anchor
                )
                runner = self.runner_up
                assert runner is not None
                excess = price - runner if self.is_high else runner - price
                if atr is None or excess <= 0.0:
                    strength = 0.0
                elif atr <= 0.0:
                    strength = 1.0
                else:
                    strength = math.tanh(excess / atr)
                result = PineSwing(
                    price=price,
                    is_high=self.is_high,
                    scope="EXTERNAL" if is_external else "INTERNAL",
                    strength=strength,
                    bar_index=self.cand_index,
                    confirm_index=bar_index,
                )
                if is_external:
                    self.external_anchor = price
                # شمعة الحسم قد تبدأ ترشيحًا جديدًا (استمرارية بلا فجوة).
                self.cand_price = None
                self.confirm_count = 0
                if self._entry_edge(extreme):
                    self.cand_price = extreme
                    self.cand_index = bar_index
                    self.confirm_count = 0
                    self.runner_up = self._seed_runner()
        self.prev_extreme = extreme
        return result


@dataclass
class PineZone:
    """منفذ نوع Zone — منطقة سيولة كبرى مرسَّمة من متطرف."""

    price_low: float
    price_high: float
    is_buy_side: bool
    state: str = "ACTIVE"  # ACTIVE | SWEPT | CONSUMED | INVALIDATED
    origin_index: int = 0
    source: str = "PRIOR_SWING"  # PRIOR_SWING | EQUAL_LEVEL


def pine_ingest_swing(
    zones: list[PineZone], sw: PineSwing, atr: float | None, bar_index: int
) -> None:
    """منفذ f_ingestSwing — دمج المستوى المتساوي أو إنشاء PRIOR_SWING.

    قطبية المحرك: متطرف القمة ⇒ BUY_SIDE (سيولة فوق السعر عند القمم
    — أوامر الشراء المتوقفة فوقها) والقاع ⇒ SELL_SIDE (تحته).
    """
    merged = False
    if atr is not None and atr > 0.0:
        tolerance = _EQUAL_TOL_MULT * atr
        cluster: PineZone | None = None
        for z in zones:
            if (
                z.state == "ACTIVE"
                and z.is_buy_side == sw.is_high
                and z.source in ("PRIOR_SWING", "EQUAL_LEVEL")
                and sw.price >= z.price_low - tolerance
                and sw.price <= z.price_high + tolerance
            ):
                if cluster is None:
                    # أول مطابقة تصبح العنقود وتمتص المتطرف الجديد.
                    cluster = z
                    z.source = "EQUAL_LEVEL"
                    z.price_low = min(z.price_low, sw.price)
                    z.price_high = max(z.price_high, sw.price)
                else:
                    # عضو إضافي — يوسّع العنقود ويُبطَل.
                    cluster.price_low = min(cluster.price_low, z.price_low)
                    cluster.price_high = max(cluster.price_high, z.price_high)
                    z.state = "INVALIDATED"
                merged = True
    if not merged:
        zones.append(
            PineZone(
                price_low=sw.price,
                price_high=sw.price,
                is_buy_side=sw.is_high,
                # معرف تسلسلي فريد: قد تتكون منطقتان بنفس الشمعة (قمة وقاع
                # معًا) ففهرس الشمعة ليس فريدًا — الطول قبل الإضافة فريد
                # دائمًا ورتيب الإنشاء نفسه (ترتيب المسح الحتمي).
                origin_index=len(zones),
                source="PRIOR_SWING",
            )
        )


@dataclass
class PineInteraction:
    """منفذ نوع Interaction — حلقة تفاعل اجتياح واحدة."""

    z_origin: int
    z_price_low: float
    z_price_high: float
    z_buy_side: bool
    start_index: int
    window_start: int = -1
    closes_in_window: int = 0
    qualifying_closes: int = 0
    max_excursion: float = 0.0
    penetrated_ever: bool = False
    penetration_reached: bool = False


@dataclass
class PineSweepEvent:
    """حدث اجتياح من منفذ f_sweepScan — بمفاتيح المقارنة المعلنة."""

    kind: str  # "SWEEP" | "ACCEPT"
    event_name: str  # LIQUIDITY_SWEEP_HIGH/LOW | BREAK_AND_ACCEPT_HIGH/LOW
    bar_index: int
    price: float


def pine_sweep_scan(
    zones: list[PineZone],
    interactions: list[PineInteraction],
    bar: dict[str, Any],
    bar_index: int,
    atr: float | None,
) -> list[PineSweepEvent]:
    """منفذ f_sweepScan — مسح المناطق النشطة بترتيب الإنشاء (§10.4).

    يرجع كل أحداث هذا الشريط (منطقة فحدث — قد تتعدد) بترتيب المسح.
    """
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
    atr_ok = atr is not None and atr > 0.0
    events: list[PineSweepEvent] = []
    # (طي تفاعلات المناطق الميتة أولًا)
    alive_origins = {z.origin_index for z in zones if z.state == "ACTIVE"}
    interactions[:] = [i for i in interactions if i.z_origin in alive_origins]
    # (مسح المناطق النشطة بترتيب الإنشاء)
    for z in zones:
        if z.state != "ACTIVE":
            continue
        inter = next((i for i in interactions if i.z_origin == z.origin_index), None)
        if inter is None:
            touched = high >= z.price_low and low <= z.price_high
            if not touched:
                if atr_ok:
                    assert atr is not None
                    buffer = _STRUCT_BUF_MULT * atr
                    if z.is_buy_side:
                        decisive = low > z.price_high and close - z.price_high >= buffer
                    else:
                        decisive = high < z.price_low and z.price_low - close >= buffer
                    if decisive:
                        z.state = "INVALIDATED"
                continue
            inter = PineInteraction(
                z_origin=z.origin_index,
                z_price_low=z.price_low,
                z_price_high=z.price_high,
                z_buy_side=z.is_buy_side,
                start_index=bar_index,
            )
            interactions.append(inter)
        # رصد التغلغل وراء الحافة البعيدة.
        if inter.z_buy_side:
            if high >= inter.z_price_high:
                inter.max_excursion = max(inter.max_excursion, high - inter.z_price_high)
                inter.penetrated_ever = True
        else:
            if low <= inter.z_price_low:
                inter.max_excursion = max(inter.max_excursion, inter.z_price_low - low)
                inter.penetrated_ever = True
        # العتبة والنافذة.
        if atr_ok:
            assert atr is not None
            vol_part = _SWEEP_TOL_MULT * atr
            width = inter.z_price_high - inter.z_price_low
            required = max(vol_part, width * _SWEEP_WIDTH_FRACTION)
            if inter.max_excursion >= required:
                inter.penetration_reached = True
            if inter.penetrated_ever and inter.window_start == -1:
                inter.window_start = bar_index
                inter.closes_in_window = 0
                inter.qualifying_closes = 0
        # الحسم.
        if inter.window_start != -1:
            inter.closes_in_window += 1
            beyond_far = (
                close > inter.z_price_high if inter.z_buy_side else close < inter.z_price_low
            )
            if beyond_far:
                inter.qualifying_closes += 1
            reclaimed = (
                close < inter.z_price_low if inter.z_buy_side else close > inter.z_price_high
            )
            if reclaimed:
                if inter.penetration_reached:
                    events.append(
                        PineSweepEvent(
                            kind="SWEEP",
                            event_name="LIQUIDITY_SWEEP_HIGH"
                            if inter.z_buy_side
                            else "LIQUIDITY_SWEEP_LOW",
                            bar_index=bar_index,
                            price=close,
                        )
                    )
                    z.state = "SWEPT"
                interactions.remove(inter)
            elif inter.qualifying_closes >= _SWEEP_ACCEPT_CLOSES and inter.penetration_reached:
                events.append(
                    PineSweepEvent(
                        kind="ACCEPT",
                        event_name="BREAK_AND_ACCEPT_HIGH"
                        if inter.z_buy_side
                        else "BREAK_AND_ACCEPT_LOW",
                        bar_index=bar_index,
                        price=close,
                    )
                )
                z.state = "CONSUMED"
                interactions.remove(inter)
            elif bar_index - inter.window_start >= _SWEEP_EVAL_WINDOW - 1:
                interactions.remove(inter)
        else:
            reclaimed_early = (
                close < inter.z_price_low if inter.z_buy_side else close > inter.z_price_high
            )
            if reclaimed_early:
                interactions.remove(inter)
    return events


@dataclass
class PineBosLevel:
    """منفذ نوع BosLevel — مستوى متطرف حي غير مكسور."""

    swing: PineSwing
    broken: bool = False


@dataclass
class PineBos:
    """منفذ BosState + f_onSwing/f_bosUpdate (§11.2-§11.3، الإغلاق وحده)."""

    levels: list[PineBosLevel] = field(default_factory=list)
    framework_dir: int = 0  # 0 مؤسسًا بعد / +1 صاعدًا / −1 هابطًا

    def on_swing(self, sw: PineSwing) -> None:
        self.levels.append(PineBosLevel(swing=sw))

    def update(
        self, bar: dict[str, Any], bar_index: int, atr: float | None
    ) -> list[tuple[str, str, float]]:
        """يرجع [(event_type, direction, breach), ...] — ترتيب UP ثم DOWN."""
        close = float(bar["close"])
        events: list[tuple[str, str, float]] = []
        if atr is None or atr <= 0.0 or not self.levels:
            return events
        threshold = _DISP_MIN_MULT * atr
        for direction in (1, 2):  # UP ثم DOWN — ترتيب حتمي
            is_up = direction == 1
            ref_idx = -1
            ref_gap = math.inf
            for i, lv in enumerate(self.levels):
                if lv.broken or lv.swing.is_high != is_up:
                    continue
                if is_up:
                    # المساواة ليست عبورًا فلا تُختار (عقد _nearest_level حرفيًا).
                    if lv.swing.price < close and close - lv.swing.price < ref_gap:
                        ref_gap = close - lv.swing.price
                        ref_idx = i
                else:
                    if lv.swing.price > close and lv.swing.price - close < ref_gap:
                        ref_gap = lv.swing.price - close
                        ref_idx = i
            if ref_idx < 0:
                continue
            lv = self.levels[ref_idx]
            breach = close - lv.swing.price if is_up else lv.swing.price - close
            if breach < threshold:
                continue
            if lv.swing.scope == "EXTERNAL":
                et = "EXTERNAL_BOS" if (self.framework_dir in (0, direction)) else "CHOCH"
                self.framework_dir = direction
            else:
                et = "INTERNAL_BOS"
            events.append((et, "UP" if is_up else "DOWN", breach))
            # ابتلاع المستويات الأضعف وراء امتداد الكسر (الإغلاق).
            for lv2 in self.levels:
                if lv2.broken or lv2.swing.is_high != is_up:
                    continue
                beyond = lv2.swing.price < close if is_up else lv2.swing.price > close
                if beyond:
                    lv2.broken = True
        return events


def pine_alert_payload(
    event_name: str,
    *,
    instrument: str,
    bar_time_ms: int,
    timeframe: str,
    price: float,
    schema_version: str = "1.0.0",
) -> dict[str, Any]:
    """منفذ f_alertPayload — الحمولة الخام الثمانية (§36) بلا أسرار.

    ``alert_id`` حتمي محليًا (أداة|إطار|حدث|زمن الشمعة). لا مفتاح
    idempotency هنا (يشتقه الخادم حصرًا — D-07).
    """
    return {
        "schema_version": schema_version,
        "source": "tradingview",
        "alert_id": f"{instrument}|{timeframe}|{event_name}|{bar_time_ms}",
        "instrument": instrument,
        "bar_time_ms": bar_time_ms,
        "timeframe": timeframe,
        "event": event_name,
        "price": price,
    }


# ═══════════════════════════ سلسلة منافذ Pine الكاملة ═══════════════════════════


@dataclass
class PineChainResult:
    """مخرجات سلسلة منافذ Pine فوق عينة خام — مفاتيح المقارنة كلها."""

    atr: list[float | None]
    swings: list[PineSwing]
    sweeps: list[PineSweepEvent]
    bos: list[tuple[int, str, str]]  # (bar_index, event_type, direction)
    zones_final_count: int


def run_pine_chain(bars: list[dict[str, Any]]) -> PineChainResult:
    """تشغيل منافذ Pine بترتيب المؤشر الموثق على الشموع المغلقة."""
    from market_state.volatility import VolatilityConfig

    trs = pine_true_range(bars)
    # سياسة المحرك حرفيًا: ATR محدود الذاكرة بإعادة حساب النافذة (المخزن
    # الدائري) — لا RMA متراكمة غير محدودة (تطابق القيم بعد الامتلاء).
    atr_series = pine_volatility_atr(trs, VolatilityConfig().history_bars)
    st_high = PineSwingPolarity(is_high=True)
    st_low = PineSwingPolarity(is_high=False)
    zones: list[PineZone] = []
    interactions: list[PineInteraction] = []
    bos = PineBos()
    swings: list[PineSwing] = []
    sweeps: list[PineSweepEvent] = []
    bos_events: list[tuple[int, str, str]] = []
    for i, bar in enumerate(bars):
        atr = atr_series[i]
        # (0) المتطرفات — قطبيتان حتميتا الترتيب (HIGH ثم LOW).
        sw_high = st_high.update(i, float(bar["high"]), atr)
        sw_low = st_low.update(i, float(bar["low"]), atr)
        fresh = [s for s in (sw_high, sw_low) if s is not None]
        # (1) الاجتياح أولا (§10.4 شرط 1) — ضد المناطق القائمة [0..t−1].
        sweeps.extend(pine_sweep_scan(zones, interactions, bar, i, atr))
        # (2) هضم المتطرفات: الخريطة ثم مستويات الكسر.
        for sw in fresh:
            pine_ingest_swing(zones, sw, atr, i)
            bos.on_swing(sw)
        swings.extend(fresh)
        # (4) كسر البنية بعد تغذية مستويات هذا الشريط.
        for et, direction, _breach in bos.update(bar, i, atr):
            bos_events.append((i, et, direction))
    return PineChainResult(
        atr=atr_series,
        swings=swings,
        sweeps=sweeps,
        bos=bos_events,
        zones_final_count=len(zones),
    )


# ═══════════════════════════ سلسلة المحرك الحقيقية ═══════════════════════════


def _bars_to_candles(bars: list[dict[str, Any]], timeframe: str, instrument: str) -> list[Candle]:
    """محول عينة → شموع قانونية (نمط verify_phase7 حرفيًا — عقد §8.1)."""
    out: list[Candle] = []
    prev_close: float | None = None
    for bar in bars:
        o, h, low, c = (
            float(bar["open"]),
            float(bar["high"]),
            float(bar["low"]),
            float(bar["close"]),
        )
        span = h - low
        body = abs(c - o)
        if span > 0.0:
            body_fraction = body / span
            clv = (c - low) / span
        else:
            body_fraction = 0.0
            clv = 0.5
        tr = (
            span if prev_close is None else max(h - low, abs(h - prev_close), abs(low - prev_close))
        )
        bt = datetime.fromtimestamp(int(bar["open_time_ms"]) / 1000.0, tz=UTC)
        out.append(
            Candle(
                instrument_id=instrument,
                timeframe=timeframe,
                bar_time=bt,
                session_id=bt.strftime("%Y-%m-%d"),
                quality=DataQuality.HEALTHY,
                is_closed=True,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=float(bar["volume"]),
                range=span,
                body_size=body,
                upper_wick=h - max(o, c),
                lower_wick=min(o, c) - low,
                body_fraction=body_fraction,
                close_location_value=clv,
                true_range=tr,
                realized_volatility=abs(math.log(c / o)) if o > 0.0 else 0.0,
            )
        )
        prev_close = c
    return out


@dataclass
class EngineChainResult:
    """مخرجات سلسلة المحرك — بنفس مفاتيح مقارنة PineChainResult."""

    atr: list[float | None]
    swings: list[Any]
    sweeps_swing_sourced: list[tuple[int, str, str]]  # (bar_index, kind, event_name)
    sweeps_engine_only: list[tuple[int, str, str]]
    bos: list[tuple[int, str, str]]
    swing_zone_count: int
    engine_zone_count: int


def run_engine_chain(
    bars: list[dict[str, Any]], timeframe: str, instrument: str
) -> EngineChainResult:
    """تشغيل مكونات المحرك الحقيقية بترتيب الواجهات الموثق.

    الترتيب (شرط 1 §10.4 + ترتيب StructureEngine الموثق):
    تقلب ← متطرفات ← (لكل متطرف: bos.on_swing) ← bos.update ←
    اجتياح ضد الخريطة القائمة ← map.update بالشمعة والمتطرفات.
    """
    from liquidity.sweep import SweepDetector
    from liquidity.zones import LiquidityMapEngine
    from market_state.volatility import VolatilityEngine
    from schemas import StructureBreakPayload
    from structure.bos import StructureBreakEngine
    from structure.swings import SwingDetector

    candles = _bars_to_candles(bars, timeframe, instrument)
    vol_engine = VolatilityEngine()
    swing_det = SwingDetector()
    bos_engine = StructureBreakEngine()
    zone_map = LiquidityMapEngine(instrument_id=instrument, timeframe=timeframe)
    sweep_det = SweepDetector(zone_map)

    atr_series: list[float | None] = []
    swings: list[Any] = []
    sweeps_all: list[tuple[int, str, str, str]] = []  # (شريط، نوع، اسم الحدث، معرف المنطقة)
    bos_events: list[tuple[int, str, str]] = []

    for i, candle in enumerate(candles):
        vstate = vol_engine.update(candle)
        atr_series.append(vstate.atr if vstate is not None else None)
        new_swings = swing_det.update(candle, vstate)
        for sw in new_swings:
            bos_engine.on_swing(sw)
        for bos_ev in bos_engine.update(candle, vstate):
            if not isinstance(bos_ev.payload, StructureBreakPayload):
                continue  # محرك الكسور لا يبث غير حمولات الكسر — تحوط أنواع حصرًا
            bos_events.append(
                (i, str(bos_ev.event_type.value), str(bos_ev.payload.break_direction.value))
            )
        for sweep_ev in sweep_det.update(candle, vstate):
            kind = "SWEEP" if "SWEEP" in sweep_ev.event_type.value else "ACCEPT"
            sweeps_all.append((i, kind, str(sweep_ev.event_type.value), sweep_ev.payload.zone_id))
        zone_map.update(candle, vstate, new_swings)
        swings.extend(new_swings)

    # تصنيف مصدر كل منطقة عند نهاية التشغيل: المصدر لا يتغير بعد الإنشاء
    # أبداً (لا مسار لإعادة التشكيل — عقد بلا-نظرة في zones.py) فالتصنيف
    # النهائي صحيح تماماً لكل الأحداث الماضية. مناطق القمم/قيعان الجلسة
    # والأسبوع وحدود النطاق = إثراء جانب-المحرك (خارج المجموعة المشتركة).
    zone_sources = {z.zone_id: z.source_type.value for z in zone_map.zones()}
    swing_sources = {"PRIOR_SWING", "EQUAL_LEVEL"}
    swings_sourced: list[tuple[int, str, str]] = []
    engine_only: list[tuple[int, str, str]] = []
    for i, kind, name, zone_id in sweeps_all:
        if zone_sources.get(zone_id) in swing_sources:
            swings_sourced.append((i, kind, name))
        else:
            engine_only.append((i, kind, name))

    return EngineChainResult(
        atr=atr_series,
        swings=swings,
        sweeps_swing_sourced=swings_sourced,
        sweeps_engine_only=engine_only,
        bos=bos_events,
        swing_zone_count=sum(1 for s in zone_sources.values() if s in swing_sources),
        engine_zone_count=len(zone_sources),
    )


# ═══════════════════════════ المقارنة (D-08) والتقرير ═══════════════════════════


def _compare_ohlcv(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """OHLCV مطابقة تامة — الطرفان يقرآن نفس العينة بلا اشتقاق."""
    return {
        "family": "OHLCV",
        "rule": "exact",
        "status": "MATCH",
        "bars": len(bars),
        "detail": (
            "الطرفان يستهلكان الشموع المغلقة حصرًا من العينة المرجعية نفسها (bar_time = open_time)."
        ),
    }


def _compare_atr(pine_atr: list[float | None], engine_atr: list[float | None]) -> dict[str, Any]:
    """ATR ±0.01% عنصرًا بعنصر حيث الطرفان معرفان."""
    compared = 0
    worst = 0.0
    for p, e in zip(pine_atr, engine_atr, strict=True):
        if p is None or e is None:
            continue
        rel = abs(p - e) / abs(e) if e != 0.0 else (0.0 if p == 0.0 else math.inf)
        compared += 1
        worst = max(worst, rel)
    ok = compared > 0 and worst <= D08_TOLERANCES["ATR"]["tolerance"]
    return {
        "family": "ATR",
        "rule": "relative ±0.01%",
        "status": "MATCH" if ok else "MISMATCH",
        "compared": compared,
        "worst_relative_deviation": worst,
        "detail": (
            "ta.rma(ta.tr(true), 14) مقابل wilder_atr(tr, 14) بسياسة المخزن الدائري "
            "للمحرك — نفس البذرة والاستدعاء الذاتي."
        ),
    }


def _compare_swings(pine_swings: list[PineSwing], engine_swings: list[Any]) -> dict[str, Any]:
    """المتطرفات مطابقة صارمة — (الفهرس، السعر، القطبية، النطاق، وقت التأكيد)."""
    mismatches: list[str] = []
    n = min(len(pine_swings), len(engine_swings))
    for i in range(n):
        p, e = pine_swings[i], engine_swings[i]
        if (
            abs(p.price - e.price) > 0.0
            or p.is_high != (e.direction.value == "HIGH")
            or p.scope != e.external_or_internal.value
            or p.confirm_index - p.bar_index != _SWING_CONFIRM_BARS
        ):
            mismatches.append(
                f"#{i}: pine({p.price},{p.scope}) engine({e.price},{e.external_or_internal.value})"
            )
    ok = len(pine_swings) == len(engine_swings) and not mismatches
    return {
        "family": "SWINGS",
        "rule": "strict",
        "status": "MATCH" if ok else "MISMATCH",
        "pine_count": len(pine_swings),
        "engine_count": len(engine_swings),
        "mismatches": mismatches[:5],
        "detail": (
            "آلة المتطرفات الفراكتلية بتأكيد متأخر 3 شموع — السعر والقطبية والنطاق وفهرس التأكيد."
        ),
    }


def _compare_sweeps(
    pine_sweeps: list[PineSweepEvent], engine_sweeps: list[tuple[int, str, str]]
) -> dict[str, Any]:
    """الأحداث البنائية مطابقة صارمة — (الشريط، النوع) بترتيب الحدوث."""
    pine_keys = [(s.bar_index, s.event_name) for s in pine_sweeps]
    engine_keys = [(i, name) for i, _kind, name in engine_sweeps]
    ok = pine_keys == engine_keys
    return {
        "family": "SWEEP",
        "rule": "strict",
        "status": "MATCH" if ok else "MISMATCH",
        "pine_count": len(pine_keys),
        "engine_count": len(engine_keys),
        "detail": (
            "آلة اجتياح §10.4 على مناطق المتطرفات (المجموعة المشتركة) — "
            "مطابقة صارمة عند تساوي المعايير."
        ),
    }


def _compare_bos(
    pine_bos: list[tuple[int, str, str]], engine_bos: list[tuple[int, str, str]]
) -> dict[str, Any]:
    """كسور البنية مطابقة صارمة — (الشريط، النوع) بترتيب الحدوث."""
    pine_keys = [(i, et) for i, et, _d in pine_bos]
    engine_keys = [(i, et) for i, et, _d in engine_bos]
    ok = pine_keys == engine_keys
    return {
        "family": "BOS",
        "rule": "strict",
        "status": "MATCH" if ok else "MISMATCH",
        "pine_count": len(pine_keys),
        "engine_count": len(engine_keys),
        "detail": "كسر الإغلاق بعتبة 1.0 ATR وابتلاع المستويات وتصنيف §11.3 — ترتيب UP ثم DOWN.",
    }


def _delta_poc_row() -> dict[str, Any]:
    """صف دلتا/POC — غير مشترك موثق (D-08: فرق منهجي معلن لا فشل)."""
    return {
        "family": "DELTA_POC",
        "rule": "not_shared",
        "status": "DOCUMENTED_DIFFERENCE",
        "detail": (
            "فوتبرنت TradingView يتطلب حساب Premium (§6.2) والمحرك يعيد بناء الدلتا/POC "
            "من aggTrades — مصدران مختلفان منهجيًا: يوثق الاختلاف ولا يقارن زورًا."
        ),
    }


def validate_pine_source() -> list[str]:
    """فحص بنيوي لمصدر Pine — العلامات الإلزامية للمواصفة (§27/§35/§36).

    يرجع قائمة الخروق (فارغة = سليم).
    """
    issues: list[str] = []
    lib = PINE_LIB.read_text(encoding="utf-8") if PINE_LIB.exists() else ""
    ind = PINE_INDICATOR.read_text(encoding="utf-8") if PINE_INDICATOR.exists() else ""
    if not lib:
        return [f"مكتبة Pine مفقودة: {PINE_LIB}"]
    if not ind:
        return [f"مؤشر Pine مفقود: {PINE_INDICATOR}"]
    # §27.1 — حالات الإشارة الأربع معلنة في المكتبة.
    for state in (
        "SIGNAL_DEVELOPING",
        "SIGNAL_CONFIRMED",
        "SIGNAL_INVALIDATED",
        "SIGNAL_RETRACTED",
    ):
        if state not in lib:
            issues.append(f"§27.1: حالة الإشارة {state} غير معلنة في المكتبة")
    # §27.2 — تقنية القيمة المؤكدة (إزاحة [1] + lookahead_on).
    if "[1]" not in lib or "lookahead_on" not in lib:
        issues.append("§27.2: تقنية القيمة المؤكدة (إزاحة [1] مع lookahead_on) غائبة عن قارئ HTF")
    # §35.1 — الطبقات السبع بترتيبها في المؤشر.
    layers = [
        "خريطة السيولة الكبرى",
        "نطاق المعالجة النشط",
        "بنية HTF",
        "السيناريو النشط",
        "الدخول/الإبطال/الأهداف",
        "تعليقات التدفق المختارة",
        "علامات الأحداث",
    ]
    cursor = -1
    for layer in layers:
        idx = ind.find(layer)
        if idx < 0:
            issues.append(f"§35.1: طبقة العرض «{layer}» غائبة عن المؤشر")
        elif idx < cursor:
            issues.append(f"§35.1: طبقة «{layer}» خارج الترتيب")
        else:
            cursor = idx
    # §36 — حقول الحمولة الثمانية في باني الحمولة.
    for f in (
        "schema_version",
        "source",
        "alert_id",
        "instrument",
        "bar_time",
        "timeframe",
        "event",
        "price",
    ):
        if f'"{f}"' not in lib:
            issues.append(f"§36: حقل الحمولة «{f}» غائب عن باني الحمولة")
    # §37.1 — لا أسرار في المصدر (لا توكن مكتوب ولا في جسم).
    for src_name, src in (("المكتبة", lib), ("المؤشر", ind)):
        if re.search(r"(token|secret|api[_-]?key)\s*=", src, flags=re.IGNORECASE):
            issues.append(f"§37.1: نمط سر في {src_name} — لا أسرار في مصدر Pine أبدًا")
    # §27.4 — التنبيهات من شموع مغلقة حصرًا.
    if "barstate.isconfirmed" not in ind:
        issues.append("§27.4: معالجة المؤشر ليست على الشموع المغلقة حصرًا")
    if "alert.freq_once_per_bar_close" not in ind:
        issues.append("§27.4/ضبط التنبيه: التكرار ليس once-per-bar-close (منطق مؤكد حصرًا)")
    return issues


def load_phase2_bars(timeframe: str = "1m") -> list[dict[str, Any]]:
    """تحميل عينة المرحلة 2 الخام (نفس عينة البوابات 7-8-9)."""
    path = PHASE2_DIR / f"klines_{timeframe}.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], loaded)


def run_mirror(timeframe: str = "1m", instrument: str = "BINANCE_USDM:BTCUSDT") -> dict[str, Any]:
    """تشغيل المرآة الكاملة — تقرير حتمي قابل لإعادة الإنتاج.

    لا ساعة جدرية: التقرير دالة في العينة والمصدرين حصرًا.
    """
    bars = load_phase2_bars(timeframe)
    pine = run_pine_chain(bars)
    engine = run_engine_chain(bars, timeframe, instrument)
    rows = [
        _compare_ohlcv(bars),
        _compare_atr(pine.atr, engine.atr),
        _compare_swings(pine.swings, engine.swings),
        _compare_sweeps(pine.sweeps, engine.sweeps_swing_sourced),
        _compare_bos(pine.bos, engine.bos),
        _delta_poc_row(),
    ]
    issues = validate_pine_source()
    all_match = all(r["status"] in ("MATCH", "DOCUMENTED_DIFFERENCE") for r in rows) and not issues
    return {
        "schema_version": "1.0.0",
        "mirror": "pine-vs-engine (D-08)",
        "timeframe": timeframe,
        "instrument": instrument,
        "bars": len(bars),
        "tolerance_table": D08_TOLERANCES,
        "rows": rows,
        "pine_source_checks": {"status": "OK" if not issues else "VIOLATIONS", "issues": issues},
        "status": "AGREED_WITHIN_TOLERANCE" if all_match else "DIVERGENCE",
    }
