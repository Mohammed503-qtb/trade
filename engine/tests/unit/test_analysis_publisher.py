"""اختبارات ناشر أحداث التحليل ومصنع مغلفاتها — المهمة 3-f (عميل وهمي بلا بنية حية).

التغطية:
- ``build_envelope``: معرف ``event_id`` حتمي (نفس الحدث ⇒ نفس المعرف عبر
  الاستدعاءات والمنشئات — روح D-07) ومختلف بين حدثين مختلفين، وكل حقول
  §32 التسعة مكتملة، والحمولة مطابقة لـ``model_dump()`` للنموذج الموثق.
- ``subject_for``: البادئة القانونية market.event وlowercase للنوع وتنظيف
  الأداة بنمط 2-f.
- البث عبر عميل وهمي: الحمولة ``model_dump_json()`` بايت-بايت، والرؤوس
  event_type/schema_version من المصدر المولَّد، وflush مرة لكل نشر.
- المغلف الناتج يمر jsonschema ضد المخطط المصدَّر EventEnvelope.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import schemas
from engine_worker.analysis_publisher import (
    AnalysisEventPublisher,
    build_envelope,
    subject_for,
)
from jsonschema import validate as jsonschema_validate
from schemas import (
    BreakDirection,
    EventEnvelope,
    EventType,
    StructureBreakPayload,
    SwingScope,
)
from schemas.export import GENERATED_DIR
from structure.events import EmittedEvent

SCHEMA_PATH = GENERATED_DIR / "EventEnvelope.schema.json"

_T0 = datetime(2026, 9, 27, 2, 5, tzinfo=UTC)


class FakeNATSClient:
    """عميل وهمي — يحقق عقد NATSPublishClient ويجمع ما نُشر."""

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


def _event(
    event_type: EventType = EventType.INTERNAL_BOS, bar_time: datetime = _T0
) -> EmittedEvent:
    """حدث بنيوي مثالي — حمولة كسر بنية موثقة كاملة."""
    payload = StructureBreakPayload(
        instrument="BINANCE_USDM:BTCUSDT",
        timeframe="1m",
        bar_time=bar_time,
        swing_id="sw-h-test",
        swing_scope=SwingScope.INTERNAL,
        break_direction=BreakDirection.UP,
        breach_distance_atr=1.4,
        closing_acceptance=0.8,
        follow_through=0.0,
        choch_prior_direction=None,
    )
    if event_type is EventType.FVG_BULLISH:
        payload = schemas.FvgEventPayload(  # type: ignore[assignment]
            instrument="BINANCE_USDM:BTCUSDT",
            timeframe="1m",
            bar_time=bar_time,
            direction=schemas.FvgDirection.BULLISH,
            gap_low=100.0,
            gap_high=102.0,
            size_atr=1.0,
            state=schemas.FvgState.CREATED,
        )
    return EmittedEvent(event_type=event_type, event_time=bar_time, payload=payload)


# ═══════════ مصنع المغلف — الحتمية والاكتمال ═══════════


class TestBuildEnvelope:
    """event_id حتمي وكل حقول §32 مكتملة."""

    def test_event_id_deterministic_across_calls(self) -> None:
        """نفس الحدث ⇒ نفس المعرف عبر الاستدعاءات — شرط الإعادة (روح D-07)."""
        event = _event()
        a = build_envelope(
            event, "BINANCE_USDM:BTCUSDT", source="s", trace_id="t", receive_time=_T0
        )
        b = build_envelope(
            _event(), "BINANCE_USDM:BTCUSDT", source="s", trace_id="t", receive_time=_T0
        )
        assert a.event_id == b.event_id

    def test_event_id_differs_across_events(self) -> None:
        """حدثان مختلفان (نوع/زمن) ⇒ معرفان مختلفان."""
        a = build_envelope(
            _event(), "BINANCE_USDM:BTCUSDT", source="s", trace_id="t", receive_time=_T0
        )
        b = build_envelope(
            _event(EventType.INTERNAL_BOS, datetime(2026, 9, 27, 2, 6, tzinfo=UTC)),
            "BINANCE_USDM:BTCUSDT",
            source="s",
            trace_id="t",
            receive_time=_T0,
        )
        assert a.event_id != b.event_id

    def test_all_nine_envelope_fields_complete(self) -> None:
        envelope = build_envelope(
            _event(),
            "BINANCE_USDM:BTCUSDT",
            source="engine.test",
            trace_id="trace-1",
            receive_time=_T0,
            correlation_id="corr-9",
        )
        assert isinstance(envelope, EventEnvelope)
        assert envelope.schema_version == schemas.SCHEMA_VERSION
        assert envelope.event_type is EventType.INTERNAL_BOS
        assert envelope.event_time == _T0
        assert envelope.receive_time == _T0
        assert envelope.source == "engine.test"
        assert envelope.trace_id == "trace-1"
        assert envelope.correlation_id == "corr-9"
        assert envelope.payload == _event().payload.model_dump()

    def test_envelope_passes_exported_schema(self) -> None:
        """المغلف الناتج يمر مخطط EventEnvelope المصدَّر (دورة JSON كاملة)."""
        envelope = build_envelope(
            _event(), "BINANCE_USDM:BTCUSDT", source="s", trace_id="t", receive_time=_T0
        )
        jsonschema_validate(
            json.loads(envelope.model_dump_json()), json.loads(SCHEMA_PATH.read_text())
        )


# ═══════════ الموضوع والناشر ═══════════


class TestSubjectAndPublisher:
    """الموضوع القانوني والبث بالعميل الوهمي."""

    def test_subject_format(self) -> None:
        """‏market.event.{instrument}.{timeframe}.{type-lowercase} حرفيًا."""
        assert (
            subject_for(EventType.INTERNAL_BOS, "BINANCE_USDM:BTCUSDT", "1m")
            == "market.event.binance-usdm-btcusdt.1m.internal_bos"
        )

    def test_publish_payload_bytes_and_headers(self) -> None:
        """الحمولة model_dump_json بايت-بايت والرؤوس §32 وflush مرة."""
        client = FakeNATSClient()
        publisher = AnalysisEventPublisher(client)
        envelope = build_envelope(
            _event(), "BINANCE_USDM:BTCUSDT", source="s", trace_id="t", receive_time=_T0
        )
        import asyncio

        asyncio.run(publisher.publish(envelope))
        ((subject, payload, headers),) = client.published
        assert subject == "market.event.binance-usdm-btcusdt.1m.internal_bos"
        assert payload == envelope.model_dump_json().encode("utf-8")
        assert headers == {
            "schema_version": schemas.SCHEMA_VERSION,
            "event_type": "INTERNAL_BOS",
        }
        assert client.flush_calls == 1

    def test_publish_fvg_subject_uses_type_lowercase(self) -> None:
        """النمطي (فجوة) يبث على موضوعه النمطي بالنوع lowercase."""
        client = FakeNATSClient()
        publisher = AnalysisEventPublisher(client)
        envelope = build_envelope(
            _event(EventType.FVG_BULLISH),
            "BINANCE_USDM:BTCUSDT",
            source="s",
            trace_id="t",
            receive_time=_T0,
        )
        import asyncio

        asyncio.run(publisher.publish(envelope))
        ((subject, _, headers),) = client.published
        assert subject.endswith(".fvg_bullish")
        assert headers is not None and headers["event_type"] == "FVG_BULLISH"


# ═══════════ عقود صاخبة ═══════════


class TestNoisyValidation:
    """الرفض الصاخب عند المصدر."""

    def test_receive_time_is_mandatory(self) -> None:
        """المصنع لا يخترع طابع استقبال — إلزامي صريح من المستدعي."""
        event = _event()
        with pytest.raises(TypeError):
            build_envelope(  # type: ignore[call-arg]
                event, "BINANCE_USDM:BTCUSDT", source="s", trace_id="t"
            )
