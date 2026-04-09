# Monte Carlo Robustness Report

- Output prefix: `v52_monte_carlo_run2`
- Bots: Traderv52.py, Traderv51.py

## Families

- `original_noise`: Original historical path with very mild execution-noise perturbations.
- `bootstrap_path`: Block-bootstrap of the historical path with no fill perturbation.
- `bootstrap_balanced`: Block-bootstrap with calibrated mild-to-moderate execution degradation.
- `bootstrap_stress`: Block-bootstrap with stressed execution assumptions.

## Baseline Replay

### Traderv51

- Combined total PnL: `29488.5000`
- Day -1: `14868.0000`
- Day -2: `14620.5000`

### Traderv52

- Combined total PnL: `29884.0000`
- Day -1: `15081.0000`
- Day -2: `14803.0000`

## Monte Carlo Summary

### Traderv51

- Overall samples: `12` | mean `24592.875` | p10 `17461.6` | cvar10 `16577.0` | std `4750.7815`
- Profile `all`: count `12`, mean `24592.875`, p10 `17461.6`, cvar10 `16577.0`
- Profile `plausible`: count `9`, mean `27058.9444`, p10 `24465.9`, cvar10 `23741.5`
- Profile `stress`: count `3`, mean `17194.6667`, p10 `16110.8`, cvar10 `15800.0`
- `bootstrap_balanced`: count `3`, mean `24487.1667`, p10 `23922.6`, cvar10 `23741.5`
- `bootstrap_path`: count `3`, mean `28231.1667`, p10 `26370.2`, cvar10 `26266.0`
- `bootstrap_stress`: count `3`, mean `17194.6667`, p10 `16110.8`, cvar10 `15800.0`
- `original_noise`: count `3`, mean `28458.5`, p10 `28301.3`, cvar10 `28252.5`

### Traderv52

- Overall samples: `12` | mean `24652.0417` | p10 `16947.7` | cvar10 `16784.0` | std `4716.17`
- Profile `all`: count `12`, mean `24652.0417`, p10 `16947.7`, cvar10 `16784.0`
- Profile `plausible`: count `9`, mean `27152.8333`, p10 `24722.0`, cvar10 `24064.0`
- Profile `stress`: count `3`, mean `17149.6667`, p10 `16748.0`, cvar10 `16724.0`
- `bootstrap_balanced`: count `3`, mean `24696.8333`, p10 `24228.5`, cvar10 `24064.0`
- `bootstrap_path`: count `3`, mean `28315.5`, p10 `26701.7`, cvar10 `26580.5`
- `bootstrap_stress`: count `3`, mean `17149.6667`, p10 `16748.0`, cvar10 `16724.0`
- `original_noise`: count `3`, mean `28446.1667`, p10 `27987.6`, cvar10 `27876.5`

## Comparison

- Primary: `Traderv52`
- Compare: `Traderv51`
- Shared samples: `12`
- Mean delta: `59.1667`
- Median delta: `123.25`
- P10 delta: `-579.6`
- Win rate: `0.5833`

- `bootstrap_balanced`: mean delta `209.6667`, p10 delta `-453.0`, win rate `0.6667`
- `bootstrap_path`: mean delta `84.3333`, p10 delta `-305.9`, win rate `0.6667`
- `bootstrap_stress`: mean delta `-45.0`, p10 delta `-541.2`, win rate `0.3333`
- `original_noise`: mean delta `-12.3333`, p10 delta `-564.1`, win rate `0.6667`

- Profile `all`: mean delta `59.1667`, p10 delta `-579.6`, win rate `0.5833`
- Profile `plausible`: mean delta `93.8889`, p10 delta `-616.4`, win rate `0.6667`
- Profile `stress`: mean delta `-45.0`, p10 delta `-541.2`, win rate `0.3333`
