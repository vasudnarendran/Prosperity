## How to run the backtest

Run this in the VS Code terminal from the project folder:

```bash
python3 backtest_round0.py
```

After the script finishes, it saves files into:

```bash
backtest_output/
```



## What gets generated

### 1. Full log CSV

```bash
backtest_output/backtest_log.csv
```

This contains the step-by-step output of the backtest, for example:
- day
- timestamp
- positions
- mid prices
- portfolio mark-to-market value
- executed orders

### 2. Portfolio plot

```bash
backtest_output/portfolio_mtm.png
```

This shows the portfolio mark-to-market value over time.

### 3. Position plot

```bash
backtest_output/positions.png
```

This shows how your position in `EMERALDS` and `TOMATOES` changes over time.

## How to view the plots

You do **not** need to read only the CSV.

In VS Code, open the files directly:

- `backtest_output/portfolio_mtm.png`
- `backtest_output/positions.png`

VS Code will show them as images.

You can also open them in Finder by navigating to the `backtest_output` folder.