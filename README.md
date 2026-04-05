# Prosperity
Coding an Algorithm that trades for you


# Backtest
Local backtesting is documented in [Backtest/README.md](/Users/xavierwinkelmann/Prosperity/Backtest/README.md).

Run it from the `Backtest` folder with:

```bash
python3 backtest Traderv9.py
```

The runner uses market data from `Data/`, loads the selected bot from `Bots/`, and writes logs plus plots to `Backtest/output/<bot_name>/`.


# Bots
Continueing to improve the Bots 

Record Total PnL: 2'266
Bot: Trader v20.1

Failed_Bot_Count: 5

Current Best Notes:
V20.1 is currently the best official bot.
It keeps the V16 EMERALDS engine unchanged and extends the V18 regression family with a slightly riskier TOMATOES carry profile that improved total PnL only marginally, mainly through a bit better TOMATOES exit quality.

# Current Parameter Map:
Based on [Traderv20_1.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv20_1.py), which is the current best official bot.

| Product | Fair Value | Inventory Skew | Take Logic | Quote Logic | Size Logic | Target / Bias |
| --- | --- | --- | --- | --- | --- | --- |
| `EMERALDS` | `0.80 * 10000 + 0.20 * mid` | `0.12` against current position | Tiered taking by distance from fair: small / medium / large clips, plus explicit clear orders near fair | Join or step-inside book-aware quotes using `disregard_edge`, `join_edge`, and `default_edge`, with early inventory leaning | Base order size `10`, larger on the side that helps flatten, smaller on the wrong side | Fixed-anchor market maker around `10000` with explicit inventory recycling |
| `TOMATOES` | `0.25 * mid + 0.30 * micro + 0.25 * history + 0.20 * predicted_next + 0.35 * imbalance`, plus trend fair-value carry bonus | `0.035` against current position | Base take edge `1.10`, shifted by forecasted edge, fit quality, inventory, spread, volatility, and trend-carry bonuses | Base quote edge `2.25`, capped at `5.0`, widened in volatile/trending states | Passive size `8`, trend passive-size bonus `2`, max take size `10` | Predictive carry regime model with wider trend bands and slower trend exits |

Important candidate note:
- `V20.1` is the new official best, but only by a very small margin over `V18`.
- The official gain came from TOMATOES again, but this time more through slightly better sell quality than better entries.
- `V18` is still the main structural breakthrough because it found the regression-based TOMATOES alpha family in the first place.

Emeralds key levers:
- `REFERENCE_WEIGHT = 0.80`
- `INVENTORY_SKEW = 0.12`
- `TAKE_TIER_1_DISTANCE = 1`
- `TAKE_TIER_2_DISTANCE = 4`
- `TAKE_TIER_3_DISTANCE = 8`
- `TAKE_TIER_1_SIZE = 6`
- `TAKE_TIER_2_SIZE = 12`
- `TAKE_TIER_3_SIZE = 20`
- `CLEAR_WIDTH = 0`
- `BASE_ORDER_SIZE = 10`
- `DISREGARD_EDGE = 2`
- `JOIN_EDGE = 1`
- `DEFAULT_EDGE = 8`
- `soft_limit = 20`

Tomatoes key levers:
- `MID_WEIGHT = 0.25`
- `MICRO_WEIGHT = 0.30`
- `HISTORY_WEIGHT = 0.25`
- `REGRESSION_WEIGHT = 0.20`
- `RESIDUAL_REVERT_WEIGHT = 0.12`
- `IMBALANCE_WEIGHT = 0.35`
- `INVENTORY_SKEW = 0.035`
- `BASE_TAKE_EDGE = 1.10`
- `BASE_QUOTE_EDGE = 2.25`
- `MAX_QUOTE_EDGE = 5.0`
- `PASSIVE_SIZE = 8`
- `MAX_TAKE_SIZE = 10`
- `REGRESSION_WINDOW = 8`
- `REGRESSION_HORIZON = 2.0`
- `TREND_EDGE_THRESHOLD = 1.00`
- `STRONG_TREND_EDGE = 2.50`
- `FIT_THRESHOLD = 0.45`
- `TREND_IMBALANCE_THRESHOLD = 0.12`
- `SOFT_LIMIT_RATIO = 0.65`
- `POSITION_BIAS_DIVISOR = 12.0`
- `TREND_FAIR_BONUS = 0.25`
- `TREND_ENTRY_TAKE_BONUS = 3.0`
- `TREND_HOLD_EXIT_BONUS = 0.55`
- `STRONG_TREND_HOLD_EXIT_BONUS = 0.90`
- `TREND_PASSIVE_PUSH = 0.0`
- `TREND_PASSIVE_SIZE_BONUS = 2.0`
- `TOXIC_VOLATILITY_THRESHOLD = 3.2`

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)
