# Prosperity 4 Monte Carlo Backtester

Test your trading strategies against a calibrated simulation of the Prosperity 4 market and compete on the leaderboard.

This release bundle is standalone. You do not need Cargo, Node, or a full repo checkout. The zip already includes the Rust simulator binary, built visualizer assets, tutorial data, and the Python CLIs.

## Quick Start

```bash
# 1. Install Python dependencies
pip install typer jsonpickle numpy orjson pandas tqdm

# 2. Write your trader (see example_trader.py and datamodel.py)
cp example_trader.py my_trader.py
# Edit my_trader.py with your strategy...

# 3. Run a quick test (100 sessions, ~1 min)
python -m prosperity4mcbt my_trader.py --quick --vis

# 3.5 Check your install and latest release
python -m prosperity4mcbt --self-test

# 4. Submit to the leaderboard
python -m prosperity4mcbt my_trader.py --leaderboard-run --display-name "your_name" --vis
```

## Commands

### Quick Test (100 sessions)
```bash
python -m prosperity4mcbt my_trader.py --quick --vis
```
Fast iteration. ~1 minute. Opens the dashboard in your browser when done.

### Heavy Test (1000 sessions)
```bash
python -m prosperity4mcbt my_trader.py --heavy --vis
```
More statistically stable. ~10 minutes.

### Custom Run
```bash
python -m prosperity4mcbt my_trader.py --sessions 500 --vis
```

### Self Test / Update Check
```bash
python -m prosperity4mcbt --self-test
```
Checks the local install, Rust toolchain, and the latest published release. Normal runs also warn automatically if a newer release is available.

### Leaderboard Submission
```bash
python -m prosperity4mcbt my_trader.py --leaderboard-run --display-name "your_name" --vis
```
Runs 1,000 sessions with locked settings (same for everyone). Your score is automatically submitted to the public leaderboard. Each machine gets a unique ID on first run — your best score is kept.

## Fixes In This Release

- The extracted bundle now runs directly against the packaged `bin/prosperity4_sim` binary instead of expecting a repo checkout with `rust_simulator/`.
- `--self-test` and automatic update notices now report the shipped release version correctly.
- The zip is built from a clean staging directory, so duplicate frontend assets and stale data folders are no longer carried into the release.
- The README and platform notes now match the current CLI flags and supported release targets.

## Writing a Trader

Your trader must be a Python file with a `Trader` class that has a `run` method:

```python
from datamodel import Order, TradingState

class Trader:
    def run(self, state: TradingState):
        orders = {}
        for product in state.order_depths:
            orders[product] = []
            # Your logic here — add Order objects to orders[product]
        
        return orders, 0, ""
```

See `example_trader.py` for a working example and `datamodel.py` for all available types.

### Key Objects

- `state.order_depths[product]` — current order book (`.buy_orders`, `.sell_orders` dicts of `{price: volume}`)
- `state.position` — dict of `{product: position}`
- `state.own_trades` — your fills from the previous tick
- `state.market_trades` — bot-vs-bot trades from the previous tick
- `Order(product, price, quantity)` — positive quantity = buy, negative = sell

### Products & Limits

| Product | Position Limit |
|---------|---------------|
| EMERALDS | 80 |
| TOMATOES | 80 |

## Dashboard

After a run with `--vis`, a local server starts and opens your browser. The dashboard shows:
- **Backtest tab** — PnL distribution, per-session paths, product breakdown
- **Leaderboard tab** — ranked submissions from all participants

The server runs in the background on `http://localhost:8001/`. To stop it, close your terminal or kill the process.

## Options Reference

```
python -m prosperity4mcbt --help

Options:
  --vis                Open dashboard in browser when done
  --quick              100 sessions, 10 sample paths
  --heavy              1000 sessions, 100 sample paths
  --sessions N         Custom session count
  --leaderboard-run    Locked settings + submit to leaderboard
  --display-name NAME  Your name on the leaderboard
  --self-test          Check install + latest published release
  --no-update-check    Skip the automatic release check
  --out PATH           Custom output path for dashboard
  -v, --version        Show version
```

## Requirements

- Python 3.9+
- One of the released platform bundles for macOS ARM64, macOS x86_64, Linux x86_64, or Windows x86_64
- `pip install typer jsonpickle numpy orjson pandas tqdm`
