"""اختبارات وحدة المرآة D-08 — المنافذ والفحص البنيوي (بوابة 10).

تختبر العقود الصرفة للمنافذ (الحتمية والقطبية والمعرفات الفريدة) —
المقارنة الكاملة مقابل المحرك فوق العينة المرجعية تعمل في بوابة
المرحلة 10 (verify_phase10) وفي أمر ‎engine-replay mirror‎.
"""

from __future__ import annotations

import math

import pytest
from _phase2_loader import load_phase2_bars
from engine_replay.mirror import (
    D08_TOLERANCES,
    PineSwing,
    PineSwingPolarity,
    PineZone,
    pine_alert_payload,
    pine_atr_wilder,
    pine_ingest_swing,
    pine_sweep_scan,
    pine_true_range,
    pine_volatility_atr,
    run_pine_chain,
    validate_pine_source,
)

# ───────────────────────── ATR وايلدر (§16) ─────────────────────────


class TestPineAtrWilder:
    def test_seed_is_sma_then_recursive(self) -> None:
        """البذرة SMA عند period−1 ثم الاستدعاء الذاتي — حرفيًا."""
        trs = [10.0] * 5 + [20.0] * 5
        out = pine_atr_wilder(trs, 4)
        assert out[0] is None and out[2] is None
        assert out[3] == pytest.approx(10.0)  # بذرة SMA(10,10,10,10)
        assert out[4] == pytest.approx(10.0)  # (10×3 + 10)/4 — ما زال TR=10
        assert out[5] == pytest.approx((10.0 * 3 + 20.0) / 4)  # أول 20
        prev = out[5]
        assert prev is not None
        assert out[6] == pytest.approx((prev * 3 + 20.0) / 4)

    def test_period_one_is_identity(self) -> None:
        trs = [3.5, 7.0, 2.25]
        assert pine_atr_wilder(trs, 1) == trs

    def test_true_range_first_bar_is_span(self) -> None:
        bars = [{"high": 12.0, "low": 7.5, "close": 9.0}, {"high": 13.0, "low": 8.0, "close": 12.5}]
        trs = pine_true_range(bars)
        assert trs[0] == pytest.approx(4.5)
        assert trs[1] == pytest.approx(max(5.0, abs(13.0 - 9.0), abs(8.0 - 9.0)))

    def test_bounded_atr_matches_full_window_recompute(self) -> None:
        """سياسة المخزن الدائري: بعد الامتلاء يساوي إعادة الحساب على النافذة."""
        trs = [float(i % 17) + 1.0 for i in range(60)]
        bounded = pine_volatility_atr(trs, history_bars=30)
        window = trs[-30:]
        series = pine_atr_wilder(window, 14)
        assert bounded[-1] == pytest.approx(series[-1], rel=1e-12)


# ───────────────────────── آلة المتطرفات (§11.1) ─────────────────────────


class TestPineSwingPolarity:
    def test_entry_edge_and_confirmation_delay(self) -> None:
        st = PineSwingPolarity(is_high=True)
        highs = [10.0, 11.0, 10.5, 10.4, 10.3]
        results = [st.update(i, h, 5.0) for i, h in enumerate(highs)]
        # الترشيح عند الشمعة 1 (11.0 > 10.0) والتأكيد بعد 3 شموع (الشمعة 4).
        assert all(r is None for r in results[:4])
        swing = results[4]
        assert swing is not None
        assert swing.price == 11.0
        assert swing.bar_index == 1
        assert swing.confirm_index == 4
        assert swing.scope == "EXTERNAL"  # أول متطرف يؤسس الإطار الخارجي

    def test_invalidation_by_strictly_higher_high(self) -> None:
        st = PineSwingPolarity(is_high=True)
        st.update(0, 10.0, 5.0)  # prev=10 — لا ترشيح (أول شمعة)
        st.update(1, 11.0, 5.0)  # ترشيح 11.0
        swing = st.update(2, 11.5, 5.0)  # إبطال قطعي (11.5 > 11.0) — مرشح جديد
        assert swing is None
        # المساواة لا تُبطل: 11.5 == 11.5 عدّ تأكيد لا إبطال.
        assert st.update(3, 11.5, 5.0) is None
        assert st.cand_price == 11.5

    def test_strength_tanh_with_declared_zero_and_saturation(self) -> None:
        st = PineSwingPolarity(is_high=True)
        st.update(0, 10.0, None)  # بلا ATR
        st.update(1, 12.0, None)  # ترشيح 12.0
        st.update(2, 11.9, None)  # تأكيد 1
        st.update(3, 11.8, None)  # تأكيد 2
        swing = st.update(4, 11.7, None)  # تأكيد 3 — يبث
        assert swing is not None and swing.strength == 0.0  # غياب ATR ⇒ صفر معلن

        st2 = PineSwingPolarity(is_high=True)
        st2.update(0, 10.0, 5.0)
        st2.update(1, 12.0, 5.0)  # ترشيح 12.0
        st2.update(2, 11.5, 5.0)  # تأكيد 1 — وصيف 11.5
        st2.update(3, 11.5, 5.0)  # تأكيد 2
        swing2 = st2.update(4, 11.5, 5.0)  # تأكيد 3 — يبث (وصيف 11.5)
        assert swing2 is not None
        assert swing2.strength == pytest.approx(math.tanh(0.5 / 5.0))


# ───────────────────────── المناطق والاجتياح (§10) ─────────────────────────


def _swing(price: float, *, is_high: bool, bar_index: int = 3) -> PineSwing:
    """متطرف اختباري جاهز — القيم الافتراضية موثقة في كل اختبار يستعملها."""
    from engine_replay.mirror import PineSwing

    return PineSwing(
        price=price,
        is_high=is_high,
        scope="EXTERNAL",
        strength=0.5,
        bar_index=bar_index,
        confirm_index=bar_index + 3,
    )


class TestPineZonesAndSweep:
    def test_swing_high_forms_buy_side_zone_above(self) -> None:
        """قطبية المحرك: القمة ⇒ BUY_SIDE (سيولة فوق السعر)."""
        zones: list[PineZone] = []

        sw = _swing(100.0, is_high=True)
        pine_ingest_swing(zones, sw, atr=5.0, bar_index=6)
        assert zones and zones[0].is_buy_side is True
        assert zones[0].price_low == zones[0].price_high == 100.0
        assert zones[0].source == "PRIOR_SWING"

    def test_zone_ids_unique_for_same_bar_polarities(self) -> None:
        """معرف تسلسلي فريد — قمة وقاع بنفس الشمعة لا يتصادمان."""

        zones: list[PineZone] = []
        hi = _swing(100.0, is_high=True)
        lo = _swing(90.0, is_high=False)
        pine_ingest_swing(zones, hi, atr=5.0, bar_index=6)
        pine_ingest_swing(zones, lo, atr=5.0, bar_index=6)
        assert len(zones) == 2
        assert zones[0].origin_index != zones[1].origin_index

    def test_equal_level_merge_within_tolerance(self) -> None:

        zones: list[PineZone] = []
        a = _swing(100.0, is_high=True)
        b = _swing(101.0, is_high=True, bar_index=8)
        pine_ingest_swing(zones, a, atr=8.0, bar_index=6)  # تسامح 0.25×8=2
        pine_ingest_swing(zones, b, atr=8.0, bar_index=11)
        assert len(zones) == 1
        assert zones[0].source == "EQUAL_LEVEL"
        assert zones[0].price_low == 100.0 and zones[0].price_high == 101.0

    def test_sweep_event_name_follows_engine_convention(self) -> None:
        """اجتياح منطقة BUY_SIDE (عند القمم) ثم استرجاع ⇒ LIQUIDITY_SWEEP_HIGH."""

        zones: list[PineZone] = []
        sw = _swing(100.0, is_high=True, bar_index=0)
        pine_ingest_swing(zones, sw, atr=5.0, bar_index=3)

        def bar(h: float, low: float, c: float) -> dict[str, float]:
            return {"high": h, "low": low, "close": c}

        # لمس ونافذة وتغلغل كافٍ ثم استرجاع.
        pine_sweep_scan(zones, [], bar(103.0, 99.0, 101.0), 4, 5.0)  # لمس + تغلغل 3
        ev = pine_sweep_scan(zones, [], bar(105.0, 100.5, 102.0), 5, 5.0)  # تغلغل 5 + إغلاق فوق
        assert isinstance(ev, list) and len(ev) == 0
        ev2 = pine_sweep_scan(zones, [], bar(106.0, 99.0, 99.5), 6, 5.0)  # استرجاع (إغلاق دون 100)
        assert isinstance(ev2, list) and len(ev2) == 1
        assert ev2[0].event_name == "LIQUIDITY_SWEEP_HIGH"
        assert zones[0].state == "SWEPT"


# ───────────────────────── حمولة التنبيه (§36 + D-07) ─────────────────────────


class TestAlertPayload:
    def test_payload_has_exactly_eight_fields_and_no_secret(self) -> None:
        payload = pine_alert_payload(
            "LIQUIDITY_SWEEP_LOW",
            instrument="BINANCE:BTCUSDT",
            bar_time_ms=1735689600000,
            timeframe="1",
            price=42000.5,
        )
        assert set(payload) == {
            "schema_version",
            "source",
            "alert_id",
            "instrument",
            "bar_time_ms",
            "timeframe",
            "event",
            "price",
        }
        assert payload["source"] == "tradingview"
        assert "idempotency_key" not in payload  # يشتقه الخادم حصرًا (D-07)
        assert "token" not in str(payload).lower()  # لا أسرار في الجسم (§37.1)
        assert payload["alert_id"] == "BINANCE:BTCUSDT|1|LIQUIDITY_SWEEP_LOW|1735689600000"

    def test_d07_key_deterministic_over_five_raw_fields(self) -> None:
        from engine_api.api.webhook import derive_idempotency_key
        from schemas import TVAlertPayload

        payload = TVAlertPayload.model_validate(
            {
                "schema_version": "1.0.0",
                "source": "tradingview",
                "alert_id": "X|1|CHOCH|100",
                "instrument": "BINANCE:BTCUSDT",
                "bar_time_ms": 1000,
                "timeframe": "1",
                "event": "CHOCH",
                "price": 42.0,
            }
        )
        assert derive_idempotency_key(payload) == derive_idempotency_key(payload)
        other = payload.model_copy(update={"event": "EXTERNAL_BOS"})
        assert derive_idempotency_key(payload) != derive_idempotency_key(other)


# ───────────────────────── فحص مصدر Pine البنيوي ─────────────────────────


class TestValidatePineSource:
    def test_real_sources_pass(self) -> None:
        assert validate_pine_source() == []

    def test_tolerance_table_is_declared_per_family(self) -> None:
        assert D08_TOLERANCES["OHLCV"]["rule"] == "exact"
        assert D08_TOLERANCES["ATR"]["tolerance"] == pytest.approx(0.0001)
        assert D08_TOLERANCES["SWEEP"]["rule"] == "strict"
        assert D08_TOLERANCES["BOS"]["rule"] == "strict"
        assert D08_TOLERANCES["DELTA_POC"]["rule"] == "not_shared"


# ───────────────────────── حتمية سلسلة المنافذ ─────────────────────────


class TestPineChainDeterminism:
    def test_two_runs_identical_over_sample(self) -> None:
        bars = load_phase2_bars("1m")
        first = run_pine_chain(bars)
        second = run_pine_chain(bars)
        assert first.atr == second.atr
        assert [(s.bar_index, s.price, s.scope) for s in first.swings] == [
            (s.bar_index, s.price, s.scope) for s in second.swings
        ]
        assert [(e.bar_index, e.event_name) for e in first.sweeps] == [
            (e.bar_index, e.event_name) for e in second.sweeps
        ]
        assert first.bos == second.bos
