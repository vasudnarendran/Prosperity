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

Record Total PnL: 1'850
Bot: Trader v11.3 / v13.1

Failed_Bot_Count: 5

Current Best Notes:
V11.3 and V13.1 currently tie as the best official bots.
They keep the strong TOMATOES engine from V9 and improve EMERALDS by using a more selective, higher-quality trade profile.

Current Parameter Map:
Based on [Traderv13_1.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv13_1.py), which matches the tied best official behavior.

| Product | Fair Value | Inventory Skew | Take Logic | Quote Logic | Size Logic | Target / Bias |
| --- | --- | --- | --- | --- | --- | --- |
| `EMERALDS` | `0.80 * 10000 + 0.20 * mid` | `0.12` against current position | Base take edge `1.00`, widened in wide spreads, easier buys when short, easier sells when long | Base quote edge `2.0`, capped at `4.0`, tightened when book touches `10000`, quotes lean toward flattening near soft limit | Passive size `7`, larger in wide spreads, larger on the side that helps flatten inventory | Fixed-anchor market maker around `10000` |
| `TOMATOES` | `0.35 * mid + 0.35 * micro + 0.30 * history + 0.20 * momentum + 0.70 * imbalance` | `0.08` against current position | Base take edge `1.35`, shifted by regime, inventory, spread, and toxicity | Base quote edge `2.0`, capped at `5.0`, widened in toxic/trending states | Passive size `7`, reduced in toxic/trending states, then adjusted by inventory and toxicity | Regime-driven: `trend_up`, `trend_down`, `mean_revert`, `toxic` |

Emeralds key levers:
- `REFERENCE_WEIGHT = 0.80`
- `INVENTORY_SKEW = 0.12`
- `BASE_TAKE_EDGE = 1.00`
- `BASE_QUOTE_EDGE = 2.0`
- `MAX_TAKE_SIZE = 10`
- `PASSIVE_SIZE = 7`
- `soft_limit = 40`

Tomatoes key levers:
- `MID_WEIGHT = 0.35`
- `MICRO_WEIGHT = 0.35`
- `HISTORY_WEIGHT = 0.30`
- `MOMENTUM_WEIGHT = 0.20`
- `IMBALANCE_WEIGHT = 0.70`
- `INVENTORY_SKEW = 0.08`
- `BASE_TAKE_EDGE = 1.35`
- `BASE_QUOTE_EDGE = 2.0`
- `MAX_QUOTE_EDGE = 5.0`
- `PASSIVE_SIZE = 7`
- `MAX_TAKE_SIZE = 8`

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)
