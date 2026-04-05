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

Record Total PnL: 2'264
Bot: Trader v18

Failed_Bot_Count: 5

Current Best Notes:
V18 is currently the best official bot.
It keeps the V16 EMERALDS engine unchanged and replaces the older TOMATOES microstructure overlay with a regression-based predictive model that improved TOMATOES entry quality significantly.

# Current Parameter Map:
Based on [Traderv18.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv18.py), which is the current best official bot.

| Product | Fair Value | Inventory Skew | Take Logic | Quote Logic | Size Logic | Target / Bias |
| --- | --- | --- | --- | --- | --- | --- |
| `EMERALDS` | `0.80 * 10000 + 0.20 * mid` | `0.12` against current position | Tiered taking by distance from fair: small / medium / large clips, plus explicit clear orders near fair | Join or step-inside book-aware quotes using `disregard_edge`, `join_edge`, and `default_edge`, with early inventory leaning | Base order size `10`, larger on the side that helps flatten, smaller on the wrong side | Fixed-anchor market maker around `10000` with explicit inventory recycling |
| `TOMATOES` | `0.25 * mid + 0.30 * micro + 0.25 * history + 0.20 * predicted_next + 0.35 * imbalance`, plus small regression-gap adjustment | `0.06` against current position | Base take edge `1.45`, shifted by forecasted edge, fit quality, inventory, spread, and volatility | Base quote edge `2.25`, capped at `5.0`, widened in volatile/trending states | Passive size `8`, reduced in volatile/trending states, then adjusted by inventory and volatility | Predictive regime model: `trend_up`, `trend_down`, `range`, `volatile` |

Important candidate note:
- `V18` is the new official best because it found a different TOMATOES optimum: much better buy timing with the regression-based model, even though sell prices are slightly weaker.
- `V18.1` is the current best local refinement candidate from the regression sweep and keeps the same model family with a longer forecast horizon and tighter taking.

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
- `INVENTORY_SKEW = 0.06`
- `BASE_TAKE_EDGE = 1.45`
- `BASE_QUOTE_EDGE = 2.25`
- `MAX_QUOTE_EDGE = 5.0`
- `PASSIVE_SIZE = 8`
- `MAX_TAKE_SIZE = 8`
- `REGRESSION_WINDOW = 8`
- `REGRESSION_HORIZON = 1.5`
- `TREND_EDGE_THRESHOLD = 1.50`
- `FIT_THRESHOLD = 0.65`
- `TREND_IMBALANCE_THRESHOLD = 0.12`
- `TOXIC_VOLATILITY_THRESHOLD = 3.2`

Tomatoes predictive candidate levers from `V18.1`:
- `REGRESSION_HORIZON = 3.0`
- `TREND_EDGE_THRESHOLD = 1.25`
- `FIT_THRESHOLD = 0.55`
- `TREND_IMBALANCE_THRESHOLD = 0.18`
- `BASE_TAKE_EDGE = 1.25`
- `BASE_QUOTE_EDGE = 2.75`
- `MAX_TAKE_SIZE = 6`
- `RESIDUAL_REVERT_WEIGHT = 0.20`

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)
