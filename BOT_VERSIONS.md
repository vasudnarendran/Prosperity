# Bot Versions

This file contains the running experiment log for all bot versions.

V1:
Works: Yes
Improvement: First base model with a fixed acceptable price.
Notes: Technically runs, but the fixed value is too naive and can lead to one-sided trading.
PnL: N/A

V2:
Works: No
Improvement: Tried to move away from the fixed-price baseline.
Notes: Had errors and was discarded.
PnL: N/A

V3:
Works: Yes
Improvement: Uses best bid and best ask to create a midpoint-based buy and sell level.
Notes: Current record bot with Total PnL 590.
PnL: 590

V3.1:
Works: Yes
Improvement: Added more direct interaction with visible top-of-book volume.
Notes: Underperformed badly at around -1.4k PnL because the sell logic became too aggressive and asymmetric.
PnL: -1.4k

V3.2:
Works: Yes
Improvement: Keeps the V3 midpoint idea but improves buy/sell interaction by using symmetric take-or-quote logic and stepping quotes inside the spread.
Notes: Built to isolate execution-side improvements before moving on to fixed anchors or dynamic pricing.
PnL: 560

V4:
Works: No
Improvement: Experimental branch.
Notes: Did not work and is not part of the active path.
PnL: N/A

V5:
Works: Yes
Improvement: Added product-specific fair value handling and both taking and passive quoting.
Notes: Broader experiment, but not the current focus while testing pure buy/sell adjustments.
PnL: 540

V6:
Works: Yes
Improvement: Broader market-making version with inventory skew, quote edges, and product-specific fair value logic.
Notes: Strong base version that opened the path to the later execution improvements, but it has now been overtaken by V6.2.
PnL: 1'173

V6.1:
Works: Yes
Improvement: Keeps the V6 logic but tests small EMERALDS fair-value weight changes around the reference price.
Notes: Both small blend changes stayed close to V6 but did not beat it. The effect shows up almost entirely in EMERALDS while TOMATOES stays unchanged, so this does not look like the highest-value tuning path right now.
PnL: 1'169

V6.2:
Works: Yes
Improvement: Returns to the original V6 fair value, then explores execution improvements with spread-adaptive quote edges, inventory-aware aggressiveness, softer same-side quoting near inventory limits, and less quote stacking after taking liquidity.
Notes: New record version. The logs suggest the gain came mostly from better execution quality rather than more trades: better buy prices and better sell prices on both EMERALDS and TOMATOES.
PnL: 1'764

V6.3:
Works: Yes
Improvement: Builds on V6.2 with slightly tighter TOMATOES quoting, slightly more selective EMERALDS taking, a softer inventory limit, and a bit more passive EMERALDS size.
Notes: Underperformed V6.2. EMERALDS stayed almost unchanged, but TOMATOES execution got worse, so this version likely over-adjusted the TOMATOES quoting layer.
PnL: 1'603

V6.3.1:
Works: Yes
Improvement: Retuned V6.3 by moving TOMATOES closer to the V6.2 execution setup and adding a lightweight dynamic fair-value model for non-anchored products using midprice, microprice, and short traderData history.
Notes: Recovered most of the lost score from V6.3, but still did not beat V6.2. The dynamic TOMATOES fair value helped compared with V6.3, yet the original V6.2 execution remains slightly stronger overall.
PnL: 1'747

V6.4:
Works: Yes
Improvement: Starts from V6.2 and adds a focused TOMATOES drift filter using traderData history, widening or suppressing the wrong-side quote in short-term trending conditions and biasing aggressive taking with the drift.
Notes: Bad attempt. EMERALDS was identical to V6.2, but the TOMATOES filter suppressed too much good trading and cut both trade count and total edge, so the regime layer was too restrictive in this form.
PnL: 1'559

V6.5:
Works: Yes
Improvement: Starts from V6.2 and adds a TOMATOES-only dynamic fair value using current mid, microprice, and short traderData mid-history, without hard quote suppression or regime blocking.
Notes: Close to V6.2 but still slightly worse. EMERALDS stayed identical, while TOMATOES kept the same trade count but bought a bit worse on average, so the dynamic fair value did not improve execution enough to beat the base version.
PnL: 1'750

V7:
Works: Yes
Improvement: Keeps TOMATOES on the proven V6.2-style logic and introduces a dedicated EMERALDS module with fixed-anchor pricing, stronger state-based reactions around the rare off-anchor book states, and more aggressive reversion-style sizing.
Notes: Worse than V6.2. TOMATOES stayed identical, but the EMERALDS module overtraded heavily, moving from a selective high-quality profile to many more lower-edge trades with much worse average buy and sell prices.
PnL: 1'534

V7.1:
Works: Yes
Improvement: Returns to the V6.2 base and adds only a narrow EMERALDS rare-state enhancement: a bit more size and slightly stronger quote bias when the best ask compresses to 10000 or the best bid lifts to 10000, while suppressing the wrong-side quote in those moments.
Notes: Very close to V6.2, but still slightly worse overall. TOMATOES stayed identical and the whole gap came from EMERALDS buying a touch worse while keeping the same general trade profile, so this looks more like a tiny execution shift than a new edge.
PnL: 1'757

V8:
Works: Yes
Improvement: Larger rewrite that combines the strongest parts of the earlier bots into a more modular structure: traderData memory, product-specific fair value models, microprice and history signals, regime-aware take edges, and separate passive quoting logic.
Notes: New record version. The gain came almost entirely from TOMATOES: it kept the same trade count as V6.2 but bought slightly cheaper and sold materially better on average. EMERALDS was weaker than V6.2, so V8's current edge looks like a stronger TOMATOES engine rather than an all-around improvement yet.
PnL: 1'791

V8.1:
Works: Yes
Improvement: Keeps the V8 architecture and adds a TOMATOES bullish-trend sell-restraint layer, making sells more selective in strong upward moves by widening passive asks, reducing passive sell size, and raising the bar for aggressive sells.
Notes: The idea looks directionally interesting, but this version overdid it. EMERALDS stayed identical to V8, while TOMATOES bought cheaper but sold far less often and at much worse prices on average, which suggests the bot held back too much and then gave up edge later when it finally sold.
PnL: 1'647

V8.1.1:
Works: Yes
Improvement: Keeps the V8.1 idea but softens it substantially, so TOMATOES only restrains selling in stronger bullish states and does so with smaller quote, size, and edge adjustments.
Notes: Much better than V8.1, but still below V8. The softer version recovered trade flow and improved TOMATOES a lot versus V8.1, yet it still sold less often and at worse prices than V8 overall. That suggests the trend-aware sell idea has some signal, but it is still not adding enough edge in this form to beat the simpler V8 base.
PnL: 1'743

V8.2:
Works: Yes
Improvement: Moves to a more layered framework with explicit alpha, regime classification, target-position construction, execution toward the target, and basic risk controls. EMERALDS stays anchor-based, while TOMATOES switches to a regime-aware momentum versus mean-reversion alpha.
Notes: Massive downgrade. The layered structure itself may still be useful, but this version diluted the edge too much: it traded both products near fair value with much flatter buy and sell prices, so it captured very little spread or directional edge. The result suggests the portfolio and alpha layers became too neutral and smoothed out the profitable asymmetry that V8 had in TOMATOES.
PnL: 134

V9:
Works: Yes
Improvement: Keeps EMERALDS close to the stronger V8 behavior and rebuilds TOMATOES as a state-machine strategy with discrete regimes, position bands, and one-sided execution rules instead of a single smoothed fair-value response.
Notes: New record version, though only by a small margin over V8. The state-machine idea appears to have helped without destabilizing the bot: TOMATOES improved slightly while keeping the same trade count, and EMERALDS also improved modestly. That suggests the discrete regime logic preserved V8's edge better than the smoother V8.2 framework did.
PnL: 1'800

V10:
Works: Yes
Improvement: First explicitly product-specialized architecture for Prosperity 4, with a shared base trader, a dedicated EMERALDS module based on selective anchor-style market making, and a dedicated TOMATOES module based on regime/state behavior.
Notes: The modular design held up well, but it did not beat the current best. The result landed at roughly the same level as V8, with essentially the same trade profile and product split: TOMATOES stayed strong while EMERALDS remained weaker than the old V6.2 peak. That suggests the architecture is promising for future development, but the product modules still need new alpha rather than just cleaner structure.
PnL: 1'794

V11:
Works: Yes
Improvement: Keeps the modular V10 structure but retunes only the EMERALDS module toward a stricter, more selective V6.2-style anchor trader while leaving TOMATOES unchanged.
Notes: This recovered a large part of the V10 gap in local Rust backtests and confirmed that EMERALDS is the right place to keep tuning. The first V11 local Rust run reached 9'971, which was clearly better than V10's 9'783 but still below V9's 9'992 in the same backtester.
PnL: Official N/A | Rust: 9'971

V11.x Search:
Works: Yes
Improvement: Small EMERALDS-only search around V11, testing more exact V6.2 soft-limit handling plus asymmetric tweaks for avoiding weak 10000 buys and leaning harder into sells above the anchor.
Notes: The best local Rust variants were V11.3, V11.5, V11.6, and V11.7, all tying at 9'998. The official-site result for V11.3 then validated the direction and became a new overall high score at about 1'850. The key insight is that V11.3 kept TOMATOES identical to the strong V9 engine while restoring EMERALDS to a much more V6.2-like trade profile: fewer EMERALDS trades, better average buy price, and stronger concentration in the high-value 10004-10006 sell region.
PnL: Official Best 1'850 | Rust Best: 9'998

V11.8:
Works: Yes
Improvement: Tests the hard-filter idea of blocking EMERALDS buys at exactly 10000 while keeping the stronger V11.3-style sell behavior.
Notes: Bad result. The local Rust score dropped sharply to 9'050, with the entire damage coming from EMERALDS. That strongly suggests the 10000 buys are not just low-quality noise; they are still important for inventory recycling and staying engaged in the anchor state. A full hard block is too aggressive.
PnL: Official N/A | Rust: 9'050

V11.9:
Works: Yes
Improvement: Softer version of the 10000-buy filter idea, keeping the V11.3 structure but allowing EMERALDS buys at 10000 only at reduced size instead of blocking them completely.
Notes: Still worse than the best V11.x variants. The local Rust score fell to 9'930, which is much better than the hard block in V11.8 but still clearly below the 9'998 plateau. This suggests the anchor-state 10000 buys are not only useful to have, but are probably too important to shrink aggressively.
PnL: Official N/A | Rust: 9'930

V12:
Works: Yes
Improvement: Adds timestamp-aware phases to the V11.3 foundation: more aggressive sizing and tighter edges early, normal behavior in the middle, and more passive / lower-inventory behavior late in the run.
Notes: Mixed result in the local Rust backtester. TOMATOES improved noticeably, but EMERALDS weakened enough that total PnL fell below the V11.3 high. That suggests the general idea may have some signal, especially for TOMATOES, but the late-session passive shift is currently too blunt and is giving up too much EMERALDS edge.
PnL: Official N/A | Rust: 9'929

V13:
Works: Yes
Improvement: Prosperity 3-inspired branch. EMERALDS was rebuilt toward a simpler static anchor market maker, while TOMATOES was pushed toward a more explicit Kelp-style dynamic trader with half-limit position bands and stronger directional leaning.
Notes: The concepts transferred less cleanly than expected. The official-site result came in at about 1'566, which is far below V11.3's 1'850. Both products got worse: EMERALDS fell from 739 to 639 and TOMATOES fell from 1'111.6 to 927.3. The trade profile explains why: V13 overtraded EMERALDS at worse prices, buying 120 instead of 90 units at a much worse average price and also selling at weaker prices; TOMATOES also got worse on both sides with fewer sells and worse buys. The local Rust backtester had already shown weakness at 9'301, and the official result confirms the direct Prosperity 3 behavior copy is too blunt for this round. The useful takeaway is still structural: keep the architecture ideas, but preserve our proven V11.3 behavior.
PnL: Official 1'566 | Rust: 9'301

V13.1:
Works: Yes
Improvement: Keeps the Prosperity 3-style base structure and clearer take-versus-make separation, but restores the actual EMERALDS and TOMATOES trading behavior much closer to V11.3.
Notes: Strong local recovery and a useful official confirmation. In the Rust backtester V13.1 reached 10'046, beating both V11.3's 9'998 and V13's 9'301. On the official site, however, V13.1 tied V11.3 exactly at about 1'850.6, with the same product split and the same trade profile. That means the structural cleanup did not create a new official edge yet, but it also did not hurt performance. The important takeaway is that the Prosperity 3-style structure appears safe as long as the profitable V11.3 behavior is preserved.
PnL: Official 1'850.6 (tie with V11.3) | Rust: 10'046

V14:
Works: Yes
Improvement: Starts from the V13.1 structure and introduces a probability-based TOMATOES regime model. Instead of hard switching only between trend and mean reversion, it estimates soft probabilities for trend, range, and high-volatility states from recent mid-price slope, momentum, imbalance, realized volatility, spread, and drawdown. Those probabilities then scale target position, edges, passive size, and a soft kill switch.
Notes: The official result confirms this branch is too cautious in practice. It finished at about 1'566.9, far below the 1'850.6 tie from V11.3 and V13.1. EMERALDS was unchanged, which is actually useful: it stayed exactly at 739 with the same trade profile, so the probability layer did not damage the stable anchor trader. The entire loss came from TOMATOES, which fell from 1'111.6 to 827.9. The trade profile shows why: the bot traded TOMATOES much less, buying only 98 instead of 124 units and selling only 93 instead of 109. Sell prices were slightly better on average, but buy prices were worse and the strategy simply gave up too much good flow. The takeaway is that regime probabilities may still help, but only as a very light sizing or edge modifier on the existing TOMATOES engine, not as a broader gating layer.
PnL: Official 1'566.9 | Rust: 9'552

V14.1:
Works: Yes
Improvement: Keeps the V13.1 decision flow and uses regime probabilities only as small TOMATOES nudges on three levers: `MAX_TAKE_SIZE`, `PASSIVE_SIZE`, and `take_edge`.
Notes: This is much closer to the right use of probabilities. In the local Rust backtester V14.1 recovered to 10'043, almost exactly back to V13.1's 10'046. EMERALDS stayed unchanged at 4'902, and TOMATOES recovered to 5'141 versus V13.1's 5'144. So the lighter probability layer no longer chokes off good flow. It still has not shown a clear improvement locally, but it is now safe enough to justify an official-site test.
PnL: Official N/A | Rust: 10'043

V14.x Attribute Sweep:
Works: Yes
Improvement: Isolated which TOMATOES attributes are actually affected usefully by regime probabilities by testing temporary local variants off the V13.1 base.
Notes: The local Rust sweep showed a surprisingly clean result. `take_edge` only, `MAX_TAKE_SIZE` only, and `take_edge + MAX_TAKE_SIZE` all tied the baseline at 10'046, meaning they were effectively neutral in this backtest. Any variant that included probability-based `PASSIVE_SIZE` dropped slightly to 10'043, which means that small size suppression was the only tested lever that measurably hurt TOMATOES. The main takeaway is that the current probability signals are too weak or too noisy to improve the strategy through these levers, and `PASSIVE_SIZE` is the most sensitive one in the wrong direction.
PnL: Rust Sweep Best 10'046 | Worst 10'043

V15:
Works: Yes
Improvement: Starts from the tied best V13.1 behavior, adds external parameter overrides so the same bot can be swept systematically, and then applies the best local layered settings back into the bot. The sweep tested EMERALDS and TOMATOES separately across fair-value, skew, edge, size, and regime-threshold parameters.
Notes: This became the new official top bot. The official log came in at about 1'873.6, beating the old V11.3 / V13.1 tie by 23 points. The whole official improvement came from TOMATOES while EMERALDS stayed identical: EMERALDS remained at 739.0 with the same trade counts and average prices, while TOMATOES improved from 1'111.6 to 1'134.6. The TOMATOES trade count and quantity stayed exactly the same too, which is the strongest signal here: the tuned parameters improved execution quality rather than just increasing activity. Average TOMATOES buy improved from 4986.782 to 4986.637 and average TOMATOES sell improved from 4995.633 to 4995.679. That lines up well with the Rust sweep, which already suggested that TOMATOES still had room while EMERALDS was near a local optimum. The sweep outputs live in `Analysis/output/v15_sweep_report.txt` and `Analysis/output/v15_sweep_results.csv`.
PnL: Official 1'873.6 | Rust: 10'326

V16:
Works: Yes
Improvement: Keeps the V15 TOMATOES engine unchanged and rewrites only EMERALDS toward a more explicit Prosperity 3-style execution layer: tiered take sizes based on distance from fair value, a separate clear-position pass near fair, earlier inventory pressure with a lower soft limit, and book-aware passive quoting using join / undercut style placement.
Notes: This became the new breakout official bot. The official result came in at about 2'184.6, which is a huge jump over V15's 1'873.6. The most important confirmation is that TOMATOES stayed exactly unchanged from V15 at 1'134.6, so the entire gain came from EMERALDS, which jumped from 739.0 to 1'050.0. The EMERALDS trade profile changed sharply in the direction we wanted: buys increased from 90 to 115 and got better on average, improving from 9996.356 to 9995.922, while sells increased from 109 to 128 and got materially better, improving from 10003.771 to 10004.539. The level distribution is also much more concentrated and decisive than V15: EMERALDS mainly bought at 9993 and 10000, and sold heavily at 10007, instead of spreading inventory across many middling price levels. This is the clearest evidence so far that the missing EMERALDS edge was execution structure and inventory recycling, not a better fair-value formula.
PnL: Official 2'184.6 | Rust: 12'827

V16.1:
Works: Yes
Improvement: Keeps EMERALDS frozen from V16 and tests TOMATOES layered soft limits with staged trend exits, aiming to hold trend inventory longer without shutting the product down completely.
Notes: The official-site result you reported came in around 2'150, so it stayed fairly close to V16 but did not improve it. The local Rust direction was also negative: the stronger soft-band version dropped from 12'827 to 12'622, with EMERALDS unchanged and TOMATOES falling from 5'424 to 5'219. The common pattern matches earlier attempts: the soft-limit idea changes TOMATOES behavior, but still tends to become too cautious and give up good trading flow.
PnL: Official ~2'150 | Rust: 12'622

V16.2:
Works: Yes
Improvement: Keeps EMERALDS frozen from V16 and tests a narrower TOMATOES microstructure overlay. It only adds a confirmed-trend bias to fair value, take edge, and passive quote placement when momentum, short momentum, and imbalance all line up strongly.
Notes: Local result was clearly worse than V16. Total Rust PnL dropped from 12'827 to 12'414. EMERALDS stayed unchanged at 7'403, so the whole loss came from TOMATOES, which fell from 5'424 to 5'011. That suggests the confirmed-trend nudges made TOMATOES too selective or misplaced quotes enough to reduce the good flow that V16 already captures well.
PnL: Official N/A | Rust: 12'414

V17:
Works: Yes
Improvement: Builds a fuller TOMATOES microstructure overlay on top of V16. It adds a pressure score from microprice dislocation, short-horizon momentum, and order-book imbalance, then uses that pressure to nudge fair value, taking thresholds, and passive quote placement.
Notes: This is the cleanest implementation of the microstructure idea so far, but the first local result was still weaker than V16. Total Rust PnL dropped from 12'827 to 12'613. EMERALDS stayed frozen at 7'403, so again the whole change came from TOMATOES, which fell from 5'424 to 5'210. The overlay increased trade count, so the problem was not missed participation; it likely pushed too many TOMATOES quotes or takes in the wrong direction. The good news is that this confirms the architecture can be isolated cleanly. The next improvement probably needs either a much smaller pressure coefficient or a narrower maker/taker split rather than pressure moving both fair value and quotes at the same time.
PnL: Official N/A | Rust: 12'613

V17.x Sweep:
Works: Yes
Improvement: Tests the TOMATOES microstructure architecture directly with a dedicated local sweep over pressure coefficients and execution levers, instead of guessing a single next variant. The sweep keeps EMERALDS frozen and only changes the TOMATOES pressure layer and its interaction with base take and quote edges.
Notes: The sweep shows the architecture is salvageable, but only with much softer pressure influence. The best layered local result reached 13'038, beating both the raw V17 result and even V16 locally. The strongest findings were: lower `PRESSURE_MICRO_COEF` at 0.60 worked better than 1.00, `PRESSURE_FAIR_BONUS` should be small at 0.15 rather than large, `PRESSURE_EDGE_BONUS` worked best at 0.0, and the biggest lever by far was simply lowering TOMATOES `BASE_TAKE_EDGE` from 1.50 to 1.35. The best layered combination also preferred a slightly wider TOMATOES `BASE_QUOTE_EDGE` of 2.50 and a high `PRESSURE_QUOTE_THRESHOLD` of 1.60, which means the pressure signal should act rarely and mostly through fair-value / quote placement, not aggressive-edge changes. The sweep outputs live in `Analysis/output/v17_sweep_report.txt` and `Analysis/output/v17_sweep_results.csv`.
PnL: Rust Sweep Best 13'038 | Baseline 12'613

V17 Coarse Sweep:
Works: Yes
Improvement: Runs a second, wider-step search over the V17 TOMATOES microstructure architecture to check whether a different local optimum exists beyond the small-step tuning region. The sweep explores bigger jumps in `BASE_TAKE_EDGE`, `BASE_QUOTE_EDGE`, passive / take size, and the main pressure coefficients.
Notes: The wider search did not discover a stronger second basin. The best result was still the same `light_pressure_balanced` region at 13'038 Rust PnL, identical to the earlier V17.x sweep winner that later became V17.1. That is actually useful: it suggests we are not simply trapped by tiny-step tuning. The coarse run also made the failure mode clearer. The worst cases were the strong-pressure, low-threshold variants such as `strong_pressure_trend`, which collapsed TOMATOES to about 4'554 while EMERALDS stayed fixed. The best broad directions were: keep pressure light, avoid pressure-based edge bonuses, let quote-thresholds stay high so pressure acts rarely, and use TOMATOES pressure more as a placement hint than as a regime override. Disabling pressure entirely could still perform well in taker-leaning setups, but the best local result still came from a softer overlay rather than from removing the architecture completely. Outputs live in `Analysis/output/v17_coarse_report.txt` and `Analysis/output/v17_coarse_results.csv`.
PnL: Rust Sweep Best 13'038 | Baseline 12'613 | Worst 11'957

V17.1:
Works: Yes
Improvement: Clean upload-safe implementation of the best `V17.x` sweep result. It keeps EMERALDS unchanged from V16 and applies the winning softer TOMATOES microstructure settings directly in the bot defaults.
Notes: Officially, this is a small but real improvement over V16. Total PnL moved from about 2'184.6 to 2'186.6. EMERALDS stayed completely unchanged at 1'050.0 with the exact same trade profile and price levels, so the whole gain came from TOMATOES. The TOMATOES trade count and quantity also stayed identical to V16 at 36 buys / 124 quantity and 32 sells / 109 quantity, which means the improvement came purely from slightly better execution quality. In the official log the average TOMATOES buy improved from 4986.637 to 4986.621 while average sell stayed the same at 4995.679. So this is not a major breakout, but it is a clean confirmation that the softer microstructure overlay can help when it is kept light.
PnL: Official 2'186.6 | Rust: 13'038

V18:
Works: Yes
Improvement: Drops the TOMATOES microstructure-pressure architecture and replaces it with a different alpha model inspired by the guide repo: short-horizon linear regression on recent mid-prices. EMERALDS stays frozen from V16 / V17.1, while TOMATOES now trades around a predicted next mid-price with separate `trend_up`, `trend_down`, `range`, and `volatile` states based on regression edge, fit quality, imbalance, and volatility.
Notes: This became the new best official branch. The first pure-regression pass was far too aggressive and blew up TOMATOES locally, but the softened hybrid version recovered well and then transferred strongly to the official simulator. Officially, V18 reached about 2'264.4 versus 2'186.6 for V17.1. EMERALDS stayed completely unchanged at 1'050.0, so the whole gain came from TOMATOES, which improved from 1'136.6 to 1'214.4. The trade profile explains the new optimum: TOMATOES buys increased from 124 to 129 quantity and improved materially on price from 4986.621 to 4986.178, while TOMATOES sells stayed at the same 109 quantity but got a bit worse on average from 4995.679 to 4995.413. That means the new regression model is improving entry timing more than exit timing. The useful takeaway is big: this is the first post-V17 model family that clearly improved on the official site without relying on the pressure overlay architecture. The guide repo explicitly recommends fitting simple models such as linear regression for mid-price prediction and treating drifting assets as a slope / timing problem rather than just static market making, which is exactly the direction this branch takes.
PnL: Official 2'264.4 | Rust: 13'291

V18 Regression Sweep:
Works: Yes
Improvement: Adds a dedicated local sweep for the new TOMATOES predictive model instead of guessing at the regression settings manually. The sweep only touched the regression-family levers: forecast horizon, trend edge threshold, fit threshold, residual reversion weight, and the matching take / quote parameters around that model.
Notes: The sweep found a small but coherent improvement over the V18 baseline. The best local result moved from 13'291 to 13'302. The winning region was not “more regression weight” but a more permissive trend classifier with a longer horizon and more conservative execution: `REGRESSION_HORIZON = 3.0`, `TREND_EDGE_THRESHOLD = 1.25`, `FIT_THRESHOLD = 0.55`, `TREND_IMBALANCE_THRESHOLD = 0.18`, `BASE_TAKE_EDGE = 1.25`, `BASE_QUOTE_EDGE = 2.75`, `MAX_TAKE_SIZE = 6`, and `RESIDUAL_REVERT_WEIGHT = 0.20`. A useful negative result also came out clearly: range-heavy / over-cautious predictive settings collapsed TOMATOES to roughly 2'691 Rust PnL, so this model still needs strong participation and cannot be turned into a timid filter. Outputs live in `Analysis/output/v18_sweep_report.txt` and `Analysis/output/v18_sweep_results.csv`.
PnL: Rust Sweep Best 13'302 | Baseline 13'291

V18.1:
Works: Yes
Improvement: Clean upload-safe implementation of the best V18 regression-sweep settings. It keeps the new predictive TOMATOES model but stretches the forecast horizon, lowers the trend gate, raises quote width, tightens taking, and reduces max take size.
Notes: Local Rust result reproduced the sweep winner exactly at 13'302, so the improvement is real but very small. EMERALDS stayed unchanged at 7'403, and TOMATOES improved from 5'888 to 5'899. That means the gain is only +11 locally, but it comes from a genuinely different alpha family than the V17 pressure overlay. This makes V18.1 the best next official-site test if we want to keep exploring the regression direction without overcomplicating the model.
PnL: Official N/A | Rust: 13'302

V18.2:
Works: Yes
Improvement: Experimental branch that implements four layered follow-ups on top of V18: asymmetric sell optimization for TOMATOES, two-horizon regression, forecast-persistence before entering trend states, and separate buy-versus-sell trend thresholds.
Notes: The first full-strength version was far too aggressive and collapsed locally, so it was softened into a lighter implementation. The current local result is stable again, but still worse than V18. Rust PnL came in at 13'159, with EMERALDS unchanged at 7'403 and TOMATOES falling from 5'888 to 5'756. That suggests the idea package is conceptually reasonable but still overconstrains TOMATOES, especially by delaying or reshaping profitable sell flow too much. The useful takeaway is not that the four ideas are invalid, but that they should probably be reintroduced one at a time on top of V18 rather than all in the same jump.
PnL: Official N/A | Rust: 13'159

V18.3 Isolated Tests:
Works: Yes
Improvement: Breaks the V18.2 idea bundle back into isolated V18 forks so each TOMATOES hypothesis can be tested fairly on top of the proven V18 base. The tested branches were: sell optimization only, two-horizon regression only, persistence only, and separate buy/sell thresholds only.
Notes: This was a very clean readout. Three isolated ideas were effectively neutral locally: `Traderv18_3_sell.py`, `Traderv18_3_persistence.py`, and `Traderv18_3_thresholds.py` all tied the V18 baseline at 13'291 Rust PnL with the same product split and trade count. That suggests those changes either rarely activated or activated too mildly to move the local result. The only isolated idea that clearly mattered was two-horizon regression on its own, and it mattered in the wrong direction: `Traderv18_3_horizon.py` collapsed to 2'165 total Rust PnL, with TOMATOES dropping from 5'888 to -5'238. The main takeaway is that the V18 breakthrough is not coming from any one of these add-ons alone. It seems to come from the integrated regression alpha itself, while the attempted add-on refinements are either inert or too destabilizing when isolated.
PnL: Sell 13'291 | Persistence 13'291 | Thresholds 13'291 | Two-Horizon 2'165

V18.4 Exit Path:
Works: Yes
Improvement: Tests a narrower exit-optimization family on top of V18, without touching the TOMATOES regression entry model that already worked. The branches isolate three exit ideas: passive sell-quote lifting, aggressive sell-take restraint, and sliced smaller exits during still-bullish forecasts.
Notes: This finally showed a clear directional path. Passive sell-quote lifting did nothing locally: `Traderv18_4_quote.py` tied the V18 baseline exactly at 13'291. Exit slicing also did nothing: `Traderv18_4_slice.py` also tied at 13'291. The only branch that improved was aggressive sell-take restraint. A soft version (`Traderv18_4_take_soft.py`) reached 13'304, and the best version (`Traderv18_4_take.py`, copied into `Traderv18_4.py`) reached 13'321, while a harder version (`Traderv18_4_take_hard.py`) fell back to 13'275. EMERALDS stayed unchanged at 7'403 in every case, so the whole path is TOMATOES-only. TOMATOES moved from 5'888 in V18 to 5'918 in the best exit branch. The practical lesson is strong: the next bit of edge does not seem to be in passive quote geometry or slicing, but in making aggressive sells slightly harder when the forecast is still supportive. This is the first exit-only family that actually improved on V18 locally.
PnL: Baseline 13'291 | Quote 13'291 | Slice 13'291 | Take Soft 13'304 | Take Best 13'321 | Take Hard 13'275

V19 Family:
Works: Yes
Improvement: Explores a new TOMATOES family built around predictive fair value plus more explicit market making. The idea was to move away from the V18/V18.4 taker-leaning regression style and test maker-first hybrids with narrower book-aware quoting, larger passive participation in clean spreads, and more selective taking.
Notes: The family gave a clean negative result locally. `Traderv19.py`, the strongest maker-first attempt, dropped sharply to 12'022 Rust PnL with EMERALDS unchanged at 7'403 and TOMATOES falling to 4'619. That showed the pure maker-first shift gave up too much of the V18 regression edge. Two softer hybrids were then tested: `Traderv19_1.py`, which mostly added book-aware joining and larger passive participation, reached 13'185; and `Traderv19_2.py`, which combined the passive changes with a light taker holdback, reached 13'082. Both were still below V18 and V18.4. The useful takeaway is that TOMATOES does not currently want a broad shift toward market making. The predictive entry model is still the main edge, and the maker overlays tested here were not able to improve on it. If market making comes back later, it likely needs to be much lighter and subordinated to the existing regression signal rather than treated as a new primary style.
PnL: V19 12'022 | V19.1 13'185 | V19.2 13'082

V20:
Works: Yes
Improvement: Starts a new higher-risk TOMATOES family from the V18 line instead of the V19 market-making branch. EMERALDS stays frozen, while TOMATOES becomes more willing to carry trend inventory: wider target bands, lower inventory skew, lower trend threshold, bigger take size in confirmed trends, stronger target-position bias in fair value, and slower exits when the forecast still supports the move.
Notes: The first local result is modest but encouraging. `Traderv20.py` reached 13'340 Rust PnL, beating both V18 at 13'291 and V18.4 at 13'321. EMERALDS stayed fixed at 7'403, so the whole gain came from TOMATOES, which improved from 5'918 in V18.4 to 5'937. Trade count fell slightly from 722 to 719, which is a good sign for this family: the improvement did not come from spraying more orders, but from holding or sizing TOMATOES trend exposure a bit more decisively. This is the first branch after V18 that supports the thesis that a riskier carry-oriented TOMATOES engine might open a new optimum instead of just adding tiny execution refinements.
PnL: Official N/A | Rust: 13'340

V20 Risk Sweep:
Works: Yes
Improvement: Runs the first dedicated sweep over the higher-risk TOMATOES carry family, instead of hand-tuning one aggressive branch at a time. The search focuses on the actual carry levers: inventory skew, take edge, passive size, max take size, trend thresholds, soft limit, position-bias strength, trend fair-value bonus, trend entry size bonus, and exit hold bonuses.
Notes: This sweep confirmed that the V20 family has more headroom. Baseline V20 at 13'340 improved to a best local result of 13'431. The most important lesson is that the best risky carry setup was not the most extreme one. The winning region used easier trend activation and cheaper taking, but not the heaviest inventory carry: `BASE_TAKE_EDGE = 1.10`, `TREND_EDGE_THRESHOLD = 1.00`, `STRONG_TREND_EDGE = 2.50`, `FIT_THRESHOLD = 0.45`, and `SOFT_LIMIT_RATIO = 0.65`, while keeping `INVENTORY_SKEW = 0.035`, `MAX_TAKE_SIZE = 10`, and the existing trend hold bonuses. It also worked better with `PASSIVE_SIZE = 8` and `TREND_PASSIVE_PUSH = 0.0`, which suggests the family wants stronger directional conviction mainly through taking and target persistence, not through extra passive leaning. This is a useful structural result: the next optimum seems to come from faster commitment to a trend, not from the heaviest possible carry settings. Outputs live in `Analysis/output/v20_sweep_report.txt` and `Analysis/output/v20_sweep_results.csv`.
PnL: Rust Sweep Best 13'431 | Baseline 13'340

V20.1:
Works: Yes
Improvement: Clean upload-safe implementation of the best V20 risk-sweep result. It keeps EMERALDS unchanged and applies the winning TOMATOES carry settings directly into the bot defaults.
Notes: Small but real improvement. Official PnL moved from 2'264.445 in V18 to 2'266.016. EMERALDS stayed unchanged at 1'050.0, so the gain came only from TOMATOES: 1'214.445 -> 1'216.016. This confirmed the riskier carry family works, but only marginally so far.
PnL: Official 2'266.0 | Rust: 13'431

V21:
Works: Yes
Improvement: First attempt at a much riskier TOMATOES engine built around breakout trend-following instead of the existing regression/carry family. The design introduces rolling breakout levels, volatility filters, ATR-style scaling, pyramiding, wide trailing stops, and a kill-switch layer. The second implementation softened the idea into a hybrid by falling back to the active V20.1 TOMATOES engine when no breakout state was live, so the branch could still trade day-to-day flow while trying to become more convex in strong moves.
Notes: Clear negative result. Pure breakout ended at 7'290 Rust PnL with TOMATOES at -113. The hybrid fallback version was even worse at 7'105 with TOMATOES at -298. Conclusion: a pure breakout engine is too sparse and brittle for this market.
PnL: Official N/A | Rust Pure 7'290 | Rust Hybrid 7'105

V22:
Works: Yes
Improvement: Full switch to the opposite extreme of V21. EMERALDS stays unchanged, while TOMATOES becomes a maker-first mean-reversion / market-making engine with dynamic fair value, deviation-based target inventory, tighter recycling, and much lower willingness to carry trends.
Notes: Good counter-model, but clearly weaker than the best carry family. Local Rust PnL reached 11'693 versus 13'431 for V20.1. EMERALDS stayed at 7'403, while TOMATOES came in at 4'290. The useful part is that V22 is active and stable, so it gives us a real opposite pole for a later V23 hybrid or interpolation sweep.
PnL: Official N/A | Rust: 11'693

V23:
Works: Yes
Improvement: First true hybrid between the V20.1 carry model and the V22 mean-reversion model for TOMATOES. It blends both target-position views and fair values into one shared execution layer.
Notes: The first bridge did not find a good middle ground. Local Rust PnL was 9'657 with EMERALDS unchanged at 7'403 and TOMATOES only 2'254. A wider local blend sweep also came out flat, so this implementation is not expressing the blend strongly enough to create a useful new optimum.
PnL: Official N/A | Rust: 9'657

V23.1:
Works: Yes
Improvement: Regime-switch version of V23. Instead of blending every tick, TOMATOES now switches hard between the carry engine in directional states and the fade engine in range/stretch states.
Notes: Also a miss. Local Rust PnL was 9'555 with EMERALDS unchanged at 7'403 and TOMATOES at 2'152. So a simple carry-versus-fade handoff did not solve the problem either and was slightly worse than the blended V23.
PnL: Official N/A | Rust: 9'555

EMERALDS Minimal MM Check:
Works: Yes
Improvement: Quick side test of a very simple EMERALDS maker: buy at `best_bid + 1`, sell at `best_ask - 1`, with no tiered taking or clearing logic.
Notes: Simpler EMERALDS market making is viable, but not best. Local Rust total reached 12'981 with TOMATOES unchanged at 6'028, while EMERALDS fell from 7'403 to 6'953. So the minimal MM captures a lot of the edge, but the current EMERALDS engine still adds meaningful value.
PnL: Rust: 12'981

V24:
Works: Yes
Improvement: Rebuilds TOMATOES as an alpha-skewed adaptive market maker: predictive fair value, inventory-skewed two-sided quoting, join/undercut placement, and selective taking. EMERALDS stays unchanged from the current best family.
Notes: Close, but still below V20.1 locally. Rust PnL reached 13'305 versus 13'431 for V20.1. EMERALDS stayed fixed at 7'403, while TOMATOES came in at 5'902 versus 6'028 for V20.1. Trade count rose to 755, so this version clearly participated more, but the extra maker activity did not create enough edge to beat the stronger carry baseline.
PnL: Official N/A | Rust: 13'305

V24.1:
Works: Yes
Improvement: Makes the V24 maker engine more selective in trends: smaller passive clips, wider quote edge, slower trend exits, and much stricter join/undercut use outside clear range states.
Notes: This is now a genuinely different engine from V24, but it moved in the wrong direction locally. Rust PnL came in at 13'151 with EMERALDS unchanged at 7'403 and TOMATOES at 5'748. Trade count dipped slightly to 752, so the extra selectivity reduced participation but did not improve edge.
PnL: Official N/A | Rust: 13'151

V25:
Works: Yes
Improvement: Adds a lightweight online-ML layer on top of V20.1 for TOMATOES. It learns a small linear forecast from microprice drift, momentum, imbalance, and regression context, then blends that prediction into the existing carry signal only when the model's recent error history looks good.
Notes: No practical change locally. Rust PnL tied V20.1 exactly at 13'431, with EMERALDS 7'403, TOMATOES 6'028, and 721 own trades. So this first ML overlay is valid and safe, but currently too weak or too aligned with the base model to move actual decisions.
PnL: Official N/A | Rust: 13'431

V25.1:
Works: Yes
Improvement: Offline-trained TOMATOES model on top of V20.1. The model is fitted on day -2 price data and adds a short-horizon forecast for immediate edge plus a longer-horizon directional forecast for carry/hold bias, while EMERALDS stays unchanged.
Notes: Good local lift, weak official transfer. Rust improved from 13'431 to 13'556, but official PnL slipped from 2'266.016 to 2'259.445. EMERALDS stayed identical at 1'050.0; the miss came entirely from TOMATOES. Buys improved a bit, but sells got much worse because the offline model traded more and gave back exit quality.
PnL: Official 2'259.4 | Rust 13'556

V26:
Works: Yes
Improvement: Physics-assisted TOMATOES hybrid on top of the V20.1 base. Uses slow-fair displacement, velocity, acceleration, order-book force, and a Peclet-style drift-vs-noise score to bias the existing carry engine rather than replace it.
Notes: The pure physics rewrite was a complete miss locally, but the best hybrid recovered to a stable result. EMERALDS stayed unchanged at 7'403 and TOMATOES came in at 5'869, still below V20.1's 6'028. Useful conceptually, but not a better bot yet.
PnL: Official N/A | Rust 13'272

V27:
Works: Yes
Improvement: Keeps the V20.1 TOMATOES alpha and regime logic, but replaces part of the execution/control layer with an HJB-style reservation-price model. Inventory, volatility, and time remaining now adjust the reservation price and quote width instead of only using fixed skew rules.
Notes: Strong local result and a real official improvement. Rust PnL improved from 13'431 to 13'674. On the official site, V27 reached about 2'292.9, beating V20.1's 2'266.0. EMERALDS stayed unchanged at 1'050, so the whole gain came from TOMATOES.
PnL: Official 2'292.9 | Rust 13'674

V27 PDE Sweep:
Works: Yes
Improvement: Tests where PDE-style control helps most inside the V27 family: reservation price, quote spread, take thresholds, hold bonuses, and combinations of them.
Notes: The biggest lever was quote-spread control. `spread_strong` was best at 13'877, moving TOMATOES from 6'271 to 6'474 with the same 721 trades. Reservation control mattered too, but the best reservation result came from turning most of it off, which suggests V27's reservation shift is too strong while its spread control is still underused. Take control was mostly noise, and hold control helped only a little.
PnL: Best Rust 13'877 | Baseline 13'674

V27 Alpha/Hold Sweep:
Works: Yes
Improvement: Tests a continuation of V27 in two directions: adjusting the alpha region itself and replacing the fixed TOMATOES soft inventory bound with a regime-aware dynamic holding limit that still stays below the hard cap of 80.
Notes: Alpha mattered a little; dynamic holding limits did not. `alpha_light` was best at 13'721, improving TOMATOES from 6'271 to 6'318 with the same 721 trades. All three dynamic holding-limit variants tied the V27 baseline exactly, so the current target/quote logic is not really constrained by that soft bound yet.
PnL: Best Rust 13'721 | Baseline 13'674

V27.1:
Works: Yes
Improvement: Combines the two best V27 continuation levers: stronger PDE-style spread control and the light alpha-region boost.
Notes: Best local V27 continuation so far. Rust PnL improved from 13'674 to 13'881 with EMERALDS unchanged at 7'403 and TOMATOES improving from 6'271 to 6'478. Trade count stayed fixed at 721, so the gain still looks like cleaner control and better TOMATOES pricing rather than extra activity.
PnL: Official N/A | Rust 13'881

V27.1 Broad Sweep:
Works: Yes
Improvement: Much wider continuation search around V27.1 across alpha scaling, reservation control, spread control, gamma/risk settings, and asymmetric trend-hold behavior.
Notes: This broader search found a meaningfully better local region than the earlier hand-picked sweeps. Best result was `broad_random_22` at 14'236 Rust PnL, driven entirely by TOMATOES at 6'833. The strongest pattern was: wider control-layer spreads, heavier reservation scaling, stronger imbalance use, and extra trend-side sell patience.
PnL: Best Rust 14'236 | Baseline 13'956

V27.2:
Works: Yes
Improvement: Clean upload-safe continuation of V27.1 using the best broad-sweep direction: stronger spread control, stronger reservation scaling, a lighter alpha edge multiplier, heavier imbalance scaling, and extra TOMATOES trend-side sell patience.
Notes: Strong official continuation. Rust PnL reached 14'016, and the official result improved from 2'292.875 to 2'359.875. EMERALDS stayed exactly fixed at 1'050.0, so the whole gain came from TOMATOES again. Official TOMATOES improved from 1'242.875 to 1'309.875, with the same trade counts but better average buy and sell prices.
PnL: Official 2'359.9 | Rust 14'016

V27.3a:
Works: Yes
Improvement: Isolates the spread-heavy part of the V27.2 improvement path: wider PDE-style quote-width control and a slightly wider base quote edge, while leaving reservation and sell-patience closer to V27.1.
Notes: Best of the three isolated subfamilies. Rust PnL reached 14'081 with TOMATOES at 6'678 and 721 trades. That says spread control is the strongest single lever inside the V27.2 family.
PnL: Official N/A | Rust 14'081

V27.3b:
Works: Yes
Improvement: Isolates the reservation-heavy part of the V27.2 path: stronger gamma terms and reservation biases, with spread and sell-patience closer to V27.1.
Notes: Weaker than both the spread-only and sell-patience-only branches. Rust PnL reached 13'835 with TOMATOES at 6'432 and 721 trades. Reservation control still matters, but it does not appear to be the main driver of the latest gains.
PnL: Official N/A | Rust 13'835

V27.3c:
Works: Yes
Improvement: Isolates the sell-patience path: firmer base take edge and extra trend-side hold bonuses, with reservation and spread closer to V27.1.
Notes: Positive, but not as strong as the spread-heavy branch. Rust PnL reached 13'892 with TOMATOES at 6'489 and 720 trades. Sell patience helps, but not as much as stronger spread control.
PnL: Official N/A | Rust 13'892

V27.2 Region Sweep:
Works: Yes
Improvement: Tighter continuation sweep around the V27.2 neighborhood, searching whether spread control, reservation control, or sell-patience style changes still dominate once combined with the stronger baseline.
Notes: The best regional result was `region_random_53` at 14'350 Rust PnL, beating the V27.2-region baseline of 14'236. Spread-heavy designed cases were the best structured family, but the top random region added even more TOMATOES edge through stronger imbalance scaling, stronger spread control, a firmer take edge, and larger trend-side sell hold.
PnL: Best Rust 14'350 | Baseline 14'236

V27.3:
Works: Yes
Improvement: Clean upload-safe continuation of the best V27.2 regional sweep result. Keeps EMERALDS frozen and applies the strongest local TOMATOES combination from `region_random_53`.
Notes: Best current bot overall. Rust PnL reached 14'350 exactly, and both official runs came back identical at 2'381.875. EMERALDS stayed exactly fixed at 1'050.0, so the whole official gain over V27.2 came from TOMATOES again. Official TOMATOES improved from 1'309.875 to 1'331.875 with the same trade counts and better average buy and sell prices. The repeated identical result is a strong sign that the gain is stable rather than lucky.
PnL: Official 2'381.9 (twice) | Rust 14'350

V28.1:
Works: Yes
Improvement: Riskier continuation of V27.3 through wider TOMATOES trend inventory bands, allowing the bot to carry more directional exposure in confirmed trend states.
Notes: No local change at all. Rust PnL tied V27.3 exactly at 14'350 with TOMATOES unchanged at 6'947 over 722 trades. That suggests the wider bands did not bind in the current winning path, so simply expanding the allowed carry range is not enough by itself.
PnL: Official N/A | Rust 14'350

V28.2:
Works: Yes
Improvement: Riskier continuation of V27.3 through lower TOMATOES inventory skew, so the bot flattens more slowly and tolerates larger carried positions before leaning back toward flat.
Notes: Worse locally. Rust PnL dropped to 14'209 with TOMATOES at 6'806 and 720 trades. So reducing inventory skew directly gave back edge rather than unlocking a better higher-drawdown path.
PnL: Official N/A | Rust 14'209

V28.3:
Works: Yes
Improvement: Riskier continuation of V27.3 through stronger trend-side hold bonuses and slower exits, aiming to let TOMATOES winners run longer and accept more drawdown on the way.
Notes: Clearly worse locally. Rust PnL fell to 14'030 with TOMATOES at 6'627 over 722 trades. This suggests that the current V27.3 engine is already close to the useful edge in exit patience, and pushing it further mostly delays good exits instead of improving carry.
PnL: Official N/A | Rust 14'030

V27.3 Combo Sweep:
Works: Yes
Improvement: Broader combination-style search around the V27.3 winner, testing interactions between spread control, imbalance scaling, take edge, reservation control, and trend-side hold behavior.
Notes: The best result was still mostly a spread-control story. `spread_plus` reached 14'384 Rust PnL, beating the V27.3 baseline of 14'350. Most other combinations were flat or worse, which suggests the current family has little room outside stronger quote-width control.
PnL: Best Rust 14'384 | Baseline 14'350

V29:
Works: Yes
Improvement: Clean upload-safe continuation of V27.3 using the best V27.3 combo result: slightly wider base quote edge and stronger spread-control coefficients.
Notes: Small but real official improvement. Rust PnL reached 14'384 with EMERALDS unchanged at 7'403 and TOMATOES at 6'981 over 722 trades. Officially, V29 improved from 2'381.875 to 2'386.875. EMERALDS stayed exactly fixed at 1'050.0, and TOMATOES improved from 1'331.875 to 1'336.875 with the same trade counts, a slightly better average buy, and an unchanged average sell.
PnL: Official 2'386.9 | Rust 14'384

V30:
Works: Yes
Improvement: First simplified redesign attempt. Prunes a lot of overlapping control logic and keeps a much more compact fair-value, inventory, and spread framework.
Notes: Runs cleanly, but simplification cost a lot of edge. Rust PnL reached 10'745 with EMERALDS at 6'394 and TOMATOES at 4'351 over 612 trades. So the leaner structure is workable, but too much of the profitable control logic was removed.
PnL: Official N/A | Rust 10'745

V30.1:
Works: Yes
Improvement: Alternative simplified branch with the same general cleanup idea but slightly different weights and quoting behavior.
Notes: Much weaker than both V29 and V30. Rust PnL reached only 5'008 with EMERALDS at 2'274 and TOMATOES at 2'734 over 661 trades. This version is runnable, but clearly not competitive.
PnL: Official N/A | Rust 5'008

V29.1 Family:
Works: Yes
Improvement: Three narrow continuations of V29 clean, isolating spread control, sell patience, and deeper imbalance usage.
Notes: The only branch that improved was the spread-heavy one. All three kept EMERALDS fixed at 7'403 and 722 trades, so the differences are entirely TOMATOES control quality.
PnL: Baseline Rust 14'384 | Best Rust 14'430

V29.1a:
Works: Yes
Improvement: Spread-heavy branch with a wider base quote edge and stronger volatility, inventory, and time-based spread control.
Notes: Best of the family. Rust PnL reached 14'430 with TOMATOES at 7'027 over 722 trades, beating V29 clean by 46. This says spread control is still the strongest live lever in the current family.
PnL: Official N/A | Rust 14'430

V29.1b:
Works: Yes
Improvement: Sell-patience-heavy branch with stronger trend-side hold bonuses, extra sell hold, higher quote lift, and more time-based hold.
Notes: Worse than baseline. Rust PnL dropped to 14'042 with TOMATOES at 6'639 over 722 trades. So extra exit patience in this family is still giving back too much edge.
PnL: Official N/A | Rust 14'042

V29.1c:
Works: Yes
Improvement: Deeper-imbalance-heavy branch with stronger imbalance weighting and an easier trend imbalance threshold.
Notes: Better than the sell-patience branch but still below baseline. Rust PnL reached 14'168 with TOMATOES at 6'765 over 722 trades. Imbalance matters, but not as much as cleaner spread control.
PnL: Official N/A | Rust 14'168

V29.2:
Works: Yes
Improvement: Adds a TOMATOES rebound-exit gate for long inventory accumulated in downtrends, suppressing sells until either a rebound, a time release, or an adverse stop.
Notes: Completely neutral locally. Rust PnL tied V29 exactly at 14'384 with EMERALDS at 7'403, TOMATOES at 6'981, and 722 trades. So the idea is not obviously wrong, but in this form it did not bind enough to change behavior.
PnL: Official N/A | Rust 14'384

V29.3:
Works: Yes
Improvement: Quote-refined continuation of the spread-heavy V29.1a branch, adding slightly stronger directional quote skew in TOMATOES trend states.
Notes: Positive, but not a new local winner. Rust PnL reached 14'430 with EMERALDS at 7'403 and TOMATOES at 7'027 over 722 trades, exactly matching V29.1a. So the quote asymmetry is viable, but this version did not improve beyond the existing spread-heavy optimum.
PnL: Official N/A | Rust 14'430

V29.1a Plateau Sweep:
Works: Yes
Improvement: Focused local sweep around the V29.1a / V29.3 plateau, searching for another hidden pocket in the spread-heavy region instead of inventing a new strategy family.
Notes: The plateau was breakable, but only slightly. Best result was `spread_plus_small` at 14'438, beating V29.1a by 8. The winning region again came entirely from TOMATOES and kept the same 722 trades, so this is still a quote-control improvement rather than a flow change.
PnL: Best Rust 14'438 | Baseline 14'430

V29.4:
Works: Yes
Improvement: Clean upload-safe continuation of the plateau sweep winner, pushing the spread-heavy region slightly further with a higher base quote edge and stronger volatility, inventory, and time spread coefficients.
Notes: New best official bot. Rust PnL reached 14'438 with EMERALDS unchanged at 7'403 and TOMATOES at 7'035 over 722 trades. Officially, V29.4 improved from 2'386.875 to 2'394.875. EMERALDS stayed exactly fixed at 1'050.0, and TOMATOES improved from 1'336.875 to 1'344.875 with the same trade counts, a slightly better average buy, and an unchanged average sell.
PnL: Official 2'394.9 | Rust 14'438
