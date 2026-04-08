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

Record Total PnL: 2'640.875
Bot: Trader v39.4

Failed_Bot_Count: 50

Current Best Notes:
V39.4 is currently the best official bot in the repo.
It keeps the stronger `V39.2` hybrid execution core, but improves TOMATOES fair estimation with a persistent EWMA wall-fair signal built from large nearby quotes. The key gain was not EMERALDS, which stayed at the standard `1'050` profile, but a cleaner TOMATOES fair proxy that lifted official total PnL above `V39.2`. Follow-up variants confirmed that the wall signal transfers best as a persistent fair-value anchor rather than as an extra alpha input.

# Performance Maxes
These are the highest scores reached so far. The best single-product peak does not always come from the best total bot.

## Local Rust Backtester

| Metric | Best Value | Bot |
| --- | ---: | --- |
| Total PnL | `15'825` | `V40.7` |
| EMERALDS PnL | `7'723` | `V29.8`, later matched by `V29.9`, `V39`, and `V39.1` |
| TOMATOES PnL | `8'102` | `V40.7`, later matched by `V40.9.2` |

## Official Logs

| Metric | Best Value | Bot |
| --- | ---: | --- |
| Total PnL | `2'640.875` | `V39.4` |
| EMERALDS PnL | `1'050.0` | `V16` first reached it, later matched by several bots including `V29.4`, `V39`, and `V39.2` |
| TOMATOES PnL | `1'590.875` | `V39.4` |

# Current Parameter Map:
Based on [Traderv39_4.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv39_4.py), which is the current best official bot.

| Product | Fair Value | Inventory Skew | Take Logic | Quote Logic | Size Logic | Target / Bias |
| --- | --- | --- | --- | --- | --- | --- |
| `EMERALDS` | `0.80 * 10000 + 0.20 * mid` | `0.12` against current position | Tiered taking by distance from fair: small / medium / large clips, plus explicit clear orders near fair | Join or step-inside book-aware quotes using `disregard_edge`, `join_edge`, and `default_edge`, with early inventory leaning | Base order size `10`, larger on the side that helps flatten, smaller on the wrong side | Fixed-anchor market maker around `10000` with explicit inventory recycling |
| `TOMATOES` | `0.25 * mid + 0.30 * micro + 0.25 * history + 0.20 * predicted_next + 0.35 * imbalance`, plus trend fair-value carry bonus | `0.035` against current position, then adjusted again through a reservation-price control layer | Base take edge `1.25`, shifted by forecasted edge, fit quality, inventory, spread, volatility, trend-carry bonuses, and stronger control-layer hold adjustments | Base quote edge `2.75`, then widened or tightened by PDE/HJB-style spread control using stronger volatility, inventory, and time coefficients | Passive size `8`, trend passive-size bonus `2`, max take size `10` | Predictive carry regime model with inventory-aware reservation price, adaptive quote-width control, and stronger trend-side exit patience |

Important candidate note:
- `V39.4` is now the official best and improved over `V39.2` by about `+16.7`.
- The gain again came entirely from TOMATOES, while EMERALDS stayed unchanged at `1'050`.
- The key transfer insight so far is that a persistent wall-fair estimate helps, but stronger local wall-fair calibrations like `V39.6` can still over-activate TOMATOES on the official replay.
- The current split in evidence is: `V39.4` is the best official-transfer bot, while `V40.7` is still the best local Rust bot.

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
- `BASE_TAKE_EDGE = 1.25`
- `BASE_QUOTE_EDGE = 2.75`
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
- `GAMMA_RANGE = 0.34`
- `GAMMA_TREND = 0.10`
- `GAMMA_VOLATILE = 0.40`
- `RESERVATION_SCALE = 0.12`
- `TREND_RESERVATION_BIAS = 0.04`
- `RANGE_RESERVATION_BIAS = 0.20`
- `SPREAD_VOL_COEF = 0.90`
- `SPREAD_INV_COEF = 0.42`
- `SPREAD_TIME_COEF = 0.90`
- `HOLD_VOL_COEF = 0.0`
- `HOLD_TIME_COEF = 0.08`
- `ALPHA_EDGE_SCALE = 1.06`
- `ALPHA_IMBALANCE_SCALE = 1.16`
- `ALPHA_THRESHOLD_SCALE = 1.03`
- `TREND_SELL_HOLD_EXTRA = 0.24`
- `TREND_BUY_TAKE_EXTRA = 0.08`
- `TREND_QUOTE_LIFT_EXTRA = 1.0`

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)

Monte Carlo Comparison:
See [MONTE_CARLO_COMPARISON.md](/Users/xavierwinkelmann/Prosperity/MONTE_CARLO_COMPARISON.md)

Latest Monte Carlo note:
- The heavier 1000-session run for [Traderv39_6.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv39_6.py) came in strong under the generator with mean total PnL `15,524.24` and mean TOMATOES PnL `7,990.81`, beating the earlier quick Monte Carlo means for `V39.2` and `V40.7`.
- But `V39.6` still underperformed on the official replay, so Monte Carlo strength alone is not enough to promote a bot over `V39.4`.
