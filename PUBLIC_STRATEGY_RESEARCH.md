# Public Strategy Research

This file summarizes reusable ideas from public IMC Prosperity and Optiver competition repos/writeups.

Goal:
- extract tactics we can reuse in our own bots
- separate high-signal ideas from one-off hacks
- focus on ideas that could improve our current EMERALDS / TOMATOES family

Important caveats:
- not every linked repo had a detailed writeup; some were mostly code dumps or lightweight retrospectives
- some Kaggle writeup pages were not directly accessible through the browser tooling, so Optiver notes lean more on public GitHub mirrors and public blog summaries than the Kaggle pages themselves
- many high-ranked teams used product-specific hardcoding in later rounds; those ideas are useful as examples of workflow and state modeling, but not directly portable to EMERALDS / TOMATOES

## Highest-Signal Recurring Ideas

### 1. Price proxy quality matters more than adding more indicators

This is the most repeated winning pattern.

Observed in:
- [Stanford Cardinal, Prosperity 1](https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal)
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)
- [Frankfurt Hedgehogs, Prosperity 3](https://github.com/TimoDiehm/imc-prosperity-3)
- [Alpha Animals, Prosperity 3](https://github.com/CarterT27/imc-prosperity-3)

Recurring pattern:
- stable product: use a fixed or nearly fixed fair
- drifting product: use a cleaner fair proxy than raw mid
- the best fair proxies often came from "large, stable, real maker quotes", not from all visible quotes equally

Reusable idea for us:
- TOMATOES should continue to prioritize a robust fair proxy over extra indicators
- test a size-filtered or wall-filtered fair estimate:
  - identify persistent large-size bid/ask levels
  - compute a "wall mid" or "popular mid"
  - blend that with microprice and our current regression fair

Why this matters:
- our bots already do well when TOMATOES is grounded in a stable internal fair
- this directly matches the "market maker mid" / "wall mid" discoveries from the strongest public writeups

### 2. Inventory clearing is not optional

Observed in:
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)
- [jmerle, Prosperity 2](https://github.com/jmerle/imc-prosperity-2)
- [TimoDiehm, Prosperity 3](https://github.com/TimoDiehm/imc-prosperity-3)

Recurring pattern:
- profitable bots often added explicit "0 EV" or near-0 EV clearing trades
- this was not treated as a bug or a concession; it was part of maximizing future capacity

Reusable idea for us:
- make TOMATOES clearing more explicit and less scattered
- keep one dedicated "inventory relief" path:
  - if inventory is large and there is a neutral or slightly favorable exit, take it
  - avoid spreading inventory penalties across too many knobs

This lines up with:
- our own finding that too many overlapping inventory penalties make the bot overfit and undertrade

### 3. Two-sided quoting should turn into one-sided behavior under strong directional pressure

Observed in:
- [TimoDiehm, Prosperity 3](https://github.com/TimoDiehm/imc-prosperity-3)
- [Chris Roberts, Prosperity 3](https://github.com/chrispyroberts/imc-prosperity-3)
- [YBansal95, Prosperity 3](https://github.com/YBansal95/imc-prosperity-3)

Recurring pattern:
- normal state: market make around fair
- stronger directional state: quote mostly on the favorable side
- still stronger state: allow taking, but do not chase blindly

Reusable idea for us:
- keep our current regime/mode structure, but simplify the action ladder:
  - neutral: two-sided
  - lean: one-sided passive on the alpha side
  - strong: one-sided passive plus small aggressive entry
  - toxic/loaded: clearing / defensive mode

This is more actionable than adding more small bonus terms.

### 4. Mean reversion works best after subtracting a cleaner trend or anchor

Observed in:
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)
- [nicolassinott, Prosperity 1](https://github.com/nicolassinott/IMC_Prosperity)
- [AcreixYuan, Prosperity 2](https://github.com/AcreixYuan/IMC-Prosperity-2)

Recurring pattern:
- use spread/premium residuals rather than raw prices
- hold mean fixed when the economics are fixed, but let volatility estimate adapt quickly
- use z-scores or standardized residuals rather than bare price deviations

Reusable idea for us:
- our `v40.9` branch already showed the right way to use this:
  - keep a detrended residual
  - use it as a chase brake or taker veto
  - do not let it broadly rewrite fair value, regime gating, and passive logic all at once

### 5. Fill probability and expected value should be estimated, not guessed

Observed in:
- [pe049395, Prosperity 2](https://github.com/pe049395/IMC-Prosperity-2024)
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)
- [liyiyan128 Optiver TAC](https://github.com/liyiyan128/optiver-trading-at-the-close)

Recurring pattern:
- good teams reasoned in terms of:
  - edge
  - execution probability
  - inventory utility / risk
- not just fixed spread offsets

Reusable idea for us:
- continue the passive calibration work, but simplify it
- maintain empirical tables keyed by a few high-value buckets only:
  - side
  - quote distance from touch
  - spread bucket
  - imbalance bucket
  - maybe a simple toxic / non-toxic flag
- use these tables only for:
  - passive go/no-go
  - join vs sit-back decision
  - take-vs-wait veto in bad states

This still looks like one of the highest ROI future improvements.

### 6. A strong backtester + replay dashboard is itself an alpha source

Observed in:
- [TimoDiehm, Prosperity 3](https://github.com/TimoDiehm/imc-prosperity-3)
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)
- [CarterT27, Prosperity 3](https://github.com/CarterT27/imc-prosperity-3)
- [jmerle, Prosperity 2](https://github.com/jmerle/imc-prosperity-2)

Recurring pattern:
- top teams repeatedly mention that synchronized order-book/PnL replay was crucial
- many strategic discoveries came from visual inspection of missed trades, not from new indicators

Reusable idea for us:
- this reinforces our current workflow:
  - local Rust backtests
  - official log comparisons
  - Monte Carlo checks
- future work should keep focusing on path analysis:
  - missed good takes
  - bad passive fills
  - inventory stuck at the wrong time

## Concrete Tactics Worth Testing On Our Current Bots

### A. Size-filtered fair for TOMATOES

Idea:
- identify the most persistent large-size bid/ask levels
- compute a "size-filtered fair" from those levels
- blend into the current TOMATOES fair only modestly

Why:
- this is the most transferable idea from the "wall mid" / "market maker mid" findings
- it should help transfer more than adding more reactive alpha

Suggested implementation:
- track top few levels and their sizes
- if one level dominates size on a side for multiple ticks, treat it as a candidate wall
- compute:
  - `wall_mid = (wall_bid + wall_ask) / 2`
- blend:
  - `fair = base_fair * 0.8 + wall_mid * 0.2`
- only apply when both walls are credible

### B. Explicit inventory relief mode

Idea:
- replace many small inventory penalties with:
  - one reservation-price shift
  - one smooth size reduction
  - one explicit neutral-clear rule

Why:
- this is cleaner
- it matches both the papers and the strongest public Prosperity repos

Suggested implementation:
- if `abs(position)` is beyond a threshold and a zero-edge or near-zero-edge unwind is available, take it
- stop double-counting inventory in fair, quote width, take edge, passive size, and target all at once

### C. One-sided quoting ladder

Idea:
- make the neutral/lean/strong/defensive action map more explicit

Suggested ladder:
- `neutral`: quote both sides
- `lean_up/down`: quote only inventory-reducing side plus alpha side if cheap
- `strong_up/down`: quote one side and allow one extra taker entry
- `defensive`: mostly flatten / minimize new risk

Why:
- the top Prosperity writeups are more consistent with this than with many tiny nudges

### D. "Hard mean + fast std" residuals

Observed especially in:
- [Linear Utility, Prosperity 2](https://github.com/ericcccsliu/imc-prosperity-2)

Idea:
- if a spread or premium has a stable center, keep the center fairly fixed
- let the volatility estimate adapt quickly

For us:
- use this on residuals or stretch, not necessarily on raw TOMATOES price
- this could improve:
  - chase brakes
  - one-sided passive veto
  - re-entry timing after pullbacks

### E. Small spike-reversion sidecar

Observed in:
- [CarterT27, Prosperity 3](https://github.com/CarterT27/imc-prosperity-3)
- [Chris Roberts, Prosperity 3](https://github.com/chrispyroberts/imc-prosperity-3)

Idea:
- detect extreme short-term move relative to rolling diff volatility
- trade a small reversion position only when:
  - move exceeds threshold
  - spread is not too wide
  - inventory is not already loaded

For us:
- this is a sidecar only
- not a replacement for the main TOMATOES engine

### F. Runtime-updated classifier / online model ideas

Observed in:
- [YBansal95, Prosperity 3](https://github.com/YBansal95/imc-prosperity-3)

Interesting but medium confidence:
- online logistic regression with small feature set
- retraining periodically on recent history

Takeaway for us:
- the spirit is useful
- but we should probably keep our lighter online learner / filtered state rather than jumping to a bigger runtime model

## Optiver Ideas That Transfer Well

### 1. Feature interactions around imbalance are very useful

Observed in:
- [liyiyan128 Optiver TAC](https://github.com/liyiyan128/optiver-trading-at-the-close)
- [fan2goa1 TAC summary](https://fan2goa1.github.io/mkdocs-material/blog/2023/12/24/kaggle-optiver---trading-at-the-close/)

High-value feature families:
- liquidity imbalance
- market urgency
- microprice
- price pressure
- spread intensity
- imbalance momentum
- lagged returns / lagged pressure
- global or stock-specific normalization features

Best transfer to us:
- keep feature engineering compact, but enrich interaction terms rather than stacking classic TA indicators
- especially promising:
  - `market_urgency = spread * imbalance`
  - `micro_gap`
  - `imbalance_momentum`
  - short lagged differences in microprice / imbalance

### 2. Generalization discipline matters

Observed in:
- [liyiyan128 Optiver TAC](https://github.com/liyiyan128/optiver-trading-at-the-close)

Transferable ideas:
- purged time-series validation
- memory optimization and fast feature pipelines
- favor robust single models / simpler systems over heavy ensembles when deployment or transfer matters

For us:
- this supports our current preference for:
  - lightweight online logic
  - Monte Carlo robustness checks
  - official-log transfer over pure local peak

### 3. Reconstructing synthetic or cross-sectional context can help

Observed in:
- [liyiyan128 Optiver TAC](https://github.com/liyiyan128/optiver-trading-at-the-close)

Transferable idea:
- build a synthetic context signal from multiple instruments or shared market state

For us:
- EMERALDS and TOMATOES are not obviously a stat-arb pair
- but the general lesson is still useful:
  - consider cross-product risk budgeting
  - reduce risk appetite in one product if another is already heavily loaded in the same directional regime

### 4. Competition-specific hacks are dangerous

Observed in:
- [michaelpoluektov ORVP 7th](https://github.com/michaelpoluektov/orvp)

Key lesson:
- some leaderboard gains come from exploiting quirks of the competition setup rather than learning robust market structure

For us:
- avoid overfitting to replay-specific timestamps or brittle official quirks
- prefer ideas that survive:
  - local Rust
  - official logs
  - Monte Carlo

## What Looks Weak or Low ROI For Our Current Bots

### Low ROI

- adding RSI / MACD / oscillator stacks
- replacing the current TOMATOES core with a fully different ML architecture
- broad state machines with many loosely motivated bonus parameters
- making detrended residual a full fair-value engine rather than a small chase brake

### Medium ROI, but only if done carefully

- online classifier upgrades
- explicit volatility forecasting submodels
- cross-product risk terms
- Monte Carlo data augmentation for threshold selection

### High ROI

- better fair proxy from persistent large quotes
- simpler inventory relief architecture
- one-sided quoting ladder under strong alpha
- empirical fill/adverse-selection calibration
- compact microstructure feature interactions

## Recommended Next Experiments

### Best next experiment

Add a small "wall mid" / "popular mid" layer to the current best family:
- start from [Traderv39_2.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv39_2.py) or [Traderv40_9_2.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv40_9_2.py)
- estimate a size-filtered fair from persistent large bid/ask levels
- blend it lightly into TOMATOES fair
- do not change the rest of the execution stack initially

### Second-best experiment

Refactor inventory control:
- one reservation-price shift
- one size-pressure function
- one explicit neutral clear rule

### Third-best experiment

Add compact execution-calibration tables:
- passive fill rate by quote distance / spread / imbalance bucket
- passive adverse markout by same buckets
- use only for go/no-go and join-vs-wait

## Source Quality Notes

Highest signal:
- [TimoDiehm/imc-prosperity-3](https://github.com/TimoDiehm/imc-prosperity-3)
- [ericcccsliu/imc-prosperity-2](https://github.com/ericcccsliu/imc-prosperity-2)
- [ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal](https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal)
- [jmerle/imc-prosperity-2](https://github.com/jmerle/imc-prosperity-2)
- [chrispyroberts/imc-prosperity-3](https://github.com/chrispyroberts/imc-prosperity-3)
- [CarterT27/imc-prosperity-3](https://github.com/CarterT27/imc-prosperity-3)
- [YBansal95/imc-prosperity-3](https://github.com/YBansal95/imc-prosperity-3)

Medium signal:
- [pe049395/IMC-Prosperity-2024](https://github.com/pe049395/IMC-Prosperity-2024)
- [nicolassinott/IMC_Prosperity](https://github.com/nicolassinott/IMC_Prosperity)
- [edmund870/2024-IMC-Global-Trading-Challenge](https://github.com/edmund870/2024-IMC-Global-Trading-Challenge)
- [stephen-w-choo/imc-prosperity-2024](https://github.com/stephen-w-choo/imc-prosperity-2024)
- [liyiyan128/optiver-trading-at-the-close](https://github.com/liyiyan128/optiver-trading-at-the-close)
- [fan2goa1 TAC summary](https://fan2goa1.github.io/mkdocs-material/blog/2023/12/24/kaggle-optiver---trading-at-the-close/)

Lower signal or less directly reusable:
- repos with little strategic commentary and mostly code snapshots
- Kaggle leaderboard solutions that rely on competition-specific quirks
- product-specific hardcoding from later Prosperity rounds that does not transfer to EMERALDS / TOMATOES

## Bottom Line

The strongest reusable lesson is:

Do not add more indicators by default.

Instead:
- improve the fair proxy
- simplify inventory control
- make one-sided behavior more explicit
- calibrate fill/adverse-selection empirically
- use persistent filtered state only where it clearly improves execution

## Additional Synthesis

This section adds a higher-level synthesis focused on what seems to repeat across Prosperity 1, 2, 3, and adjacent Optiver order-book competitions.

### Tooling first, strategy second

One of the clearest recurring lessons is that the best public teams did not win by discovering one magical signal first. They won by building:
- fast backtesting
- synchronized timestamp replay
- parameter injection
- visual inspection tools
- good experiment hygiene

This shows up repeatedly in:
- [ericcccsliu/imc-prosperity-2](https://github.com/ericcccsliu/imc-prosperity-2)
- [jmerle/imc-prosperity-2](https://github.com/jmerle/imc-prosperity-2)
- [MichalOkon/imc_prosperity](https://github.com/MichalOkon/imc_prosperity)
- [davidteather/imc-prosperity-2024](https://github.com/davidteather/imc-prosperity-2024)
- [TimoDiehm/imc-prosperity-3](https://github.com/TimoDiehm/imc-prosperity-3)

That reinforces a core principle for our own work:
- better tooling usually beats more indicators

### Product taxonomy is more reusable than any single bot

Across years, products tend to fall into repeatable buckets:
- fixed-fair market making
- local-fair / rolling-fair market making
- chaotic spike-fade or reduced-size products
- basket-vs-synthetic stat arb
- options / implied-volatility trading
- conversion / second-venue arbitrage
- trader-ID exploitation

That taxonomy appears again and again in public Prosperity repos, even when the implementation details differ. For future rounds, the right response is usually:
- classify the product archetype early
- plug it into the appropriate module
- then optimize execution around that module

For Prosperity 4 specifically, that means the best reusable asset is not an old trader file. It is a modular engine that already supports those archetypes.

### Large, persistent quotes are often better than naive midpoint

This idea is strong enough to repeat twice in this note because it shows up so often and maps directly to our current bots.

Observed repeatedly:
- large-liquidity quotes
- persistent wall levels
- "market-maker mid"
- "wall mid"

Interpretation:
- the raw midpoint often contains too much transient noise
- a filtered price proxy based on persistent size can be more stable and more predictive

This remains one of the most promising near-term upgrades for our current EMERALDS / TOMATOES family.

### Inventory freeing is a first-class alpha enabler

Another important repeated lesson:
- some of the best gains came not from predicting better
- but from freeing position limits so the bot could take the next good trade

This supports a design principle for us:
- inventory relief should be explicit
- not spread across many small hidden penalties

### Chaotic products should usually be simplified, not overmodeled

Public writeups repeatedly show the same outcome on very noisy products:
- either trade them with a very specific trigger and smaller size
- or skip them

The common failure mode is:
- adding more prediction machinery to a chaotic series
- then getting chopped up anyway

This is a strong warning for our own future product modules:
- when a product looks structurally ugly, default to smaller size, spike rules, or no trade

### Basket and conversion rounds reward execution realism

Another repeated pattern is that the theoretical relationship is often easy to find:
- basket premium
- synthetic spread
- conversion edge

But the real edge depends on:
- timing
- slippage
- fill probability
- position limits
- whether full hedging is actually feasible

That means our future basket or conversion modules should be built around:
- tradeable premium
- execution-adjusted edge
- partial-hedge realism

not just a textbook residual.

### ML is most useful as a sidecar

The Optiver-style material is still valuable, but the main lesson is not "replace the bot with a model."

The highest-transfer ideas are:
- imbalance features
- urgency features
- spread/pressure interactions
- lagged order-book features
- careful time-based validation

These are best used for:
- regime classification
- quote aggressiveness
- short-horizon confidence adjustments

not as a full black-box trading policy.

### Prosperity 4 framing

Prosperity 4 is live as a five-round challenge starting April 14, 2026, so the public repos should be treated as:
- pattern libraries
- workflow examples
- research prompts

not as code to transplant directly.

The most practical import into a Prosperity 4 framework is:
- product classification
- fair-value estimation tricks
- execution-aware logic
- logging and replay tooling

### Practical build priority for a future framework

If turning the public lessons into a reusable architecture, the build order should be:

1. Tooling:
- backtester
- synchronized replay
- experiment logging
- parameter injection

2. Core product modules:
- fixed-fair MM
- local-fair MM
- noisy-product spike/reversion
- basket/conversion arb
- options/IV module

3. Execution layer:
- explicit inventory relief
- layered posting / taking
- fill-aware quote adaptivity
- size-down / skip rules

4. Research sidecar:
- microstructure feature set
- regime classification
- confidence estimates

5. Counterparty / ID plumbing:
- if trader IDs appear, the infrastructure is already ready

### Condensed conclusion

The most useful thing to import from public Prosperity and Optiver work is not someone else's finished trader.

It is:
- their tooling discipline
- their product taxonomy
- their fair-value estimation tricks
- their execution realism
- and their risk sizing habits
