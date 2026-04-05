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

Record Total PnL: 2'187
Bot: Trader v17.1

Failed_Bot_Count: 5

Current Best Notes:
V17.1 is currently the best official bot.
It keeps the V16 EMERALDS engine unchanged and adds a lighter TOMATOES microstructure overlay that improved execution quality without changing overall TOMATOES trade flow.

# Current Parameter Map:
Based on [Traderv16.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv16.py), which is the current best official bot.

| Product | Fair Value | Inventory Skew | Take Logic | Quote Logic | Size Logic | Target / Bias |
| --- | --- | --- | --- | --- | --- | --- |
| `EMERALDS` | `0.80 * 10000 + 0.20 * mid` | `0.12` against current position | Tiered taking by distance from fair: small / medium / large clips, plus explicit clear orders near fair | Join or step-inside book-aware quotes using `disregard_edge`, `join_edge`, and `default_edge`, with early inventory leaning | Base order size `10`, larger on the side that helps flatten, smaller on the wrong side | Fixed-anchor market maker around `10000` with explicit inventory recycling |
| `TOMATOES` | `0.35 * mid + 0.35 * micro + 0.30 * history + 0.30 * momentum + 0.70 * imbalance` | `0.06` against current position | Base take edge `1.50`, shifted by regime, inventory, spread, and toxicity | Base quote edge `2.25`, capped at `5.0`, widened in toxic/trending states | Passive size `8`, reduced in toxic/trending states, then adjusted by inventory and toxicity | Regime-driven: `trend_up`, `trend_down`, `mean_revert`, `toxic` |

Important candidate note:
- `V17.1` keeps the `V16` EMERALDS logic unchanged and only upgrades TOMATOES with a lighter microstructure overlay. Best local settings were `BASE_TAKE_EDGE = 1.35`, `BASE_QUOTE_EDGE = 2.50`, `PRESSURE_MICRO_COEF = 0.60`, `PRESSURE_SHORT_MOMENTUM_COEF = 0.35`, `PRESSURE_IMBALANCE_COEF = 1.80`, `PRESSURE_FAIR_BONUS = 0.15`, `PRESSURE_EDGE_BONUS = 0.0`, and `PRESSURE_QUOTE_THRESHOLD = 1.60`.

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
- `MID_WEIGHT = 0.35`
- `MICRO_WEIGHT = 0.35`
- `HISTORY_WEIGHT = 0.30`
- `MOMENTUM_WEIGHT = 0.30`
- `IMBALANCE_WEIGHT = 0.70`
- `INVENTORY_SKEW = 0.06`
- `BASE_TAKE_EDGE = 1.50`
- `BASE_QUOTE_EDGE = 2.25`
- `MAX_QUOTE_EDGE = 5.0`
- `PASSIVE_SIZE = 8`
- `MAX_TAKE_SIZE = 8`

Tomatoes microstructure candidate levers from `V17.1`:
- `BASE_TAKE_EDGE = 1.35`
- `BASE_QUOTE_EDGE = 2.50`
- `PRESSURE_MICRO_COEF = 0.60`
- `PRESSURE_SHORT_MOMENTUM_COEF = 0.35`
- `PRESSURE_IMBALANCE_COEF = 1.80`
- `PRESSURE_FAIR_BONUS = 0.15`
- `PRESSURE_EDGE_BONUS = 0.0`
- `PRESSURE_QUOTE_THRESHOLD = 1.60`

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)
