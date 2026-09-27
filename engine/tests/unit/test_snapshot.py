"""اختبارات بنّاء لقطة حالة السوق (مثال §32) — المهمة 2-f.

التغطية:
- البناء من حالات موضعية مصنوعة يدويًا: كل قيم التعدادات الثلاث
  (MarketRegime الثمانية، HTFBias الخمسة، DataQuality التسعة).
- الجودة الكسولة: بيانات تقلب غير كافية ⇒ volatility_percentile=0.0
  واللقطة لا تسقط (سياسة مرحلية موثقة).
- تحويل المقياس: كسرة المحرك [0,1] ← نسبة المخطط [0,100] (مثال §32:
  0.624 ← 62.4).
- الحتمية بايت-بايت (بناءان من مدخلات متساوية).
- عقد الجلسة: الصريح يمر بعد تحقق الصيغة والغائب يُشتق من event_time UTC.
- التحقق ضد المخطط المصدَّر: jsonschema.validate على model_dump(mode="json").
- هوية الأداة الحتمية: تثبيت التطابق مع اصطلاح ingestion (uuid5 نفسه).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest
from jsonschema import validate as jsonschema_validate
from market_state.htf_bias import HtfBiasState
from market_state.regime import RegimeState
from market_state.snapshot import SnapshotInputs, build_snapshot, snapshot_session_id
from market_state.store import MarketStateStoreError, snapshot_instrument_uuid
from market_state.volatility import VolatilityState
from pydantic import ValidationError
from schemas import DataQuality, HTFBias, MarketRegime, MarketStateSnapshot
from schemas.export import GENERATED_DIR

# المخطط المصدَّر — مصدر الحقيقة للترميز القانوني (لا يُحرَّر يدويًا)
SCHEMA_PATH = GENERATED_DIR / "MarketStateSnapshot.schema.json"

_T0 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)


def _load_schema() -> dict[str, object]:
    return cast("dict[str, object]", json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _volatility(
    *,
    atr_percentile: float | None = 0.624,
    data_sufficient: bool = True,
) -> VolatilityState:
    """حالة تقلب مصنوعة يدويًا — دافئة افتراضيًا بمئيني 0.624 (§32: 62.4)."""
    return VolatilityState(
        atr=1.25 if data_sufficient else None,
        atr_percentile=atr_percentile if data_sufficient else None,
        realized_vol=0.0011,
        range_expansion_percentile=0.42,
        vol_of_vol=0.12,
        gap_shock=0.05,
        spread_to_range=0.30,
        expected_holding_vol_1h=0.002,
        data_sufficient=data_sufficient,
        bar_time=_T0,
        warmup_bars_remaining=0 if data_sufficient else 40,
    )


def _regime(regime: MarketRegime = MarketRegime.TREND_PULLBACK) -> RegimeState:
    return RegimeState(
        regime=regime,
        pending_regime=None,
        pending_count=0,
        bars_seen=120,
        data_sufficient=True,
        transitions=3,
    )


def _bias(bias: HTFBias = HTFBias.BULLISH) -> HtfBiasState:
    return HtfBiasState(
        bias=bias, pending_bias=None, pending_count=0, bars_seen=60, data_sufficient=True
    )


def _inputs(
    *,
    regime_state: RegimeState | None = None,
    bias_state: HtfBiasState | None = None,
    volatility_state: VolatilityState | None = None,
    data_quality: DataQuality = DataQuality.HEALTHY,
    session_id: str | None = None,
    event_time: datetime = _T0,
) -> SnapshotInputs:
    return SnapshotInputs(
        instrument="binance-usdm-futures:BTCUSDT",
        timeframe="5m",
        event_time=event_time,
        regime_state=regime_state if regime_state is not None else _regime(),
        bias_state=bias_state if bias_state is not None else _bias(),
        volatility_state=volatility_state if volatility_state is not None else _volatility(),
        data_quality=data_quality,
        session_id=session_id,
    )


class TestBuildSnapshot:
    """البناء الأساسي: الحقول السبعة من مدخلاتها مباشرة."""

    def test_warm_snapshot_fields(self) -> None:
        snapshot = build_snapshot(_inputs())
        assert snapshot.instrument == "binance-usdm-futures:BTCUSDT"
        assert snapshot.timeframe == "5m"
        assert snapshot.event_time == _T0
        assert snapshot.regime is MarketRegime.TREND_PULLBACK
        assert snapshot.htf_bias is HTFBias.BULLISH
        assert snapshot.data_quality is DataQuality.HEALTHY

    @pytest.mark.parametrize(
        "fraction,percent",
        [(0.0, 0.0), (0.25, 25.0), (0.5, 50.0), (0.624, 62.4), (1.0, 100.0)],
    )
    def test_volatility_fraction_converted_to_percent(
        self, fraction: float, percent: float
    ) -> None:
        """التحويل [0,1] ← [0,100] — مسؤولية طبقة الدمج (توثيق المحرك)."""
        snapshot = build_snapshot(_inputs(volatility_state=_volatility(atr_percentile=fraction)))
        assert snapshot.volatility_percentile == pytest.approx(percent)

    def test_insufficient_volatility_data_gives_zero(self) -> None:
        """سياسة مرحلية موثقة: غير-الكافي لا يسقط اللقطة — 0.0 صراحةً."""
        snapshot = build_snapshot(_inputs(volatility_state=_volatility(data_sufficient=False)))
        assert snapshot.volatility_percentile == 0.0
        assert snapshot.regime is MarketRegime.TREND_PULLBACK  # بقية الحقول تمر كما هي

    def test_none_atr_percentile_gives_zero(self) -> None:
        """دافئ لكن القيمة منحلة (nan حُوِّلت None) ⇒ 0.0 — لا انفجار ولا غش."""
        state = _volatility(atr_percentile=None)
        assert state.atr_percentile is None
        snapshot = build_snapshot(_inputs(volatility_state=state))
        assert snapshot.volatility_percentile == 0.0

    def test_cold_states_are_legal(self) -> None:
        """قبل الدافئ: UNKNOWN للنظام والانحياز قيمتا تعداد مقررتان."""
        cold = SnapshotInputs(
            instrument="binance-usdm-futures:BTCUSDT",
            timeframe="5m",
            event_time=_T0,
            regime_state=RegimeState(),
            bias_state=HtfBiasState(),
            volatility_state=_volatility(data_sufficient=False),
        )
        snapshot = build_snapshot(cold)
        assert snapshot.regime is MarketRegime.UNKNOWN
        assert snapshot.htf_bias is HTFBias.UNKNOWN
        assert snapshot.volatility_percentile == 0.0

    def test_data_quality_default_is_healthy(self) -> None:
        inputs = _inputs()
        assert inputs.data_quality is DataQuality.HEALTHY

    def test_lazy_quality_passes_untouched(self) -> None:
        """البنّاء يصمت عن الجودة الكسولة: تمر كما وصلت بلا إعادة كتابة."""
        snapshot = build_snapshot(
            _inputs(
                data_quality=DataQuality.GAP_DETECTED,
                volatility_state=_volatility(data_sufficient=False),
            )
        )
        assert snapshot.data_quality is DataQuality.GAP_DETECTED

    def test_event_time_normalized_to_utc(self) -> None:
        """زمن واعٍ بمنطقة غير UTC يُطبَّع إلى UTC (عقد §7.1 في UTCDatetime)."""
        aware = datetime(2026, 9, 27, 5, 0, tzinfo=timezone(timedelta(hours=3)))
        snapshot = build_snapshot(_inputs(event_time=aware))
        assert snapshot.event_time == _T0

    def test_naive_event_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build_snapshot(_inputs(event_time=datetime(2026, 9, 27, 2, 0)))

    def test_snapshot_is_frozen(self) -> None:
        snapshot = build_snapshot(_inputs())
        with pytest.raises(ValidationError):
            snapshot.regime = MarketRegime.COMPRESSION  # type: ignore[misc]

    def test_builds_example_32_payload(self) -> None:
        """مثال §32 حرفيًا: مدخلات المحرك المكافئة تنتج حمولة المثال نفسها."""
        snapshot = MarketStateSnapshot(
            instrument="EXAMPLE",
            timeframe="5m",
            event_time=_T0,
            regime=MarketRegime.TREND_PULLBACK,
            htf_bias=HTFBias.BULLISH,
            volatility_percentile=62.4,
            data_quality=DataQuality.HEALTHY,
        )
        inputs = SnapshotInputs(
            instrument="EXAMPLE",
            timeframe="5m",
            event_time=_T0,
            regime_state=_regime(MarketRegime.TREND_PULLBACK),
            bias_state=_bias(HTFBias.BULLISH),
            volatility_state=_volatility(atr_percentile=0.624),
        )
        assert build_snapshot(inputs) == snapshot
        assert build_snapshot(inputs).model_dump(mode="json") == snapshot.model_dump(mode="json")


class TestDeterminism:
    """نفس المدخلات ⇒ نفس اللقطة بايت-بايت."""

    def test_same_inputs_same_bytes(self) -> None:
        first = build_snapshot(_inputs())
        second = build_snapshot(_inputs())
        assert first.model_dump_json() == second.model_dump_json()

    def test_distinct_equal_states_same_bytes(self) -> None:
        """حالات موضعية منفصلة الكائنات لكن متساوية القيم ⇒ نفس البايتات."""
        first = build_snapshot(_inputs())
        rebuilt = build_snapshot(
            _inputs(
                regime_state=_regime(MarketRegime.TREND_PULLBACK),
                bias_state=_bias(HTFBias.BULLISH),
                volatility_state=_volatility(atr_percentile=0.624),
            )
        )
        assert first.model_dump_json() == rebuilt.model_dump_json()

    def test_different_regime_different_bytes(self) -> None:
        warm = build_snapshot(_inputs(regime_state=_regime(MarketRegime.COMPRESSION)))
        shocked = build_snapshot(_inputs(regime_state=_regime(MarketRegime.VOLATILITY_SHOCK)))
        assert warm.model_dump_json() != shocked.model_dump_json()


@pytest.mark.parametrize("regime", list(MarketRegime))
def test_every_regime_value_passes(regime: MarketRegime) -> None:
    """كل قيم MarketRegime الثمانية قانونية في اللقطة (UNKNOWN قبل الدافئ معها)."""
    snapshot = build_snapshot(_inputs(regime_state=_regime(regime)))
    assert snapshot.regime is regime
    jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())


@pytest.mark.parametrize("bias", list(HTFBias))
def test_every_htf_bias_value_passes(bias: HTFBias) -> None:
    snapshot = build_snapshot(_inputs(bias_state=_bias(bias)))
    assert snapshot.htf_bias is bias
    jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())


@pytest.mark.parametrize("quality", list(DataQuality))
def test_every_data_quality_value_passes(quality: DataQuality) -> None:
    snapshot = build_snapshot(_inputs(data_quality=quality))
    assert snapshot.data_quality is quality
    jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())


class TestExportedSchemaValidation:
    """اللقطة تمر jsonschema.validate ضد المخطط المصدَّر — لا رسالة بلا مخطط."""

    def test_warm_snapshot_validates(self) -> None:
        snapshot = build_snapshot(_inputs())
        jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())

    def test_cold_snapshot_validates(self) -> None:
        snapshot = build_snapshot(_inputs(volatility_state=_volatility(data_sufficient=False)))
        jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())

    @pytest.mark.parametrize("percentile", [0.0, 100.0])
    def test_boundary_percentiles_validate(self, percentile: float) -> None:
        fraction = percentile / 100.0
        snapshot = build_snapshot(_inputs(volatility_state=_volatility(atr_percentile=fraction)))
        assert snapshot.volatility_percentile == percentile
        jsonschema_validate(snapshot.model_dump(mode="json"), _load_schema())

    def test_out_of_range_percentile_rejected_by_model(self) -> None:
        """المخطط يحصر [0,100] — كسرة أعلى من 1.0 تُرفض عند البناء نفسه."""
        with pytest.raises(ValidationError):
            build_snapshot(_inputs(volatility_state=_volatility(atr_percentile=1.5)))


class TestSessionId:
    """عقد الجلسة: صريح يمر بعد تحقق الصيغة، غائب يُشتق من event_time UTC."""

    def test_explicit_session_id_passes_through(self) -> None:
        assert snapshot_session_id(_T0, "2026-09-27") == "2026-09-27"

    def test_none_session_id_derived_from_event_time(self) -> None:
        assert snapshot_session_id(_T0, None) == "2026-09-27"

    def test_derivation_uses_utc_day(self) -> None:
        """يوم UTC حصرًا — 23:30 بتوقيت نيويورك تظل في يوم UTC نفسه."""
        late_ny = datetime(2026, 9, 27, 23, 30, tzinfo=timezone(timedelta(hours=-4)))
        assert snapshot_session_id(late_ny, None) == "2026-09-28"

    @pytest.mark.parametrize(
        "bad", ["27-09-2026", "2026/09/27", "2026-9-7", "2026-09-27T00:00Z", ""]
    )
    def test_invalid_session_id_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="معرف جلسة غير صالح"):
            snapshot_session_id(_T0, bad)

    def test_build_accepts_explicit_session_id(self) -> None:
        """session_id في المدخلات قانوني ولا يمس حقول النموذج السبعة."""
        snapshot = build_snapshot(_inputs(session_id="2026-09-27"))
        assert snapshot.model_dump(mode="json") == build_snapshot(_inputs()).model_dump(mode="json")

    def test_build_rejects_invalid_session_id(self) -> None:
        with pytest.raises(ValueError, match="معرف جلسة غير صالح"):
            build_snapshot(_inputs(session_id="يوم-السبت"))


class TestInstrumentIdentity:
    """هوية الأداة الحتمية — تثبيت التطابق مع اصطلاح ingestion (1.6)."""

    def test_pins_ingestion_convention(self) -> None:
        """uuid5(namespace, "venue:symbol") نفسه — مساواة مباشرة مع ingestion."""
        from ingestion.market_store import instrument_uuid

        assert snapshot_instrument_uuid("binance-usdm-futures:BTCUSDT") == instrument_uuid(
            "binance-usdm-futures", "BTCUSDT"
        )

    def test_deterministic_across_calls(self) -> None:
        first = snapshot_instrument_uuid("binance-usdm-futures:BTCUSDT")
        second = snapshot_instrument_uuid("binance-usdm-futures:BTCUSDT")
        assert first == second

    def test_different_instruments_differ(self) -> None:
        assert snapshot_instrument_uuid("venue:AAA") != snapshot_instrument_uuid("venue:BBB")

    def test_empty_instrument_rejected(self) -> None:
        with pytest.raises(MarketStateStoreError, match="مفتاح أداة فارغ"):
            snapshot_instrument_uuid("")
