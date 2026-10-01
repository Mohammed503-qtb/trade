# المخططات المُصدَّرة — حزمة schemas

> هذا الملف مولّد آليًا بواسطة `python -m schemas.export write` — **لا تحرّره يدويًا أبدًا**.
> حرس الجودة: `python -m schemas.export check` يجب أن يبقى أخضر في كل بوابة (لا رسالة بلا مخطط مُصدَّر).

- إصدار المخططات: `1.0.0`
- عدد النماذج الجذرية: 47

| النموذج | الملف | الوحدة | فقرة الخطة |
|---|---|---|---|
| `EventEnvelope` | `EventEnvelope.schema.json` | `schemas.envelope` | §32 |
| `TradeEvent` | `TradeEvent.schema.json` | `schemas.market` | §7.1 |
| `Candle` | `Candle.schema.json` | `schemas.market` | §8.1 |
| `FootprintBar` | `FootprintBar.schema.json` | `schemas.market` | §8.2 + §12.7 |
| `MarketStateSnapshot` | `MarketStateSnapshot.schema.json` | `schemas.market` | §32 (المثال) |
| `LiquidityZone` | `LiquidityZone.schema.json` | `schemas.liquidity` | §10.2 |
| `SweepEventPayload` | `SweepEventPayload.schema.json` | `schemas.liquidity` | §10.4 + §20 |
| `BreakAcceptEventPayload` | `BreakAcceptEventPayload.schema.json` | `schemas.liquidity` | §10.4 + §20 |
| `Swing` | `Swing.schema.json` | `schemas.structure` | §11.1 |
| `StructureBreakPayload` | `StructureBreakPayload.schema.json` | `schemas.structure` | §11.2-3 + §20 |
| `DisplacementEventPayload` | `DisplacementEventPayload.schema.json` | `schemas.structure` | §11.4 + §20 |
| `FvgEventPayload` | `FvgEventPayload.schema.json` | `schemas.structure` | §11.5 + §20 |
| `OrderBlockEventPayload` | `OrderBlockEventPayload.schema.json` | `schemas.structure` | §11.6 + §20 |
| `PremiumDiscountEventPayload` | `PremiumDiscountEventPayload.schema.json` | `schemas.structure` | §11.7 + §20 |
| `AbsorptionConditions` | `AbsorptionConditions.schema.json` | `schemas.orderflow` | §12.3 |
| `AbsorptionEventPayload` | `AbsorptionEventPayload.schema.json` | `schemas.orderflow` | §12.3 + §20 |
| `FlowContinuationEventPayload` | `FlowContinuationEventPayload.schema.json` | `schemas.orderflow` | §12.2 + §20 |
| `ExhaustionEventPayload` | `ExhaustionEventPayload.schema.json` | `schemas.orderflow` | §12.4 + §20 |
| `ImbalanceClusterEventPayload` | `ImbalanceClusterEventPayload.schema.json` | `schemas.orderflow` | §12.6 + §20 |
| `AnchorPoint` | `AnchorPoint.schema.json` | `schemas.patterns` | §13.2 (anchor_points) |
| `CandlePatternEventPayload` | `CandlePatternEventPayload.schema.json` | `schemas.patterns` | §13.1 + §20 |
| `ClassicalPatternEventPayload` | `ClassicalPatternEventPayload.schema.json` | `schemas.patterns` | §13.2 + §20 |
| `EvidenceRecord` | `EvidenceRecord.schema.json` | `schemas.evidence` | §19.1 |
| `AvailabilitySignature` | `AvailabilitySignature.schema.json` | `schemas.evidence` | D-03-ب + A-01 |
| `GroupScore` | `GroupScore.schema.json` | `schemas.evidence` | §19.3 + D-03-أ |
| `CalibrationReport` | `CalibrationReport.schema.json` | `schemas.evidence` | §19.6 |
| `FusionSnapshot` | `FusionSnapshot.schema.json` | `schemas.evidence` | §19.2-5 + D-03 |
| `ExplanationObject` | `ExplanationObject.schema.json` | `schemas.evidence` | §2.8 |
| `PriceZone` | `PriceZone.schema.json` | `schemas.scenario` | §18.1 (entry_zone) |
| `TriggerDefinition` | `TriggerDefinition.schema.json` | `schemas.scenario` | §18.1 + §18.4 |
| `InvalidationRule` | `InvalidationRule.schema.json` | `schemas.scenario` | §18.5 + §23.4 |
| `TargetZone` | `TargetZone.schema.json` | `schemas.scenario` | §10.5 |
| `Scenario` | `Scenario.schema.json` | `schemas.scenario` | §18.1 |
| `ScenarioTransition` | `ScenarioTransition.schema.json` | `schemas.scenario` | §18.2 + §31.3 |
| `OrderIntent` | `OrderIntent.schema.json` | `schemas.execution` | §24.1 |
| `SlippageRecord` | `SlippageRecord.schema.json` | `schemas.execution` | §24.4 |
| `LatencyRecord` | `LatencyRecord.schema.json` | `schemas.execution` | §24.5 |
| `MacroEventWindow` | `MacroEventWindow.schema.json` | `schemas.risk` | §17.3 + §22.1-10 |
| `EvaluationContext` | `EvaluationContext.schema.json` | `schemas.risk` | §22.1 + §22.2 |
| `NoTradeExplanation` | `NoTradeExplanation.schema.json` | `schemas.risk` | §22.3 |
| `StructuralStop` | `StructuralStop.schema.json` | `schemas.risk` | §23.4 |
| `SizingModifier` | `SizingModifier.schema.json` | `schemas.risk` | §23.2 |
| `SizingResult` | `SizingResult.schema.json` | `schemas.risk` | §23.2 |
| `CostBreakdown` | `CostBreakdown.schema.json` | `schemas.risk` | §25.2 |
| `RewardRiskEstimate` | `RewardRiskEstimate.schema.json` | `schemas.risk` | §23.5 |
| `RiskDecision` | `RiskDecision.schema.json` | `schemas.risk` | §31.3 (decisions) |
| `ExperienceRecord` | `ExperienceRecord.schema.json` | `schemas.learning` | §29.1 |
