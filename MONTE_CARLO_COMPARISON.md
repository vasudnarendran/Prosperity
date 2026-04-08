# Monte Carlo Quick Comparison

Date: 2026-04-07

This note records the 100-session Monte Carlo quick-test comparison for the current top bots:

- [Traderv29_9.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv29_9.py)
- [Traderv39_2.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv39_2.py)
- [Traderv40_7.py](/Users/xavierwinkelmann/Prosperity/Bots/Traderv40_7.py)

Dashboard outputs:

- [traderv29_9_quick_dashboard.json](/Users/xavierwinkelmann/Prosperity/MonteCarloBacktester/backtests/traderv29_9_quick_dashboard.json)
- [traderv39_2_quick_dashboard.json](/Users/xavierwinkelmann/Prosperity/MonteCarloBacktester/backtests/traderv39_2_quick_dashboard.json)
- [traderv40_7_quick_dashboard.json](/Users/xavierwinkelmann/Prosperity/MonteCarloBacktester/backtests/traderv40_7_quick_dashboard.json)

## Summary Table

| Bot | Mean Total | Std | Median | 5% | 95% | Mean EMERALDS | Mean TOMATOES |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `v29.9` | 14,707.84 | 842.75 | 14,715.62 | 13,254.88 | 15,960.71 | 7,568.27 | 7,139.57 |
| `v39.2` | 15,428.74 | 1,002.06 | 15,420.75 | 13,834.90 | 16,993.25 | 7,568.27 | 7,860.47 |
| `v40.7` | 15,348.42 | 1,013.26 | 15,274.25 | 13,670.80 | 17,108.89 | 7,568.27 | 7,780.15 |

## TOMATOES Position Distribution

| Bot | Mean Final Position | Std | 5% | 95% |
| --- | ---: | ---: | ---: | ---: |
| `v29.9` | 3.98 | 9.37 | -10.10 | 17.00 |
| `v39.2` | 7.70 | 12.71 | -16.05 | 27.00 |
| `v40.7` | 7.51 | 12.60 | -14.10 | 25.05 |

## Read

- `v39.2` is the strongest all-around bot in this quick Monte Carlo comparison.
- `v40.7` is close, but slightly weaker on mean and median total PnL.
- `v40.7` has a slightly stronger upside tail than `v39.2` at the 95th percentile, so it looks a bit more swingy rather than clearly better.
- `v29.9` trails both hybrids clearly, and the gap comes almost entirely from TOMATOES.
- EMERALDS is effectively identical across all three bots in this test.

## Current Ranking

1. `v39.2`
2. `v40.7`
3. `v29.9`

## Notes

- These are quick 100-session Monte Carlo runs, so they are useful for fast comparison but not final statistical proof.
- The next useful step is a heavier Monte Carlo head-to-head between `v39.2` and `v40.7`.
