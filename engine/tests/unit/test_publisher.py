"""اختبارات ناشر لقطات حالة السوق عبر NATS — المهمة 2-f (عميل وهمي بلا بنية حية).

التغطية:
- تنسيق الموضوع: بادئة، lowercase، تنظيف الرموز غير الكلمة-الحرفية إلى
  شرطات مجمَّعة، قلم الحواف، ورفض الأداة التي تنتج رمزًا فارغًا.
- البث عبر عميل وهمي يجمع (الموضوع، الحمولة، الرؤوس) ويؤكد استدعاء flush.
- الحمولة JSON قانونية تفك back إلى MarketStateSnapshot وتطابق
  model_dump_json بايت-بايت وتمر jsonschema ضد المخطط المصدَّر.
- الرؤوس: event_type (نمط §32) وschema_version من schemas.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import schemas
from engine_worker.publisher import (
    MARKET_STATE_EVENT_TYPE,
    SnapshotPublisher,
    normalize_instrument,
)
from jsonschema import validate as jsonschema_validate
from schemas import MarketStateSnapshot
from schemas.export import GENERATED_DIR

SCHEMA_PATH = GENERATED_DIR / "MarketStateSnapshot.schema.json"

_T0 = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)


class FakeNATSClient:
    """عميل وهمي — يحقق عقد NATSPublishClient الهيكلي ويجمع ما نُشر."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str] | None]] = []
        self.flush_calls = 0

    async def publish(
        self,
        subject: str,
        payload: bytes = b"",
        reply: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.published.append((subject, payload, headers))

    async def flush(self) -> None:
        self.flush_calls += 1


def _snapshot(instrument: str = "EXAMPLE") -> MarketStateSnapshot:
    """لقطة مثال §32 — نفس القيم الحرفية من المثال في الخطة."""
    return MarketStateSnapshot(
        instrument=instrument,
        timeframe="5m",
        event_time=_T0,
        regime=schemas.MarketRegime.TREND_PULLBACK,
        htf_bias=schemas.HTFBias.BULLISH,
        volatility_percentile=62.4,
        data_quality=schemas.DataQuality.HEALTHY,
    )


class TestSubject:
    """تنسيق الموضوع: market.state.{instrument}.{timeframe}.updated."""

    def test_plain_instrument(self) -> None:
        publisher = SnapshotPublisher(FakeNATSClient())
        assert publisher.subject("EXAMPLE", "5m") == "market.state.example.5m.updated"

    def test_lowercases(self) -> None:
        publisher = SnapshotPublisher(FakeNATSClient())
        assert publisher.subject("BTCUSDT", "1h") == "market.state.btcusdt.1h.updated"

    def test_weird_symbols_become_dashes(self) -> None:
        publisher = SnapshotPublisher(FakeNATSClient())
        subject = publisher.subject("binance:BTC/USDT.P!", "5m")
        assert subject == "market.state.binance-btc-usdt-p.5m.updated"

    def test_runs_collapse_to_single_dash(self) -> None:
        assert normalize_instrument("A--B__C  D") == "a-b-c-d"

    def test_edges_trimmed(self) -> None:
        assert normalize_instrument(":BTCUSDT:") == "btcusdt"
        assert normalize_instrument("  EXAMPLE ") == "example"

    def test_digits_kept(self) -> None:
        assert normalize_instrument("TEST-2F") == "test-2f"

    def test_custom_prefix(self) -> None:
        publisher = SnapshotPublisher(FakeNATSClient(), subject_prefix="test")
        assert publisher.subject("EXAMPLE", "5m") == "test.state.example.5m.updated"

    def test_timeframe_kept_literal(self) -> None:
        publisher = SnapshotPublisher(FakeNATSClient())
        assert publisher.subject("EXAMPLE", "15m").endswith(".15m.updated")

    def test_symbol_only_instrument_rejected(self) -> None:
        """أداة تنتج رمزًا فارغًا بعد التنظيف ⇒ رفض صريح لا موضوع مشوه."""
        publisher = SnapshotPublisher(FakeNATSClient())
        with pytest.raises(ValueError, match="رمز موضوع قانونيًا"):
            publisher.subject("###", "5m")


class TestPublish:
    """البث عبر العميل الوهمي — التوجيه والحمولة والرؤوس وflush."""

    async def test_publish_routes_to_derived_subject(self) -> None:
        fake = FakeNATSClient()
        publisher = SnapshotPublisher(fake)
        snapshot = _snapshot()
        await publisher.publish(snapshot)
        assert len(fake.published) == 1
        subject, _, _ = fake.published[0]
        assert subject == publisher.subject(snapshot.instrument, snapshot.timeframe)
        assert subject == "market.state.example.5m.updated"

    async def test_flush_called_once_per_publish(self) -> None:
        fake = FakeNATSClient()
        publisher = SnapshotPublisher(fake)
        await publisher.publish(_snapshot())
        assert fake.flush_calls == 1

    async def test_headers_event_type_pattern_32(self) -> None:
        fake = FakeNATSClient()
        await SnapshotPublisher(fake).publish(_snapshot())
        _, _, headers = fake.published[0]
        assert headers is not None
        assert headers["event_type"] == MARKET_STATE_EVENT_TYPE == "market.state.updated"

    async def test_headers_schema_version_from_schemas(self) -> None:
        fake = FakeNATSClient()
        await SnapshotPublisher(fake).publish(_snapshot())
        _, _, headers = fake.published[0]
        assert headers is not None
        assert headers["schema_version"] == schemas.SCHEMA_VERSION

    async def test_payload_is_model_dump_json_bytes(self) -> None:
        fake = FakeNATSClient()
        snapshot = _snapshot()
        await SnapshotPublisher(fake).publish(snapshot)
        _, payload, _ = fake.published[0]
        assert payload == snapshot.model_dump_json().encode("utf-8")

    async def test_payload_parses_back_to_snapshot(self) -> None:
        fake = FakeNATSClient()
        snapshot = _snapshot()
        await SnapshotPublisher(fake).publish(snapshot)
        _, payload, _ = fake.published[0]
        decoded = MarketStateSnapshot.model_validate_json(payload.decode("utf-8"))
        assert decoded == snapshot

    async def test_payload_is_valid_json_object(self) -> None:
        fake = FakeNATSClient()
        await SnapshotPublisher(fake).publish(_snapshot())
        _, payload, _ = fake.published[0]
        data = json.loads(payload)
        expected_keys = set(_snapshot().model_dump())
        assert isinstance(data, dict) and set(data) == expected_keys

    async def test_payload_validates_against_exported_schema(self) -> None:
        fake = FakeNATSClient()
        await SnapshotPublisher(fake).publish(_snapshot())
        _, payload, _ = fake.published[0]
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema_validate(json.loads(payload), schema)

    async def test_multiple_publishes_accumulate(self) -> None:
        fake = FakeNATSClient()
        publisher = SnapshotPublisher(fake)
        first = _snapshot("venue:A")
        second = _snapshot("venue:B")
        await publisher.publish(first)
        await publisher.publish(second)
        assert len(fake.published) == 2
        assert fake.flush_calls == 2
        assert fake.published[0][0] != fake.published[1][0]
        assert MarketStateSnapshot.model_validate_json(fake.published[1][1]) == second
