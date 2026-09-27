# AI Market Reasoning Engine — Master Plan

**Document status:** Authoritative architecture and build specification  
**Version:** 1.0  
**Date:** 2026-09-27  
**Owner:** System Architecture / Research / Execution  
**Primary objective:** Build a market-reasoning system that converts raw market information into auditable market state, evidence, scenarios, risk decisions, execution instructions, and post-trade learning without relying on brittle indicator stacking.

---

## 1. Project Definition

AI Market Reasoning Engine is an adaptive, data-driven market analysis and decision system for short-horizon trading. It is designed to read price structure, liquidity, volume/footprint and order-flow proxies, session context, classical price action, harmonic structures, market-phase behavior, volatility, and macroeconomic context; fuse these observations into explicit competing scenarios; reject low-quality situations; convert only validated scenarios into risk-bounded trade intents; execute through a broker/exchange adapter only when execution constraints are acceptable; and record the complete causal chain so every decision can later be evaluated and learned from.

It is **not** a collection of indicators, a black-box LLM that predicts the next candle, a proof that “smart money” can be seen directly from public chart data, a guarantee of profitability, or a system that treats the appearance of one named pattern as a trade signal. Terms such as Order Block, institutional zone, accumulation, manipulation, and distribution are treated as measurable **market-behavior hypotheses**, not as unverifiable claims about the identity or intention of market participants. The initial system is for research, analysis, paper trading, and tightly controlled live execution; any live use is gated by empirical validation after realistic costs.

---

## 2. Core Design Principles

### 2.1 Causal chain

Every production decision must be traceable through:

`Raw Data → Data Quality → Market State → Context → Events → Evidence → Scenario → Risk Decision → Execution Intent → Fill/Outcome → Attribution → Learning`

No module is allowed to create an isolated score that is not consumed by a downstream decision or stored for later evaluation.

### 2.2 Evidence is contextual, not absolute

A signal is never interpreted without location, regime, timing, volatility, and data quality. A bullish footprint inside a major bearish expansion can mean continuation, absorption, or trapped buyers depending on the surrounding auction.

### 2.3 Independent evidence beats repeated evidence

Five observations derived from the same price move do not equal five independent confirmations. Evidence Fusion therefore groups correlated observations and caps their combined contribution.

### 2.4 Hard constraints before soft scores

A hard risk or data-quality failure blocks a trade regardless of how attractive the analytical score is. Examples: stale feed, invalid instrument state, missing execution price, extreme spread, unavailable stop placement, or market halt.

### 2.5 Scenario-first reasoning

The engine generates competing explanations of the current market state rather than searching for a single predetermined direction.

### 2.6 No magical confidence

Before calibration, the engine uses evidence scores and grades, not pseudo-probabilities. A probability is exposed only after an explicit calibration procedure on out-of-sample data and is tracked by regime.

### 2.7 Learning is controlled, not self-corrupting

The live production policy never rewrites itself because of one trade or a short run of trades. Learning occurs through an immutable experience ledger, cohort statistics, offline re-estimation, walk-forward evaluation, promotion gates, and versioned deployment.

### 2.8 Human-readable causality

Every trade intent must have an explanation object containing: market context, liquidity map, structural state, supporting evidence, opposing evidence, trigger, invalidation, expected path, cost estimate, and reason for rejection when no trade is taken.

---

## 3. System Boundary and Responsibilities

The platform is divided into six responsibility domains:

1. **Understanding:** transform data into market facts and state.
2. **Decision:** compare scenarios and select whether a trade intent is justified.
3. **Risk:** determine whether the intent is allowed and size/shape it.
4. **Execution:** translate the approved intent into orders and verify actual fills.
5. **Learning:** measure what worked, what failed, why, and under which regime.
6. **Presentation:** render the state and reasoning to TradingView and the web dashboard.

The boundaries are strict. The Understanding layer never submits orders. The Learning layer never directly mutates live trading parameters. Execution never invents market analysis to justify an order.

---

# 4. Reference Architecture

```text
                           ┌──────────────────────────┐
                           │ External Market Feeds    │
                           │ Trades / Quotes / Bars   │
                           │ Economic / Calendar      │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │ Data Ingestion & QA       │
                           │ Normalize / Deduplicate   │
                           │ Timestamp / Health        │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │ Canonical Market Store    │
                           │ PostgreSQL + TimescaleDB  │
                           │ Raw Objects → Object Store│
                           └────────────┬─────────────┘
                                        │
                    ┌───────────────────┼──────────────────┐
                    │                   │                  │
                    ▼                   ▼                  ▼
             Context Engine      Liquidity Engine    Flow/Footprint
                    │                   │                  │
                    └───────────────────┼──────────────────┘
                                        ▼
                              ┌─────────────────────┐
                              │ Structure / SMC     │
                              │ Pattern / Macro     │
                              │ Volatility / Session│
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Evidence Fusion     │
                              │ Contradiction Model │
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Scenario Engine     │
                              │ Candidate / Active  │
                              │ Trigger / Invalidate│
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ No-Trade + Risk     │
                              │ Gate + Position Size│
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Execution Engine     │
                              │ Orders / Fills / Time│
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Position Monitor     │
                              │ Exit / Management    │
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Post-Trade Ledger    │
                              │ Attribution / Labels  │
                              └──────────┬──────────┘
                                         ▼
                              ┌─────────────────────┐
                              │ Learning Laboratory   │
                              │ WFO / Calibration     │
                              │ Drift / Versioning    │
                              └──────────┬──────────┘
                                         │ approved model
                                         └──────────────► Production

TradingView Pine v6 runs in parallel as a constrained visualization,
independent signal mirror, alert source, and operator interface. It is
not the authoritative store, learner, or sole live-data source.
```

---

# 5. Technology Decisions

## 5.1 Canonical language

**Python 3.12+** is the canonical language for the external engine.

Reasons:

- Strong market-data and quantitative ecosystem.
- Efficient numerical work with NumPy/Polars.
- Mature APIs, async networking, testing, and ML tooling.
- Fast iteration for research while keeping production services in one language.

**Pine Script v6** is used only for the TradingView component. It is not used as the central learning or execution platform.

## 5.2 Storage

**PostgreSQL + TimescaleDB** is the canonical relational/time-series store.

Use it for:

- normalized candles and market features;
- events, zones, scenarios, decisions;
- orders, fills, positions, and outcomes;
- model versions and parameters;
- calibration and drift statistics;
- audit logs.

**S3-compatible object storage (MinIO in the first self-hosted deployment)** stores large immutable datasets:

- raw trades;
- raw quote snapshots;
- compressed historical datasets;
- backtest exports;
- model artifacts;
- replay fixtures.

Do not store every raw tick inside ordinary relational rows unless required by the data source; keep large raw streams in partitioned columnar files such as Parquet and store their metadata in PostgreSQL.

## 5.3 Messaging

**NATS JetStream** is the event bus.

Reasons:

- Low operational overhead compared with a full Kafka deployment.
- Durable streams and consumer groups are sufficient for the first production scale.
- Clear separation between ingestion, feature calculation, scenario decisions, execution, and learning.

## 5.4 Hot state

**Redis** is used for:

- latest instrument state;
- short-lived locks;
- webhook idempotency keys;
- execution guards;
- rate limiting;
- cached session and macro state.

Redis is not the system of record.

## 5.5 API layer

**FastAPI** exposes:

- TradingView webhook endpoint;
- market-state API;
- scenario and decision API;
- operator dashboard API;
- execution status;
- research/replay controls.

## 5.6 Research stack

- Polars for high-performance tabular processing.
- NumPy for numerical arrays.
- SciPy for statistical procedures.
- scikit-learn for baseline models, calibration, metrics, and preprocessing.
- LightGBM for the first production-grade nonlinear ranking/classification learner after a deterministic baseline proves the feature set useful.
- PyTorch is deferred until a concrete problem is shown to benefit from sequence/deep models. It is not a default dependency.

## 5.7 Frontend

**React + TypeScript** web dashboard.

The dashboard is an investigation and monitoring surface, not the source of truth.

## 5.8 Deployment

First production architecture uses Docker Compose on a persistent server with managed or separately backed-up PostgreSQL when available. Kubernetes is explicitly deferred until deployment scale or availability requirements prove it necessary.

---

# 6. TradingView Architecture

## 6.1 Role of Pine v6

The TradingView component has four responsibilities:

1. Render canonical market concepts on the chart.
2. Run a lightweight, deterministic mirror of the most important event logic.
3. Create auditable alerts when configured conditions occur.
4. Act as a human-facing diagnostic surface.

Pine is not responsible for:

- long-term storage;
- model training;
- large-scale walk-forward jobs;
- portfolio-wide correlation analysis;
- broker reconciliation;
- live parameter mutation;
- large raw tick retention.

## 6.2 Current relevant Pine constraints

As of 2026-09-27, TradingView documents the following constraints relevant to this project:

- Pine Script v6 is the current language.
- General `request.*()` calls are limited to 40 unique calls, or 64 on Ultimate plans; `request.footprint()` has its own one-unique-call restriction and requires Premium or Ultimate access.
- Script execution and loop execution are bounded; the documented total script execution limit is 20 seconds for basic accounts and 40 seconds for other accounts, with a 500 ms per-loop-per-bar limit.
- Compiled Pine code is limited to 100,256 compiled tokens; the compilation request has a 5 MB limit.
- Collections are limited to 100,000 elements.
- Lower-timeframe requests are capped by plan; current documentation lists up to 100K intrabars on non-professional plans, 125K on Expert, and 200K on Ultimate.

These limits are reasons for keeping the external engine authoritative rather than trying to build the full reasoning and learning system in Pine.

Official references:

- https://www.tradingview.com/pine-script-docs/writing/limitations/
- https://www.tradingview.com/pine-script-docs/release-notes/
- https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/

## 6.3 Footprint capability

TradingView now exposes footprint data to Pine through `request.footprint()`. The available data includes total buy volume, sell volume, delta, POC, VAH, VAL, and row-level imbalances. The project must use this capability where the instrument/feed supports it rather than reconstructing the same information from crude lower-timeframe guesses.

A footprint request is a **bar-level observation**. It does not prove global market-wide order-book intent.

Official reference:

- https://www.tradingview.com/pine-script-docs/release-notes/
- https://www.tradingview.com/pine-script-docs/language/type-system/

## 6.4 Webhook boundary

TradingView alerts send HTTP POST requests to an external endpoint. JSON alert bodies are supported. Current TradingView documentation states webhook delivery uses ports 80/443, requests taking more than three seconds are cancelled, IPv6 is not currently supported for webhooks, and webhook delivery can occasionally fail; therefore the endpoint must respond quickly, persist the event, and process asynchronously.

Webhook requirements:

- HTTPS only.
- Authenticated endpoint.
- Replay/idempotency key.
- Schema version.
- Timestamp and alert event UUID.
- No secrets or credentials in the alert body.
- Fast acknowledgement; heavy work occurs asynchronously.

Official reference:

- https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/

---

# 7. Data Model and Market Data Contract

The entire engine depends on a canonical event-time model.

## 7.1 Time contract

Every market record must contain:

- `event_time_utc`: actual event timestamp when available.
- `receive_time_utc`: system arrival time.
- `source_timeframe`.
- `venue`.
- `symbol`.
- `feed_id`.
- `sequence_id` when supplied by source.
- `source_latency_ms` where measurable.

Never use local wall-clock time as market event time.

## 7.2 Data hierarchy

```text
Raw Tick / Trade / Quote
        ↓
Normalized Event
        ↓
Time-bucketed Bars
        ↓
Intrabar / Footprint Aggregates
        ↓
Features
        ↓
Events
        ↓
Market State
```

## 7.3 Source hierarchy

The engine distinguishes:

1. Exchange/broker-native trade and quote data.
2. Specialized order-flow/market-depth data where licensed.
3. TradingView chart/footprint observations.
4. Economic releases from authoritative providers.
5. Derived features from the above.

A derived value is never treated as a primary fact.

## 7.4 Data-quality states

Each instrument/time slice is classified as:

- `HEALTHY`
- `DELAYED`
- `PARTIAL`
- `DUPLICATED`
- `OUT_OF_ORDER`
- `STALE`
- `GAP_DETECTED`
- `UNAVAILABLE`
- `QUARANTINED`

Only `HEALTHY` and explicitly approved `DELAYED` states can reach normal decision processing. Any data-quality degradation is attached to downstream evidence quality.

---

# 8. Candle and Footprint Canonical Objects

## 8.1 Candle object

Each canonical candle contains:

```text
open
high
low
close
volume
range
body_size
upper_wick
lower_wick
body_fraction
close_location_value
true_range
realized_volatility
session_id
bar_time
```

Derived features are normalized by recent regime statistics rather than hard-coded absolute values wherever possible.

## 8.2 Footprint object

Where available:

```text
buy_volume
sell_volume
total_volume
delta
buy_share
sell_share
poc
vah
val
row_count
buy_imbalance_count
sell_imbalance_count
max_positive_delta_row
max_negative_delta_row
```

Row-level information is retained for the current bar and for selected historical rows that materially affect a detected event. The system does not create unbounded row storage merely for visualization.

---

# 9. Context Engine

The Context Engine answers: **What kind of market are we in?**

It produces a structured state, not a trade direction.

## 9.1 Timeframe hierarchy

The engine uses three functional levels:

- **Higher timeframe:** defines broad context and external structure.
- **Middle timeframe:** defines the setup and location.
- **Execution timeframe:** defines the trigger.

Example reference stack:

```text
HTF: 1H / 4H
MTF: 5m / 15m
LTF: 1m
```

The exact selected periods are configuration values, but the role separation is invariant.

## 9.2 HTF Bias

HTF bias is a structured state determined from:

- confirmed swing sequence;
- external structure direction;
- current dealing range;
- relationship to major liquidity;
- expansion/contraction state;
- higher-timeframe displacement;
- volatility regime.

It is represented as:

```text
BULLISH
BEARISH
NEUTRAL
TRANSITION
UNKNOWN
```

HTF bias is contextual evidence. It does not trigger a trade.

## 9.3 Market regime

The engine classifies:

- `TREND_EXPANSION`
- `TREND_PULLBACK`
- `RANGE_BALANCE`
- `RANGE_EXPANSION`
- `COMPRESSION`
- `VOLATILITY_SHOCK`
- `TRANSITION`
- `UNKNOWN`

Regime features include normalized range, directional efficiency, volatility percentile, swing persistence, volume concentration, and displacement frequency.

## 9.4 Session context

Sessions are explicit objects with:

- open time;
- close time;
- opening range;
- initial balance where meaningful;
- prior session high/low;
- current session high/low;
- session volume profile where available;
- overlap flags;
- session transition risk.

Session is contextual metadata. It is not a direction signal by itself.

## 9.5 Opening structure

The system tracks:

- gap relative to prior session where meaningful;
- opening range;
- opening drive;
- opening reversal;
- early liquidity formation;
- opening imbalance;
- prior close relationship.

No fixed assumption is made that a gap must fill or that an opening drive must continue.

---

# 10. Liquidity Map Engine

The Liquidity Map represents **where price has structural reasons to encounter opposing interest or stop-driven activity**.

It is an inferred map, not direct knowledge of every participant's orders.

## 10.1 Liquidity sources

### Sell-side candidates

- prior swing lows;
- equal lows;
- session lows;
- previous day/week lows;
- range boundaries;
- obvious repeated lows;
- untested external liquidity.

### Buy-side candidates

- prior swing highs;
- equal highs;
- session highs;
- previous day/week highs;
- range boundaries;
- obvious repeated highs;
- untested external liquidity.

## 10.2 Liquidity zone object

```text
zone_id
side
price_low
price_high
origin_time
age
source_type
test_count
last_test_time
sweep_status
reaction_score
unmitigated_score
importance_score
```

## 10.3 Zone strength

Zone strength is calculated from:

- structural importance;
- number and spacing of equal/repeated levels;
- freshness;
- timeframe significance;
- distance to current price;
- previous reaction quality;
- whether the zone has already been consumed.

The score is not treated as probability.

## 10.4 Sweep detection

A sweep is a sequence, not a single wick.

Minimum structure:

1. A previously identified liquidity zone exists.
2. Price trades through the zone by a regime-normalized excursion.
3. The excursion reaches a threshold relative to local volatility and zone width.
4. Price either reclaims the zone or shows a continuation response that distinguishes a sweep from a genuine break.
5. The event is timestamped and linked to the consumed liquidity zone.

A sweep may be classified:

- `FAILED_SWEEP`
- `PARTIAL_SWEEP`
- `CONFIRMED_SWEEP`
- `BREAK_AND_ACCEPT`
- `UNKNOWN`

## 10.5 Target mapping

After an active setup is created, the engine computes the next relevant liquidity targets on both sides. Scenario generation uses these targets to estimate the plausible path and invalidation distance.

---

# 11. Structure and SMC Engine

SMC concepts are implemented only when they become measurable state transitions.

## 11.1 Swing detection

A swing is confirmed only after a defined structural lookback/confirmation rule is satisfied. The rule must not rely on future bars in live mode beyond the required confirmation delay.

Each swing contains:

```text
swing_id
price
timeframe
direction
strength
confirmation_time
external_or_internal
```

## 11.2 BOS

**Break of Structure (BOS)** is a confirmed breach of a structurally relevant prior swing in the current directional framework.

Programmable condition:

- identify a confirmed swing;
- require a close or accepted trade beyond the swing by a configurable minimum displacement threshold;
- verify the break is not merely an isolated wick unless a strategy explicitly treats wick breaks as valid;
- classify as internal or external.

Measure:

- breach distance normalized by ATR/local range;
- closing acceptance;
- volume/flow support;
- follow-through.

## 11.3 CHoCH

**Change of Character (CHoCH)** is a structure transition in which the current swing sequence first violates the prior directional continuation pattern.

It is weaker than a confirmed regime reversal and should not be treated as one automatically.

## 11.4 Displacement

Displacement measures unusually directional price travel relative to recent volatility.

Core features:

```text
range_zscore
body_fraction
close_location
ATR_multiple
velocity
follow_through
```

A displacement event requires a directional range/impulse above a rolling percentile and meaningful closing efficiency.

## 11.5 Fair Value Gap (FVG)

For a three-bar sequence:

- bullish FVG candidate: current low > high of bar two-bars-back;
- bearish FVG candidate: current high < low of bar two-bars-back.

The gap is stored as a price interval with:

- origin time;
- direction;
- size normalized by local ATR;
- fill percentage;
- first mitigation time;
- invalidation/consumption state.

The engine does not assume every FVG must fill.

## 11.6 Order Block

An Order Block is defined operationally as a bounded pre-displacement consolidation/candle region that precedes a structurally meaningful displacement and remains relevant after the move.

The detection pipeline is:

1. Identify a confirmed displacement.
2. Trace backward to the final opposing candle or compact opposing cluster before the impulse.
3. Verify the impulse generated meaningful structure change or liquidity interaction.
4. Define the source zone.
5. Track retests and reactions.

Quality depends on:

- displacement magnitude;
- structural consequence;
- freshness;
- retest response;
- volume/flow behavior.

An “Order Block” is not interpreted as proof of institutional order placement.

## 11.7 Premium / Discount

For a defined dealing range:

```text
equilibrium = (range_high + range_low) / 2
premium = price > equilibrium
discount = price < equilibrium
```

The dealing range must be explicitly named. The engine refuses ambiguous “premium/discount” calculations that change range definition silently.

## 11.8 Inducement

Inducement is not implemented as a mystical label. It is represented as a **candidate liquidity-building pattern** where price creates a local obvious level before a larger structural event. It only contributes evidence when the subsequent liquidity interaction validates the hypothesis.

---

# 12. Order Flow and Footprint Engine

Order Flow answers: **What did trading activity look like at price, and did price respond accordingly?**

## 12.1 Core metrics

- total volume;
- buy volume;
- sell volume;
- delta;
- buy/sell share;
- POC;
- VAH/VAL;
- row-level delta;
- buy imbalance;
- sell imbalance;
- volume concentration;
- delta trend.

## 12.2 Delta

```text
delta = buy_volume - sell_volume
```

The important observation is not the sign alone. The engine compares delta to price result.

### Effort vs Result

Examples:

- large positive delta + strong price rise → aggressive buying accepted;
- large positive delta + weak price response → possible absorption/trapped buying;
- large negative delta + weak price decline → possible sell absorption;
- large volume + narrow range → possible two-sided auction or absorption.

These are hypotheses that must be confirmed by subsequent response.

## 12.3 Absorption

Absorption is detected as a mismatch between aggressive traded volume and realized price movement at a meaningful location.

A candidate requires:

1. elevated directional delta or volume at a zone;
2. limited price extension relative to the aggression;
3. repeated response or failure to continue;
4. optional subsequent displacement in the opposite direction.

Absorption quality increases when the event occurs at mapped liquidity or structural boundaries.

## 12.4 Exhaustion

Exhaustion is a decline in directional effectiveness:

- declining extension per unit of directional volume;
- reducing follow-through;
- repeated failed highs/lows;
- deteriorating delta efficiency.

Exhaustion alone is not a reversal signal.

## 12.5 POC / VAH / VAL

These represent auction concentration and value boundaries for the footprint bar or configured profile.

They are used to answer:

- where did activity concentrate?
- did price accept/reject value?
- did the next move occur from value or away from it?

They are not treated as universal support/resistance.

## 12.6 Imbalance

A footprint imbalance is recorded according to the feed's row-level buy/sell comparison rule. The system stores both:

- raw imbalance detection;
- contextual importance.

An isolated imbalance has low directional weight. Repeated imbalances aligned with displacement and structure carry more evidence.

## 12.7 Important limitation

Footprint buy/sell volume is feed-specific. The engine must store its source and methodology. It must never label a computed split as “all market buyers vs all market sellers” without qualifying the actual data source.

---

# 13. Price Action and Classical Pattern Engine

Patterns are treated as compressed descriptions of price behavior, not independent magical predictors.

## 13.1 Candlestick features

Each candle may be classified by:

- body fraction;
- wick asymmetry;
- close location;
- range percentile;
- gap relationship;
- volume relationship.

Named patterns are aliases for feature combinations.

Supported pattern families:

- engulfing;
- pin/rejection bar;
- hammer/shooting star;
- inside bar;
- doji;
- morning/evening star;
- strong closing candle;
- expansion candle.

## 13.2 Classical structures

Implemented candidates:

- double top/bottom;
- head and shoulders / inverse;
- triangle;
- wedge;
- flag;
- channel;
- range breakout;
- failed breakout.

Each pattern must produce:

```text
pattern_type
geometry
anchor_points
completion_time
breakout_level
invalidation_level
measured_move
quality
```

If the geometry is ambiguous, the pattern remains a candidate and contributes little or nothing to Evidence Fusion.

## 13.3 Why RSI is not a core decision engine

Generic oscillators may be useful as contextual features but do not receive first-class event status. They are not required because the architecture prioritizes structure, liquidity, order flow, volatility, and direct price behavior. Adding an oscillator is allowed only after an ablation study proves incremental out-of-sample value after costs.

---

# 14. Harmonic Pattern Engine

Harmonics are retained because their geometry is measurable.

Supported initial families:

- AB=CD;
- Gartley;
- Bat;
- Butterfly;
- Crab;
- Cypher.

The engine detects candidate pivot sequences and evaluates Fibonacci-ratio conformance within configurable tolerances.

Each detection stores:

```text
pattern
X/A/B/C/D
ratio_deviations
completion_zone
invalidation
symmetry
quality
```

Harmonics become useful only when:

- the geometry is sufficiently complete;
- the completion zone overlaps meaningful liquidity/location;
- structural/flow evidence does not contradict the scenario.

A harmonic pattern alone never creates an order.

---

# 15. Market-Phase / Wyckoff-Style Engine

The project uses Wyckoff-style phase reasoning as a state classification framework, not as a claim that every market follows an exact textbook sequence.

## 15.1 Phase features

- trading range duration;
- volatility compression;
- volume concentration;
- failed breakdowns/breakouts;
- liquidity sweeps;
- absorption;
- structural response;
- directional expansion.

## 15.2 Phase states

```text
RANGE_BUILDING
ACCUMULATION_CANDIDATE
DISTRIBUTION_CANDIDATE
LIQUIDITY_EVENT
MARKUP_EXPANSION
MARKDOWN_EXPANSION
RE-ACCUMULATION_CANDIDATE
RE-DISTRIBUTION_CANDIDATE
UNKNOWN
```

The phase engine produces a state with supporting observations. It cannot directly override a higher-priority risk block.

## 15.3 Accumulation → manipulation → distribution

The project explicitly models this sequence only as a candidate pattern:

```text
Range / liquidity build
        ↓
False break / sweep candidate
        ↓
Acceptance or rejection
        ↓
Displacement / continuation
        ↓
Opposite liquidity formation
```

The engine never assumes that “market makers manipulated price” as a fact; it detects observable behavior consistent with the hypothesis.

---

# 16. Volatility Engine

Volatility is used to normalize nearly every threshold.

Metrics:

- ATR and ATR percentile;
- realized volatility;
- range expansion percentile;
- volatility-of-volatility;
- spread-to-range ratio;
- recent gap/shock size;
- expected holding-time volatility.

Every price-distance threshold should prefer a normalized form such as:

```text
threshold = local_volatility × multiplier
```

instead of one universal number of ticks/pips.

---

# 17. Fundamental / Macro Engine

## 17.1 Explicit role

**Fundamental analysis on small timeframes is a context and risk filter, not a signal generator.**

Its outputs influence:

- trade eligibility;
- volatility expectation;
- event risk;
- regime context;
- size reduction;
- no-trade windows.

It does not generate `BUY` merely because an economic statistic is better or worse than expected.

## 17.2 Inputs

- central-bank decisions;
- inflation releases;
- employment releases;
- GDP and growth indicators;
- major economic surprises;
- rate-expectation changes;
- scheduled high-impact events;
- market-wide risk regime.

TradingView exposes economic data through `request.economic()`, but the external Macro service remains canonical because the engine also needs event metadata, publication time, surprise magnitude, revisions, and explicit release-quality handling.

Reference:

- https://www.tradingview.com/support/solutions/43000665359-what-economic-data-is-available-in-pine/

## 17.3 Macro risk windows

Each event has:

```text
event_time
asset_scope
importance
expected
actual
surprise
revision
pre_event_window
post_event_window
```

A high-impact event near a scalp entry can cause a hard block even when technical evidence is strong.

---

# 18. Scenario Engine

The Scenario Engine is the center of the reasoning model.

## 18.1 Scenario object

```text
scenario_id
symbol
direction
regime
context_snapshot
location_snapshot
thesis
supporting_evidence
opposing_evidence
trigger_definition
entry_zone
invalidation
primary_targets
secondary_targets
expiry_time
state
scenario_score
calibrated_probability (nullable until calibrated)
```

## 18.2 Scenario lifecycle

```text
DRAFT
  ↓ sufficient context
ACTIVE
  ↓ trigger occurs
TRIGGERED
  ↓ risk approved
AUTHORIZED
  ↓ order sent
EXECUTING
  ↓ fill
IN_TRADE
  ↓ exit
COMPLETED
```

Alternative endings:

- `INVALIDATED`
- `EXPIRED`
- `SUPPRESSED`
- `REJECTED_BY_RISK`
- `CANCELLED_BY_DATA_QUALITY`

## 18.3 Scenario construction

A scenario must contain:

1. Context.
2. Location.
3. Expected mechanism.
4. Trigger.
5. Invalidation.
6. Expected path.
7. Cost-aware reward/risk estimate.
8. Time horizon.
9. Contradictions.

Example:

```text
Context: HTF bullish, MTF pullback
Location: sell-side liquidity + demand hypothesis
Mechanism: sweep → rejection → displacement
Trigger: confirmed reclaim + execution-timeframe displacement
Invalidation: below sweep low + volatility buffer
Target: nearest meaningful buy-side liquidity
No-trade: major event within embargo window
```

## 18.4 Scenario promotion

A scenario may move from DRAFT to ACTIVE when at least two independent evidence groups support it and no hard veto exists.

A scenario may become TRIGGERED only when its defined trigger is observed.

A triggered scenario is rejected if the market has moved too far from the planned entry so that cost-adjusted reward/risk or execution quality fails.

## 18.5 Scenario invalidation

Immediate invalidation occurs when:

- explicit structural invalidation is reached;
- the thesis-required liquidity event fails in the opposite direction;
- price accepts through the invalidation zone;
- expected timing expires;
- data quality becomes unsafe;
- execution conditions become structurally different.

The scenario cannot be “rescued” by inventing new evidence after invalidation. A new scenario must be opened.

---

# 19. Evidence Fusion Engine

Evidence Fusion combines heterogeneous observations without double counting.

## 19.1 Evidence record

Each item is represented as:

```text
evidence_id
group
event_type
direction_score ∈ [-1, +1]
raw_strength ∈ [0, 1]
quality ∈ [0, 1]
freshness ∈ [0, 1]
independence_discount ∈ [0, 1]
prior_weight
context_modifier
opposition
source
```

## 19.2 Directional contribution

Conceptual contribution:

```text
c_i = prior_weight
    × direction_score
    × raw_strength
    × quality
    × freshness
    × independence_discount
    × context_modifier
```

No individual event can override a hard veto.

## 19.3 Evidence groups

Default groups:

| Group | Default share | Purpose |
|---|---:|---|
| Structure | 25% | HTF/MTF structure, BOS, CHoCH, displacement |
| Liquidity / Location | 20% | liquidity zones, sweeps, FVG/OB location, premium/discount |
| Order Flow | 30% | delta, absorption, POC/VA, imbalances |
| Price Action / Patterns | 10% | candles, classical, harmonics |
| Volatility / Session | 10% | regime and execution context |
| Macro | 5% | macro regime and event-risk context only |

These are **starting priors**, not permanent truths. They are re-tested in the Learning Lab.

## 19.4 Correlation control

Events are assigned correlation groups. Example:

```text
BOS
Displacement
Strong close
Large body
```

may all arise from the same impulse. They must not count as four independent confirmations.

The system applies an independence discount based on:

- shared source data;
- time proximity;
- causal duplication;
- historical correlation.

## 19.5 Contradiction model

A scenario receives explicit negative evidence.

For example:

```text
Support:
Sweep + absorption + bullish displacement

Contradiction:
HTF bearish expansion + immediate major resistance
```

The result is not a binary cancel unless the contradiction is a hard veto. Otherwise it reduces the scenario score and may keep the scenario in `ACTIVE` rather than `TRIGGERED`.

## 19.6 Calibrated probability

After sufficient out-of-sample data, scenario scores may be mapped to empirical probabilities using a calibration model such as isotonic regression or Platt-style calibration. Calibration is performed on data never used to optimize the raw score.

The system reports:

```text
raw_evidence_score
calibrated_probability (only when eligible)
calibration_sample_size
calibration_regime
```

A raw score is never labeled “94% chance”.

---

# 20. Event Dictionary

The following table defines the initial production event vocabulary. `Weight` is the starting prior used by Evidence Fusion before context and quality modifiers. It is not a percentage win probability.

| Event | Meaning | Programmable detection | Primary measurement | Weight |
|---|---|---|---|---:|
| HTF_BULLISH | Confirmed higher-timeframe upward structure | Confirmed external swing sequence | Directional swing consistency | 0.90 |
| HTF_BEARISH | Confirmed higher-timeframe downward structure | Confirmed external swing sequence | Directional swing consistency | 0.90 |
| INTERNAL_BOS | Internal structure break | Close/acceptance beyond confirmed internal swing | Break distance / ATR | 0.80 |
| EXTERNAL_BOS | External structure break | Acceptance beyond major external swing | Break distance / ATR | 1.00 |
| CHOCH | First meaningful violation of prior continuation pattern | Opposite structural break before confirmed reversal | Structure transition quality | 0.75 |
| DISPLACEMENT_UP | Strong bullish impulse | Range/body/close efficiency above regime threshold | Range z-score, ATR multiple | 0.90 |
| DISPLACEMENT_DOWN | Strong bearish impulse | Same, bearish | Range z-score, ATR multiple | 0.90 |
| LIQUIDITY_SWEEP_HIGH | Buy-side liquidity taken and rejected | Zone breach + rejection/reclaim | Excursion, reclaim speed | 0.95 |
| LIQUIDITY_SWEEP_LOW | Sell-side liquidity taken and rejected | Zone breach + rejection/reclaim | Excursion, reclaim speed | 0.95 |
| BREAK_AND_ACCEPT_HIGH | High broken with acceptance | Break + closes/volume acceptance | Acceptance ratio | 0.85 |
| BREAK_AND_ACCEPT_LOW | Low broken with acceptance | Break + closes/volume acceptance | Acceptance ratio | 0.85 |
| ABSORPTION_BUY | Sell pressure absorbed | Negative aggression with limited downside response | Delta vs excursion | 0.90 |
| ABSORPTION_SELL | Buy pressure absorbed | Positive aggression with limited upside response | Delta vs excursion | 0.90 |
| FLOW_CONTINUATION_UP | Flow and price agree | Positive delta + upward response | Delta efficiency | 0.70 |
| FLOW_CONTINUATION_DOWN | Flow and price agree | Negative delta + downward response | Delta efficiency | 0.70 |
| EXHAUSTION_UP | Upward effort loses effectiveness | Falling extension per effort | Efficiency decay | 0.65 |
| EXHAUSTION_DOWN | Downward effort loses effectiveness | Same, bearish | Efficiency decay | 0.65 |
| FVG_BULLISH | Bullish three-bar gap | Current low above earlier high | Gap/ATR | 0.55 |
| FVG_BEARISH | Bearish three-bar gap | Current high below earlier low | Gap/ATR | 0.55 |
| ORDER_BLOCK_BULLISH | Pre-displacement bullish source zone | Opposing candle/cluster before validated impulse | Displacement consequence + freshness | 0.65 |
| ORDER_BLOCK_BEARISH | Pre-displacement bearish source zone | Opposing candle/cluster before validated impulse | Same | 0.65 |
| PREMIUM_LOCATION | Price above defined dealing midpoint | Price > equilibrium | Normalized distance | 0.35 |
| DISCOUNT_LOCATION | Price below defined dealing midpoint | Price < equilibrium | Normalized distance | 0.35 |
| POC_ACCEPTANCE | Price accepted around footprint POC | Time/volume concentration around POC | POC dwell/return | 0.45 |
| POC_REJECTION | Price rejected from POC | Rapid departure + low acceptance | Excursion / dwell | 0.45 |
| VAH_REJECTION | Value high rejected | Rejection from VAH | Return distance | 0.40 |
| VAL_REJECTION | Value low rejected | Rejection from VAL | Return distance | 0.40 |
| BUY_IMBALANCE_CLUSTER | Repeated bullish row imbalances | Count/spacing threshold | Imbalance density | 0.55 |
| SELL_IMBALANCE_CLUSTER | Repeated bearish row imbalances | Count/spacing threshold | Imbalance density | 0.55 |
| BULLISH_ENGULFING | Strong bullish candle sequence | Body relation + close location | Body ratio | 0.35 |
| BEARISH_ENGULFING | Strong bearish candle sequence | Body relation + close location | Body ratio | 0.35 |
| REJECTION_CANDLE | Strong rejection | Wick/range/location threshold | Wick ratio | 0.30 |
| INSIDE_BAR_BREAK | Compression then expansion | Inside-range sequence + break | Range compression/expansion | 0.35 |
| CLASSICAL_BREAKOUT | Geometric structure breaks | Pattern anchor + acceptance | Break quality | 0.45 |
| CLASSICAL_FAILED_BREAKOUT | Break fails | Break + reclaim | Failure speed | 0.60 |
| HARMONIC_COMPLETION | Valid harmonic completion | Ratio constraints + D completion | Ratio error | 0.45 |
| RANGE_COMPRESSION | Tight auction | Low normalized volatility | Vol percentile | 0.45 |
| RANGE_EXPANSION | High expansion | High normalized volatility | Vol percentile | 0.55 |
| SESSION_OPENING_DRIVE | Strong early session directional movement | Opening range break + persistence | Opening range multiple | 0.45 |
| SESSION_REVERSAL | Early move reverses | Opening drive failure + structure response | Reversal magnitude | 0.45 |
| MACRO_HIGH_IMPACT_NEAR | Major macro event is near | Scheduled event inside embargo window | Time to event | 0.00* |
| DATA_STALE | Market input is stale | Receive lag > threshold | Lag ms | HARD BLOCK |
| SPREAD_EXTREME | Spread is too high | Spread/range > threshold | Spread-to-range | HARD BLOCK |
| LATENCY_EXTREME | Execution latency unsafe | Measured p95 > budget | Latency | HARD BLOCK |
| RISK_LIMIT_REACHED | Risk budget exhausted | Daily/portfolio risk threshold | Exposure | HARD BLOCK |

`*` Macro event itself is not a directional score. It modifies eligibility and risk.

---

# 21. Pattern Interaction Rules

The engine deliberately avoids “one pattern means one action”. Interactions are represented as mechanisms.

## 21.1 Preferred interaction chain

```text
Location
  +
Liquidity Event
  +
Order-Flow Response
  +
Structure Change
  +
Execution Trigger
```

## 21.2 Stronger causal sequences

### Reversal candidate

```text
Major liquidity
→ sweep
→ absorption/exhaustion
→ displacement
→ structure reclaim
→ retrace/trigger
```

### Continuation candidate

```text
HTF structure aligned
→ pullback into validated location
→ flow re-aligns
→ internal BOS/displacement
→ continuation trigger
```

### Breakout candidate

```text
Compression
→ liquidity build
→ expansion
→ acceptance beyond boundary
→ retest/continuation
```

These are scenario templates, not hard-coded universal truths.

---

# 22. No-Trade Engine

No-Trade is a first-class subsystem. Its job is to reject trades even when a directional scenario looks attractive.

## 22.1 Hard blocks

The engine must refuse new entries when any of the following holds:

1. Market data is stale, corrupted, duplicated beyond tolerance, or missing required fields.
2. Instrument status is halted, unavailable, or outside approved trading hours.
3. Execution venue connection is unhealthy.
4. Estimated spread exceeds the configured percentage of expected edge or stop distance.
5. Expected slippage exceeds the cost budget.
6. Execution latency exceeds the maximum allowed for the strategy horizon.
7. Position/risk limits have been reached.
8. A required stop cannot be reliably placed or reconciled.
9. Broker/exchange rejects the instrument or order type.
10. A high-impact scheduled event is inside the configured embargo window for the instrument.
11. Scenario invalidation has already occurred.
12. Entry is too late and remaining reward cannot compensate for execution costs.
13. Conflicting higher-priority scenario creates unresolved bilateral risk.
14. The same scenario was already consumed and no new structural information has formed.
15. The system is in emergency/kill-switch state.

## 22.2 Soft suppressions

The system may also decline when:

- price is mid-range with poor location;
- evidence is weak or highly correlated;
- volatility is too low for the target movement;
- volatility is too extreme for safe stop placement;
- the market is transitioning between regimes;
- the target is too close;
- the stop is too wide;
- the setup conflicts with session behavior;
- the signal requires chasing an already-expanded move;
- expected holding time exceeds the scalp horizon.

## 22.3 No-trade explanation

Every rejection has:

```text
no_trade_code
severity
triggering_conditions
offsetting_evidence
whether_retry_is_allowed
retry_condition
```

---

# 23. Risk Engine

The Risk Engine receives an **approved trade intent candidate**, not raw technical analysis.

## 23.1 Risk unit

Every strategy uses an abstract `R` unit:

```text
1R = planned monetary loss at the initial invalidation stop
```

All post-trade analysis is normalized by R so instruments and periods are comparable.

## 23.2 Position sizing

Base sizing:

```text
position_size = allowed_risk_money / stop_distance_value
```

Then apply:

- volatility modifier;
- liquidity modifier;
- execution-quality modifier;
- correlation modifier;
- daily drawdown modifier;
- scenario quality modifier after calibration.

Sizing is capped by absolute portfolio and instrument limits.

## 23.3 Risk constraints

The configuration must contain:

- per-trade risk cap;
- daily loss cap;
- rolling loss cap;
- simultaneous position cap;
- correlated exposure cap;
- event-risk cap;
- maximum slippage budget;
- maximum stop distance;
- maximum holding time for the strategy.

## 23.4 Invalidation

Stops are defined from market structure and volatility, not from a universal number of points.

The stop may use:

```text
structural invalidation
+ volatility buffer
+ expected execution uncertainty
```

## 23.5 Reward/risk

The engine computes:

- gross target distance;
- expected slippage;
- commission/fee;
- spread cost;
- expected adverse selection;
- partial-fill risk;
- estimated net R.

A setup can be rejected because the gross target is large but cost-adjusted edge is insufficient.

---

# 24. Execution Engine

Execution is separate from reasoning.

## 24.1 Order intent

The decision engine creates:

```text
trade_intent_id
scenario_id
symbol
side
entry_policy
entry_zone
stop
targets
max_slippage
max_latency
expiry
risk_budget
client_order_id
```

## 24.2 Execution policies

Initial supported policies:

- market with max-slippage guard;
- limit at defined zone;
- staged limit/market combination;
- reduce-only exit;
- emergency flatten.

The strategy determines which policy is allowed; the execution engine chooses the safest valid order implementation inside those constraints.

## 24.3 Partial fills

Every fill is an independent event. The position is calculated as the sum of fills.

Risk is recalculated after partial fills. The engine must prevent the accidental assumption that the entire intended size filled at the first price.

## 24.4 Slippage

Actual slippage is stored separately from modeled slippage:

```text
modeled_entry
actual_average_entry
modeled_exit
actual_average_exit
entry_slippage
exit_slippage
```

## 24.5 Latency

Store:

```text
signal_time
webhook_receive_time
engine_decision_time
broker_send_time
exchange_ack_time
fill_time
```

This allows the Learning Engine to quantify the difference between an analytical edge and an executable edge.

## 24.6 Reconciliation

The execution adapter must reconcile internal state against the broker/exchange after:

- startup;
- reconnect;
- each fill;
- every periodic heartbeat;
- any unexpected order message.

An unreconciled account enters a safety state and stops new orders.

---

# 25. Cost Model

Backtests and live analysis must include:

```text
spread
commission / trading fee
slippage
latency impact
partial-fill impact
funding/financing where applicable
borrow costs where applicable
market-impact approximation where material
```

## 25.1 Backtest cost modes

Three modes must exist:

1. `OPTIMISTIC` — diagnostic only.
2. `REALISTIC` — acceptance mode.
3. `STRESS` — robustness mode.

A strategy cannot pass production gates based only on optimistic costs.

## 25.2 Cost attribution

Post-trade P&L must be decomposed into:

```text
Gross Price Edge
- Spread
- Commission
- Slippage
- Funding/Financing
- Other Execution Costs
= Net Trading Edge
```

---

# 26. Backtesting and Replay Engine

A deterministic replay engine is required before optimization.

## 26.1 Principles

- Event time only.
- No future data access.
- Same feature functions in replay and live as far as possible.
- Costs included.
- Latency simulated.
- Partial fills modeled.
- Data gaps preserved or explicitly marked.
- Parameter versions immutable.

## 26.2 Reproducibility

Every backtest creates:

```text
backtest_id
data_snapshot_id
code_version
model_version
parameter_set_version
cost_model_version
random_seed
start_time
end_time
instrument_set
```

The exact result must be reproducible from those identifiers.

## 26.3 No-lookahead enforcement

The replay framework exposes only data available at each simulated timestamp.

Tests explicitly verify:

- no future bar indexing;
- no future swing confirmation leakage;
- no future footprint row usage;
- no revised macro observation before release time;
- no post-entry features leaking into the entry decision;
- no calibration on the evaluation fold.

---

# 27. Repainting Policy

Repainting is treated as a formal engineering concern, not a visual annoyance.

## 27.1 Signal states

Every real-time signal has one of:

```text
DEVELOPING
CONFIRMED
INVALIDATED
RETRACTED
```

### Developing Signal

Can use current-bar information but may change before the bar closes. It is visualization/informational only and cannot directly authorize a live order unless a separate explicit tick-level strategy is designed and validated.

### Confirmed Signal

Uses data that is confirmed under the strategy's execution rules. It is eligible for normal decision processing.

## 27.2 Higher-timeframe data

Higher-timeframe requests must follow non-repainting rules. The engine prefers confirmed HTF values and documents the confirmation delay.

TradingView's documentation explicitly notes that `request.security()` can behave differently on realtime and historical bars when requesting higher-timeframe values and that confirmed-value techniques are required to avoid misleading results.

Reference:

- https://www.tradingview.com/pine-script-docs/v5/concepts/repainting/
- https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/

## 27.3 Lower-timeframe data

`request.security_lower_tf()` is used when Pine needs multiple intrabars rather than one sampled intrabar. Even then, feed differences can cause historical/realtime differences, so Pine output is never assumed to be identical to the external engine's tick stream.

Reference:

- https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/

## 27.4 Alert policy

Live order-capable alerts must be based on confirmed logic unless a dedicated tick-level system has been separately validated.

---

# 28. Pine Strategy Backtest Caveats

TradingView strategies use a broker emulator. Historical execution is based on chart data and assumptions about intrabar movement unless higher-detail settings are used. By default, orders generated on a bar close are typically filled at the next available tick, and options such as `process_orders_on_close`, `calc_on_every_tick`, `calc_on_order_fills`, and Bar Magnifier alter execution behavior and can make historical/live behavior diverge.

Therefore:

- TradingView Strategy Tester is a research aid, not the final acceptance engine.
- The canonical acceptance backtest runs in the external replay engine.
- Any Pine strategy result must state its execution settings and cost assumptions.

References:

- https://www.tradingview.com/pine-script-docs/concepts/strategies/
- https://www.tradingview.com/pine-script-docs/language/declaration-statements/

---

# 29. Learning Architecture

The Learning Engine is designed around **experience attribution**, not uncontrolled online reinforcement learning.

## 29.1 Experience record

After a trade closes, store:

```text
market_state_snapshot
scenario_snapshot
evidence_snapshot
risk_snapshot
execution_snapshot
fill_sequence
position_path
MFE
MAE
holding_time
exit_reason
gross_pnl
costs
net_pnl
net_R
regime
session
```

## 29.2 MFE / MAE

Maximum Favorable Excursion and Maximum Adverse Excursion are measured from the actual entry path.

They help distinguish:

- bad entry;
- good analysis but poor execution;
- correct direction but poor target;
- good setup but premature exit;
- inherently weak scenario.

## 29.3 Evidence attribution

For every trade, the system asks:

- Which evidence supported the chosen scenario?
- Which opposing evidence existed?
- Which evidence changed before entry?
- Which evidence was predictive of outcome?
- Which evidence was redundant?
- Which evidence behaved differently across regimes?

## 29.4 Reward / penalty

The project uses reward/penalty conceptually as an attribution ledger, not as immediate self-modification.

Example:

```text
Outcome = +1.8R

Liquidity Sweep: supportive
Absorption: strongly supportive
Displacement: supportive
Harmonic: neutral
Candle pattern: neutral
Session: supportive
```

The system accumulates these observations across large samples.

A single successful trade cannot promote a weak event.

## 29.5 Parameter update workflow

```text
Experience Ledger
      ↓
Feature / Event Statistics
      ↓
Candidate Parameter Set
      ↓
Train / Validation
      ↓
Walk-Forward OOS
      ↓
Stress Test
      ↓
Human/Automated Promotion Gate
      ↓
New Production Version
```

## 29.6 Non-stationarity

The market changes. The Learning Engine tracks:

- feature distribution drift;
- regime frequency drift;
- event success-rate drift;
- execution-cost drift;
- latency drift;
- calibration drift.

When drift exceeds configured thresholds, the engine does not blindly retrain. It enters one of:

```text
MONITOR
DEGRADE
RECALIBRATE
RESEARCH_REQUIRED
SAFE_MODE
```

## 29.7 Overfitting defenses

Mandatory defenses:

- strict temporal splits;
- no random shuffling of time-series folds;
- walk-forward evaluation;
- out-of-sample holdouts;
- parameter-count control;
- regularization;
- event ablation tests;
- regime-specific analysis;
- cost stress testing;
- Monte Carlo trade-order analysis;
- stability checks across nearby parameter values;
- minimum sample sizes;
- model version locking.

## 29.8 First ML model

The first learned model is a supervised outcome model/ranker using LightGBM after the deterministic engine proves feature integrity.

Targets should not simply be “next candle up/down”. Prefer trading-relevant labels such as:

```text
hit_target_before_invalidation
net_R_after_costs
MFE_before_MAE_threshold
execution_feasibility
```

The deterministic rule engine remains the policy boundary. ML ranks and calibrates scenario quality rather than inventing unrestricted trades.

---

# 30. Scenario Labeling for ML

Each candidate scenario receives a label only after its defined evaluation horizon ends.

Example:

```text
entry = E
invalidation = S
primary_target = T
max_holding_time = H
```

Label states:

```text
TARGET_FIRST
INVALIDATION_FIRST
TIMEOUT_WITH_PROFIT
TIMEOUT_WITH_LOSS
NOT_EXECUTABLE
```

Net target evaluation includes realistic costs.

If both target and stop are touched inside an interval where timestamp ordering cannot be known, the label must use conservative intrabar ordering or higher-resolution data; it must never choose the favorable outcome merely because it makes the backtest prettier.

---

# 31. Database Schema

The following schema is the minimum canonical model.

## 31.1 Reference tables

### `instruments`

- `instrument_id`
- `symbol`
- `asset_class`
- `venue`
- `tick_size`
- `lot_size`
- `quote_currency`
- `contract_multiplier`
- `status`

### `feeds`

- `feed_id`
- `provider`
- `venue`
- `data_type`
- `timezone`
- `latency_profile`
- `methodology_version`

### `strategies`

- `strategy_id`
- `name`
- `description`
- `risk_profile`
- `version`
- `active`

## 31.2 Time-series tables

### `market_events`

Raw normalized trade/quote events when retained in the database.

### `candles`

- `instrument_id`
- `timeframe`
- `bar_time`
- OHLCV
- session
- quality flags

### `footprint_bars`

- `instrument_id`
- `timeframe`
- `bar_time`
- buy/sell/total/delta
- POC/VAH/VAL
- imbalance summaries
- source feed

### `footprint_rows`

Only retained when required for research or a detected event; partitioned by date/instrument.

## 31.3 Analysis tables

### `market_states`

Stores regime, HTF/MTF state, volatility state, session state, and quality state.

### `liquidity_zones`

Stores every detected liquidity zone and lifecycle state.

### `structure_events`

BOS/CHoCH/swing/displacement events.

### `pattern_events`

Candlestick, classical, harmonic, FVG, OB and phase detections.

### `orderflow_events`

Absorption, exhaustion, delta/imbalance events.

### `macro_events`

Scheduled releases, actuals, revisions, surprise, and event windows.

### `evidence_items`

Every evidence input to fusion.

### `scenarios`

Scenario lifecycle and thesis.

### `scenario_transitions`

Immutable lifecycle transitions with timestamp and reason.

### `decisions`

Final decision object and all gates.

## 31.4 Execution tables

### `trade_intents`

Approved execution specifications.

### `orders`

External order IDs, requested quantities, prices, status.

### `fills`

Actual executions.

### `positions`

Current and historical position state.

### `trade_outcomes`

Final outcome and attribution.

## 31.5 Learning tables

### `experience_ledger`

Immutable one-row-per-trade or one-row-per-scenario experience reference.

### `feature_statistics`

Per-event and per-feature outcome statistics by regime.

### `parameter_sets`

Versioned fusion/risk/strategy parameters.

### `model_versions`

Model artifacts, code commit, training dataset, feature schema, calibration results.

### `drift_metrics`

Population drift and outcome drift.

### `promotion_runs`

Evidence that a candidate model passed all gates.

## 31.6 Operational tables

### `alerts`

Webhook events and delivery status.

### `data_quality_events`

Feed failures and anomalies.

### `system_health`

Service and connector heartbeat state.

### `audit_log`

Every security-sensitive and trade-sensitive state change.

---

# 32. Event Schemas

All internal messages use versioned JSON/Protobuf-style contracts with:

```text
event_id
schema_version
event_type
event_time
receive_time
source
trace_id
correlation_id
payload
```

Example market-state message:

```json
{
  "event_type": "market.state.updated",
  "schema_version": "1.0",
  "event_time": "2026-09-27T02:00:00Z",
  "instrument": "EXAMPLE",
  "timeframe": "5m",
  "regime": "TREND_PULLBACK",
  "htf_bias": "BULLISH",
  "volatility_percentile": 62.4,
  "data_quality": "HEALTHY"
}
```

The actual production contracts must be generated/validated from typed schemas, not hand-maintained strings.

---

# 33. Full End-to-End Data Flow

## 33.1 From incoming market data to a candle

```text
Market provider event
→ adapter
→ timestamp normalization
→ duplicate check
→ sequence/order check
→ instrument validation
→ event persisted
→ event published
→ candle aggregator
→ candle persisted
```

## 33.2 Candle to analysis

```text
Closed/developing candle
→ volatility features
→ session state
→ structure update
→ liquidity map update
→ footprint update
→ SMC event detection
→ pattern detection
→ macro context merge
→ market-state snapshot
```

## 33.3 Analysis to evidence

Every detector emits event records.

The Evidence Builder converts those events into contextual evidence:

```text
raw event
→ quality
→ freshness
→ location relevance
→ regime relevance
→ correlation group
→ directional contribution
```

## 33.4 Evidence to scenario

```text
candidate location
→ generate scenarios
→ attach supporting evidence
→ attach opposing evidence
→ calculate raw scenario score
→ apply vetoes
→ create/update lifecycle state
```

## 33.5 Scenario to risk

```text
TRIGGERED scenario
→ cost estimate
→ expected path
→ invalidation
→ position size
→ portfolio exposure
→ event risk
→ execution quality
→ No-Trade Engine
```

## 33.6 Risk to execution

Only after all gates pass:

```text
AUTHORIZED
→ trade intent
→ execution adapter
→ order
→ acknowledgement
→ fill(s)
→ position update
```

## 33.7 Execution to trade monitoring

```text
position live
→ monitor structure
→ monitor flow
→ monitor target/invalidation
→ monitor latency and cost
→ adjust/exit only under predefined management rules
```

## 33.8 Trade close to learning

```text
exit/final fill
→ outcome reconstruction
→ MFE/MAE
→ gross/net P&L
→ evidence attribution
→ experience ledger
→ statistics
→ drift checks
→ candidate model updates
```

No step bypasses persistence or auditability.

---

# 34. Trade Management Logic

## 34.1 Initial position

At entry, the position records:

- intended scenario;
- actual entry;
- actual size;
- initial stop;
- targets;
- time horizon;
- cost budget.

## 34.2 Management events

Trade management is triggered only by explicit events such as:

- target reached;
- invalidation reached;
- structural continuation validated;
- structure failure;
- severe flow reversal;
- time expiry;
- risk emergency;
- execution/reconciliation anomaly.

## 34.3 Partial exits

Partial take-profit rules are predetermined by strategy version. The system cannot dynamically invent percentages solely because the trade is profitable.

## 34.4 Breakeven

Breakeven is allowed only when supported by an explicit strategy rule or when a new structural state reduces the probability of continuation sufficiently. It is not an automatic emotional “protect profit” rule.

---

# 35. Dashboard and TradingView Presentation

## 35.1 Chart layers

TradingView display order:

1. major liquidity map;
2. active dealing range;
3. HTF/MTF structure;
4. active scenario;
5. entry / invalidation / targets;
6. selected flow annotations;
7. event markers.

Do not render every internal event simultaneously.

## 35.2 Information panel

Minimum live panel:

```text
Market Regime
HTF Bias
MTF Setup State
Liquidity Above / Below
Flow State
Delta
Volatility State
Session
Macro Risk
Active Scenario
Trigger Status
Risk Status
Execution Status
```

## 35.3 Reasoning trace

The dashboard provides a collapsible trace:

```text
WHY ACTIVE?
- Sell-side liquidity identified
- Sweep confirmed
- Absorption candidate
- Bullish displacement confirmed
- MTF structure reclaimed

WHAT AGAINST IT?
- HTF resistance nearby
- Macro event in 18 minutes

WHY WAIT?
- Trigger not confirmed
```

This is intentionally more valuable than a “BUY 91%” label.

---

# 36. TradingView Webhook Protocol

The Pine alert payload should be minimal and sufficient to identify the event; the external engine must re-read canonical state before authorizing any order.

Example:

```json
{
  "schema_version": "1.0",
  "source": "tradingview",
  "alert_id": "{{id}}",
  "instrument": "{{ticker}}",
  "bar_time": "{{time}}",
  "timeframe": "{{interval}}",
  "event": "scenario.trigger_candidate",
  "price": "{{close}}",
  "idempotency_key": "generated-deterministically"
}
```

The webhook service:

1. authenticates;
2. validates schema;
3. checks duplicate `idempotency_key`;
4. persists raw alert;
5. responds immediately;
6. publishes to NATS;
7. canonical decision engine revalidates current state;
8. only then can risk/execution proceed.

---

# 37. Security and Operational Safety

## 37.1 Secrets

- secrets never in Pine source;
- no credentials inside webhook messages;
- encrypted storage;
- restricted service accounts;
- key rotation;
- audit access.

## 37.2 Kill switches

Three independent kill switches:

1. System-wide.
2. Strategy-specific.
3. Instrument-specific.

The execution adapter must honor all three.

## 37.3 Safe startup

On restart:

```text
start
→ load configuration
→ verify database
→ verify feeds
→ reconcile broker
→ rebuild hot state
→ verify no orphaned orders
→ enter SAFE mode
→ run health checks
→ enable trading only if all gates pass
```

## 37.4 Safe shutdown

No new orders after shutdown begins. Existing positions follow the configured recovery/monitoring policy.

---

# 38. Testing Strategy

Testing is divided into six layers.

## 38.1 Unit tests

Every detector receives deterministic fixtures.

Examples:

- exact sweep fixture;
- near-miss sweep fixture;
- BOS with wick-only break;
- true displacement;
- weak expansion;
- FVG formation/fill;
- absorption candidate/invalid case;
- harmonic ratio tolerance.

## 38.2 Property tests

Verify invariants such as:

- score always remains within configured bounds;
- scenario cannot move from COMPLETED back to ACTIVE;
- risk cannot exceed cap;
- an invalidated scenario cannot authorize a trade;
- duplicate webhook does not create duplicate order intents;
- timestamps remain monotonic inside a feed sequence.

## 38.3 Replay tests

Feed historical data through the same event pipeline used by live mode.

Acceptance criterion: deterministic results from the same dataset/version.

## 38.4 Integration tests

Test:

```text
feed → ingestion → DB → event bus → analysis → scenario → risk → execution mock
```

## 38.5 Failure-injection tests

Inject:

- missing bars;
- duplicate trades;
- delayed webhook;
- broker timeout;
- partial fill;
- stale quote;
- disconnected exchange;
- database restart;
- Redis loss;
- event-provider outage.

The expected behavior is safe degradation, not continued blind trading.

---

# 39. Validation Program

## 39.1 Phase A — Deterministic research validation

Goal: prove that every event is correctly detected.

Acceptance:

- zero known future-data leaks;
- 100% deterministic replay on fixed fixtures;
- all hard gates tested;
- every event has a timestamp and source;
- every scenario has a complete lifecycle;
- every order can be traced to a scenario.

## 39.2 Phase B — Backtest with realistic costs

Use realistic spread, fees, slippage, latency, and partial-fill assumptions.

Do not optimize on the final holdout.

## 39.3 Phase C — Walk-Forward

Default research protocol:

```text
2,000 eligible historical candidates → TRAIN
500 candidates → VALIDATION
500 candidates → OUT-OF-SAMPLE
roll forward by 500 candidates
```

The split is time-ordered and an embargo equal to at least the maximum strategy evaluation horizon is applied between adjacent sets.

The exact sample count can be increased when several regimes require more observations; it is never reduced merely to pass a gate.

## 39.4 Phase D — Out-of-Sample holdout

One untouched final period is frozen before model promotion. No parameter or event definition can be tuned against this period.

## 39.5 Phase E — Paper trading

The system receives live market data but submits no real orders.

Minimum gate:

- at least 500 eligible scenario evaluations or four continuous weeks, whichever is longer;
- measured live spread and latency;
- zero unexplained reconciliation failures;
- decision/execution trace complete for every signal.

## 39.6 Phase F — Shadow Mode

The system creates real order intents and expected fills but does not submit them. Actual market conditions are recorded for slippage and latency comparison.

## 39.7 Phase G — Controlled Live

Start with a very small risk budget. Increase only after stability gates are passed.

---

# 40. Production Acceptance Criteria

A strategy/model version cannot be promoted merely because it made money in one backtest.

Minimum starting acceptance gates:

1. **Data integrity:** no unexplained missing/duplicated critical data.
2. **Leakage:** zero unresolved future-data leakage findings.
3. **Reproducibility:** same dataset + same version → same result.
4. **Out-of-sample expectancy:** positive net expectancy after realistic costs.
5. **Profit factor:** at least 1.15 on the aggregate OOS set as an initial engineering gate.
6. **Stability:** median positive expectancy across the walk-forward folds; no isolated fold responsible for the majority of total P&L.
7. **Cost robustness:** strategy remains viable under stress-cost assumptions.
8. **Drawdown:** within the declared risk budget under historical and Monte Carlo trade-order stress.
9. **Execution feasibility:** p95 measured latency and slippage remain within the model budget.
10. **Calibration:** if a probability is shown, calibration error must pass the configured threshold on held-out data.
11. **Drift:** no unresolved severe feature/outcome drift.
12. **Operational safety:** reconciliation, kill-switch, startup, and shutdown tests pass.

These are project acceptance gates, not a promise that meeting them guarantees future profitability.

---

# 41. Model and Strategy Promotion Gates

Every promoted artifact includes:

```text
code_commit
feature_schema
parameter_set
training_window
validation_window
OOS_window
cost_model
data_source_versions
model_artifact_hash
calibration_artifact
approval_timestamp
```

Promotion is atomic.

Rollback target is always the last known-good version.

Two consecutive failed production validation cycles trigger automatic rollback to the last approved configuration.

---

# 42. Non-Stationarity and Drift Handling

## 42.1 Feature drift

Compare live feature distributions to the training reference using statistics such as PSI, KS, or Wasserstein distance.

## 42.2 Outcome drift

Track:

- event conditional expectancy;
- win-rate conditional on cost model;
- MFE/MAE distribution;
- calibration drift;
- regime-level performance.

## 42.3 Execution drift

Track:

- spread;
- slippage;
- latency;
- fill ratio;
- rejection ratio.

A strategy may remain analytically correct but become non-executable because costs worsen; execution drift therefore can independently disable the strategy.

---

# 43. Research Method: Ablation and Incremental Value

Every concept must justify its existence.

For each event or subsystem, research compares:

```text
Base model
Base + Feature
Base + Feature - Feature
```

A feature is retained only if it provides stable incremental value after:

- realistic costs;
- out-of-sample testing;
- regime segmentation;
- parameter perturbation;
- correlation controls.

This is how the project decides whether something like a harmonic pattern, candle name, or specific footprint event is useful rather than assuming it is useful because traders use the label.

---

# 44. Concepts Explicitly Rejected as First-Class Signals

## 44.1 “Institutional order detected”

Rejected because public chart data cannot reliably identify the actor behind a price event. We can detect price/volume behavior consistent with a zone hypothesis.

## 44.2 Pattern-count trading

Rejected because counting named patterns double-counts correlated evidence.

## 44.3 Raw RSI/indicator stacking

Rejected as a core architecture because it creates redundant signals and encourages threshold tuning without causal structure.

## 44.4 LLM deciding the trade

Rejected as the primary decision mechanism. LLMs may explain, summarize, assist research, and inspect anomalous logs, but the live decision path must be deterministic/statistical, testable, and bounded.

## 44.5 Fully autonomous online reinforcement learning

Rejected in the first production version. A model that changes policy during live losses can amplify a regime change rather than learn safely. Controlled offline learning comes first.

## 44.6 Guaranteed liquidity prediction

Rejected. Liquidity maps are inferred target/interaction zones, not guaranteed destinations.

---

# 45. Common Failure Modes — Explicitly Forbidden

## 45.1 Lookahead bias

Deadly because it manufactures impossible foresight.

## 45.2 Repainting signals presented as historical certainty

Deadly because it makes the chart appear better than live execution.

## 45.3 Optimizing on the final test set

Deadly because the “out-of-sample” set becomes training data by repeated inspection.

## 45.4 Ignoring transaction costs

Deadly for scalp systems because the gross edge may be smaller than friction.

## 45.5 Ignoring latency

Deadly when the average holding period is close to the execution timescale.

## 45.6 Using OHLC-only assumptions to claim order-flow truth

Deadly because candle geometry cannot magically recreate full market depth.

## 45.7 Treating delta as direction

Deadly because aggressive flow can be absorbed.

## 45.8 Treating every FVG/OB as valid

Deadly because context and market regime determine whether a zone matters.

## 45.9 Letting one trade update the model

Deadly because the learning system becomes noise-reactive.

## 45.10 Adding more features instead of measuring contribution

Deadly because complexity increases false confidence and overfitting.

## 45.11 Backtesting one symbol in one regime

Deadly because the engine learns the instrument's history rather than a transferable mechanism.

## 45.12 Assuming broker fills equal backtest fills

Deadly because real fills include queue position, spread, latency, rejection, and partial execution.

## 45.13 Making risk an afterthought

Deadly because analytical accuracy does not control drawdown.

## 45.14 Allowing the model to override a hard risk block

Deadly because it turns confidence into permission to break safety rules.

## 45.15 Building the UI before the canonical data model

Deadly because visual labels then become the architecture instead of a consequence of it.

---

# 46. Build Order

The project is built in the following dependency order. No later layer is allowed to hide an incomplete earlier layer.

## Phase 0 — Repository and operating system

Build:

- monorepo structure;
- Python services;
- Pine project;
- schema package;
- test harness;
- Docker development environment;
- linting/type checking;
- CI;
- versioning rules.

Exit gate:

- clean build;
- deterministic test runner;
- local database/event bus start;
- no secrets in repository.

## Phase 1 — Canonical data ingestion

Build:

- one reference market-data adapter;
- normalization;
- event timestamps;
- quality flags;
- candle builder;
- immutable raw storage.

Exit gate:

- gap/duplication tests pass;
- replay can reproduce candles exactly.

## Phase 2 — Volatility, session, and context

Build:

- ATR/realized volatility;
- session engine;
- opening range;
- HTF/MTF structure state;
- regime classification.

Exit gate:

- state transitions are deterministic and visualized.

## Phase 3 — Liquidity and structure

Build:

- swings;
- BOS/CHoCH;
- liquidity zones;
- sweeps;
- FVG;
- Order Block hypothesis;
- premium/discount.

Exit gate:

- event fixtures and replay tests pass;
- no known lookahead.

## Phase 4 — Footprint/order flow

Build:

- feed footprint adapter;
- TradingView footprint mirror where supported;
- delta;
- POC/VAH/VAL;
- imbalances;
- absorption/exhaustion.

Exit gate:

- event calculations match source/reference data within declared tolerance.

## Phase 5 — Pattern and phase engines

Build:

- candlestick feature families;
- classical structures;
- harmonics;
- Wyckoff-style state candidates.

Exit gate:

- ablation harness exists before these features are allowed into live scoring.

## Phase 6 — Evidence Fusion

Build:

- evidence schema;
- group weights;
- correlation control;
- contradiction scoring;
- scenario explanation.

Exit gate:

- every scenario can show its full evidence chain.

## Phase 7 — Scenario Engine

Build:

- lifecycle;
- trigger rules;
- invalidation;
- target map;
- expiry;
- competing scenarios.

Exit gate:

- no scenario can authorize a trade without an explicit trigger and invalidation.

## Phase 8 — No-Trade and Risk

Build:

- hard blocks;
- cost model;
- position sizing;
- portfolio risk;
- kill switches.

Exit gate:

- every risk violation results in a hard rejection.

## Phase 9 — Replay/backtest

Build:

- deterministic replay;
- historical costs;
- latency simulation;
- partial-fill simulation;
- trade metrics;
- walk-forward tooling.

Exit gate:

- OOS process and reports are automated.

## Phase 10 — TradingView integration

Build:

- Pine v6 indicator;
- visualization;
- webhook;
- signal mirror;
- alert validation.

Exit gate:

- Pine and external engine agree within declared tolerance on the shared subset of calculations.

## Phase 11 — Execution integration

Build:

- broker/exchange adapter;
- order state machine;
- fills;
- reconciliation;
- failure injection.

Exit gate:

- paper and shadow modes pass operational gates.

## Phase 12 — Learning laboratory

Build:

- experience ledger;
- evidence attribution;
- feature statistics;
- calibration;
- candidate model training;
- drift monitoring.

Exit gate:

- model promotion is versioned and reproducible.

## Phase 13 — Controlled live

Start with the smallest permitted risk.

Exit gate for increasing risk:

- live execution quality stable;
- no unresolved safety incidents;
- strategy remains within risk and drift budgets.

---

# 47. Repository Structure

```text
ai-market-reasoning-engine/
├── apps/
│   ├── api/
│   ├── dashboard/
│   ├── replay/
│   └── worker/
├── pine/
│   ├── indicators/
│   ├── libraries/
│   └── alerts/
├── services/
│   ├── ingestion/
│   ├── market_state/
│   ├── liquidity/
│   ├── orderflow/
│   ├── structure/
│   ├── patterns/
│   ├── macro/
│   ├── fusion/
│   ├── scenarios/
│   ├── risk/
│   ├── execution/
│   └── learning/
├── packages/
│   ├── schemas/
│   ├── features/
│   ├── math/
│   ├── backtest/
│   └── common/
├── data/
├── migrations/
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   ├── replay/
│   └── fixtures/
├── docs/
│   ├── architecture/
│   ├── runbooks/
│   └── research/
├── infra/
├── scripts/
└── pyproject.toml
```

The repository is organized by responsibility so a future contributor cannot accidentally place execution logic inside the analysis layer.

---

# 48. Observability

Every component emits:

- structured logs;
- metrics;
- traces with `trace_id`/`scenario_id`/`trade_intent_id`.

Core metrics:

### Data

- feed latency;
- missing bars;
- duplicate events;
- out-of-order events.

### Analysis

- event counts;
- detector runtime;
- active scenarios;
- veto rates.

### Risk

- blocked trades;
- risk utilization;
- daily drawdown;
- emergency shutdowns.

### Execution

- acknowledgement latency;
- fill latency;
- fill ratio;
- slippage;
- rejection rate.

### Learning

- feature drift;
- calibration error;
- OOS expectancy;
- model promotion frequency;
- strategy degradation.

---

# 49. Failure Handling Matrix

| Failure | Action | Trading state |
|---|---|---|
| Market feed stale | Stop new entries | SAFE |
| TradingView webhook duplicate | Ignore duplicate | RUNNING |
| Database unavailable | Stop new orders | SAFE |
| Redis unavailable | Stop state-dependent execution | SAFE |
| Broker disconnected | Stop new orders; reconcile on reconnect | SAFE |
| Position cannot reconcile | Freeze affected instrument | LOCKED |
| Macro feed unavailable | Apply configured macro-data policy; for high-impact uncertainty, block | SAFE/DEGRADED |
| Excessive latency | Block scalp entries | SAFE |
| Spread spike | Block entries | SAFE |
| Model artifact mismatch | Refuse startup | SAFE |
| Drift severe | Disable affected strategy | RESEARCH_REQUIRED |
| Risk limit breach | Stop new orders | LOCKED |
| Kill switch | Stop all new orders and optionally flatten | EMERGENCY |

---

# 50. Decision Precedence

When subsystems disagree, use this order:

```text
1. Security / System Health
2. Data Integrity
3. Position / Broker Reconciliation
4. Hard Risk Limits
5. Execution Feasibility
6. Scenario Invalidation
7. Macro Event Risk
8. Market Context
9. Evidence Fusion
10. Pattern Preference
```

A lower-priority layer cannot override a higher-priority block.

---

# 51. Minimum Viable Reasoning Engine

The first useful release is deliberately smaller than the full vision.

It must include:

```text
OHLCV
+ Volatility
+ Sessions
+ HTF/MTF Structure
+ Liquidity Map
+ Sweep
+ BOS/CHoCH
+ Displacement
+ FVG
+ Footprint Delta / POC / VA where available
+ Basic Absorption
+ Evidence Fusion
+ Scenario Engine
+ No-Trade Engine
+ Cost-Aware Risk
+ Replay Backtest
+ TradingView Visualization
```

Harmonics, advanced classical recognition, ML ranking, and adaptive parameter learning are added only after this core is validated.

This ordering protects the project from spending months optimizing a beautiful pattern layer on top of unreliable data and risk plumbing.

---

# 52. What “Professor-Level” Means in This Architecture

The system is not called “professor” because it produces complicated explanations. It earns that role only if it can consistently answer, with evidence:

```text
WHERE are we?
WHAT regime are we in?
WHERE is meaningful liquidity?
WHAT happened when price interacted with it?
WHO is apparently aggressive in the available flow data?
DID that aggression produce result?
WHAT structure changed?
WHAT scenarios explain the state?
WHAT evidence supports each scenario?
WHAT evidence contradicts it?
WHAT would invalidate it?
WHAT is the best executable location if any?
WHAT does execution cost?
WHAT is the maximum acceptable risk?
WHEN should we do nothing?
WHAT actually happened after the decision?
WHICH observations were useful?
HAS the market regime changed enough to require recalibration?
```

If the system cannot answer these questions from stored data, the feature is not considered production-complete.

---

# 53. Final Operating Principle

The final architecture is:

```text
Observe
  ↓
Normalize
  ↓
Validate
  ↓
Contextualize
  ↓
Map Liquidity
  ↓
Read Flow
  ↓
Detect Structure
  ↓
Interpret Patterns
  ↓
Apply Macro Context
  ↓
Fuse Evidence
  ↓
Construct Competing Scenarios
  ↓
Wait for Trigger
  ↓
Reject Unsafe Situations
  ↓
Size Risk
  ↓
Execute Under Constraints
  ↓
Monitor Actual Market Path
  ↓
Close / Invalidate
  ↓
Measure Real Outcome
  ↓
Attribute Evidence
  ↓
Detect Drift
  ↓
Research Candidate Updates
  ↓
Validate Out-of-Sample
  ↓
Promote Only Proven Versions
```

The engine is successful only when **analysis, decision, risk, execution, and learning remain separate but causally connected**.

The system must prefer `NO TRADE` over a low-quality trade, `WAIT` over an unconfirmed trigger, and `INVALIDATED` over rationalizing a failed thesis. The goal is not to predict every movement. The goal is to maintain a disciplined representation of market state and act only when the expected opportunity remains valid after evidence, risk, and execution constraints.

---

# Appendix A — Current TradingView References

The following vendor documentation was checked against the current TradingView Pine documentation available on 2026-09-27:

1. Pine Script v6 limitations:  
   https://www.tradingview.com/pine-script-docs/writing/limitations/
2. Pine Script v6 release notes / footprint introduction:  
   https://www.tradingview.com/pine-script-docs/release-notes/
3. Other timeframes and data:  
   https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/
4. Execution model:  
   https://www.tradingview.com/pine-script-docs/language/execution-model/
5. Strategies / broker emulator:  
   https://www.tradingview.com/pine-script-docs/concepts/strategies/
6. Repainting:  
   https://www.tradingview.com/pine-script-docs/v5/concepts/repainting/
7. Webhook alerts:  
   https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
8. Pine economic data:  
   https://www.tradingview.com/support/solutions/43000665359-what-economic-data-is-available-in-pine/

---

# Appendix B — Definition of Done

The project is considered technically complete only when all of the following are true:

- A live market event can enter the system and become canonical data.
- Data quality is checked before analysis.
- The three-timeframe hierarchy is maintained.
- Liquidity zones have a lifecycle.
- SMC events have deterministic definitions.
- Footprint metrics are source-labelled and validated.
- Patterns are candidates, not automatic orders.
- Macro is context/risk on short timeframes.
- Evidence is fused with correlation controls.
- Scenarios can be created, upgraded, triggered, invalidated, expired, and completed.
- No-Trade decisions are explicit.
- Risk is calculated before execution.
- Costs, spread, slippage, latency, and partial fills are modeled.
- TradingView alerts reach an authenticated endpoint and are idempotent.
- Broker state is reconciled.
- Every trade has an immutable causal trace.
- Replay and walk-forward runs are reproducible.
- OOS validation exists.
- Paper and shadow modes exist.
- Learning operates through versioned candidates rather than uncontrolled live mutation.
- Drift monitoring exists.
- Rollback exists.
- Kill switches exist.
- A future engineer can inspect one trade and reconstruct why it happened, why it was allowed, what actually happened, and what the system learned from it.

**This document is the architectural source of truth. Implementation documents may refine interfaces and numerical parameters, but they may not silently change the responsibility boundaries, causality chain, safety hierarchy, or validation philosophy defined here.**
