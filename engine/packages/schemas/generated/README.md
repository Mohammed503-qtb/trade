# المخططات المُصدَّرة — حزمة schemas

> هذا الملف مولّد آليًا بواسطة `python -m schemas.export write` — **لا تحرّره يدويًا أبدًا**.
> حرس الجودة: `python -m schemas.export check` يجب أن يبقى أخضر في كل بوابة (لا رسالة بلا مخطط مُصدَّر).

- إصدار المخططات: `1.0.0`
- عدد النماذج الجذرية: 15

| النموذج | الملف | الوحدة | فقرة الخطة |
|---|---|---|---|
| `EventEnvelope` | `EventEnvelope.schema.json` | `schemas.envelope` | §32 |
| `TradeEvent` | `TradeEvent.schema.json` | `schemas.market` | §7.1 |
| `Candle` | `Candle.schema.json` | `schemas.market` | §8.1 |
| `FootprintBar` | `FootprintBar.schema.json` | `schemas.market` | §8.2 + §12.7 |
| `MarketStateSnapshot` | `MarketStateSnapshot.schema.json` | `schemas.market` | §32 (المثال) |
| `EvidenceRecord` | `EvidenceRecord.schema.json` | `schemas.evidence` | §19.1 |
| `PriceZone` | `PriceZone.schema.json` | `schemas.scenario` | §18.1 (entry_zone) |
| `TriggerDefinition` | `TriggerDefinition.schema.json` | `schemas.scenario` | §18.1 + §18.4 |
| `InvalidationRule` | `InvalidationRule.schema.json` | `schemas.scenario` | §18.5 + §23.4 |
| `TargetZone` | `TargetZone.schema.json` | `schemas.scenario` | §10.5 |
| `Scenario` | `Scenario.schema.json` | `schemas.scenario` | §18.1 |
| `OrderIntent` | `OrderIntent.schema.json` | `schemas.execution` | §24.1 |
| `SlippageRecord` | `SlippageRecord.schema.json` | `schemas.execution` | §24.4 |
| `LatencyRecord` | `LatencyRecord.schema.json` | `schemas.execution` | §24.5 |
| `ExperienceRecord` | `ExperienceRecord.schema.json` | `schemas.learning` | §29.1 |
