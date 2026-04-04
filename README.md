# Prosperity
Coding an Algorithm that trades for you


# Backtest
Usless


# Bots
Continueing to improve the Bots 

Record Total PnL: 1'791
Bot: Trader v8

Failed_Bot_Count: 5

# Bot Version Log
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
