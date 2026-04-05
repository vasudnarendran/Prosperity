# Backtest

Run the backtest from inside this folder:

```bash
python3 backtest
```

That uses the current default bot:

```bash
Traderv9.py
```

You can test a different bot like this:

```bash
python3 backtest Traderv8.py
```

Outputs are written to:

```bash
output/<bot_name>/
```

Main files:

- `output/<bot_name>/summary.txt`
- `output/<bot_name>/step_log.csv`
- `output/<bot_name>/fills.csv`
- `output/<bot_name>/product_log.csv`
- `output/<bot_name>/pnl_overview.png`
- `output/<bot_name>/positions.png`
- `output/<bot_name>/emeralds_price_and_fills.png`
- `output/<bot_name>/tomatoes_price_and_fills.png`

What this local backtest does:

- feeds real market snapshots from `Data/`
- loads your trader file directly from `Bots/` or `Bots/archive/`
- simulates immediate fills for crossing orders
- simulates one-interval resting fills for passive orders
- tracks cash, positions, product PnL, and total PnL

Important note:

This is meant to be a useful local approximation of Prosperity-style testing, but it is not the official hidden simulator.
