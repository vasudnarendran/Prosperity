# Prosperity
Coding an Algorithm that trades for you


# Backtest
Usless


# Bots
Continueing to improve the Bots 

Record Total PnL: 1'764
Bot: Trader v6.2

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
Works: Not tested yet
Improvement: Starts from V6.2 and adds a TOMATOES-only dynamic fair value using current mid, microprice, and short traderData mid-history, without hard quote suppression or regime blocking.
Notes: Built as a cleaner next step after V6.4, keeping the strong V6.2 execution while only improving the TOMATOES fair-value estimate.
PnL:
