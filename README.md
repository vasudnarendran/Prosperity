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

Record Total PnL: 1'800
Bot: Trader v9

Failed_Bot_Count: 5

Current Best Notes:
V9 is the current record bot.
It improved both TOMATOES and EMERALDS slightly over V8 without changing the overall trade profile too aggressively.

Version Log:
See [BOT_VERSIONS.md](/Users/xavierwinkelmann/Prosperity/BOT_VERSIONS.md)
