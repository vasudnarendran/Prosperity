# Round 0 Local Backtest v2

## Run

From the folder containing `Trader.py`, `datamodel.py`, and the CSV files:

```bash
python3 backtest_round0_v2.py
```

## What it writes

Everything goes into `backtest_output_v2/`:

- `step_log.csv` – one row per simulator timestamp
- `product_log.csv` – one row per product per timestamp
- `fills.csv` – every executed fill
- `status_log.csv` – tells you whether the bot was active, had no fills, or sat at the position limit
- `total_pnl.png` – the main PnL curve
- `positions.png` – positions over time
- `<product>_price_and_fills.png` – mid price with your buy/sell markers
- `<product>_pnl.png` – per-product mark-to-market PnL
- `summary.txt` – quick overview

## Why this is better than the old version

The old log could look like it stopped because it only gave you a coarse timestamp-level view. This version also writes a product-level log and a status log, so you can see whether the bot:

- still submitted orders
- got no fills
- hit the position limit
- crashed with an exception

## Fill logic

This is still a replay backtest, not the official Prosperity engine.
It fills only when your order crosses the visible best prices in the snapshot.
That makes it useful for debugging and strategy iteration, but not a perfect competition replica.
