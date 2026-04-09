# V37 Reconstruction Notes

This note documents the calculations and decision tools used by [Traderv37.py](/Users/vasudravinarendran/Documents/Prosperity/MyProsperity/Bots/Traderv37.py) and the reconstructed equivalent [Traderv51.py](/Users/vasudravinarendran/Documents/Prosperity/Prosperity/Bots/Traderv51.py).

## Architecture

- `BaseProductTrader`
  - Normalizes book state.
  - Maintains `mid_history`.
  - Maintains per-product persistent memory through `traderData`.
  - Owns order capacity and quote clamping.
- `EmeraldsTrader`
  - Anchored market maker around a fixed reference.
- `TomatoesTrader`
  - Short-horizon forecasting + flow inference + breakout overlay + inventory-aware execution.
- `Trader`
  - Dispatches per product and serializes `traderData`.

## Shared State And Persistence

- `mid_history`
  - Rolling mid history per product.
- `product_memory`
  - Product-specific dictionaries stored in `traderData`.
- `prev_book`
  - Previous top-of-book snapshot for flow inference.
- `activity_history`
  - Rolling book-activity magnitudes.
- `signed_flow_history`
  - Rolling signed book impulse.
- `bias_history`
  - Rolling normalized flow bias.
- `price_pressure_history`
  - Rolling short-horizon price pressure.
- `compression_history`
  - Rolling spread compression.
- `imbalance_history`
  - Rolling L1 imbalance.
- `micro_premium_history`
  - Rolling micro-mid premium.
- `pressure_buckets`
  - Decaying price-bucket memory used as support/resistance pressure.

## EMERALDS Model

EMERALDS is deliberately simple and anchored.

- Fair value:
  - `REFERENCE_WEIGHT * REFERENCE_PRICE + MID_WEIGHT * mid + MICRO_WEIGHT * micro`
- Inventory adjustment:
  - `fair - projected_position * INVENTORY_SKEW`
- Aggressive taking:
  - Three distance tiers from adjusted fair.
  - Inventory expands take size when offside and shrinks it when already full.
- Clearing:
  - If long and best bid is good enough, hit bid to reduce.
  - If short and best ask is good enough, lift ask to reduce.
- Passive quoting:
  - Builds a default quote around fair.
  - Joins or steps ahead of outer book levels when those levels are sufficiently far from fair.
  - Skews quote pair by one tick when inventory is near the soft limit.

## TOMATOES Inputs

The TOMATOES model uses these real-time inputs:

- `mid`
- `micro`
- `spread`
- `imbalance`
- `recent_average`
- `momentum`
- Previous book state from `prev_book`
- Persistent short-window and long-window flow histories

## TOMATOES Forecast Stack

### 1. Regression Forecast

- Windowed linear regression over the last `REGRESSION_WINDOW` mids.
- Outputs:
  - `predicted_now`
  - `predicted_next`
  - `fit_quality`
  - `volatility`
- Core signal:
  - `regression_edge = (predicted_next - mid) * ALPHA_EDGE_SCALE`

### 2. Book-Delta Flow Inference

Flow is inferred from changes in:

- best bid / ask price steps
- bid / ask queue depletion
- bid / ask queue rebuild
- microprice drift
- mid drift
- imbalance drift
- spread compression

This produces:

- `activity`
- `signed_flow`
- `bias`
- `price_pressure`
- `flow_acceleration`
- `compression`
- `persistence`

### 3. Burst Detection

`burst_score` is a percentile-based breakout precursor.

- compares current `activity` against recent windows
- requires directional agreement from flow bias
- dampens when imbalance, pressure, or persistence disagree
- boosts when compression and acceleration align

### 4. Pressure Memory

`pressure_buckets` creates decaying support/resistance memory.

- positive impulses reinforce bid-side support buckets
- negative impulses reinforce ask-side resistance buckets
- nearby buckets feed `pressure_bias`

### 5. Hybrid Alpha

`hybrid_alpha` blends:

- recent average
- mid
- micro
- flow-shifted midpoint

Then `guarded_hybrid_alpha` damps it when:

- regime is `range`
- it conflicts with regression edge
- it conflicts with imbalance
- it conflicts with momentum
- it aligns with already-large inventory

### 6. Predicted Edge

The final directional forecast is:

- regression component
- guarded hybrid alpha blend
- breakout follow-through
- pressure-bias follow-through

This is the main edge used for regime classification, targeting, and execution.

## TOMATOES Regime Logic

`classify_state` returns one of:

- `trend_up`
- `trend_down`
- `range`
- `volatile`

It uses:

- predicted edge size
- fit quality
- volatility
- breakout score
- flow bias
- imbalance
- momentum
- micro vs mid relationship

## Targeting And Inventory Control

### Target Band

`target_band` maps regime and conviction to an allowed inventory band.

- strong `trend_up` widens positive inventory bands
- strong `trend_down` widens negative inventory bands
- `range` keeps the band narrow around zero
- `volatile` shrinks the band sharply

### Target Position

`target_position`:

- clips current inventory into the current target band
- otherwise pushes to the upper band in `trend_up`
- pushes to the lower band in `trend_down`
- centers at `0` in `range`

### Reservation Adjustment

Reservation price depends on:

- `GAMMA_*` by regime
- inventory gap relative to target
- volatility
- time remaining
- regime-specific directional bias

## TOMATOES Fair Value

Fair value combines:

- `MID_WEIGHT * mid`
- `MICRO_WEIGHT * micro`
- `HISTORY_WEIGHT * recent_average`
- `REGRESSION_WEIGHT * predicted_next`
- `IMBALANCE_WEIGHT * scaled_imbalance`
- `FAIR_ALPHA_WEIGHT * hybrid_alpha`
- `PRESSURE_BIAS_SCALE * pressure_bias`
- target-position bias
- residual mean reversion in `range`
- trend continuation bonus in `trend_up` / `trend_down`

Then adjusted fair subtracts:

- `projected_position * INVENTORY_SKEW`
- reservation adjustment

## TOMATOES Aggressive Execution

### Take Edge

`take_edge` depends on:

- base take edge
- wide-spread penalty
- inventory sign and size
- toxicity
- regime direction
- predicted-edge agreement
- breakout alignment or opposition

### Take Thresholds

Each side then adds:

- trend hold-exit bonuses
- breakout hold bonuses
- time remaining pressure
- volatility hold penalty

### Quantity Rules

- `range`
  - can take without forcing toward target
- directional regimes
  - takes are capped toward target
- `MAX_TAKE_SIZE`
  - hard cap per aggressive action

## TOMATOES Passive Execution

### Quote Edge

Half-spread is widened or tightened using:

- base quote edge
- current spread
- inventory pressure
- regime
- volatility
- gamma-scaled inventory effect
- time remaining
- breakout tightening in aligned trends

### Quote Placement

- base quotes around adjusted fair
- trend-up pushes buy quotes upward when still building long
- trend-up lifts sells when already long
- trend-down mirrors that behavior
- `volatile` with low inventory may disable both passive sides
- breakout can shift the quote pair by one additional tick

### Passive Size

Passive size depends on:

- spread
- regime
- toxicity
- inventory sign

### Passive Side Allowance

Passive participation is disabled when:

- already beyond soft limit on that side
- low-inventory `volatile` regime

## What Was Preserved In V51

The reconstructed [Traderv51.py](/Users/vasudravinarendran/Documents/Prosperity/Prosperity/Bots/Traderv51.py) preserves the `v37` formulas but cleans the flow of the TOMATOES run path:

- `SignalSnapshot`
  - gathers the full forecast/execution state in one place
- `build_signal_snapshot`
  - reconstructs all signal calculations before execution
- `trend_hold_adjustment`
  - isolates trend-specific threshold shifts
- `breakout_hold_adjustment`
  - isolates breakout hold adjustments
- `hold_adjusted_take_threshold`
  - centralizes the full aggressive threshold calculation
- `aggressive_take_quantity`
  - centralizes quantity capping toward target

Local verification result:

- `Traderv37` and `Traderv51` are identical on the current local harness
  - day `-1`: `14868.0`
  - day `-2`: `14620.5`

## Optimization Guidance

The reconstructed model should be optimized conservatively.

Good CMA-ES candidates:

- `GAMMA_RANGE`
- `RESERVATION_SCALE`
- `RANGE_RESERVATION_BIAS`
- `SPREAD_VOL_COEF`
- `SPREAD_INV_COEF`
- `SPREAD_TIME_COEF`
- `BASE_TAKE_EDGE`
- `ALPHA_EDGE_SCALE`
- `ALPHA_IMBALANCE_SCALE`
- `INVENTORY_SKEW`
- `SOFT_LIMIT_RATIO`
- `PRESSURE_BIAS_SCALE`
- `BREAKOUT_FOLLOW_SCALE`
- `BREAKOUT_QUOTE_TIGHTEN`
- `BREAKOUT_HOLD_BONUS`

Optimization lessons to keep:

- optimize on average of day `-1` and day `-2`
- penalize one-day regressions instead of rewarding a single large spike
- regularize toward current `v37` defaults so local search does not drift too far from the official best
