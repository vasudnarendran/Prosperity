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
Notes: This is the first version where the optimization workflow mattered as much as the strategy idea itself. The layered Rust sweep lifted local PnL from 10'046 to 10'326, and almost all of that gain came from TOMATOES while EMERALDS stayed flat at 4'902. The biggest positive shifts were lower TOMATOES inventory skew, higher TOMATOES take edge, higher TOMATOES momentum weight, and slightly larger TOMATOES passive size. EMERALDS was surprisingly stable: its best values stayed very close to the old baseline, which reinforces the view that EMERALDS is already near a local optimum while TOMATOES still has more room. The sweep outputs live in `Analysis/output/v15_sweep_report.txt` and `Analysis/output/v15_sweep_results.csv`.
PnL: Official N/A | Rust: 10'326
